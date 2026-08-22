"""
Configuration Service for WhisperBridge.

This module provides a centralized configuration service with
observer pattern for change notifications and validation.
"""

import threading
from typing import Any, Dict, Optional
from weakref import WeakSet

from loguru import logger
from PySide6.QtCore import QObject

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
    """Centralized configuration service with observer notifications."""

    def __init__(self):
        super().__init__()
        # Use the shared singleton settings_manager to avoid multiple independent managers
        # which can cause conflicting reads/writes on startup.
        self._settings_manager = settings_manager
        self._settings: Optional[Settings] = None
        self._observers: WeakSet[SettingsObserver] = WeakSet()
        self._lock = threading.RLock()

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

        # Check if API-related settings changed and reinitialize API manager if needed
        self._check_and_reinitialize_api_manager(old_settings, new_settings)

    def get_settings(self) -> Settings:
        """Get current settings, loading if necessary."""
        with self._lock:
            if self._settings is None:
                return self.load_settings()
            return self._settings

    def get_setting(self, key: str) -> Any:
        """Get a setting from the current model."""
        with self._lock:
            return getattr(self.get_settings(), key, None)

    def set_setting(self, key: str, value: Any) -> bool:
        """Set a specific setting value."""
        with self._lock:
            try:
                settings = self.get_settings()
                old_value = getattr(settings, key, None)

                # Use the new method to save only one setting
                success = self._settings_manager.save_single_setting(key, value)

                if success:
                    validated_settings = self._settings_manager.get_settings()
                    validated_value = getattr(validated_settings, key, value)
                    self._settings = validated_settings

                    if old_value != validated_value:
                        self._notify_observers("changed", key, old_value, validated_value)

                    # If log level changed, reconfigure logging
                    if key == "log_level" and old_value != validated_value:
                        try:
                            from ..core.logger import setup_logging

                            setup_logging(self)
                            logger.info(f"Applied new log level: {validated_value}")
                        except Exception as e:
                            logger.error(f"Failed to apply new log level '{validated_value}': {e}")

                return success

            except Exception as e:
                logger.error(f"Failed to set setting {key}: {e}")
                return False

    def update_settings(self, updates: Dict[str, Any]) -> bool:
        """Update multiple settings at once."""
        with self._lock:
            try:
                current_settings = self.get_settings()
                merged_data = current_settings.model_dump()
                merged_data.update(updates)
                new_settings = Settings.model_validate(merged_data)
                return self.save_settings(new_settings)
            except Exception as e:
                logger.error(f"Failed to update settings: {e}")
                return False

    def _check_and_reinitialize_api_manager(self, old_settings: Settings, new_settings: Settings):
        """Check if API-related settings changed and reinitialize API manager if needed."""
        try:
            must_reinit = False

            # Check if provider changed
            if old_settings.api_provider != new_settings.api_provider:
                must_reinit = True

            # Check if any API key changed
            if not must_reinit:
                providers = ["openai", "google", "deepl"]
                for provider in providers:
                    old_key = getattr(old_settings, f"{provider}_api_key", None) or ""
                    new_key = getattr(new_settings, f"{provider}_api_key", None) or ""
                    if old_key != new_key:
                        must_reinit = True
                        break

            # Check if DeepL plan changed
            if not must_reinit:
                try:
                    old_plan = getattr(old_settings, "deepl_plan", "free")
                    new_plan = getattr(new_settings, "deepl_plan", "free")
                    if old_plan != new_plan:
                        must_reinit = True
                except Exception:
                    pass

            if must_reinit:
                from ..core.api_manager import get_api_manager
                api_manager = get_api_manager()
                api_manager.reinitialize()
                logger.info("API manager reinitialized after settings change (provider/key/plan).")

        except Exception as e:
            logger.error(f"Failed to reinitialize API manager after settings change: {e}")




# Global config service instance
config_service = ConfigService()
