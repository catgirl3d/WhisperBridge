"""
Unit tests for LLM OCR functionality in OCRService.

Tests validate key behaviors without hitting real network.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from PIL import Image

from whisperbridge.services.ocr_service import OCRService, OCREngine, OCRResult, OCRRequest
from whisperbridge.services.ocr_translation_service import OCRTranslationCoordinator
from whisperbridge.services.translation_service import TranslationService


class FakeConfigService:
    """Fake config service for testing."""

    def __init__(self):
        self.settings = {}

    def get_setting(self, key, use_cache=True):
        return self.settings.get(key)


class FakeAPIManager:
    """Fake API manager for testing."""

    def __init__(self):
        self.make_vision_request = MagicMock()
        self.extract_text_from_response = MagicMock()


@pytest.fixture
def fake_config():
    """Create a fake config service."""
    return FakeConfigService()


@pytest.fixture
def fake_api_manager():
    """Create a fake API manager."""
    return FakeAPIManager()


def test_ensure_ready_returns_true(fake_config):
    """Test ensure_ready returns True for LLM engine."""
    # Setup
    service = OCRService(fake_config)
    
    # Action
    result = service.ensure_ready()

    # Assertions
    assert result is True


def test_llm_success_path_returns_llm_result(fake_config, fake_api_manager, mocker):
    """Test LLM success path returns LLM result."""
    # Setup
    service = OCRService(fake_config)
    fake_config.settings.update({
        "ocr_engine": "llm",
        "api_provider": "openai",
        "ocr_llm_prompt": "Extract plain text...",
        "openai_vision_model": "gpt-5.4-mini"
    })

    # Mock to_data_url_jpeg
    mock_to_data_url = mocker.patch("whisperbridge.services.ocr_service.to_data_url_jpeg")
    mock_to_data_url.return_value = "data:image/jpeg;base64,AA=="

    # Mock get_api_manager
    mock_get_api_manager = mocker.patch("whisperbridge.services.ocr_service.get_api_manager")
    mock_get_api_manager.return_value = fake_api_manager
    fake_api_manager.make_vision_request.return_value = (
        {"choices": [{"message": {"content": "Hello LLM"}}]},
        "gpt-5.4-mini"
    )

    # Mock the response object to have the expected structure
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "Hello LLM"
    fake_api_manager.make_vision_request.return_value = (mock_response, "gpt-5.4-mini")

    # Mock extract_text_from_response to return the expected text
    fake_api_manager.extract_text_from_response.return_value = "Hello LLM"

    # Mock config_service.get_setting for _process_llm_image
    mock_config_service = mocker.patch("whisperbridge.services.ocr_service.config_service")
    mock_config_service.get_setting.side_effect = lambda key, default=None: {
        "ocr_llm_prompt": "Extract plain text...",
        "api_provider": "openai",
        "openai_vision_model": "gpt-5.4-mini",
        "ocr_engine": "llm"
    }.get(key, default)

    # Action
    tiny_image = Image.new("RGB", (8, 8))
    request = OCRRequest(image=tiny_image, preprocess=False)
    result = service.process_image(request)

    # Assertions
    assert result.engine == OCREngine.LLM
    assert result.text == "Hello LLM"
    assert result.success is True


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
