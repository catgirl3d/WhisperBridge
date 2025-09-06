"""
Settings Manager for WhisperBridge.

This module provides a comprehensive settings management system with
JSON persistence, secure key storage, migration support, and thread-safety.
"""

import json
import shutil
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from datetime import datetime

import keyring
from loguru import logger

from .config import Settings, ensure_config_dir, get_config_path


class SettingsManager:
    """Thread-safe settings manager with persistence and migration support."""

    def __init__(self):
        self._lock = threading.RLock()
        self._settings: Optional[Settings] = None
        self._backup_count = 5
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
        data.setdefault('system_prompt', "You are a professional translator...")
        data.setdefault('activation_hotkey', 'ctrl+shift+a')
        data.setdefault('api_timeout', 30)
        data.setdefault('max_retries', 3)
        data.setdefault('cache_enabled', True)
        data.setdefault('cache_ttl', 3600)

        return data

    def _migrate_from_1_1_0(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate settings from version 1.1.0."""
        logger.info("Migrating settings from version 1.1.0")

        # Add newer fields
        data.setdefault('supported_languages', ["en", "ru", "es", "fr", "de"])
        data.setdefault('thread_pool_size', 4)
        data.setdefault('log_to_file', True)

        return data

    def _migrate_from_1_2_1(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate settings from version 1.2.1."""
        logger.info("Migrating settings from version 1.2.1")

        # Add UI backend field
        data.setdefault('ui_backend', 'qt')
        data.setdefault('copy_translate_hotkey', 'ctrl+shift+j')

        return data

    def _get_settings_file(self) -> Path:
        """Get the path to the settings file."""
        return get_config_path() / "settings.json"

    def _get_backup_dir(self) -> Path:
        """Get the backup directory path."""
        return get_config_path() / "backups"

    def _create_backup(self, settings_file: Path):
        """Create a backup of the current settings file."""
        try:
            backup_dir = self._get_backup_dir()
            backup_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"settings_backup_{timestamp}.json"

            if settings_file.exists():
                shutil.copy2(settings_file, backup_file)

            # Clean old backups
            self._cleanup_old_backups()

            logger.debug(f"Settings backup created: {backup_file}")

        except Exception as e:
            logger.warning(f"Failed to create settings backup: {e}")

    def _cleanup_old_backups(self):
        """Remove old backup files keeping only the most recent ones."""
        try:
            backup_dir = self._get_backup_dir()
            if not backup_dir.exists():
                return

            backups = sorted(backup_dir.glob("settings_backup_*.json"),
                           key=lambda x: x.stat().st_mtime, reverse=True)

            if len(backups) > self._backup_count:
                for old_backup in backups[self._backup_count:]:
                    old_backup.unlink()
                    logger.debug(f"Removed old backup: {old_backup}")

        except Exception as e:
            logger.warning(f"Failed to cleanup old backups: {e}")

    def _load_api_key(self) -> Optional[str]:
        """Load API key from keyring."""
        try:
            return keyring.get_password("whisperbridge", "openai_api_key")
        except Exception as e:
            logger.warning(f"Failed to load API key from keyring: {e}")
            return None

    def _save_api_key(self, api_key: str) -> bool:
        """Save API key to keyring."""
        try:
            keyring.set_password("whisperbridge", "openai_api_key", api_key)
            return True
        except Exception as e:
            logger.error(f"Failed to save API key to keyring: {e}")
            return False

    def _migrate_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply migrations to settings data."""
        current_version = data.get('version', '1.0.0')

        # Apply migrations in order
        for version, handler in sorted(self._migration_handlers.items()):
            if self._compare_versions(current_version, version) < 0:
                try:
                    data = handler(data)
                    data['version'] = version
                    logger.info(f"Applied migration to version {version}")
                except Exception as e:
                    logger.error(f"Failed to apply migration {version}: {e}")

        return data

    def _compare_versions(self, v1: str, v2: str) -> int:
        """Compare two version strings."""
        v1_parts = [int(x) for x in v1.split('.')]
        v2_parts = [int(x) for x in v2.split('.')]

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
                    with open(settings_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # Apply migrations
                    data = self._migrate_settings(data)
                else:
                    data = {}

                # Load API key
                api_key = self._load_api_key()
                if api_key:
                    data['openai_api_key'] = api_key

                # Create and validate settings
                self._settings = Settings(**data)
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
                print(f"DEBUG: SettingsManager.save_settings called from {caller_info}")
                print(f"DEBUG: SettingsManager.save_settings called with theme='{settings.theme}'")

                settings_file = self._get_settings_file()

                # Create backup
                self._create_backup(settings_file)

                # Prepare data for saving
                data = settings.model_dump()
                data['version'] = '1.2.1'  # Current version

                print(f"DEBUG: Data to save - theme='{data.get('theme', 'NOT_FOUND')}'")
                print(f"DEBUG: Full data keys: {list(data.keys())}")

                # Remove API key from JSON (stored in keyring)
                api_key = data.pop('openai_api_key', None)

                # Save to JSON
                with open(settings_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                print(f"DEBUG: Settings saved to file: {settings_file}")

                # Save API key separately
                if api_key:
                    self._save_api_key(api_key)

                self._settings = settings
                logger.info("Settings saved successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to save settings: {e}", exc_info=True)
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

    def reset_to_defaults(self) -> bool:
        """Reset all settings to defaults."""
        with self._lock:
            try:
                default_settings = Settings()
                return self.save_settings(default_settings)
            except Exception as e:
                logger.error(f"Failed to reset settings: {e}")
                return False

    def export_settings(self, export_path: Path) -> bool:
        """Export settings to a file."""
        with self._lock:
            try:
                settings = self.get_settings()
                data = settings.model_dump()

                with open(export_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                logger.info(f"Settings exported to {export_path}")
                return True

            except Exception as e:
                logger.error(f"Failed to export settings: {e}")
                return False

    def import_settings(self, import_path: Path) -> bool:
        """Import settings from a file."""
        with self._lock:
            try:
                with open(import_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Validate imported settings
                imported_settings = Settings(**data)

                # Save imported settings
                return self.save_settings(imported_settings)

            except Exception as e:
                logger.error(f"Failed to import settings: {e}")
                return False


# Global settings manager instance
settings_manager = SettingsManager()