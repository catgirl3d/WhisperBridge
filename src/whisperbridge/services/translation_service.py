"""
Translation Service for WhisperBridge.

This module provides GPT API integration for text translation with
caching, error handling, and async processing.
"""

import asyncio
import hashlib
import json
import threading
import time
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

from loguru import logger

from ..core.config import settings
from ..core.api_manager import get_api_manager, APIProvider
from ..utils.api_utils import (
    format_translation_prompt,
    validate_translation_response,
    detect_language,
    parse_gpt_response,
    TranslationRequest,
    TranslationResponse
)
from ..services.config_service import config_service


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
        return hashlib.md5(content.encode('utf-8')).hexdigest()

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
            sorted_entries = sorted(
                self._cache.items(),
                key=lambda x: x[1].timestamp
            )
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

    def put(self, text: str, translated_text: str, source_lang: str,
            target_lang: str, model: str, ttl: Optional[int] = None):
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
                ttl=ttl or self._default_ttl
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
            max_size=settings.max_cache_size,
            default_ttl=settings.cache_ttl
        )
        self._executor = ThreadPoolExecutor(max_workers=settings.thread_pool_size)
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
                from ..core.api_manager import APIProvider
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
        use_cache: bool = True
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
            if use_cache and settings.cache_enabled:
                cached_result = self._cache.get(text, source_lang, target_lang, settings.model)
                if cached_result:
                    logger.info("Translation found in cache.")
                    return TranslationResponse(
                        success=True,
                        translated_text=cached_result,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        model=settings.model,
                        cached=True
                    )
                else:
                    logger.info("Translation not found in cache.")

            # Prepare translation request
            request = TranslationRequest(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                system_prompt=current_settings.system_prompt,
                model=current_settings.model
            )

            # Make API call
            logger.debug(f"Preparing to call GPT API with request: {request}")
            response = await self._call_gpt_api_async(request)
            logger.debug(f"Received response from API call: {response}")

            # Validate response
            if not validate_translation_response(response):
                logger.error(f"Invalid translation response format: {response}")
                raise ValueError("Invalid translation response format")

            # Cache result
            if use_cache and settings.cache_enabled:
                self._cache.put(text, response.translated_text, source_lang,
                              target_lang, settings.model)

            return response

        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return TranslationResponse(
                success=False,
                error_message=str(e),
                source_lang=source_lang or "auto",
                target_lang=target_lang or "en"
            )

    async def _detect_language_async(self, text: str) -> Optional[str]:
        """Detect language of the input text asynchronously."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self._executor,
                detect_language,
                text
            )
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return None

    async def _call_gpt_api_async(self, request: TranslationRequest) -> TranslationResponse:
        """Make actual GPT API call."""
        if not self._api_manager.is_initialized():
            raise RuntimeError("API manager not initialized")

        # Check if we have API clients available
        from ..core.api_manager import APIProvider
        if not self._api_manager._clients:
            raise RuntimeError("No API clients available. Please configure your API key in settings.")

        try:
            # Format messages for GPT
            messages = [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": format_translation_prompt(request)}
            ]

            # Prepare API call parameters with provider-specific optimizations
            api_params = {
                "model": request.model,
                "messages": messages,
                "temperature": 1,  
                "max_completion_tokens": 2048,
            }
            
            # Apply OpenAI-specific optimizations only for OpenAI provider
            if settings.api_provider == "openai":
                # Add GPT-5 specific optimizations if using GPT-5 model
                if request.model.startswith(("gpt-5", "chatgpt")):
                    api_params["extra_body"] = {
                        "reasoning_effort": "minimal",  # Minimize latency for translation tasks
                        "verbosity": "low"  # Concise output for translation
                    }
                    logger.debug(f"Using OpenAI GPT-5 optimizations: reasoning_effort=minimal, verbosity=low")
                elif request.model.startswith("gpt-"):
                    # For older GPT models, just use reasoning_effort if supported
                    api_params["extra_body"] = {"reasoning_effort": "minimal"}
                    logger.debug(f"Using OpenAI GPT optimizations: reasoning_effort=minimal")
                else:
                    logger.debug(f"Using OpenAI without special optimizations")
            else:
                # For other providers (Google, etc.), don't add OpenAI-specific parameters
                logger.debug(f"Using provider {settings.api_provider} without OpenAI-specific optimizations")

            logger.debug(f"Final API parameters for {settings.api_provider}: {api_params}")

            # Determine the API provider to use
            if settings.api_provider == "openai":
                api_provider = APIProvider.OPENAI
            elif settings.api_provider == "azure_openai":
                api_provider = APIProvider.AZURE_OPENAI
            else:
                # Default to OpenAI if provider not recognized
                api_provider = APIProvider.OPENAI
                logger.warning(f"Unknown API provider: {settings.api_provider}, defaulting to OpenAI")

            # Make API call through manager (includes retry logic)
            response = await self._api_manager.make_request_async(
                api_provider,
                **api_params
            )

            # Extract translation from response (clean common GPT prefixes)
            raw_text = response.choices[0].message.content
            translated_text = parse_gpt_response(raw_text).strip()
       
            return TranslationResponse(
                success=True,
                translated_text=translated_text,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                model=request.model,
                tokens_used=response.usage.total_tokens if response.usage else 0
            )

        except Exception as e:
            logger.error(f"API call failed: {e}")
            raise

    def translate_text_sync(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
        use_cache: bool = True
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
                target_lang=target_lang or "en"
            )

    def clear_cache(self):
        """Clear translation cache."""
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": self._cache.size(),
            "max_size": settings.max_cache_size,
            "enabled": settings.cache_enabled
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