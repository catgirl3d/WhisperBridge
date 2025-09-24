"""
Keyboard Manager for WhisperBridge.

This module provides centralized management of keyboard events,
hotkey parsing, validation, and conversion between different formats.
"""

import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Set

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
                    registered=False,
                )

                self._hotkeys[normalized] = hotkey_info
                logger.info(f"Hotkey registered: {normalized}")
                return True

            except Exception as e:
                logger.error(f"Failed to register hotkey '{combination}': {e}")
                return False

    def get_enabled_hotkeys(self) -> List[str]:
        """Get list of all enabled hotkey combinations.

        Returns:
            List[str]: List of enabled hotkey combinations
        """
        with self._lock:
            return [combo for combo, info in self._hotkeys.items() if info.enabled]

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
                "total_registered": total,
                "enabled": enabled,
                "disabled": disabled,
                "active": len(self._active_hotkeys),
            }

    def set_hotkey_enabled(self, combination: str, enabled: bool) -> bool:
        """Enable or disable a registered hotkey.

        Args:
            combination: Hotkey combination string
            enabled: True to enable, False to disable

        Returns:
            bool: True if hotkey existed and was updated
        """
        with self._lock:
            try:
                normalized = KeyboardUtils.normalize_hotkey(combination)
                info = self._hotkeys.get(normalized)
                if not info:
                    logger.debug(f"set_hotkey_enabled: hotkey not found: {normalized}")
                    return False
                info.enabled = bool(enabled)
                logger.info(f"Hotkey '{normalized}' enabled state set to: {enabled}")
                return True
            except Exception as e:
                logger.error(f"Failed to set enabled state for hotkey '{combination}': {e}")
                return False

    def unregister_hotkey(self, combination: str) -> bool:
        """Unregister/remove a previously registered hotkey.

        Args:
            combination: Hotkey combination string

        Returns:
            bool: True if removed, False if not found
        """
        with self._lock:
            try:
                normalized = KeyboardUtils.normalize_hotkey(combination)
                if normalized in self._hotkeys:
                    del self._hotkeys[normalized]
                    logger.info(f"Unregistered hotkey: {normalized}")
                    return True
                logger.debug(f"unregister_hotkey: hotkey not found: {normalized}")
                return False
            except Exception as e:
                logger.error(f"Failed to unregister hotkey '{combination}': {e}")
                return False

    def _on_hotkey_pressed_internal(self, combination: str):
        """Internal handler for hotkey press events.

        Args:
            combination: The hotkey combination that was pressed
        """
        logger.info(f"Hotkey '{combination}' pressed in thread: {threading.current_thread().name}")
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

        Kept as a no-op hook for future use.
        """
        # Intentionally left as a no-op
        logger.debug(f"KeyboardManager._on_hotkey_released_internal called for: {combination}")
        return
