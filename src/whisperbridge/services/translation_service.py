"""
Translation Service for WhisperBridge.

This module provides GPT API integration for text translation with
caching, error handling, and async processing.
"""

import asyncio
import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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


@dataclass
class TranslationCacheEntry:
    """Cache entry for translation results."""

    text_hash: str
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    model: str
    timestamp: float
    ttl: int


class TranslationCache:
    """Thread-safe translation cache with TTL support."""

    def __init__(self, max_size: int = 100, default_ttl: int = 3600):
        self._cache: Dict[str, TranslationCacheEntry] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.RLock()

    def _get_cache_key(self, text: str, source_lang: str, target_lang: str, model: str) -> str:
        """Generate cache key from translation parameters."""
        content = f"{text}|{source_lang}|{target_lang}|{model}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def _is_expired(self, entry: TranslationCacheEntry) -> bool:
        """Check if cache entry is expired."""
        return time.time() - entry.timestamp > entry.ttl

    def _cleanup_expired(self):
        """Remove expired cache entries."""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if current_time - entry.timestamp > entry.ttl
        ]
        for key in expired_keys:
            del self._cache[key]
            logger.debug(f"Removed expired cache entry: {key}")

    def _evict_oldest(self):
        """Remove oldest cache entries when max size is reached."""
        if len(self._cache) >= self._max_size:
            # Sort by timestamp and remove oldest
            sorted_entries = sorted(self._cache.items(), key=lambda x: x[1].timestamp)
            to_remove = len(self._cache) - self._max_size + 1
            for key, _ in sorted_entries[:to_remove]:
                del self._cache[key]
                logger.debug(f"Evicted old cache entry: {key}")

    def get(self, text: str, source_lang: str, target_lang: str, model: str) -> Optional[str]:
        """Get cached translation result."""
        with self._lock:
            self._cleanup_expired()
            key = self._get_cache_key(text, source_lang, target_lang, model)

            entry = self._cache.get(key)
            if entry and not self._is_expired(entry):
                logger.debug(f"Cache hit for key: {key}")
                return entry.translated_text

            return None

    def put(
        self,
        text: str,
        translated_text: str,
        source_lang: str,
        target_lang: str,
        model: str,
        ttl: Optional[int] = None,
    ):
        """Store translation result in cache."""
        with self._lock:
            key = self._get_cache_key(text, source_lang, target_lang, model)

            entry = TranslationCacheEntry(
                text_hash=key,
                source_text=text,
                translated_text=translated_text,
                source_lang=source_lang,
                target_lang=target_lang,
                model=model,
                timestamp=time.time(),
                ttl=ttl or self._default_ttl,
            )

            self._cache[key] = entry
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
            self._cleanup_expired()
            return len(self._cache)


