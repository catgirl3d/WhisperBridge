"""
Tests for APIManager class in api_manager.manager module.

This module tests API manager integration functionality including:
- Initialization and reinitialization
- Request handling with retry logic
- Translation requests
- Vision requests
- Response text extraction
- Shutdown
"""

import pytest

from whisperbridge.core.api_manager.manager import APIManager
from whisperbridge.core.api_manager.providers import APIProvider


# ============================================================================
# Initialized API Manager Fixtures (Specific to this file)
# ============================================================================

@pytest.fixture
def initialized_openai_manager(api_manager, config_openai, mock_openai_client):
    """API manager with an initialized OpenAI provider."""
    api_manager.initialize()
    return api_manager


@pytest.fixture
def initialized_google_manager(api_manager, config_google, mock_google_client):
    """API manager with an initialized Google provider."""
    api_manager.initialize()
    return api_manager


@pytest.fixture
def initialized_deepl_manager(api_manager, config_deepl, mock_deepl_client):
    """API manager with an initialized DeepL provider."""
    # mock_deepl_client.client ensures the patch is applied
    api_manager.initialize()
    return api_manager


class TestInitialization:
    """Tests for API manager initialization."""

    def test_initialization_success_with_valid_keys(self, api_manager, mock_config_service, mocker):
        """Test successful initialization with valid API keys."""
        # Arrange
        mock_config_service.get_setting.side_effect = lambda key: {
            "openai_api_key": "sk-test123",
            "google_api_key": "AIzatest123",
            "deepl_api_key": "deepl-test-key",
            "deepl_plan": "free",
            "api_provider": "openai",
            "api_timeout": 30,
        }.get(key)

        mock_openai_client = mocker.Mock()
        mock_google_client = mocker.Mock()
        mock_deepl_client = mocker.Mock()

        mocker.patch(
            "whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter",
            return_value=mock_openai_client
        )
        mocker.patch(
            "whisperbridge.core.api_manager.providers.GoogleChatClientAdapter",
            return_value=mock_google_client
        )
        mocker.patch(
            "whisperbridge.core.api_manager.providers.DeepLClientAdapter",
            return_value=mock_deepl_client
        )

        # Act
        result = api_manager.initialize()

        # Assert
        assert result is True
        assert api_manager.is_initialized() is True
        assert api_manager.has_clients() is True

    def test_initialization_without_keys_partial_mode(self, api_manager, mock_config_service):
        """Test initialization without API keys (partial mode)."""
        # Arrange
        mock_config_service.get_setting.return_value = None

        # Act
        result = api_manager.initialize()

        # Assert
        assert result is True  # Initialization succeeds even without keys
        assert api_manager.is_initialized() is True
        assert api_manager.has_clients() is False

    def test_reinitialize_clears_state(self, api_manager, mock_config_service, mocker):
        """Test that reinitialize clears all state."""
        # Arrange
        mock_config_service.get_setting.side_effect = lambda key: {
            "openai_api_key": "sk-test123",
            "api_provider": "openai",
            "api_timeout": 30,
        }.get(key)

        mock_openai_client = mocker.Mock()
        mocker.patch(
            "whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter",
            return_value=mock_openai_client
        )

        # Initialize with valid provider state
        api_manager.initialize()

        # Act
        api_manager.reinitialize()

        # Assert
        assert api_manager.is_initialized() is True
        assert api_manager.has_clients() is True
        
    def test_reinitialize_removes_persistent_model_cache(
        self, api_manager, mock_config_service, mocker, tmp_path
    ):
        """Reinitialization must not reload models from the previous session."""
        mock_config_service.get_setting.side_effect = lambda key: {
            "openai_api_key": "sk-test123",
            "api_provider": "openai",
            "api_timeout": 30,
        }.get(key)
        mocker.patch(
            "whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter",
            return_value=mocker.Mock(),
        )

        api_manager._cache.cache_models_and_persist("openai", ["stale-model"])
        cache_file = tmp_path / "models_cache.json"
        assert cache_file.exists()

        api_manager.reinitialize()

        assert not cache_file.exists()
        assert api_manager._cache.get("openai") is None


