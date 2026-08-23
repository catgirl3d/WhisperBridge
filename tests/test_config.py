"""Tests for Settings configuration and validation."""

import pytest
from whisperbridge.core.provider_catalog import get_supported_provider_values
from whisperbridge.core.config import (
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
    assert settings.api_timeout == 30


def test_api_provider_is_normalized_to_catalog_default(loguru_caplog):
    """Unknown and empty provider settings fall back without rejecting the config."""
    assert Settings(api_provider="unknown").api_provider == "openai"
    assert Settings(api_provider=" ").api_provider == "openai"

    assert sum("Invalid API provider" in record.message for record in loguru_caplog.records) == 2


def test_supported_provider_values_follow_catalog():
    """The public config list is derived from the provider enum catalog."""
    from whisperbridge.core.config import SUPPORTED_PROVIDERS

    assert SUPPORTED_PROVIDERS == get_supported_provider_values()


def test_api_timeout_uses_canonical_range():
    assert Settings(api_timeout=1).api_timeout == 1
    assert Settings(api_timeout=60).api_timeout == 60
    with pytest.raises(ValueError):
        Settings(api_timeout=0)
    with pytest.raises(ValueError):
        Settings(api_timeout=61)


def test_openai_model_policy_has_selected_defaults():
    """OpenAI selection defaults must come from one policy."""
    assert OPENAI_MODEL_POLICY.minimum_version == (5, 4)
    assert OPENAI_MODEL_POLICY.default_model == "gpt-5.4-mini"


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
        "chatgpt-5.3",
        "gpt-5.4-mini",
        "chatgpt-5.6",
        "gpt-5.6-luna",
        "gpt-5.7",
        "gpt-6",
    ]

    assert filter_openai_model_selection(models) == [
        "gpt-5.4-mini",
        "chatgpt-5.6",
        "gpt-5.6-luna",
        "gpt-5.7",
        "gpt-6",
    ]

def test_translator_font_size_is_normalized_by_settings_model():
    """translator_font_size should be clamped and coerced at the Settings boundary."""
    assert Settings(translator_font_size="19").translator_font_size == 19
    assert Settings(translator_font_size=3).translator_font_size == 8
    assert Settings(translator_font_size=99).translator_font_size == 32
    assert Settings(translator_font_size=True).translator_font_size == 9
