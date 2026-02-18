"""
Pytest configuration for WhisperBridge test suite.

This file provides common fixtures for all tests.
Note: Python path is configured via pyproject.toml's pythonpath setting.
"""

import logging
from pathlib import Path

import pytest
from loguru import logger


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for Qt tests."""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app
    except ImportError:
        # Qt not available - skip fixture
        pytest.skip("PySide6 not available")


@pytest.fixture
def loguru_caplog(caplog):
    """Fixture to bridge loguru to pytest caplog with proper cleanup."""
    # Remove all handlers to avoid duplicate logs or side effects
    logger.remove()
    
    # Add caplog handler
    handler_id = logger.add(caplog.handler, format="{message}")
    caplog.set_level(logging.DEBUG)
    
    yield caplog
    
    # Cleanup: remove caplog handler
    try:
        logger.remove(handler_id)
    except ValueError:
        # Handler already removed
        pass


# ============================================================================
# Shared API Manager & Config Fixtures
# ============================================================================

@pytest.fixture
def mock_config_service(mocker):
    """Create a mock config service for testing."""
    config = mocker.Mock()
    config.get_setting = mocker.Mock(return_value=None)
    return config


@pytest.fixture
def api_manager(mock_config_service, tmp_path, mocker):
    """Create an APIManager instance for testing."""
    from whisperbridge.core.api_manager.manager import APIManager
    mocker.patch("whisperbridge.core.api_manager.manager.ensure_config_dir", return_value=tmp_path)
    # Also patch validate_api_key_format to return True for our test keys
    mocker.patch("whisperbridge.core.api_manager.providers.validate_api_key_format", return_value=True)
    return APIManager(mock_config_service)


@pytest.fixture
def mock_openai_response(mocker):
    """Create a standard OpenAI API response mock."""
    mock_response = mocker.Mock()
    mock_response.choices = [mocker.Mock()]
    mock_response.choices[0].message.content = "Test response"
    mock_response.usage = mocker.Mock(total_tokens=50)
    return mock_response


@pytest.fixture
def mock_deepl_response(mocker):
    """Create a standard DeepL API response mock."""
    mock_response = mocker.Mock()
    mock_response.choices = [mocker.Mock()]
    mock_response.choices[0].message.content = "Translated text"
    mock_response.usage = mocker.Mock(total_tokens=0)  # DeepL doesn't track tokens
    return mock_response


@pytest.fixture
def mock_openai_client(mocker, mock_openai_response):
    """Mock OpenAI client with standard response."""
    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = mock_openai_response
    
    mocker.patch(
        "whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter",
        return_value=mock_client
    )
    return mock_client


@pytest.fixture
def mock_google_client(mocker, mock_openai_response):
    """Mock Google client with standard response."""
    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = mock_openai_response
    
    mocker.patch(
        "whisperbridge.core.api_manager.providers.GoogleChatClientAdapter",
        return_value=mock_client
    )
    return mock_client


@pytest.fixture
def mock_deepl_client(mocker, mock_deepl_response):
    """Mock DeepL client with standard response.
    
    Returns an object with:
        - client: The mock client
        - patch: The patch object for verifying initialization parameters
    """
    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = mock_deepl_response
    
    deepl_patch = mocker.patch(
        "whisperbridge.core.api_manager.providers.DeepLClientAdapter",
        return_value=mock_client
    )
    
    class MockDeepLClient:
        def __init__(self, client, patch):
            self.client = client
            self.patch = patch
    
    return MockDeepLClient(mock_client, deepl_patch)


# ============================================================================
# Provider Configuration Fixtures
# ============================================================================

@pytest.fixture
def config_openai(mock_config_service):
    """Configure mock config service for OpenAI provider."""
    mock_config_service.get_setting.side_effect = lambda key: {
        "openai_api_key": "sk-test123",
        "api_provider": "openai",
        "api_timeout": 30,
        "llm_temperature_translation": 0.8,
        "llm_temperature_vision": 0.0,
    }.get(key)
    return mock_config_service


@pytest.fixture
def config_google(mock_config_service):
    """Configure mock config service for Google provider."""
    mock_config_service.get_setting.side_effect = lambda key: {
        "google_api_key": "AIzatest123",
        "api_provider": "google",
        "api_timeout": 30,
        "llm_temperature_translation": 0.8,
        "llm_temperature_vision": 0.0,
    }.get(key)
    return mock_config_service


@pytest.fixture
def config_deepl(mock_config_service):
    """Configure mock config service for DeepL provider."""
    mock_config_service.get_setting.side_effect = lambda key: {
        "deepl_api_key": "deepl-test-key",
        "deepl_plan": "pro",
        "api_provider": "deepl",
        "api_timeout": 30,
    }.get(key)
    return mock_config_service
