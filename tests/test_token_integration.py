"""Integration-style tests for token management across API manager paths."""
import pytest

from whisperbridge.core.api_manager import APIManager, APIProvider
from whisperbridge.services.config_service import ConfigService


@pytest.fixture
def mock_config_service(mocker):
    """Create a mock config service."""
    config = mocker.Mock(spec=ConfigService)
    config.get_setting = mocker.Mock(return_value=None)
    return config


@pytest.fixture
def api_manager(mock_config_service, mocker):
    """Create an API manager instance for testing."""
    manager = APIManager(mock_config_service)
    manager._is_initialized = True  # Skip initialization for tests
    return manager


class TestAPIManagerTokenIntegration:
    """API manager token integration tests."""

    def test_api_manager_vision_uses_hard_output_limit(self, api_manager, mock_config_service, mocker):
        """
        Test that APIManager.make_vision_request passes the hard token limit.

        This verifies that the vision request path builds LLM params and forwards
        max_completion_tokens to the provider request.
        """
        # Setup mock client
        mock_client = mocker.Mock()
        
        # Mock the chat.completions.create method
        mock_response = mocker.Mock()
        mock_response.choices = [mocker.Mock(message=mocker.Mock(content="Test response"))]
        mock_response.usage = mocker.Mock(total_tokens=100)
        mock_client.chat.completions.create.return_value = mock_response
        
        # Configure the manager
        api_manager._providers._clients[APIProvider.OPENAI] = mock_client
        mock_config_service.get_setting.side_effect = lambda key: {
            "api_provider": "openai",
            "api_timeout": 30,
        }.get(key)
        
        # Create a vision request with a text prompt
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,test"}}
                ]
            }
        ]
        
        # Call vision request
        response, model = api_manager.make_vision_request(messages, "gpt-5.6-luna")
        
        # Verify adapter was called
        assert mock_client.chat.completions.create.called
        
        call_args = mock_client.chat.completions.create.call_args
        assert call_args is not None
        assert 'temperature' not in call_args.kwargs
        assert call_args.kwargs.get('max_completion_tokens') == 128000

