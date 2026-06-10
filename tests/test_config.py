"""Tests for Settings configuration and validation."""

import pytest
from whisperbridge.core.config import Settings

def test_settings_initialization():
    """Test that settings can be initialized."""
    settings = Settings()
    assert settings.api_provider == "openai"

def test_ocr_engine_migration():
    """Test that legacy ocr_engine values are correctly migrated to 'llm'."""
    # Test migration from 'easyocr' to 'llm'
    settings = Settings(ocr_engine="easyocr")
    assert settings.ocr_engine == "llm", "Legacy 'easyocr' should be migrated to 'llm'"

    # Test that 'llm' remains unchanged
    settings = Settings(ocr_engine="llm")
    assert settings.ocr_engine == "llm", "Valid 'llm' should remain unchanged"

    # Test that any other value also gets migrated to 'llm'
    settings = Settings(ocr_engine="some_other_engine")
    assert settings.ocr_engine == "llm", "Any non-'llm' value should be migrated to 'llm'"


def test_translator_font_size_is_normalized_by_settings_model():
    """translator_font_size should be clamped and coerced at the Settings boundary."""
    assert Settings(translator_font_size="19").translator_font_size == 19
    assert Settings(translator_font_size=3).translator_font_size == 8
    assert Settings(translator_font_size=99).translator_font_size == 32
    assert Settings(translator_font_size=True).translator_font_size == 9
