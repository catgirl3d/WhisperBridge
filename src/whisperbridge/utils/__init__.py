"""
Utilities package for WhisperBridge.

This package contains helper functions and utilities used throughout
the WhisperBridge application for common operations and data processing.
"""

from .config_utils import (
    cleanup_old_files,
    dict_to_settings,
    format_hotkey,
    get_available_ocr_engines,
    get_available_themes,
    get_cache_dir,
    get_config_dir,
    get_file_size_mb,
    get_language_name,
    get_log_dir,
    get_system_info,
    is_valid_language_code,
    merge_settings_dicts,
    normalize_hotkey,
    parse_hotkey,
    sanitize_filename,
    settings_to_dict,
    validate_api_key_format,
    validate_config_file,
    validate_hotkey,
    validate_ocr_engine,
    validate_openai_api_key,
    validate_theme,
)
from .window_utils import WindowUtils

__all__ = [
    "get_config_dir",
    "get_log_dir",
    "get_cache_dir",
    "validate_openai_api_key",
    "get_language_name",
    "validate_hotkey",
    "get_available_themes",
    "sanitize_filename",
    "is_valid_language_code",
    "validate_api_key_format",
    "parse_hotkey",
    "format_hotkey",
    "normalize_hotkey",
    "validate_theme",
    "get_available_ocr_engines",
    "validate_ocr_engine",
    "get_file_size_mb",
    "cleanup_old_files",
    "validate_config_file",
    "get_system_info",
    "merge_settings_dicts",
    "settings_to_dict",
    "dict_to_settings",
    "WindowUtils",
]
