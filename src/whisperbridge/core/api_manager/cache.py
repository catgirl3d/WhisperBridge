"""
Model cache management for the API Manager package.

This module provides the ModelCache class for caching model lists
with disk persistence and TTL support.
"""

import json
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger


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
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._cache_file = config_dir / "models_cache.json"

    def load_from_disk(self) -> None:
        """Load persistent model cache into memory if present."""
        path = self._cache_file
        try:
            if not path.exists():
                return
            with path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            with self._lock:
                # raw expected as {provider_value: {"models": [...], "timestamp": ts}}
                for provider, entry in raw.items():
                    self._cache[provider] = (
                        entry.get("models", []),
                        entry.get("timestamp", 0),
                    )
            logger.info("Loaded model cache from disk")
        except Exception as e:
            logger.warning(f"Failed to load model cache from disk: {e}")

    def save_to_disk(self) -> None:
        """Persist in-memory model cache to disk."""
        with self._lock:
            self._save_locked()

    def _save_locked(self) -> None:
        """Write the current cache snapshot; caller must hold ``_lock``."""
        data = {
            provider: {"models": models, "timestamp": timestamp}
            for provider, (models, timestamp) in self._cache.items()
        }
        try:
            with self._cache_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug("Saved model cache to disk")
        except Exception as e:
            logger.warning(f"Failed to save model cache to disk: {e}")

    def cleanup_old_files(self) -> None:
        """Remove expired entries using their stored timestamps."""
        now = time.time()
        with self._lock:
            expired_providers = [
                provider
                for provider, (_, timestamp) in self._cache.items()
                if now - timestamp >= self._ttl
            ]
            if not expired_providers:
                return

            for provider in expired_providers:
                self._cache.pop(provider, None)

            if self._cache:
                self._save_locked()
                return

            try:
                self._cache_file.unlink(missing_ok=True)
                logger.debug("Removed expired model cache file")
            except Exception as e:
                logger.debug(f"Failed to cleanup expired model cache: {e}")

    def cache_models_and_persist(self, provider: str, models: List[str]) -> None:
        """
        Cache models and persist to disk in one operation.

        Args:
            provider: Provider identifier (e.g., "openai", "google").
            models: List of model names to cache.
        """
        with self._lock:
            self._cache[provider] = (models, time.time())
            self._save_locked()

    def initialize_safely(self) -> None:
        """Safely initialize model cache with error handling."""
        self.load_from_disk()
        self.cleanup_old_files()

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

    def clear(self, provider: Optional[str] = None, *, delete_persisted: bool = False) -> None:
        """
        Clear cache entries.

        Args:
            provider: If provided, clear only this provider's cache.
                     If None, clear all cache entries.
            delete_persisted: Also remove the disk cache when clearing all entries.
        """
        with self._lock:
            if provider:
                self._cache.pop(provider, None)
            else:
                self._cache.clear()

            if delete_persisted:
                if provider:
                    self._save_locked()
                else:
                    try:
                        self._cache_file.unlink(missing_ok=True)
                    except Exception as e:
                        logger.debug(f"Failed to remove persisted model cache: {e}")

    def is_cached(self, provider: str) -> bool:
        """
        Check if provider has a non-expired cache entry.

        Args:
            provider: Provider identifier.

        Returns:
            True if provider has a non-expired cache entry, False otherwise.
        """
        return self.get(provider) is not None

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
