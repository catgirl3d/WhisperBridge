"""
Tests for ProviderRegistry class in api_manager.providers module.

This module tests provider management functionality including:
- Provider initialization with valid/invalid keys
- Client retrieval
- Provider clearing
- DeepL plan parameter handling
- Simultaneous provider initialization
"""

import pytest

from whisperbridge.core.api_manager.providers import APIProvider, ProviderRegistry


class TestProviderInitialization:
    """Tests for provider initialization."""

    def test_initialize_with_valid_openai_key(self, mock_config_service, mocker):
        """Test successful initialization of OpenAI provider with valid key."""
        # Arrange
        mock_config_service.get_setting.side_effect = lambda key: {
            "openai_api_key": "sk-test123",
            "api_timeout": 30,
        }.get(key)

        # Mock validate_api_key_format to return True
        mocker.patch(
            "whisperbridge.core.api_manager.providers.validate_api_key_format",
            return_value=True
        )

        mock_client = mocker.Mock()
        mocker.patch(
            "whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter",
            return_value=mock_client
        )

        # Act
        registry = ProviderRegistry(mock_config_service)
        registry.initialize_all()

        # Assert
        assert registry.is_provider_available(APIProvider.OPENAI) is True
        assert registry.get_client(APIProvider.OPENAI) == mock_client

    def test_initialize_with_invalid_key_format(self, mock_config_service, mocker, loguru_caplog):
        """Test graceful degradation when API key format is invalid."""
        # Arrange
        mock_config_service.get_setting.side_effect = lambda key: {
            "openai_api_key": "invalid-key-no-sk-prefix",
            "api_timeout": 30,
        }.get(key)

        # Mock validate_api_key_format to return False
        mocker.patch(
            "whisperbridge.core.api_manager.providers.validate_api_key_format",
            return_value=False
        )

        # Act
        registry = ProviderRegistry(mock_config_service)
        registry.initialize_all()

        # Assert
        assert registry.is_provider_available(APIProvider.OPENAI) is False
        assert any("Invalid OpenAI API key format" in record.message for record in loguru_caplog.records)

    def test_initialize_without_api_keys(self, mock_config_service, mocker):
        """Test behavior when no API keys are configured."""
        # Arrange - config returns None for all keys
        mock_config_service.get_setting.return_value = None

        # Act
        registry = ProviderRegistry(mock_config_service)
        registry.initialize_all()

        # Assert
        assert registry.has_any_clients() is False
        assert registry.is_provider_available(APIProvider.OPENAI) is False
        assert registry.is_provider_available(APIProvider.GOOGLE) is False
        assert registry.is_provider_available(APIProvider.DEEPL) is False


class TestClientRetrieval:
    """Tests for client retrieval."""

    def test_get_client_for_initialized_provider(self, mock_config_service, mocker):
        """Test getting client for an initialized provider."""
        # Arrange
        mock_config_service.get_setting.side_effect = lambda key: {
            "openai_api_key": "sk-test123",
            "api_timeout": 30,
        }.get(key)

        # Mock validate_api_key_format to return True
        mocker.patch(
            "whisperbridge.core.api_manager.providers.validate_api_key_format",
            return_value=True
        )

        mock_client = mocker.Mock()
        mocker.patch(
            "whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter",
            return_value=mock_client
        )

        registry = ProviderRegistry(mock_config_service)
        registry.initialize_all()

        # Act
        client = registry.get_client(APIProvider.OPENAI)

        # Assert
        assert client is not None
        assert client == mock_client

    def test_get_client_for_uninitialized_provider(self, mock_config_service):
        """Test getting client returns None for uninitialized provider."""
        # Arrange
        mock_config_service.get_setting.return_value = None
        registry = ProviderRegistry(mock_config_service)
        registry.initialize_all()

        # Act
        client = registry.get_client(APIProvider.GOOGLE)

        # Assert
        assert client is None


