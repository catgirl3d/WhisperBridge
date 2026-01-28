"""
Keyboard utilities for WhisperBridge.

This module provides utilities for working with keyboard combinations,
converting between different formats, and validating hotkey strings.
"""

import re
from typing import Dict, List, Optional, Set, Tuple

from loguru import logger

# Platform-specific key mappings
PLATFORM_KEYS = {
    "windows": {"cmd": "win", "super": "win", "meta": "win", "control": "ctrl"},
    "linux": {"cmd": "super", "win": "super", "meta": "super", "control": "ctrl"},
    "darwin": {"win": "cmd", "super": "cmd", "meta": "cmd", "control": "ctrl"},
}

# Standard modifier keys
MODIFIERS = {"ctrl", "alt", "shift", "cmd", "win", "super", "meta"}

# Special keys that need special handling
SPECIAL_KEYS = {
    "space": "space",
    "enter": "enter",
    "return": "enter",
    "tab": "tab",
    "esc": "esc",
    "escape": "esc",
    "backspace": "backspace",
    "delete": "delete",
    "del": "delete",  # Alternative name for delete
    "insert": "insert",
    "home": "home",
    "end": "end",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "f1": "f1",
    "f2": "f2",
    "f3": "f3",
    "f4": "f4",
    "f5": "f5",
    "f6": "f6",
    "f7": "f7",
    "f8": "f8",
    "f9": "f9",
    "f10": "f10",
    "f11": "f11",
    "f12": "f12",
}

# Common system hotkeys to avoid conflicts
SYSTEM_HOTKEYS = {
    "windows": {
        "ctrl+alt+del",
        "ctrl+shift+esc",
        "win+d",
        "win+l",
        "win+r",
        "alt+f4",
        "alt+tab",
        "ctrl+c",
        "ctrl+v",
        "ctrl+x",
        "ctrl+z",
        "ctrl+a",
        "ctrl+s",
        "ctrl+o",
        "ctrl+n",
        "ctrl+w",
        "ctrl+q",
    },
    "linux": {
        "ctrl+alt+t",
        "ctrl+alt+l",
        "alt+f2",
        "ctrl+alt+del",
        "ctrl+c",
        "ctrl+v",
        "ctrl+x",
        "ctrl+z",
        "ctrl+a",
        "ctrl+s",
    },
    "darwin": {
        "cmd+space",
        "cmd+tab",
        "cmd+q",
        "cmd+w",
        "cmd+c",
        "cmd+v",
        "cmd+x",
        "cmd+z",
        "cmd+a",
        "cmd+s",
        "cmd+o",
        "cmd+n",
        "ctrl+cmd+f",
        "ctrl+cmd+space",
    },
}


# Windows Virtual Key Codes (VK) for absolute reliability (e.g., RDP, layout issues)
# Only defined for Windows platform as primary fallback.
WIN_VK_MAP = {
    # Modifiers
    "ctrl": 17, "alt": 18, "shift": 16, "win": 91,
    # Letters
    "a": 65, "b": 66, "c": 67, "d": 68, "e": 69, "f": 70, "g": 71, "h": 72,
    "i": 73, "j": 74, "k": 75, "l": 76, "m": 77, "n": 78, "o": 79, "p": 80,
    "q": 81, "r": 82, "s": 83, "t": 84, "u": 85, "v": 86, "w": 87, "x": 88,
    "y": 89, "z": 90,
    # Numbers
    "0": 48, "1": 49, "2": 50, "3": 51, "4": 52, "5": 53, "6": 54, "7": 55, "8": 56, "9": 57,
    # Function keys
    "f1": 112, "f2": 113, "f3": 114, "f4": 115, "f5": 116, "f6": 117,
    "f7": 118, "f8": 119, "f9": 120, "f10": 121, "f11": 122, "f12": 123,
    # Special
    "space": 32, "enter": 13, "esc": 27, "tab": 9, "backspace": 8, "delete": 46,
    "up": 38, "down": 40, "left": 37, "right": 39, "home": 36, "end": 35,
    "pageup": 33, "pagedown": 34, "insert": 45,
}

# Inverse map for looking up names from VK codes
_VK_TO_NAME_MAP = {v: k for k, v in WIN_VK_MAP.items()}

