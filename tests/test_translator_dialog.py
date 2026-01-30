"""Tests for TranslatorSettingsDialog factory integration."""

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton, QGroupBox, QWidget
from PySide6.QtCore import Qt
from unittest.mock import Mock

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

    # Check that Display Options widgets were created via factory
    assert dialog.compact_view_checkbox is not None
    assert isinstance(dialog.compact_view_checkbox, QCheckBox)
    assert dialog.compact_view_checkbox.objectName() == "compact_view_checkbox"

    assert dialog.autohide_buttons_checkbox is not None
    assert isinstance(dialog.autohide_buttons_checkbox, QCheckBox)
    assert dialog.autohide_buttons_checkbox.objectName() == "autohide_buttons_checkbox"

    # Check that Performance widgets were created via factory
    assert dialog.stylist_cache_checkbox is not None
    assert isinstance(dialog.stylist_cache_checkbox, QCheckBox)
    assert dialog.stylist_cache_checkbox.objectName() == "stylist_cache_checkbox"

    assert dialog.translation_cache_checkbox is not None
    assert isinstance(dialog.translation_cache_checkbox, QCheckBox)
    assert dialog.translation_cache_checkbox.objectName() == "translation_cache_checkbox"

    # Check that Clipboard widgets were created via factory
    assert dialog.auto_copy_translated_checkbox is not None
    assert isinstance(dialog.auto_copy_translated_checkbox, QCheckBox)
    assert dialog.auto_copy_translated_checkbox.objectName() == "auto_copy_translated_checkbox"

    # Check that close button exists and has correct objectName
    # (close_button is local variable, but we can check the layout has it)
    layout = dialog.layout()
    assert layout is not None
    # Layout contains: display_group, performance_group, clipboard_group, close_button
    assert layout.count() == 4

    # Check that the last item is the close button with correct objectName
    close_item = layout.itemAt(3)
    close_button = close_item.widget()
    assert isinstance(close_button, QPushButton)
    assert close_button.objectName() == "translatorCloseButton"

    dialog.close()


# ==================== Initialization Tests ====================

def test_translator_dialog_initialization_from_config(qapp, mocker):
    """Test initialization of checkboxes from config_service."""
    # Mock config_service
    mock_settings = Mock()
    mock_settings.compact_view = True
    mock_settings.overlay_side_buttons_autohide = False
    mock_settings.stylist_cache_enabled = True
    mock_settings.translation_cache_enabled = False
    mock_settings.auto_copy_translated_main_window = True
    
    mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.get_settings',
                 return_value=mock_settings)
    
    dialog = TranslatorSettingsDialog()
    
    assert dialog.compact_view_checkbox.isChecked()
    assert not dialog.autohide_buttons_checkbox.isChecked()
    assert dialog.stylist_cache_checkbox.isChecked()
    assert not dialog.translation_cache_checkbox.isChecked()
    assert dialog.auto_copy_translated_checkbox.isChecked()
    
    dialog.close()


def test_translator_dialog_initialization_with_defaults(qapp, mocker):
    """Test initialization with default values when settings are missing."""
    # Mock config_service with empty settings object
    mock_settings = Mock(spec=[])  # Without attributes
    
    mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.get_settings',
                 return_value=mock_settings)
    
    dialog = TranslatorSettingsDialog()
    
    # All should be False by default due to getattr(..., False)
    assert not dialog.compact_view_checkbox.isChecked()
    assert not dialog.autohide_buttons_checkbox.isChecked()
    assert not dialog.stylist_cache_checkbox.isChecked()
    assert not dialog.translation_cache_checkbox.isChecked()
    assert not dialog.auto_copy_translated_checkbox.isChecked()
    
    dialog.close()


# ==================== Event Handler/Callback Tests ====================

def test_compact_view_changed_callback(qapp, mocker):
    """Test saving compact_view setting when checkbox changes."""
    mock_set_setting = mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.set_setting')
    
    dialog = TranslatorSettingsDialog()
    
    # Simulate checkbox state change
    dialog.compact_view_checkbox.setChecked(True)
    
    # Verify config_service.set_setting was called with correct parameters
    mock_set_setting.assert_called_with("compact_view", True)
    
    dialog.close()


