"""
UI components package.

This package contains reusable UI components for the WhisperBridge application,
including language selectors, hotkey inputs, and prompt editors.
"""

from .language_selector import LanguageSelector
from .hotkey_input import HotkeyInput
from .prompt_editor import PromptEditor

__all__ = ['LanguageSelector', 'HotkeyInput', 'PromptEditor']