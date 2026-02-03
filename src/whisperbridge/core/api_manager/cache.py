"""
Model cache management for the API Manager package.

This module provides the ModelCache class for caching model lists
with disk persistence and TTL support.
"""

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

from ..config import ensure_config_dir


class ModelCache:
    """
    Manages model caching with disk persistence and TTL.

    This class provides thread-safe caching of model lists with
    automatic cleanup of expired cache entries.
    """

    def __init__(self, config_dir: Path, ttl_seconds: int = 1209600):
        """
        Initialize the ModelCache.

        Args:
            config_dir: Directory to store cache files.
            ttl_seconds: Time-to-live for cache entries (default: 2 weeks).
        """
        self._cache: Dict[str, Tuple[List[str], float]] = {}
        self._lock = threading.RLock()
        self._config_dir = config_dir
        self._ttl = ttl_seconds
        self._cache_file = config_dir / "models_cache.json"

    def _get_cache_path(self) -> Path:
        """Return path to persistent model cache file."""
        return self._cache_file

    def load_from_disk(self) -> None:
        """Load persistent model cache into memory if present."""
        path = self._get_cache_path()
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            with self._lock:
                # raw expected as {provider_value: {"models": [...], "timestamp": ts}}
                for prov_str, entry in raw.items():
                    models = entry.get("models", [])
                    ts = entry.get("timestamp", 0)
                    self._cache[prov_str] = (models, ts)
            logger.info("Loaded model cache from disk")
        except Exception as e:
            logger.warning(f"Failed to load model cache from disk: {e}")

    def save_to_disk(self) -> None:
        """Persist in-memory model cache to disk."""
        path = self._get_cache_path()
        data = {}
        with self._lock:
            for prov, (models, ts) in self._cache.items():
                data[prov] = {"models": models, "timestamp": ts}
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug("Saved model cache to disk")
        except Exception as e:
            logger.warning(f"Failed to save model cache to disk: {e}")

    def cleanup_old_files(self) -> None:
        """Remove cache files older than TTL."""
        try:
            path = self._get_cache_path()
            if path.exists():
                file_age = time.time() - path.stat().st_mtime
                if file_age > self._ttl:
                    path.unlink()
                    logger.debug("Removed old model cache file")
        except Exception as e:
            logger.debug(f"Failed to cleanup old cache files: {e}")

    def _handle_cache_operation(self, operation: str, operation_func: Callable) -> Optional[Any]:
        """Universal cache operation handler with error logging."""
        try:
            return operation_func()
        except Exception as e:
            logger.warning(f"Failed to {operation} model cache: {e}")
            return None

    def cache_models_and_persist(self, provider: str, models: List[str]) -> None:
        """
        Cache models and persist to disk in one operation.

        Args:
            provider: Provider identifier (e.g., "openai", "google").
            models: List of model names to cache.
        """
        with self._lock:
            self._cache[provider] = (models, time.time())
        self._handle_cache_operation("persist", self.save_to_disk)

    def initialize_safely(self) -> None:
        """Safely initialize model cache with error handling."""
        def load_cache():
            self.load_from_disk()
            self.cleanup_old_files()

        self._handle_cache_operation("load cache during initialization", load_cache)

    def get(self, provider: str) -> Optional[Tuple[List[str], float]]:
        """
        Get cached models for a provider.

        Args:
            provider: Provider identifier.

        Returns:
            Tuple of (models_list, timestamp) if found and not expired, None otherwise.
        """
        with self._lock:
            if provider in self._cache:
                models, timestamp = self._cache[provider]
                # Only return cache if not expired
                if time.time() - timestamp < self._ttl:
                    return models, timestamp
        return None

    def set(self, provider: str, models: List[str]) -> None:
        """
        Set cached models for a provider.

        Args:
            provider: Provider identifier.
            models: List of model names to cache.
        """
        with self._lock:
            self._cache[provider] = (models, time.time())

    def clear(self, provider: Optional[str] = None) -> None:
        """
        Clear cache entries.

        Args:
            provider: If provided, clear only this provider's cache.
                     If None, clear all cache entries.
        """
        with self._lock:
            if provider:
                self._cache.pop(provider, None)
            else:
                self._cache.clear()

    def is_cached(self, provider: str) -> bool:
        """
        Check if provider has cached models.

        Args:
            provider: Provider identifier.

        Returns:
            True if provider has cached models, False otherwise.
        """
        with self._lock:
            return provider in self._cache

    @staticmethod
    def validate_model_list(models: List[str]) -> bool:
        """
        Validate that model list is not empty and contains valid strings.

        Args:
            models: List of model names to validate.

        Returns:
            True if valid, False otherwise.
        """
        if not models:
            return False
        return all(isinstance(model, str) and model.strip() for model in models)


__all__ = [
    "ModelCache",
]
