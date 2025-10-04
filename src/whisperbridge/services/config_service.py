"""
Configuration Service for WhisperBridge.

This module provides a centralized configuration service with
observer pattern for change notifications, caching, and validation.
"""

import threading
import time
from typing import Any, Dict, Optional
from weakref import WeakSet

from loguru import logger
from PySide6.QtCore import QObject, QThread, Slot, Signal

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


class ConfigService(QObject):
    """Centralized configuration service with observer pattern and caching."""
    # Emitted on async save completion (main thread): success, message
    saved_async_result = Signal(bool, str)

    def __init__(self):
        super().__init__()
        # Use the shared singleton settings_manager to avoid multiple independent managers
        # which can cause conflicting reads/writes on startup.
        self._settings_manager = settings_manager
        self._settings: Optional[Settings] = None
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._observers: WeakSet[SettingsObserver] = WeakSet()
        self._lock = threading.RLock()
        self._cache_ttl = 300  # 5 minutes default
        self._worker_threads: list = []  # Holds (thread, worker) pairs to prevent garbage collection
        self._last_saved_settings: Optional[Settings] = None  # Track settings sent to async save

    def _notify_observers(self, event: str, *args, **kwargs):
        """Notify all observers of an event."""
        for observer in list(self._observers):
            try:
                if event == "changed":
                    observer.on_settings_changed(*args, **kwargs)
                elif event == "loaded":
                    observer.on_settings_loaded(*args, **kwargs)
                elif event == "saved":
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


    def load_settings(self) -> Settings:
        """Load settings and notify observers."""
        with self._lock:
            try:
                self._settings = self._settings_manager.load_settings()
                self._invalidate_cache()  # Clear cache on reload
                self._notify_observers("loaded", self._settings)
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

                logger.debug(f"ConfigService.save_settings called with theme='{settings.theme}'")

                # Track changes for notifications
                old_settings = self._settings.model_copy() if self._settings else None

                success = self._settings_manager.save_settings(settings)
                logger.debug(f"SettingsManager.save_settings returned: {success}")

                if success:
                    self._settings = settings
                    self._invalidate_cache()  # Clear cache on save
                    self._notify_observers("saved", self._settings)

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
                self._notify_observers("changed", key, old_value, new_value)

                # If log level changed, reconfigure logging immediately so new level takes effect.
                if key == "log_level":
                    try:
                        # Import here to avoid circular import at module import time
                        from ..core.logger import setup_logging

                        setup_logging(self)
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
                    self._notify_observers("changed", key, old_value, value)

                    # If log level changed, reconfigure logging
                    if key == "log_level":
                        try:
                            from ..core.logger import setup_logging

                            setup_logging(self)
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

    def save_settings_async(self, settings: Optional[Settings] = None):
        """
        Save settings asynchronously using a worker thread.
        This method is non-blocking.
        """
        with self._lock:
            if settings is None:
                settings = self._settings
                if settings is None:
                    logger.warning("No settings to save asynchronously.")
                    return

            logger.info("Starting asynchronous settings save from ConfigService.")

            # Создаем копию, чтобы избежать проблем с потоками
            settings_copy = settings.model_copy()

            # Store the settings being saved for use in callback
            self._last_saved_settings = settings_copy

            from .config_workers import SettingsSaveWorker
            from ..ui_qt.app import get_qt_app
            worker = SettingsSaveWorker(settings_copy)
            app = get_qt_app()
            app.create_and_run_worker(worker, self._on_async_save_finished, lambda: None)

    @Slot(bool, str)
    def _on_async_save_finished(self, success: bool, message: str):
        """Handle the result of the asynchronous settings save."""
        with self._lock:
            if success:
                logger.info(f"Async save successful: {message}")
                # Снимем копию старых настроек для корректной дифф-нотификации
                old_settings = self._settings.model_copy() if self._settings else None

                # Update in-memory state with the settings that were successfully saved
                # This avoids unnecessary file I/O and potential race conditions
                if self._last_saved_settings:
                    self._settings = self._last_saved_settings
                    self._invalidate_cache()  # Clear cache since settings changed

                # Уведомим 'saved' и по-раздельности изменения ключей
                new_settings = self.get_settings()
                self._notify_observers("saved", new_settings)
                if old_settings:
                    self._notify_setting_changes(old_settings, new_settings)
            else:
                logger.error(f"Async save failed: {message}")
    
        # Emit result signal on the main thread so UI can notify the user
        try:
            self.saved_async_result.emit(success, message)
        except Exception as e:
            logger.debug(f"Failed to emit saved_async_result: {e}")
    
        # Очистка завершенных потоков (опционально, для долгоживущих приложений)
        self._worker_threads = [
            (t, w) for t, w in self._worker_threads if t.isRunning()
        ]







# Global config service instance
config_service = ConfigService()
