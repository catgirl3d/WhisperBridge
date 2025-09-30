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

from ..core.api_manager import get_api_manager
from ..services.config_service import config_service
from ..utils.language_utils import detect_language
from ..utils.translation_utils import (
    TranslationRequest,
    TranslationResponse,
    format_translation_prompt,
    parse_gpt_response,
    validate_translation_response,
)


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
        translated_text: str = "",
        error_message: Optional[str] = None,
        source_lang: str,
        target_lang: str,
        model: str = "",
        cached: bool = False,
        tokens_used: int = 0,
    ) -> TranslationResponse:
        """Create a standardized TranslationResponse."""
        return TranslationResponse(
            success=success,
            translated_text=translated_text,
            error_message=error_message,
            source_lang=source_lang,
            target_lang=target_lang,
            model=model,
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

        model_setting_key = f"{provider.lower()}_model"
        model = config_service.get_setting(model_setting_key)

        if not model:
            raise ValueError(
                f"Model for provider '{provider}' is not configured. "
                f"Expected setting: '{model_setting_key}'"
            )

        return model

    async def translate_text_async(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
        use_cache: bool = True,
    ) -> TranslationResponse:
        """Translate text asynchronously using API."""
        # Normalize defaults once
        source_lang = source_lang or "auto"
        target_lang = target_lang or "en"
        
        logger.info(f"Starting translation for text: '{text[:30]}...'")
        
        try:
            # Auto-detect source language if needed
            if source_lang == "auto":
                detected_lang = await self._detect_language_async(text)
                source_lang = detected_lang or "en"
                logger.debug(f"Auto-detected source language: {source_lang}")

            # Get model and cache settings once
            intended_model = self._get_active_model()
            cache_enabled = use_cache and config_service.get_setting("cache_enabled")

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

        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return self._make_response(
                success=False,
                error_message=str(e),
                source_lang=source_lang,
                target_lang=target_lang,
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
            # Format messages for GPT
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

    def clear_cache(self):
        """Clear translation cache."""
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": self._cache.size(),
            "max_size": self._cache._max_size,
            "enabled": config_service.get_setting("cache_enabled"),
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
