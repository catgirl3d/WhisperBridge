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
        """Test getting models from cache."""
        # Arrange
        models = ["gpt-5-mini", "gpt-4o"]
        timestamp = 1234567890.0
        
        # Ensure provider is seen as configured
        mock_provider_registry.is_provider_available.return_value = True
        
        # Patch the get method of the cache object
        mocker.patch.object(mock_cache, "get", return_value=(models, timestamp))
        
        # Ensure apply_filters doesn't filter out our test models
        mocker.patch.object(model_manager, "apply_filters", side_effect=lambda p, m: m)

        # Act
        result_models, source = model_manager.get_available_models(APIProvider.OPENAI)

        # Assert
        assert result_models == models
        assert source == ModelSource.CACHE.value
        mock_cache.get.assert_called_once_with("openai")

    def test_get_available_models_from_api(self, model_manager, mock_cache, mock_provider_registry, mocker):
        """Test fetching models from API when cache is empty."""
        # Arrange
        mocker.patch.object(mock_cache, "get", return_value=None)
        mock_client = mocker.Mock()

        # Mock models.list() response
        mock_model1 = mocker.Mock()
        mock_model1.id = "gpt-5-mini"
        mock_model2 = mocker.Mock()
        mock_model2.id = "gpt-4o"
        mock_models_response = mocker.Mock()
        mock_models_response.data = [mock_model1, mock_model2]

        mock_client.models.list.return_value = mock_models_response
        mock_provider_registry.is_provider_available.return_value = True
        mock_provider_registry.get_client.return_value = mock_client

        # Act
        result_models, source = model_manager.get_available_models(APIProvider.OPENAI)

        # Assert
        assert "gpt-5-mini" in result_models
        assert "gpt-4o" in result_models
        assert source == ModelSource.API.value

    def test_get_available_models_with_temp_key(self, model_manager, mock_provider_registry, mocker):
        """Test using temporary API key without caching."""
        # Arrange
        mock_client = mocker.Mock()

        # Mock models.list() response
        mock_model = mocker.Mock()
        mock_model.id = "gpt-5-nano"
        mock_models_response = mocker.Mock()
        mock_models_response.data = [mock_model]

        mock_client.models.list.return_value = mock_models_response

        # Mock temporary client creation
        mock_openai_adapter = mocker.patch(
            "whisperbridge.core.api_manager.models.OpenAIChatClientAdapter",
            return_value=mock_client
        )

        # Act
        result_models, source = model_manager.get_available_models(
            APIProvider.OPENAI,
            temp_api_key="sk-temp123"
        )

        # Assert
        assert result_models == ["gpt-5-nano"]
        assert source == ModelSource.API_TEMP_KEY.value
        mock_openai_adapter.assert_called_once()

    def test_get_available_models_unconfigured_provider(self, model_manager, mock_cache, mock_provider_registry, mocker):
        """Test behavior when provider is not configured."""
        # Arrange
        mock_provider_registry.is_provider_available.return_value = False
        mocker.patch.object(mock_cache, "get", return_value=None)

        # Act
        result_models, source = model_manager.get_available_models(APIProvider.GOOGLE)

        # Assert
        assert result_models == []
        assert source == ModelSource.UNCONFIGURED.value


