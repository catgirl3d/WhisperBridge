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
            model="gpt-5.4-mini",
            messages=messages,
            temperature=0.7
        )

        assert response.choices[0].message.content == "Hello from OpenAI"
        assert mock_create.called
        # Verify params
        args, kwargs = mock_create.call_args
        assert kwargs["model"] == "gpt-5.4-mini"
        assert kwargs["messages"] == messages
        assert kwargs["temperature"] == 0.7

    @pytest.mark.parametrize("model", [
        "gpt-5.4",
        "gpt-5.6-luna",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
    ])
    def test_gpt5_reasoning_is_not_inferred_from_model_name(
        self, mocker, fake_openai_client, mock_completion_response, model
    ):
        """The adapter must not guess reasoning support from a model name."""
        messages = [{"role": "user", "content": "Hi"}]
        mock_create = mocker.patch.object(
            fake_openai_client._client.chat.completions, "create", return_value=mock_completion_response
        )

        fake_openai_client.chat.completions.create(
            model=model,
            messages=messages
        )

        assert mock_create.called
        kwargs = mock_create.call_args.kwargs
        assert "reasoning_effort" not in kwargs
        assert "verbosity" not in kwargs

    def test_explicit_gpt5_params_are_forwarded(self, mocker, fake_openai_client, mock_completion_response):
        """Test that caller-provided GPT-5 params are forwarded unchanged."""
        messages = [{"role": "user", "content": "Hi"}]
        mock_create = mocker.patch.object(
            fake_openai_client._client.chat.completions, "create", return_value=mock_completion_response
        )

        fake_openai_client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=messages,
            reasoning_effort="high",
            verbosity="medium",
        )

        kwargs = mock_create.call_args.kwargs
        assert kwargs["reasoning_effort"] == "high"
        assert kwargs["verbosity"] == "medium"

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
            model="gpt-5.4-mini",
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
            model="gpt-5.4-mini",
            messages=messages,
            temperature=0.0
        )
        kwargs = mock_create.call_args.kwargs
        assert kwargs["temperature"] == 0.0

        # Test with temperature=2.0 (maximum creativity)
        fake_openai_client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=messages,
            temperature=2.0
        )
        kwargs = mock_create.call_args.kwargs
        assert kwargs["temperature"] == 2.0

    def test_model_variations(self, mocker, fake_openai_client, mock_completion_response):
        """Test different model name handling."""
        models_to_test = ["gpt-5.4-mini", "gpt-5.6-luna", "gpt-5.7"]
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
                model="gpt-5.4-mini",
                messages=messages
            )


class TestOpenAIModels:
    """Tests for model listing and filtering."""

    def test_list_models(self, mocker, fake_openai_client):
        """Test that adapter-level model listing filters unsupported models."""
        mock_models = SimpleNamespace(data=[
            SimpleNamespace(id="gpt-5.4-mini"),
            SimpleNamespace(id="gpt-5.6-luna"),
            SimpleNamespace(id="whisper-1"),  # Should be excluded
            SimpleNamespace(id="dall-e-3"),   # Should be excluded
            SimpleNamespace(id="gpt-5.7"),
        ])
        mocker.patch.object(fake_openai_client._client.models, "list", return_value=mock_models)
        
        # We need to mock get_openai_model_excludes to avoid external dependency issues in tests
        mocker.patch("whisperbridge.providers.openai_adapter.get_openai_model_excludes", return_value=["whisper", "dall-e"])

        res = fake_openai_client.models.list()
        
        ids = [m.id for m in res.data]
        assert ids == ["gpt-5.4-mini", "gpt-5.6-luna", "gpt-5.7"]
        assert "gpt-5.4-mini" in ids
        assert "gpt-5.7" in ids
        assert "whisper-1" not in ids
        assert "dall-e-3" not in ids

    def test_list_models_includes_chatgpt_prefix_models(self, mocker, fake_openai_client):
        """Test that adapter-level model listing keeps chatgpt-* models."""
        mock_models = SimpleNamespace(data=[
            SimpleNamespace(id="chatgpt-5.6-latest"),
            SimpleNamespace(id="gpt-5.4-mini"),
            SimpleNamespace(id="omni-moderation-latest"),
        ])
        mocker.patch.object(fake_openai_client._client.models, "list", return_value=mock_models)
        mocker.patch("whisperbridge.providers.openai_adapter.get_openai_model_excludes", return_value=[])

        res = fake_openai_client.models.list()

        ids = [m.id for m in res.data]
        assert ids == ["chatgpt-5.6-latest", "gpt-5.4-mini"]

    def test_list_models_returns_empty_on_sdk_error(self, mocker, fake_openai_client):
        """Test that model listing returns an empty result on SDK errors."""
        mocker.patch.object(fake_openai_client._client.models, "list", side_effect=Exception("API Error"))

        res = fake_openai_client.models.list()

        assert res.data == []