class TestMakeRequestSync:
    """Tests for make_request_sync method."""

    def test_make_request_sync_success(self, initialized_openai_manager):
        """Test successful API request."""
        # Act
        result = initialized_openai_manager.make_request_sync(
            APIProvider.OPENAI,
            model="gpt-5.4-mini",
            messages=[{"role": "user", "content": "Hello"}],
        )

        # Assert
        assert result is not None

    def test_make_request_sync_rejects_temperature_before_client_call(self, initialized_openai_manager):
        client = initialized_openai_manager._providers.get_client(APIProvider.OPENAI)

        with pytest.raises(TypeError, match="temperature is not a supported"):
            initialized_openai_manager.make_request_sync(
                APIProvider.OPENAI,
                model="gpt-5.4-mini",
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.5,
            )

        client.chat.completions.create.assert_not_called()

    def test_make_request_sync_retry_on_rate_limit(self, api_manager, mock_config_service, mocker):
        """Test retry logic on rate limit error."""
        # Arrange
        mock_config_service.get_setting.side_effect = lambda key: {
            "openai_api_key": "sk-test123",
            "api_provider": "openai",
            "api_timeout": 30,
        }.get(key)

        # First two calls fail, third succeeds
        error = Exception("rate limit exceeded")
        mock_response = mocker.Mock()
        mock_response.choices = [mocker.Mock()]
        mock_response.choices[0].message.content = "Test response"
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.side_effect = [error, error, mock_response]

        mocker.patch(
            "whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter",
            return_value=mock_client
        )

        api_manager.initialize()

        # Act
        # Note: tenancy retry will wait, so this test might take a few seconds
        # BUT we can mock the wait to make it fast
        mocker.patch("tenacity.nap.time.sleep")
        
        result = api_manager.make_request_sync(
            APIProvider.OPENAI,
            model="gpt-5.4-mini",
            messages=[{"role": "user", "content": "Hello"}],
        )

        # Assert
        assert result is not None
        assert mock_client.chat.completions.create.call_count == 3

    def test_make_request_sync_no_retry_on_auth_error(self, api_manager, mock_config_service, mocker):
        """Test that auth errors are not retried."""
        # Arrange
        mock_config_service.get_setting.side_effect = lambda key: {
            "openai_api_key": "sk-test123",
            "api_provider": "openai",
            "api_timeout": 30,
        }.get(key)

        error = Exception("unauthorized: invalid api key")
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.side_effect = error

        mocker.patch(
            "whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter",
            return_value=mock_client
        )

        api_manager.initialize()

        # Act & Assert
        with pytest.raises(Exception, match="unauthorized"):
            api_manager.make_request_sync(
                APIProvider.OPENAI,
                model="gpt-5.4-mini",
                messages=[{"role": "user", "content": "Hello"}],
            )

        # Should only be called once (no retry for auth errors)
        assert mock_client.chat.completions.create.call_count == 1


class TestTranslationRequests:
    """Tests for make_translation_request method."""

    def test_make_translation_request_openai(self, initialized_openai_manager):
        """Test translation request through OpenAI."""
        messages = [{"role": "user", "content": "Translate this"}]

        # Act
        response, model = initialized_openai_manager.make_translation_request(
            messages=messages,
            model_hint="gpt-5.4-mini",
        )

        # Assert
        assert response is not None
        assert model == "gpt-5.4-mini"

    def test_make_translation_request_passes_configured_reasoning_effort(
        self, initialized_openai_manager, mock_openai_client
    ):
        """Configured OpenAI reasoning effort is sent without model-name inference."""
        initialized_openai_manager.config_service.get_setting.side_effect = lambda key: {
            "api_provider": "openai",
            "openai_reasoning_effort": "none",
        }.get(key)

        initialized_openai_manager.make_translation_request(
            messages=[{"role": "user", "content": "Translate this"}],
            model_hint="gpt-5.6-luna",
        )

        kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
        assert kwargs["reasoning_effort"] == "none"

    def test_make_translation_request_not_set_does_not_send_reasoning_effort(
        self, initialized_openai_manager, mock_openai_client
    ):
        """not_set leaves reasoning selection to the selected model."""
        initialized_openai_manager.config_service.get_setting.side_effect = lambda key: {
            "api_provider": "openai",
            "openai_reasoning_effort": "not_set",
        }.get(key)

        initialized_openai_manager.make_translation_request(
            messages=[{"role": "user", "content": "Translate this"}],
            model_hint="gpt-5.6-luna",
        )

        kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
        assert "reasoning_effort" not in kwargs

    def test_make_translation_request_deepl(self, initialized_deepl_manager, mock_deepl_client):
        """Test translation request through DeepL."""
        messages = [{"role": "user", "content": "Translate this"}]

        # Act
        response, model = initialized_deepl_manager.make_translation_request(
            messages=messages,
            model_hint="test-deepl-model",
            target_lang="DE",
            source_lang=None,
        )

        # Assert
        assert response is mock_deepl_client.client.chat.completions.create.return_value
        assert model == "test-deepl-model"
        mock_deepl_client.client.chat.completions.create.assert_called_once_with(
            model="test-deepl-model",
            messages=messages,
            target_lang="DE",
        )
