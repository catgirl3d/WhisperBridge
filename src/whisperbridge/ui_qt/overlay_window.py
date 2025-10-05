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
from PySide6.QtGui import QFont, QIcon, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
    QVBoxLayout,
)

from ..services.config_service import config_service
from ..utils.language_utils import detect_language, get_language_name
from .styled_overlay_base import StyledOverlayWindow
from .workers import TranslationWorker


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

        # Compact view checkbox
        self.compact_view_checkbox = QCheckBox("Compact view")
        self.compact_view_checkbox.setToolTip("Hides labels and buttons for a more compact translator window")
        self.compact_view_checkbox.setChecked(self._safe_get_setting("compact_view", False))

        self.compact_view_checkbox.stateChanged.connect(self._on_compact_view_changed)
        layout.addWidget(self.compact_view_checkbox)

        close_button = QPushButton("Close")
        close_button.setFixedHeight(26)
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

    def _safe_get_setting(self, key, default):
        try:
            settings = config_service.get_settings()
            return getattr(settings, key, default)
        except Exception:
            return default

    def _on_compact_view_changed(self, state):
        """Persist compact view setting."""
        try:
            enabled = bool(state)
            config_service.set_setting("compact_view", enabled)
            logger.info(f"Compact view setting updated: {enabled}")
            # If parent overlay is visible, apply immediately
            parent = self.parent()
            if parent and hasattr(parent, "apply_compact_view"):
                # Use getattr to avoid static attribute errors from type checkers
                getattr(parent, "apply_compact_view")(enabled)
        except Exception as e:
            logger.error(f"Failed to save compact view setting: {e}")


