"""
Tests for ClipboardService.

Verifies:
- copy_text with standard strings and empty strings
- copy_text error handling
- get_clipboard_text success and error handling
- get_clipboard_service singleton behavior and missing dependency handling
- shutdown method compatibility
"""

import pytest
import whisperbridge.services.clipboard_service as cs_module
from whisperbridge.services.clipboard_service import (
    ClipboardService,
    get_clipboard_service,
)


@pytest.fixture(autouse=True)
def reset_clipboard_singleton():
    """Reset the module-level singleton instance before and after each test."""
    orig_instance = cs_module._clipboard_service_instance
    cs_module._clipboard_service_instance = None
    yield
    cs_module._clipboard_service_instance = orig_instance


class TestClipboardService:
    """Unit tests for ClipboardService operations."""

    def test_copy_text_success(self, mocker):
        mock_copy = mocker.patch.object(cs_module.pyperclip, "copy")
        service = ClipboardService()

        result = service.copy_text("hello world")

        assert result is True
        mock_copy.assert_called_once_with("hello world")

    def test_copy_text_empty_string(self, mocker):
        mock_copy = mocker.patch.object(cs_module.pyperclip, "copy")
        service = ClipboardService()

        result = service.copy_text("")

        assert result is True
        mock_copy.assert_called_once_with("")

    def test_copy_text_none_input(self, mocker):
        mock_copy = mocker.patch.object(cs_module.pyperclip, "copy")
        service = ClipboardService()

        result = service.copy_text(None)  # type: ignore

        assert result is False
        mock_copy.assert_not_called()

    def test_copy_text_exception_handled(self, mocker):
        mocker.patch.object(cs_module.pyperclip, "copy", side_effect=RuntimeError("Clipboard locked"))
        service = ClipboardService()

        result = service.copy_text("sample")

        assert result is False

    def test_get_clipboard_text_success(self, mocker):
        mocker.patch.object(cs_module.pyperclip, "paste", return_value="copied text")
        service = ClipboardService()

        result = service.get_clipboard_text()

        assert result == "copied text"

    def test_get_clipboard_text_empty(self, mocker):
        mocker.patch.object(cs_module.pyperclip, "paste", return_value="")
        service = ClipboardService()

        result = service.get_clipboard_text()

        assert result == ""

    def test_get_clipboard_text_exception_returns_none(self, mocker):
        mocker.patch.object(cs_module.pyperclip, "paste", side_effect=RuntimeError("Cannot open clipboard"))
        service = ClipboardService()

        result = service.get_clipboard_text()

        assert result is None

    def test_shutdown_is_safe_noop(self):
        service = ClipboardService()
        # Should execute cleanly without error
        service.shutdown()

    def test_init_raises_if_pyperclip_unavailable(self, mocker):
        mocker.patch.object(cs_module, "PYPERCLIP_AVAILABLE", False)

        with pytest.raises(ImportError, match="pyperclip is required"):
            ClipboardService()


class TestGetClipboardServiceSingleton:
    """Unit tests for get_clipboard_service singleton factory."""

    def test_get_clipboard_service_returns_same_instance(self):
        service1 = get_clipboard_service()
        service2 = get_clipboard_service()

        assert service1 is not None
        assert service1 is service2

    def test_get_clipboard_service_when_pyperclip_unavailable(self, mocker):
        mocker.patch.object(cs_module, "PYPERCLIP_AVAILABLE", False)

        service = get_clipboard_service()

        assert service is None
