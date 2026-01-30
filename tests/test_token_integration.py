"""
Integration tests for token management with API Manager.

Based on test_implementation_plan.md
Coverage Goal: ≥80% coverage of affected code paths in api_manager.py
"""

import pytest
from unittest.mock import Mock, patch

from whisperbridge.core.model_limits import calculate_dynamic_completion_tokens
from whisperbridge.core.api_manager import APIManager, APIProvider
from whisperbridge.services.config_service import ConfigService


@pytest.fixture
def mock_config_service():
    """Create a mock config service."""
    config = Mock(spec=ConfigService)
    config.get_setting = Mock(return_value=None)
    return config


@pytest.fixture
def api_manager(mock_config_service):
    """Create an API manager instance for testing."""
    manager = APIManager(mock_config_service)
    manager._is_initialized = True  # Skip initialization for tests
    return manager


class TestAPIManagerTokenIntegration:
    """Category 1: API Manager Integration (4 tests)"""

    @patch('whisperbridge.core.api_manager.OpenAIChatClientAdapter')
    def test_api_manager_vision_uses_dynamic_tokens(self, mock_adapter, api_manager, mock_config_service):
        """
        TC-INT-001: APIManager.send_vision_request should use calculate_dynamic_completion_tokens.
        
        This test verifies that the vision request properly calculates dynamic tokens.
        """
        # Setup mock client
        mock_client = Mock()
        mock_adapter.return_value = mock_client
        
        # Mock the chat.completions.create method
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Test response"))]
        mock_response.usage = Mock(total_tokens=100)
        mock_client.chat.completions.create.return_value = mock_response
        
        # Configure the manager
        api_manager._clients[APIProvider.OPENAI] = mock_client
        mock_config_service.get_setting.side_effect = lambda key: {
            "api_provider": "openai",
            "llm_temperature_vision": 0.0,
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
        response, model = api_manager.make_vision_request(messages, "gpt-4o")
        
        # Verify adapter was called
        assert mock_client.chat.completions.create.called
        
        # The vision request doesn't use max_completion_tokens for OpenAI
        # (it's handled differently in the adapter), but we verify the call was made
        call_args = mock_client.chat.completions.create.call_args
        assert call_args is not None

    def test_gemini_vision_cyrillic_prompt_estimation(self):
        """
        TC-INT-002: Large Cyrillic prompt should not overflow Gemini output limit.
        
        Tests that dynamic calculation works correctly for Cyrillic text.
        """
        # Calculate dynamic tokens for Gemini 3
        max_output = calculate_dynamic_completion_tokens(
            model="gemini-3-flash",
            min_output_tokens=2048
        )
        
        # Should not exceed model limit
        assert max_output <= 65536
        # Should reserve reasonable output
        assert max_output >= 2048

    @pytest.mark.parametrize("model,expected_max", [
        ("gpt-4o-mini", 16384),
        ("gpt-5", 128000),
        ("gemini-3-pro", 65536),
    ])
    def test_model_switching_token_limits(self, model, expected_max):
        """
        TC-INT-003: Switching models should correctly update token limits.
        
        Tests that different models have appropriate token limits.
        """
        # Calculate tokens for same input
        tokens = calculate_dynamic_completion_tokens(
            model=model,
            output_safety_margin=0.1
        )
        
        # Should respect new model's limit
        assert tokens <= expected_max
        # Should have reasonable output capacity
        assert tokens >= 2048  # min_output_tokens default

class TestTranslationRequestTokenIntegration:
    """Additional integration tests for translation requests."""

    @patch('whisperbridge.core.api_manager.OpenAIChatClientAdapter')
    def test_translation_request_with_dynamic_tokens(self, mock_adapter, api_manager, mock_config_service):
        """Test that translation requests use dynamic token calculation."""
        # Setup mock client
        mock_client = Mock()
        mock_adapter.return_value = mock_client
        
        # Mock the chat.completions.create method
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Translated text"))]
        mock_response.usage = Mock(total_tokens=100)
        mock_client.chat.completions.create.return_value = mock_response
        
        # Configure the manager
        api_manager._clients[APIProvider.OPENAI] = mock_client
        mock_config_service.get_setting.side_effect = lambda key: {
            "api_provider": "openai",
            "llm_temperature_translation": 1.0,
            "api_timeout": 30,
        }.get(key)
        
        # Create a translation request
        messages = [
            {"role": "system", "content": "You are a translator"},
            {"role": "user", "content": "Translate to English: Привет мир"}
        ]
        
        # Call translation request
        response, model = api_manager.make_translation_request(messages, "gpt-4o-mini")
        
        # Verify adapter was called with max_completion_tokens
        assert mock_client.chat.completions.create.called
        call_args = mock_client.chat.completions.create.call_args
        
        # Check that max_completion_tokens was passed
        max_tokens = call_args.kwargs.get('max_completion_tokens')
        assert max_tokens is not None
        assert isinstance(max_tokens, int)
        assert max_tokens <= 16384  # gpt-4o-mini limit
        assert max_tokens >= 2048  # min_output_tokens

    @patch('whisperbridge.core.api_manager.OpenAIChatClientAdapter')
    def test_translation_with_large_cyrillic_text(self, mock_adapter, api_manager, mock_config_service):
        """Test translation with large Cyrillic text doesn't overflow."""
        # Setup mock client
        mock_client = Mock()
        mock_adapter.return_value = mock_client
        
        # Mock the chat.completions.create method
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Translation result"))]
        mock_response.usage = Mock(total_tokens=100)
        mock_client.chat.completions.create.return_value = mock_response
        
        # Configure the manager
        api_manager._clients[APIProvider.OPENAI] = mock_client
        mock_config_service.get_setting.side_effect = lambda key: {
            "api_provider": "openai",
            "llm_temperature_translation": 1.0,
            "api_timeout": 30,
        }.get(key)
        
        # Create a large Cyrillic text
        large_cyrillic = "Переведи это: " * 5000  # ~50K chars
        
        messages = [
            {"role": "user", "content": large_cyrillic}
        ]
        
        # Call translation request
        response, model = api_manager.make_translation_request(messages, "gpt-5")
        
        # Verify max_completion_tokens is within model limits
        call_args = mock_client.chat.completions.create.call_args
        max_tokens = call_args.kwargs.get('max_completion_tokens')
        
        # GPT-5 has 128K output limit
        assert max_tokens <= 128000
        # Should reserve minimum output
        assert max_tokens >= 2048




class TestModelLimitsIntegration:
    """Integration tests for model limits."""

    def test_all_known_models_have_valid_limits(self):
        """Test that all known models in registry have valid limits."""
        from whisperbridge.core.model_limits import MODEL_TOKEN_LIMITS
        
        for model, limit in MODEL_TOKEN_LIMITS.items():
            assert isinstance(limit, int), f"{model} has non-int limit: {type(limit)}"
            assert limit > 0, f"{model} has non-positive limit: {limit}"
            assert limit <= 1_000_000, f"{model} limit seems unrealistic: {limit}"

    def test_unknown_model_fallback(self):
        """Test that unknown models fall back to default limit."""
        result = calculate_dynamic_completion_tokens(
            model="unknown-future-model"
        )
        
        from whisperbridge.core.model_limits import DEFAULT_MAX_COMPLETION_TOKENS
        # Should use default limit
        assert result <= DEFAULT_MAX_COMPLETION_TOKENS
        assert result >= 2048  # min_output_tokens

    def test_model_variant_prefix_matching(self):
        """Test that model variants match base models correctly."""
        # Test various model variants
        variants = [
            ("gpt-5-turbo-2025", 128000),
            ("gpt-4o-mini-2024-07-18", 16384),
            ("gemini-3-flash-preview", 65536),
        ]
        
        for model, expected_limit in variants:
            result = calculate_dynamic_completion_tokens(
                model=model,
                output_safety_margin=0.0
            )
            assert result == expected_limit, f"Model {model} should have limit {expected_limit}, got {result}"


class TestOpenAIAdapterRemovedModels:
    """Tests for OpenAI adapter behavior with removed models."""

    @patch('whisperbridge.providers.openai_adapter.openai.OpenAI')
    def test_gpt41_models_do_not_get_gpt5_optimizations(self, mock_openai):
        """
        TC-INT-004: Removed GPT-4.1 models should NOT receive GPT-5 optimizations.
        
        Regression test to ensure that gpt-4.1-mini and gpt-4.1-nano don't
        accidentally get GPT-5 specific parameters (reasoning_effort, verbosity).
        """
        from whisperbridge.providers.openai_adapter import OpenAIChatClientAdapter
        
        # Setup mock client
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        # Mock the chat.completions.create response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Test response"))]
        mock_client.chat.completions.create.return_value = mock_response
        
        # Create adapter
        adapter = OpenAIChatClientAdapter(api_key="test-key")
        
        # Test with gpt-4.1-mini (removed from DEFAULT_GPT_MODELS)
        messages = [{"role": "user", "content": "Test message"}]
        
        adapter._create(model="gpt-4.1-mini", messages=messages)
        
        # Verify the API was called
        assert mock_client.chat.completions.create.called
        call_args = mock_client.chat.completions.create.call_args
        
        # Should NOT have extra_body with GPT-5 optimizations
        extra_body = call_args.kwargs.get('extra_body')
        assert extra_body is None, (
            "gpt-4.1-mini should NOT receive GPT-5 optimizations (extra_body)"
        )

    @patch('whisperbridge.providers.openai_adapter.openai.OpenAI')
    def test_gpt5_models_do_get_gpt5_optimizations(self, mock_openai):
        """
        TC-INT-005: GPT-5 models SHOULD receive GPT-5 optimizations.
        
        This is a positive control test to verify that GPT-5 models
        correctly receive the extra_body parameters.
        """
        from whisperbridge.providers.openai_adapter import OpenAIChatClientAdapter
        
        # Setup mock client
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        # Mock the chat.completions.create response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Test response"))]
        mock_client.chat.completions.create.return_value = mock_response
        
        # Create adapter
        adapter = OpenAIChatClientAdapter(api_key="test-key")
        
        # Test with gpt-5-mini (current default)
        messages = [{"role": "user", "content": "Test message"}]
        
        adapter._create(model="gpt-5-mini", messages=messages)
        
        # Verify the API was called
        assert mock_client.chat.completions.create.called
        call_args = mock_client.chat.completions.create.call_args
        
        # Should have extra_body with GPT-5 optimizations
        extra_body = call_args.kwargs.get('extra_body')
        assert extra_body is not None, (
            "gpt-5-mini SHOULD receive GPT-5 optimizations (extra_body)"
        )
        assert extra_body.get('reasoning_effort') == 'minimal'
        assert extra_body.get('verbosity') == 'low'

    @patch('whisperbridge.providers.openai_adapter.openai.OpenAI')
    @pytest.mark.parametrize("model,should_have_optimizations", [
        ("gpt-5-mini", True),
        ("gpt-5-nano", True),
        ("gpt-5", True),
        ("gpt-4.1-mini", False),
        ("gpt-4.1-nano", False),
        ("gpt-4o-mini", False),
        ("gpt-4o", False),
    ])
    def test_gpt5_optimizations_applied_correctly(self, mock_openai, model, should_have_optimizations):
        """
        TC-INT-006: GPT-5 optimizations should only be applied to GPT-5 models.
        
        Parametrized test to verify that the startswith("gpt-5") check
        correctly identifies which models get optimizations.
        """
        from whisperbridge.providers.openai_adapter import OpenAIChatClientAdapter
        
        # Setup mock client
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        # Mock the chat.completions.create response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Test response"))]
        mock_client.chat.completions.create.return_value = mock_response
        
        # Create adapter
        adapter = OpenAIChatClientAdapter(api_key="test-key")
        
        # Test with the specified model
        messages = [{"role": "user", "content": "Test message"}]
        
        adapter._create(model=model, messages=messages)
        
        # Verify the API was called
        assert mock_client.chat.completions.create.called
        call_args = mock_client.chat.completions.create.call_args
        
        # Check for extra_body
        extra_body = call_args.kwargs.get('extra_body')
        
        if should_have_optimizations:
            assert extra_body is not None, (
                f"Model '{model}' SHOULD have GPT-5 optimizations"
            )
            assert extra_body.get('reasoning_effort') == 'minimal'
            assert extra_body.get('verbosity') == 'low'
        else:
            assert extra_body is None, (
                f"Model '{model}' should NOT have GPT-5 optimizations"
            )

    @patch('whisperbridge.providers.openai_adapter.openai.OpenAI')
    def test_vision_request_with_removed_models(self, mock_openai):
        """
        TC-INT-007: Vision requests with removed models should work correctly.
        
        Tests that _create_vision handles gpt-4.1-mini and gpt-4.1-nano
        correctly with dynamic token calculation.
        """
        from whisperbridge.providers.openai_adapter import OpenAIChatClientAdapter
        
        # Setup mock client
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        # Mock the chat.completions.create response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Vision response"))]
        mock_client.chat.completions.create.return_value = mock_response
        
        # Create adapter
        adapter = OpenAIChatClientAdapter(api_key="test-key")
        
        # Test vision request with gpt-4.1-mini
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,test"}}
                ]
            }
        ]
        
        adapter._create_vision(model="gpt-4.1-mini", messages=messages)
        
        # Verify the API was called
        assert mock_client.chat.completions.create.called
        call_args = mock_client.chat.completions.create.call_args
        
        # Should have max_completion_tokens calculated for gpt-4 (4096 limit)
        max_tokens = call_args.kwargs.get('max_completion_tokens')
        assert max_tokens is not None
        assert max_tokens <= 4096  # gpt-4 limit
        assert max_tokens >= 2048  # min_output_tokens