def test_autohide_buttons_changed_callback(qapp, mocker):
    """Test saving overlay_side_buttons_autohide setting when checkbox changes."""
    mock_set_setting = mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.set_setting')
    
    dialog = TranslatorSettingsDialog()
    dialog.autohide_buttons_checkbox.setChecked(True)
    
    mock_set_setting.assert_called_with("overlay_side_buttons_autohide", True)
    dialog.close()


def test_stylist_cache_changed_callback(qapp, mocker):
    """Test saving stylist_cache_enabled setting when checkbox changes."""
    mock_set_setting = mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.set_setting')
    
    dialog = TranslatorSettingsDialog()
    # Change to True first (default is False)
    dialog.stylist_cache_checkbox.setChecked(True)
    mock_set_setting.assert_called_with("stylist_cache_enabled", True)
    dialog.close()


def test_translation_cache_changed_callback(qapp, mocker):
    """Test saving translation_cache_enabled setting when checkbox changes."""
    mock_set_setting = mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.set_setting')
    
    dialog = TranslatorSettingsDialog()
    dialog.translation_cache_checkbox.setChecked(True)
    
    mock_set_setting.assert_called_with("translation_cache_enabled", True)
    dialog.close()


def test_auto_copy_translated_changed_callback(qapp, mocker):
    """Test saving auto_copy_translated_main_window setting when checkbox changes."""
    mock_set_setting = mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.set_setting')
    
    dialog = TranslatorSettingsDialog()
    dialog.auto_copy_translated_checkbox.setChecked(True)
    
    mock_set_setting.assert_called_with("auto_copy_translated_main_window", True)
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


# ==================== Parent Window Integration Tests ====================

def test_compact_view_triggers_parent_update_layout(qapp, mocker):
    """Test calling parent._update_layout() when compact_view changes."""
    # Create mock parent with _update_layout method
    mock_parent = Mock(spec=['_update_layout'])
    mock_parent._update_layout = mocker.Mock()
    
    mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.set_setting')
    
    dialog = TranslatorSettingsDialog(parent=None)
    dialog.parent = lambda: mock_parent  # Mock parent() method
    
    dialog.compact_view_checkbox.setChecked(True)
    
    # Verify _update_layout was called
    mock_parent._update_layout.assert_called_once()
    dialog.close()


def test_autohide_buttons_triggers_parent_update_layout(qapp, mocker):
    """Test calling parent._update_layout() when autohide_buttons changes."""
    # Create mock parent with _update_layout method
    mock_parent = Mock(spec=['_update_layout'])
    mock_parent._update_layout = mocker.Mock()
    
    mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.set_setting')
    
    dialog = TranslatorSettingsDialog(parent=None)
    dialog.parent = lambda: mock_parent  # Mock parent() method
    
    dialog.autohide_buttons_checkbox.setChecked(True)
    
    mock_parent._update_layout.assert_called_once()
    dialog.close()


def test_callback_without_parent(qapp, mocker):
    """Test that callbacks work without parent window."""
    mock_set_setting = mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.set_setting')
    
    dialog = TranslatorSettingsDialog(parent=None)  # No parent
    dialog.compact_view_checkbox.setChecked(True)
    
    # No errors should occur, setting should be saved
    mock_set_setting.assert_called_with("compact_view", True)
    dialog.close()


def test_callback_with_parent_without_update_layout(qapp, mocker):
    """Test that callbacks work if parent doesn't have _update_layout method."""
    # Create mock parent without _update_layout method
    mock_parent = Mock(spec=[])
    mock_set_setting = mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.set_setting')
    
    dialog = TranslatorSettingsDialog(parent=None)
    dialog.parent = lambda: mock_parent  # Mock parent() method
    
    dialog.compact_view_checkbox.setChecked(True)
    
    # No errors should occur, setting should be saved
    mock_set_setting.assert_called_with("compact_view", True)
    dialog.close()


# ==================== Error Handling Tests ====================

def test_error_handling_in_compact_view_callback(qapp, mocker):
    """Test error handling when saving compact_view setting."""
    # Mock set_setting to raise exception
    mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.set_setting',
                 side_effect=Exception("Database error"))
    
    dialog = TranslatorSettingsDialog()
    # Should not raise exception, just log error
    dialog.compact_view_checkbox.setChecked(True)
    
    dialog.close()


