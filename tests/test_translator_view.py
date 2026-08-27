"""Observable presentation contract for the translator view component."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QVBoxLayout

from whisperbridge.ui_qt.translator_view import TranslatorView
from whisperbridge.utils.language_utils import Language


@pytest.fixture
def view(qapp, qtbot):
    languages = [Language("en", "English", "en.png"), Language("ru", "Russian", "ru.png")]
    widget = TranslatorView(languages, [{"name": "Formal"}], parent=None)
    qtbot.addWidget(widget)
    return widget


def test_view_layout_owns_order_and_panel_stretch(view):
    layout = view.layout()
    assert isinstance(layout, QVBoxLayout)
    assert layout.contentsMargins().left() == 0
    assert layout.spacing() == 6
    assert [layout.itemAt(i).widget() or layout.itemAt(i).layout() for i in range(layout.count())] == [
        view.info_row, view.language_row, view.original_panel, view.translated_label, view.translated_panel, view.footer_widget
    ]
    assert layout.stretch(layout.indexOf(view.original_panel)) == 1
    assert layout.stretch(layout.indexOf(view.translated_panel)) == 1


def test_view_preserves_identity_and_dynamic_properties(view):
    assert view.original_text.objectName() == "textEdit"
    assert view.translated_text.objectName() == "textEdit"
    assert view.source_combo.objectName() == "sourceLanguageCombo"
    assert view.target_combo.objectName() == "targetLanguageCombo"
    assert view.translate_btn.property("role") == "translateButton"
    assert view.reader_mode_btn.property("role") == "readerButton"
    assert view.copy_original_btn.property("utility") is True


def test_translator_text_controls_override_dark_palette_text_color(qapp, qtbot):
    """Light-styled translator controls stay readable with a dark application palette."""
    from PySide6.QtWidgets import QCheckBox, QGroupBox

    from whisperbridge.services.theme_service import ThemeService

    previous_palette = qapp.palette()
    previous_stylesheet = qapp.styleSheet()
    config_service = Mock()
    config_service.get_setting.return_value = "dark"

    try:
        ThemeService(qt_app=qapp, config_service=config_service, logger=Mock())
        checkbox = QCheckBox("Auto-translate EN <-> RU")
        disabled_checkbox = QCheckBox("Disabled")
        disabled_checkbox.setEnabled(False)
        group_box = QGroupBox("Display Options")
        for widget in (checkbox, disabled_checkbox, group_box):
            qtbot.addWidget(widget)
        qapp.processEvents()

        assert checkbox.palette().color(QPalette.ColorRole.WindowText) == QColor("#111111")
        assert disabled_checkbox.palette().color(QPalette.ColorRole.WindowText) == QColor("#9e9e9e")
        assert group_box.palette().color(QPalette.ColorRole.WindowText) == QColor("#111111")
    finally:
        qapp.setStyleSheet(previous_stylesheet)
        qapp.setPalette(previous_palette)


def test_language_selection_blocks_signals_and_falls_back(view):
    source_spy = QSignalSpy(view.source_combo.currentIndexChanged)
    view.set_language_selection("unknown", "ru")
    assert view.source_combo.currentData() == "en"
    assert view.target_combo.currentData() == "ru"
    assert source_spy.size() == 0


def test_style_refresh_preserves_selection_and_improve_fallback(view):
    view.style_combo.setCurrentText("Formal")
    view.refresh_styles([{"name": "Formal"}, {"name": "Casual"}])
    assert view.style_combo.currentText() == "Formal"
    view.refresh_styles([])
    assert view.style_combo.currentText() == "Improve"


def test_view_starts_in_translate_mode_and_reveals_style_controls(view):
    assert view.mode_combo.currentText() == "Translate"
    assert view.style_combo.isHidden()
    assert view.edit_styles_btn.isHidden()

    view.set_mode_visibility("Style", compact=False)
    assert not view.style_combo.isHidden()
    assert not view.edit_styles_btn.isHidden()


def test_panel_reconfiguration_does_not_duplicate_controls(view):
    for compact, autohide in ((False, False), (True, False), (True, True), (False, False)):
        view.configure(compact, autohide, 16)
    assert len(view.original_panel.buttons) == 3
    assert len(view.translated_panel.buttons) == 3
    assert view.original_panel.btn_row is not None
    assert view.original_panel.side_panel is None


def test_status_disabled_restore_and_provider_transitions(view):
    view.set_status("Error", "error")
    assert view.status_label.text() == "Error"
    assert view.status_label.property("status") == "error"
    view.set_translate_disabled("No key", False)
    assert view.translate_btn.property("logically_disabled") is True
    view.restore_translate(False)
    assert view.translate_btn.property("logically_disabled") is False
    view.set_style_mode_available(False)
    assert view.mode_combo.findText("Style") == -1
    view.set_style_mode_available(True)
    assert view.mode_combo.findText("Style") >= 0
    view.set_provider_badge("OpenAI", "openai")
    assert view.provider_badge.property("provider") == "openai"


def test_overlay_content_has_only_view_and_top_controls_are_external(qapp, qtbot, mocker):
    from whisperbridge.ui_qt.overlay_window import OverlayWindow

    settings = SimpleNamespace(
        text_styles=[], ui_source_language="en", ui_target_language="en",
        compact_view=False, overlay_side_buttons_autohide=False,
        translator_font_size=16, auto_swap_en_ru=True,
    )
    mocker.patch("whisperbridge.ui_qt.overlay_window.config_service.get_settings", return_value=settings)
    mocker.patch("whisperbridge.ui_qt.overlay_window.config_service.get_setting", return_value=None)
    window = OverlayWindow()
    qtbot.addWidget(window)
    assert window.content_layout.count() == 1
    assert window.content_layout.itemAt(0).widget() is window.view
    assert window.view.parentWidget() is window
    assert window.close_btn_top.parentWidget() is window
    assert window.collapse_btn_top.parentWidget() is window


def test_overlay_language_swap_uses_view_controls_and_persists(qapp, qtbot, mocker):
    from whisperbridge.ui_qt.overlay_window import OverlayWindow

    settings = SimpleNamespace(
        text_styles=[], ui_source_language="en", ui_target_language="ru",
        compact_view=False, overlay_side_buttons_autohide=False,
        translator_font_size=16, auto_swap_en_ru=True,
    )
    mocker.patch("whisperbridge.ui_qt.overlay_window.config_service.get_settings", return_value=settings)
    mocker.patch("whisperbridge.ui_qt.overlay_window.config_service.get_setting", return_value=None)
    persist = mocker.patch(
        "whisperbridge.ui_qt.overlay_window.config_service.update_settings",
        return_value=True,
    )
    window = OverlayWindow()
    qtbot.addWidget(window)

    assert window.view.source_combo.currentData() == "en"
    assert window.view.target_combo.currentData() == "ru"
    window._perform_language_swap()

    assert window.view.source_combo.currentData() == "ru"
    assert window.view.target_combo.currentData() == "en"
    persist.assert_called_once_with({"ui_source_language": "ru", "ui_target_language": "en"})