class TestApplyFilters:
    """Tests for apply_filters method."""

    def test_apply_filters_openai(self, model_manager, mocker):
        """Test filtering OpenAI models by excludes."""
        # Arrange
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=["audio", "preview"]
        )

        models = ["gpt-5-mini", "gpt-4o", "gpt-4o-audio-preview"]

        # Act
        result = model_manager.apply_filters(APIProvider.OPENAI, models)

        # Assert
        assert "gpt-5-mini" in result
        assert "gpt-4o" in result
        assert "gpt-4o-audio-preview" not in result

    def test_apply_filters_openai_prefix_and_substring_excludes(self, model_manager, mocker):
        """Test OpenAI excludes for prefix and substring matches."""
        # Arrange
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=["gpt-4", "audio"]
        )
        models = ["gpt-4o", "gpt-4o-audio-preview", "gpt-5-nano"]

        # Act
        result = model_manager.apply_filters(APIProvider.OPENAI, models)

        # Assert
        assert result == ["gpt-5-nano"]

    def test_apply_filters_google_excludes(self, model_manager, mocker):
        """Test filtering Google models by excludes (non-gemini remains unless excluded)."""
        # Arrange
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_google_model_excludes",
            return_value=["embedding", "audio"]
        )

        models = ["gemini-2.5-flash", "palm-2", "gemini-1.5-pro", "embedding-001"]

        # Act
        result = model_manager.apply_filters(APIProvider.GOOGLE, models)

        # Assert
        assert "gemini-2.5-flash" in result
        assert "gemini-1.5-pro" in result
        assert "palm-2" in result 
        assert "embedding-001" not in result

    def test_apply_filters_non_llm_provider_passthrough(self, model_manager):
        """Test that non-LLM providers return models unchanged."""
        # Arrange
        models = ["deepl-translate", "audio-preview"]

        # Act
        result = model_manager.apply_filters(APIProvider.DEEPL, models)

        # Assert
        assert result == models

    def test_google_model_ranking(self, model_manager, mocker):
        """Test that Google models are ranked correctly (flash -> pro -> other, latest at end)."""
        # Arrange
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_google_model_excludes",
            return_value=[]
        )
        models = [
            "gemini-1.5-pro",
            "gemini-1.5-flash-latest",
            "gemini-2.0-flash",
            "gemini-1.0-pro-latest"
        ]

        # Act
        result = model_manager.apply_filters(APIProvider.GOOGLE, models)

        # Assert
        assert result == [
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash-latest",
            "gemini-1.0-pro-latest"
        ]

    def test_google_model_ranking_with_other_model(self, model_manager, mocker):
        """Test Google ranking when a model is neither flash nor pro."""
        # Arrange
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_google_model_excludes",
            return_value=[]
        )
        models = [
            "gemini-1.0",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.0-latest"
        ]

        # Act
        result = model_manager.apply_filters(APIProvider.GOOGLE, models)

        # Assert
        assert result == [
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.0",
            "gemini-1.0-latest"
        ]

    def test_openai_model_ranking(self, model_manager, mocker):
        """Test that OpenAI models are ranked correctly (gpt-5 nano/mini/std -> other -> gpt-4 -> latest)."""
        # Arrange
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=[]
        )
        models = [
            "gpt-4o",
            "gpt-5-mini",
            "gpt-5-nano",
            "gpt-4o-latest",
            "gpt-5",
            "o1-mini"
        ]

        # Act
        result = model_manager.apply_filters(APIProvider.OPENAI, models)

        # Assert
        assert result == [
            "gpt-5-nano",
            "gpt-5-mini",
            "gpt-5",
            "o1-mini",
            "gpt-4o",
            "gpt-4o-latest"
        ]

    def test_openai_model_ranking_with_chatgpt4(self, model_manager, mocker):
        """Test OpenAI ranking treats chatgpt-4 as GPT-4 and keeps latest last."""
        # Arrange
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=[]
        )
        models = [
            "chatgpt-4",
            "gpt-5-mini",
            "gpt-5-nano",
            "o3-mini",
            "gpt-4o-latest"
        ]

        # Act
        result = model_manager.apply_filters(APIProvider.OPENAI, models)

        # Assert
        assert result == [
            "gpt-5-nano",
            "gpt-5-mini",
            "o3-mini",
            "chatgpt-4",
            "gpt-4o-latest"
        ]


class TestGetDefaultModels:
    """Tests for get_default_models method."""

    def test_get_default_models_from_config(self, model_manager, mock_config_service):
        """Test getting custom default models from config."""
        # Arrange
        custom_models = ["custom-model-1", "custom-model-2"]
        mock_config_service.get_setting.return_value = custom_models

        # Act
        result = model_manager.get_default_models()

        # Assert
        assert result == custom_models

    def test_get_default_models_builtin_fallback(self, model_manager, mock_config_service):
        """Test fallback to built-in models when config is None."""
        # Arrange
        mock_config_service.get_setting.return_value = None

        # Act
        result = model_manager.get_default_models()

        # Assert
        assert isinstance(result, list)
        assert len(result) > 0


class TestGetFallbackModels:
    """Tests for get_fallback_models method."""

    def test_get_fallback_models_openai(self, model_manager, mock_cache, mocker):
        """Test fallback models for OpenAI."""
        # Arrange
        mocker.patch.object(mock_cache, "cache_models_and_persist")

        # Act
        models, source = model_manager.get_fallback_models(APIProvider.OPENAI)

        # Assert
        assert isinstance(models, list)
        assert len(models) > 0
        assert source == ModelSource.FALLBACK.value
        mock_cache.cache_models_and_persist.assert_called_once()

    def test_get_fallback_models_google(self, model_manager, mock_cache, mocker):
        """Test fallback models for Google."""
        # Arrange
        mocker.patch.object(mock_cache, "cache_models_and_persist")

        # Act
        models, source = model_manager.get_fallback_models(APIProvider.GOOGLE)

        # Assert
        assert "gemini-2.5-flash" in models
        assert "gemini-1.5-flash" in models
        assert source == ModelSource.FALLBACK.value
        mock_cache.cache_models_and_persist.assert_called_once()

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
