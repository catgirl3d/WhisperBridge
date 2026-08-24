"""
Translator overlay dialogs and panel widgets.

Configuration Guidelines:
- All widget styles should be centralized in CONFIG dictionaries.
- Use consistent naming: {WIDGET_TYPE}_CONFIG.
- Shared widget factory [`src/whisperbridge/ui_qt/widget_factory.py`](src/whisperbridge/ui_qt/widget_factory.py:1) handles low-level creation.
- Python sets identity/state (objectName, role, properties); QSS handles visuals.

Key Principles:
1. Centralized Configuration: All metadata in CONFIG dictionaries at class level.
2. Explicit Mapping: Use explicit role-to-config mappings, not dynamic key generation.
3. Shared Factory: Use `widget_factory` helpers to deduplicate common setup logic.
4. Stable Identity: Always set `objectName` (for QSS) and `role` (for internal logic).
5. Separation of Concerns: Visual appearance lives exclusively in QSS.
"""

from typing import List, Optional

from loguru import logger
from PySide6.QtCore import (
    QEvent,
    Qt,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTextEdit,
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

    # Configuration for translator settings dialog
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

        # Apply dialog configuration
        dialog_config = self.TRANSLATOR_DIALOG_CONFIG["dialog"]
        self.setWindowTitle(dialog_config["title"])
        self.setObjectName(dialog_config["object_name"])
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMinimumWidth(dialog_config["minimum_width"])

        layout = QVBoxLayout(self)
        settings = config_service.get_settings()

        config_maps = {"translator": self.TRANSLATOR_DIALOG_CONFIG}

        # Display Options group
        from PySide6.QtWidgets import QGroupBox
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

        # Clipboard group
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

        # Close button
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
            if enabled is None:
                return

            parent = self.parent()
            if parent and hasattr(parent, "_update_layout"):
                getattr(parent, "_update_layout")()
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
            if enabled is None:
                return

            parent = self.parent()
            if parent and hasattr(parent, "_update_layout"):
                getattr(parent, "_update_layout")()
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


class PanelWidget(QFrame):
    """Reusable panel with a text area and an optional side or bottom button area."""
    
    # Configuration for layout spacing and dimensions
    LAYOUT_CONFIG = {
        'main_vertical_spacing': 4,
        'main_vertical_margins': (0, 0, 0, 0),
        'top_horizontal_margins': (0, 0, 0, 0),
        'side_panel_expanded_width': 28,
        'side_panel_collapsed_width': 1,
        'side_panel_spacing': 3,
        'side_panel_margins': (0, 0, 0, 0),
        'btn_row_margins': (0, 0, 0, 0)
    }

    def __init__(self, text_edit: QTextEdit, buttons: List[QPushButton], apply_button_style_cb, parent=None):
        super().__init__(parent)
        self.text_edit = text_edit
        self.buttons = buttons
        self._apply_btn_style = apply_button_style_cb
        self.side_panel: Optional[QFrame] = None
        self.btn_row: Optional[QHBoxLayout] = None
        self._autohide = False

        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.installEventFilter(self)

        # Main structure: top (text + optional side panel), bottom (optional btn row)
        self._main_v = QVBoxLayout(self)
        self._main_v.setContentsMargins(*self.LAYOUT_CONFIG['main_vertical_margins'])
        self._main_v.setSpacing(self.LAYOUT_CONFIG['main_vertical_spacing'])

        self._top_h = QHBoxLayout()
        self._top_h.setContentsMargins(*self.LAYOUT_CONFIG['top_horizontal_margins'])
        self._top_h.addWidget(self.text_edit, 1)
        self._main_v.addLayout(self._top_h, 1)

    def _ensure_side_panel(self):
        if self.side_panel is None:
            panel = QFrame()
            panel.setFrameStyle(QFrame.Shape.NoFrame)
            panel.setFixedWidth(self.LAYOUT_CONFIG['side_panel_expanded_width'])
            v = QVBoxLayout(panel)
            v.setSpacing(self.LAYOUT_CONFIG['side_panel_spacing'])
            v.setContentsMargins(*self.LAYOUT_CONFIG['side_panel_margins'])
            v.addStretch()
            v.addStretch()
            panel.setMouseTracking(True)
            panel.installEventFilter(self)
            # Insert buttons above the bottom stretch
            for btn in self.buttons:
                v.insertWidget(v.count() - 1, btn, alignment=Qt.AlignmentFlag.AlignHCenter)
            self._top_h.addWidget(panel)
            self.side_panel = panel

    def _remove_side_panel(self):
        if self.side_panel is not None:
            layout = self.side_panel.layout()
            if layout:
                for btn in self.buttons:
                    layout.removeWidget(btn)
            self._top_h.removeWidget(self.side_panel)
            self.side_panel.deleteLater()
            self.side_panel = None

    def _ensure_btn_row(self):
        if self.btn_row is None:
            row = QHBoxLayout()
            row.setContentsMargins(*self.LAYOUT_CONFIG['btn_row_margins'])
            row.addStretch(1)
            for btn in self.buttons:
                row.addWidget(btn)
            self._main_v.addLayout(row)
            self.btn_row = row

    def _remove_btn_row(self):
        if self.btn_row is not None:
            for btn in self.buttons:
                self.btn_row.removeWidget(btn)
            self._main_v.removeItem(self.btn_row)
            self.btn_row = None

    def configure(self, compact: bool, autohide: bool):
        """Switch between compact (side panel) and full (bottom row) modes."""
        self._autohide = autohide
        if compact:
            self._remove_btn_row()
            self._ensure_side_panel()
            if self.side_panel:
                width = self.LAYOUT_CONFIG['side_panel_expanded_width'] if not autohide else self.LAYOUT_CONFIG['side_panel_collapsed_width']
                self.side_panel.setFixedWidth(width)
            for b in self.buttons:
                b.setVisible(not autohide)
                self._apply_btn_style(b, True)
        else:
            self._remove_side_panel()
            self._ensure_btn_row()
            for b in self.buttons:
                b.setVisible(True)
                self._apply_btn_style(b, False)

    def eventFilter(self, obj, event):
        # Hover-based autohide for compact mode
        try:
            autohide = getattr(self, '_autohide', False)
            side_panel = getattr(self, 'side_panel', None)
            if autohide and side_panel and obj in (self, side_panel):
                if event.type() == QEvent.Type.Enter:
                    side_panel.setFixedWidth(self.LAYOUT_CONFIG['side_panel_expanded_width'])
                    for b in self.buttons:
                        b.setVisible(True)
                elif event.type() == QEvent.Type.Leave:
                    if not side_panel.underMouse() and not self.underMouse():
                        side_panel.setFixedWidth(self.LAYOUT_CONFIG['side_panel_collapsed_width'])
                        for b in self.buttons:
                            b.setVisible(False)
        except Exception as e:
            logger.debug(f"PanelWidget eventFilter error: {e}")
        return False
