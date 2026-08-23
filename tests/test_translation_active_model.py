import pytest

from whisperbridge.services.translation_service import TranslationService, config_service


@pytest.mark.parametrize(
    ("provider", "setting_key", "model"),
    [
        ("openai", "openai_model", "gpt-5.4-mini"),
        ("google", "google_model", "gemini-2.5-flash"),
    ],
)
def test_get_active_model_uses_provider_model_setting(mocker, provider, setting_key, model):
    config = mocker.patch.object(config_service, "get_setting")
    config.side_effect = lambda key: {
        "api_provider": provider,
        setting_key: model,
    }.get(key)

    service = TranslationService.__new__(TranslationService)

    assert service._get_active_model() == model
    assert config.call_args_list == [
        mocker.call("api_provider"),
        mocker.call(setting_key),
    ]


def test_get_active_model_uses_configured_deepl_identifier(mocker):
    config = mocker.patch.object(config_service, "get_setting")
    config.side_effect = lambda key: {
        "api_provider": "deepl",
        "deepl_identifier": "deepl-fixed",
    }.get(key)
    service = TranslationService.__new__(TranslationService)

    assert service._get_active_model() == "deepl-fixed"


def test_get_active_model_treats_unknown_non_llm_provider_as_fixed_identifier(mocker):
    config = mocker.patch.object(config_service, "get_setting")
    config.side_effect = lambda key: {
        "api_provider": "unknown",
        "deepl_identifier": "fixed-sentinel",
    }.get(key)
    service = TranslationService.__new__(TranslationService)

    assert service._get_active_model() == "fixed-sentinel"
    assert config.call_args_list == [
        mocker.call("api_provider"),
        mocker.call("deepl_identifier"),
    ]
