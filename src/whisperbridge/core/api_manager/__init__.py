"""
API Manager package for WhisperBridge.

Provides centralized API management with authentication,
error handling, retry logic, and usage monitoring.
"""

from .types import APIUsage, ModelSource
from .errors import APIError, APIErrorType, RetryableAPIError
from .providers import APIProvider
from .manager import APIManager

# Singleton management
_api_manager: APIManager | None = None
_manager_lock = None


def get_api_manager() -> APIManager:
    """
    Get the global APIManager instance.

    This function ensures that a single instance of the APIManager is used throughout
    the application. It uses a lock to be thread-safe.
    """
    global _api_manager, _manager_lock

    # Import lock and config here to avoid circular imports
    import threading
    from ...services.config_service import config_service

    if _manager_lock is None:
        _manager_lock = threading.RLock()

    with _manager_lock:
        if _api_manager is None:
            # Pass the global config_service instance to the APIManager
            _api_manager = APIManager(config_service)
        return _api_manager


def init_api_manager() -> APIManager:
    """
    Initialize and return the global APIManager instance.

    This function retrieves the global APIManager instance and initializes it if it
    hasn't been already. Uses the global config_service instance internally.

    Returns:
        The initialized APIManager instance.

    Raises:
        RuntimeError: If initialization fails.
    """
    manager = get_api_manager()
    if not manager.is_initialized():
        if not manager.initialize():
            raise RuntimeError("Failed to initialize API manager")
    return manager


__all__ = [
    "APIManager",
    "APIProvider",
    "APIError",
    "APIErrorType",
    "RetryableAPIError",
    "APIUsage",
    "ModelSource",
    "get_api_manager",
    "init_api_manager",
]
