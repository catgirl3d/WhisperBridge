"""
Unit tests for OpenAIChatClientAdapter.
"""

import pytest
from types import SimpleNamespace
from whisperbridge.providers.openai_adapter import OpenAIChatClientAdapter


@pytest.fixture
def fake_openai_client(mocker):
    """Create a fake OpenAI adapter for testing."""
    # Mock the openai.OpenAI client
    mocker.patch("openai.OpenAI")
    adapter = OpenAIChatClientAdapter(api_key="sk-fake-key", timeout=30)
    return adapter


@pytest.fixture
def mock_completion_response(mocker):
    """Create a mock OpenAI completion response."""
    mock_res = mocker.Mock()
    mock_res.choices = [
        SimpleNamespace(message=SimpleNamespace(content="Hello from OpenAI"))
    ]
    mock_res.usage = SimpleNamespace(total_tokens=50)
    return mock_res


class TestOpenAITextRequests:
    """Tests for text-only chat completion requests."""

    def test_text_only_success(self, mocker, fake_openai_client, mock_completion_response):
        """Test regular chat completion."""
        messages = [{"role": "user", "content": "Hi"}]
        mock_create = mocker.patch.object(
            fake_openai_client._client.chat.completions, "create", return_value=mock_completion_response
        )

        response = fake_openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7
        )

        assert response.choices[0].message.content == "Hello from OpenAI"
        assert mock_create.called
        # Verify params
        args, kwargs = mock_create.call_args
        assert kwargs["model"] == "gpt-4"
        assert kwargs["messages"] == messages
        assert kwargs["temperature"] == 0.7

    def test_gpt5_optimizations(self, mocker, fake_openai_client, mock_completion_response):
        """Test that gpt-5 models get extra_body optimizations."""
        messages = [{"role": "user", "content": "Hi"}]
        mock_create = mocker.patch.object(
            fake_openai_client._client.chat.completions, "create", return_value=mock_completion_response
        )

        fake_openai_client.chat.completions.create(
            model="gpt-5-mini",
            messages=messages
        )

        assert mock_create.called
        kwargs = mock_create.call_args.kwargs
        assert "extra_body" in kwargs
        assert kwargs["extra_body"]["reasoning_effort"] == "minimal"

    def test_text_system_and_history(self, mocker, fake_openai_client, mock_completion_response):
        """Test complex message history handling."""
        messages = [
            {"role": "system", "content": "System instruction"},
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1"},
            {"role": "user", "content": "Question 2"}
        ]
        mock_create = mocker.patch.object(
            fake_openai_client._client.chat.completions, "create", return_value=mock_completion_response
        )

        fake_openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages
        )

        assert mock_create.called
        kwargs = mock_create.call_args.kwargs
        assert kwargs["messages"] == messages

    def test_temperature_extremes(self, mocker, fake_openai_client, mock_completion_response):
        """Test temperature edge cases (0.0 and 2.0)."""
        messages = [{"role": "user", "content": "Test"}]
        mock_create = mocker.patch.object(
            fake_openai_client._client.chat.completions, "create", return_value=mock_completion_response
        )

        # Test with temperature=0.0 (deterministic)
        fake_openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.0
        )
        kwargs = mock_create.call_args.kwargs
        assert kwargs["temperature"] == 0.0

        # Test with temperature=2.0 (maximum creativity)
        fake_openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=2.0
        )
        kwargs = mock_create.call_args.kwargs
        assert kwargs["temperature"] == 2.0

    def test_model_variations(self, mocker, fake_openai_client, mock_completion_response):
        """Test different model name handling."""
        models_to_test = ["gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
        messages = [{"role": "user", "content": "Hi"}]
        
        mock_create = mocker.patch.object(
            fake_openai_client._client.chat.completions, "create", return_value=mock_completion_response
        )

        for model_name in models_to_test:
            fake_openai_client.chat.completions.create(
                model=model_name,
                messages=messages
            )
            kwargs = mock_create.call_args.kwargs
            assert kwargs["model"] == model_name

    def test_error_handling(self, mocker, fake_openai_client):
        """Test that SDK errors are propagated correctly."""
        messages = [{"role": "user", "content": "Test"}]
        
        # Mock the SDK to raise an exception
        mock_create = mocker.patch.object(
            fake_openai_client._client.chat.completions,
            "create",
            side_effect=Exception("API Error: Rate limit exceeded")
        )

        with pytest.raises(Exception, match="API Error: Rate limit exceeded"):
            fake_openai_client.chat.completions.create(
                model="gpt-4",
                messages=messages
            )


class TestOpenAIVisionRequests:
    """Tests for vision-related features and the new defensive check."""

    def test_vision_success(self, mocker, fake_openai_client, mock_completion_response):
        """Test vision request with a valid image part."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is this?"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,xxx"}}
                ]
            }
        ]
        mock_create = mocker.patch.object(
            fake_openai_client._client.chat.completions, "create", return_value=mock_completion_response
        )

        response = fake_openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            is_vision=True
        )

        assert response.choices[0].message.content == "Hello from OpenAI"
        assert mock_create.called
        kwargs = mock_create.call_args.kwargs
        # Verify is_vision was NOT passed to SDK (it's popped)
        assert "is_vision" not in kwargs

    def test_vision_fails_without_image(self, fake_openai_client):
        """Test that vision request raises ValueError if no image is provided."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "I forgot to add an image"}
                ]
            }
        ]

        with pytest.raises(ValueError, match="Vision request requires at least one image part"):
            fake_openai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                is_vision=True
            )

    def test_vision_png_success(self, mocker, fake_openai_client, mock_completion_response):
        """Test vision request with PNG format."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw..."}}
                ]
            }
        ]
        mock_create = mocker.patch.object(
            fake_openai_client._client.chat.completions, "create", return_value=mock_completion_response
        )

        fake_openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            is_vision=True
        )

        assert mock_create.called
        kwargs = mock_create.call_args.kwargs
        assert kwargs["messages"] == messages

    def test_vision_multiple_images(self, mocker, fake_openai_client, mock_completion_response):
        """Test vision request with multiple images."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Compare these two"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,img1"}},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,img2"}}
                ]
            }
        ]
        mock_create = mocker.patch.object(
            fake_openai_client._client.chat.completions, "create", return_value=mock_completion_response
        )

        fake_openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            is_vision=True
        )

        assert mock_create.called
        # The defensive check should pass
        assert mock_create.call_count == 1

    def test_vision_dynamic_tokens(self, mocker, fake_openai_client, mock_completion_response):
        """Test that dynamic token calculation is used for vision."""
        messages = [
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "url"}}]}
        ]
        
        # Mock calculate_dynamic_completion_tokens to return a specific value
        mock_calc = mocker.patch(
            "whisperbridge.providers.openai_adapter.calculate_dynamic_completion_tokens",
            return_value=1234
        )
        
        mock_create = mocker.patch.object(
            fake_openai_client._client.chat.completions, "create", return_value=mock_completion_response
        )

        fake_openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            is_vision=True
        )

        assert mock_calc.called
        kwargs = mock_create.call_args.kwargs
        assert kwargs["max_completion_tokens"] == 1234

    def test_vision_malformed_parts(self, fake_openai_client):
        """Test the robust has_image check with malformed content parts."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"not_type": "strange"},
                    {"type": "not_image"},
                    None,
                    "just a string"
                ]
            }
        ]

        with pytest.raises(ValueError, match="Vision request requires at least one image part"):
            fake_openai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                is_vision=True
            )

    def test_vision_with_empty_content(self, fake_openai_client):
        """Test vision request with empty content list."""
        messages = [
            {"role": "user", "content": []}
        ]

        with pytest.raises(ValueError, match="Vision request requires at least one image part"):
            fake_openai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                is_vision=True
            )

    def test_vision_temperature_override(self, mocker, fake_openai_client, mock_completion_response):
        """Test that temperature can be overridden for vision requests."""
        messages = [
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "url"}}]}
        ]
        
        mock_create = mocker.patch.object(
            fake_openai_client._client.chat.completions, "create", return_value=mock_completion_response
        )

        # Vision requests default to temperature=0.0, but we can override
        fake_openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            is_vision=True,
            temperature=0.5
        )

        kwargs = mock_create.call_args.kwargs
        assert kwargs["temperature"] == 0.5


class TestOpenAIModels:
    """Tests for model listing and filtering."""

    def test_list_models(self, mocker, fake_openai_client):
        """Test that models are correctly filtered and sorted."""
        mock_models = SimpleNamespace(data=[
            SimpleNamespace(id="gpt-4"),
            SimpleNamespace(id="gpt-5-mini"),
            SimpleNamespace(id="whisper-1"),  # Should be excluded
            SimpleNamespace(id="dall-e-3"),   # Should be excluded
            SimpleNamespace(id="gpt-3.5-turbo"),
        ])
        mocker.patch.object(fake_openai_client._client.models, "list", return_value=mock_models)
        
        # We need to mock get_openai_model_excludes to avoid external dependency issues in tests
        mocker.patch("whisperbridge.providers.openai_adapter.get_openai_model_excludes", return_value=["whisper", "dall-e"])

        res = fake_openai_client.models.list()
        
        ids = [m.id for m in res.data]
        # Sort order: gpt-5, then gpt-4, then others
        assert ids[0] == "gpt-5-mini"
        assert "gpt-4" in ids
        assert "gpt-3.5-turbo" in ids
        assert "whisper-1" not in ids
        assert "dall-e-3" not in ids
