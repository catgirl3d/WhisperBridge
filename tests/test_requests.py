"""
Tests for RequestBuilder class in api_manager.requests module.

This module tests request building functionality including:
- Temperature support detection for models
- Temperature adjustment for restricted models
- LLM parameter building
- DeepL parameter building
- Temperature and limits resolution
"""

import pytest

from whisperbridge.core.api_manager.requests import (
    RequestBuilder,
    adjust_temperature_for_model,
    model_supports_temperature,
)


class TestModelSupportsTemperature:
    """Tests for model_supports_temperature function."""

    def test_model_supports_temperature_standard_models(self):
        """Test that standard models support temperature."""
        # Arrange & Act & Assert
        assert model_supports_temperature("gpt-4o-mini") is True
        assert model_supports_temperature("gpt-4o") is True
        assert model_supports_temperature("gemini-2.5-flash") is True
        assert model_supports_temperature("gemini-1.5-pro") is True

    def test_model_supports_temperature_reasoning_models(self):
        """Test that reasoning models do NOT support temperature."""
        # Arrange & Act & Assert
        assert model_supports_temperature("o1-preview") is False
        assert model_supports_temperature("o1-mini") is False
        assert model_supports_temperature("o3-mini") is False
        assert model_supports_temperature("gpt-5-nano") is False
        assert model_supports_temperature("gpt-5-pro") is False


class TestAdjustTemperatureForModel:
    """Tests for adjust_temperature_for_model function."""

    def test_adjust_temperature_for_restricted_model(self, loguru_caplog):
        """Test that temperature is forced to 1.0 for restricted models."""
        # Arrange & Act
        result = adjust_temperature_for_model("o1-preview", 0.7)

        # Assert
        assert result == 1.0
        assert any(
            "does not support custom temperature" in record.message
            for record in loguru_caplog.records
        )

    def test_adjust_temperature_for_standard_model(self):
        """Test that temperature is NOT changed for standard models."""
        # Arrange & Act
        result = adjust_temperature_for_model("gpt-4o", 0.5)

        # Assert
        assert result == 0.5


class TestRequestBuilderLLMParams:
    """Tests for LLM parameter building."""

    def test_build_llm_params_with_explicit_temperature(self, mocker):
        """Test building LLM params with explicit temperature."""
        # Arrange
        mock_config = mocker.Mock()
        mock_config.get_setting.return_value = 1.0

        builder = RequestBuilder(mock_config)
        messages = [{"role": "user", "content": "Hello"}]

        # Act
        params = builder.build_llm_params(
            model="gpt-4",
            messages=messages,
            temperature=0.8,
            temperature_setting_key="llm_temperature_translation",
            temperature_default=1.0,
            log_label="Translation",
        )

        # Assert
        assert params["model"] == "gpt-4"
        assert params["messages"] == messages
        assert params["temperature"] == 0.8
        assert "max_completion_tokens" in params

    def test_build_llm_params_temperature_from_config(self, mocker):
        """Test that temperature is loaded from config when not provided."""
        # Arrange
        mock_config = mocker.Mock()
        mock_config.get_setting.return_value = 0.9

        builder = RequestBuilder(mock_config)
        messages = [{"role": "user", "content": "Hello"}]

        # Act
        params = builder.build_llm_params(
            model="gpt-4",
            messages=messages,
            temperature=None,
            temperature_setting_key="llm_temperature_translation",
            temperature_default=1.0,
            log_label="Translation",
        )

        # Assert
        assert params["temperature"] == 0.9
        mock_config.get_setting.assert_called_with("llm_temperature_translation")

    def test_build_llm_params_temperature_fallback(self, mocker, loguru_caplog):
        """Test fallback to default when config value is invalid."""
        # Arrange
        mock_config = mocker.Mock()
        mock_config.get_setting.return_value = "invalid-string"

        builder = RequestBuilder(mock_config)
        messages = [{"role": "user", "content": "Hello"}]

        # Act
        params = builder.build_llm_params(
            model="gpt-4",
            messages=messages,
            temperature=None,
            temperature_setting_key="llm_temperature_translation",
            temperature_default=1.0,
            log_label="Translation",
        )

        # Assert
        assert params["temperature"] == 1.0
        assert any(
            "Failed to parse translation temperature" in record.message
            for record in loguru_caplog.records
        )


class TestRequestBuilderDeepLParams:
    """Tests for DeepL parameter building."""

    def test_build_deepl_params(self, mocker):
        """Test building DeepL-specific parameters."""
        # Arrange
        mock_config = mocker.Mock()
        builder = RequestBuilder(mock_config)
        messages = [{"role": "user", "content": "Translate this"}]
        api_kwargs = {"target_lang": "DE", "source_lang": "EN"}

        # Act
        params = builder.build_deepl_params(
            model="deepl",
            messages=messages,
            api_kwargs=api_kwargs,
        )

        # Assert
        assert params["model"] == "deepl"
        assert params["messages"] == messages
        assert params["target_lang"] == "DE"
        assert params["source_lang"] == "EN"

    def test_build_deepl_params_without_api_kwargs(self, mocker):
        """Test building DeepL params without additional kwargs."""
        # Arrange
        mock_config = mocker.Mock()
        builder = RequestBuilder(mock_config)
        messages = [{"role": "user", "content": "Translate this"}]

        # Act
        params = builder.build_deepl_params(
            model="deepl",
            messages=messages,
            api_kwargs=None,
        )

        # Assert
        assert params["model"] == "deepl"
        assert params["messages"] == messages
        assert "target_lang" not in params


class TestResolveTemperatureAndLimits:
    """Tests for temperature and limits resolution."""

    def test_resolve_temperature_and_limits(self, mocker):
        """Test resolving temperature and max completion tokens."""
        # Arrange
        mock_config = mocker.Mock()
        mock_config.get_setting.return_value = 0.7

        builder = RequestBuilder(mock_config)

        # Act
        temp, max_tokens = builder.resolve_llm_temperature_and_limits(
            model="gpt-4o",
            temperature=0.7,
            temperature_setting_key="llm_temperature_translation",
            temperature_default=1.0,
            log_label="Translation",
        )

        # Assert
        assert temp == 0.7
        assert isinstance(max_tokens, int)
        assert max_tokens > 0

    def test_resolve_temperature_for_restricted_model(self, mocker):
        """Test that temperature is adjusted for restricted models."""
        # Arrange
        mock_config = mocker.Mock()
        mock_config.get_setting.return_value = 0.5

        builder = RequestBuilder(mock_config)

        # Act
        temp, max_tokens = builder.resolve_llm_temperature_and_limits(
            model="o1-preview",
            temperature=0.5,
            temperature_setting_key="llm_temperature_translation",
            temperature_default=1.0,
            log_label="Translation",
        )

        # Assert
        assert temp == 1.0  # Forced to 1.0 for reasoning models
        assert isinstance(max_tokens, int)
