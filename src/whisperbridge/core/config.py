"""
Configuration module for WhisperBridge.

This module handles application configuration, settings loading,
and environment variable management.
"""

import json
import re
from pathlib import Path
from typing import List, Literal, Optional

import keyring
from loguru import logger
from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings model with comprehensive validation."""

    # API Settings
    openai_api_key: Optional[str] = Field(
        default=None, description="OpenAI API key (stored securely)"
    )
    google_api_key: Optional[str] = Field(
        default=None, description="Google Generative AI API key (stored securely)"
    )
    api_provider: str = Field(default="openai", description="API provider")
    openai_model: str = Field(default="gpt-5-nano", description="Default OpenAI model")
    google_model: str = Field(default="gemini-1.5-flash", description="Default Google model")
    api_timeout: int = Field(default=30, description="API request timeout in seconds")
    default_models: Optional[List[str]] = Field(
        default=None, description="Custom default models list (overrides built-in default)"
    )

    # Language Settings (legacy - now handled by UI overlay)
    supported_languages: List[str] = Field(
        default=["en", "ru", "de", "ua"], description="List of supported languages"
    )

    # Overlay UI-specific language selections (do not affect core behavior)
    # - ui_source_language: "auto" or explicit ISO code
    # - ui_target_mode: "auto_swap" or "explicit"
    # - ui_target_language: explicit ISO code used when ui_target_mode == "explicit"
    ui_source_language: str = Field(default="auto", description="Overlay UI source language ('auto' or ISO code)")
    ui_target_mode: Literal["auto_swap", "explicit"] = Field(default="explicit", description="Overlay UI target selection mode")
    ui_target_language: str = Field(default="en", description="Overlay UI explicit target language (ISO code)")

    # Translation behavior flags
    # When True, OCR translation will auto-swap between English and Russian:
    # - If OCR detects English, translate to Russian
    # - If OCR detects Russian, translate to English
    ocr_auto_swap_en_ru: bool = Field(
        default=True,
        description="If enabled, OCR translations will auto-swap EN <-> RU based on detected language",
    )

    # Hotkeys
    translate_hotkey: str = Field(default="ctrl+shift+t", description="Translate hotkey")
    quick_translate_hotkey: str = Field(default="ctrl+shift+q", description="Quick translate hotkey")
    activation_hotkey: str = Field(default="ctrl+shift+a", description="Activation hotkey")
    copy_translate_hotkey: str = Field(default="ctrl+shift+j", description="Hotkey that copies selected text and translates it")

    # Copy-Translate enhancements
    auto_copy_translated: bool = Field(
        default=False, description="Automatically copy translated text to clipboard"
    )
    clipboard_poll_timeout_ms: int = Field(
        default=2000,
        description="Clipboard polling timeout in milliseconds (used by clipboard monitoring)",
    )

    # System Prompt
    system_prompt: str = Field(
        default="You are a translation engine. Do not reason. Do not explain. Do not add any extra text. Only return the translated text.",
        description="System prompt for GPT translation",
    )

    # OCR Settings
    ocr_languages: List[str] = Field(default=["en", "ru"], description="OCR languages")
    ocr_confidence_threshold: float = Field(default=0.7, description="OCR confidence threshold")
    ocr_timeout: int = Field(default=10, description="OCR timeout in seconds")
    # OCR initialization flag (default: disabled)
    initialize_ocr: bool = Field(
        default=False,
        description="Initialize OCR service on startup and enable OCR actions",
    )

    # UI Settings
    theme: str = Field(default="light", description="UI theme")
    font_size: int = Field(default=12, description="Font size")
    window_width: int = Field(default=400, description="Default window width")
    window_height: int = Field(default=300, description="Default window height")
    window_geometry: Optional[List[int]] = Field(default=None, description="Window geometry [x, y, width, height]")
    overlay_window_geometry: Optional[List[int]] = Field(default=None, description="Overlay window geometry [x, y, width, height]")

    # General Settings
    show_notifications: bool = Field(default=True, description="Show notifications")

    # Performance Settings
    cache_enabled: bool = Field(default=True, description="Enable caching")
    cache_ttl: int = Field(default=3600, description="Cache TTL in seconds")
    max_cache_size: int = Field(default=100, description="Maximum cache size")
    thread_pool_size: int = Field(default=4, description="Thread pool size")

    # Logging Settings
    log_level: str = Field(default="INFO", description="Logging level")
    log_to_file: bool = Field(default=True, description="Log to file")
    max_log_size: int = Field(default=10, description="Max log file size in MB")

    model_config = ConfigDict(
        env_file=".env", case_sensitive=False, validate_assignment=True, extra="ignore"
    )

    @field_validator("ui_source_language", "ui_target_language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate language codes."""
        if v not in ["auto"] and len(v) != 2:
            raise ValueError(f"Invalid language code: {v}")
        return v

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v: str) -> str:
        """Validate theme value."""
        valid_themes = ["light", "dark", "system"]
        if v not in valid_themes:
            raise ValueError(f"Invalid theme: {v}. Must be one of {valid_themes}")
        return v

    @field_validator("api_provider")
    @classmethod
    def validate_api_provider(cls, v: str) -> str:
        """Validate API provider format."""
        if not v or not isinstance(v, str) or not v.strip():
            raise ValueError("API provider must be a non-empty string.")
        # Allow any provider name, removing the hardcoded list.
        # The system will dynamically handle the provider as long as
        # a corresponding '{provider}_model' setting exists.
        return v.strip().lower()

    @field_validator("clipboard_poll_timeout_ms")
    @classmethod
    def validate_clipboard_timeout(cls, v: int) -> int:
        """Validate clipboard polling timeout (ms). Must be between 500 and 10000."""
        try:
            iv = int(v)
        except Exception:
            raise ValueError("clipboard_poll_timeout_ms must be an integer")
        if iv < 500 or iv > 10000:
            raise ValueError("clipboard_poll_timeout_ms must be between 500 and 10000")
        return iv

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()




