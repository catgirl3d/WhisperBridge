"""
Unit tests for LLM OCR functionality in OCRService.

Tests validate key behaviors without hitting real network or EasyOCR models.
"""

import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from whisperbridge.services.ocr_service import OCRService, OCREngine, OCRResult, OCRRequest
from whisperbridge.services.config_service import config_service


class FakeConfigService:
    """Fake config service for testing."""

    def __init__(self):
        self.settings = {
            "ocr_confidence_threshold": 0.5,
            "ocr_languages": ["en", "ru"]
        }

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


def test_ensure_ready_fast_path_for_llm(fake_config):
    """Test ensure_ready fast-path for LLM engine."""
    # Setup
    service = OCRService(fake_config)
    fake_config.settings["ocr_engine"] = "llm"

    # Action
    result = service.ensure_ready()

    # Assertions
    assert result is True
    assert service._easyocr_reader is None


def test_llm_success_path_returns_llm_result(fake_config, fake_api_manager):
    """Test LLM success path returns LLM result."""
    # Setup
    service = OCRService(fake_config)
    fake_config.settings.update({
        "ocr_engine": "llm",
        "ocr_enabled": True,
        "api_provider": "openai",
        "ocr_llm_prompt": "Extract plain text...",
        "openai_vision_model": "gpt-4o-mini"
    })

    # Mock to_data_url_jpeg
    with patch("whisperbridge.services.ocr_service.to_data_url_jpeg") as mock_to_data_url:
        mock_to_data_url.return_value = "data:image/jpeg;base64,AA=="

        # Mock get_api_manager
        with patch("whisperbridge.services.ocr_service.get_api_manager") as mock_get_api_manager:
            mock_get_api_manager.return_value = fake_api_manager
            fake_api_manager.make_vision_request.return_value = (
                {"choices": [{"message": {"content": "Hello LLM"}}]},
                "gpt-4o-mini"
            )

            # Mock the response object to have the expected structure
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message = MagicMock()
            mock_response.choices[0].message.content = "Hello LLM"
            fake_api_manager.make_vision_request.return_value = (mock_response, "gpt-4o-mini")

            # Mock extract_text_from_response to return the expected text
            fake_api_manager.extract_text_from_response.return_value = "Hello LLM"

            # Mock config_service.get_setting for _process_llm_image
            with patch("whisperbridge.services.ocr_service.config_service") as mock_config_service:
                mock_config_service.get_setting.side_effect = lambda key, default=None: {
                    "ocr_llm_prompt": "Extract plain text...",
                    "api_provider": "openai",
                    "openai_vision_model": "gpt-4o-mini",
                    "ocr_engine": "llm",
                    "ocr_enabled": True
                }.get(key, default)

            # Mock is_ocr_engine_ready to return True for LLM
            with patch.object(service, "is_ocr_engine_ready", return_value=True):
                # Mock _process_easyocr_array to ensure not called
                with patch.object(service, "_process_easyocr_array") as mock_easyocr:
                    mock_easyocr.side_effect = AssertionError("EasyOCR should not be called")
    
                    # Action
                    tiny_image = Image.new("RGB", (8, 8))
                    request = OCRRequest(image=tiny_image, preprocess=False)  # Disable preprocessing to avoid fallback
                    result = service.process_image(request)
    
                    # Assertions
                    assert result.engine == OCREngine.LLM
                    assert result.text == "Hello LLM"
                    assert result.success is True
                    mock_easyocr.assert_not_called()


def test_llm_failure_falls_back_to_easyocr_when_enabled(fake_config, fake_api_manager):
    """Test LLM failure falls back to EasyOCR when enabled."""
    # Setup
    service = OCRService(fake_config)
    fake_config.settings.update({
        "ocr_engine": "llm",
        "ocr_enabled": True,
        "initialize_ocr": True,
        "api_provider": "openai"
    })

    # Mock get_api_manager to raise exception
    with patch("whisperbridge.services.ocr_service.get_api_manager") as mock_get_api_manager:
        mock_get_api_manager.return_value = fake_api_manager
        fake_api_manager.make_vision_request.side_effect = Exception("LLM failed")

        # Mock is_ocr_engine_ready to return True for LLM
        with patch.object(service, "is_ocr_engine_ready", return_value=True):
            # Mock _process_easyocr_array
            with patch.object(service, "_process_easyocr_array") as mock_easyocr:
                mock_easyocr.return_value = OCRResult(
                    engine=OCREngine.EASYOCR,
                    text="easyocr text",
                    success=True,
                    confidence=0.85,
                    processing_time=0.1
                )

                # Mock config_service.get_setting for _process_llm_image
                with patch("whisperbridge.services.ocr_service.config_service") as mock_config_service:
                    mock_config_service.get_setting.side_effect = lambda key, default=None: {
                        "ocr_llm_prompt": "Extract plain text...",
                        "api_provider": "openai",
                        "openai_vision_model": "gpt-4o-mini",
                        "ocr_enabled": True,
                        "initialize_ocr": True
                    }.get(key, default)

                    # Action
                    tiny_image = Image.new("RGB", (8, 8))
                    request = OCRRequest(image=tiny_image)
                    result = service.process_image(request)

                    # Assertions
                    assert result.engine == OCREngine.EASYOCR
                    assert result.text == "easyocr text"
                    assert result.success is True


def test_llm_failure_without_fallback_when_disabled(fake_config, fake_api_manager):
    """Test LLM failure without fallback when EasyOCR disabled."""
    # Setup
    service = OCRService(fake_config)
    fake_config.settings.update({
        "ocr_engine": "llm",
        "ocr_enabled": False,
        "api_provider": "openai"
    })

    # Mock get_api_manager to raise exception
    with patch("whisperbridge.services.ocr_service.get_api_manager") as mock_get_api_manager:
        mock_get_api_manager.return_value = fake_api_manager
        fake_api_manager.make_vision_request.side_effect = Exception("LLM failed")

        # Mock is_ocr_engine_ready to return True for LLM
        with patch.object(service, "is_ocr_engine_ready", return_value=True):
            # Mock _process_easyocr_array to ensure not called
            with patch.object(service, "_process_easyocr_array") as mock_easyocr:
                mock_easyocr.side_effect = AssertionError("EasyOCR should not be called")

                # Mock config_service.get_setting for _process_llm_image
                with patch("whisperbridge.services.ocr_service.config_service") as mock_config_service:
                    mock_config_service.get_setting.side_effect = lambda key, default=None: {
                        "ocr_llm_prompt": "Extract plain text...",
                        "api_provider": "openai",
                        "openai_vision_model": "gpt-4o-mini",
                        "ocr_enabled": False,
                        "ocr_engine": "llm"
                    }.get(key, default)

                    # Action
                    tiny_image = Image.new("RGB", (8, 8))
                    request = OCRRequest(image=tiny_image, preprocess=False)  # Disable preprocessing to avoid fallback
                    result = service.process_image(request)

                    # Assertions
                    assert result.engine == OCREngine.LLM
                    assert result.success is False
                    assert result.text == ""
                    mock_easyocr.assert_not_called()