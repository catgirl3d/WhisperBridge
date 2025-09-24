"""
API Manager for WhisperBridge.

This module provides centralized API management with authentication,
error handling, retry logic, and usage monitoring.
"""

import asyncio
import concurrent.futures
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import openai
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..services.config_service import ConfigService, config_service
from .config import (
    ensure_config_dir,
    validate_api_key_format,
)


def requires_initialization(func):
    """Decorator to ensure API manager is initialized before method execution."""
    if asyncio.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            if not self.is_initialized():
                raise RuntimeError("API manager not initialized")
            return await func(self, *args, **kwargs)
        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(self, *args, **kwargs):
            if not self.is_initialized():
                raise RuntimeError("API manager not initialized")
            return func(self, *args, **kwargs)
        return sync_wrapper


class APIProvider(Enum):
    """Supported API providers."""

    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"


class APIErrorType(Enum):
    """Types of API errors."""

    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    QUOTA_EXCEEDED = "quota_exceeded"
    NETWORK = "network"
    TIMEOUT = "timeout"
    INVALID_REQUEST = "invalid_request"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


@dataclass
class APIUsage:
    """API usage statistics."""

    requests_count: int = 0
    tokens_used: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    last_request_time: Optional[datetime] = None
    rate_limit_hits: int = 0