def get_config_path() -> Path:
    """Get the configuration directory path."""
    return Path.home() / ".whisperbridge"


def ensure_config_dir() -> Path:
    """Ensure the configuration directory exists."""
    config_path = get_config_path()
    config_path.mkdir(exist_ok=True)
    return config_path


def load_api_key(provider: str = "openai") -> Optional[str]:
    """Load API key for the given provider from keyring."""
    try:
        if provider.lower() == "google":
            return keyring.get_password("whisperbridge", "google_api_key")
        # default to openai for backward compatibility
        return keyring.get_password("whisperbridge", "openai_api_key")
    except Exception as e:
        logger.warning(f"Failed to load {provider} API key from keyring: {e}")
        return None


def save_api_key(api_key: str, provider: str = "openai") -> bool:
    """Save API key for the given provider to keyring."""
    try:
        if provider.lower() == "google":
            keyring.set_password("whisperbridge", "google_api_key", api_key)
        else:
            keyring.set_password("whisperbridge", "openai_api_key", api_key)
        logger.info(f"{provider.capitalize()} API key saved to keyring")
        return True
    except Exception as e:
        logger.error(f"Failed to save {provider} API key to keyring: {e}")
        return False


def delete_api_key(provider: str = "openai") -> bool:
    """Delete API key for the given provider from keyring."""
    try:
        if provider.lower() == "google":
            keyring.delete_password("whisperbridge", "google_api_key")
        else:
            keyring.delete_password("whisperbridge", "openai_api_key")
        logger.info(f"{provider.capitalize()} API key deleted from keyring")
        return True
    except Exception as e:
        logger.error(f"Failed to delete {provider} API key from keyring: {e}")
        return False


def validate_api_key_format(api_key: str, provider: Optional[str] = "openai") -> bool:
    """Validate API key format for supported providers.

    Supported providers:
      - openai: keys start with 'sk-' and contain 20+ characters (letters, digits, '-', or '_') after the prefix
      - google: keys start with 'AIza' followed by 35+ URL-safe characters (letters, digits, '_' or '-')
    """
    if not api_key or not isinstance(api_key, str):
        return False

    prov = (provider or "openai").lower()

    try:
        if prov == "openai":
            pattern = r"^sk-[A-Za-z0-9_-]{20,}$"
            return bool(re.match(pattern, api_key))
        if prov == "google":
            pattern = r"^AIza[0-9A-Za-z_-]{35,}$"
            return bool(re.match(pattern, api_key))
        # Generic fallback for unknown providers
        return len(api_key) >= 16
    except Exception:
        return False
