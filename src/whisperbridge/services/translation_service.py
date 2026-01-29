"""
Translation Service for WhisperBridge.

This module provides API integration for text translation with
caching, error handling, and async processing.
"""

import asyncio
import hashlib
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

from loguru import logger
from tenacity import RetryError

from ..core.api_manager import get_api_manager
from ..services.config_service import config_service
from ..utils.language_utils import detect_language
from ..utils.translation_utils import (
    TranslationRequest,
    TranslationResponse,
    StyleRequest,
    format_translation_prompt,
    format_style_prompt,
    parse_gpt_response,
    validate_translation_response,
)
from ..core.config import get_deepl_identifier, requires_model_selection, is_llm_provider


class TranslationCache:
    """Thread-safe, in-memory, session-only LRU cache."""

    def __init__(self, max_size: int = 100):
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.RLock()

    def _get_cache_key(self, text: str, source_lang: str, target_lang: str, model: str) -> str:
        """Generate cache key from translation parameters."""
        content = f"{text}|{source_lang}|{target_lang}|{model}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def _evict_oldest(self):
        """Remove oldest cache entries when max size is reached."""
        while len(self._cache) >= self._max_size:
            key, _ = self._cache.popitem(last=False)
            logger.debug(f"Evicted old cache entry: {key}")

    def get(self, text: str, source_lang: str, target_lang: str, model: str) -> Optional[str]:
        """Get cached translation result."""
        with self._lock:
            key = self._get_cache_key(text, source_lang, target_lang, model)

            if key in self._cache:
                self._cache.move_to_end(key)
                logger.debug(f"Cache hit for key: {key}")
                return self._cache[key]

            return None

    def put(
        self,
        text: str,
        translated_text: str,
        source_lang: str,
        target_lang: str,
        model: str,
    ):
        """Store translation result in cache."""
        with self._lock:
            key = self._get_cache_key(text, source_lang, target_lang, model)

            self._cache[key] = translated_text
            self._evict_oldest()
            logger.debug(f"Cached translation for key: {key}")

    def clear(self):
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            logger.info("Translation cache cleared")

    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)


