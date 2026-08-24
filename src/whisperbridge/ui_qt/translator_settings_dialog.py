"""Translator-specific settings dialog."""

from typing import Optional

from loguru import logger
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ..core.config import (
    TRANSLATOR_FONT_SIZE_DEFAULT,
    TRANSLATOR_FONT_SIZE_MAX,
    TRANSLATOR_FONT_SIZE_MIN,
)
from ..services.config_service import config_service
from .widget_factory import create_widget as _create_widget


def _resolve_translator_font_size_setting(settings) -> int:
    """Return a safe integer font size for dialog initialization/rollback."""
    value = getattr(settings, "translator_font_size", TRANSLATOR_FONT_SIZE_DEFAULT)
    if isinstance(value, bool) or not isinstance(value, int):
        return TRANSLATOR_FONT_SIZE_DEFAULT
    return value


def _resolve_bool_setting(settings, key: str, default: bool = False) -> bool:
    """Return a strict boolean from settings, falling back for missing/mock values."""
    value = getattr(settings, key, default)
    return value if isinstance(value, bool) else default


class TranslatorSettingsDialog(QDialog):
    """Dialog for translator-specific settings."""

    layout_settings_changed = Signal()

    TRANSLATOR_DIALOG_CONFIG = {
        'dialog': {
            'title': "Translator Settings",
            'object_name': "TranslatorSettingsDialog",
            'minimum_width': 320
        },
        'compact_view_checkbox': {
            'text': "Compact view",
            'tooltip': "Hides labels and buttons for a more compact translator window",
            'object_name': "compact_view_checkbox"
        },
        'autohide_buttons_checkbox': {
            'text': "Hide right-side buttons (show on hover)",
            'tooltip': "If enabled, the narrow buttons on the right appear only on hover",
            'object_name': "autohide_buttons_checkbox"
        },
        'translator_font_size_label': {
            'text': "Text size:",
            'object_name': "translator_font_size_label"
        },
        'translator_font_size_spinbox': {
            'object_name': "translator_font_size_spinbox",
            'tooltip': "Set the font size for both translator text fields",
            'width': 64,
            'minimum': TRANSLATOR_FONT_SIZE_MIN,
            'maximum': TRANSLATOR_FONT_SIZE_MAX,
            'single_step': 1,
        },
        'auto_copy_translated_checkbox': {
            'text': "Auto-copy translated text to clipboard",
            'tooltip': "Automatically copy translated text to clipboard after translation",
            'object_name': "auto_copy_translated_checkbox"
        },
        'close_button': {
            'text': "Close",
            'size': (None, 26),
            'object_name': "translatorCloseButton"
        }
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        dialog_config = self.TRANSLATOR_DIALOG_CONFIG["dialog"]
        self.setWindowTitle(dialog_config["title"])
        self.setObjectName(dialog_config["object_name"])
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMinimumWidth(dialog_config["minimum_width"])

        layout = QVBoxLayout(self)
        settings = config_service.get_settings()
        config_maps = {"translator": self.TRANSLATOR_DIALOG_CONFIG}

        display_group = QGroupBox("Display Options")
        display_layout = QVBoxLayout(display_group)

        self.compact_view_checkbox, _ = _create_widget(config_maps, "translator", "compact_view_checkbox", QCheckBox)
        self.compact_view_checkbox.setChecked(_resolve_bool_setting(settings, "compact_view"))
        self.compact_view_checkbox.stateChanged.connect(self._on_compact_view_changed)
        display_layout.addWidget(self.compact_view_checkbox)

        self.autohide_buttons_checkbox, _ = _create_widget(
            config_maps, "translator", "autohide_buttons_checkbox", QCheckBox
        )
        self.autohide_buttons_checkbox.setChecked(_resolve_bool_setting(settings, "overlay_side_buttons_autohide"))
        self.autohide_buttons_checkbox.stateChanged.connect(self._on_autohide_buttons_changed)
        display_layout.addWidget(self.autohide_buttons_checkbox)

        self.translator_font_size_label, _ = _create_widget(
            config_maps, "translator", "translator_font_size_label", QLabel
        )
        self.translator_font_size_spinbox, font_size_config = _create_widget(
            config_maps, "translator", "translator_font_size_spinbox", QSpinBox
        )
        self.translator_font_size_spinbox.setRange(font_size_config["minimum"], font_size_config["maximum"])
        self.translator_font_size_spinbox.setSingleStep(font_size_config["single_step"])
        self.translator_font_size_spinbox.setValue(_resolve_translator_font_size_setting(settings))
        self.translator_font_size_spinbox.valueChanged.connect(self._on_translator_font_size_changed)

        font_size_row = QHBoxLayout()
        font_size_row.addWidget(self.translator_font_size_label)
        font_size_row.addWidget(self.translator_font_size_spinbox)
        font_size_row.addStretch()
        display_layout.addLayout(font_size_row)
        layout.addWidget(display_group)

        clipboard_group = QGroupBox("Clipboard")
        clipboard_layout = QVBoxLayout(clipboard_group)
        self.auto_copy_translated_checkbox, _ = _create_widget(
            config_maps, "translator", "auto_copy_translated_checkbox", QCheckBox
        )
        self.auto_copy_translated_checkbox.setChecked(
            _resolve_bool_setting(settings, "auto_copy_translated_overlay")
        )
        self.auto_copy_translated_checkbox.stateChanged.connect(self._on_auto_copy_translated_changed)
        clipboard_layout.addWidget(self.auto_copy_translated_checkbox)
        layout.addWidget(clipboard_group)

        close_button, _ = _create_widget(config_maps, "translator", "close_button", QPushButton)
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

    def _on_compact_view_changed(self, state):
        """Persist compact view setting."""
        try:
            enabled = self._persist_checkbox_setting(
                checkbox=self.compact_view_checkbox,
                setting_key="compact_view",
                state=state,
                success_message="Compact view setting updated",
            )
            if enabled is not None:
                self.layout_settings_changed.emit()
        except Exception as e:
            logger.error(f"Failed to save compact view setting: {e}")

    def _on_autohide_buttons_changed(self, state):
        """Persist side-buttons auto-hide setting and apply policy immediately."""
        try:
            enabled = self._persist_checkbox_setting(
                checkbox=self.autohide_buttons_checkbox,
                setting_key="overlay_side_buttons_autohide",
                state=state,
                success_message="Side buttons auto-hide updated",
            )
            if enabled is not None:
                self.layout_settings_changed.emit()
        except Exception as e:
            logger.error(f"Failed to save side buttons auto-hide setting: {e}")

    def _on_translator_font_size_changed(self, value):
        """Persist translator text font size setting."""
        try:
            previous_font_size = _resolve_translator_font_size_setting(config_service.get_settings())
            font_size = int(value)
            success = config_service.set_setting("translator_font_size", font_size)
            if not success:
                self.translator_font_size_spinbox.blockSignals(True)
                self.translator_font_size_spinbox.setValue(previous_font_size)
                self.translator_font_size_spinbox.blockSignals(False)
                logger.error(f"Failed to persist translator font size setting: {font_size}")
                return
            logger.info(f"Translator font size updated: {font_size}")
        except Exception as e:
            logger.error(f"Failed to save translator font size setting: {e}")

    def _on_auto_copy_translated_changed(self, state):
        """Persist auto-copy translated text setting."""
        try:
            self._persist_checkbox_setting(
                checkbox=self.auto_copy_translated_checkbox,
                setting_key="auto_copy_translated_overlay",
                state=state,
                success_message="Auto-copy translated text setting updated",
            )
        except Exception as e:
            logger.error(f"Failed to save auto-copy translated text setting: {e}")

    def _persist_checkbox_setting(self, checkbox: QCheckBox, setting_key: str, state, success_message: str) -> Optional[bool]:
        """Persist a checkbox-backed setting and roll back the UI if saving fails."""
        previous_value = _resolve_bool_setting(config_service.get_settings(), setting_key)
        enabled = bool(state)
        success = config_service.set_setting(setting_key, enabled)
        if not success:
            checkbox.blockSignals(True)
            checkbox.setChecked(previous_value)
            checkbox.blockSignals(False)
            logger.error(f"Failed to persist {setting_key}: {enabled}")
            return None

        logger.info(f"{success_message}: {enabled}")
        return enabled
