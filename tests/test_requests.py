"""Tests for API request parameter builders."""

from whisperbridge.core.api_manager.requests import RequestBuilder


class TestRequestBuilderLLMParams:
    def test_build_llm_params_uses_model_token_limit_without_temperature(self, mocker):
        builder = RequestBuilder(mocker.Mock())
        messages = [{"role": "user", "content": "Hello"}]

        params = builder.build_llm_params(model="gemini-3-flash", messages=messages)

        assert params == {
            "model": "gemini-3-flash",
            "messages": messages,
            "max_completion_tokens": 65536,
        }


class TestRequestBuilderDeepLParams:
    def test_build_deepl_params(self, mocker):
        builder = RequestBuilder(mocker.Mock())
        messages = [{"role": "user", "content": "Translate this"}]

        params = builder.build_deepl_params(
            model="deepl",
            messages=messages,
            api_kwargs={"target_lang": "DE", "source_lang": "EN"},
        )

        assert params == {
            "model": "deepl",
            "messages": messages,
            "target_lang": "DE",
            "source_lang": "EN",
        }

    def test_build_deepl_params_without_api_kwargs(self, mocker):
        builder = RequestBuilder(mocker.Mock())
        messages = [{"role": "user", "content": "Translate this"}]

        params = builder.build_deepl_params(
            model="deepl",
            messages=messages,
            api_kwargs=None,
        )

        assert params == {"model": "deepl", "messages": messages}
