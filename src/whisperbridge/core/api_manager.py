"""
API Manager for WhisperBridge.

This module provides centralized API management with authentication,
error handling, retry logic, and usage monitoring.
"""

import asyncio
import time
import threading
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

import openai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger

from .config import settings
from ..utils.api_utils import validate_api_key_format, format_error_message


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

    def __init__(self):
        self._clients: Dict[APIProvider, Any] = {}
        self._usage: Dict[APIProvider, APIUsage] = {}
        self._lock = threading.RLock()
        self._error_handlers: List[Callable[[APIError], None]] = []
        self._is_initialized = False

    def initialize(self) -> bool:
        """Initialize API manager with configured providers."""
        with self._lock:
            try:
                # Initialize OpenAI client
                if settings.api_provider == "openai":
                    if not settings.openai_api_key:
                        logger.warning("OpenAI API key not configured. Translation features will be disabled.")
                        logger.info("To enable translation, set your OpenAI API key in the settings.")
                        # Don't return False here - allow the app to run without API
                    elif not validate_api_key_format(settings.openai_api_key):
                        logger.error("Invalid OpenAI API key format")
                        logger.info("Please check your OpenAI API key format (should start with 'sk-')")
                        # Don't return False here - allow the app to run without API
                    else:
                        self._clients[APIProvider.OPENAI] = openai.AsyncOpenAI(
                            api_key=settings.openai_api_key,
                            timeout=settings.api_timeout
                        )
                        self._usage[APIProvider.OPENAI] = APIUsage()
                        logger.info("OpenAI client initialized")

                # Initialize Azure OpenAI client if configured
                elif settings.api_provider == "azure_openai":
                    # Azure configuration would go here
                    logger.warning("Azure OpenAI not yet implemented")
                    # Don't return False here - allow the app to run without API

                # Allow initialization even without API clients
                # The app can still run OCR and other features
                self._is_initialized = True

                if self._clients:
                    logger.info("API manager initialized successfully with clients")
                else:
                    logger.info("API manager initialized (no API clients - translation features disabled)")

                return True

            except Exception as e:
                logger.error(f"Failed to initialize API manager: {e}")
                # Still allow initialization even if there are errors
                self._is_initialized = True
                logger.info("API manager initialized with errors (limited functionality)")
                return True

    def is_initialized(self) -> bool:
        """Check if API manager is initialized."""
        return self._is_initialized

    def add_error_handler(self, handler: Callable[[APIError], None]):
        """Add error handler callback."""
        with self._lock:
            self._error_handlers.append(handler)

    def remove_error_handler(self, handler: Callable[[APIError], None]):
        """Remove error handler callback."""
        with self._lock:
            if handler in self._error_handlers:
                self._error_handlers.remove(handler)

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
            if hasattr(error, 'retry_after'):
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
        if hasattr(error, 'status_code') and error.status_code >= 500:
            return APIError(APIErrorType.SERVER_ERROR, str(error), error.status_code)

        # Unknown error
        return APIError(APIErrorType.UNKNOWN, str(error))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError))
    )
    async def make_request_async(self, provider: APIProvider, **kwargs) -> Any:
        """Make API request with retry logic."""
        if not self.is_initialized():
            raise RuntimeError("API manager not initialized")

        client = self._clients.get(provider)
        if not client:
            raise ValueError(f"Provider {provider.value} not configured. Please set up your API key in settings.")

        usage = self._usage.get(provider, APIUsage())

        try:
            # Make the request
            start_time = time.time()
            response = await client.chat.completions.create(**kwargs)
            request_time = time.time() - start_time

            # Update usage statistics
            with self._lock:
                usage.requests_count += 1
                usage.successful_requests += 1
                usage.last_request_time = datetime.now()
                if hasattr(response, 'usage') and response.usage:
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

    def make_request_sync(self, provider: APIProvider, **kwargs) -> Any:
        """Synchronous wrapper for make_request_async."""
        try:
            # Get or create event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            return loop.run_until_complete(self.make_request_async(provider, **kwargs))

        except Exception as e:
            logger.error(f"Synchronous API request failed: {e}")
            raise

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

    def reset_usage_stats(self, provider: Optional[APIProvider] = None):
        """Reset usage statistics."""
        with self._lock:
            if provider:
                if provider in self._usage:
                    self._usage[provider] = APIUsage()
                    logger.info(f"Reset usage stats for {provider.value}")
            else:
                for prov in list(self._usage.keys()):
                    self._usage[prov] = APIUsage()
                logger.info("Reset usage stats for all providers")

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

    def shutdown(self):
        """Shutdown API manager and cleanup resources."""
        with self._lock:
            self._clients.clear()
            self._usage.clear()
            self._error_handlers.clear()
            self._is_initialized = False
            logger.info("API manager shutdown")


# Global API manager instance
_api_manager: Optional[APIManager] = None
_manager_lock = threading.RLock()


def get_api_manager() -> APIManager:
    """Get the global API manager instance."""
    global _api_manager
    with _manager_lock:
        if _api_manager is None:
            _api_manager = APIManager()
        return _api_manager


def init_api_manager() -> APIManager:
    """Initialize and return the API manager instance."""
    manager = get_api_manager()
    if not manager.is_initialized():
        if not manager.initialize():
            raise RuntimeError("Failed to initialize API manager")
    return manager