class TestProviderClearing:
    """Tests for provider clearing operations."""

    def test_clear_all_providers(self, mock_config_service, mocker):
        """Test clearing all registered providers."""
        # Arrange
        mock_config_service.get_setting.side_effect = lambda key: {
            "openai_api_key": "sk-test123",
            "google_api_key": "AIzatest123",
            "api_timeout": 30,
        }.get(key)

        # Mock validate_api_key_format to return True
        mocker.patch(
            "whisperbridge.core.api_manager.providers.validate_api_key_format",
            return_value=True
        )

        mock_openai_client = mocker.Mock()
        mock_google_client = mocker.Mock()
        mocker.patch(
            "whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter",
            return_value=mock_openai_client
        )
        mocker.patch(
            "whisperbridge.core.api_manager.providers.GoogleChatClientAdapter",
            return_value=mock_google_client
        )

        registry = ProviderRegistry(mock_config_service)
        registry.initialize_all()
        assert registry.has_any_clients() is True

        # Act
        registry.clear()

        # Assert
        assert registry.has_any_clients() is False
        assert registry.get_client(APIProvider.OPENAI) is None
        assert registry.get_client(APIProvider.GOOGLE) is None


class TestDeepLPlanParameter:
    """Tests for DeepL plan parameter handling."""

    def test_deepl_plan_parameter(self, mock_config_service, mocker):
        """Test that DeepL plan parameter is passed correctly."""
        # Arrange
        mock_config_service.get_setting.side_effect = lambda key: {
            "deepl_api_key": "deepl-test-key",
            "deepl_plan": "pro",
            "api_timeout": 30,
        }.get(key)

        # Mock validate_api_key_format to return True
        mocker.patch(
            "whisperbridge.core.api_manager.providers.validate_api_key_format",
            return_value=True
        )

        mock_deepl_client = mocker.Mock()
        deepl_init_mock = mocker.patch(
            "whisperbridge.core.api_manager.providers.DeepLClientAdapter",
            return_value=mock_deepl_client
        )

        # Act
        registry = ProviderRegistry(mock_config_service)
        registry.initialize_all()

        # Assert
        assert registry.is_provider_available(APIProvider.DEEPL) is True
        deepl_init_mock.assert_called_once()
        call_kwargs = deepl_init_mock.call_args.kwargs
        assert call_kwargs.get("plan") == "pro"


class TestSimultaneousInitialization:
    """Tests for simultaneous provider initialization."""

    def test_initialize_all_providers_simultaneously(self, mock_config_service, mocker):
        """Test that all providers can be initialized together."""
        # Arrange
        mock_config_service.get_setting.side_effect = lambda key: {
            "openai_api_key": "sk-test123",
            "google_api_key": "AIzatest123",
            "deepl_api_key": "deepl-test-key",
            "deepl_plan": "free",
            "api_timeout": 30,
        }.get(key)

        # Mock validate_api_key_format to return True
        mocker.patch(
            "whisperbridge.core.api_manager.providers.validate_api_key_format",
            return_value=True
        )

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
        registry = ProviderRegistry(mock_config_service)
        registry.initialize_all()

        # Assert
        assert registry.is_provider_available(APIProvider.OPENAI) is True
        assert registry.is_provider_available(APIProvider.GOOGLE) is True
        assert registry.is_provider_available(APIProvider.DEEPL) is True
        assert registry.has_any_clients() is True


class TestGetAllProviders:
    """Tests for getting all providers."""

    def test_get_all_providers(self, mock_config_service, mocker):
        """Test getting all registered providers."""
        # Arrange
        mock_config_service.get_setting.side_effect = lambda key: {
            "openai_api_key": "sk-test123",
            "google_api_key": "AIzatest123",
            "api_timeout": 30,
        }.get(key)

        # Mock validate_api_key_format to return True
        mocker.patch(
            "whisperbridge.core.api_manager.providers.validate_api_key_format",
            return_value=True
        )

        mock_openai_client = mocker.Mock()
        mock_google_client = mocker.Mock()
        mocker.patch(
            "whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter",
            return_value=mock_openai_client
        )
        mocker.patch(
            "whisperbridge.core.api_manager.providers.GoogleChatClientAdapter",
            return_value=mock_google_client
        )

        registry = ProviderRegistry(mock_config_service)
        registry.initialize_all()

        # Act
        all_providers = registry.get_all_providers()

        # Assert
        assert APIProvider.OPENAI in all_providers
        assert APIProvider.GOOGLE in all_providers
        assert all_providers[APIProvider.OPENAI] == mock_openai_client
        assert all_providers[APIProvider.GOOGLE] == mock_google_client
