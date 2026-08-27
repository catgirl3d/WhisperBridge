"""UIService overlay lifecycle contract tests."""

from unittest.mock import Mock

from whisperbridge.services.ui_service import UIService


class _OverlayLifecycleFake:
    """Minimal concrete OverlayWindow lifecycle surface used by UIService."""

    def __init__(self, visible: bool, dismiss_error: Exception | None = None):
        self._visible = visible
        self._dismiss_error = dismiss_error
        self.dismiss_calls = 0
        self.show_calls = []

    def dismiss(self):
        self.dismiss_calls += 1
        if self._dismiss_error is not None:
            raise self._dismiss_error
        self._visible = False

    def is_overlay_visible(self) -> bool:
        return self._visible

    def show_overlay(self, original_text: str, translated_text: str):
        self.show_calls.append((original_text, translated_text))
        self._visible = True


def _build_ui_service(mocker, overlays=None) -> UIService:
    """Create UIService without initializing heavyweight Qt components."""
    mocker.patch.object(UIService, "_initialize_ui_components", return_value=None)
    ui = UIService(app=Mock(), overlay_windows=overlays)
    ui.logger = Mock()
    return ui


def test_hide_overlay_window_dismisses_existing_overlay(mocker):
    overlay = _OverlayLifecycleFake(visible=True)
    ui = _build_ui_service(mocker, {"ocr": overlay})

    ui.hide_overlay_window("ocr")

    assert overlay.dismiss_calls == 1


def test_hide_overlay_window_ignores_missing_overlay_without_registry_changes(mocker):
    untouched = _OverlayLifecycleFake(visible=True)
    ui = _build_ui_service(mocker, {"main": untouched})

    ui.hide_overlay_window("missing")

    assert ui.overlay_windows == {"main": untouched}
    assert untouched.dismiss_calls == 0
    ui.logger.error.assert_not_called()


def test_hide_overlay_window_logs_dismiss_failure_without_hide_fallback(mocker):
    overlay = _OverlayLifecycleFake(visible=True, dismiss_error=RuntimeError("dismiss failed"))
    ui = _build_ui_service(mocker, {"main": overlay})

    ui.hide_overlay_window()

    assert overlay.dismiss_calls == 1
    ui.logger.error.assert_called_once()
    assert "'main'" in ui.logger.error.call_args.args[0]
    assert ui.logger.error.call_args.kwargs["exc_info"] is True


def test_toggle_overlay_dismisses_visible_overlay_without_replacing_it(mocker):
    overlay = _OverlayLifecycleFake(visible=True)
    ui = _build_ui_service(mocker, {"main": overlay})

    ui.toggle_overlay()

    assert overlay.dismiss_calls == 1
    assert ui.overlay_windows["main"] is overlay


def test_toggle_overlay_shows_hidden_overlay(mocker):
    overlay = _OverlayLifecycleFake(visible=False)
    ui = _build_ui_service(mocker, {"main": overlay})

    ui.toggle_overlay()

    assert overlay.dismiss_calls == 0
    assert overlay.show_calls == [("", "")]


def test_toggle_overlay_replaces_broken_overlay_when_dismiss_fails(mocker):
    broken = _OverlayLifecycleFake(visible=True, dismiss_error=RuntimeError("dismiss failed"))
    replacement = _OverlayLifecycleFake(visible=False)
    overlay_factory = mocker.patch(
        "whisperbridge.services.ui_service.OverlayWindow",
        return_value=replacement,
    )
    ui = _build_ui_service(mocker, {"main": broken})

    ui.toggle_overlay()

    assert overlay_factory.call_count == 1
    assert ui.overlay_windows["main"] is replacement
    assert replacement.show_calls == [("", "")]
    assert ui.logger.error.called


def test_handle_copy_translate_skips_auto_copy_for_empty_translated_text(mocker):
    """pyperclip.copy("") wipes the whole clipboard; auto-copy must not run on empty text."""
    ui = _build_ui_service(mocker, {"copy_translate": Mock()})
    copy_mock = mocker.patch("whisperbridge.services.ui_service.pyperclip.copy")

    ui.handle_copy_translate("selected text", "", auto_copy=True)

    copy_mock.assert_not_called()


def test_handle_copy_translate_copies_nonempty_translated_text_with_auto_copy(mocker):
    """Non-empty translated text with auto_copy=True is copied exactly once after the overlay is shown."""
    ui = _build_ui_service(mocker)
    overlay = Mock()
    ui.overlay_windows["copy_translate"] = overlay
    copy_mock = mocker.patch("whisperbridge.services.ui_service.pyperclip.copy")

    ui.handle_copy_translate("selected text", "перевод", auto_copy=True)

    copy_mock.assert_called_once_with("перевод")
    overlay.show_overlay.assert_called_once_with("selected text", "перевод", error_message="")
