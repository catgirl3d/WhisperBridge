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
from PySide6.QtGui import QFont, QIcon, QKeyEvent, QPixmap, QPainter, QPen, QColor
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
from ..utils.language_utils import detect_language, get_language_name, get_supported_languages
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
        self.original_side_buttons = None
        self.translated_side_buttons = None
        self.btn_row_orig = None
        self.btn_row_tr = None

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

        self.translated_label = QLabel("Translation:")
        self.translated_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.translated_label.setStyleSheet("padding-bottom: 6px;")

        self.translate_btn = self._create_button(text="  Translate", size=(120, 28))
        # Ensure stylesheet targeting and identity remain intact
        self.translate_btn.setObjectName("translateButton")
        # Set icon for translate button
        img_path = Path(__file__).parent.parent / "assets" / "icons" / "translation-icon.png"
        self.translate_btn.setIcon(QIcon(QPixmap(str(img_path))))
        self.translate_btn.setIconSize(QSize(14, 14))
        # preserve original display text for restore
        self._translate_original_text = self.translate_btn.text()
        self.reader_mode_btn = self._create_button(text="", tooltip="Open text in reader mode for comfortable reading")
        # Set icon for reader mode button
        img_path = Path(__file__).parent.parent / "assets" / "icons" / "book_black.png"
        self.reader_mode_btn.setIcon(QIcon(QPixmap(str(img_path))))
        self.reader_mode_btn.setIconSize(QSize(14, 14))
        # preserve original display text for restore
        self._reader_original_text = self.reader_mode_btn.text()
        self.reader_mode_btn.setEnabled(False)  # Disable by default if no translated text
        self.reader_mode_btn.clicked.connect(self._on_reader_mode_clicked)
        self.clear_original_btn = self._create_button(text="", icon=qta.icon("fa5s.eraser", color="black"), size=(40, 28), tooltip="Clear text")
        self.copy_original_btn = self._create_button(text="", icon=qta.icon("fa5.copy", color="black"), size=(40, 28), tooltip="Copy text")
        self.clear_translated_btn = self._create_button(text="", icon=qta.icon("fa5s.eraser", color="black"), size=(40, 28), tooltip="Clear text")
        self.copy_translated_btn = self._create_button(text="", icon=qta.icon("fa5.copy", color="black"), size=(40, 28), tooltip="Copy text")

        self.original_buttons = [self.translate_btn, self.clear_original_btn, self.copy_original_btn]
        self.translated_buttons = [self.reader_mode_btn, self.clear_translated_btn, self.copy_translated_btn]

        self.original_container = self._create_text_panel(self.original_text)
        self.translated_container = self._create_text_panel(self.translated_text)

        self.footer_row, self.close_btn = self._create_footer()

        # Assemble layout
        layout = self.content_layout
        layout.addLayout(info_row)
        layout.addLayout(language_row)
        layout.addWidget(self.original_container)
        layout.addWidget(self.translated_label)
        layout.addWidget(self.translated_container)
        layout.addLayout(self.footer_row)

        # Set stretch factors
        layout.setStretch(layout.indexOf(self.original_container), 1)
        layout.setStretch(layout.indexOf(self.translated_container), 1)

        self.hideable_elements.extend([info_row, self.original_label, self.translated_label, self.footer_row])
        self.add_settings_button(self._open_translator_settings)

    def _create_text_panel(self, text_edit: QTextEdit) -> QFrame:
        """Creates a container with a text edit area."""
        container = QFrame()
        container.setFrameStyle(QFrame.Shape.NoFrame)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(text_edit, 1)

        container.setMouseTracking(True)
        container.installEventFilter(self)

        return container

    def _connect_signals(self):
        """Connect all UI signals to their slots."""
        self.auto_swap_checkbox.stateChanged.connect(self._on_auto_swap_changed)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        self.swap_btn.clicked.connect(self._on_swap_clicked)
        self.original_text.textChanged.connect(self._on_original_text_changed)
        self.translated_text.textChanged.connect(self._update_reader_button_state)
        if self.translate_btn:
            self.translate_btn.clicked.connect(self._on_translate_clicked)
        self.clear_original_btn.clicked.connect(self._clear_original_text)
        self.copy_original_btn.clicked.connect(self._copy_original_to_clipboard)
        self.clear_translated_btn.clicked.connect(self._clear_translated_text)
        self.copy_translated_btn.clicked.connect(self._copy_translated_to_clipboard)
        self.close_btn.clicked.connect(self.dismiss)
        self.close_btn.installEventFilter(self)


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
            combo.setFixedSize(125, 28)
            combo.setIconSize(QSize(25, 25))
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            combo.setStyleSheet("QComboBox { background-color: #fff; color: #111111; padding: 0px; padding-left: 8px; }")

        self.swap_btn = QPushButton()
        self.swap_btn.setFixedSize(35, 28)
        img_path = Path(__file__).parent.parent / "assets" / "icons" / "arrows-exchange.png"
        self.swap_btn.setIcon(QIcon(QPixmap(str(img_path))))
        self.swap_btn.setIconSize(QSize(20, 24))

        language_row.addWidget(self.source_combo)
        language_row.addWidget(self.swap_btn)
        language_row.addWidget(self.target_combo)

        # Spacer for compact mode button panel
        self.language_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        language_row.addItem(self.language_spacer)

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
        """Apply styling to a button based on compact mode."""
        if compact:
            button.setText("")
            button.setFixedSize(24, 24)
            button.setIconSize(QSize(15, 15))
            if button == self.translate_btn:
                button.setIconSize(QSize(12, 12))
                button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; border: none; border-radius: 4px; font-weight: bold; padding: 0px; margin: 0px; } QPushButton:hover { background-color: #45a049; }")
            elif button == self.reader_mode_btn:
                button.setFixedSize(24, 24)
                button.setIconSize(QSize(17, 17))
                button.setStyleSheet("QPushButton { background-color: #2196F3; color: white; border: none; border-radius: 4px; font-weight: bold; padding: 0px; margin: 0px; } QPushButton:hover { background-color: #1976D2; }")
                button.setIcon(QIcon(QPixmap(str(Path(__file__).parent.parent / "assets" / "icons" / "book_white.png"))))
            else:
                button.setStyleSheet("QPushButton { padding: 0px; margin: 0px; }")
        else:
            if button == self.translate_btn:
                button.setText(self._translate_original_text if hasattr(self, "_translate_original_text") else "  Translate")
                button.setFixedSize(120, 28)
                button.setIconSize(QSize(14, 14))
                button.setStyleSheet("")
            elif button == self.reader_mode_btn:
                button.setText(self._reader_original_text if hasattr(self, "_reader_original_text") else "Reader")
                button.setFixedSize(40, 28)
                button.setIconSize(QSize(19, 19))
                button.setIcon(QIcon(QPixmap(str(Path(__file__).parent.parent / "assets" / "icons" / "book_black.png"))))
                button.setStyleSheet("")
            else:
                button.setFixedSize(40, 28)
                button.setIconSize(QSize(16, 16))
                button.setStyleSheet("")

    def _create_footer(self):
        """Create the footer row with the close button."""
        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFixedSize(86, 28)
        close_btn.setObjectName("closeButton")
        self.close_icon_normal = qta.icon("fa5s.times", color="black")
        self.close_icon_hover = qta.icon("fa5s.times", color="white")
        close_btn.setIcon(self.close_icon_normal)
        close_btn.setIconSize(QSize(16, 16))
        footer_row.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        return footer_row, close_btn

    def _create_side_buttons_widget(self):
        """Create a side panel widget with vertical layout for buttons."""
        widget = QFrame()
        widget.setFrameStyle(QFrame.Shape.NoFrame)
        widget.setFixedWidth(28)
        layout = QVBoxLayout(widget)
        layout.setSpacing(3)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        layout.addStretch()
        widget.setMouseTracking(True)
        widget.installEventFilter(self)
        return widget


    def _create_bordered_icon(self, icon_path: Path) -> QIcon:
        """Creates an icon with a 1px border drawn around it."""
        if not icon_path.exists():
            return QIcon()

        original_pixmap = QPixmap(str(icon_path))
        if original_pixmap.isNull():
            return QIcon()

        border_width = 1

        # New pixmap size is original + border on all 4 sides
        new_size = original_pixmap.size() + QSize(border_width * 2, border_width * 2)
        bordered_pixmap = QPixmap(new_size)
        bordered_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(bordered_pixmap)

        # Draw the original pixmap, offset by the border width
        painter.drawPixmap(border_width, border_width, original_pixmap)

        # Draw the border rectangle around the original pixmap's area
        pen = QPen(QColor("#cccccc"))  # Light gray border
        pen.setWidth(border_width)
        painter.setPen(pen)

        rect = bordered_pixmap.rect()
        # Adjust to be inside the pixmap. The pen is centered on the line.
        rect.adjust(0, 0, -border_width, -border_width)
        painter.drawRect(rect)

        painter.end()

        return QIcon(bordered_pixmap)

    def _init_language_controls(self):
        """Populate and configure language selection combos."""
        supported_languages = get_supported_languages()
        flags_path = Path(__file__).parent.parent / "assets" / "icons" / "flags"

        self.source_combo.insertItem(0, "Auto", userData="auto")

        for lang in supported_languages:
            icon_path = flags_path / lang.icon_name
            icon = self._create_bordered_icon(icon_path)

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

        # Hide/show main elements
        for element in self.hideable_elements:
            if isinstance(element, QLayout):
                for i in range(element.count()):
                    item = element.itemAt(i)
                    if item and item.widget():
                        item.widget().setVisible(not compact)
            else:
                element.setVisible(not compact)

        # Adjust language row spacer for compact mode
        if hasattr(self, 'language_spacer'):
            if compact:
                self.language_spacer.changeSize(34, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
            else:
                self.language_spacer.changeSize(0, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        # Handle buttons
        if compact:
            # Remove horizontal rows if exist and move buttons to side
            if self.btn_row_orig:
                for btn in self.original_buttons:
                    self.btn_row_orig.removeWidget(btn)
                idx = self.content_layout.indexOf(self.btn_row_orig) 
                if idx != -1:
                    self.content_layout.takeAt(idx)
                self.btn_row_orig = None
            if self.btn_row_tr:
                for btn in self.translated_buttons:
                    self.btn_row_tr.removeWidget(btn)
                idx = self.content_layout.indexOf(self.btn_row_tr)
                if idx != -1:
                    self.content_layout.takeAt(idx)
                self.btn_row_tr = None

            # Create side buttons if not exist and add buttons
            if not self.original_side_buttons:
                self.original_side_buttons = self._create_side_buttons_widget()
                orig_layout = self.original_container.layout()
                if orig_layout:
                    orig_layout.addWidget(self.original_side_buttons)
                side_layout = self.original_side_buttons.layout()
                if isinstance(side_layout, QVBoxLayout):
                    for btn in self.original_buttons:
                        side_layout.insertWidget(side_layout.count() - 1, btn, alignment=Qt.AlignmentFlag.AlignHCenter)
            if not self.translated_side_buttons:
                self.translated_side_buttons = self._create_side_buttons_widget()
                trans_layout = self.translated_container.layout()
                if trans_layout:
                    trans_layout.addWidget(self.translated_side_buttons)
                side_layout = self.translated_side_buttons.layout()
                if isinstance(side_layout, QVBoxLayout):
                    for btn in self.translated_buttons:
                        side_layout.insertWidget(side_layout.count() - 1, btn, alignment=Qt.AlignmentFlag.AlignHCenter)

            # Set widths and visibility
            self.original_side_buttons.setFixedWidth(28 if not autohide else 1)
            self.translated_side_buttons.setFixedWidth(28 if not autohide else 1)
            for btn in self.original_buttons + self.translated_buttons:
                btn.setVisible(not autohide)
                self._apply_button_style(btn, True)

        else:
            # Remove side buttons if exist and move buttons to rows
            if self.original_side_buttons:
                side_layout = self.original_side_buttons.layout()
                if side_layout:
                    for btn in self.original_buttons:
                        side_layout.removeWidget(btn)
                orig_layout = self.original_container.layout()
                if orig_layout:
                    orig_layout.removeWidget(self.original_side_buttons)
                # delete panel safely; buttons have parent=self so they won't be deleted
                self.original_side_buttons.deleteLater()
                self.original_side_buttons = None
            if self.translated_side_buttons:
                side_layout = self.translated_side_buttons.layout()
                if side_layout:
                    for btn in self.translated_buttons:
                        side_layout.removeWidget(btn)
                trans_layout = self.translated_container.layout()
                if trans_layout:
                    trans_layout.removeWidget(self.translated_side_buttons)
                # delete panel safely; buttons have parent=self so they won't be deleted
                self.translated_side_buttons.deleteLater()
                self.translated_side_buttons = None

            # Create horizontal rows if not exist
            if not self.btn_row_orig:
                self.btn_row_orig = QHBoxLayout()
                self.btn_row_orig.addStretch(1)
                self.btn_row_orig.addWidget(self.translate_btn)
                self.btn_row_orig.addWidget(self.clear_original_btn)
                self.btn_row_orig.addWidget(self.copy_original_btn)
                # Insert after original_container
                idx = self.content_layout.indexOf(self.original_container) + 1
                self.content_layout.insertLayout(idx, self.btn_row_orig)
            if not self.btn_row_tr:
                self.btn_row_tr = QHBoxLayout()
                self.btn_row_tr.addStretch(1)
                self.btn_row_tr.addWidget(self.reader_mode_btn)
                self.btn_row_tr.addWidget(self.clear_translated_btn)
                self.btn_row_tr.addWidget(self.copy_translated_btn)
                # Insert after translated_container
                idx = self.content_layout.indexOf(self.translated_container) + 1
                self.content_layout.insertLayout(idx, self.btn_row_tr)

            for btn in self.original_buttons + self.translated_buttons:
                self._apply_button_style(btn, False)

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
            if obj is self.original_container or obj is self.original_side_buttons:
                panel, buttons, container = self.original_side_buttons, self.original_buttons, self.original_container
            elif obj is self.translated_container or obj is self.translated_side_buttons:
                panel, buttons, container = self.translated_side_buttons, self.translated_buttons, self.translated_container

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

        # Update reader button state after setting text
        self._update_reader_button_state()

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
            for i in range(combo.count()):
                if combo.itemData(i) == data_value:
                    combo.setCurrentIndex(i)
                    break
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

        settings = config_service.get_settings()
        compact = getattr(settings, "compact_view", False)

        if self.translate_btn:
            self.translate_btn.setEnabled(False)
            if compact:
                prev_text = self.translate_btn.text()
            else:
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
            settings = config_service.get_settings()
            compact = getattr(settings, "compact_view", False)
            prev_text = getattr(self, "_translation_prev_text", "Translate")
            if self.translate_btn:
                self.translate_btn.setEnabled(True)
                if not compact:
                    self.translate_btn.setText(prev_text)
            if hasattr(self, "_translation_prev_text"):
                delattr(self, "_translation_prev_text")

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