class TranslationService:
    """Main translation service with GPT API integration."""

    def __init__(self):
        self._api_manager = get_api_manager()
        self._cache = TranslationCache(
            max_size=config_service.get_setting("max_cache_size"),
            default_ttl=config_service.get_setting("cache_ttl"),
        )
        self._executor = ThreadPoolExecutor(
            max_workers=config_service.get_setting("thread_pool_size")
        )
        self._lock = threading.RLock()
        self._is_initialized = False

    def initialize(self) -> bool:
        """Initialize the translation service."""
        with self._lock:
            try:
                if not self._api_manager.is_initialized():
                    logger.error("API manager not initialized")
                    return False

                # Check if we have any API clients available
                has_clients = bool(self._api_manager._clients)

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

    async def translate_text_async(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
        use_cache: bool = True,
    ) -> TranslationResponse:
        """Translate text asynchronously using GPT API."""
        logger.info(f"Starting translation for text: '{text[:30]}...'")
        logger.debug(f"Initial translate_text_async args: text='{text}', source_lang='{source_lang}', target_lang='{target_lang}', use_cache='{use_cache}'")
        try:
            # Use settings defaults if not specified
            current_settings = config_service.get_settings()
            logger.debug(f"Loaded settings in translate_text_async. System prompt: '{current_settings.system_prompt}'")
            # Legacy language settings removed - languages must be explicitly provided
            if source_lang is None:
                source_lang = "auto"
            if target_lang is None:
                target_lang = "en"  # Default fallback
            logger.debug(f"Resolved languages: source='{source_lang}', target='{target_lang}'")

            # Auto-detect source language if needed
            if source_lang == "auto":
                detected_lang = await self._detect_language_async(text)
                source_lang = detected_lang or "en"
                logger.debug(f"Auto-detected source language: {source_lang}")

            # Check cache first
            if use_cache and config_service.get_setting("cache_enabled"):
                provider = config_service.get_setting("api_provider")
                if provider == "openai":
                    model = config_service.get_setting("openai_model")
                else:
                    model = config_service.get_setting("google_model")
                
                cached_result = self._cache.get(text, source_lang, target_lang, model)
                if cached_result:
                    logger.info("Translation found in cache.")
                    return TranslationResponse(
                        success=True,
                        translated_text=cached_result,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        model=model,
                        cached=True,
                    )
                else:
                    logger.info("Translation not found in cache.")

            # Prepare translation request
            provider = config_service.get_setting("api_provider")
            if provider == "openai":
                model = current_settings.openai_model
            else:
                model = current_settings.google_model

            request = TranslationRequest(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                system_prompt=current_settings.system_prompt,
                model=model,
            )
            logger.debug(f"Preparing to call GPT API with request: {request}")
            response = await self._call_gpt_api_async(request)
            logger.debug(f"Received response from API call: {response}")

            # Validate response
            if not validate_translation_response(response):
                logger.error(f"Invalid translation response format: {response}")
                raise ValueError("Invalid translation response format")

            # Cache result
            if use_cache and config_service.get_setting("cache_enabled"):
                provider = config_service.get_setting("api_provider")
                if provider == "openai":
                    model = config_service.get_setting("openai_model")
                else:
                    model = config_service.get_setting("google_model")

                self._cache.put(
                    text,
                    response.translated_text,
                    source_lang,
                    target_lang,
                    model,
                )

            return response

        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return TranslationResponse(
                success=False,
                error_message=str(e),
                source_lang=source_lang or "auto",
                target_lang=target_lang or "en",
            )

    async def _detect_language_async(self, text: str) -> Optional[str]:
        """Detect language of the input text asynchronously."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(self._executor, detect_language, text)
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return None

    async def _call_gpt_api_async(self, request: TranslationRequest) -> TranslationResponse:
        """Make actual GPT API call with automatic provider/model fallback."""
        if not self._api_manager.is_initialized():
            raise RuntimeError("API manager not initialized")

        # Check if we have API clients available
        from ..core.api_manager import APIProvider

        if not self._api_manager._clients:
            logger.info("No API clients configured; returning empty translation")
            return TranslationResponse(
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

            # Resolve provider with fallback if requested one isn't configured
            requested_provider_name = (config_service.get_setting("api_provider") or "openai").strip().lower()
            available = set(self._api_manager._clients.keys())

            def _name_to_enum(name: str) -> APIProvider:
                return APIProvider.OPENAI if name == "openai" else APIProvider.GOOGLE

            # Pick provider: prefer requested if configured, else fallback to the other if available
            if requested_provider_name == "openai":
                if APIProvider.OPENAI in available:
                    selected_provider = APIProvider.OPENAI
                elif APIProvider.GOOGLE in available:
                    logger.warning("Requested OpenAI provider not configured; falling back to Google")
                    requested_provider_name = "google"
                    selected_provider = APIProvider.GOOGLE
                else:
                    raise RuntimeError("No configured API provider available. Set OpenAI or Google API key in Settings.")
            elif requested_provider_name == "google":
                if APIProvider.GOOGLE in available:
                    selected_provider = APIProvider.GOOGLE
                elif APIProvider.OPENAI in available:
                    logger.warning("Requested Google provider not configured; falling back to OpenAI")
                    requested_provider_name = "openai"
                    selected_provider = APIProvider.OPENAI
                else:
                    raise RuntimeError("No configured API provider available. Set OpenAI or Google API key in Settings.")
            else:
                # Unknown setting; prefer any available provider (OpenAI first)
                selected_provider = APIProvider.OPENAI if APIProvider.OPENAI in available else (
                    APIProvider.GOOGLE if APIProvider.GOOGLE in available else None
                )
                if not selected_provider:
                    raise RuntimeError("No configured API provider available. Set OpenAI or Google API key in Settings.")
                requested_provider_name = selected_provider.value
                logger.warning(f"Unknown provider '{requested_provider_name}', using {selected_provider.value}")

            # Adjust model if it doesn't fit the selected provider
            final_model = (request.model or "").strip()
            try:
                if selected_provider == APIProvider.GOOGLE:
                    if not final_model.lower().startswith("gemini-"):
                        models, _ = self._api_manager.get_available_models_sync(APIProvider.GOOGLE)
                        final_model = (models[0] if models else "gemini-1.5-flash-8b")
                        logger.debug(f"Switched to GOOGLE-compatible model: {final_model}")
                elif selected_provider == APIProvider.OPENAI:
                    lm = final_model.lower()
                    if (not lm) or lm.startswith("gemini-"):
                        models, _ = self._api_manager.get_available_models_sync(APIProvider.OPENAI)
                        final_model = (models[0] if models else "gpt-4.1-mini")
                        logger.debug(f"Switched to OPENAI-compatible model: {final_model}")
            except Exception as e:
                logger.debug(f"Model compatibility adjustment failed, using original model '{final_model}': {e}")

            # Prepare API call parameters (baseline)
            api_params = {
                "model": final_model,
                "messages": messages,
                "temperature": 1,
                "max_completion_tokens": 2048,
            }

            # Apply OpenAI-specific optimizations only for OpenAI-selected provider
            if selected_provider == APIProvider.OPENAI:
                if final_model.startswith(("gpt-5", "chatgpt")):
                    api_params["extra_body"] = {
                        "reasoning_effort": "minimal",
                        "verbosity": "low",
                    }
                    logger.debug("Using OpenAI GPT-5 optimizations: reasoning_effort=minimal, verbosity=low")
                elif final_model.startswith("gpt-"):
                    api_params["extra_body"] = {"reasoning_effort": "minimal"}
                    logger.debug("Using OpenAI GPT optimizations: reasoning_effort=minimal")
            else:
                logger.debug(f"Using provider {requested_provider_name} without OpenAI-specific optimizations")

            logger.debug(f"Final API parameters for {requested_provider_name}: {api_params}")

            # Make API call through manager (includes retry logic)
            response = self._api_manager.make_request_sync(selected_provider, **api_params)

            # Extract translation from response (clean common GPT prefixes)
            raw_text = response.choices[0].message.content
            translated_text = parse_gpt_response(raw_text).strip()

            return TranslationResponse(
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
            # Get or create event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Run async translation
            return loop.run_until_complete(
                self.translate_text_async(text, source_lang, target_lang, use_cache)
            )

        except Exception as e:
            logger.error(f"Synchronous translation failed: {e}")
            return TranslationResponse(
                success=False,
                error_message=str(e),
                source_lang=source_lang or "auto",
                target_lang=target_lang or "en",
            )

    def clear_cache(self):
        """Clear translation cache."""
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": self._cache.size(),
            "max_size": config_service.get_setting("max_cache_size"),
            "enabled": config_service.get_setting("cache_enabled"),
        }

    def shutdown(self):
        """Shutdown the translation service."""
        with self._lock:
            if self._executor:
                self._executor.shutdown(wait=True)
            self._is_initialized = False
            logger.info("Translation service shutdown")


# Global translation service instance
_translation_service: Optional[TranslationService] = None
_service_lock = threading.RLock()


def get_translation_service() -> TranslationService:
    """Get the global translation service instance."""
    global _translation_service
    with _service_lock:
        if _translation_service is None:
            _translation_service = TranslationService()
        return _translation_service


def init_translation_service() -> TranslationService:
    """Initialize and return the translation service instance."""
    service = get_translation_service()
    if not service.is_initialized():
        if not service.initialize():
            raise RuntimeError("Failed to initialize translation service")
    return service
