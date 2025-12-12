"""
Settings Manager for WhisperBridge.

This module provides a comprehensive settings management system with
JSON persistence, secure key storage, migration support, and thread-safety.
"""

import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import keyring
from loguru import logger

from .config import Settings, get_config_path


class SettingsManager:
    """Thread-safe settings manager with persistence and migration support."""

    def __init__(self):
        self._lock = threading.RLock()
        self._settings: Optional[Settings] = None
        self._migration_handlers: Dict[str, Callable] = {}

        # Register migration handlers
        self._register_migrations()

    def _register_migrations(self):
        """Register settings migration handlers for version upgrades."""
        self._migration_handlers = {
            "1.0.0": self._migrate_from_1_0_0,
            "1.1.0": self._migrate_from_1_1_0,
            "1.2.1": self._migrate_from_1_2_1,
        }

    def _migrate_from_1_0_0(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate settings from version 1.0.0."""
        logger.info("Migrating settings from version 1.0.0")

        # Add new fields with defaults
        data.setdefault("system_prompt", "You are a professional translator...")
        data.setdefault("activation_hotkey", "ctrl+shift+a")
        data.setdefault("api_timeout", 30)
        data.setdefault("max_retries", 3)

        # Global caching settings (used by TranslationService; OCR cache removed)
        data.setdefault("cache_enabled", True)
        data.setdefault("max_cache_size", 100)

        return data

    def _migrate_from_1_1_0(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate settings from version 1.1.0."""
        logger.info("Migrating settings from version 1.1.0")

        # Add newer fields
        data.setdefault("supported_languages", ["en", "ru", "es", "fr", "de"])
        data.setdefault("log_to_file", True)

        return data

    def _migrate_from_1_2_1(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate settings from version 1.2.1."""
        logger.info("Migrating settings from version 1.2.1")

        # Add UI backend field
        data.setdefault("ui_backend", "qt")
        data.setdefault("copy_translate_hotkey", "ctrl+shift+j")

        return data

    def _get_settings_file(self) -> Path:
        """Get the path to the settings file."""
        return get_config_path() / "settings.json"

    def _load_key(self, key_name: str) -> Optional[str]:
        """Load a generic API key from keyring."""
        try:
            return keyring.get_password("whisperbridge", key_name)
        except Exception as e:
            logger.warning(f"Failed to load key '{key_name}' from keyring: {e}")
            return None

    def _save_key(self, key_name: str, api_key: str) -> bool:
        """Save a generic API key to keyring."""
        try:
            keyring.set_password("whisperbridge", key_name, api_key)
            return True
        except Exception as e:
            logger.error(f"Failed to save key '{key_name}' to keyring: {e}")
            return False

    def _delete_key(self, key_name: str) -> bool:
        """Delete a generic API key from keyring."""
        try:
            keyring.delete_password("whisperbridge", key_name)
            logger.debug(f"Successfully deleted key '{key_name}' from keyring.")
            return True
        except Exception as e:
            # Ignore if key doesn't exist or deletion fails (safe fallback)
            logger.warning(
                f"Could not delete key '{key_name}' from keyring, but proceeding (this is often normal). Error: {e}"
            )
            return True

    def _migrate_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply migrations to settings data."""
        current_version = data.get("version", "1.0.0")

        # Apply migrations in order
        for version, handler in sorted(self._migration_handlers.items()):
            if self._compare_versions(current_version, version) < 0:
                try:
                    data = handler(data)
                    data["version"] = version
                    logger.info(f"Applied migration to version {version}")
                except Exception as e:
                    logger.error(f"Failed to apply migration {version}: {e}")

        return data

    def _compare_versions(self, v1: str, v2: str) -> int:
        """Compare two version strings."""
        v1_parts = [int(x) for x in v1.split(".")]
        v2_parts = [int(x) for x in v2.split(".")]

        for i in range(max(len(v1_parts), len(v2_parts))):
            v1_part = v1_parts[i] if i < len(v1_parts) else 0
            v2_part = v2_parts[i] if i < len(v2_parts) else 0

            if v1_part < v2_part:
                return -1
            elif v1_part > v2_part:
                return 1

        return 0

    def load_settings(self) -> Settings:
        """Load settings from file with migration and validation."""
        with self._lock:
            try:
                settings_file = self._get_settings_file()

                if settings_file.exists():
                    with open(settings_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # Apply migrations
                    data = self._migrate_settings(data)
                else:
                    data = {}

                # --- Security: API keys are stored only in keyring ---
                # Settings MUST NOT accept API keys from JSON. If keys are present in settings.json
                # (e.g., by manual edit or legacy file), we ignore them and scrub them from disk.
                scrubbed = False
                for api_key_field in ("openai_api_key", "google_api_key", "deepl_api_key"):
                    if api_key_field in data:
                        data.pop(api_key_field, None)
                        scrubbed = True

                if scrubbed and settings_file.exists():
                    try:
                        with open(settings_file, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        logger.info("Security: Scrubbed API keys from settings.json")
                    except Exception as e:
                        logger.warning(f"Security: Failed to scrub API keys from settings.json: {e}")

                # Load secure keys from keyring (the only source of truth)
                keyring_openai = self._load_key("openai_api_key")
                keyring_google = self._load_key("google_api_key")
                keyring_deepl = self._load_key("deepl_api_key")

                # Inject secure keys into data for Settings model creation (in-memory only)
                if keyring_openai:
                    data["openai_api_key"] = keyring_openai
                if keyring_google:
                    data["google_api_key"] = keyring_google
                if keyring_deepl:
                    data["deepl_api_key"] = keyring_deepl

                # Create settings with environment variables first (including .env)
                # This ensures ocr_enabled is loaded from .env or build flag
                temp_settings = Settings()

                # Apply saved settings onto the temp_settings while preserving ocr_enabled
                # Use model_copy(update=...) to avoid re-validating ocr_enabled twice.
                update_data = dict(data)  # copy to avoid modifying original
                update_data.pop("ocr_enabled", None)  # preserve env/build value from temp_settings

                # Merge saved settings into the environment-initialized model
                self._settings = temp_settings.model_copy(update=update_data)
                logger.info("Settings loaded successfully")
                return self._settings

            except Exception as e:
                logger.error(f"Failed to load settings: {e}")
                # Return default settings on failure
                self._settings = Settings()
                return self._settings

    def save_settings(self, settings: Optional[Settings] = None) -> bool:
        """Save settings to file with backup (with caller debug)."""
        import inspect

        with self._lock:
            try:
                if settings is None:
                    settings = self._settings
                    if settings is None:
                        logger.warning("No settings to save")
                        return False

                # Caller inspection for debugging unexpected saves
                stack = inspect.stack()
                caller_frame = stack[1]
                caller_info = f"{caller_frame.function} in {caller_frame.filename}:{caller_frame.lineno}"
                logger.debug(f"SettingsManager.save_settings called from {caller_info}")

                settings_file = self._get_settings_file()

                # Prepare data for saving
                data = settings.model_dump()
                data["version"] = "1.2.1"  # Current version

                # Extract keys for secure storage
                openai_key = data.pop("openai_api_key", None)
                google_key = data.pop("google_api_key", None)
                deepl_key = data.pop("deepl_api_key", None)

                # --- Secure Storage First ---
                # Save keys to keyring BEFORE writing JSON.
                # If this fails, we abort to avoid losing the keys.
                try:
                    if openai_key:
                        if not self._save_key("openai_api_key", openai_key):
                            raise Exception("Failed to save OpenAI key")
                    else:
                        self._delete_key("openai_api_key")

                    if google_key:
                        if not self._save_key("google_api_key", google_key):
                            raise Exception("Failed to save Google key")
                    else:
                        self._delete_key("google_api_key")

                    if deepl_key:
                        if not self._save_key("deepl_api_key", deepl_key):
                            raise Exception("Failed to save DeepL key")
                    else:
                        self._delete_key("deepl_api_key")

                except Exception as e:
                    logger.error(f"Aborting save: Keyring operation failed: {e}")
                    return False

                # Save to JSON (scrubbed of keys)
                with open(settings_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                logger.debug(f"Settings saved to file: {settings_file}")

                self._settings = settings
                logger.info("Settings saved successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to save settings: {e}", exc_info=True)
                return False

    def save_single_setting(self, key: str, value: Any) -> bool:
        """Save a single setting to the file without overwriting others.

        API keys are stored securely in keyring rather than in JSON.
        """
        with self._lock:
            try:
                settings_file = self._get_settings_file()

                # Special handling for API keys (secure storage)
                if key in ("openai_api_key", "google_api_key", "deepl_api_key"):
                    str_value = str(value) if value else ""
                    ok = self._save_key(key, str_value) if str_value else self._delete_key(key)
                    
                    if not ok:
                        return False

                    # Update in-memory settings
                    if self._settings:
                        setattr(self._settings, key, str_value)
                    logger.info(f"Successfully saved secure setting: {key}=****")
                    return True

                # Load existing data
                if settings_file.exists():
                    with open(settings_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    data = {}

                # Security: scrub any API keys if they ever appear in JSON
                for api_key_field in ("openai_api_key", "google_api_key", "deepl_api_key"):
                    data.pop(api_key_field, None)

                # Update the single value
                data[key] = value

                # Write the updated data back
                with open(settings_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                # Update in-memory settings if they exist
                if self._settings:
                    # Create a new validated model instance before assigning
                    new_data = self._settings.model_dump()
                    new_data[key] = value
                    self._settings = Settings(**new_data)

                logger.info(f"Successfully saved single setting: {key}={value}")
                return True

            except Exception as e:
                logger.error(f"Failed to save single setting '{key}': {e}", exc_info=True)
                return False

    def get_settings(self) -> Settings:
        """Get current settings, loading if necessary."""
        with self._lock:
            if self._settings is None:
                return self.load_settings()
            return self._settings

    def update_settings(self, updates: Dict[str, Any]) -> bool:
        """Update specific settings fields."""
        with self._lock:
            try:
                current = self.get_settings()

                # Create updated settings
                updated_data = current.model_dump()
                updated_data.update(updates)

                # Validate new settings
                new_settings = Settings(**updated_data)

                # Save if valid
                return self.save_settings(new_settings)

            except Exception as e:
                logger.error(f"Failed to update settings: {e}")
                return False

# Global settings manager instance
settings_manager = SettingsManager()