class TranslationService:
    """Main translation service with API integration."""

    def __init__(self):
        self._api_manager = get_api_manager()
        self._cache = TranslationCache(
            max_size=config_service.get_setting("max_cache_size"),
        )
        self._is_initialized = False

    def initialize(self) -> bool:
        """Initialize the translation service."""
        try:
            if not self._api_manager.is_initialized():
                logger.error("API manager not initialized")
                return False

            # Check if we have any API clients available
            has_clients = self._api_manager.has_clients()

            if not has_clients:
                logger.warning("No API clients available. Translation features will be disabled.")
                logger.info("To enable translation, configure your API key in settings.")
            else:
                logger.info("Translation service initialized with API clients")

            self._is_initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize translation service: {e}")
            return False

    def is_initialized(self) -> bool:
        """Check if service is initialized."""
        return self._is_initialized

    @property
    def is_available(self) -> bool:
        """Check if translation is available (initialized and has API clients)."""
        return self._is_initialized and self._api_manager.has_clients()

    def _make_response(
        self,
        *,
        success: bool,
        translated_text: Optional[str] = None,
        error_message: Optional[str] = None,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
        model: Optional[str] = None,
        cached: bool = False,
        tokens_used: int = 0,
    ) -> TranslationResponse:
        """Create a standardized TranslationResponse."""
        return TranslationResponse(
            success=success,
            translated_text=translated_text or "",
            error_message=error_message or "",
            source_lang=source_lang or "",
            target_lang=target_lang or "",
            model=model or "",
            cached=cached,
            tokens_used=tokens_used,
        )

    def _get_active_model(self) -> str:
        """
        Gets the currently configured model based on the selected API provider.
        Dynamically constructs the model setting key (e.g., 'openai_model').
        """
        provider = config_service.get_setting("api_provider")
        if not provider:
            raise ValueError("API provider is not configured in settings.")

        # Providers without model selection (e.g., DeepL) use fixed identifier
        if not requires_model_selection(str(provider)):
            return get_deepl_identifier()

        model_setting_key = f"{provider.lower()}_model"
        model = config_service.get_setting(model_setting_key)

        if not model:
            raise ValueError(
                f"Model for provider '{provider}' is not configured. "
                f"Expected setting: '{model_setting_key}'"
            )

        return model

    async def _determine_languages(self, text: str, ui_source_lang: Optional[str], ui_target_lang: Optional[str]) -> tuple[str, str]:
        """Determines the effective source and target languages for translation."""
        detected_lang = await self._detect_language_async(text) or "auto"

        settings = config_service.get_settings()
        swap_enabled = getattr(settings, "auto_swap_en_ru", False)

        # 1. Check for auto-swap feature
        if swap_enabled and detected_lang in ["en", "ru"]:
            source = detected_lang
            target = "ru" if detected_lang == "en" else "en"
            logger.debug(f"Applied auto-swap: {source} -> {target}")
            return source, target

        # 2. Use UI selection if auto-swap doesn't apply
        source = ui_source_lang or "auto"
        if source == "auto":
            source = detected_lang

        target = ui_target_lang or getattr(settings, "ui_target_language", "en")

        logger.debug(f"Languages determined from UI/settings: {source} -> {target}")
        return source, target

    async def translate_text_async(
        self,
        text: str,
        ui_source_lang: Optional[str] = None,
        ui_target_lang: Optional[str] = None,
        use_cache: bool = True,
    ) -> TranslationResponse:
        """Translate text asynchronously using API."""

        logger.info(f"Starting translation for text: '{text[:30]}...'")

        try:
            # Determine languages using the new helper
            source_lang, target_lang = await self._determine_languages(text, ui_source_lang, ui_target_lang)

            # Get model and cache settings once
            intended_model = self._get_active_model()
            cache_enabled = use_cache and config_service.get_setting("translation_cache_enabled")

            # Check cache
            if cache_enabled:
                cached_result = self._cache.get(text, source_lang, target_lang, intended_model)
                if cached_result:
                    logger.info("Translation found in cache")
                    return self._make_response(
                        success=True,
                        translated_text=cached_result,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        model=intended_model,
                        cached=True,
                    )
                else:
                    logger.info("Translation not found in cache.")

            # Prepare and execute translation request
            current_settings = config_service.get_settings()
            request = TranslationRequest(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                system_prompt=current_settings.system_prompt,
                model=intended_model,
            )

            response = await self._call_gpt_api_async(request)

            # Validate response
            if not validate_translation_response(response):
                logger.error(f"Invalid translation response format: {response}")
                raise ValueError("Invalid translation response format")

            # Cache successful result
            if cache_enabled and response.success:
                self._cache.put(
                    text,
                    response.translated_text,
                    source_lang,
                    target_lang,
                    response.model,
                )

            return response

        except RetryError as e:
            # Unwrap the original exception from the RetryError
            original_error = e.last_attempt.exception()
            error_msg = str(original_error) if original_error else str(e)
            logger.error(f"Translation failed (retries exhausted): {error_msg}")
            return self._make_response(
                success=False,
                error_message=error_msg,
                source_lang=source_lang,
                target_lang=target_lang,
            )

        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return self._make_response(
                success=False,
                error_message=str(e),
                source_lang=source_lang,
                target_lang=target_lang,
            )

    async def style_text_async(
        self,
        text: str,
        style_name: str,
        use_cache: bool = True,
    ) -> TranslationResponse:
        """Rewrite text in a selected style using the same API pipeline as translation."""
        logger.info(f"Starting style rewrite for text: '{text[:30]}...' with style '{style_name}'")

        try:
            # Get model and cache settings once
            intended_model = self._get_active_model()
            stylist_cache_enabled = use_cache and config_service.get_setting("stylist_cache_enabled")

            # Resolve style preset
            settings = config_service.get_settings()
            styles = getattr(settings, "text_styles", []) or []
            style_entry = None
            for s in styles:
                try:
                    if (s.get("name") or "").strip().lower() == style_name.strip().lower():
                        style_entry = s
                        break
                except Exception:
                    continue
            if not style_entry and styles:
                style_entry = styles[0]  # fallback to first preset if provided style not found
                logger.warning(f"Style '{style_name}' not found. Falling back to preset '{style_entry.get('name','')}'.")
                style_name = style_entry.get("name", style_name)
            if not style_entry:
                raise ValueError("No style presets configured. Please add styles in settings.")

            style_prompt = style_entry.get("prompt", "").strip()
            if not style_prompt:
                raise ValueError(f"Selected style '{style_name}' has empty prompt")

            request = StyleRequest(
                text=text,
                style_name=style_name,
                style_prompt=style_prompt,
                model=intended_model,
            )

            # Check cache
            if stylist_cache_enabled:
                cached_result = self._cache.get(text, f"style:{style_name}", "-", intended_model)
                if cached_result:
                    logger.info("Style result found in cache")
                    return self._make_response(
                        success=True,
                        translated_text=cached_result,
                        source_lang="style",
                        target_lang=style_name,
                        model=intended_model,
                        cached=True,
                    )
                else:
                    logger.info("Style result not found in cache.")

            if not self._api_manager.is_initialized():
                raise RuntimeError("API manager not initialized")

            if not self._api_manager.has_clients():
                logger.info("No API clients configured; returning empty styled text")
                return self._make_response(
                    success=True,
                    translated_text="",
                    source_lang="style",
                    target_lang=style_name,
                    model=intended_model,
                )

            # Enforce "respond in the same language as input" policy for stylist mode
            detected_lang = await self._detect_language_async(text)
            language_policy_lines = [
                "Important language policy:",
                "- Detect the input language and return the rewritten text in the same language.",
                "- Do not translate into another language.",
                "- Output only the rewritten text without explanations.",
            ]
            if detected_lang:
                language_policy_lines.append(f"- Input language code: {detected_lang}. Respond in {detected_lang}.")

            language_policy = "\n".join(language_policy_lines)

            # Get stylist temperature from config
            try:
                val = config_service.get_setting("llm_temperature_stylist")
                stylist_temp = round(float(val if val is not None else 1.2), 2)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse stylist temperature from config, using default 1.2. Error: {e}")
                stylist_temp = 1.2
            
            messages = [
                {"role": "system", "content": f"{style_prompt}\n\n{language_policy}"},
                {"role": "user", "content": format_style_prompt(request)},
            ]
            
            logger.debug(f"Stylist temperature: {stylist_temp}")
            
            response, final_model = self._api_manager.make_translation_request(
                messages=messages, model_hint=intended_model, temperature=stylist_temp
            )

            raw_text = response.choices[0].message.content
            styled_text = parse_gpt_response(raw_text).strip()

            # Cache successful result (if we got here, the operation was successful)
            if stylist_cache_enabled:
                self._cache.put(
                    text,
                    styled_text,
                    f"style:{style_name}",
                    "-",  # target placeholder for styling flow
                    final_model,
                )

            return self._make_response(
                success=True,
                translated_text=styled_text,
                source_lang="style",
                target_lang=style_name,
                model=final_model,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )

        except RetryError as e:
            # Unwrap the original exception from the RetryError
            original_error = e.last_attempt.exception()
            error_msg = str(original_error) if original_error else str(e)
            logger.error(f"Styling failed (retries exhausted): {error_msg}")
            return self._make_response(
                success=False,
                error_message=error_msg,
                source_lang="style",
                target_lang=style_name,
            )

        except Exception as e:
            logger.error(f"Styling failed: {e}")
            return self._make_response(
                success=False,
                error_message=str(e),
                source_lang="style",
                target_lang=style_name,
            )

    def detect_language_sync(self, text: str) -> Optional[str]:
        """Detect language of the input text synchronously."""
        try:
            return detect_language(text)
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return None

    async def _detect_language_async(self, text: str) -> Optional[str]:
        """Detect language of the input text asynchronously."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.detect_language_sync, text)
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return None

    async def _call_gpt_api_async(self, request: TranslationRequest) -> TranslationResponse:
        """Make actual API call using the API manager's logic."""
        if not self._api_manager.is_initialized():
            raise RuntimeError("API manager not initialized")

        # The API manager now centralizes the logic for client availability.
        if not self._api_manager.has_clients():
            logger.info("No API clients configured; returning empty translation")
            return self._make_response(
                success=True,
                translated_text="",
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                model=(request.model or ""),
            )

        try:
            # Determine provider and prepare request accordingly
            provider_name = (config_service.get_setting("api_provider") or "openai").strip().lower()

            if not is_llm_provider(provider_name):
                # Non-LLM flow (e.g., DeepL): no system prompts; send raw user text and pass langs explicitly
                messages = [
                    {"role": "user", "content": request.text},
                ]
                # Map 'auto' to None to let DeepL auto-detect
                source_arg = None if (request.source_lang or "auto") == "auto" else request.source_lang
                target_arg = request.target_lang

                response, final_model = self._api_manager.make_translation_request(
                    messages=messages,
                    model_hint=get_deepl_identifier(),
                    target_lang=target_arg,
                    source_lang=source_arg,
                )

                raw_text = response.choices[0].message.content
                translated_text = (raw_text or "").strip()
            else:
                # LLM flow (OpenAI/Google): use system prompt + formatted user prompt
                messages = [
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": format_translation_prompt(request)},
                ]

                # Delegate provider selection, model adjustment, and API call to the manager
                response, final_model = self._api_manager.make_translation_request(
                    messages=messages, model_hint=request.model
                )

                # Extract translation from response
                raw_text = response.choices[0].message.content
                translated_text = parse_gpt_response(raw_text).strip()

            return self._make_response(
                success=True,
                translated_text=translated_text,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                model=final_model,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )

        except Exception as e:
            logger.error(f"API call failed: {e}")
            raise

    def translate_text_sync(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
        use_cache: bool = True,
    ) -> TranslationResponse:
        """Synchronous wrapper for translate_text_async."""
        try:
            # asyncio.run() handles the event loop management automatically.
            return asyncio.run(
                self.translate_text_async(text, source_lang, target_lang, use_cache)
            )
        except Exception as e:
            logger.error(f"Synchronous translation failed: {e}")
            return self._make_response(
                success=False,
                error_message=str(e),
                source_lang=source_lang,
                target_lang=target_lang,
            )

    def style_text_sync(
        self,
        text: str,
        style_name: str,
        use_cache: bool = True,
    ) -> TranslationResponse:
        """Synchronous wrapper for style_text_async."""
        try:
            return asyncio.run(self.style_text_async(text, style_name, use_cache))
        except Exception as e:
            logger.error(f"Synchronous styling failed: {e}")
            return self._make_response(
                success=False,
                error_message=str(e),
                source_lang="style",
                target_lang=style_name,
            )

    def clear_cache(self):
        """Clear translation cache."""
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": self._cache.size(),
            "max_size": self._cache._max_size,
            "enabled": config_service.get_setting("translation_cache_enabled"),
        }

    def shutdown(self):
        """Shutdown the translation service."""
        self._is_initialized = False
        logger.info("Translation service shutdown")


# Global translation service instance
_translation_service: Optional[TranslationService] = None
_service_lock = threading.RLock()


def get_translation_service(initialize: bool = False) -> TranslationService:
    """
    Get the global translation service instance.
    
    Args:
        initialize: If True, initialize the service if not already initialized.
    
    Returns:
        The global TranslationService instance.
        
    Raises:
        RuntimeError: If initialize=True and initialization fails.
    """
    global _translation_service
    with _service_lock:
        if _translation_service is None:
            _translation_service = TranslationService()
        
        if initialize and not _translation_service.is_initialized():
            if not _translation_service.initialize():
                raise RuntimeError("Failed to initialize translation service")
        
        return _translation_service


def init_translation_service() -> TranslationService:
    """Initialize and return the translation service instance (legacy wrapper)."""
    return get_translation_service(initialize=True)
