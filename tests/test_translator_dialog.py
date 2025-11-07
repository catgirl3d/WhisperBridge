"""Tests for TranslatorSettingsDialog factory integration."""

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton

from src.whisperbridge.ui_qt.overlay_ui_builder import TranslatorSettingsDialog


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_translator_dialog_factory_integration(qapp):
    """Test that TranslatorSettingsDialog uses factory and preserves attributes."""
    dialog = TranslatorSettingsDialog()

    # Check that widgets were created via factory (have objectName from config)
    assert dialog.compact_view_checkbox is not None
    assert isinstance(dialog.compact_view_checkbox, QCheckBox)
    assert dialog.compact_view_checkbox.objectName() == "compact_view_checkbox"

    assert dialog.autohide_buttons_checkbox is not None
    assert isinstance(dialog.autohide_buttons_checkbox, QCheckBox)
    assert dialog.autohide_buttons_checkbox.objectName() == "autohide_buttons_checkbox"

    # Check that close button exists and has correct objectName
    # (close_button is local variable, but we can check the layout has it)
    layout = dialog.layout()
    assert layout is not None
    assert layout.count() == 3  # Two checkboxes + close button

    # Check that the last item is the close button with correct objectName
    close_item = layout.itemAt(2)
    close_button = close_item.widget()
    assert isinstance(close_button, QPushButton)
    assert close_button.objectName() == "translatorCloseButton"

    dialog.close()


def test_translator_dialog_config_consistency(qapp):
    """Test that config values are applied correctly."""
    dialog = TranslatorSettingsDialog()

    # Check compact view checkbox config
    checkbox = dialog.compact_view_checkbox
    assert checkbox.text() == "Compact view"
    assert checkbox.toolTip() == "Hides labels and buttons for a more compact translator window"

    # Check autohide checkbox config
    autohide_checkbox = dialog.autohide_buttons_checkbox
    assert autohide_checkbox.text() == "Hide right-side buttons (show on hover)"
    assert autohide_checkbox.toolTip() == "If enabled, the narrow buttons on the right appear only on hover"

    dialog.close()