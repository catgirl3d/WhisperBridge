"""
Tests for ModelManager class in api_manager.models module.

This module tests model management functionality including:
- Getting available models from cache/API
- Temporary API key handling
- Model filtering
- Default model retrieval
- Fallback model retrieval
- Cache invalidation on API errors
"""

import pytest

from whisperbridge.core.api_manager.cache import ModelCache
from whisperbridge.core.api_manager.models import ModelManager
from whisperbridge.core.api_manager.providers import APIProvider
from whisperbridge.core.api_manager.types import ModelSource
from whisperbridge.core.config import OPENAI_MODEL_POLICY


@pytest.fixture
def mock_cache(tmp_path, mocker):
    """Create a mock ModelCache for testing."""
    # We create a real ModelCache object but mock its methods if needed
    cache = ModelCache(tmp_path, ttl_seconds=1209600)
    return cache


@pytest.fixture
def mock_provider_registry(mocker):
    """Create a mock ProviderRegistry for testing."""
    registry = mocker.Mock()
    # Default behavior: provider is available
    registry.is_provider_available = mocker.Mock(return_value=True)
    registry.get_client = mocker.Mock(return_value=None)
    return registry


@pytest.fixture
def model_manager(mock_cache, mock_config_service, mock_provider_registry):
    """Create a ModelManager instance for testing."""
    return ModelManager(mock_cache, mock_config_service, mock_provider_registry)


