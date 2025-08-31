"""
Keyboard utilities for WhisperBridge.

This module provides utilities for working with keyboard combinations,
converting between different formats, and validating hotkey strings.
"""

import re
from typing import List, Dict, Set, Optional, Tuple
from loguru import logger

# Platform-specific key mappings
PLATFORM_KEYS = {
    'windows': {
        'cmd': 'win',
        'super': 'win',
        'meta': 'win',
        'control': 'ctrl'
    },
    'linux': {
        'cmd': 'super',
        'win': 'super',
        'meta': 'super',
        'control': 'ctrl'
    },
    'darwin': {
        'win': 'cmd',
        'super': 'cmd',
        'meta': 'cmd',
        'control': 'ctrl'
    }
}

# Standard modifier keys
MODIFIERS = {'ctrl', 'alt', 'shift', 'cmd', 'win', 'super', 'meta'}

# Special keys that need special handling
SPECIAL_KEYS = {
    'space': 'space',
    'enter': 'enter',
    'return': 'enter',
    'tab': 'tab',
    'esc': 'esc',
    'escape': 'esc',
    'backspace': 'backspace',
    'delete': 'delete',
    'del': 'delete',  # Alternative name for delete
    'insert': 'insert',
    'home': 'home',
    'end': 'end',
    'pageup': 'pageup',
    'pagedown': 'pagedown',
    'up': 'up',
    'down': 'down',
    'left': 'left',
    'right': 'right',
    'f1': 'f1', 'f2': 'f2', 'f3': 'f3', 'f4': 'f4',
    'f5': 'f5', 'f6': 'f6', 'f7': 'f7', 'f8': 'f8',
    'f9': 'f9', 'f10': 'f10', 'f11': 'f11', 'f12': 'f12'
}

# Common system hotkeys to avoid conflicts
SYSTEM_HOTKEYS = {
    'windows': {
        'ctrl+alt+del', 'ctrl+shift+esc', 'win+d', 'win+l', 'win+r',
        'alt+f4', 'alt+tab', 'ctrl+c', 'ctrl+v', 'ctrl+x', 'ctrl+z',
        'ctrl+a', 'ctrl+s', 'ctrl+o', 'ctrl+n', 'ctrl+w', 'ctrl+q'
    },
    'linux': {
        'ctrl+alt+t', 'ctrl+alt+l', 'alt+f2', 'ctrl+alt+del',
        'ctrl+c', 'ctrl+v', 'ctrl+x', 'ctrl+z', 'ctrl+a', 'ctrl+s'
    },
    'darwin': {
        'cmd+space', 'cmd+tab', 'cmd+q', 'cmd+w', 'cmd+c', 'cmd+v',
        'cmd+x', 'cmd+z', 'cmd+a', 'cmd+s', 'cmd+o', 'cmd+n',
        'ctrl+cmd+f', 'ctrl+cmd+space'
    }
}


