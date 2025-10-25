"""
Overlay window implementation for Qt-based UI.
"""

from pathlib import Path

import qtawesome as qta
from loguru import logger
from PySide6.QtCore import (
    QEvent,
    QSize,
    Qt,
    QThread,
    QTimer,
)
from PySide6.QtGui import QFont, QIcon, QKeyEvent, QPixmap, QPainter, QColor, QPainterPath
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
from typing import List, Optional
from .styled_overlay_base import StyledOverlayWindow
from .workers import TranslationWorker, StyleWorker

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


class _OverlaySettingsObserver(SettingsObserver):
    """Lightweight observer to react to settings changes affecting API readiness."""
    def __init__(self, owner):
        self._owner = owner

    def on_settings_changed(self, key, old_value, new_value):
        try:
            if key in ("api_provider", "openai_api_key", "google_api_key", "deepl_api_key", "api_timeout"):
                if hasattr(self._owner, "_update_api_state_and_ui"):
                    self._owner._update_api_state_and_ui()
        except Exception as e:
            logger.debug(f"Overlay observer change handler error: {e}")

    def on_settings_loaded(self, settings):
        self.on_settings_changed("loaded", None, None)

    def on_settings_saved(self, settings):
        self.on_settings_changed("saved", None, None)


class OverlayWindow(StyledOverlayWindow):
    """Overlay window for displaying translation results."""

    def __init__(self):
        """Initialize the overlay window."""
        super().__init__(title="Translator")
        self._translator_settings_dialog = None
        # Removed redundant flag

        # Status tracking
        self._translation_start_time = None

        self._init_ui()
        self._init_language_controls()
        self._connect_signals()

        # Observe settings changes to react to provider/key updates
        try:
            self._settings_observer = _OverlaySettingsObserver(self)
            config_service.add_observer(self._settings_observer)
        except Exception as e:
            logger.debug(f"Failed to add settings observer: {e}")
        try:
            # Re-check UI state after async settings saves
            config_service.saved_async_result.connect(lambda *_: self._update_api_state_and_ui())
        except Exception as e:
            logger.debug(f"Failed to connect saved_async_result: {e}")

        # Initial API state check for button/status
        self._update_api_state_and_ui()

        logger.debug("OverlayWindow initialized")

    def _set_bold_font(self, label: QLabel):
        """Set the font of a QLabel to bold."""
        font = QFont("Arial", 10)
        font.setBold(True)
        label.setFont(font)

    def _load_icon(self, icon_name: str) -> QIcon:
        """Load icon from assets."""
        return QIcon(QPixmap(str(_ASSETS_BASE / "icons" / icon_name)))

    def _init_ui(self):
        """Initialize the main UI widgets."""
        # Cache all icons to avoid redundant loading
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

        self.original_label = QLabel("Original:")
        self._set_bold_font(self.original_label)

        self.hideable_elements = []

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
        self.reader_mode_btn.clicked.connect(self._on_reader_mode_clicked)
        self.clear_original_btn = self._create_button(text="", icon=self.icon_eraser, size=(40, 28), tooltip="Clear text")
        self.copy_original_btn = self._create_button(text="", icon=self.icon_copy, size=(40, 28), tooltip="Copy text")
        self.clear_translated_btn = self._create_button(text="", icon=self.icon_eraser, size=(40, 28), tooltip="Clear text")
        self.copy_translated_btn = self._create_button(text="", icon=self.icon_copy, size=(40, 28), tooltip="Copy text")

        self.original_buttons = [self.translate_btn, self.clear_original_btn, self.copy_original_btn]
        self.translated_buttons = [self.reader_mode_btn, self.clear_translated_btn, self.copy_translated_btn]

        # Use reusable panel widgets instead of ad-hoc containers
        self.original_panel = PanelWidget(self.original_text, self.original_buttons, self._apply_button_style, parent=self)
        self.translated_panel = PanelWidget(self.translated_text, self.translated_buttons, self._apply_button_style, parent=self)

        self.footer_widget, self.close_btn = self._create_footer()

        # Assemble layout
        layout = self.content_layout
        layout.setSpacing(6)
        # Keep a reference to the info row widget
        self.info_row_widget = info_row
        layout.addWidget(self.info_row_widget)
        layout.addLayout(language_row)
        # Apply initial mode visibility now that all controls exist
        if hasattr(self, "mode_combo"):
            try:
                self._apply_mode_visibility(self.mode_combo.currentText())
            except Exception:
                pass
        layout.addWidget(self.original_panel)
        layout.addWidget(self.translated_label)
        layout.addWidget(self.translated_panel)
        layout.addWidget(self.footer_widget)

        # Set stretch factors
        layout.setStretch(layout.indexOf(self.original_panel), 1)
        layout.setStretch(layout.indexOf(self.translated_panel), 1)

        self.hideable_elements.extend([self.info_row_widget, self.original_label, self.translated_label, self.footer_widget])
        self.add_settings_button(self._open_translator_settings)


    def _connect_signals(self):
        """Connect all UI signals to their slots."""
        self.auto_swap_checkbox.stateChanged.connect(self._on_auto_swap_changed)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        self.swap_btn.clicked.connect(self._on_swap_clicked)
        self.original_text.textChanged.connect(self._on_original_text_changed)
        self.translated_text.textChanged.connect(self._update_reader_button_state)
        if hasattr(self, "mode_combo"):
            self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        if self.translate_btn:
            self.translate_btn.clicked.connect(self._on_translate_clicked)
        self.clear_original_btn.clicked.connect(self._clear_original_text)
        self.copy_original_btn.clicked.connect(self._copy_original_to_clipboard)
        self.clear_translated_btn.clicked.connect(self._clear_translated_text)
        self.copy_translated_btn.clicked.connect(self._copy_translated_to_clipboard)
        self.close_btn.clicked.connect(self.dismiss)
        self.close_btn.installEventFilter(self)


    def _create_info_row(self):
        """Create the top info row with mode selector, style presets, language detection and auto-translate."""
        container = QFrame()
        container.setFrameStyle(QFrame.Shape.NoFrame)

        info_row = QHBoxLayout(container)
        info_row.setContentsMargins(0, 0, 0, 0)

        # Left: Mode selector + Style presets (when Style mode is active)
        mode_label = QLabel("Mode:")
        info_row.addWidget(mode_label)

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

    def _apply_mode_visibility(self, mode_text: str | None = None):
        """Show/hide controls based on selected mode."""
        try:
            mode = (mode_text or "").strip() or (self.mode_combo.currentText() if hasattr(self, "mode_combo") else "Translate")
            is_style = (mode.lower() == "style")

            # Update window title based on mode
            self.set_title("Styler" if is_style else "Translator")

            # Language-related widgets
            for w in [self.source_combo, self.target_combo, self.swap_btn, self.auto_swap_checkbox, self.detected_lang_label]:
                if w:
                    w.setVisible(not is_style)

            # Style presets widget
            if hasattr(self, "style_combo") and self.style_combo:
                self.style_combo.setVisible(is_style)

            # Labels/buttons text adjustments
            if hasattr(self, "translated_label") and self.translated_label:
                self.translated_label.setText("Result:" if is_style else "Translation:")

            if hasattr(self, "translate_btn") and self.translate_btn:
                # keep icon; only change text in non-compact mode; compact handled by _apply_button_style
                try:
                    if not getattr(self._cached_settings, "compact_view", False):
                        self.translate_btn.setText("  Style" if is_style else (self._translate_original_text if hasattr(self, "_translate_original_text") else "  Translate"))
                except Exception:
                    pass

            # Add bottom spacer to info row in Style mode
            if hasattr(self, "info_row_widget") and self.info_row_widget:
                if is_style:
                    if not hasattr(self, '_style_spacer'):
                        self._style_spacer = QSpacerItem(0, 13, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
                        idx = self.content_layout.indexOf(self.info_row_widget) + 1
                        self.content_layout.insertItem(idx, self._style_spacer)
                else:
                    if hasattr(self, '_style_spacer'):
                        self.content_layout.removeItem(self._style_spacer)
                        delattr(self, '_style_spacer')
        except Exception as e:
            logger.debug(f"Failed to apply mode visibility: {e}")

    def _on_mode_changed(self, index: int):
        """Handle mode switch between Translate and Style."""
        try:
            self._apply_mode_visibility(self.mode_combo.currentText())
        except Exception as e:
            logger.debug(f"Mode change failed: {e}")

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
        if parent is None:
            parent = self
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

    def _is_api_ready(self) -> tuple[bool, str]:
        """Check whether API calls can proceed given current provider/key settings."""
        try:
            provider = (config_service.get_setting("api_provider") or "openai").strip().lower()
            if provider not in ("openai", "google", "deepl"):
                provider = "openai"

            key = config_service.get_setting(f"{provider}_api_key")
            if not key:
                return False, f"{provider.capitalize()} API key is not configured"

            try:
                if validate_api_key_format(key, provider):
                    return True, ""
                else:
                    return False, f"{provider.capitalize()} API key format is invalid"
            except Exception:
                # Conservative fallback: consider presence sufficient if validator fails
                return True, ""
        except Exception as e:
            logger.debug(f"API readiness check failed: {e}")
            return False, "API key is not configured"

    def _apply_disabled_translate_visuals(self, reason_msg: str) -> None:
        """Apply strong disabled visuals for the Translate/Style button."""
        try:
            if not hasattr(self, "translate_btn") or not self.translate_btn:
                return

            # Determine compact mode safely
            compact = False
            try:
                compact = bool(getattr(getattr(self, "_cached_settings", None), "compact_view", False))
            except Exception:
                compact = False

            # Disable and set cursor/tooltip
            self.translate_btn.setEnabled(False)
            try:
                self.translate_btn.setCursor(Qt.CursorShape.ForbiddenCursor)
            except Exception:
                pass
            try:
                self.translate_btn.setToolTip(reason_msg or "API key is not configured. Open Settings to add a key.")
            except Exception:
                pass

            # Visual style and icon per mode
            if compact:
                # Compact: small square button → gray with white lock
                self.translate_btn.setStyleSheet(
                    "QPushButton { background-color: #9e9e9e; color: #ffffff; border: none; border-radius: 4px; font-weight: bold; padding: 0px; margin: 0px; }"
                )
                try:
                    self.translate_btn.setIcon(self.icon_lock_white)
                except Exception:
                    pass
            else:
                # Full: wider button → light gray bg, muted text, gray lock icon
                self.translate_btn.setStyleSheet(
                    "QPushButton { background-color: #e0e0e0; color: #9e9e9e; border: 1px solid #cfcfcf; border-radius: 4px; }"
                )
                try:
                    self.translate_btn.setIcon(self.icon_lock_grey)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Failed to apply disabled translate visuals: {e}")

    def _restore_enabled_translate_visuals(self) -> None:
        """Restore normal visuals for the Translate/Style button."""
        try:
            if not hasattr(self, "translate_btn") or not self.translate_btn:
                return

            # Avoid re-enabling visuals during an active request
            if getattr(self, "_translation_start_time", None) is None:
                self.translate_btn.setEnabled(True)

            # Restore cursor/tooltip
            try:
                self.translate_btn.setCursor(Qt.CursorShape.ArrowCursor)
            except Exception:
                pass
            try:
                self.translate_btn.setToolTip("")
            except Exception:
                pass

            # Re-apply normal style/icon based on compact mode
            compact = False
            try:
                compact = bool(getattr(getattr(self, "_cached_settings", None), "compact_view", False))
            except Exception:
                compact = False

            # Re-apply standard button styles for current mode
            try:
                self._apply_button_style(self.translate_btn, compact)
            except Exception:
                # Fallback to clearing the stylesheet
                self.translate_btn.setStyleSheet("")

            # Restore translation icon
            try:
                self.translate_btn.setIcon(self.icon_translation)
                self.translate_btn.setIconSize(QSize(14, 14))
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Failed to restore enabled translate visuals: {e}")

    def _update_api_state_and_ui(self) -> None:
        """Enable/disable action button and set high-priority status when API key is missing/invalid."""
        try:
            ready, msg = self._is_api_ready()

            # Strong visual treatment for the action button
            if not ready:
                self._apply_disabled_translate_visuals(msg)
            else:
                self._restore_enabled_translate_visuals()

            # Update status label with priority red message when not ready
            if hasattr(self, "status_label") and self.status_label:
                if not ready:
                    self.status_label.setStyleSheet("color: #c62828; font-weight: 600; font-size: 10px;")
                    self.status_label.setText(msg)
                else:
                    # Restore default style; don't override non-key statuses
                    self.status_label.setStyleSheet("color: #666; font-size: 10px;")
                    if "API key" in (self.status_label.text() or ""):
                        self.status_label.setText("")

            # Enforce provider capabilities (disable Style mode for DeepL)
            try:
                provider = (config_service.get_setting("api_provider") or "openai").strip().lower()
                if hasattr(self, "mode_combo") and self.mode_combo:
                    # Helper to find index by visible text
                    def _find_index_by_text(combo, text: str) -> int:
                        for i in range(combo.count()):
                            if (combo.itemText(i) or "").strip().lower() == text.lower():
                                return i
                        return -1

                    style_idx = _find_index_by_text(self.mode_combo, "Style")
                    if provider == "deepl":
                        # If currently on Style, switch to Translate before removing the item
                        try:
                            if (self.mode_combo.currentText() or "").strip().lower() == "style":
                                trans_idx = _find_index_by_text(self.mode_combo, "Translate")
                                if trans_idx != -1:
                                    self.mode_combo.setCurrentIndex(trans_idx)
                                    self._apply_mode_visibility("Translate")
                        except Exception:
                            pass
                        # Remove Style option
                        if style_idx != -1:
                            self.mode_combo.removeItem(style_idx)
                        # Ensure style combo is hidden
                        if hasattr(self, "style_combo") and self.style_combo:
                            self.style_combo.setVisible(False)
                    else:
                        # Ensure Style option exists for LLM providers
                        if style_idx == -1:
                            try:
                                self.mode_combo.addItem("Style")
                            except Exception:
                                pass
            except Exception as e:
                logger.debug(f"Provider capability enforcement failed: {e}")
        except Exception as e:
            logger.debug(f"Failed to update API state/UI: {e}")

    def show_loading(self, position: tuple | None = None):
        """Show a minimal loading state at an optional absolute position."""
        try:
            logger.info("OverlayWindow: show_loading() called")
            if position:
                x, y = position
                self.move(x, y)

            self.original_text.setPlainText("Loading...")
            self.show()
            self.raise_()
            self.activateWindow()
            logger.debug("Loading overlay shown")
        except Exception as e:
            logger.error(f"Error in show_loading: {e}")

    def geometry_string(self) -> str:
        """Return a geometry string similar to Tkinter 'WxH+X+Y' for logs."""
        try:
            g = self.geometry()
            return f"{g.width()}x{g.height()}+{g.x()}+{g.y()}"
        except Exception:
            return "0x0+0+0"

    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape:
            logger.info("Escape key pressed, dismissing overlay")
            self.dismiss()
        else:
            super().keyPressEvent(event)

    def _open_translator_settings(self):
        """Show the translator-specific settings dialog."""
        try:
            if self._translator_settings_dialog is None:
                dialog = TranslatorSettingsDialog(self)
                dialog.destroyed.connect(lambda: setattr(self, "_translator_settings_dialog", None))
                self._translator_settings_dialog = dialog

            dialog = self._translator_settings_dialog
            if dialog.isHidden():
                dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        except Exception as e:
            logger.error(f"Failed to open translator settings dialog: {e}")

    def _update_layout(self):
        """Updates the entire UI layout based on current view settings."""
        settings = config_service.get_settings()
        compact = getattr(settings, "compact_view", False)
        autohide = getattr(settings, "overlay_side_buttons_autohide", False)

        # Cache settings for use in other methods
        self._cached_settings = settings

        for element in self.hideable_elements:
            element.setVisible(not compact)

        if hasattr(self, 'language_spacer'):
            size = 34 if compact else 0
            self.language_spacer.changeSize(size, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        # Configure panel widgets instead of manual per-panel logic
        self.original_panel.configure(compact, autohide)
        self.translated_panel.configure(compact, autohide)

        # Re-apply API state after layout changes to override any button style resets
        self._update_api_state_and_ui()

        logger.debug(f"Layout updated: compact={compact}, autohide={autohide}")

    def eventFilter(self, obj, event):
        """Handle events for child widgets, including hover for compact buttons."""
        if not hasattr(self, "original_text"):
            return super().eventFilter(obj, event)

        # PanelWidget handles its own hover-based autohide; no-op here

        if obj == self.close_btn:
            if event.type() == QEvent.Type.Enter:
                self.close_btn.setIcon(self.close_icon_hover)
            elif event.type() == QEvent.Type.Leave:
                self.close_btn.setIcon(self.close_icon_normal)

        return super().eventFilter(obj, event)

    def show_overlay(self, original_text: str = "", translated_text: str = "", position: tuple[int, int] | None = None):
        """Show the overlay with specified content."""
        logger.info("Showing overlay window")
        # Ensure button/state reflect API key presence at time of showing
        self._update_api_state_and_ui()

        settings = config_service.get_settings()
        current_state = getattr(settings, "ocr_auto_swap_en_ru", True)
        self.auto_swap_checkbox.setChecked(current_state)

        self._update_layout()
        # Re-assert API state after layout restyles
        self._update_api_state_and_ui()

        self.original_text.setPlainText(original_text)
        self.translated_text.setPlainText(translated_text)

        # Update reader button state after setting text
        self._update_reader_button_state()

        self.show()
        self.raise_()
        self.activateWindow()
        logger.debug("Overlay window shown and activated")

    def _show_button_feedback(self, button: QPushButton):
        """Show visual feedback on a button by displaying a green checkmark for 1.2 seconds."""
        try:
            prev_icon = button.icon()
            prev_text = button.text()

            try:
                button.setIcon(self.icon_check_green)
            except Exception:
                pass
            button.setText("")
            QTimer.singleShot(
                1200,
                lambda p_icon=prev_icon, p_text=prev_text: (
                    button.setIcon(p_icon),
                    button.setText(p_text),
                ),
            )
        except Exception as e:
            logger.error(f"Failed to show button feedback: {e}")

    def _copy_text_to_clipboard(self, text_widget: QTextEdit, button: QPushButton, text_name: str):
        """Copy text from a QTextEdit to clipboard and provide visual feedback on a button."""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(text_widget.toPlainText())
            logger.info(f"{text_name} text copied to clipboard")
            self._show_button_feedback(button)
        except Exception as e:
            logger.error(f"Failed to copy {text_name} text: {e}")

    def _copy_original_to_clipboard(self):
        """Copy original text to clipboard."""
        self._copy_text_to_clipboard(self.original_text, self.copy_original_btn, "Original")

    def _clear_text(self, text_widget: QTextEdit, button: QPushButton, label_to_reset: Optional[QLabel] = None):
        """Clear text from a QTextEdit widget and optionally reset a label, with visual feedback on button."""
        try:
            text_widget.clear()
            if label_to_reset:
                label_to_reset.setText("Language: —")
            self._show_button_feedback(button)
        except Exception as e:
            logger.error(f"Failed to clear text: {e}")

    def _clear_original_text(self):
        """Clear original text area and reset language label."""
        self._clear_text(self.original_text, self.clear_original_btn, self.detected_lang_label)
        self.status_label.setText("")
        # Re-assert API state warning if needed
        self._update_api_state_and_ui()

    def _clear_translated_text(self):
        """Clear translated text area."""
        self._clear_text(self.translated_text, self.clear_translated_btn)
        self.status_label.setText("")
        # Re-assert API state warning if needed
        self._update_api_state_and_ui()


    def _on_original_text_changed(self):
        """Update detected language label when original text changes."""
        try:
            text = self.original_text.toPlainText().strip()
            if not text:
                self.detected_lang_label.setText("Language: —")
                return

            lang_code = detect_language(text)
            if lang_code:
                lang_name = get_language_name(lang_code)
                self.detected_lang_label.setText(f"Language: {lang_name}")
            else:
                self.detected_lang_label.setText("Language: —")
        except Exception as e:
            logger.debug(f"Failed to update detected language label: {e}")

    def _update_reader_button_state(self):
        """Update the reader mode button state based on translated text presence."""
        try:
            translated_text = self.translated_text.toPlainText().strip()
            self.reader_mode_btn.setEnabled(bool(translated_text))
        except Exception as e:
            logger.debug(f"Failed to update reader button state: {e}")

    def _on_auto_swap_changed(self, state):
        """Persist OCR auto-swap checkbox state to settings when changed."""
        enabled = bool(state)
        if config_service.set_setting("ocr_auto_swap_en_ru", enabled):
            logger.info(f"OCR auto-swap setting updated: {enabled}")

    def _on_source_changed(self, index: int):
        """User changed Source combo -> persist ui_source_language."""
        code = self.source_combo.currentData()
        if config_service.set_setting("ui_source_language", code):
            logger.info(f"UI source language updated: {code}")

    def _on_target_changed(self, index: int):
        """User changed Target combo -> persist ui_target_mode/ui_target_language."""
        data = self.target_combo.currentData()
        updates = {"ui_target_mode": "explicit", "ui_target_language": data}
        try:
            config_service.update_settings(updates)
            logger.info(f"UI target updated: mode=explicit, lang={data}")
        except Exception as e:
            logger.error(f"Failed to persist target selection: {e}")

    def _perform_language_swap(self):
        """Perform the language swap logic and persist changes."""
        if not hasattr(self, "source_combo") or not hasattr(self, "target_combo"):
            return

        src_data = self.source_combo.currentData()
        tgt_data = self.target_combo.currentData()

        if src_data == "auto":
            new_source = tgt_data
            new_target = tgt_data
            self._set_combo_data(self.source_combo, new_source)
            logger.info(f"Swap with 'auto' source: source set to '{new_source}'")
        else:
            new_source = tgt_data
            new_target = src_data
            self._set_combo_data(self.source_combo, new_source)
            self._set_combo_data(self.target_combo, new_target)
            logger.info(f"Swapped languages: source='{new_source}', target='{new_target}'")

        # Common settings update logic
        updates = {
            "ui_source_language": new_source,
            "ui_target_mode": "explicit",
            "ui_target_language": new_target,
        }
        try:
            config_service.update_settings(updates)
        except Exception as e:
            logger.error(f"Failed to persist swap: {e}")

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

    def _on_swap_clicked(self):
        """Swap button behavior"""
        self._perform_language_swap()

    def _setup_worker(self, worker_class, *args):
        """Generic method to set up and start a worker in a background thread."""
        worker = worker_class(*args)
        thread = QThread()
        worker.moveToThread(thread)

        worker.finished.connect(self._on_translation_finished)
        worker.error.connect(self._on_translation_error)
        thread.started.connect(worker.run)

        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start()
        return worker, thread



    def _on_translate_clicked(self):
        """Translate or Style the text from the original_text field based on mode."""
        text = self.original_text.toPlainText().strip()
        if not text:
            logger.info("Translate/Style button clicked with empty original_text")
            return

        # Guard: API must be ready (key configured/valid)
        ready, _msg = self._is_api_ready()
        if not ready:
            self._update_api_state_and_ui()
            return

        # Record start time and update status
        import time
        self._translation_start_time = time.time()
        self.status_label.setText("Request sent...")

        settings = self._cached_settings
        compact = getattr(settings, "compact_view", False)
        is_style = hasattr(self, "mode_combo") and (self.mode_combo.currentText().strip().lower() == "style")

        if self.translate_btn:
            self.translate_btn.setEnabled(False)
            prev_text = self.translate_btn.text()
            if not compact:
                self.translate_btn.setText("  Styling..." if is_style else "  Translating...")
                QApplication.processEvents()
        else:
            prev_text = "Translate" if not is_style else "Style"

        if is_style:
            # Resolve selected style name
            style_name = ""
            try:
                style_name = self.style_combo.currentText().strip()
            except Exception:
                pass
            if not style_name:
                # fallback to first configured style if available
                try:
                    styles = getattr(settings, "text_styles", []) or []
                    if styles:
                        style_name = (styles[0].get("name") or "Improve") if isinstance(styles[0], dict) else str(styles[0])
                except Exception:
                    style_name = "Improve"

            logger.debug(f"Style mode selected. Style='{style_name}'")
            self._translation_prev_text = prev_text
            self._style_worker, self._style_thread = self._setup_worker(StyleWorker, text, style_name)
            return

        # Translate mode
        ui_source_lang = self.source_combo.currentData()
        ui_target_lang = self.target_combo.currentData()
        logger.debug(f"Translate mode selected with UI languages: source='{ui_source_lang}', target='{ui_target_lang}'")
        self._translation_prev_text = prev_text
        self._translation_worker, self._translation_thread = self._setup_worker(TranslationWorker, text, ui_source_lang, ui_target_lang)

    def _on_translation_finished(self, success: bool, result: str):
        """Handle completion of background translation."""
        try:
            if success:
                self.translated_text.setPlainText(result)
                logger.info("Translation completed and inserted into translated_text")
            else:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Translation failed", f"Translation error: {result}")
                logger.error(f"Translation failed: {result}")
        finally:
            # Update status with completion time
            if self._translation_start_time is not None:
                import time
                elapsed = time.time() - self._translation_start_time
                self.status_label.setText(f"Completed in {elapsed:.1f}s")
                self._translation_start_time = None
            else:
                self.status_label.setText("")

            settings = self._cached_settings
            compact = getattr(settings, "compact_view", False)
            prev_text = getattr(self, "_translation_prev_text", "Translate")
            if self.translate_btn:
                self.translate_btn.setEnabled(True)
                if not compact:
                    self.translate_btn.setText(prev_text)
            if hasattr(self, "_translation_prev_text"):
                delattr(self, "_translation_prev_text")

    def _on_translation_error(self, error_message: str):
        """Handle error from background translation."""
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Translation failed", f"Translation error: {error_message}")
            logger.error(f"Translation failed: {error_message}")
        finally:
            # Update status with error indication
            if self._translation_start_time is not None:
                import time
                elapsed = time.time() - self._translation_start_time
                self.status_label.setText(f"Failed after {elapsed:.1f}s")
                self._translation_start_time = None
            else:
                self.status_label.setText("Failed")
            # UX: emphasize error state in red (same styling priority as key-missing)
            try:
                self.status_label.setStyleSheet("color: #c62828; font-weight: 600; font-size: 10px;")
            except Exception:
                pass

            settings = self._cached_settings
            compact = getattr(settings, "compact_view", False)
            prev_text = getattr(self, "_translation_prev_text", "Translate")
            if self.translate_btn:
                self.translate_btn.setEnabled(True)
                if not compact:
                    self.translate_btn.setText(prev_text)
            if hasattr(self, "_translation_prev_text"):
                delattr(self, "_translation_prev_text")

            # Re-evaluate API readiness in case the key was changed mid-flight; also reapplies disabled visuals if needed
            try:
                self._update_api_state_and_ui()
            except Exception:
                pass

    def _copy_translated_to_clipboard(self):
        """Copy translated text to clipboard."""
        self._copy_text_to_clipboard(self.translated_text, self.copy_translated_btn, "Translated")

    def _on_reader_mode_clicked(self):
        """Handle reader mode button click."""
        try:
            translated_text = self.translated_text.toPlainText().strip()
            if not translated_text:
                logger.info("Reader mode clicked with empty translated text")
                return

            from ..services.ui_service import get_ui_service
            ui_service = get_ui_service()
            if ui_service:
                ui_service.show_reader_window(translated_text)
                logger.info("Reader mode activated with translated text")
            else:
                logger.error("UI service not available")
        except Exception as e:
            logger.error(f"Failed to open reader mode: {e}")


    def dismiss(self) -> None:
        """Dismiss the overlay window, ensuring child dialogs are closed first."""
        logger.info("Dismissing overlay window")
        if self._translator_settings_dialog:
            try:
                self._translator_settings_dialog.close()
            except Exception as e:
                logger.warning(f"Could not close translator settings dialog: {e}")
        
        super().dismiss()
        logger.debug("Overlay window dismissed")

    def is_overlay_visible(self) -> bool:
        """Check if overlay is currently visible."""
        return self.isVisible()