class TestGetAvailableModels:
    """Tests for get_available_models method."""

    def test_get_available_models_from_cache(self, model_manager, mock_cache, mock_provider_registry, mocker):
        """Cached OpenAI models are re-filtered by exclusions and policy."""
        models = ["gpt-5.3", "whisper-1", "omni-moderation-latest", "gpt-5.4-mini"]
        timestamp = 1234567890.0
        mock_provider_registry.is_provider_available.return_value = True
        mocker.patch.object(mock_cache, "get", return_value=(models, timestamp))
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=["whisper"],
        )

        result_models, source = model_manager.get_available_models(APIProvider.OPENAI)

        assert result_models == ["gpt-5.4-mini"]
        assert source == ModelSource.CACHE.value
        mock_cache.get.assert_called_once_with("openai")

    def test_get_available_models_refreshes_fully_filtered_cache(
        self, model_manager, mock_cache, mock_provider_registry, mocker
    ):
        """A cache invalidated by current filters must fall through to the API."""
        mocker.patch.object(mock_cache, "get", return_value=(["gpt-5.3"], 1234567890.0))
        mocker.patch.object(mock_cache, "cache_models_and_persist")
        mock_provider_registry.is_provider_available.return_value = True
        mock_client = mocker.Mock()
        mock_client.models.list.return_value.data = [mocker.Mock(id="gpt-5.4-mini")]
        mock_provider_registry.get_client.return_value = mock_client

        result_models, source = model_manager.get_available_models(APIProvider.OPENAI)

        assert result_models == ["gpt-5.4-mini"]
        assert source == ModelSource.API.value
        mock_client.models.list.assert_called_once_with()
        mock_cache.cache_models_and_persist.assert_called_once_with(
            "openai", ["gpt-5.4-mini"]
        )

    def test_get_available_models_from_api(self, model_manager, mock_cache, mock_provider_registry, mocker):
        """OpenAI API results retain only current models and cache those results."""
        mocker.patch.object(mock_cache, "get", return_value=None)
        mocker.patch.object(mock_cache, "cache_models_and_persist")
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=[],
        )
        mock_client = mocker.Mock()
        mock_models_response = mocker.Mock()
        mock_models_response.data = [
            mocker.Mock(id="gpt-5.3"),
            mocker.Mock(id="gpt-5.6-luna"),
            mocker.Mock(id="omni-moderation-latest"),
            mocker.Mock(id="gpt-5.4-mini"),
        ]
        mock_client.models.list.return_value = mock_models_response
        mock_provider_registry.is_provider_available.return_value = True
        mock_provider_registry.get_client.return_value = mock_client

        result_models, source = model_manager.get_available_models(APIProvider.OPENAI)

        assert result_models == ["gpt-5.6-luna", "gpt-5.4-mini"]
        assert source == ModelSource.API.value
        mock_cache.cache_models_and_persist.assert_called_once_with(
            "openai", ["gpt-5.6-luna", "gpt-5.4-mini"]
        )

    def test_get_available_models_hides_latest_aliases_and_keeps_supported_chatgpt_models(
        self, model_manager, mock_cache, mock_provider_registry, mocker
    ):
        """The picker retains supported named ChatGPT models but excludes latest aliases."""
        mocker.patch.object(mock_cache, "get", return_value=None)
        mocker.patch.object(mock_cache, "cache_models_and_persist")
        mock_client = mocker.Mock()
        mock_client.models.list.return_value.data = [
            mocker.Mock(id="gpt-5.3"),
            mocker.Mock(id="gpt-5.4-mini"),
            mocker.Mock(id="gpt-5.7-latest"),
            mocker.Mock(id="chatgpt-5.6"),
            mocker.Mock(id="chatgpt-5.6-latest"),
        ]
        mock_provider_registry.get_client.return_value = mock_client

        result_models, source = model_manager.get_available_models(APIProvider.OPENAI)

        assert result_models == ["chatgpt-5.6", "gpt-5.4-mini"]
        assert source == ModelSource.API.value
        mock_cache.cache_models_and_persist.assert_called_once_with(
            "openai", ["chatgpt-5.6", "gpt-5.4-mini"]
        )

    def test_get_available_models_with_temp_key(self, model_manager, mock_cache, mock_provider_registry, mocker):
        """Temporary OpenAI fetch applies the current-model policy."""
        mock_client = mocker.Mock()
        mocker.patch.object(mock_cache, "cache_models_and_persist")
        mock_models_response = mocker.Mock()
        mock_models_response.data = [mocker.Mock(id="gpt-5.3")]
        mock_client.models.list.return_value = mock_models_response
        mock_openai_adapter = mocker.patch(
            "whisperbridge.core.api_manager.models.OpenAIChatClientAdapter",
            return_value=mock_client,
        )

        result_models, source = model_manager.get_available_models(
            APIProvider.OPENAI,
            temp_api_key="sk-temp123",
        )

        assert result_models == []
        assert source == ModelSource.API_TEMP_KEY.value
        mock_openai_adapter.assert_called_once()
        mock_cache.cache_models_and_persist.assert_not_called()

    def test_get_available_models_with_temp_key_applies_openai_filters_and_ranking(
        self, model_manager, mock_cache, mock_provider_registry, mocker
    ):
        """Temporary OpenAI fetch uses exclusion, policy, and ranking rules."""
        mock_client = mocker.Mock()
        mocker.patch.object(mock_cache, "cache_models_and_persist")
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=["whisper", "audio"],
        )
        mock_models_response = mocker.Mock()
        mock_models_response.data = [
            mocker.Mock(id="gpt-5.4-audio-preview"),
            mocker.Mock(id="whisper-1"),
            mocker.Mock(id="omni-moderation-latest"),
            mocker.Mock(id="gpt-5.6-luna"),
        ]
        mock_client.models.list.return_value = mock_models_response
        mock_openai_adapter = mocker.patch(
            "whisperbridge.core.api_manager.models.OpenAIChatClientAdapter",
            return_value=mock_client,
        )

        result_models, source = model_manager.get_available_models(
            APIProvider.OPENAI,
            temp_api_key="sk-temp123",
        )

        assert result_models == ["gpt-5.6-luna"]
        assert source == ModelSource.API_TEMP_KEY.value
        mock_openai_adapter.assert_called_once()
        mock_cache.cache_models_and_persist.assert_not_called()



    def test_get_available_models_unconfigured_provider(self, model_manager, mock_cache, mock_provider_registry, mocker):
        """Test unconfigured providers ignore cache and return UNCONFIGURED."""
        # Arrange
        mock_provider_registry.is_provider_available.return_value = False
        mocker.patch.object(mock_cache, "get", return_value=(["stale-model"], 1234567890.0))

        # Act
        result_models, source = model_manager.get_available_models(APIProvider.GOOGLE)

        # Assert
        assert result_models == []
        assert source == ModelSource.UNCONFIGURED.value
        mock_cache.get.assert_not_called()


