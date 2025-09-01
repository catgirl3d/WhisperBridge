"""
Configuration module for WhisperBridge.

This module handles application configuration, settings loading,
and environment variable management.
"""

import os
import json
import keyring
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal
from pydantic import Field, ConfigDict, field_validator, model_validator
from pydantic_settings import BaseSettings
from loguru import logger


class Settings(BaseSettings):
    """Application settings model with comprehensive validation."""

    # API Settings
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key (stored securely)")
    api_provider: str = Field(default="openai", description="API provider")
    model: str = Field(default="gpt-3.5-turbo", description="GPT model")
    api_timeout: int = Field(default=30, description="API request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum API retry attempts")

    # Language Settings
    source_language: str = Field(default="auto", description="Source language (auto for detection)")
    target_language: str = Field(default="ru", description="Target language")
    supported_languages: List[str] = Field(
        default=["en", "ru", "es", "fr", "de", "it", "pt", "ja", "ko", "zh"],
        description="List of supported languages"
    )

    # Hotkeys
    translate_hotkey: str = Field(default="ctrl+shift+t", description="Translate hotkey")
    quick_translate_hotkey: str = Field(default="ctrl+shift+q", description="Quick translate hotkey")
    activation_hotkey: str = Field(default="ctrl+shift+a", description="Activation hotkey")

    # System Prompt
    system_prompt: str = Field(
        default="You are a professional translator. Translate the following text accurately and naturally. Maintain the original meaning and tone.",
        description="System prompt for GPT translation"
    )

    # OCR Settings
    ocr_languages: List[str] = Field(default=["en", "ru"], description="OCR languages")
    ocr_confidence_threshold: float = Field(default=0.7, description="OCR confidence threshold")
    ocr_timeout: int = Field(default=10, description="OCR timeout in seconds")

    # UI Settings
    ui_backend: Literal["ctk", "qt"] = Field(default="ctk", description="UI backend framework")
    theme: str = Field(default="dark", description="UI theme")
    overlay_position: str = Field(default="cursor", description="Overlay position")
    overlay_timeout: int = Field(default=10, description="Overlay timeout in seconds")
    window_opacity: float = Field(default=0.95, description="Window opacity")
    font_size: int = Field(default=12, description="Font size")
    window_width: int = Field(default=400, description="Default window width")
    window_height: int = Field(default=300, description="Default window height")
    window_geometry: Optional[List[int]] = Field(default=None, description="Window geometry [x, y, width, height]")

    # General Settings
    language: str = Field(default="ru", description="Application language")
    startup_with_system: bool = Field(default=True, description="Start with system")
    show_notifications: bool = Field(default=True, description="Show notifications")
    auto_save_settings: bool = Field(default=True, description="Auto-save settings on change")

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
        env_file=".env",
        case_sensitive=False,
        validate_assignment=True,
        extra='ignore'
    )

    @field_validator('source_language', 'target_language')
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate language codes."""
        if v not in ['auto'] and len(v) != 2:
            raise ValueError(f'Invalid language code: {v}')
        return v

    @field_validator('theme')
    @classmethod
    def validate_theme(cls, v: str) -> str:
        """Validate theme value."""
        valid_themes = ['light', 'dark', 'system']
        if v not in valid_themes:
            raise ValueError(f'Invalid theme: {v}. Must be one of {valid_themes}')
        return v


    @field_validator('api_provider')
    @classmethod
    def validate_api_provider(cls, v: str) -> str:
        """Validate API provider."""
        valid_providers = ['openai', 'anthropic', 'google']
        if v not in valid_providers:
            raise ValueError(f'Invalid API provider: {v}. Must be one of {valid_providers}')
        return v

    @field_validator('ui_backend')
    @classmethod
    def validate_ui_backend(cls, v: str) -> str:
        """Validate UI backend."""
        valid_backends = ['ctk', 'qt']
        if v not in valid_backends:
            raise ValueError(f'Invalid UI backend: {v}. Must be one of {valid_backends}')
        return v

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Invalid log level: {v}. Must be one of {valid_levels}')
        return v.upper()

    @model_validator(mode='after')
    def validate_dependencies(self) -> 'Settings':
        """Validate interdependent settings."""
        if self.source_language == self.target_language and self.source_language != 'auto':
            raise ValueError('Source and target languages cannot be the same')
        return self


# Global settings instance
settings = Settings()


def get_config_path() -> Path:
    """Get the configuration directory path."""
    return Path.home() / ".whisperbridge"


def ensure_config_dir() -> Path:
    """Ensure the configuration directory exists."""
    config_path = get_config_path()
    config_path.mkdir(exist_ok=True)
    return config_path


def load_api_key() -> Optional[str]:
    """Load API key from keyring."""
    try:
        return keyring.get_password("whisperbridge", "openai_api_key")
    except Exception as e:
        logger.warning(f"Failed to load API key from keyring: {e}")
        return None


def save_api_key(api_key: str) -> bool:
    """Save API key to keyring."""
    try:
        keyring.set_password("whisperbridge", "openai_api_key", api_key)
        logger.info("API key saved to keyring")
        return True
    except Exception as e:
        logger.error(f"Failed to save API key to keyring: {e}")
        return False


def load_settings() -> Settings:
    """Load settings from file and environment with error handling."""
    global settings
    try:
        config_path = ensure_config_dir()
        settings_file = config_path / "settings.json"

        # Load from file if exists
        if settings_file.exists():
            with open(settings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {}

        # Load API key from keyring
        api_key = load_api_key()
        if api_key:
            data['openai_api_key'] = api_key

        # Create settings with loaded data
        settings = Settings(**data)
        logger.info("Settings loaded successfully")
        return settings

    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        # Fallback to default settings
        settings = Settings()
        return settings


def save_settings(settings: Settings) -> bool:
    """Save settings to file with error handling."""
    try:
        config_path = ensure_config_dir()
        settings_file = config_path / "settings.json"

        # Prepare data for saving (exclude API key)
        data = settings.model_dump()
        data.pop('openai_api_key', None)

        # Save to JSON
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Save API key separately if present
        if settings.openai_api_key:
            save_api_key(settings.openai_api_key)

        logger.info("Settings saved successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        return False


# Load settings on import
settings = load_settings()