class OverlayWindow(StyledOverlayWindow):
    """Overlay window for displaying translation results."""

    def __init__(self):
        """Initialize the overlay window."""
        super().__init__(title="Translator")
        self._translator_settings_dialog = None
        self._programmatic_combo_change = False
        self.active_buttons = None  # For unified compact button hiding

        self._init_compact_buttons()
        self._init_ui()
        self._init_language_controls()
        self._connect_signals()

        logger.debug("OverlayWindow initialized")

    def _safe_get_setting(self, key, default):
        """Safely get a setting from config_service."""
        try:
            settings = config_service.get_settings()
            return getattr(settings, key, default)
        except Exception:
            return default

    def _safe_set_setting(self, key, value):
        """Safely set a setting in config_service."""
        try:
            config_service.set_setting(key, value)
            return True
        except Exception as e:
            logger.error(f"Failed to set setting '{key}': {e}")
            return False

    def _init_ui(self):
        """Initialize the main UI widgets."""
        self.original_label = QLabel("Original:")
        self.original_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))

        self.hideable_elements = []

        info_row = self._create_info_row()
        language_row = self._create_language_row()

        self.original_text = self._create_text_edit("Recognized text will appear here...")
        self.translated_text = self._create_text_edit("Translation will appear here...")

        self.translated_label = QLabel("Translation:")
        self.translated_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.translated_label.setStyleSheet("padding-bottom: 6px;")

        self.btn_row_orig, self.translate_btn, self.clear_original_btn, self.copy_original_btn = self._create_button_row(is_original=True)
        self.btn_row_tr, _, self.clear_translated_btn, self.copy_translated_btn = self._create_button_row(is_original=False)

        self.footer_row, self.close_btn = self._create_footer()

        # Assemble layout
        layout = self.content_layout
        layout.addLayout(info_row)
        layout.addLayout(language_row)
        layout.addWidget(self.original_text)
        layout.addSpacing(6)
        layout.addLayout(self.btn_row_orig)
        layout.addWidget(self.translated_label)
        layout.addWidget(self.translated_text)
        layout.addSpacing(6)
        layout.addLayout(self.btn_row_tr)
        layout.addLayout(self.footer_row)

        # Set stretch factors
        layout.setStretch(layout.indexOf(self.original_text), 1)
        layout.setStretch(layout.indexOf(self.translated_text), 1)

        self.hideable_elements.extend([info_row, language_row, self.original_label, self.btn_row_orig, self.translated_label, self.btn_row_tr, self.footer_row])
        self.add_settings_button(self._open_translator_settings)

    def _connect_signals(self):
        """Connect all UI signals to their slots."""
        self.auto_swap_checkbox.stateChanged.connect(self._on_auto_swap_changed)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        self.swap_btn.clicked.connect(self._on_swap_clicked)
        self.original_text.textChanged.connect(self._on_original_text_changed)
        if self.translate_btn:
            self.translate_btn.clicked.connect(self._on_translate_clicked)
        self.clear_original_btn.clicked.connect(self._clear_original_text)
        self.copy_original_btn.clicked.connect(self._copy_original_to_clipboard)
        self.clear_translated_btn.clicked.connect(self._clear_translated_text)
        self.copy_translated_btn.clicked.connect(self._copy_translated_to_clipboard)
        self.close_btn.clicked.connect(self.hide_overlay)
        self.close_btn.installEventFilter(self)

        # Connect compact buttons
        self.compact_translate_btn.clicked.connect(self._on_translate_clicked)
        self.compact_clear_original_btn.clicked.connect(self._clear_original_text)
        self.compact_copy_original_btn.clicked.connect(self._copy_original_to_clipboard)
        self.compact_clear_translated_btn.clicked.connect(self._clear_translated_text)
        self.compact_copy_translated_btn.clicked.connect(self._copy_translated_to_clipboard)

        # Compact button event filters are installed in their factory
        self.original_text.viewport().setMouseTracking(True)
        self.translated_text.viewport().setMouseTracking(True)
        self.original_text.installEventFilter(self)
        self.translated_text.installEventFilter(self)

    def _create_info_row(self):
        """Create the top info row with language detection and auto-swap checkbox."""
        info_row = QHBoxLayout()
        info_row.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        self.detected_lang_label = QLabel("Language: —")
        self.detected_lang_label.setFixedWidth(120)
        info_row.addWidget(self.detected_lang_label)
        self.auto_swap_checkbox = QCheckBox("Auto-translate EN ↔ RU")
        self.auto_swap_checkbox.setToolTip("If enabled, English will be translated to Russian, and Russian to English")
        info_row.addWidget(self.auto_swap_checkbox)
        return info_row

    def _create_language_row(self):
        """Create the language selection row."""
        language_row = QHBoxLayout()
        language_row.addWidget(self.original_label)
        language_row.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self.source_combo = QComboBox()
        self.target_combo = QComboBox()
        for combo in [self.source_combo, self.target_combo]:
            combo.setFixedSize(120, 28)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)

        self.swap_btn = QPushButton()
        self.swap_btn.setFixedSize(35, 28)
        img_path = Path(__file__).parent.parent / "assets" / "icons" / "arrows-exchange.png"
        self.swap_btn.setIcon(QIcon(QPixmap(str(img_path))))
        self.swap_btn.setIconSize(QSize(20, 24))

        language_row.addWidget(self.source_combo)
        language_row.addWidget(self.swap_btn)
        language_row.addWidget(self.target_combo)
        return language_row

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
        """Generic button factory."""
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

    def _create_button_row(self, is_original):
        """Create a button row for original or translated text areas."""
        btn_row = QHBoxLayout()
        btn_row.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        translate_btn = None
        if is_original:
            translate_btn = self._create_button(text="  Translate", size=(120, 28))
            translate_btn.setObjectName("translateButton")
            btn_row.addWidget(translate_btn)

        clear_btn = self._create_button(text="", icon=qta.icon("fa5s.eraser", color="black"), tooltip="Clear text")
        copy_btn = self._create_button(text="", icon=qta.icon("fa5.copy", color="black"), tooltip="Copy text")
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(copy_btn)

        return btn_row, translate_btn, clear_btn, copy_btn

    def _create_footer(self):
        """Create the footer row with the close button."""
        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)
        close_btn = QPushButton("Close")
        close_btn.setFixedSize(86, 28)
        close_btn.setObjectName("closeButton")
        self.close_icon_normal = qta.icon("fa5s.times", color="black")
        self.close_icon_hover = qta.icon("fa5s.times", color="white")
        close_btn.setIcon(self.close_icon_normal)
        close_btn.setIconSize(QSize(16, 16))
        footer_row.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        return footer_row, close_btn

    def _init_compact_buttons(self):
        """Initialize all compact mode buttons."""
        self.original_compact_buttons = [
            self._create_compact_button(qta.icon("fa5s.chevron-right", color="white"), "Translate"),
            self._create_compact_button(qta.icon("fa5s.eraser", color="black"), "Clear original text"),
            self._create_compact_button(qta.icon("fa5.copy", color="black"), "Copy original text"),
        ]
        self.original_compact_buttons[0].setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border: none; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #45a049; }"
        )

        self.translated_compact_buttons = [
            self._create_compact_button(qta.icon("fa5s.eraser", color="black"), "Clear translated text"),
            self._create_compact_button(qta.icon("fa5.copy", color="black"), "Copy translated text"),
        ]

        # Single timer for all compact button groups
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._hide_active_buttons)

        # Assign to instance for easy access
        self.compact_translate_btn = self.original_compact_buttons[0]
        self.compact_clear_original_btn = self.original_compact_buttons[1]
        self.compact_copy_original_btn = self.original_compact_buttons[2]
        self.compact_clear_translated_btn = self.translated_compact_buttons[0]
        self.compact_copy_translated_btn = self.translated_compact_buttons[1]

    def _create_compact_button(self, icon, tooltip):
        """Factory for creating a compact button."""
        btn = self._create_button(parent=self, text="", icon=icon, size=(24, 24), tooltip=tooltip)
        btn.setIconSize(QSize(12, 12))
        btn.setVisible(False)
        btn.installEventFilter(self)
        return btn

    def _init_language_controls(self):
        """Populate and configure language selection combos."""
        codes_set = ["en", "ru", "ua", "de"]
        display_overrides = {}

        self.source_combo.insertItem(0, "Auto", userData="auto")
        for code in codes_set:
            display = display_overrides.get(code, get_language_name(code))
            self.source_combo.addItem(display, userData=code)
            self.target_combo.addItem(display, userData=code)

        self._programmatic_combo_change = True
        self.source_combo.blockSignals(True)
        self.target_combo.blockSignals(True)

        def _set_combo_by_data(combo: QComboBox, value: str):
            index = combo.findData(value)
            if index != -1:
                combo.setCurrentIndex(index)
                return True
            return False

        ui_source_language = self._safe_get_setting("ui_source_language", "en")
        if not _set_combo_by_data(self.source_combo, ui_source_language):
            _set_combo_by_data(self.source_combo, "en")

        ui_target_language = self._safe_get_setting("ui_target_language", "en")
        if not _set_combo_by_data(self.target_combo, ui_target_language):
            _set_combo_by_data(self.target_combo, "en")

        self.source_combo.blockSignals(False)
        self.target_combo.blockSignals(False)
        self._programmatic_combo_change = False

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
            logger.info("Escape key pressed, hiding overlay")
            self.hide_overlay()
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

    def apply_compact_view(self, enabled: bool):
        """Apply compact view by hiding/showing elements."""
        # Hide/show main elements
        for element in self.hideable_elements:
            if isinstance(element, QLayout):
                for i in range(element.count()):
                    item = element.itemAt(i)
                    if item and item.widget():
                        item.widget().setVisible(not enabled)
            else:
                element.setVisible(not enabled)

        # Hide all compact buttons when toggling the view
        for group in [self.original_compact_buttons, self.translated_compact_buttons]:
            for btn in group:
                if btn:
                    btn.setVisible(False)

        # Stop timer when view is disabled
        if not enabled:
            self.hide_timer.stop()

        logger.debug(f"Compact view applied: {enabled}")

    # --- Unified compact button helpers ---

    def _hide_active_buttons(self):
        """Hide the currently active compact button group."""
        if self.active_buttons:
            for w in self.active_buttons:
                if w:
                    w.setVisible(False)
            self.active_buttons = None

    def _show_compact_buttons_for_group(self, buttons, show, timer):
        """Unified logic for showing/hiding compact buttons for a group."""
        if show:
            # Hide any currently active buttons from previous group
            if self.active_buttons and self.active_buttons != buttons:
                for btn in self.active_buttons:
                    if btn:
                        btn.setVisible(False)
            self.active_buttons = buttons
            timer.stop()
            for btn in buttons:
                if btn:
                    btn.setVisible(True)
                    btn.raise_()
        else:
            self.active_buttons = buttons
            timer.start(100)

    def _position_compact_buttons_for_group(self, text_widget, buttons, right_margin=5, spacing=1):
        """Unified logic for positioning compact buttons for a group."""
        if not text_widget:
            return
        try:
            geo = text_widget.geometry()
            top_right = geo.topRight()

            current_x = top_right.x() - right_margin

            # Position buttons from right to left
            for btn in reversed(buttons):
                if btn:
                    button_width = btn.width()
                    current_x -= button_width
                    btn.move(current_x, top_right.y() + 5)

                    if btn.isVisible():
                        btn.raise_()

                    current_x -= spacing
        except Exception as e:
            logger.debug(f"_position_compact_buttons_for_group error: {e}")

    def eventFilter(self, obj, event):
        """Handle events for child widgets, including hover for compact buttons."""
        if not hasattr(self, "original_text"):
            return super().eventFilter(obj, event)

        if self.compact_view_enabled():
            self._handle_compact_button_hover(obj, event)

        if obj == self.close_btn:
            if event.type() == QEvent.Type.Enter:
                self.close_btn.setIcon(self.close_icon_hover)
            elif event.type() == QEvent.Type.Leave:
                self.close_btn.setIcon(self.close_icon_normal)

        if event.type() == QEvent.Type.Resize and obj in [self.original_text, self.translated_text]:
            self._position_all_compact_buttons()

        return super().eventFilter(obj, event)

    def _handle_compact_button_hover(self, obj, event):
        """Handle hover events for compact button groups."""
        if obj == self.original_text:
            buttons = self.original_compact_buttons
        elif obj == self.translated_text:
            buttons = self.translated_compact_buttons
        else:
            return

        if event.type() == QEvent.Type.Enter:
            self._show_compact_buttons_for_group(buttons, True, self.hide_timer)
        elif event.type() == QEvent.Type.Leave:
            self._show_compact_buttons_for_group(buttons, False, self.hide_timer)

    def compact_view_enabled(self):
        """Check if compact view is enabled."""
        return self._safe_get_setting("compact_view", False)

    def _position_all_compact_buttons(self):
        """Position all compact button groups."""
        self._position_compact_buttons_for_group(self.original_text, self.original_compact_buttons, right_margin=5, spacing=3)
        self._position_compact_buttons_for_group(self.translated_text, self.translated_compact_buttons, right_margin=5, spacing=3)

    def show_overlay(self, original_text: str = "", translated_text: str = "", position: tuple[int, int] | None = None):
        """Show the overlay with specified content.

        Args:
            original_text: Original text to display
            translated_text: Translated text to display
            position: (x, y) position for the window (ignored for fullscreen)
        """
        logger.info("Showing overlay window")

        # Update auto-swap checkbox state from settings each time the window is shown
        current_state = self._safe_get_setting("ocr_auto_swap_en_ru", True)
        self.auto_swap_checkbox.setChecked(current_state)

        # Apply compact view
        compact_enabled = self._safe_get_setting("compact_view", False)
        self.apply_compact_view(compact_enabled)

        self.original_text.setPlainText(original_text)
        self.translated_text.setPlainText(translated_text)

        # For fullscreen overlay, position is ignored
        self.show()
        self.raise_()
        self.activateWindow()
        logger.debug("Overlay window shown and activated")

    def _copy_text_to_clipboard(self, text_widget: QTextEdit, button: QPushButton, text_name: str):
        """Copy text from a QTextEdit to clipboard and provide visual feedback on a button."""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(text_widget.toPlainText())
            logger.info(f"{text_name} text copied to clipboard")

            prev_icon = button.icon()
            prev_text = button.text()

            try:
                button.setIcon(qta.icon("fa5s.check", color="green"))
            except Exception:
                pass  # Fallback to existing icon

            button.setText("")
            QTimer.singleShot(
                1200,
                lambda p_icon=prev_icon, p_text=prev_text: (
                    button.setIcon(p_icon),
                    button.setText(p_text),
                ),
            )
        except Exception as e:
            logger.error(f"Failed to copy {text_name} text: {e}")

    def _copy_original_to_clipboard(self):
        """Copy original text to clipboard."""
        self._copy_text_to_clipboard(self.original_text, self.copy_original_btn, "Original")

    def _clear_original_text(self):
        """Clear original text area and reset language label."""
        try:
            self.original_text.clear()
            try:
                self.detected_lang_label.setText("Language: —")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Failed to clear original text: {e}")

    def _clear_translated_text(self):
        """Clear translated text area."""
        try:
            self.translated_text.clear()
        except Exception as e:
            logger.error(f"Failed to clear translated text: {e}")

    def _clear_focused_text(self):
        """Clear text in the currently focused text area (if any)."""
        try:
            w = QApplication.focusWidget()
            if w is self.original_text:
                self._clear_original_text()
            elif w is self.translated_text:
                self._clear_translated_text()
        except Exception as e:
            logger.debug(f"Clear focused text failed: {e}")

    def _on_original_text_changed(self):
        """Update detected language label when original text changes and auto-update Source if needed."""
        try:
            text = self.original_text.toPlainText().strip()
            if not text:
                self.detected_lang_label.setText("Language: —")
                return

            # Detect language (may return codes like 'en', 'ru', etc.)
            lang_code = detect_language(text)
            if lang_code:
                lang_name = get_language_name(lang_code)
                # Show short name in Russian UI, e.g., "Язык: English"
                self.detected_lang_label.setText(f"Language: {lang_name}")

            else:
                self.detected_lang_label.setText("Language: —")
        except Exception as e:
            logger.debug(f"Failed to update detected language label: {e}")

    def _on_auto_swap_changed(self, state):
        """Persist OCR auto-swap checkbox state to settings when changed."""
        enabled = bool(state)
        if self._safe_set_setting("ocr_auto_swap_en_ru", enabled):
            logger.info(f"OCR auto-swap setting updated: {enabled}")

    # --- New handlers for language controls ---

    def _find_index_by_data(self, combo: QComboBox, data_value: str) -> int:
        for i in range(combo.count()):
            if combo.itemData(i) == data_value:
                return i
        return -1

    def _on_source_changed(self, index: int):
        """User changed Source combo -> persist ui_source_language."""
        if self._programmatic_combo_change:
            return
        code = self.source_combo.currentData()
        if self._safe_set_setting("ui_source_language", code):
            logger.info(f"UI source language updated: {code}")

    def _on_target_changed(self, index: int):
        """User changed Target combo -> persist ui_target_mode/ui_target_language."""
        if self._programmatic_combo_change:
            return
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
            # Special case: move target to source, keep target unchanged
            new_source = tgt_data
            new_target = tgt_data  # Keep as is
            self._set_combo_data(self.source_combo, new_source)
            updates = {
                "ui_source_language": new_source,
                "ui_target_mode": "explicit",
                "ui_target_language": new_target,
            }
            logger.info(f"Swap with 'auto' source: source set to '{new_source}'")
        else:
            # Standard swap
            new_source = tgt_data
            new_target = src_data
            self._set_combo_data(self.source_combo, new_source)
            self._set_combo_data(self.target_combo, new_target)
            updates = {
                "ui_source_language": new_source,
                "ui_target_mode": "explicit",
                "ui_target_language": new_target,
            }
            logger.info(f"Swapped languages: source='{new_source}', target='{new_target}'")

        try:
            config_service.update_settings(updates)
        except Exception as e:
            logger.error(f"Failed to persist swap: {e}")

    def _set_combo_data(self, combo, data_value):
        """Set combo to the index matching the data value, with signal blocking."""
        self._programmatic_combo_change = True
        try:
            combo.blockSignals(True)
            idx = self._find_index_by_data(combo, data_value)
            if idx != -1:
                combo.setCurrentIndex(idx)
        finally:
            combo.blockSignals(False)
            self._programmatic_combo_change = False

    def _on_swap_clicked(self):
        """Swap button behavior"""
        self._perform_language_swap()

    def _setup_translation_worker(self, text, source_lang, target_lang, prev_text):
        """Set up and start the translation worker in a background thread."""
        self._translation_worker = TranslationWorker(text, source_lang, target_lang)
        self._translation_thread = QThread()
        self._translation_worker.moveToThread(self._translation_thread)

        # Connect signals
        self._translation_prev_text = prev_text
        self._translation_worker.finished.connect(self._on_translation_finished)
        self._translation_thread.started.connect(self._translation_worker.run)

        # Cleanup
        self._translation_worker.finished.connect(self._translation_thread.quit)
        self._translation_worker.finished.connect(self._translation_worker.deleteLater)
        self._translation_thread.finished.connect(self._translation_thread.deleteLater)

        self._translation_thread.start()

    def _on_translate_clicked(self):
        """Translate the text from the original_text field and put result into translated_text using a background thread."""
        text = self.original_text.toPlainText().strip()
        if not text:
            logger.info("Translate button clicked with empty original_text")
            return

        # Disable button and provide feedback
        if self.translate_btn:
            self.translate_btn.setEnabled(False)
            prev_text = self.translate_btn.text()
            self.translate_btn.setText("  Translating...")
            QApplication.processEvents()
        else:
            prev_text = "Translate"

        # Determine detected language from input
        detected = detect_language(text) or "auto"

        # Read all relevant settings
        swap_enabled = self._safe_get_setting("ocr_auto_swap_en_ru", False)

        # Determine effective source language from Source combo
        source_lang = self.source_combo.currentData() or detected
        if source_lang == "auto":
            source_lang = detected

        # Determine effective target language with checkbox priority
        ui_target_language = self.target_combo.currentData()
        if ui_target_language is None:
            ui_target_language = self._safe_get_setting("ui_target_language", "en")

        if swap_enabled:
            if detected == "en":
                target_lang = "ru"
            elif detected == "ru":
                target_lang = "en"
            else:
                target_lang = ui_target_language
        else:
            target_lang = ui_target_language

        logger.debug(f"Translate clicked with detected='{detected}', source='{source_lang}', target='{target_lang}'")

        self._setup_translation_worker(text, source_lang, target_lang, prev_text)

    def _on_translation_finished(self, success: bool, result: str):
        """Handle completion of background translation."""
        try:
            if success:
                # This slot runs in the main (GUI) thread — safe to update widgets
                self.translated_text.setPlainText(result)
                logger.info("Translation completed and inserted into translated_text")
            else:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(self, "Translation failed", f"Translation error: {result}")
                logger.error(f"Translation failed: {result}")
        finally:
            # Use stored prev_text (set when translation started)
            prev_text = getattr(self, "_translation_prev_text", "Translate")
            if self.translate_btn:
                self.translate_btn.setEnabled(True)
                self.translate_btn.setText(prev_text)
            # Clean up stored value
            if hasattr(self, "_translation_prev_text"):
                delattr(self, "_translation_prev_text")

    def _copy_translated_to_clipboard(self):
        """Copy translated text to clipboard."""
        self._copy_text_to_clipboard(self.translated_text, self.copy_translated_btn, "Translated")

    def show_result(self, original_text: str, translated_text: str | None = None):
        """Show the overlay with OCR result.

        Args:
            original_text: OCR text to display
            translated_text: Translated text to display (optional)
        """
        self.show_overlay(original_text, translated_text or "")

    def hide_overlay(self):
        """Hide the overlay window."""
        logger.info("Hiding overlay window")
        # Close settings dialog if open
        try:
            if self._translator_settings_dialog:
                self._translator_settings_dialog.close()
        except Exception:
            pass
        # Delegate hiding/minibar handling to base dismiss
        super().dismiss()
        logger.debug("Overlay window hidden")

    # Using BaseWindow closeEvent from StyledOverlayWindow

    def dismiss(self):
        """Dismiss the overlay window."""
        self.hide_overlay()

    def is_overlay_visible(self) -> bool:
        """Check if overlay is currently visible.

        Returns:
            bool: True if overlay is visible
        """
        return self.isVisible()