class TestTranslationRequestTokenIntegration:
    """Additional integration tests for translation requests."""

    def test_translation_request_uses_hard_output_limit(self, api_manager, mock_config_service, mocker):
        """Test that translation requests use the hard output limit."""
        # Setup mock client
        mock_client = mocker.Mock()
        
        # Mock the chat.completions.create method
        mock_response = mocker.Mock()
        mock_response.choices = [mocker.Mock(message=mocker.Mock(content="Translated text"))]
        mock_response.usage = mocker.Mock(total_tokens=100)
        mock_client.chat.completions.create.return_value = mock_response
        
        # Configure the manager
        api_manager._providers._clients[APIProvider.OPENAI] = mock_client
        mock_config_service.get_setting.side_effect = lambda key: {
            "api_provider": "openai",
            "api_timeout": 30,
        }.get(key)
        
        # Create a translation request
        messages = [
            {"role": "system", "content": "You are a translator"},
            {"role": "user", "content": "Translate to English: Привет мир"}
        ]
        
        # Call translation request
        response, model = api_manager.make_translation_request(messages, "gpt-5.4-mini")
        
        # Verify adapter was called with max_completion_tokens
        assert mock_client.chat.completions.create.called
        call_args = mock_client.chat.completions.create.call_args

        assert 'temperature' not in call_args.kwargs
        assert call_args.kwargs.get('max_completion_tokens') == 128000

    def test_translation_request_omits_unconfigured_reasoning_effort(
        self, api_manager, mock_config_service, mocker
    ):
        """An unconfigured reasoning effort is omitted from the provider request."""
        mock_client = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.usage = mocker.Mock(total_tokens=100)
        mock_client.chat.completions.create.return_value = mock_response
        api_manager._providers._clients[APIProvider.OPENAI] = mock_client
        mock_config_service.get_setting.side_effect = lambda key: {
            "api_provider": "openai",
            "openai_reasoning_effort": "not_set",
        }.get(key)

        api_manager.make_translation_request(
            messages=[{"role": "user", "content": "Translate this"}],
            model_hint="gpt-5.4-mini",
        )

        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "reasoning_effort" not in kwargs

    def test_translation_request_forwards_configured_reasoning_effort(
        self, api_manager, mock_config_service, mocker
    ):
        """A configured reasoning effort reaches the provider request unchanged."""
        mock_client = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.usage = mocker.Mock(total_tokens=100)
        mock_client.chat.completions.create.return_value = mock_response
        api_manager._providers._clients[APIProvider.OPENAI] = mock_client
        mock_config_service.get_setting.side_effect = lambda key: {
            "api_provider": "openai",
            "openai_reasoning_effort": "high",
        }.get(key)

        api_manager.make_translation_request(
            messages=[{"role": "user", "content": "Translate this"}],
            model_hint="gpt-5.4-mini",
        )

        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["reasoning_effort"] == "high"

    def test_translation_request_with_large_text_uses_model_output_cap(self, api_manager, mock_config_service, mocker):
        """Test that a large translation request still uses the model-based output cap."""
        # Setup mock client
        mock_client = mocker.Mock()
        
        # Mock the chat.completions.create method
        mock_response = mocker.Mock()
        mock_response.choices = [mocker.Mock(message=mocker.Mock(content="Translation result"))]
        mock_response.usage = mocker.Mock(total_tokens=100)
        mock_client.chat.completions.create.return_value = mock_response
        
        # Configure the manager
        api_manager._providers._clients[APIProvider.OPENAI] = mock_client
        mock_config_service.get_setting.side_effect = lambda key: {
            "api_provider": "openai",
            "api_timeout": 30,
        }.get(key)
        
        # Create a large Cyrillic text
        large_cyrillic = "Переведи это: " * 5000  # ~50K chars
        
        messages = [
            {"role": "user", "content": large_cyrillic}
        ]
        
        # Call translation request
        response, model = api_manager.make_translation_request(messages, "gpt-5.4-mini")
        
        # Verify max_completion_tokens is within model limits
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs.get('max_completion_tokens') == 128000


class TestAPIManagerHelperMethods:
    """Targeted tests for APIManager helper methods."""

    def test_resolve_provider_uses_config_and_client(self, api_manager, mock_config_service, mocker):
        """Test that provider resolution uses configured provider when a client exists."""
        api_manager._providers._clients[APIProvider.OPENAI] = mocker.Mock()
        mock_config_service.get_setting.side_effect = lambda key: {
            "api_provider": "openai",
        }.get(key)

        assert api_manager._resolve_provider() == APIProvider.OPENAI

    def test_resolve_provider_raises_on_invalid_provider(self, api_manager, mock_config_service):
        """Test that provider resolution fails for an unknown provider value."""
        mock_config_service.get_setting.side_effect = lambda key: {
            "api_provider": "not-a-provider",
        }.get(key)

        with pytest.raises(RuntimeError):
            api_manager._resolve_provider()

    def test_resolve_provider_raises_when_client_missing(self, api_manager, mock_config_service):
        """Test that provider resolution fails when provider is configured but client is missing."""
        # Ensure client is missing
        api_manager._providers.clear()
        mock_config_service.get_setting.side_effect = lambda key: {
            "api_provider": "openai",
        }.get(key)

        with pytest.raises(RuntimeError):
            api_manager._resolve_provider()

    def test_resolve_model_deepl_fallback(self, api_manager, mocker):
        """Test that DeepL model resolution falls back to the configured pseudo-model."""
        sentinel = "deepl-test-sentinel"
        get_deepl_identifier = mocker.patch(
            "whisperbridge.core.api_manager.manager.get_deepl_identifier",
            return_value=sentinel,
        )

        model = api_manager._resolve_model(None, APIProvider.DEEPL, missing_message="missing")

        assert model == sentinel
        get_deepl_identifier.assert_called_once_with()

    def test_resolve_model_llm_missing_raises(self, api_manager):
        """Test that LLM model resolution raises when model selection is empty."""
        with pytest.raises(ValueError):
            api_manager._resolve_model("", APIProvider.OPENAI, missing_message="missing")
