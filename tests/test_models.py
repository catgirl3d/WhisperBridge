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

from whisperbridge.core.api_manager.models import ModelManager
from whisperbridge.core.provider_catalog import APIProvider
from whisperbridge.core.api_manager.types import ModelSource


@pytest.fixture
def mock_provider_registry(mocker):
    """Create a mock ProviderRegistry for testing."""
    registry = mocker.Mock()
    # Default behavior: provider is available
    registry.is_provider_available = mocker.Mock(return_value=True)
    registry.get_client = mocker.Mock(return_value=None)
    return registry


@pytest.fixture
def model_manager(mock_provider_registry):
    """Create a ModelManager instance for testing."""
    return ModelManager(mock_provider_registry)


class TestModelMemoryCache:
    """Unit tests for the in-memory model cache inside ModelManager."""

    def test_missing_provider_returns_none(self, model_manager):
        assert model_manager.get_cached_models("google") is None

    def test_clear_specific_provider_only(self, model_manager):
        model_manager._models_cache["openai"] = ["gpt-5.4-mini"]
        model_manager._models_cache["google"] = ["gemini-2.0-flash"]

        model_manager.clear_cached_models("openai")

        assert model_manager.get_cached_models("openai") is None
        assert model_manager.get_cached_models("google") == ["gemini-2.0-flash"]

    def test_clear_all_providers(self, model_manager):
        model_manager._models_cache["openai"] = ["gpt-5.4-mini"]
        model_manager._models_cache["google"] = ["gemini-2.0-flash"]

        model_manager.clear_cached_models()

        assert model_manager.get_cached_models("openai") is None
        assert model_manager.get_cached_models("google") is None


class TestGetAvailableModels:
    """Tests for get_available_models method."""

    def test_get_available_models_from_cache(self, model_manager, mock_provider_registry, mocker):
        """Cached OpenAI models are re-filtered by exclusions and policy."""
        models = ["gpt-5.3", "whisper-1", "omni-moderation-latest", "gpt-5.4-mini"]
        mock_provider_registry.is_provider_available.return_value = True
        model_manager._models_cache["openai"] = models
        mocker.patch(
            "whisperbridge.core.api_manager.models.get_openai_model_excludes",
            return_value=["whisper"],
        )

        result_models, source = model_manager.get_available_models(APIProvider.OPENAI)

        assert result_models == ["gpt-5.4-mini"]
        assert source == ModelSource.CACHE.value

    def test_get_available_models_refreshes_fully_filtered_cache(
        self, model_manager, mock_provider_registry, mocker
    ):
        """A cache invalidated by current filters must fall through to the API."""
        model_manager._models_cache["openai"] = ["gpt-5.3"]
        mock_provider_registry.is_provider_available.return_value = True
        mock_client = mocker.Mock()
        mock_client.models.list.return_value.data = [mocker.Mock(id="gpt-5.4-mini")]
        mock_provider_registry.get_client.return_value = mock_client

        result_models, source = model_manager.get_available_models(APIProvider.OPENAI)

        assert result_models == ["gpt-5.4-mini"]
        assert source == ModelSource.API.value
        mock_client.models.list.assert_called_once_with()
        assert model_manager.get_cached_models("openai") == ["gpt-5.4-mini"]

    def test_get_available_models_from_api(self, model_manager, mock_provider_registry, mocker):
        """OpenAI API results retain only current models and cache those results."""
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
        assert model_manager.get_cached_models("openai") == ["gpt-5.6-luna", "gpt-5.4-mini"]

    def test_get_available_models_hides_latest_aliases_and_keeps_supported_chatgpt_models(
        self, model_manager, mock_provider_registry, mocker
    ):
        """The picker retains supported named ChatGPT models but excludes latest aliases."""
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
        assert model_manager.get_cached_models("openai") == ["chatgpt-5.6", "gpt-5.4-mini"]

    def test_get_available_models_with_temp_key(self, model_manager, mock_provider_registry, mocker):
        """Temporary OpenAI fetch applies the current-model policy."""
        mock_client = mocker.Mock()
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
        assert model_manager.get_cached_models("openai") is None

    def test_get_available_models_with_temp_key_applies_openai_filters_and_ranking(
        self, model_manager, mock_provider_registry, mocker
    ):
        """Temporary OpenAI fetch uses exclusion, policy, and ranking rules."""
        mock_client = mocker.Mock()
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
        assert model_manager.get_cached_models("openai") is None



    def test_get_available_models_unconfigured_provider(self, model_manager, mock_provider_registry, mocker):
        """Test unconfigured providers ignore cache and return UNCONFIGURED."""
        # Arrange
        mock_provider_registry.is_provider_available.return_value = False
        model_manager._models_cache[APIProvider.GOOGLE.value] = ["stale-model"]

        # Act
        result_models, source = model_manager.get_available_models(APIProvider.GOOGLE)

        # Assert
        assert result_models == []
        assert source == ModelSource.UNCONFIGURED.value


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