class KeyboardUtils:
    """Utility class for keyboard operations."""

    @staticmethod
    def get_platform() -> str:
        """Get the current platform."""
        import platform

        system = platform.system().lower()
        if system == "windows":
            return "windows"
        elif system == "linux":
            return "linux"
        elif system == "darwin":
            return "darwin"
        else:
            return "unknown"

    @staticmethod
    def get_vks_for_hotkey(hotkey: str) -> Set[int]:
        """Resolve a hotkey string into a set of Windows VK codes.
        
        Args:
            hotkey: Hotkey string (e.g., "ctrl+alt+j")
            
        Returns:
            Set[int]: Set of integer VK codes. Empty set if resolution fails.
        """
        if not hotkey:
            return set()
            
        normalized = KeyboardUtils.normalize_hotkey(hotkey)
        parts = normalized.split("+")
        vks = set()
        
        platform = KeyboardUtils.get_platform()
        if platform != "windows":
            return set() # VK-based matching is primarily for Windows/RDP issues
            
        for part in parts:
            if part in WIN_VK_MAP:
                vks.add(WIN_VK_MAP[part])
            else:
                logger.debug(f"Key '{part}' not found in VK map")
                return set() # Entire combination fails if one key is unknown
                
        return vks

    @staticmethod
    def get_name_from_vk(vk: int) -> Optional[str]:
        """Get the standardized key name from a Window VK code.
        
        Args:
            vk: The integer Virtual Key code.
            
        Returns:
            Optional[str]: The standardized key name (e.g., 'a', 'enter'), or None if not found.
        """
        return _VK_TO_NAME_MAP.get(vk)

    @staticmethod
    def normalize_hotkey(hotkey: str) -> str:
        """Normalize hotkey string to standard format.

        Args:
            hotkey: Hotkey string to normalize

        Returns:
            str: Normalized hotkey string
        """
        if not hotkey:
            return ""

        # Convert to lowercase
        hotkey = hotkey.lower().strip()

        # Split by '+'
        parts = [part.strip() for part in hotkey.split("+") if part.strip()]

        if not parts:
            return ""

        # Normalize modifiers
        modifiers = []
        main_key = None

        for part in parts:
            if part in MODIFIERS:
                # Normalize modifier
                normalized = KeyboardUtils._normalize_modifier(part)
                if normalized and normalized not in modifiers:
                    modifiers.append(normalized)
            else:
                # This should be the main key
                if main_key is None:
                    main_key = KeyboardUtils._normalize_key(part)
                else:
                    logger.warning(f"Multiple main keys in hotkey: {hotkey}")

        if not main_key:
            logger.warning(f"No main key found in hotkey: {hotkey}")
            return ""

        # Sort modifiers for consistency
        modifiers.sort()

        # Combine
        if modifiers:
            return "+".join(modifiers + [main_key])
        else:
            return main_key

    @staticmethod
    def _normalize_modifier(modifier: str) -> Optional[str]:
        """Normalize modifier key name."""
        modifier = modifier.lower()

        # Platform-specific normalization
        platform = KeyboardUtils.get_platform()
        platform_map = PLATFORM_KEYS.get(platform, {})

        if modifier in platform_map:
            return platform_map[modifier]

        # Standard normalization
        if modifier in {"ctrl", "control"}:
            return "ctrl"
        elif modifier in {"alt", "option"}:
            return "alt"
        elif modifier in {"shift"}:
            return "shift"
        elif modifier in {"cmd", "command", "super", "win", "meta"}:
            if platform == "darwin":
                return "cmd"
            elif platform == "windows":
                return "win"
            else:
                return "super"

        return None

    @staticmethod
    def _normalize_key(key: str) -> Optional[str]:
        """Normalize main key name."""
        key = key.lower()

        # Check special keys
        if key in SPECIAL_KEYS:
            return SPECIAL_KEYS[key]

        # Single character
        if len(key) == 1 and key.isalnum():
            return key

        # Function keys
        if re.match(r"^f\d+$", key):
            return key

        # Numpad keys
        if key.startswith("numpad") or key.startswith("num"):
            return key

        return None

    @staticmethod
    def validate_hotkey(hotkey: str) -> Tuple[bool, Optional[str]]:
        """Validate hotkey string.

        Args:
            hotkey: Hotkey string to validate

        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        if not hotkey or not isinstance(hotkey, str):
            return False, "Hotkey cannot be empty"

        # Normalize first
        normalized = KeyboardUtils.normalize_hotkey(hotkey)
        if not normalized:
            return False, "Invalid hotkey format"

        # Check format
        parts = normalized.split("+")
        if len(parts) < 1:
            return False, "Hotkey must have at least one key"

        # Check for conflicts with system hotkeys
        conflict = KeyboardUtils.check_system_conflict(normalized)
        if conflict:
            return False, f"Hotkey conflicts with system shortcut: {conflict}"

        return True, None

    @staticmethod
    def check_system_conflict(hotkey: str) -> Optional[str]:
        """Check if hotkey conflicts with system shortcuts.

        Args:
            hotkey: Normalized hotkey string

        Returns:
            Optional[str]: Conflicting system hotkey or None
        """
        platform = KeyboardUtils.get_platform()
        system_hotkeys = SYSTEM_HOTKEYS.get(platform, set())

        normalized = KeyboardUtils.normalize_hotkey(hotkey)

        for system_hotkey in system_hotkeys:
            if KeyboardUtils.normalize_hotkey(system_hotkey) == normalized:
                return system_hotkey

        return None


