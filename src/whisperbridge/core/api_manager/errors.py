"""
Error handling and diagnostics for the API Manager package.

This module contains:
- APIErrorType enum for categorizing errors
- APIError dataclass for error information
- RetryableAPIError exception for retryable errors
- requires_initialization decorator
- classify_error function for error classification
- log_network_diagnostics function for network debugging
"""

import importlib
import os
import platform
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any, Dict, Optional

from loguru import logger


class APIErrorType(str, Enum):
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
class APIError:
    """API error information."""

    error_type: APIErrorType
    message: str
    status_code: Optional[int] = None
    retry_after: Optional[int] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class RetryableAPIError(Exception):
    """Custom exception to signal a retryable API error."""

    pass


def requires_initialization(func):
    """Decorator to ensure API manager is initialized before method execution."""
    @wraps(func)
    def sync_wrapper(self, *args, **kwargs):
        if not self.is_initialized():
            raise RuntimeError("API manager not initialized")
        return func(self, *args, **kwargs)

    return sync_wrapper


def classify_error(error: Exception, provider: Optional[str] = None) -> APIError:
    """
    Classify exception into API error type.

    Args:
        error: The exception to classify.
        provider: Optional provider name for context.

    Returns:
        APIError with classified error type.
    """
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    # Authentication errors
    if any(keyword in error_str for keyword in ["unauthorized", "invalid api key", "authentication"]):
        return APIError(APIErrorType.AUTHENTICATION, str(error))

    # Rate limit errors
    if any(keyword in error_str for keyword in ["rate limit", "too many requests"]):
        retry_after = None
        if hasattr(error, "retry_after"):
            retry_after = getattr(error, "retry_after", None)
        return APIError(APIErrorType.RATE_LIMIT, str(error), retry_after=retry_after)

    # Quota exceeded
    if any(keyword in error_str for keyword in ["quota", "billing"]):
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
    if hasattr(error, "status_code"):
        status_code = getattr(error, "status_code", None)
        if status_code and status_code >= 500:
            return APIError(APIErrorType.SERVER_ERROR, str(error), status_code)

    # Unknown error
    return APIError(APIErrorType.UNKNOWN, str(error))


def log_network_diagnostics(url: Optional[str] = None, error: Optional[Exception] = None) -> None:
    """
    Log one-shot diagnostics to investigate crashes in frozen builds.

    Args:
        url: Optional URL that was being accessed.
        error: Optional error that occurred.
    """
    try:
        info: Dict[str, Any] = {
            "frozen": getattr(sys, "frozen", False),
            "meipass": getattr(sys, "_MEIPASS", None),
            "python": sys.version,
            "platform": platform.platform(),
            "executable": getattr(sys, "executable", None),
            "SSL_CERT_FILE": os.environ.get("SSL_CERT_FILE"),
            "REQUESTS_CA_BUNDLE": os.environ.get("REQUESTS_CA_BUNDLE"),
        }
        if url:
            info["url"] = url
        if error:
            info["error"] = str(error)

        # certifi
        try:
            import certifi  # type: ignore
            info["certifi.where"] = certifi.where()
            info["certifi.file"] = getattr(certifi, "__file__", None)
        except Exception as e:
            info["certifi.error"] = str(e)

        def _mod_info(name: str) -> Dict[str, Any]:
            try:
                m = importlib.import_module(name)
                return {
                    "file": getattr(m, "__file__", None),
                    "version": getattr(m, "__version__", None),
                }
            except Exception as ex:
                return {"error": str(ex)}

        # Critical runtime modules
        info["openai"] = _mod_info("openai")
        info["httpx"] = _mod_info("httpx")
        info["httpcore"] = _mod_info("httpcore")
        info["h11"] = _mod_info("h11")
        info["pydantic_core"] = _mod_info("pydantic_core")

        logger.debug(f"Network diagnostics: {info}")
    except Exception as e:
        logger.debug(f"Failed to log network diagnostics: {e}")


__all__ = [
    "APIErrorType",
    "APIError",
    "RetryableAPIError",
    "requires_initialization",
    "classify_error",
    "log_network_diagnostics",
]
