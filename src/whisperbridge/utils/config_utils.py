"""
Configuration Utilities for WhisperBridge.

This module provides utility functions for configuration management,
including path handling, API key validation, language utilities, and hotkey management.
"""

import os
import re
import platform
from pathlib import Path
from typing import Any, Dict, List, Tuple

from loguru import logger

from ..core.config import Settings, get_config_path


# Path Utilities
def get_config_dir() -> Path:
    """Get the configuration directory path."""
    return get_config_path()


def get_log_dir() -> Path:
    """Get the log directory path."""
    return get_config_path() / "logs"


def get_cache_dir() -> Path:
    """Get the cache directory path."""
    return get_config_path() / "cache"


def get_temp_dir() -> Path:
    """Get the temporary directory path."""
    return get_config_path() / "temp"


def ensure_dir(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_app_data_dir() -> Path:
    """Get the application data directory for the current platform."""
    system = platform.system()

    if system == "Windows":
        base_dir = Path(os.environ.get("APPDATA", "~/.whisperbridge"))
    elif system == "Darwin":  # macOS
        base_dir = Path.home() / "Library" / "Application Support" / "WhisperBridge"
    else:  # Linux and others
        base_dir = Path.home() / ".whisperbridge"

    return base_dir.expanduser()


# API Key Validation
def validate_openai_api_key(api_key: str) -> bool:
    """Validate OpenAI API key format."""
    if not api_key or not isinstance(api_key, str):
        return False

    # OpenAI API keys start with 'sk-' and are followed by characters
    pattern = r"^sk-[a-zA-Z0-9]{48,}$"
    return bool(re.match(pattern, api_key))


def validate_api_key_format(api_key: str, provider: str) -> bool:
    """Validate API key format for different providers."""
    if not api_key:
        return False

    patterns = {
        "openai": r"^sk-[a-zA-Z0-9]{48,}$",
        "anthropic": r"^sk-ant-[a-zA-Z0-9_-]{95,}$",
        "google": r"^AIza[0-9A-Za-z_-]{35}$",
    }

    pattern = patterns.get(provider.lower())
    if not pattern:
        return len(api_key) > 10  # Generic validation

    return bool(re.match(pattern, api_key))


def mask_api_key(api_key: str, visible_chars: int = 4) -> str:
    """Mask API key for display purposes."""
    if not api_key or len(api_key) <= visible_chars:
        return api_key

    return api_key[:visible_chars] + "*" * (len(api_key) - visible_chars)


# Language Utilities
LANGUAGE_NAMES = {
    "auto": "Auto-detect",
    "en": "English",
    "ru": "Russian",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic",
    "hi": "Hindi",
    "tr": "Turkish",
    "pl": "Polish",
    "nl": "Dutch",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
}


def get_language_name(code: str) -> str:
    """Get the display name for a language code."""
    return LANGUAGE_NAMES.get(code.lower(), code.upper())


def get_supported_languages() -> Dict[str, str]:
    """Get dictionary of supported languages."""
    return LANGUAGE_NAMES.copy()


def is_valid_language_code(code: str) -> bool:
    """Check if a language code is valid."""
    return code.lower() in LANGUAGE_NAMES


def detect_language_from_text(text: str) -> str:
    """Simple language detection based on character sets."""
    # This is a basic implementation - in production, use a proper language detection library
    text = text.strip()

    # Cyrillic characters (Russian, etc.)
    if re.search(r"[а-яё]", text.lower()):
        return "ru"

    # Japanese characters
    if re.search(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]", text):
        return "ja"

    # Korean characters
    if re.search(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]", text):
        return "ko"

    # Chinese characters
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"

    # Arabic characters
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"

    # Default to English
    return "en"


# Hotkey Utilities
def parse_hotkey(hotkey_str: str) -> List[str]:
    """Parse a hotkey string into modifier + key components."""
    if not hotkey_str:
        return []

    parts = [part.strip().lower() for part in hotkey_str.split("+")]
    return parts


def format_hotkey(parts: List[str]) -> str:
    """Format hotkey parts into a string."""
    return "+".join(part.capitalize() for part in parts)


def validate_hotkey(hotkey_str: str) -> bool:
    """Validate a hotkey string format."""
    if not hotkey_str:
        return False

    parts = parse_hotkey(hotkey_str)
    if len(parts) < 1:
        return False

    valid_modifiers = {"ctrl", "alt", "shift", "cmd", "win", "super"}
    valid_keys = set("abcdefghijklmnopqrstuvwxyz0123456789") | {
        "f1",
        "f2",
        "f3",
        "f4",
        "f5",
        "f6",
        "f7",
        "f8",
        "f9",
        "f10",
        "f11",
        "f12",
        "space",
        "enter",
        "tab",
        "escape",
        "backspace",
        "delete",
        "insert",
        "home",
        "end",
        "pageup",
        "pagedown",
        "up",
        "down",
        "left",
        "right",
    }

    # Check modifiers
    modifiers = parts[:-1]
    key = parts[-1]

    for mod in modifiers:
        if mod not in valid_modifiers:
            return False

    # Check key
    return key in valid_keys


def normalize_hotkey(hotkey_str: str) -> str:
    """Normalize a hotkey string to standard format."""
    parts = parse_hotkey(hotkey_str)
    return format_hotkey(parts)


# Theme Utilities
def get_available_themes() -> List[str]:
    """Get list of available UI themes."""
    return ["light", "dark", "system"]


def validate_theme(theme: str) -> bool:
    """Validate theme name."""
    return theme.lower() in get_available_themes()


# OCR Engine Utilities
def get_available_ocr_engines() -> List[str]:
    """Get list of available OCR engines."""
    return ["easyocr", "paddleocr"]


def validate_ocr_engine(engine: str) -> bool:
    """Validate OCR engine name."""
    return engine.lower() in get_available_ocr_engines()


# File and Path Utilities
def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by removing invalid characters."""
    # Remove invalid characters for Windows, macOS, and Linux
    invalid_chars = '<>:"/\\|?*'
    sanitized = "".join(c for c in filename if c not in invalid_chars)

    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(" .")

    # Ensure it's not empty
    if not sanitized:
        sanitized = "untitled"

    return sanitized


def get_file_size_mb(file_path: Path) -> float:
    """Get file size in megabytes."""
    if not file_path.exists():
        return 0.0

    size_bytes = file_path.stat().st_size
    return size_bytes / (1024 * 1024)


def cleanup_old_files(directory: Path, max_age_days: int = 30, pattern: str = "*") -> int:
    """Clean up old files in a directory."""
    import time

    if not directory.exists():
        return 0

    cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
    deleted_count = 0

    for file_path in directory.glob(pattern):
        if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
            try:
                file_path.unlink()
                deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete old file {file_path}: {e}")

    return deleted_count


# Configuration Validation
def validate_config_file(config_path: Path) -> Tuple[bool, List[str]]:
    """Validate a configuration file and return errors."""
    errors = []

    if not config_path.exists():
        errors.append(f"Configuration file does not exist: {config_path}")
        return False, errors

    try:
        import json

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validate required fields
        required_fields = ["version"]
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")

        # Validate version format
        if "version" in data:
            version = data["version"]
            if not isinstance(version, str) or not re.match(
                r"^\d+\.\d+\.\d+$", version
            ):
                errors.append(f"Invalid version format: {version}")

    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON format: {e}")
    except Exception as e:
        errors.append(f"Error reading configuration: {e}")

    return len(errors) == 0, errors


# System Information
def get_system_info() -> Dict[str, str]:
    """Get system information for logging/debugging."""
    return {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "config_dir": str(get_config_dir()),
        "app_data_dir": str(get_app_data_dir()),
    }


# Utility Functions for Settings
def merge_settings_dicts(base: Dict, updates: Dict) -> Dict:
    """Merge two settings dictionaries."""
    result = base.copy()
    result.update(updates)
    return result


def settings_to_dict(settings: Settings) -> Dict:
    """Convert Settings object to dictionary."""
    return settings.model_dump()


def dict_to_settings(data: Dict) -> Settings:
    """Convert dictionary to Settings object."""
    return Settings(**data)


def compare_settings(old: Settings, new: Settings) -> Dict[str, Tuple[Any, Any]]:
    """Compare two Settings objects and return differences."""
    differences = {}

    old_dict = old.model_dump()
    new_dict = new.model_dump()

    for key in set(old_dict.keys()) | set(new_dict.keys()):
        old_value = old_dict.get(key)
        new_value = new_dict.get(key)

        if old_value != new_value:
            differences[key] = (old_value, new_value)

    return differences
