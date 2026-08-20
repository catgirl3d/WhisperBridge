"""Tests for Settings configuration and validation."""

import pytest
from whisperbridge.core.config import (
    API_TIMEOUT_DEFAULT,
    API_TIMEOUT_MAX,
    API_TIMEOUT_MIN,
    OPENAI_MODEL_POLICY,
    Settings,
    filter_openai_model_selection,
)

def test_settings_initialization():
    """Test that settings can be initialized."""
    settings = Settings()
    assert settings.api_provider == "openai"
    assert settings.openai_model == OPENAI_MODEL_POLICY.default_model
    assert settings.openai_vision_model == OPENAI_MODEL_POLICY.default_model
    assert settings.openai_reasoning_effort == "not_set"
    assert settings.api_timeout == API_TIMEOUT_DEFAULT


def test_api_timeout_uses_canonical_range():
    assert Settings(api_timeout=API_TIMEOUT_MIN).api_timeout == API_TIMEOUT_MIN
    assert Settings(api_timeout=API_TIMEOUT_MAX).api_timeout == API_TIMEOUT_MAX
    with pytest.raises(ValueError):
        Settings(api_timeout=API_TIMEOUT_MAX + 1)


def test_openai_model_policy_has_selected_defaults_and_fallbacks():
    """OpenAI defaults and fallback must come from one policy."""
    assert OPENAI_MODEL_POLICY.minimum_version == (5, 4)
    assert OPENAI_MODEL_POLICY.default_model == "gpt-5.4-mini"
    assert OPENAI_MODEL_POLICY.fallback_models == ("gpt-5.4-mini",)


def test_openai_reasoning_effort_accepts_supported_values():
    """OpenAI reasoning effort is stored as an explicit user setting."""
    assert Settings(openai_reasoning_effort="none").openai_reasoning_effort == "none"
    assert Settings(openai_reasoning_effort="xhigh").openai_reasoning_effort == "xhigh"
    assert Settings(openai_reasoning_effort="auto").openai_reasoning_effort == "not_set"


def test_openai_reasoning_effort_rejects_unknown_values():
    """Unknown reasoning modes must not be persisted or sent to the API."""
    with pytest.raises(ValueError):
        Settings(openai_reasoning_effort="unsupported")


def test_filter_openai_model_selection_keeps_supported_families():
    """Both model selectors should use the same current model families."""
    models = [
        "gpt-5.3-mini",
        "gpt-5.4-mini",
        "gpt-5.6-luna",
        "gpt-5.7",
        "gpt-6",
    ]

    assert filter_openai_model_selection(models) == [
        "gpt-5.4-mini",
        "gpt-5.6-luna",
        "gpt-5.7",
        "gpt-6",
    ]

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
