"""
Tests for APIManager class in api_manager.manager module.

This module tests API manager integration functionality including:
- Initialization and reinitialization
- Request handling with retry logic
- Translation requests
- Vision requests
- Response text extraction
- Usage statistics
- Rate limiting
- Temperature unsupported retry
- Shutdown
"""

from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time

from whisperbridge.core.api_manager.manager import APIManager
from whisperbridge.core.api_manager.providers import APIProvider
from whisperbridge.core.api_manager.types import APIUsage


# ============================================================================
# Initialized API Manager Fixtures (Specific to this file)
# ============================================================================

@pytest.fixture
def initialized_openai_manager(api_manager, config_openai, mock_openai_client):
    """API manager with initialized OpenAI provider and usage tracking."""
    api_manager.initialize()
    api_manager._usage[APIProvider.OPENAI] = APIUsage()
    return api_manager


@pytest.fixture
def initialized_google_manager(api_manager, config_google, mock_google_client):
    """API manager with initialized Google provider and usage tracking."""
    api_manager.initialize()
    api_manager._usage[APIProvider.GOOGLE] = APIUsage()
    return api_manager


@pytest.fixture
def initialized_deepl_manager(api_manager, config_deepl, mock_deepl_client):
    """API manager with initialized DeepL provider and usage tracking."""
    # mock_deepl_client.client ensures the patch is applied
    api_manager.initialize()
    api_manager._usage[APIProvider.DEEPL] = APIUsage()
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

        # Initialize and make some requests
        api_manager.initialize()
        api_manager._usage[APIProvider.OPENAI] = APIUsage(
            requests_count=5,
            successful_requests=3,
            failed_requests=2,
            tokens_used=1000,
        )

        # Act
        api_manager.reinitialize()

        # Assert
        assert api_manager.is_initialized() is True
        assert api_manager.has_clients() is True
        
        # Check if usage was cleared.
        if APIProvider.OPENAI in api_manager._usage:
            assert api_manager._usage[APIProvider.OPENAI].requests_count == 0


class TestMakeRequestSync:
    """Tests for make_request_sync method."""

    def test_make_request_sync_success(self, initialized_openai_manager):
        """Test successful API request."""
        # Act
        result = initialized_openai_manager.make_request_sync(
            APIProvider.OPENAI,
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
        )

        # Assert
        assert result is not None
        assert initialized_openai_manager._usage[APIProvider.OPENAI].successful_requests == 1

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
        # Mock usage to avoid TypeError in stats update
        mock_response.usage = mocker.Mock()
        mock_response.usage.total_tokens = 50

        mock_client = mocker.Mock()
        mock_client.chat.completions.create.side_effect = [error, error, mock_response]

        mocker.patch(
            "whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter",
            return_value=mock_client
        )

        api_manager.initialize()
        api_manager._usage[APIProvider.OPENAI] = APIUsage()

        # Act
        # Note: tenancy retry will wait, so this test might take a few seconds
        # BUT we can mock the wait to make it fast
        mocker.patch("tenacity.nap.time.sleep")
        
        result = api_manager.make_request_sync(
            APIProvider.OPENAI,
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
        )

        # Assert
        assert result is not None
        assert mock_client.chat.completions.create.call_count == 3
        assert api_manager._usage[APIProvider.OPENAI].rate_limit_hits == 2

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
        api_manager._usage[APIProvider.OPENAI] = APIUsage()

        # Act & Assert
        with pytest.raises(Exception, match="unauthorized"):
            api_manager.make_request_sync(
                APIProvider.OPENAI,
                model="gpt-4",
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
            model_hint="gpt-4",
        )

        # Assert
        assert response is not None
        assert model == "gpt-4"

    def test_make_translation_request_deepl(self, initialized_deepl_manager):
        """Test translation request through DeepL."""
        messages = [{"role": "user", "content": "Translate this"}]

        # Act
        response, model = initialized_deepl_manager.make_translation_request(
            messages=messages,
            target_lang="DE",
        )

        # Assert
        assert response is not None


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
            model_hint="gpt-4o",
        )

        # Assert
        assert response is not None
        assert model == "gpt-4o"

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
                model_hint="gpt-4o",
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


