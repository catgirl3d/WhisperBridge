"""
Utilities package for WhisperBridge.

This package contains helper functions and utilities used throughout
the WhisperBridge application for common operations and data processing.
"""

from .language_utils import get_language_name
from .window_utils import WindowUtils

__all__ = [
    "get_language_name",
    "WindowUtils",
]
