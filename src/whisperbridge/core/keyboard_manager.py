"""
Keyboard Manager for WhisperBridge.

This module provides centralized management of keyboard events,
hotkey parsing, validation, and conversion between different formats.
"""

import threading
from typing import Dict, List, Optional, Callable, Any, Set, Tuple
from dataclasses import dataclass
from loguru import logger

from ..utils.keyboard_utils import KeyboardUtils


@dataclass
class HotkeyInfo:
    """Information about a registered hotkey."""
    combination: str
    callback: Callable[[], Any]
    description: str = ""
    enabled: bool = True
    registered: bool = False


class KeyboardManager:
    """Centralized keyboard event manager."""

    def __init__(self):
        self._lock = threading.RLock()
        self._hotkeys: Dict[str, HotkeyInfo] = {}
        self._active_hotkeys: Set[str] = set()
        self._platform = KeyboardUtils.get_platform()

        logger.info(f"KeyboardManager initialized for platform: {self._platform}")

    def register_hotkey(self, combination: str, callback: Callable[[], Any],
                       description: str = "") -> bool:
        """Register a hotkey combination.

        Args:
            combination: Hotkey combination string (e.g., "ctrl+shift+t")
            callback: Function to call when hotkey is pressed
            description: Optional description of the hotkey

        Returns:
            bool: True if registration successful, False otherwise
        """
        with self._lock:
            try:
                # Validate and normalize the combination
                is_valid, error = KeyboardUtils.validate_hotkey(combination)
                if not is_valid:
                    logger.error(f"Invalid hotkey '{combination}': {error}")
                    return False

                normalized = KeyboardUtils.normalize_hotkey(combination)

                # Check for conflicts
                if normalized in self._hotkeys:
                    logger.warning(f"Hotkey '{normalized}' already registered")
                    return False

                # Create hotkey info
                hotkey_info = HotkeyInfo(
                    combination=normalized,
                    callback=callback,
                    description=description,
                    enabled=True,
                    registered=False
                )

                self._hotkeys[normalized] = hotkey_info
                logger.info(f"Hotkey registered: {normalized}")
                return True

            except Exception as e:
                logger.error(f"Failed to register hotkey '{combination}': {e}")
                return False

    def unregister_hotkey(self, combination: str) -> bool:
        """Unregister a hotkey combination.

        Args:
            combination: Hotkey combination to unregister

        Returns:
            bool: True if unregistration successful, False otherwise
        """
        with self._lock:
            try:
                normalized = KeyboardUtils.normalize_hotkey(combination)

                if normalized not in self._hotkeys:
                    logger.warning(f"Hotkey '{normalized}' not registered")
                    return False

                # Remove from active hotkeys if it's there
                self._active_hotkeys.discard(normalized)

                # Remove from registered hotkeys
                del self._hotkeys[normalized]

                logger.info(f"Hotkey unregistered: {normalized}")
                return True

            except Exception as e:
                logger.error(f"Failed to unregister hotkey '{combination}': {e}")
                return False

    def enable_hotkey(self, combination: str) -> bool:
        """Enable a registered hotkey.

        Args:
            combination: Hotkey combination to enable

        Returns:
            bool: True if enabled successfully, False otherwise
        """
        with self._lock:
            normalized = KeyboardUtils.normalize_hotkey(combination)

            if normalized not in self._hotkeys:
                logger.warning(f"Hotkey '{normalized}' not registered")
                return False

            self._hotkeys[normalized].enabled = True
            logger.info(f"Hotkey enabled: {normalized}")
            return True

    def disable_hotkey(self, combination: str) -> bool:
        """Disable a registered hotkey.

        Args:
            combination: Hotkey combination to disable

        Returns:
            bool: True if disabled successfully, False otherwise
        """
        with self._lock:
            normalized = KeyboardUtils.normalize_hotkey(combination)

            if normalized not in self._hotkeys:
                logger.warning(f"Hotkey '{normalized}' not registered")
                return False

            self._hotkeys[normalized].enabled = False
            logger.info(f"Hotkey disabled: {normalized}")
            return True

    def is_hotkey_registered(self, combination: str) -> bool:
        """Check if a hotkey is registered.

        Args:
            combination: Hotkey combination to check

        Returns:
            bool: True if registered, False otherwise
        """
        with self._lock:
            normalized = KeyboardUtils.normalize_hotkey(combination)
            return normalized in self._hotkeys

    def is_hotkey_enabled(self, combination: str) -> bool:
        """Check if a hotkey is enabled.

        Args:
            combination: Hotkey combination to check

        Returns:
            bool: True if enabled, False otherwise
        """
        with self._lock:
            normalized = KeyboardUtils.normalize_hotkey(combination)
            if normalized not in self._hotkeys:
                return False
            return self._hotkeys[normalized].enabled

    def get_registered_hotkeys(self) -> List[str]:
        """Get list of all registered hotkey combinations.

        Returns:
            List[str]: List of registered hotkey combinations
        """
        with self._lock:
            return list(self._hotkeys.keys())

    def get_enabled_hotkeys(self) -> List[str]:
        """Get list of all enabled hotkey combinations.

        Returns:
            List[str]: List of enabled hotkey combinations
        """
        with self._lock:
            return [combo for combo, info in self._hotkeys.items() if info.enabled]

    def get_hotkey_info(self, combination: str) -> Optional[HotkeyInfo]:
        """Get information about a registered hotkey.

        Args:
            combination: Hotkey combination

        Returns:
            Optional[HotkeyInfo]: Hotkey information or None if not found
        """
        with self._lock:
            normalized = KeyboardUtils.normalize_hotkey(combination)
            return self._hotkeys.get(normalized)

    def validate_hotkey_combination(self, combination: str) -> Tuple[bool, Optional[str]]:
        """Validate a hotkey combination.

        Args:
            combination: Hotkey combination to validate

        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        return KeyboardUtils.validate_hotkey(combination)

    def normalize_hotkey_combination(self, combination: str) -> str:
        """Normalize a hotkey combination.

        Args:
            combination: Hotkey combination to normalize

        Returns:
            str: Normalized hotkey combination
        """
        return KeyboardUtils.normalize_hotkey(combination)

    def format_hotkey_for_display(self, combination: str) -> str:
        """Format hotkey combination for display.

        Args:
            combination: Hotkey combination

        Returns:
            str: Formatted hotkey string
        """
        return KeyboardUtils.format_hotkey_for_display(combination)

    def check_system_conflict(self, combination: str) -> Optional[str]:
        """Check if hotkey conflicts with system shortcuts.

        Args:
            combination: Hotkey combination to check

        Returns:
            Optional[str]: Conflicting system hotkey or None
        """
        return KeyboardUtils.check_system_conflict(combination)

    def suggest_alternative_hotkey(self, combination: str) -> List[str]:
        """Suggest alternative hotkeys for a conflicting combination.

        Args:
            combination: Conflicting hotkey combination

        Returns:
            List[str]: List of suggested alternatives
        """
        return KeyboardUtils.suggest_alternative_hotkey(combination)

    def get_platform_info(self) -> Dict[str, Any]:
        """Get information about the current platform.

        Returns:
            Dict[str, Any]: Platform information
        """
        return {
            'platform': self._platform,
            'available_modifiers': KeyboardUtils.get_available_modifiers(),
            'system_hotkeys': list(KeyboardUtils.SYSTEM_HOTKEYS.get(self._platform, set()))
        }

    def clear_all_hotkeys(self):
        """Clear all registered hotkeys."""
        with self._lock:
            self._hotkeys.clear()
            self._active_hotkeys.clear()
            logger.info("All hotkeys cleared")

    def get_hotkey_statistics(self) -> Dict[str, int]:
        """Get statistics about registered hotkeys.

        Returns:
            Dict[str, int]: Statistics
        """
        with self._lock:
            total = len(self._hotkeys)
            enabled = sum(1 for info in self._hotkeys.values() if info.enabled)
            disabled = total - enabled

            return {
                'total_registered': total,
                'enabled': enabled,
                'disabled': disabled,
                'active': len(self._active_hotkeys)
            }

    def _on_hotkey_pressed_internal(self, combination: str):
        """Internal handler for hotkey press events.

        Args:
            combination: The hotkey combination that was pressed
        """
        with self._lock:
            normalized = KeyboardUtils.normalize_hotkey(combination)

            if normalized not in self._hotkeys:
                logger.warning(f"Received event for unregistered hotkey: {normalized}")
                return

            hotkey_info = self._hotkeys[normalized]

            if not hotkey_info.enabled:
                logger.debug(f"Ignoring disabled hotkey: {normalized}")
                return

            # Add to active hotkeys
            self._active_hotkeys.add(normalized)

            try:
                # Execute callback
                logger.debug(f"Executing hotkey callback: {normalized}")
                hotkey_info.callback()

            except Exception as e:
                logger.error(f"Error executing hotkey callback for '{normalized}': {e}")

            finally:
                # Remove from active hotkeys
                self._active_hotkeys.discard(normalized)

    def _on_hotkey_released_internal(self, combination: str):
        """Internal handler for hotkey release events.

        Args:
            combination: The hotkey combination that was released
        """
        # This can be used for more complex hotkey handling if needed
        pass