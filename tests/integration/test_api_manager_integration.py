"""
Integration tests for APIManager.
"""

import threading
import pytest
from whisperbridge.core.api_manager.providers import APIProvider
from whisperbridge.core.api_manager.types import APIUsage

pytestmark = pytest.mark.integration

class TestAPIManagerIntegration:
    """Integration tests for APIManager workflows."""

    def test_full_translation_flow_openai(self, api_manager, config_openai, mock_openai_client):
        """Test full cycle: init -> request -> extraction."""
        # 1. Initialize
        api_manager.initialize()
        assert api_manager.is_initialized() is True

        # 2. Make request
        messages = [{"role": "user", "content": "Hello"}]
        response, model = api_manager.make_translation_request(
            messages=messages,
            model_hint="gpt-4o"
        )

        # 3. Extract text
        text = api_manager.extract_text_from_response(response)
        assert text == "Test response"
        assert model == "gpt-4o"

        call_args = mock_openai_client.chat.completions.create.call_args
        assert call_args is not None
        assert call_args.kwargs["model"] == "gpt-4o"
        assert call_args.kwargs["messages"] == messages
        assert call_args.kwargs["temperature"] == 0.8
        assert "max_completion_tokens" in call_args.kwargs

    def test_full_translation_flow_google(self, api_manager, config_google, mock_google_client):
        """Test full cycle for Google: init -> request -> extraction."""
        api_manager.initialize()
        assert api_manager.is_initialized() is True

        messages = [{"role": "user", "content": "Hello"}]
        response, model = api_manager.make_translation_request(
            messages=messages,
            model_hint="gemini-2.5-flash"
        )

        text = api_manager.extract_text_from_response(response)
        assert text == "Test response"
        assert model == "gemini-2.5-flash"

        call_args = mock_google_client.chat.completions.create.call_args
        assert call_args is not None
        assert call_args.kwargs["model"] == "gemini-2.5-flash"
        assert call_args.kwargs["messages"] == messages
        assert call_args.kwargs["temperature"] == 0.8
        assert "max_completion_tokens" in call_args.kwargs

    def test_full_translation_flow_deepl(self, api_manager, config_deepl, mock_deepl_client):
        """Test full cycle for DeepL with plan and params validation."""
        api_manager.initialize()
        assert api_manager.is_initialized() is True

        messages = [{"role": "user", "content": "Hello"}]
        response, model = api_manager.make_translation_request(
            messages=messages,
            model_hint="deepl-translate",
            target_lang="DE"
        )

        text = api_manager.extract_text_from_response(response)
        assert text == "Translated text"
        assert model == "deepl-translate"

        mock_deepl_client.patch.assert_called_once()
        deepl_kwargs = mock_deepl_client.patch.call_args.kwargs
        assert deepl_kwargs["api_key"] == "deepl-test-key"
        assert deepl_kwargs["timeout"] == 30
        assert deepl_kwargs["plan"] == "pro"

        create_kwargs = mock_deepl_client.client.chat.completions.create.call_args.kwargs
        assert create_kwargs["model"] == "deepl-translate"
        assert create_kwargs["messages"] == messages
        assert create_kwargs["target_lang"] == "DE"

    def test_provider_switching_via_reinitialize(self, api_manager, mock_config_service, mocker):
        """Test switching providers using reinitialize."""
        # 1. Setup OpenAI
        mock_config_service.get_setting.side_effect = lambda key: {
            "openai_api_key": "sk-test",
            "api_provider": "openai",
            "api_timeout": 30,
        }.get(key)
        
        mocker.patch("whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter")
        api_manager.initialize()
        assert api_manager.has_clients() is True
        assert api_manager._providers.is_provider_available(APIProvider.OPENAI) is True
        assert api_manager._providers.is_provider_available(APIProvider.GOOGLE) is False
        
        # 2. Switch to Google
        mock_config_service.get_setting.side_effect = lambda key: {
            "google_api_key": "AIzatest",
            "api_provider": "google",
            "api_timeout": 30,
        }.get(key)
        
        mocker.patch("whisperbridge.core.api_manager.providers.GoogleChatClientAdapter")
        api_manager.reinitialize()
        
        # 3. Verify Google is active
        assert api_manager.has_clients() is True
        assert api_manager._providers.is_provider_available(APIProvider.GOOGLE) is True
        assert api_manager._providers.is_provider_available(APIProvider.OPENAI) is False

    def test_model_caching_across_sessions(self, mock_config_service, tmp_path, mocker):
        """Test that model cache persists between manager instances."""
        from whisperbridge.core.api_manager.manager import APIManager
        mocker.patch("whisperbridge.core.api_manager.manager.ensure_config_dir", return_value=tmp_path)
        mocker.patch("whisperbridge.core.api_manager.providers.validate_api_key_format", return_value=True)

        # 1. Session 1: Fetch and cache
        mock_config_service.get_setting.return_value = "sk-test"
        mock_client = mocker.Mock()
        mock_model = mocker.Mock(id="gpt-4o")
        mock_client.models.list.return_value = mocker.Mock(data=[mock_model])
        mocker.patch("whisperbridge.core.api_manager.providers.OpenAIChatClientAdapter", return_value=mock_client)

        manager1 = APIManager(mock_config_service)
        manager1.initialize()
        models, source = manager1.get_available_models_sync(APIProvider.OPENAI)
        assert source == "api"
        assert "gpt-4o" in models
        manager1.shutdown()

        # 2. Session 2: Load from cache
        # Mock client to fail to ensure it uses cache
        mock_client.models.list.side_effect = Exception("API Down")
        manager2 = APIManager(mock_config_service)
        manager2.initialize()
        models2, source2 = manager2.get_available_models_sync(APIProvider.OPENAI)
        
        assert "gpt-4o" in models2
        assert source2 == "cache"

    def test_concurrent_translation_requests(self, api_manager, config_openai, mock_openai_client):
        """Test handling multiple concurrent requests."""
        api_manager.initialize()
        api_manager._usage[APIProvider.OPENAI] = APIUsage()
        
        results = []
        errors = []
        def make_call():
            try:
                resp, _ = api_manager.make_translation_request(
                    messages=[{"role": "user", "content": "Hi"}],
                    model_hint="gpt-4o"
                )
                results.append(resp)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=make_call) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert len(errors) == 0, f"Concurrent errors: {errors}"
        assert len(results) == 5
        assert mock_openai_client.chat.completions.create.call_count == 5
        stats = api_manager.get_usage_stats(APIProvider.OPENAI)
        assert stats["requests_count"] == 5
