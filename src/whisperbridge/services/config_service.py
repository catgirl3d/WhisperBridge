"""
Configuration Service for WhisperBridge.

This module provides a centralized configuration service with
observer pattern for change notifications, caching, and validation.
"""

import threading
import time
from typing import Any, Callable, Dict, List, Optional
from weakref import WeakSet

from loguru import logger

from ..core.config import Settings
from ..core.settings_manager import settings_manager


class SettingsObserver:
    """Base class for settings observers."""

    def on_settings_changed(self, key: str, old_value: Any, new_value: Any):
        """Called when a setting value changes."""
        pass

    def on_settings_loaded(self, settings: Settings):
        """Called when settings are loaded."""
        pass

    def on_settings_saved(self, settings: Settings):
        """Called when settings are saved."""
        pass


class ConfigService:
    """Centralized configuration service with observer pattern and caching."""

    def __init__(self):
        # Use the shared singleton settings_manager to avoid multiple independent managers
        # which can cause conflicting reads/writes on startup.
        self._settings_manager = settings_manager
        self._settings: Optional[Settings] = None
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._observers: WeakSet[SettingsObserver] = WeakSet()
        self._lock = threading.RLock()
        self._cache_ttl = 300  # 5 minutes default

    def _notify_observers(self, event: str, *args, **kwargs):
        """Notify all observers of an event."""
        for observer in list(self._observers):
            try:
                if event == 'changed':
                    observer.on_settings_changed(*args, **kwargs)
                elif event == 'loaded':
                    observer.on_settings_loaded(*args, **kwargs)
                elif event == 'saved':
                    observer.on_settings_saved(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Observer notification failed: {e}")

    def _invalidate_cache(self, key: Optional[str] = None):
        """Invalidate cache for a specific key or all keys."""
        with self._lock:
            if key:
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)
            else:
                self._cache.clear()
                self._cache_timestamps.clear()

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached value is still valid."""
        if key not in self._cache_timestamps:
            return False

        return (time.time() - self._cache_timestamps[key]) < self._cache_ttl

    def _get_cached_value(self, key: str) -> Any:
        """Get value from cache if valid."""
        if self._is_cache_valid(key):
            return self._cache[key]
        return None

    def _set_cached_value(self, key: str, value: Any):
        """Set value in cache with timestamp."""
        self._cache[key] = value
        self._cache_timestamps[key] = time.time()

    def add_observer(self, observer: SettingsObserver):
        """Add an observer for settings changes."""
        with self._lock:
            self._observers.add(observer)
            logger.debug(f"Added settings observer: {observer}")

    def remove_observer(self, observer: SettingsObserver):
        """Remove an observer."""
        with self._lock:
            self._observers.discard(observer)
            logger.debug(f"Removed settings observer: {observer}")

    def load_settings(self) -> Settings:
        """Load settings and notify observers."""
        with self._lock:
            try:
                self._settings = self._settings_manager.load_settings()
                self._invalidate_cache()  # Clear cache on reload
                self._notify_observers('loaded', self._settings)
                logger.info("Settings loaded via config service")
                return self._settings
            except Exception as e:
                logger.error(f"Failed to load settings: {e}")
                raise

    def save_settings(self, settings: Optional[Settings] = None) -> bool:
        """Save settings and notify observers."""
        with self._lock:
            try:
                if settings is None:
                    settings = self._settings
                    if settings is None:
                        logger.warning("No settings to save")
                        return False

                print(f"DEBUG: ConfigService.save_settings called with theme='{settings.theme}'")

                # Track changes for notifications
                old_settings = self._settings.model_copy() if self._settings else None

                success = self._settings_manager.save_settings(settings)
                print(f"DEBUG: SettingsManager.save_settings returned: {success}")

                if success:
                    self._settings = settings
                    self._invalidate_cache()  # Clear cache on save
                    self._notify_observers('saved', self._settings)

                    # Notify about individual changes
                    if old_settings:
                        self._notify_setting_changes(old_settings, self._settings)

                return success

            except Exception as e:
                logger.error(f"Failed to save settings: {e}")
                return False

    def _notify_setting_changes(self, old_settings: Settings, new_settings: Settings):
        """Notify observers about individual setting changes."""
        old_dict = old_settings.model_dump()
        new_dict = new_settings.model_dump()
    
        for key, new_value in new_dict.items():
            old_value = old_dict.get(key)
            if old_value != new_value:
                self._notify_observers('changed', key, old_value, new_value)
    
                # If log level changed, reconfigure logging immediately so new level takes effect.
                if key == "log_level":
                    try:
                        # Import here to avoid circular import at module import time
                        from ..core.logger import setup_logging
                        setup_logging()
                        logger.info(f"Applied new log level: {new_value}")
                    except Exception as e:
                        logger.error(f"Failed to apply new log level '{new_value}': {e}")

    def get_settings(self) -> Settings:
        """Get current settings, loading if necessary."""
        with self._lock:
            if self._settings is None:
                return self.load_settings()
            return self._settings

    def get_setting(self, key: str, use_cache: bool = True) -> Any:
        """Get a specific setting value with optional caching."""
        with self._lock:
            # Try cache first
            if use_cache:
                cached_value = self._get_cached_value(key)
                if cached_value is not None:
                    return cached_value

            # Get from settings
            settings = self.get_settings()
            value = getattr(settings, key, None)

            # Cache the value
            if use_cache and value is not None:
                self._set_cached_value(key, value)

            return value

    def set_setting(self, key: str, value: Any) -> bool:
        """Set a specific setting value."""
        with self._lock:
            try:
                settings = self.get_settings()
                old_value = getattr(settings, key, None)

                # Use the new method to save only one setting
                success = self._settings_manager.save_single_setting(key, value)

                if success:
                    # Update in-memory cache and notify observers
                    # Update the main settings object as well
                    if self._settings:
                        setattr(self._settings, key, value)
                    
                    self._set_cached_value(key, value)
                    self._notify_observers('changed', key, old_value, value)
                    
                    # If log level changed, reconfigure logging
                    if key == "log_level":
                        try:
                            from ..core.logger import setup_logging
                            setup_logging()
                            logger.info(f"Applied new log level: {value}")
                        except Exception as e:
                            logger.error(f"Failed to apply new log level '{value}': {e}")

                return success

            except Exception as e:
                logger.error(f"Failed to set setting {key}: {e}")
                return False

    def update_settings(self, updates: Dict[str, Any]) -> bool:
        """Update multiple settings at once."""
        with self._lock:
            try:
                # This is less efficient as it writes the file for each setting,
                # but it reuses the existing single-setting save logic.
                for key, value in updates.items():
                    self.set_setting(key, value)
                return True
            except Exception as e:
                logger.error(f"Failed to update settings: {e}")
                return False

    def validate_settings(self, settings: Optional[Settings] = None) -> bool:
        """Validate settings configuration."""
        try:
            if settings is None:
                settings = self.get_settings()

            # Use Pydantic validation
            settings.model_validate(settings.model_dump())
            return True

        except Exception as e:
            logger.error(f"Settings validation failed: {e}")
            return False

    def reset_to_defaults(self) -> bool:
        """Reset all settings to defaults."""
        with self._lock:
            try:
                from ..core.config import Settings as DefaultSettings
                default_settings = DefaultSettings()
                return self.save_settings(default_settings)
            except Exception as e:
                logger.error(f"Failed to reset to defaults: {e}")
                return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            return {
                'cache_size': len(self._cache),
                'cache_ttl': self._cache_ttl,
                'cached_keys': list(self._cache.keys()),
                'observer_count': len(self._observers)
            }

    def clear_cache(self):
        """Clear all cached values."""
        with self._lock:
            self._invalidate_cache()
            logger.debug("Settings cache cleared")

    def set_cache_ttl(self, ttl: int):
        """Set cache time-to-live in seconds."""
        with self._lock:
            self._cache_ttl = ttl
            self._invalidate_cache()  # Clear cache when TTL changes
            logger.debug(f"Cache TTL set to {ttl} seconds")


# Global config service instance
config_service = ConfigService()