class TestCacheInvalidation:
    """Tests for cache invalidation on API errors."""

    def test_cache_invalidation_on_api_error(self, model_manager, mock_provider_registry, mocker):
        """Test that cache is cleared on API error."""
        # Arrange
        model_manager._models_cache["openai"] = ["previous-model"]

        mock_client = mocker.Mock()
        mock_client.models.list.side_effect = Exception("API Error")
        mock_provider_registry.is_provider_available.return_value = True
        mock_provider_registry.get_client.return_value = mock_client

        # Act
        result_models, source = model_manager.get_available_models(APIProvider.OPENAI)

        # Assert
        assert result_models == []
        assert source == ModelSource.ERROR.value
        assert model_manager.get_cached_models("openai") is None


class TestCredentialChangeGuard:
    """Tests for ignoring model results that belong to outdated credentials."""

    def test_cache_models_if_client_matches_writes_when_client_is_current(self, model_manager, mock_provider_registry, mocker):
        client = mocker.Mock()
        mock_provider_registry.get_client.return_value = client

        cached = model_manager.cache_models_if_client_matches("openai", ["gpt-5.4-mini"], client)

        assert cached is True
        assert model_manager.get_cached_models("openai") == ["gpt-5.4-mini"]

    def test_cache_models_if_client_matches_skips_when_credentials_changed(self, model_manager, mock_provider_registry, mocker):
        model_manager._models_cache["google"] = ["gemini-2.0-flash"]
        mock_provider_registry.get_client.return_value = mocker.Mock()

        cached = model_manager.cache_models_if_client_matches(
            "openai", ["stale-model"], mocker.Mock()
        )

        assert cached is False
        assert model_manager.get_cached_models("openai") is None
        assert model_manager.get_cached_models("google") == ["gemini-2.0-flash"]

    def test_clear_models_if_client_matches_clears_when_client_is_current(self, model_manager, mock_provider_registry, mocker):
        model_manager._models_cache["openai"] = ["gpt-5.4-mini"]
        client = mock_provider_registry.get_client.return_value

        cleared = model_manager.clear_models_if_client_matches("openai", client)

        assert cleared is True
        assert model_manager.get_cached_models("openai") is None

    def test_clear_models_if_client_matches_keeps_cache_when_credentials_changed(self, model_manager, mock_provider_registry, mocker):
        model_manager._models_cache["openai"] = ["fresh-model"]
        mock_provider_registry.get_client.return_value = mocker.Mock()

        cleared = model_manager.clear_models_if_client_matches("openai", mocker.Mock())

        assert cleared is False
        assert model_manager.get_cached_models("openai") == ["fresh-model"]

    def test_result_from_old_client_is_not_cached_after_rebind(
        self, model_manager, mock_provider_registry, mocker
    ):
        """A fetch racing a reinitialize must not poison the reset cache."""
        mock_client = mocker.Mock()
        response = mocker.Mock()
        response.data = [mocker.Mock(id="gpt-5.4-mini")]

        def fetch_models():
            mock_provider_registry.get_client.return_value = mocker.Mock()
            return response

        mock_client.models.list.side_effect = fetch_models
        mock_provider_registry.get_client.return_value = mock_client

        result_models, source = model_manager.get_available_models(APIProvider.OPENAI)

        assert result_models == ["gpt-5.4-mini"]
        assert source == ModelSource.API.value
        assert model_manager.get_cached_models("openai") is None

    def test_error_path_does_not_wipe_current_cache_after_rebind(
        self, model_manager, mock_provider_registry, mocker
    ):
        """A stale failing fetch must not clear a fresh entry from new credentials."""
        model_manager._models_cache["openai"] = ["fresh-model"]
        mock_client = mocker.Mock()

        def fetch_models():
            mock_provider_registry.get_client.return_value = mocker.Mock()
            raise Exception("stale request failed")

        mock_client.models.list.side_effect = fetch_models
        mock_provider_registry.get_client.return_value = mock_client

        result_models, source = model_manager.get_available_models(APIProvider.OPENAI)

        assert result_models == []
        assert source == ModelSource.ERROR.value
        assert model_manager.get_cached_models("openai") == ["fresh-model"]

    def test_temp_key_failure_keeps_cached_list(self, model_manager, mock_provider_registry, mocker):
        """A failed temp-key check is a credential probe and must not clear cache."""
        model_manager._models_cache["openai"] = ["gpt-5.4-mini"]
        mock_client = mocker.Mock()
        mock_client.models.list.side_effect = Exception("bad temp key")
        mocker.patch(
            "whisperbridge.core.api_manager.models.OpenAIChatClientAdapter",
            return_value=mock_client,
        )

        result_models, source = model_manager.get_available_models(
            APIProvider.OPENAI,
            temp_api_key="sk-temp123",
        )

        assert result_models == []
        assert source == ModelSource.ERROR.value
        assert model_manager.get_cached_models("openai") == ["gpt-5.4-mini"]