class KeyboardUtils:
    """Utility class for keyboard operations."""

    @staticmethod
    def get_platform() -> str:
        """Get the current platform."""
        import platform
        system = platform.system().lower()
        if system == 'windows':
            return 'windows'
        elif system == 'linux':
            return 'linux'
        elif system == 'darwin':
            return 'darwin'
        else:
            return 'unknown'

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
        parts = [part.strip() for part in hotkey.split('+') if part.strip()]

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
            return '+'.join(modifiers + [main_key])
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
        if modifier in {'ctrl', 'control'}:
            return 'ctrl'
        elif modifier in {'alt', 'option'}:
            return 'alt'
        elif modifier in {'shift'}:
            return 'shift'
        elif modifier in {'cmd', 'command', 'super', 'win', 'meta'}:
            if platform == 'darwin':
                return 'cmd'
            elif platform == 'windows':
                return 'win'
            else:
                return 'super'

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
        if re.match(r'^f\d+$', key):
            return key

        # Numpad keys
        if key.startswith('numpad') or key.startswith('num'):
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
        parts = normalized.split('+')
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

    @staticmethod
    def parse_hotkey_to_pynput(hotkey: str) -> Optional[Dict[str, List[str]]]:
        """Parse hotkey string to pynput format.

        Args:
            hotkey: Hotkey string

        Returns:
            Optional[Dict[str, List[str]]]: Pynput hotkey format or None if invalid
        """
        normalized = KeyboardUtils.normalize_hotkey(hotkey)
        if not normalized:
            return None

        parts = normalized.split('+')
        if not parts:
            return None

        modifiers = []
        main_key = None

        for part in parts:
            if part in MODIFIERS:
                modifiers.append(part)
            else:
                main_key = part

        if not main_key:
            return None

        return {
            'modifiers': modifiers,
            'key': main_key
        }

    @staticmethod
    def format_hotkey_for_pynput(hotkey: str) -> str:
        """Format hotkey string for pynput GlobalHotKeys.

        Args:
            hotkey: Normalized hotkey string

        Returns:
            str: Hotkey formatted for pynput (e.g., '<ctrl>+<shift>+t')
        """
        normalized = KeyboardUtils.normalize_hotkey(hotkey)
        if not normalized:
            return ""

        parts = normalized.split('+')
        if not parts:
            return ""

        formatted_parts = []
        for i, part in enumerate(parts):
            if i < len(parts) - 1:  # All except last are modifiers
                formatted_parts.append(f"<{part}>")
            else:  # Last part is the main key
                formatted_parts.append(part)

        return '+'.join(formatted_parts)

    @staticmethod
    def format_hotkey_for_display(hotkey: str) -> str:
        """Format hotkey for display purposes.

        Args:
            hotkey: Hotkey string

        Returns:
            str: Formatted hotkey string
        """
        if not hotkey:
            return ""

        normalized = KeyboardUtils.normalize_hotkey(hotkey)
        if not normalized:
            return hotkey

        parts = normalized.split('+')

        # Capitalize modifiers
        formatted_parts = []
        for part in parts[:-1]:  # All except last
            formatted_parts.append(part.capitalize())

        # Last part (main key)
        main_key = parts[-1]
        if len(main_key) == 1:
            formatted_parts.append(main_key.upper())
        elif main_key in SPECIAL_KEYS.values():
            formatted_parts.append(main_key.capitalize())
        else:
            formatted_parts.append(main_key)

        return ' + '.join(formatted_parts)

    @staticmethod
    def get_available_modifiers() -> List[str]:
        """Get list of available modifiers for current platform.

        Returns:
            List[str]: List of modifier keys
        """
        platform = KeyboardUtils.get_platform()

        if platform == 'darwin':
            return ['cmd', 'ctrl', 'alt', 'shift']
        elif platform == 'windows':
            return ['ctrl', 'alt', 'shift', 'win']
        else:  # linux and others
            return ['ctrl', 'alt', 'shift', 'super']

    @staticmethod
    def suggest_alternative_hotkey(conflicting_hotkey: str) -> List[str]:
        """Suggest alternative hotkeys if the given one conflicts.

        Args:
            conflicting_hotkey: The conflicting hotkey

        Returns:
            List[str]: List of suggested alternatives
        """
        suggestions = []

        # Try different modifier combinations
        modifiers = KeyboardUtils.get_available_modifiers()
        main_keys = ['t', 'q', 'a', 's', 'd', 'f', 'g', 'h', 'j', 'k']

        for mod1 in modifiers:
            for mod2 in modifiers:
                if mod1 != mod2:
                    for key in main_keys:
                        candidate = f"{mod1}+{mod2}+{key}"
                        if not KeyboardUtils.check_system_conflict(candidate):
                            suggestions.append(candidate)
                            if len(suggestions) >= 5:  # Limit suggestions
                                return suggestions

        return suggestions