# ==================== Dialog Properties Tests ====================

def test_dialog_properties(qapp):
    """Test dialog properties (modal, deleteOnClose, minimumWidth)."""
    dialog = TranslatorSettingsDialog()
    
    assert dialog.windowTitle() == "Translator Settings"
    assert dialog.objectName() == "TranslatorSettingsDialog"
    assert not dialog.isModal()
    assert dialog.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    assert dialog.minimumWidth() >= 320
    
    dialog.close()


# ==================== Widget Groups Tests ====================

def test_dialog_has_all_groups(qapp):
    """Test presence of all QGroupBox groups with correct titles."""
    dialog = TranslatorSettingsDialog()
    
    # Find all QGroupBox in layout
    layout = dialog.layout()
    groups = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        widget = item.widget()
        if isinstance(widget, QGroupBox):
            groups.append(widget.title())
    
    assert "Display Options" in groups
    assert "Performance" in groups
    assert "Clipboard" in groups
    assert len(groups) == 3  # Only 3 groups
    
    dialog.close()


def test_error_handling_in_stylist_cache_callback(qapp, mocker):
    """Test error handling when saving stylist_cache_enabled setting."""
    mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.set_setting',
                 side_effect=Exception("Config error"))
    
    dialog = TranslatorSettingsDialog()
    # Should not raise exception, just log error
    dialog.stylist_cache_checkbox.setChecked(True)
    
    dialog.close()


# ==================== All Checkboxes Text and Tooltips Tests ====================

def test_all_checkboxes_text_and_tooltips(qapp):
    """Test text and tooltip for all checkboxes."""
    dialog = TranslatorSettingsDialog()
    
    # Display Options
    assert dialog.compact_view_checkbox.text() == "Compact view"
    assert dialog.compact_view_checkbox.toolTip() == "Hides labels and buttons for a more compact translator window"
    
    assert dialog.autohide_buttons_checkbox.text() == "Hide right-side buttons (show on hover)"
    assert dialog.autohide_buttons_checkbox.toolTip() == "If enabled, the narrow buttons on the right appear only on hover"
    
    # Performance
    assert dialog.stylist_cache_checkbox.text() == "Enable Text Stylist caching"
    assert dialog.stylist_cache_checkbox.toolTip() == "Enable caching for Text Stylist mode (separate from general translation caching)"
    
    assert dialog.translation_cache_checkbox.text() == "Enable translation caching"
    assert dialog.translation_cache_checkbox.toolTip() == "Enable caching for translation mode (separate from general caching)"
    
    # Clipboard
    assert dialog.auto_copy_translated_checkbox.text() == "Auto-copy translated text to clipboard"
    assert dialog.auto_copy_translated_checkbox.toolTip() == "Automatically copy translated text to clipboard after translation"
    
    dialog.close()


# ==================== Close Button Functionality Tests ====================

def test_close_button_functionality(qapp, qtbot):
    """Test close button functionality."""
    dialog = TranslatorSettingsDialog()
    dialog.show()
    
    # Find close button
    layout = dialog.layout()
    close_item = layout.itemAt(3)
    close_button = close_item.widget()
    
    # Click the button
    qtbot.mouseClick(close_button, Qt.MouseButton.LeftButton)
    
    # Verify dialog closed
    qtbot.waitUntil(lambda: not dialog.isVisible(), timeout=1000)


# ==================== Checkbox State Conversion Tests ====================

def test_checkbox_state_conversion_to_bool(qapp, mocker):
    """Test that checkbox state is correctly converted to bool."""
    mock_set_setting = mocker.patch('src.whisperbridge.ui_qt.overlay_ui_builder.config_service.set_setting')
    
    dialog = TranslatorSettingsDialog()
    
    # Qt.CheckState.Checked (2) should convert to True
    dialog.compact_view_checkbox.setCheckState(Qt.CheckState.Checked)
    mock_set_setting.assert_called_with("compact_view", True)
    
    # Qt.CheckState.Unchecked (0) should convert to False
    dialog.compact_view_checkbox.setCheckState(Qt.CheckState.Unchecked)
    mock_set_setting.assert_called_with("compact_view", False)
    
    dialog.close()