@dataclass
class APIError:
    """API error information."""

    error_type: APIErrorType
    message: str
    status_code: Optional[int] = None
    retry_after: Optional[int] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class APIManager:
    """Centralized API manager for handling authentication and requests."""

    # Default GPT models list to avoid duplication
    DEFAULT_GPT_MODELS = ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o-mini"]
    
    def __init__(self, config_service: ConfigService):
        """
        Initialize the APIManager.

        Args:
            config_service: The application's configuration service.
        """
        self.config_service = config_service
        self._clients: Dict[APIProvider, Any] = {}
        self._usage: Dict[APIProvider, APIUsage] = {}
        self._lock = threading.RLock()
        self._error_handlers: List[Callable[[APIError], None]] = []
        self._is_initialized = False
        self._model_cache: Dict[APIProvider, tuple] = {}  # (models_list, timestamp)
        self._model_cache_ttl = 1209600  # 2 weeks cache

    def _get_model_cache_path(self) -> Path:
        """Return path to persistent model cache file."""
        config_dir = ensure_config_dir()
        return config_dir / "models_cache.json"

    def _load_model_cache_from_disk(self):
        """Load persistent model cache into memory if present."""
        path = self._get_model_cache_path()
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        with self._lock:
            # raw expected as {provider_value: {"models": [...], "timestamp": ts}}
            for prov_str, entry in raw.items():
                try:
                    prov = APIProvider(prov_str)
                except Exception:
                    continue
                models = entry.get("models", [])
                ts = entry.get("timestamp", 0)
                self._model_cache[prov] = (models, ts)
            logger.info("Loaded model cache from disk")

    def _save_model_cache_to_disk(self):
        """Persist in-memory model cache to disk."""
        path = self._get_model_cache_path()
        data = {}
        with self._lock:
            for prov, (models, ts) in self._model_cache.items():
                data[prov.value] = {"models": models, "timestamp": ts}
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug("Saved model cache to disk")

    def _cleanup_old_cache_files(self):
        """Remove cache files older than TTL."""
        try:
            path = self._get_model_cache_path()
            if path.exists():
                file_age = time.time() - path.stat().st_mtime
                if file_age > self._model_cache_ttl:
                    path.unlink()
                    logger.debug("Removed old model cache file")
        except Exception as e:
            logger.debug(f"Failed to cleanup old cache files: {e}")

    def _handle_cache_operation(self, operation: str, operation_func: Callable):
        """Universal cache operation handler with error logging."""
        try:
            return operation_func()
        except Exception as e:
            logger.warning(f"Failed to {operation} model cache: {e}")
            return None

    def _cache_models_and_persist(self, provider: APIProvider, models: List[str]) -> None:
        """Cache models and persist to disk in one operation."""
        with self._lock:
            self._model_cache[provider] = (models, time.time())
        self._handle_cache_operation("persist", self._save_model_cache_to_disk)

    def _initialize_cache_safely(self):
        """Safely initialize model cache with error handling."""
        def load_cache():
            self._load_model_cache_from_disk()
            self._cleanup_old_cache_files()

        self._handle_cache_operation("load cache during initialization", load_cache)

    def _validate_model_list(self, models: List[str]) -> bool:
        """Validate that model list is not empty and contains valid strings."""
        if not models:
            return False
        return all(isinstance(model, str) and model.strip() for model in models)

    def _get_default_models(self) -> List[str]:
        """Get default model list with optional configuration override."""
        try:
            # Check for custom models in configuration
            custom_models = self.config_service.get_setting("default_models", None)
            if custom_models and isinstance(custom_models, list) and self._validate_model_list(custom_models):
                logger.debug(f"Using custom default models from config: {custom_models}")
                return custom_models.copy()
        except Exception as e:
            logger.warning(f"Failed to get custom default models from config: {e}")
        
        # Fallback to built-in default models
        logger.debug(f"Using built-in default models: {self.DEFAULT_GPT_MODELS}")
        return self.DEFAULT_GPT_MODELS.copy()

    def _initialize_providers(self):
        """Initialize configured API providers. Returns True for any successful initialization."""
        provider = self.config_service.get_setting("api_provider")
        if provider == "openai":
            self._init_openai_provider()
        elif provider == "azure_openai":
            self._init_azure_provider()
        else:
            logger.warning(f"Unknown API provider: {provider}")

    def _init_openai_provider(self):
        """Initialize OpenAI provider with graceful degradation."""
        api_key = self.config_service.get_setting("openai_api_key")
        if not api_key:
            logger.warning("OpenAI API key not configured. Translation features will be disabled.")
            logger.info("To enable translation, set your OpenAI API key in the settings.")
            # Don't fail initialization - allow the app to run without API
            return

        # Validate API key format
        if not validate_api_key_format(api_key):
            logger.error("Invalid OpenAI API key format")
            logger.info("Please check your OpenAI API key format (should start with 'sk-')")
            # Don't fail initialization - allow the app to run without API
            return

        # Create client only if key exists and is valid
        self._clients[APIProvider.OPENAI] = openai.AsyncOpenAI(
            api_key=api_key,
            timeout=self.config_service.get_setting("api_timeout"),
        )
        self._usage[APIProvider.OPENAI] = APIUsage()
        logger.info("OpenAI client initialized")

    def _init_azure_provider(self):
        """Initialize Azure OpenAI provider."""
        # Azure configuration would go here
        logger.warning("Azure OpenAI not yet implemented")
        # Don't fail initialization - allow the app to run without API

    def _finalize_initialization(self):
        """Finalize initialization with consistent status setting and cache loading."""
        # Allow initialization even without API clients
        # The app can still run OCR and other features
        self._is_initialized = True
        
        # Load any persistent model cache from disk so first-run UI can use it
        self._initialize_cache_safely()

        if self._clients:
            logger.info("API manager initialized successfully with clients")
        else:
            logger.info("API manager initialized (no API clients - translation features disabled)")

    def _log_initialization_status(self):
        """Log current initialization status for debugging."""
        provider = self.config_service.get_setting("api_provider")
        logger.debug(f"API Manager status - Provider: {provider}, Initialized: {self._is_initialized}")
        logger.debug(f"Cache status - Entries: {len(self._model_cache)}")

    def _get_fallback_models(self, provider: APIProvider) -> tuple[List[str], str]:
        """Get fallback models with caching."""
        fallback_models = self._get_default_models()
        self._cache_models_and_persist(provider, fallback_models)
        return fallback_models, "fallback"

    def initialize(self) -> bool:
        """Initialize API manager with configured providers."""
        with self._lock:
            try:
                self._initialize_providers()
                self._finalize_initialization()
                return True
            except Exception as e:
                logger.error(f"Failed to initialize API manager: {e}")
                # Still allow initialization even if there are errors
                self._is_initialized = True
                logger.info("API manager initialized with errors (limited functionality)")
                # Try loading cache even on errors to provide offline model list
                self._initialize_cache_safely()
                return True

    def is_initialized(self) -> bool:
        """Check if API manager is initialized."""
        return self._is_initialized

    def _run_async_in_sync(self, coro, timeout: float = 30.0) -> Any:
        """Run async coroutine in synchronous context with improved error handling."""
        def _run_in_thread():
            try:
                # Save current event loop state
                current_loop = None
                try:
                    current_loop = asyncio.get_event_loop()
                except RuntimeError:
                    pass
                
                # Create and use new event loop to avoid conflicts
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(coro)
                finally:
                    loop.close()
                    # Restore previous event loop state
                    asyncio.set_event_loop(current_loop)
            except Exception as e:
                logger.debug(f"Error in async coroutine: {e}")
                raise

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            try:
                future = executor.submit(_run_in_thread)
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                logger.error(f"Operation timed out after {timeout} seconds")
                raise TimeoutError(f"Operation timed out after {timeout} seconds")
            except Exception as e:
                logger.debug(f"Thread execution failed: {e}")
                raise

    def _sync_wrapper(self, async_func, operation_name: str, *args, **kwargs) -> Any:
        """Universal synchronous wrapper for async operations."""
        try:
            # Extract sync_timeout without modifying original kwargs
            timeout = kwargs.pop('sync_timeout', self.config_service.get_setting("api_timeout", 30.0))
            return self._run_async_in_sync(
                async_func(*args, **kwargs),
                timeout=timeout
            )
        except Exception as e:
            logger.error(f"Synchronous {operation_name} failed: {e}")
            raise



    def _notify_error_handlers(self, error: APIError):
        """Notify all error handlers about an error."""
        for handler in self._error_handlers:
            try:
                handler(error)
            except Exception as e:
                logger.error(f"Error handler failed: {e}")

    def _classify_error(self, error: Exception) -> APIError:
        """Classify exception into API error type."""
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()

        # Authentication errors
        if any(keyword in error_str for keyword in ["unauthorized", "invalid api key", "authentication"]):
            return APIError(APIErrorType.AUTHENTICATION, str(error))

        # Rate limit errors
        if any(keyword in error_str for keyword in ["rate limit", "too many requests"]):
            retry_after = None
            if hasattr(error, "retry_after"):
                retry_after = error.retry_after
            return APIError(APIErrorType.RATE_LIMIT, str(error), retry_after=retry_after)

        # Quota exceeded
        if any(keyword in error_str for keyword in ["quota", "exceeded", "insufficient"]):
            return APIError(APIErrorType.QUOTA_EXCEEDED, str(error))

        # Network/timeout errors
        if any(keyword in error_type for keyword in ["timeout", "connection"]):
            return APIError(APIErrorType.TIMEOUT, str(error))
        if any(keyword in error_str for keyword in ["network", "connection", "dns"]):
            return APIError(APIErrorType.NETWORK, str(error))

        # Invalid request
        if any(keyword in error_str for keyword in ["invalid", "bad request", "malformed"]):
            return APIError(APIErrorType.INVALID_REQUEST, str(error))

        # Server errors
        if hasattr(error, "status_code") and error.status_code >= 500:
            return APIError(APIErrorType.SERVER_ERROR, str(error), error.status_code)

        # Unknown error
        return APIError(APIErrorType.UNKNOWN, str(error))

    @requires_initialization
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError))
    )
    async def make_request_async(self, provider: APIProvider, **kwargs) -> Any:
        """Make API request with retry logic."""

        client = self._clients.get(provider)
        if not client:
            raise ValueError(f"Provider {provider.value} not configured. Please set up your API key in settings.")

        usage = self._usage.get(provider, APIUsage())

        try:
            # Make the request
            logger.debug(f"Making API request to provider '{provider.value}' with args: {kwargs}")
            start_time = time.time()
            response = await client.chat.completions.create(**kwargs)
            request_time = time.time() - start_time
            logger.debug(f"Raw API response: {response}")

            # Update usage statistics
            with self._lock:
                usage.requests_count += 1
                usage.successful_requests += 1
                usage.last_request_time = datetime.now()
                if hasattr(response, "usage") and response.usage:
                    usage.tokens_used += response.usage.total_tokens

            logger.debug(f"API request completed in {request_time:.2f}s")
            return response

        except Exception as e:
            # Update failure statistics
            with self._lock:
                usage.requests_count += 1
                usage.failed_requests += 1
                if isinstance(e, openai.RateLimitError):
                    usage.rate_limit_hits += 1

            # Classify and handle error
            api_error = self._classify_error(e)
            self._notify_error_handlers(api_error)

            logger.error(f"API request failed: {api_error.error_type.value} - {api_error.message}")

            # Re-raise for retry mechanism
            raise

    @requires_initialization
    def make_request_sync(self, provider: APIProvider, **kwargs) -> Any:
        """Synchronous wrapper for make_request_async."""
        return self._sync_wrapper(self.make_request_async, "API request", provider, **kwargs)

    @requires_initialization
    def get_usage_stats(self, provider: Optional[APIProvider] = None) -> Dict[str, Any]:
        """Get API usage statistics."""
        with self._lock:
            if provider:
                usage = self._usage.get(provider, APIUsage())
                return {
                    "provider": provider.value,
                    "requests_count": usage.requests_count,
                    "tokens_used": usage.tokens_used,
                    "successful_requests": usage.successful_requests,
                    "failed_requests": usage.failed_requests,
                    "success_rate": (usage.successful_requests / usage.requests_count * 100) if usage.requests_count > 0 else 0,
                    "last_request_time": usage.last_request_time.isoformat() if usage.last_request_time else None,
                    "rate_limit_hits": usage.rate_limit_hits
                }
            else:
                # Return stats for all providers
                stats = {}
                for prov, usage in self._usage.items():
                    stats[prov.value] = self.get_usage_stats(prov)
                return stats


    @requires_initialization
    def is_rate_limited(self, provider: APIProvider) -> bool:
        """Check if provider is currently rate limited."""
        usage = self._usage.get(provider, APIUsage())

        # Simple rate limiting check based on recent failures
        if usage.rate_limit_hits > 5:
            # Check if we should reset the counter (after some time)
            if usage.last_request_time:
                time_since_last = datetime.now() - usage.last_request_time
                if time_since_last > timedelta(minutes=5):
                    with self._lock:
                        usage.rate_limit_hits = 0
                    return False
            return True

        return False

    @requires_initialization
    def get_provider_status(self, provider: APIProvider) -> Dict[str, Any]:
        """Get status information for a provider."""
        if provider not in self._clients:
            return {"available": False, "reason": "Not configured"}

        usage = self._usage.get(provider, APIUsage())

        return {
            "available": True,
            "rate_limited": self.is_rate_limited(provider),
            "last_request": usage.last_request_time.isoformat() if usage.last_request_time else None,
            "success_rate": (usage.successful_requests / usage.requests_count * 100) if usage.requests_count > 0 else 100.0
        }

    @requires_initialization
    async def get_available_models_async(self, provider: APIProvider) -> tuple[List[str], str]:
        """Get list of available models from API provider."""

        # Check cache first
        with self._lock:
            if provider in self._model_cache:
                models, timestamp = self._model_cache[provider]
                if time.time() - timestamp < self._model_cache_ttl:
                    logger.debug(f"Using cached models for {provider.value}")
                    return models, "cache"

        client = self._clients.get(provider)
        if not client:
            raise ValueError(f"Provider {provider.value} not configured")

        try:
            if provider == APIProvider.OPENAI:
                # Get models from OpenAI API
                models_response = await client.models.list()

                # Debug: log all available models
                all_models = [model.id for model in models_response.data]
                logger.debug(f"All available models from API: {all_models}")

                # Filter for chat completion models only
                chat_models = []
                for model in models_response.data:
                    model_id = model.id.lower()
                    # Include only models that start with gpt and are known to support chat
                    if (
                        model_id.startswith("gpt-") or model_id.startswith("chatgpt-")
                    ) and not any(
                        exclude in model_id
                        for exclude in [
                            "audio",
                            "realtime",
                            "image",
                            "dall-e",
                            "tts",
                            "whisper",
                            "embedding",
                            "moderation",
                            "codex",
                        ]
                    ) and not model_id.startswith("gpt-3"):
                        chat_models.append(model.id)

                # Sort models by name for consistent ordering
                chat_models.sort(
                    key=lambda x: (
                        (
                            0 if x.lower().startswith("gpt-5")
                            else 1 if x.lower().startswith("gpt-4")
                            else 2 if x.lower().startswith("chatgpt")
                            else 3
                        ),
                        x,
                    ),
                    reverse=False,
                )

                logger.debug(f"Filtered chat completion models: {chat_models}")
                models = chat_models
                source = "api"

            else:
                # For other providers, return fallback models with caching
                logger.warning(f"Model listing not implemented for {provider.value}")
                return self._get_fallback_models(provider)

            # Cache the result for successful API calls
            self._cache_models_and_persist(provider, models)

            return models, source

        except Exception as e:
            logger.error(f"Failed to fetch models from {provider.value}: {e}")
            # Return fallback list on error
            return self._get_fallback_models(provider)

    @requires_initialization
    def get_available_models_sync(self, provider: APIProvider) -> tuple[List[str], str]:
        """Synchronous wrapper for get_available_models_async."""
        try:
            return self._sync_wrapper(self.get_available_models_async, "model fetch", provider, sync_timeout=30.0)
        except Exception as e:
            logger.debug(f"Model fetch failed, using fallback: {e}")
            # Fallback in case of error
            try:
                return self._get_fallback_models(provider)
            except Exception as fallback_error:
                logger.error(f"Fallback model fetch also failed: {fallback_error}")
                # Return empty list as last resort
                return [], "error"

    def shutdown(self):
        """Shutdown API manager and cleanup resources."""
        with self._lock:
            self._clients.clear()
            self._usage.clear()
            self._error_handlers.clear()
            self._model_cache.clear()
            self._is_initialized = False
            logger.info("API manager shutdown")



# Global API manager instance
_api_manager: Optional[APIManager] = None
_manager_lock = threading.RLock()


def get_api_manager() -> APIManager:
    """
    Get the global API manager instance.

    This function ensures that a single instance of the APIManager is used throughout
    the application. It uses a lock to be thread-safe.
    """
    global _api_manager
    with _manager_lock:
        if _api_manager is None:
            # Pass the global config_service instance to the APIManager
            _api_manager = APIManager(config_service)
        return _api_manager


def init_api_manager() -> APIManager:
    """
    Initialize and return the API manager instance.

    This function retrieves the global APIManager instance and initializes it if it
    hasn't been already.
    """
    manager = get_api_manager()
    if not manager.is_initialized():
        if not manager.initialize():
            raise RuntimeError("Failed to initialize API manager")
    return manager