class TestUsageStats:
    """Tests for get_usage_stats method."""

    def test_get_usage_stats_single_provider(self, initialized_openai_manager):
        """Test getting usage stats for a single provider."""
        # Set up some usage data
        initialized_openai_manager._usage[APIProvider.OPENAI] = APIUsage(
            requests_count=10,
            successful_requests=8,
            failed_requests=2,
            tokens_used=5000,
            last_request_time=datetime.now(),
            rate_limit_hits=3,
        )

        # Act
        stats = initialized_openai_manager.get_usage_stats(APIProvider.OPENAI)

        # Assert
        assert stats["provider"] == "openai"
        assert stats["requests_count"] == 10
        assert stats["tokens_used"] == 5000
        assert stats["successful_requests"] == 8
        assert stats["failed_requests"] == 2
        assert stats["rate_limit_hits"] == 3
        assert stats["success_rate"] == 80.0

    def test_get_usage_stats_all_providers(self, api_manager, mock_config_service, mocker):
        """Test getting usage stats for all providers."""
        # Arrange
        mock_config_service.get_setting.side_effect = lambda key: {
            "openai_api_key": "sk-test123",
            "google_api_key": "AIzatest123",
            "api_provider": "openai",
            "api_timeout": 30,
        }.get(key)

        mocker.patch("whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter")
        mocker.patch("whisperbridge.core.api_manager.providers.GoogleChatClientAdapter")

        api_manager.initialize()

        # Set up usage data for multiple providers
        api_manager._usage[APIProvider.OPENAI] = APIUsage(
            requests_count=5,
            successful_requests=5,
            failed_requests=0,
            tokens_used=1000,
        )
        api_manager._usage[APIProvider.GOOGLE] = APIUsage(
            requests_count=3,
            successful_requests=2,
            failed_requests=1,
            tokens_used=500,
        )

        # Act
        stats = api_manager.get_usage_stats()

        # Assert
        assert "openai" in stats
        assert "google" in stats
        assert stats["openai"]["requests_count"] == 5
        assert stats["google"]["requests_count"] == 3


class TestRateLimiting:
    """Tests for is_rate_limited method."""

    def test_is_rate_limited_true(self, initialized_openai_manager):
        """Test detection of rate limit state."""
        # Simulate 6 rate limit hits
        initialized_openai_manager._usage[APIProvider.OPENAI] = APIUsage(
            requests_count=10,
            successful_requests=4,
            failed_requests=6,
            rate_limit_hits=6,
            last_request_time=datetime.now(),
        )

        # Act
        result = initialized_openai_manager.is_rate_limited(APIProvider.OPENAI)

        # Assert
        assert result is True

    def test_is_rate_limited_reset_after_timeout(self, initialized_openai_manager):
        """Test that rate limit counter resets after timeout."""
        # Simulate 6 rate limit hits 7 minutes ago
        old_time = datetime.now() - timedelta(minutes=7)
        initialized_openai_manager._usage[APIProvider.OPENAI] = APIUsage(
            requests_count=10,
            successful_requests=4,
            failed_requests=6,
            rate_limit_hits=6,
            last_request_time=old_time,
        )

        # Act
        result = initialized_openai_manager.is_rate_limited(APIProvider.OPENAI)

        # Assert
        assert result is False
        assert initialized_openai_manager._usage[APIProvider.OPENAI].rate_limit_hits == 0


class TestTemperatureUnsupportedRetry:
    """Tests for temperature unsupported retry logic."""

    def test_temperature_unsupported_retry(self, api_manager, config_openai, mocker):
        """Test retry without temperature on unsupported_value error."""
        # First call fails with unsupported_value, second succeeds
        error = Exception("unsupported_value: temperature not supported")
        mock_response = mocker.Mock()
        mock_response.choices = [mocker.Mock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.usage = mocker.Mock()
        mock_response.usage.total_tokens = 50

        mock_client = mocker.Mock()
        mock_client.chat.completions.create.side_effect = [error, mock_response]

        mocker.patch(
            "whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter",
            return_value=mock_client
        )

        api_manager.initialize()
        api_manager._usage[APIProvider.OPENAI] = APIUsage()

        # Act
        result = api_manager.make_request_sync(
            APIProvider.OPENAI,
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.5,
        )

        # Assert
        assert result is not None
        # First call with temperature, second without
        assert mock_client.chat.completions.create.call_count == 2


class TestShutdown:
    """Tests for shutdown method."""

    def test_shutdown_clears_all_state(self, initialized_openai_manager):
        """Test that shutdown clears all resources."""
        # Add some state
        initialized_openai_manager._usage[APIProvider.OPENAI] = APIUsage(requests_count=5)
        initialized_openai_manager._cache.set("openai", ["gpt-4"])

        # Act
        initialized_openai_manager.shutdown()

        # Assert
        assert initialized_openai_manager.is_initialized() is False
        assert initialized_openai_manager._usage == {}
        assert not initialized_openai_manager._cache.is_cached("openai")


class TestGetAvailableModelsSync:
    """Tests for get_available_models_sync method."""

    def test_get_available_models_sync(self, initialized_openai_manager, mock_openai_client, mocker):
        """Test getting available models through sync method."""
        # Setup models response
        mock_model = mocker.Mock()
        mock_model.id = "gpt-4"
        mock_models_response = mocker.Mock()
        mock_models_response.data = [mock_model]
        mock_openai_client.models.list.return_value = mock_models_response

        # Act
        models, source = initialized_openai_manager.get_available_models_sync(APIProvider.OPENAI)

        # Assert
        assert "gpt-4" in models
        # Source can be CACHE if it was cached before or API
        assert source in ("api", "cache")
