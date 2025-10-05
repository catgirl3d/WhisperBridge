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
    QFrame,
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


class OverlayWindow(StyledOverlayWindow):
    """Overlay window for displaying translation results."""

    def __init__(self):
        """Initialize the overlay window."""
        super().__init__(title="Translator")
        self._translator_settings_dialog = None
        self._programmatic_combo_change = False

        self._init_compact_buttons()
        self._init_ui()
        self._init_language_controls()
        self._connect_signals()

        logger.debug("OverlayWindow initialized")

    def _init_ui(self):
        """Initialize the main UI widgets."""
        self.original_label = QLabel("Original:")
        self.original_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))

        self.hideable_elements = []

        info_row = self._create_info_row()
        language_row = self._create_language_row()

        self.original_text = self._create_text_edit("Recognized text will appear here...")
        self.translated_text = self._create_text_edit("Translation will appear here...")

        self.original_container = self._create_text_panel(self.original_text, self.original_compact_buttons)
        self.translated_container = self._create_text_panel(self.translated_text, self.translated_compact_buttons)

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
        layout.addWidget(self.original_container)
        layout.addSpacing(6)
        layout.addLayout(self.btn_row_orig)
        layout.addWidget(self.translated_label)
        layout.addWidget(self.translated_container)
        layout.addSpacing(6)
        layout.addLayout(self.btn_row_tr)
        layout.addLayout(self.footer_row)

        # Set stretch factors
        layout.setStretch(layout.indexOf(self.original_container), 1)
        layout.setStretch(layout.indexOf(self.translated_container), 1)

        self.hideable_elements.extend([info_row, language_row, self.original_label, self.btn_row_orig, self.translated_label, self.btn_row_tr, self.footer_row])
        self.add_settings_button(self._open_translator_settings)

    def _create_text_panel(self, text_edit: QTextEdit, buttons: list[QPushButton]) -> QFrame:
        """Creates a container with a text edit area and a side panel of buttons."""
        container = QFrame()
        container.setFrameStyle(QFrame.Shape.NoFrame)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(text_edit, 1)

        buttons_widget = QFrame()
        buttons_widget.setFrameStyle(QFrame.Shape.NoFrame)
        buttons_widget.setFixedWidth(28)
        buttons_layout = QVBoxLayout(buttons_widget)
        buttons_layout.setSpacing(3)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.addStretch()
        for btn in buttons:
            buttons_layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        buttons_layout.addStretch()
        layout.addWidget(buttons_widget)

        if text_edit is self.original_text:
            self.original_buttons_widget = buttons_widget
        else:
            self.translated_buttons_widget = buttons_widget

        container.setMouseTracking(True)
        container.installEventFilter(self)
        buttons_widget.setMouseTracking(True)
        buttons_widget.installEventFilter(self)

        return container

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
        self.close_btn.clicked.connect(self.dismiss)
        self.close_btn.installEventFilter(self)

        # Connect compact buttons
        self.compact_translate_btn.clicked.connect(self._on_translate_clicked)
        self.compact_clear_original_btn.clicked.connect(self._clear_original_text)
        self.compact_copy_original_btn.clicked.connect(self._copy_original_to_clipboard)
        self.compact_clear_translated_btn.clicked.connect(self._clear_translated_text)
        self.compact_copy_translated_btn.clicked.connect(self._copy_translated_to_clipboard)

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
            "QPushButton { background-color: #4CAF50; color: white; border: none; border-radius: 4px; font-weight: bold; padding: 0px; margin: 0px; } QPushButton:hover { background-color: #45a049; }"
        )

        self.translated_compact_buttons = [
            self._create_compact_button(qta.icon("fa5s.eraser", color="black"), "Clear translated text"),
            self._create_compact_button(qta.icon("fa5.copy", color="black"), "Copy translated text"),
        ]

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
        btn.setStyleSheet("QPushButton { padding: 0px; margin: 0px; }")
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

        settings = config_service.get_settings()
        ui_source_language = getattr(settings, "ui_source_language", "en")
        if not _set_combo_by_data(self.source_combo, ui_source_language):
            _set_combo_by_data(self.source_combo, "en")

        ui_target_language = getattr(settings, "ui_target_language", "en")
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

        for element in self.hideable_elements:
            if isinstance(element, QLayout):
                for i in range(element.count()):
                    item = element.itemAt(i)
                    if item and item.widget():
                        item.widget().setVisible(not compact)
            else:
                element.setVisible(not compact)

        if not compact:
            self.original_buttons_widget.setFixedWidth(0)
            self.translated_buttons_widget.setFixedWidth(0)
        else:
            if autohide:
                self.original_buttons_widget.setFixedWidth(1)
                self.translated_buttons_widget.setFixedWidth(1)
                for btn in self.original_compact_buttons + self.translated_compact_buttons:
                    if btn:
                        btn.setVisible(False)
            else:
                self.original_buttons_widget.setFixedWidth(28)
                self.translated_buttons_widget.setFixedWidth(28)
                for btn in self.original_compact_buttons + self.translated_compact_buttons:
                    if btn:
                        btn.setVisible(True)
        logger.debug(f"Layout updated: compact={compact}, autohide={autohide}")

    def eventFilter(self, obj, event):
        """Handle events for child widgets, including hover for compact buttons."""
        if not hasattr(self, "original_text"):
            return super().eventFilter(obj, event)

        settings = config_service.get_settings()
        compact = getattr(settings, "compact_view", False)
        autohide = getattr(settings, "overlay_side_buttons_autohide", False)

        if compact and autohide:
            panel, buttons, container = None, None, None
            if obj is self.original_container or obj is self.original_buttons_widget:
                panel, buttons, container = self.original_buttons_widget, self.original_compact_buttons, self.original_container
            elif obj is self.translated_container or obj is self.translated_buttons_widget:
                panel, buttons, container = self.translated_buttons_widget, self.translated_compact_buttons, self.translated_container

            if panel and buttons and container:
                if event.type() == QEvent.Type.Enter:
                    panel.setFixedWidth(28)
                    for btn in buttons:
                        if btn:
                            btn.setVisible(True)
                elif event.type() == QEvent.Type.Leave:
                    if not panel.underMouse() and not container.underMouse():
                        panel.setFixedWidth(1)
                        for btn in buttons:
                            if btn:
                                btn.setVisible(False)

        if obj == self.close_btn:
            if event.type() == QEvent.Type.Enter:
                self.close_btn.setIcon(self.close_icon_hover)
            elif event.type() == QEvent.Type.Leave:
                self.close_btn.setIcon(self.close_icon_normal)

        return super().eventFilter(obj, event)

    def show_overlay(self, original_text: str = "", translated_text: str = "", position: tuple[int, int] | None = None):
        """Show the overlay with specified content."""
        logger.info("Showing overlay window")

        settings = config_service.get_settings()
        current_state = getattr(settings, "ocr_auto_swap_en_ru", True)
        self.auto_swap_checkbox.setChecked(current_state)

        self._update_layout()

        self.original_text.setPlainText(original_text)
        self.translated_text.setPlainText(translated_text)

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
            logger.error(f"Failed to copy {text_name} text: {e}")

    def _copy_original_to_clipboard(self):
        """Copy original text to clipboard."""
        self._copy_text_to_clipboard(self.original_text, self.copy_original_btn, "Original")

    def _clear_original_text(self):
        """Clear original text area and reset language label."""
        try:
            self.original_text.clear()
            self.detected_lang_label.setText("Language: —")
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

    def _on_auto_swap_changed(self, state):
        """Persist OCR auto-swap checkbox state to settings when changed."""
        enabled = bool(state)
        if config_service.set_setting("ocr_auto_swap_en_ru", enabled):
            logger.info(f"OCR auto-swap setting updated: {enabled}")

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
        if config_service.set_setting("ui_source_language", code):
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

    def _setup_translation_worker(self, text, ui_source_lang, ui_target_lang, prev_text):
        """Set up and start the translation worker in a background thread."""
        self._translation_worker = TranslationWorker(text, ui_source_lang, ui_target_lang)
        self._translation_thread = QThread()
        self._translation_worker.moveToThread(self._translation_thread)

        self._translation_prev_text = prev_text
        self._translation_worker.finished.connect(self._on_translation_finished)
        self._translation_thread.started.connect(self._translation_worker.run)

        self._translation_worker.finished.connect(self._translation_thread.quit)
        self._translation_worker.finished.connect(self._translation_worker.deleteLater)
        self._translation_thread.finished.connect(self._translation_thread.deleteLater)

        self._translation_thread.start()


    def _on_translate_clicked(self):
        """Translate the text from the original_text field."""
        text = self.original_text.toPlainText().strip()
        if not text:
            logger.info("Translate button clicked with empty original_text")
            return

        if self.translate_btn:
            self.translate_btn.setEnabled(False)
            prev_text = self.translate_btn.text()
            self.translate_btn.setText("  Translating...")
            QApplication.processEvents()
        else:
            prev_text = "Translate"

        # Collect UI language preferences
        ui_source_lang = self.source_combo.currentData()
        ui_target_lang = self.target_combo.currentData()

        logger.debug(f"Translate clicked with UI languages: source='{ui_source_lang}', target='{ui_target_lang}'")

        self._setup_translation_worker(text, ui_source_lang, ui_target_lang, prev_text)

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
            prev_text = getattr(self, "_translation_prev_text", "Translate")
            if self.translate_btn:
                self.translate_btn.setEnabled(True)
                self.translate_btn.setText(prev_text)
            if hasattr(self, "_translation_prev_text"):
                delattr(self, "_translation_prev_text")

    def _copy_translated_to_clipboard(self):
        """Copy translated text to clipboard."""
        self._copy_text_to_clipboard(self.translated_text, self.copy_translated_btn, "Translated")

    def show_result(self, original_text: str, translated_text: str | None = None):
        """Show the overlay with OCR result."""
        self.show_overlay(original_text, translated_text or "")

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