class TestApplyFilters:
    """Tests for provider exclusion and ordering behavior."""

    def test_apply_filters_openai(self, model_manager, mocker):
        """OpenAI exclusions remove non-chat variants before selection."""
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=["audio", "preview"],
        )
        models = ["gpt-5.4-mini", "gpt-5.6-luna", "gpt-5.4-audio-preview", "omni-moderation-latest"]

        result = model_manager.apply_filters(APIProvider.OPENAI, models)

        assert result == ["gpt-5.6-luna", "gpt-5.4-mini"]

    def test_apply_filters_openai_prefix_and_substring_excludes(self, model_manager, mocker):
        """OpenAI exclusions support both prefixes and substrings."""
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=["legacy-prefix", "audio"],
        )
        models = ["legacy-prefix-model", "gpt-5.4-audio-preview", "gpt-5.7", "moderation-model"]

        result = model_manager.apply_filters(APIProvider.OPENAI, models)

        assert result == ["gpt-5.7"]

    def test_apply_filters_openai_excludes_non_chat_models(self, model_manager, mocker):
        """OpenAI selection keeps only GPT and ChatGPT model families."""
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=[],
        )

        result = model_manager.apply_filters(
            APIProvider.OPENAI,
            ["gpt-5.4-mini", "chatgpt-5.6-latest", "omni-moderation-latest"],
        )

        assert result == ["gpt-5.4-mini", "chatgpt-5.6-latest"]

    def test_apply_filters_google_excludes(self, model_manager, mocker):
        """Google exclusions remove matching models and retain others."""
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_google_model_excludes",
            return_value=["embedding", "audio"],
        )
        models = ["gemini-2.5-flash", "palm-2", "gemini-1.5-pro", "embedding-001"]

        result = model_manager.apply_filters(APIProvider.GOOGLE, models)

        assert "gemini-2.5-flash" in result
        assert "gemini-1.5-pro" in result
        assert "palm-2" in result
        assert "embedding-001" not in result

    def test_apply_filters_non_llm_provider_passthrough(self, model_manager):
        """Non-LLM providers return models unchanged."""
        models = ["deepl-translate", "audio-preview"]

        assert model_manager.apply_filters(APIProvider.DEEPL, models) == models

    def test_google_model_ranking(self, model_manager, mocker):
        """Google models are ranked flash, pro, other, with latest last."""
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_google_model_excludes",
            return_value=[],
        )
        models = [
            "gemini-1.5-pro",
            "gemini-1.5-flash-latest",
            "gemini-2.0-flash",
            "gemini-1.0-pro-latest",
        ]

        result = model_manager.apply_filters(APIProvider.GOOGLE, models)

        assert result == [
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash-latest",
            "gemini-1.0-pro-latest",
        ]

    def test_google_model_ranking_with_other_model(self, model_manager, mocker):
        """Google ranking places an unclassified model after flash and pro."""
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_google_model_excludes",
            return_value=[],
        )
        models = [
            "gemini-1.0",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.0-latest",
        ]

        result = model_manager.apply_filters(APIProvider.GOOGLE, models)

        assert result == [
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.0",
            "gemini-1.0-latest",
        ]

    def test_openai_model_ranking(self, model_manager, mocker):
        """Current GPT models are ranked by version and model family."""
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=[],
        )
        models = [
            "gpt-5.4-mini",
            "gpt-5.6-luna",
            "gpt-5.7",
            "gpt-5.4",
            "gpt-5.7-latest",
        ]

        result = model_manager.apply_filters(APIProvider.OPENAI, models)

        assert result == [
            "gpt-5.7",
            "gpt-5.6-luna",
            "gpt-5.4-mini",
            "gpt-5.4",
            "gpt-5.7-latest",
        ]

    def test_openai_model_ranking_keeps_latest_aliases_last(self, model_manager, mocker):
        """Current-model latest aliases stay at the end."""
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=[],
        )
        models = ["gpt-5.7-latest", "gpt-5.4-mini", "gpt-5.6-luna"]

        result = model_manager.apply_filters(APIProvider.OPENAI, models)

        assert result == ["gpt-5.6-luna", "gpt-5.4-mini", "gpt-5.7-latest"]

    def test_openai_model_ranking_with_current_versions(self, model_manager, mocker):
        """Current versions precede reasoning and latest aliases."""
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=[],
        )
        models = ["gpt-5.7-latest", "gpt-5.4-mini", "gpt-5.6-luna"]

        result = model_manager.apply_filters(APIProvider.OPENAI, models)

        assert result == ["gpt-5.6-luna", "gpt-5.4-mini", "gpt-5.7-latest"]


