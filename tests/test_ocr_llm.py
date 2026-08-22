"""
Unit tests for LLM OCR functionality in OCRService.

Tests validate key behaviors without hitting real network.
"""

import asyncio
import base64
from io import BytesIO
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock
from PIL import Image

from whisperbridge.core.api_manager import APIManager, APIProvider
from whisperbridge.services.ocr_service import OCRService, OCREngine, OCRRequest
from whisperbridge.services.ocr_translation_service import OCRTranslationCoordinator
from whisperbridge.services.translation_service import TranslationService


class FakeConfigService:
    """Fake config service for testing."""

    def __init__(self):
        self.settings = {}

    def get_setting(self, key):
        return self.settings.get(key)


@pytest.fixture
def fake_config():
    """Create a fake config service."""
    return FakeConfigService()


@pytest.fixture
def openai_api_manager(fake_config):
    """Create a real API manager with only its external client replaced."""
    external_client = MagicMock()
    api_manager = APIManager(fake_config)
    api_manager._is_initialized = True
    api_manager._diag_logged = True
    api_manager._providers._clients[APIProvider.OPENAI] = external_client
    return api_manager, external_client


def test_ensure_ready_returns_true(fake_config):
    """Test ensure_ready returns True for LLM engine."""
    # Setup
    service = OCRService(fake_config)
    
    # Action
    result = service.ensure_ready()

    # Assertions
    assert result is True


def test_llm_success_path_preserves_valid_image_payload_and_returns_result(
    fake_config, openai_api_manager, mocker
):
    """The OCR pipeline sends a decodable JPEG payload and returns API text."""
    # Setup
    service = OCRService(fake_config)
    fake_config.settings.update({
        "ocr_engine": "llm",
        "api_provider": "openai",
        "ocr_llm_prompt": "Extract plain text...",
        "openai_vision_model": "gpt-5.4-mini"
    })

    # Mock only the external provider boundary.
    api_manager, external_client = openai_api_manager
    external_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Hello LLM"))],
        usage=None,
    )

    mocker.patch(
        "whisperbridge.services.ocr_service.get_api_manager",
        return_value=api_manager,
    )

    # Action
    tiny_image = Image.new("RGB", (8, 8), color=(20, 40, 60))
    request = OCRRequest(image=tiny_image, preprocess=False)
    result = service.process_image(request)

    # Assertions
    assert result.engine == OCREngine.LLM
    assert result.text == "Hello LLM"
    assert result.success is True
    external_client.chat.completions.create.assert_called_once()

    request_kwargs = external_client.chat.completions.create.call_args.kwargs
    assert request_kwargs["model"] == "gpt-5.4-mini"
    assert request_kwargs["max_completion_tokens"] > 0

    messages = request_kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "Extract plain text..."}
    assert messages[1]["role"] == "user"
    assert messages[1]["content"][0] == {
        "type": "text",
        "text": "Extract the text as-is. Keep natural reading order. Return only the text.",
    }

    image_part = messages[1]["content"][1]
    assert image_part["type"] == "image_url"
    data_url = image_part["image_url"]["url"]
    prefix, encoded_image = data_url.split(",", 1)
    assert prefix == "data:image/jpeg;base64"

    decoded_image = base64.b64decode(encoded_image, validate=True)
    with Image.open(BytesIO(decoded_image)) as encoded_pil_image:
        encoded_pil_image.load()
        assert encoded_pil_image.format == "JPEG"
        assert encoded_pil_image.size == tiny_image.size


def test_llm_whitespace_response_is_reported_as_unsuccessful(
    fake_config, openai_api_manager, mocker
):
    """Whitespace-only API text must be reported as an empty OCR result."""
    service = OCRService(fake_config)
    fake_config.settings.update(
        {
            "ocr_llm_prompt": "Extract plain text...",
            "api_provider": "openai",
            "openai_vision_model": "gpt-5.4-mini",
        }
    )
    api_manager, external_client = openai_api_manager
    external_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=" \n\t "))],
        usage=None,
    )
    mocker.patch(
        "whisperbridge.services.ocr_service.get_api_manager",
        return_value=api_manager,
    )

    result = service.process_image(OCRRequest(image=Image.new("RGB", (8, 8))))

    assert result.success is False
    assert result.text == ""
    assert result.confidence == 0.0
    assert result.error_message == "Empty OCR text from LLM"


def test_ocr_translation_passes_ui_languages_without_detection_or_swap(mocker):
    """OCR coordinator delegates effective language policy to TranslationService."""
    class Settings:
        ui_source_language = "auto"
        ui_target_language = "uk"

        @property
        def auto_swap_en_ru(self):
            raise AssertionError("OCR coordinator must not read auto_swap_en_ru")

    coordinator = object.__new__(OCRTranslationCoordinator)
    coordinator.translation_service = mocker.Mock(is_available=True)
    coordinator.translation_service.translate_text_sync.return_value = MagicMock(
        success=True,
        translated_text="translated",
    )
    mocker.patch(
        "whisperbridge.services.ocr_translation_service.config_service.get_settings",
        return_value=Settings(),
    )
    mocker.patch(
        "whisperbridge.services.ocr_translation_service.get_notification_service",
        return_value=mocker.Mock(),
    )

    translated_text, error_message = coordinator._translate_if_needed("selected text")

    assert (translated_text, error_message) == ("translated", "")
    coordinator.translation_service.detect_language_sync.assert_not_called()
    coordinator.translation_service.translate_text_sync.assert_called_once_with(
        "selected text",
        source_lang="auto",
        target_lang="uk",
    )


def test_translation_service_owns_detection_and_auto_swap(mocker):
    """TranslationService resolves effective EN/RU direction from raw UI settings."""
    class Settings:
        auto_swap_en_ru = True
        ui_target_language = "uk"

    service = object.__new__(TranslationService)
    service._detect_language_async = AsyncMock(return_value="en")
    mocker.patch(
        "whisperbridge.services.translation_service.config_service.get_settings",
        return_value=Settings(),
    )

    source_lang, target_lang = asyncio.run(
        service._determine_languages("selected text", "auto", "uk")
    )

    assert (source_lang, target_lang) == ("en", "ru")
    service._detect_language_async.assert_awaited_once_with("selected text")
