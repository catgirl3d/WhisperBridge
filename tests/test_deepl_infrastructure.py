"""External integration tests for the DeepL provider pipeline."""

import pytest

from whisperbridge.core.api_manager import APIManager, APIProvider
from whisperbridge.providers.deepl_adapter import DeepLClientAdapter
from whisperbridge.services.config_service import ConfigService

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def require_deepl_credential():
    """Prevent every integration test from making unauthenticated requests."""
    if not ConfigService().get_setting("deepl_api_key"):
        pytest.skip("DeepL API key not configured")


def _configured_adapter():
    config = ConfigService()
    return DeepLClientAdapter(
        api_key=config.get_setting("deepl_api_key"),
        timeout=30,
        plan=config.get_setting("deepl_plan") or "free",
    )


def test_deepl_adapter_direct():
    response = _configured_adapter().chat.completions.create(
        model="deepl-translate",
        messages=[{"role": "user", "content": "Hello, world!"}],
        target_lang="RU",
        source_lang="EN",
    )

    assert response.choices[0].message.content


def test_api_manager_deepl():
    config = ConfigService()
    original_provider = config.get_setting("api_provider")
    config.set_setting("api_provider", "deepl")

    try:
        api_manager = APIManager(config)
        assert api_manager.initialize()
        assert api_manager._providers.is_provider_available(APIProvider.DEEPL)

        response, model = api_manager.make_translation_request(
            messages=[{"role": "user", "content": "Good morning!"}],
            model_hint="deepl-translate",
            target_lang="RU",
            source_lang="EN",
        )

        assert model == "deepl-translate"
        assert api_manager.extract_text_from_response(response)
    finally:
        config.set_setting("api_provider", original_provider)


def test_language_auto_detection():
    response = _configured_adapter().chat.completions.create(
        model="deepl-translate",
        messages=[{"role": "user", "content": "Привет, мир!"}],
        target_lang="EN",
    )

    assert response.choices[0].message.content


def test_multiple_messages():
    response = _configured_adapter().chat.completions.create(
        model="deepl-translate",
        messages=[
            {"role": "system", "content": "This should be ignored by DeepL"},
            {"role": "user", "content": "Hello!"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "This should also be ignored"},
            {"role": "user", "content": "Have a nice day!"},
        ],
        target_lang="RU",
        source_lang="EN",
    )

    assert response.choices[0].message.content