class TestGetDefaultModels:
    """Tests for get_default_models method."""

    def test_get_default_models_from_config(self, model_manager, mock_config_service):
        """Test getting custom default models from config."""
        # Arrange
        custom_models = ["custom-model-1", "custom-model-2"]
        mock_config_service.get_setting.side_effect = (
            lambda key: custom_models if key == "default_models" else None
        )

        # Act
        result = model_manager.get_default_models()

        # Assert
        assert result == custom_models
        mock_config_service.get_setting.assert_called_once_with("default_models")

    def test_get_default_models_builtin_fallback(self, model_manager, mock_config_service):
        """Test fallback to built-in models when config is None."""
        # Arrange
        mock_config_service.get_setting.side_effect = (
            lambda key: None if key == "default_models" else ["unexpected-model"]
        )

        # Act
        result = model_manager.get_default_models()

        # Assert
        assert result == list(OPENAI_MODEL_POLICY.fallback_models)
        mock_config_service.get_setting.assert_called_once_with("default_models")


class TestGetFallbackModels:
    """Tests for get_fallback_models method."""

    def test_get_fallback_models_openai(self, model_manager, mock_cache, mocker):
        """Test fallback models for OpenAI."""
        # Arrange
        mocker.patch.object(mock_cache, "cache_models_and_persist")

        # Act
        models, source = model_manager.get_fallback_models(APIProvider.OPENAI)

        # Assert
        assert models == list(OPENAI_MODEL_POLICY.fallback_models)
        assert source == ModelSource.FALLBACK.value
        mock_cache.cache_models_and_persist.assert_called_once_with(
            "openai", list(OPENAI_MODEL_POLICY.fallback_models)
        )

    def test_get_fallback_models_google(self, model_manager, mock_cache, mocker):
        """Test fallback models for Google."""
        # Arrange
        mocker.patch.object(mock_cache, "cache_models_and_persist")

        # Act
        models, source = model_manager.get_fallback_models(APIProvider.GOOGLE)

        # Assert
        assert models == ["gemini-2.5-flash", "gemini-1.5-flash"]
        assert source == ModelSource.FALLBACK.value
        mock_cache.cache_models_and_persist.assert_called_once_with(
            "google", ["gemini-2.5-flash", "gemini-1.5-flash"]
        )

    def test_get_fallback_models_deepl(self, model_manager, mock_cache, mocker):
        """Test fallback model for DeepL."""
        # Arrange
        mocker.patch.object(mock_cache, "cache_models_and_persist")
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_deepl_identifier",
            return_value="deepl-translate"
        )

        # Act
        models, source = model_manager.get_fallback_models(APIProvider.DEEPL)

        # Assert
        assert models == ["deepl-translate"]
        assert source == ModelSource.FALLBACK.value
        mock_cache.cache_models_and_persist.assert_called_once()


class TestCacheInvalidation:
    """Tests for cache invalidation on API errors."""

    def test_cache_invalidation_on_api_error(self, model_manager, mock_cache, mock_provider_registry, mocker):
        """Test that cache is cleared on API error."""
        # Arrange
        mocker.patch.object(mock_cache, "get", return_value=None)
        mocker.patch.object(mock_cache, "clear")
        
        mock_client = mocker.Mock()
        mock_client.models.list.side_effect = Exception("API Error")
        mock_provider_registry.is_provider_available.return_value = True
        mock_provider_registry.get_client.return_value = mock_client

        # Act
        result_models, source = model_manager.get_available_models(APIProvider.OPENAI)

        # Assert
        assert result_models == []
        assert source == ModelSource.ERROR.value
        mock_cache.clear.assert_called_once_with(APIProvider.OPENAI.value)
