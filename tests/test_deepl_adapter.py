"""Hermetic unit tests for the DeepL client adapter."""

import httpx
import pytest

from whisperbridge.providers.deepl_adapter import DeepLClientAdapter


def test_create_posts_normalized_user_text_to_free_endpoint(mocker):
    response = mocker.Mock()
    response.json.return_value = {
        "translations": [{"text": "Hallo", "detected_source_language": "EN"}]
    }
    client = mocker.MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = response
    client_factory = mocker.patch("whisperbridge.providers.deepl_adapter.httpx.Client", return_value=client)

    adapter = DeepLClientAdapter(api_key="unit-test-key", timeout=7, plan="free")
    result = adapter.chat.completions.create(
        model="ignored-model",
        messages=[
            {"role": "system", "content": "Ignore this"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Ignore this too"},
            {"role": "user", "content": "world"},
        ],
        target_lang=" de ",
        source_lang=" en ",
    )

    client_factory.assert_called_once_with(timeout=7)
    client.post.assert_called_once_with(
        "https://api-free.deepl.com/v2/translate",
        headers={
            "Authorization": "DeepL-Auth-Key unit-test-key",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"text": "Hello\nworld", "target_lang": "DE", "source_lang": "EN"},
    )
    response.raise_for_status.assert_called_once_with()
    assert result.choices[0].message.content == "Hallo"


def test_create_uses_pro_endpoint_and_omits_auto_detected_source(mocker):
    response = mocker.Mock()
    response.json.return_value = {"translations": [{"text": "Привет"}]}
    client = mocker.MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = response
    mocker.patch("whisperbridge.providers.deepl_adapter.httpx.Client", return_value=client)

    adapter = DeepLClientAdapter(api_key="unit-test-key", timeout=11, plan="pro")
    result = adapter.chat.completions.create(
        model="ignored-model",
        messages=[{"role": "user", "content": "Hello"}],
        target_lang="ua",
        source_lang="auto",
    )

    client.post.assert_called_once_with(
        "https://api.deepl.com/v2/translate",
        headers={
            "Authorization": "DeepL-Auth-Key unit-test-key",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"text": "Hello", "target_lang": "UK"},
    )
    assert result.choices[0].message.content == "Привет"


def test_create_propagates_http_failures(mocker):
    response = mocker.Mock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "unauthorized", request=mocker.Mock(), response=mocker.Mock(status_code=401)
    )
    client = mocker.MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = response
    mocker.patch("whisperbridge.providers.deepl_adapter.httpx.Client", return_value=client)

    adapter = DeepLClientAdapter(api_key="unit-test-key")

    with pytest.raises(httpx.HTTPStatusError, match="unauthorized"):
        adapter.chat.completions.create(
            model="ignored-model",
            messages=[{"role": "user", "content": "Hello"}],
            target_lang="EN",
        )
