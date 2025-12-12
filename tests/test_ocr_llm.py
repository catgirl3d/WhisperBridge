"""
Unit tests for LLM OCR functionality in OCRService.

Tests validate key behaviors without hitting real network.
"""

import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from whisperbridge.services.ocr_service import OCRService, OCREngine, OCRResult, OCRRequest


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


def test_llm_success_path_returns_llm_result(fake_config, fake_api_manager):
    """Test LLM success path returns LLM result."""
    # Setup
    service = OCRService(fake_config)
    fake_config.settings.update({
        "ocr_engine": "llm",
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