class TestVisionRequests:
    """Tests for make_vision_request method."""

    def test_make_vision_request_openai(self, initialized_openai_manager):
        """Test vision request through OpenAI."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
                ],
            }
        ]

        # Act
        response, model = initialized_openai_manager.make_vision_request(
            messages=messages,
            model_hint="gpt-5.4-mini",
        )

        # Assert
        assert response is not None
        assert model == "gpt-5.4-mini"

    def test_make_vision_request_google(self, initialized_google_manager):
        """Test vision request through Google."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
                ],
            }
        ]

        # Act
        response, model = initialized_google_manager.make_vision_request(
            messages=messages,
            model_hint="gemini-2.5-flash",
        )

        # Assert
        assert response is not None
        assert model == "gemini-2.5-flash"

    def test_make_vision_request_validation_no_image(self, initialized_openai_manager):
        """Test that vision request requires an image part."""
        messages = [{"role": "user", "content": [{"type": "text", "text": "No image here"}]}]

        # Act & Assert
        with pytest.raises(ValueError, match="Vision request requires an image part"):
            initialized_openai_manager.make_vision_request(
                messages=messages,
                model_hint="gpt-5.4-mini",
            )

    def test_make_vision_request_unsupported_provider(self, initialized_deepl_manager):
        """Test that vision request fails for DeepL provider."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
                ],
            }
        ]

        # Act & Assert
        with pytest.raises(ValueError, match="does not support vision requests"):
            initialized_deepl_manager.make_vision_request(
                messages=messages,
                model_hint="deepl-translate",
            )


class TestExtractTextFromResponse:
    """Tests for extract_text_from_response method."""

    def test_extract_text_from_openai_response(self, api_manager, mocker):
        """Test extracting text from OpenAI object-based response."""
        # Arrange
        mock_message = mocker.Mock()
        mock_message.content = "Hello"
        mock_choice = mocker.Mock()
        mock_choice.message = mock_message
        mock_response = mocker.Mock()
        mock_response.choices = [mock_choice]

        # Act
        result = api_manager.extract_text_from_response(mock_response)

        # Assert
        assert result == "Hello"

    def test_extract_text_from_google_dict_response(self, api_manager, mocker):
        """Test extracting text from Google dict-based response."""
        # Arrange
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "Hi"
                    }
                }
            ]
        }

        # Act
        result = api_manager.extract_text_from_response(mock_response)

        # Assert
        assert result == "Hi"

    def test_extract_text_from_invalid_response(self, api_manager, loguru_caplog, mocker):
        """Test graceful handling of invalid response."""
        # Arrange
        invalid_responses = [None, "string", {}, {"choices": []}]

        for invalid_response in invalid_responses:
            # Act
            result = api_manager.extract_text_from_response(invalid_response)

            # Assert
            assert result == ""

        # Check that warning was logged (at least once)
        assert any(
            "Failed to extract text from response" in record.message
            for record in loguru_caplog.records
        )


class TestShutdown:
    """Tests for shutdown method."""

    def test_shutdown_clears_all_state(self, initialized_openai_manager):
        """Test that shutdown clears all resources."""
        # Add some state
        initialized_openai_manager._cache.set("openai", ["gpt-5.4-mini"])

        # Act
        initialized_openai_manager.shutdown()

        # Assert
        assert initialized_openai_manager.is_initialized() is False
        assert not initialized_openai_manager._cache.is_cached("openai")


class TestGetAvailableModelsSync:
    """Tests for get_available_models_sync method."""

    def test_get_available_models_sync(self, initialized_openai_manager, mock_openai_client, mocker):
        """Test getting available models through sync method."""
        # Setup models response
        mock_model = mocker.Mock()
        mock_model.id = "gpt-5.7"
        mock_models_response = mocker.Mock()
        mock_models_response.data = [mock_model]
        mock_openai_client.models.list.return_value = mock_models_response

        # Act
        models, source = initialized_openai_manager.get_available_models_sync(APIProvider.OPENAI)

        # Assert
        assert "gpt-5.7" in models
        # Source can be CACHE if it was cached before or API
        assert source in ("api", "cache")
