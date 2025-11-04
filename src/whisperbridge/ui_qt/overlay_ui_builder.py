"""
Overlay UI Builder module for creating overlay window components.
"""

from pathlib import Path
from typing import List, Optional

import qtawesome as qta
from loguru import logger
from PySide6.QtCore import (
    QEvent,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import QFont, QIcon, QPixmap, QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
    QVBoxLayout,
)

from ..services.config_service import config_service, SettingsObserver
from ..utils.language_utils import detect_language, get_language_name, get_supported_languages
from ..core.config import validate_api_key_format

# Base path for assets
_ASSETS_BASE = Path(__file__).parent.parent / "assets"


class TranslatorSettingsDialog(QDialog):
    """Dialog for translator-specific settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translator Settings")
        self.setObjectName("TranslatorSettingsDialog")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        settings = config_service.get_settings()

        # Compact view checkbox
        self.compact_view_checkbox = QCheckBox("Compact view")
        self.compact_view_checkbox.setToolTip("Hides labels and buttons for a more compact translator window")
        self.compact_view_checkbox.setChecked(getattr(settings, "compact_view", False))
        self.compact_view_checkbox.stateChanged.connect(self._on_compact_view_changed)
        layout.addWidget(self.compact_view_checkbox)

        # Side buttons auto-hide checkbox
        self.autohide_buttons_checkbox = QCheckBox("Hide right-side buttons (show on hover)")
        self.autohide_buttons_checkbox.setToolTip("If enabled, the narrow buttons on the right appear only on hover")
        self.autohide_buttons_checkbox.setChecked(getattr(settings, "overlay_side_buttons_autohide", False))
        self.autohide_buttons_checkbox.stateChanged.connect(self._on_autohide_buttons_changed)
        layout.addWidget(self.autohide_buttons_checkbox)

        close_button = QPushButton("Close")
        close_button.setFixedHeight(26)
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

    def _on_compact_view_changed(self, state):
        """Persist compact view setting."""
        try:
            enabled = bool(state)
            config_service.set_setting("compact_view", enabled)
            logger.info(f"Compact view setting updated: {enabled}")
            parent = self.parent()
            if parent and hasattr(parent, "_update_layout"):
                getattr(parent, "_update_layout")()
        except Exception as e:
            logger.error(f"Failed to save compact view setting: {e}")

    def _on_autohide_buttons_changed(self, state):
        """Persist side-buttons auto-hide setting and apply policy immediately."""
        try:
            enabled = bool(state)
            config_service.set_setting("overlay_side_buttons_autohide", enabled)
            logger.info(f"Side buttons auto-hide updated: {enabled}")
            parent = self.parent()
            if parent and hasattr(parent, "_update_layout"):
                getattr(parent, "_update_layout")()
        except Exception as e:
            logger.error(f"Failed to save side buttons auto-hide setting: {e}")


class PanelWidget(QFrame):
    """Reusable panel with a text area and an optional side or bottom button area."""

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
        self._main_v.setContentsMargins(0, 0, 0, 0)
        self._main_v.setSpacing(4)

        self._top_h = QHBoxLayout()
        self._top_h.setContentsMargins(0, 0, 0, 0)
        self._top_h.addWidget(self.text_edit, 1)
        self._main_v.addLayout(self._top_h, 1)

    def _ensure_side_panel(self):
        if self.side_panel is None:
            panel = QFrame()
            panel.setFrameStyle(QFrame.Shape.NoFrame)
            panel.setFixedWidth(28)
            v = QVBoxLayout(panel)
            v.setSpacing(3)
            v.setContentsMargins(0, 0, 0, 0)
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
            row.setContentsMargins(0, 0, 0, 0)
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
                self.side_panel.setFixedWidth(28 if not autohide else 1)
            for b in self.buttons:
                b.setVisible(not autohide)
                self._apply_btn_style(b, True)
        else:
            self._remove_side_panel()
            self._ensure_btn_row()
            for b in self.buttons:
                self._apply_btn_style(b, False)

    def eventFilter(self, obj, event):
        # Hover-based autohide for compact mode
        try:
            autohide = getattr(self, '_autohide', False)
            side_panel = getattr(self, 'side_panel', None)
            if autohide and side_panel and obj in (self, side_panel):
                if event.type() == QEvent.Type.Enter:
                    side_panel.setFixedWidth(28)
                    for b in self.buttons:
                        b.setVisible(True)
                elif event.type() == QEvent.Type.Leave:
                    if not side_panel.underMouse() and not self.underMouse():
                        side_panel.setFixedWidth(1)
                        for b in self.buttons:
                            b.setVisible(False)
        except Exception as e:
            logger.debug(f"PanelWidget eventFilter error: {e}")
        return False


class OverlayUIBuilder:
    """Builder class for creating overlay window UI components."""

    def __init__(self):
        self.icon_translation = self._load_icon("translation-icon.png")
        self.icon_book_black = self._load_icon("book_black.png")
        self.icon_book_white = self._load_icon("book_white.png")
        self.icon_arrows_exchange = self._load_icon("arrows-exchange.png")
        self.icon_eraser = qta.icon("fa5s.eraser", color="black")
        self.icon_copy = qta.icon("fa5.copy", color="black")
        self.icon_check_green = qta.icon("fa5s.check", color="green")
        # Disabled-state visuals
        self.icon_lock_white = qta.icon("fa5s.lock", color="white")
        self.icon_lock_grey = qta.icon("fa5s.lock", color="#757575")

    def _load_icon(self, icon_name: str) -> QIcon:
        """Load icon from assets."""
        return QIcon(QPixmap(str(_ASSETS_BASE / "icons" / icon_name)))

    def _set_bold_font(self, label: QLabel):
        """Set the font of a QLabel to bold."""
        font = QFont("Arial", 10)
        font.setBold(True)
        label.setFont(font)

    def _create_text_edit(self, placeholder):
        """Create a QTextEdit widget."""
        text_edit = QTextEdit()
        text_edit.setReadOnly(False)
        text_edit.setAcceptRichText(False)
        text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        text_edit.setPlaceholderText(placeholder)
        text_edit.setStyleSheet("QTextEdit { color: #111111; background-color: #ffffff; }")
        return text_edit

    def _create_button(self, parent=None, text=None, icon=None, size=(40, 28), tooltip=None):
        """Generic button factory. Default parent is the overlay window to ensure ownership."""
        btn = QPushButton(parent)
        if text:
            btn.setText(text)
        if icon:
            btn.setIcon(icon)
            btn.setIconSize(QSize(16, 16))
        btn.setFixedSize(*size)
        if tooltip:
            btn.setToolTip(tooltip)
        return btn

    def _apply_button_style(self, button: QPushButton, compact: bool):
        """Apply styling to a button based on compact mode using configuration dictionary."""
        button_configs = {
            self.translate_btn: {
                'compact': {
                    'text': '',
                    'size': (24, 24),
                    'icon_size': (12, 12),
                    'stylesheet': "QPushButton { background-color: #4CAF50; color: white; border: none; border-radius: 4px; font-weight: bold; padding: 0px; margin: 0px; } QPushButton:hover { background-color: #45a049; }",
                    'icon': None
                },
                'full': {
                    'text': self._translate_original_text if hasattr(self, "_translate_original_text") else "  Translate",
                    'size': (120, 28),
                    'icon_size': (14, 14),
                    'stylesheet': "",
                    'icon': None
                }
            },
            self.reader_mode_btn: {
                'compact': {
                    'text': '',
                    'size': (24, 24),
                    'icon_size': (17, 17),
                    'stylesheet': "QPushButton { background-color: #2196F3; color: white; border: none; border-radius: 4px; font-weight: bold; padding: 0px; margin: 0px; } QPushButton:hover { background-color: #1976D2; }",
                    'icon': self.icon_book_white
                },
                'full': {
                    'text': self._reader_original_text if hasattr(self, "_reader_original_text") else "Reader",
                    'size': (40, 28),
                    'icon_size': (19, 19),
                    'stylesheet': "",
                    'icon': self.icon_book_black
                }
            }
        }

        # Default styles for other buttons
        default_compact = {
            'text': '',
            'size': (24, 24),
            'icon_size': (15, 15),
            'stylesheet': "QPushButton { padding: 0px; margin: 0px; }",
            'icon': None
        }
        default_full = {
            'text': '',
            'size': (40, 28),
            'icon_size': (16, 16),
            'stylesheet': "",
            'icon': None
        }

        mode = 'compact' if compact else 'full'
        config = button_configs.get(button, {}).get(mode, default_compact if compact else default_full)

        button.setText(config['text'])
        button.setFixedSize(*config['size'])
        button.setIconSize(QSize(*config['icon_size']))
        button.setStyleSheet(config['stylesheet'])
        if config.get('icon') is not None:
            button.setIcon(config['icon'])

    def _create_info_row(self):
        """Create the top info row with mode selector, style presets, language detection and auto-translate."""
        container = QFrame()
        container.setFrameStyle(QFrame.Shape.NoFrame)

        info_row = QHBoxLayout(container)
        info_row.setContentsMargins(0, 0, 0, 0)

        # Left: Mode selector + Style presets (when Style mode is active)
        self.mode_label = QLabel("Mode:")
        info_row.addWidget(self.mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.setFixedSize(95, 28)
        self.mode_combo.addItem("Translate")
        self.mode_combo.addItem("Style")
        info_row.addWidget(self.mode_combo)

        # Style presets combo
        self.style_combo = QComboBox()
        self.style_combo.setFixedSize(95, 28)
        self._populate_styles()
        info_row.addWidget(self.style_combo)
        # Hidden by default; shown only in Style mode via _apply_mode_visibility
        self.style_combo.setVisible(False)

        # Middle: stretch to push detection + auto-swap to the right
        info_row.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        # Right: Detected language label + Auto-translate toggle
        self.detected_lang_label = QLabel("Language: —")
        self.detected_lang_label.setFixedWidth(120)
        info_row.addWidget(self.detected_lang_label)

        self.auto_swap_checkbox = QCheckBox("Auto-translate EN ↔ RU")
        self.auto_swap_checkbox.setToolTip("If enabled, English will be translated to Russian, and Russian to English")
        info_row.addWidget(self.auto_swap_checkbox)

        # Return the container widget so it can be managed uniformly (hideable_elements)
        return container

    def _create_language_row(self):
        """Create the language selection row."""
        language_row = QHBoxLayout()
        self.original_label = QLabel("Original:")
        self._set_bold_font(self.original_label)
        language_row.addWidget(self.original_label, alignment=Qt.AlignmentFlag.AlignBottom)
        language_row.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self.source_combo = QComboBox()
        self.target_combo = QComboBox()
        for combo in [self.source_combo, self.target_combo]:
            combo.setFixedSize(125, 28)
            combo.setIconSize(QSize(28, 28))
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            combo.setStyleSheet("QComboBox { background-color: #fff; color: #111111; padding: 0px; padding-left: 8px; }")

        self.swap_btn = QPushButton()
        self.swap_btn.setFixedSize(35, 28)
        self.swap_btn.setIcon(self.icon_arrows_exchange)
        self.swap_btn.setIconSize(QSize(20, 24))

        language_row.addWidget(self.source_combo)
        language_row.addWidget(self.swap_btn)
        language_row.addWidget(self.target_combo)

        # Spacer for compact mode button panel
        self.language_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        language_row.addItem(self.language_spacer)

        return language_row

    def _populate_styles(self):
        """Populate style presets from settings into style_combo."""
        try:
            self.style_combo.clear()
            settings = config_service.get_settings()
            styles = getattr(settings, "text_styles", []) or []
            if not styles:
                self.style_combo.addItem("Improve")  # fallback display
                return
            for s in styles:
                name = (s.get("name") or "").strip() if isinstance(s, dict) else str(s)
                if name:
                    self.style_combo.addItem(name)
        except Exception as e:
            logger.warning(f"Failed to populate styles: {e}")

    def _create_footer(self):
        """Create the footer row with status label and close button."""
        footer_widget = QFrame()
        footer_widget.setFrameStyle(QFrame.Shape.NoFrame)
        footer_row = QHBoxLayout(footer_widget)
        footer_row.setContentsMargins(0, 0, 0, 0)

        # Status label in the bottom-left corner
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666; font-size: 10px;")
        footer_row.addWidget(self.status_label)

        footer_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFixedSize(86, 28)
        close_btn.setObjectName("closeButton")
        self.close_icon_normal = qta.icon("fa5s.times", color="black")
        self.close_icon_hover = qta.icon("fa5s.times", color="white")
        close_btn.setIcon(self.close_icon_normal)
        close_btn.setIconSize(QSize(16, 16))
        footer_row.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        return footer_widget, close_btn

    def _init_language_controls(self):
        """Populate and configure language selection combos."""
        supported_languages = get_supported_languages()
        flags_path = _ASSETS_BASE / "icons" / "flags"

        self.source_combo.insertItem(0, "Auto", userData="auto")

        for lang in supported_languages:
            icon_path = flags_path / lang.icon_name
            icon = QIcon(QPixmap(str(icon_path)))

            self.source_combo.addItem(icon, lang.name, userData=lang.code)
            self.target_combo.addItem(icon, lang.name, userData=lang.code)

        settings = config_service.get_settings()
        ui_source_language = getattr(settings, "ui_source_language", "en")
        self._set_combo_data(self.source_combo, ui_source_language)
        if self.source_combo.currentData() != ui_source_language:
            self._set_combo_data(self.source_combo, "en")

        ui_target_language = getattr(settings, "ui_target_language", "en")
        self._set_combo_data(self.target_combo, ui_target_language)
        if self.target_combo.currentData() != ui_target_language:
            self._set_combo_data(self.target_combo, "en")

    def _set_combo_data(self, combo, data_value):
        """Set combo to the index matching the data value, with signal blocking."""
        combo.blockSignals(True)
        try:
            for i in range(combo.count()):
                if combo.itemData(i) == data_value:
                    combo.setCurrentIndex(i)
                    break
        finally:
            combo.blockSignals(False)

    def build_ui(self, owner):
        """Build and return all UI components for the overlay window."""
        # Create main UI widgets
        info_row = self._create_info_row()
        language_row = self._create_language_row()

        self.original_text = self._create_text_edit("Recognized text will appear here...")
        self.translated_text = self._create_text_edit("Translation will appear here...")

        self.translated_label = QLabel("Translation:")
        self._set_bold_font(self.translated_label)

        self.translate_btn = self._create_button(text="  Translate", size=(120, 28))
        # Ensure stylesheet targeting and identity remain intact
        self.translate_btn.setObjectName("translateButton")
        # Set icon for translate button
        self.translate_btn.setIcon(self.icon_translation)
        self.translate_btn.setIconSize(QSize(14, 14))
        # preserve original display text for restore
        self._translate_original_text = self.translate_btn.text()
        self.reader_mode_btn = self._create_button(text="", tooltip="Open text in reader mode for comfortable reading")
        # Set icon for reader mode button
        self.reader_mode_btn.setIcon(self.icon_book_black)
        self.reader_mode_btn.setIconSize(QSize(14, 14))
        # preserve original display text for restore
        self._reader_original_text = self.reader_mode_btn.text()
        self.reader_mode_btn.setEnabled(False)  # Disable by default if no translated text
        self.clear_original_btn = self._create_button(text="", icon=self.icon_eraser, size=(40, 28), tooltip="Clear text")
        self.copy_original_btn = self._create_button(text="", icon=self.icon_copy, size=(40, 28), tooltip="Copy text")
        self.clear_translated_btn = self._create_button(text="", icon=self.icon_eraser, size=(40, 28), tooltip="Clear text")
        self.copy_translated_btn = self._create_button(text="", icon=self.icon_copy, size=(40, 28), tooltip="Copy text")

        self.original_buttons = [self.translate_btn, self.clear_original_btn, self.copy_original_btn]
        self.translated_buttons = [self.reader_mode_btn, self.clear_translated_btn, self.copy_translated_btn]

        # Use reusable panel widgets instead of ad-hoc containers
        self.original_panel = PanelWidget(self.original_text, self.original_buttons, self._apply_button_style, parent=owner)
        self.translated_panel = PanelWidget(self.translated_text, self.translated_buttons, self._apply_button_style, parent=owner)

        footer_widget, close_btn = self._create_footer()

        # Return all created components
        return {
            'info_row': info_row,
            'language_row': language_row,
            'original_panel': self.original_panel,
            'translated_label': self.translated_label,
            'translated_panel': self.translated_panel,
            'footer_widget': footer_widget,
            'close_btn': close_btn,
            'hideable_elements': [info_row, self.original_label, self.translated_label, footer_widget]
        }