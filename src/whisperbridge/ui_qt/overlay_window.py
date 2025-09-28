"""
Overlay window implementation for Qt-based UI.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QApplication,
    QPushButton,
    QComboBox,
    QHBoxLayout,
    QSpacerItem,
    QSizePolicy,
    QCheckBox,
    QDialog,
)
from PySide6.QtCore import (
    Qt,
    QPoint,
    QRect,
    QTimer,
    QThread,
    Signal,
    QObject,
    QSize,
    QEvent,
)
from PySide6.QtGui import QFont, QKeyEvent, QPixmap, QIcon

import qtawesome as qta
from pathlib import Path

from loguru import logger
from ..services.config_service import config_service
from ..utils.language_utils import get_language_name, detect_language
from .minibar_overlay import MiniBarOverlay


class TranslatorSettingsDialog(QDialog):
    """Dialog for translator-specific settings (placeholder implementation)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translator Settings")
        self.setObjectName("TranslatorSettingsDialog")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        info_label = QLabel(
            "Translator-specific settings will be available here in a future update."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        close_button = QPushButton("Close")
        close_button.setFixedHeight(26)
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)


class OverlayWindow(QWidget):
    """Overlay window for displaying translation results."""

    def __init__(self):
        """Initialize the overlay window."""
        super().__init__()

        self._translator_settings_dialog = None

        # Configure window properties — frameless window with resize capability
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        # Set object name for CSS styling
        self.setObjectName("OverlayWindow")
        # Enable styled background for proper CSS rendering
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Enable window resizing
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        # No title bar, so no window title needed
        # Default size (width x height). Height set to 430px
        self.resize(480, 430)
        self.setMouseTracking(True)
        self.setMinimumSize(
            320, 220
        )  # Increased minimum height to accommodate footer layout with resize grip

        logger.debug("Overlay window configured as regular translator window")

        # Main vertical layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 10)  # left-top-right-bottom
        layout.setSpacing(6)

        # Header: title
        # Use a horizontal layout-like composition
        title_label = QLabel("Translator")
        title_label.setFont(QFont("Arial", 11, QFont.Bold))
        layout.addWidget(title_label)

        # Original text label and widget
        self.original_label = QLabel("Original:")
        self.original_label.setFont(QFont("Arial", 10, QFont.Bold))

        # Row: detected language + auto-swap checkbox
        info_row = QHBoxLayout()
        info_row.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        # Detected language label (short)
        self.detected_lang_label = QLabel("Language: —")
        self.detected_lang_label.setFixedWidth(120)
        info_row.addWidget(self.detected_lang_label)

        # Auto-swap checkbox for EN <-> RU behavior
        self.auto_swap_checkbox = QCheckBox("Auto-translate EN ↔ RU")
        self.auto_swap_checkbox.setToolTip(
            "If enabled, English will be translated to Russian, and Russian to English"
        )
        # The state of this checkbox is now set in `show_overlay` to ensure it's always up-to-date.
        # Persist changes when user toggles the checkbox
        try:
            self.auto_swap_checkbox.stateChanged.connect(self._on_auto_swap_changed)
        except Exception:
            logger.debug("Failed to connect auto_swap_checkbox.stateChanged")
        info_row.addWidget(self.auto_swap_checkbox)

        layout.addLayout(info_row)

        # New row: language controls (Original label + Source/Swap/Target)
        language_row = QHBoxLayout()

        # Original label
        language_row.addWidget(self.original_label)

        # Add a spacer to push language controls to the right
        language_row.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        # Source combo
        self.source_combo = QComboBox()
        self.source_combo.setFixedSize(120, 28)
        self.source_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        language_row.addWidget(self.source_combo)

        # Swap button
        self.swap_btn = QPushButton()
        self.swap_btn.setFixedSize(35, 28)
        img_path = Path(__file__).parent.parent.parent.parent / "img" / "arrows-exchange.png"
        pixmap = QPixmap(str(img_path))
        self.swap_btn.setIcon(QIcon(pixmap))
        self.swap_btn.setIconSize(QSize(20, 24))
        language_row.addWidget(self.swap_btn)

        # Target label and combo

        self.target_combo = QComboBox()
        self.target_combo.setFixedSize(120, 28)
        self.target_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        language_row.addWidget(self.target_combo)

        # Add font-awesome chevron arrows to comboboxes (overlay labels; preserve mouse events)
        self._combo_arrows = {}
        try:
            self._decorate_combobox(self.source_combo)
            self._decorate_combobox(self.target_combo)
        except Exception as e:
            logger.debug(f"Failed to decorate combobox arrows: {e}")

        # Populate combos
        self._programmatic_combo_change = False
        try:
            cfg = config_service.get_settings()
        except Exception:
            cfg = None

        # Build a concise canonical language list limited to requested languages
        # Keep display names consistent (English full names)
        codes_set = ["en", "ru", "ua", "de"]

        # Display name overrides for codes not present in get_language_name mappings
        display_overrides = {}

        # Source combo: selected canonical codes (use full English names)
        try:
            for code in codes_set:
                display = display_overrides.get(code, get_language_name(code))
                self.source_combo.addItem(display, userData=code)
            # Insert 'Auto' option at the top for source language
            try:
                self.source_combo.insertItem(0, "Auto", userData="auto")
            except Exception:
                # Fallback to get_language_name if available
                try:
                    self.source_combo.insertItem(
                        0, get_language_name("auto"), userData="auto"
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Failed to populate source combo: {e}")

        # Target combo: selected canonical codes (use consistent full names)
        try:
            for code in codes_set:
                display = display_overrides.get(code, get_language_name(code))
                self.target_combo.addItem(display, userData=code)
        except Exception as e:
            logger.debug(f"Failed to populate target combo: {e}")

        # Restore persisted UI selections or defaults
        try:
            ui_source_language = (
                getattr(cfg, "ui_source_language", "en") if cfg else "en"
            )
            # ui_target_mode is not used in this context
            getattr(cfg, "ui_target_mode", "explicit") if cfg else "explicit"
            # Default target language - no fallback to legacy settings
            ui_target_language = (
                getattr(cfg, "ui_target_language", "en") if cfg else "en"
            )

            # Allow 'auto' persisted value; no remapping to 'en'

            # Apply to combos without emitting signals
            self._programmatic_combo_change = True
            self.source_combo.blockSignals(True)
            self.target_combo.blockSignals(True)

            # Helper: set combo to a userData value
            def _set_combo_by_data(combo: QComboBox, value: str):
                for i in range(combo.count()):
                    if combo.itemData(i) == value:
                        combo.setCurrentIndex(i)
                        return True
                return False

            # Source: try persisted value, fallback to "en"
            if not _set_combo_by_data(self.source_combo, ui_source_language):
                _set_combo_by_data(self.source_combo, "en")

            # Target: use persisted explicit language or fallback to "en"
            if not _set_combo_by_data(self.target_combo, ui_target_language):
                _set_combo_by_data(self.target_combo, "en")

            self.source_combo.blockSignals(False)
            self.target_combo.blockSignals(False)
            self._programmatic_combo_change = False
        except Exception as e:
            logger.debug(f"Failed to restore language UI selections: {e}")
            self._programmatic_combo_change = False
            try:
                self.source_combo.blockSignals(False)
                self.target_combo.blockSignals(False)
            except Exception:
                pass

        # Connect handlers
        try:
            self.source_combo.currentIndexChanged.connect(self._on_source_changed)
            self.target_combo.currentIndexChanged.connect(self._on_target_changed)
            self.swap_btn.clicked.connect(self._on_swap_clicked)
        except Exception:
            logger.debug("Failed to connect language controls signals")

        # Add the language row to main layout
        layout.addLayout(language_row)

        self.original_text = QTextEdit()
        # Make the field interactive (editable) so user can select/modify text
        self.original_text.setReadOnly(False)
        self.original_text.setAcceptRichText(False)
        # Allow vertical expansion within layout
        # Make the text area expand in both directions
        self.original_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Placeholder test text for manual verification and visibility
        self.original_text.setPlaceholderText("Recognized text will appear here...")
        # Ensure explicit black text color and white background on the widget (override app palette)
        try:
            self.original_text.setStyleSheet("QTextEdit { color: #111111; background-color: #ffffff; }")
        except Exception:
            logger.debug("Unable to apply style to original_text")
        layout.addWidget(self.original_text)

        # Small spacing before buttons (translate, erase, copy)
        layout.addSpacing(6)

        # Buttons row for original text (positioned under the field)
        btn_row_orig = QHBoxLayout()
        btn_row_orig.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
 
        # Translate button under the original field
        self.translate_btn = QPushButton("  Translate")
        self.translate_btn.setObjectName("translateButton") # Set object name for specific styling
        self.translate_btn.setFixedHeight(28)
        self.translate_btn.setFixedWidth(120)
        try:
            img_path = Path(__file__).parent.parent.parent.parent / "img" / "translation-icon.png"
            pixmap = QPixmap(str(img_path))
            if not pixmap.isNull():
                self.translate_btn.setIcon(QIcon(pixmap))
            else:
                self.translate_btn.setIcon(qta.icon("fa5s.language", color="white"))
        except Exception:
            self.translate_btn.setIcon(qta.icon("fa5s.language", color="white"))
        self.translate_btn.setIconSize(QSize(14, 14))
        self.translate_btn.clicked.connect(self._on_translate_clicked)
        btn_row_orig.addWidget(self.translate_btn)

        # Clear original button
        self.clear_original_btn = QPushButton("")
        self.clear_original_btn.setFixedHeight(28)
        self.clear_original_btn.setFixedWidth(40)
        try:
            self.clear_original_btn.setIcon(qta.icon("fa5s.eraser", color="black"))
        except Exception:
            self.clear_original_btn.setText("Clear")
        self.clear_original_btn.setIconSize(QSize(16, 16))
        self.clear_original_btn.setToolTip("Clear original text")
        self.clear_original_btn.clicked.connect(self._clear_original_text)
        btn_row_orig.addWidget(self.clear_original_btn)

        # Copy original button (kept for parity with existing UI)
        self.copy_original_btn = QPushButton("")
        # Ensure button size
        self.copy_original_btn.setFixedHeight(28)
        self.copy_original_btn.setFixedWidth(40)
        self.copy_original_btn.setIcon(qta.icon("fa5.copy", color="black"))
        self.copy_original_btn.setIconSize(QSize(16, 16))
        self.copy_original_btn.clicked.connect(self._copy_original_to_clipboard)
        btn_row_orig.addWidget(self.copy_original_btn)

        layout.addLayout(btn_row_orig)

        # Update detected language when original text changes
        try:
            self.original_text.textChanged.connect(self._on_original_text_changed)
        except Exception:
            logger.debug("Failed to connect original_text.textChanged signal")

        # Translated text label and widget
        self.translated_label = QLabel("Translation:")
        self.translated_label.setFont(QFont("Arial", 10, QFont.Bold))
        self.translated_label.setStyleSheet("padding-bottom: 6px;")
        layout.addWidget(self.translated_label)

        self.translated_text = QTextEdit()
        # Make the field interactive (editable) so user can copy/modify text before copying out
        self.translated_text.setReadOnly(False)
        self.translated_text.setAcceptRichText(False)
        # Allow vertical expansion within layout
        self.translated_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Placeholder test text for manual verification
        self.translated_text.setPlaceholderText("Translation will appear here...")
        try:
            self.translated_text.setStyleSheet("QTextEdit { color: #111111; background-color: #ffffff; }")
        except Exception:
            logger.debug("Unable to apply style to translated_text")
        layout.addWidget(self.translated_text)
        # Give text areas stretch to grow with window
        try:
            idx_o = layout.indexOf(self.original_text)
            idx_t = layout.indexOf(self.translated_text)
            if idx_o != -1:
                layout.setStretch(idx_o, 1)
            if idx_t != -1:
                layout.setStretch(idx_t, 1)
        except Exception:
            pass

        # Small spacing before buttons
        layout.addSpacing(6)

        # Buttons row for translated text (positioned under the field)
        btn_row_tr = QHBoxLayout()
        btn_row_tr.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        # Clear translated button
        self.clear_translated_btn = QPushButton("")
        self.clear_translated_btn.setFixedHeight(28)
        self.clear_translated_btn.setFixedWidth(40)
        self.clear_translated_btn.setIcon(qta.icon("fa5s.eraser", color="black"))
        self.clear_translated_btn.setIconSize(QSize(16, 16))
        self.clear_translated_btn.setToolTip("Clear translated text")
        self.clear_translated_btn.clicked.connect(self._clear_translated_text)
        btn_row_tr.addWidget(self.clear_translated_btn)

        self.copy_translated_btn = QPushButton("")
        self.copy_translated_btn.setFixedHeight(28)
        self.copy_translated_btn.setFixedWidth(40)
        self.copy_translated_btn.setIcon(qta.icon("fa5.copy", color="black"))
        self.copy_translated_btn.setIconSize(QSize(16, 16))
        self.copy_translated_btn.clicked.connect(self._copy_translated_to_clipboard)
        btn_row_tr.addWidget(self.copy_translated_btn)
        layout.addLayout(btn_row_tr)

        # Footer row with Close button
        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)  # Left/right margins, bottom margin
        # Remove the expanding spacer to keep button aligned to the right
        self.close_btn = QPushButton("Close")
        self.close_btn.setFixedHeight(28)
        self.close_btn.setFixedWidth(86)
        self.close_btn.setObjectName(
            "closeButton"
        )  # Set object name for specific styling
        self.close_icon_normal = qta.icon("fa5s.times", color="black")
        self.close_icon_hover = qta.icon("fa5s.times", color="white")
        self.close_btn.setIcon(self.close_icon_normal)
        self.close_btn.setIconSize(QSize(16, 16))
        self.close_btn.clicked.connect(self.hide_overlay)
        self.close_btn.installEventFilter(self)
        footer_row.addWidget(self.close_btn, alignment=Qt.AlignRight)  # Align to right
        layout.addLayout(footer_row)

        # Close and collapse buttons in top-right corner
        self.close_btn_top = QPushButton(self)
        self.close_btn_top.setObjectName("closeBtnTop")
        self.close_btn_top.setFixedSize(22, 22)
        try:
            self.close_btn_top.setIcon(qta.icon("fa5s.times", color="black"))
        except Exception:
            self.close_btn_top.setText("X")
        self.close_btn_top.setIconSize(QSize(20, 16))
        self.close_btn_top.clicked.connect(self.hide_overlay)

        # Collapse button (to left of close)
        self.collapse_btn_top = QPushButton(self)
        self.collapse_btn_top.setObjectName("collapseBtnTop")
        self.collapse_btn_top.setFixedSize(22, 22)
        self.collapse_btn_top.setIcon(qta.icon("fa5s.compress-alt", color="black"))
        self.collapse_btn_top.setIconSize(QSize(20, 16))
        self.collapse_btn_top.clicked.connect(self.collapse_to_minibar)

        # Settings button (to left of collapse)
        self.settings_btn_top = QPushButton(self)
        self.settings_btn_top.setObjectName("settingsBtnTop")
        self.settings_btn_top.setFixedSize(22, 22)
        try:
            self.settings_btn_top.setIcon(qta.icon("fa5s.cog", color="black"))
        except Exception:
            self.settings_btn_top.setText("⚙")
        self.settings_btn_top.setIconSize(QSize(18, 16))
        self.settings_btn_top.setToolTip("Translator settings")
        self.settings_btn_top.clicked.connect(self._open_translator_settings)

        # Position buttons initially
        self._position_top_buttons()

        # Set background and styling — solid card with readable text
        self.setStyleSheet(
            """
            OverlayWindow {
                background-color: #ffffff;
                border: 1px solid #f5f5f5;
            }
            QLabel {
                color: #111111;
                border: none;
            }
            QTextEdit {
                background-color: #ffffff;
                color: #111111;
                border: 1px solid rgba(0,0,0,0.08);
                border-radius: 2px;
                padding: 4px 4px;
            }
            QPushButton {
                color: #111111;
                padding: 6px 10px;
                border: none;
                border-radius: 4px;
                background-color: #f0f0f0;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
            }
            QPushButton#translateButton {
                background-color: #356bd0;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton#translateButton:hover {
                background-color: #2f5db3;
            }
            QPushButton#closeButton:hover {
                background-color: #d02d2d; /* Red background on hover */
                color: #ffffff;
            }
            QPushButton#closeBtnTop {
                color: #111111;
                padding: 3px 6px;
                border-radius: 3px;
                background-color: #fff;
            }
            QPushButton#closeBtnTop:hover {
                background-color: #ff6b6b;
            }
            QPushButton#collapseBtnTop {
                color: #111111;
                padding: 3px 6px;
                border: none;
                border-radius: 3px;
                background-color: #fff;
            }
            QPushButton#collapseBtnTop:hover {
                background-color: #e8e8e8;
            }
            QPushButton#settingsBtnTop {
                color: #111111;
                padding: 3px 6px;
                border: none;
                border-radius: 3px;
                background-color: #fff;
            }
            QPushButton#settingsBtnTop:hover {
                background-color: #e8e8e8;
            }

            /* ComboBox styling */
            QComboBox {
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 4px;
                padding: 0px 0px 0px 8px;
                background-color: #ffffff;
                color: #111111;
                selection-background-color: #0078d7;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 22px;
                border-left: 1px solid rgba(0,0,0,0.08);
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
                background-color: transparent;
            }
            /* Popup list */
            QComboBox QAbstractItemView {
                border: 1px solid rgba(0,0,0,0.12);
                background-color: #ffffff;
                color: #111111;
                selection-background-color: #0078d7;
                selection-color: #ffffff;
                outline: none;
                padding: 4px;
            }
            QComboBox QAbstractItemView::item {
                min-height: 22px;
                padding: 4px 8px;
            }
            QComboBox QAbstractItemView::item:selected {
                background: #0078d7;
                color: #ffffff;
            }
        """
        )
        # Lifecycle helpers expected by overlay service
        # Public flag used by services to determine if window was destroyed
        self.is_destroyed = False
        # Hold pending timers/callbacks so we can cancel them if requested
        self._pending_timers: list[QTimer] = []

        # Dragging support for frameless window
        self._dragging = False
        self._drag_start_pos = QPoint()

        # Resizing support
        self._resizing = False
        self._resize_start_pos = QPoint()
        self._resize_start_geometry = QRect()
        self._resize_margin = 8
        self._resize_mode = None

        # Mini-bar integration state
        self._minibar: MiniBarOverlay | None = None
        self._expanded_geometry: QRect | None = None

        # Padding for top-right control buttons
        self._top_button_padding = {"top": 3, "right": 4, "bottom": 0, "left": 2}

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

    def _close_window(self):
        """Close/hide the widget and mark as destroyed for services."""
        try:
            logger.info("OverlayWindow: _close_window called — hiding and marking destroyed")
            # Cancel any pending callbacks/timers
            self._cancel_pending_callbacks()
            # Ensure minibar is closed so no orphan window remains
            try:
                if hasattr(self, "_minibar") and self._minibar:
                    self._minibar.close()
            except Exception:
                pass
            try:
                self._minibar = None
            except Exception:
                pass
            # Hide the widget instead of closing the app
            try:
                self.hide()
            except Exception:
                pass
            # Mark destroyed so services won't reuse it
            self.is_destroyed = True
        except Exception as e:
            logger.error(f"Error during _close_window: {e}")

    def _cancel_pending_callbacks(self):
        """Cancel any pending QTimer callbacks — no-op if none."""
        try:
            for t in list(self._pending_timers):
                try:
                    t.stop()
                except Exception:
                    pass
            self._pending_timers.clear()
            logger.debug("Cancelled pending overlay timers/callbacks")
        except Exception as e:
            logger.warning(f"Error cancelling pending callbacks: {e}")

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

    def mousePressEvent(self, event):
        """Handle mouse press for window dragging and resizing."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Determine resize mode on press to support immediate edge press
            pos = event.position().toPoint()
            mode = self._hit_test_resize(pos)
            if mode is not None:
                self._resize_mode = mode
                self._resizing = True
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geometry = self.geometry()
                self._update_cursor_for_mode(mode)
                event.accept()
                return
            # Otherwise start window drag
            self._dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move for window dragging and resizing."""
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_start_pos)
            event.accept()
            return

        if self._resizing and event.buttons() & Qt.MouseButton.LeftButton:
            # Compute new geometry based on original geometry (immutable baseline)
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            dx, dy = delta.x(), delta.y()

            s_geo = self._resize_start_geometry
            s_left, s_top, s_w, s_h = s_geo.left(), s_geo.top(), s_geo.width(), s_geo.height()
            min_w, min_h = self.minimumWidth(), self.minimumHeight()

            new_left, new_top, new_w, new_h = s_left, s_top, s_w, s_h
            mode = self._resize_mode or ""

            # Horizontal
            if "left" in mode:
                new_w = max(min_w, s_w - dx)
                new_left = s_left + (s_w - new_w)
            elif "right" in mode:
                new_w = max(min_w, s_w + dx)

            # Vertical
            if "top" in mode:
                new_h = max(min_h, s_h - dy)
                new_top = s_top + (s_h - new_h)
            elif "bottom" in mode:
                new_h = max(min_h, s_h + dy)

            self.setGeometry(QRect(new_left, new_top, new_w, new_h))
            event.accept()
            return

        # Update hover cursor/mode when not dragging/resizing
        pos = event.position().toPoint()
        mode = self._hit_test_resize(pos)
        self._resize_mode = mode
        self._update_cursor_for_mode(mode)

    def mouseReleaseEvent(self, event):
        """Handle mouse release to stop dragging and resizing."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._resizing = False
            self._resize_mode = None
            # Update cursor according to current hover position
            try:
                pos = event.position().toPoint()
                self._update_cursor_for_mode(self._hit_test_resize(pos))
            except Exception:
                self.setCursor(Qt.ArrowCursor)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to collapse to minibar."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.collapse_to_minibar()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _position_top_buttons(self):
        """Position the top-right control buttons (collapse + close) with padding."""
        padding = getattr(
            self, "_top_button_padding", {"top": 0, "right": 0, "bottom": 0, "left": 0}
        )

        buttons = [
            getattr(self, "close_btn_top", None),
            getattr(self, "collapse_btn_top", None),
            getattr(self, "settings_btn_top", None),
        ]

        top_offset = padding.get("top", 0)
        right_offset = padding.get("right", 0)
        spacing = padding.get("left", 2)

        current_x = self.width() - right_offset

        for button in buttons:
            if not button:
                continue
            size = button.size()
            current_x -= size.width()
            button.move(max(0, current_x), top_offset)
            current_x -= spacing

    def _open_translator_settings(self):
        """Show the translator-specific settings dialog."""
        try:
            if self._translator_settings_dialog is None:
                dialog = TranslatorSettingsDialog(self)
                dialog.destroyed.connect(
                    lambda: setattr(self, "_translator_settings_dialog", None)
                )
                self._translator_settings_dialog = dialog

            dialog = self._translator_settings_dialog
            if dialog.isHidden():
                dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        except Exception as e:
            logger.error(f"Failed to open translator settings dialog: {e}")

    def _hit_test_resize(self, pos: QPoint):
        """Return resize mode string given a position in widget coords, or None if not on edge."""
        r = self.rect()
        margin = getattr(self, "_resize_margin", 8)

        left = pos.x() <= margin
        right = pos.x() >= r.width() - margin
        top = pos.y() <= margin
        bottom = pos.y() >= r.height() - margin

        if left and bottom:
            return "bottom-left"
        if right and bottom:
            return "bottom-right"
        if left and top:
            return "top-left"
        if right and top:
            return "top-right"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"
        return None

    def _update_cursor_for_mode(self, mode: str | None):
        """Set cursor shape for given resize mode."""
        if mode == "bottom-left":
            self.setCursor(Qt.SizeBDiagCursor)
        elif mode == "bottom-right":
            self.setCursor(Qt.SizeFDiagCursor)
        elif mode == "top-left":
            self.setCursor(Qt.SizeFDiagCursor)
        elif mode == "top-right":
            self.setCursor(Qt.SizeBDiagCursor)
        elif mode in ("left", "right"):
            self.setCursor(Qt.SizeHorCursor)
        elif mode in ("top", "bottom"):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def resizeEvent(self, event):
        """Handle window resize to reposition the top buttons."""
        super().resizeEvent(event)
        self._position_top_buttons()

    def collapse_to_minibar(self):
        """Collapse the main overlay to a detachable MiniBar."""
        try:
            # Save current geometry to restore later
            try:
                self._expanded_geometry = QRect(self.geometry())
            except Exception:
                self._expanded_geometry = self.geometry()
            # Create MiniBar if not existing
            if self._minibar is None:
                self._minibar = MiniBarOverlay(self, self.restore_from_minibar)
                # Ensure layout is calculated for accurate width
                self._minibar.adjustSize()
            # Position minibar so its right edge aligns with overlay's right edge
            g = self.geometry()
            minibar_x = g.x() + g.width() - self._minibar.width()
            minibar_y = g.y()
            self._minibar.show_at((minibar_x, minibar_y))
            # Hide main overlay (do NOT mark destroyed)
            self.hide()
        except Exception as e:
            logger.error(f"Failed to collapse to minibar: {e}")

    def restore_from_minibar(self):
        """Restore the overlay from the MiniBar to its last geometry and bring to front.

        Position is restored so that the overlay's top-right aligns with the MiniBar's top-right.
        """
        try:
            # Determine minibar geometry for alignment
            minibar_geom = None
            try:
                if self._minibar:
                    try:
                        minibar_geom = self._minibar.frameGeometry()
                    except Exception:
                        minibar_geom = self._minibar.geometry()
            except Exception:
                minibar_geom = None

            if self._expanded_geometry is not None:
                g = QRect(self._expanded_geometry)
                if minibar_geom is not None:
                    # Align overlay's top-right with minibar's top-right
                    minibar_right = minibar_geom.x() + minibar_geom.width()
                    minibar_top = minibar_geom.y()
                    overlay_left = minibar_right - g.width()
                    g.moveTopLeft(QPoint(overlay_left, minibar_top))
                self.setGeometry(g)
            elif minibar_geom is not None:
                # If we don't know previous size, position so right aligns
                minibar_right = minibar_geom.x() + minibar_geom.width()
                minibar_top = minibar_geom.y()
                overlay_left = minibar_right - self.width()
                self.move(overlay_left, minibar_top)
        except Exception:
            pass
        # Show and raise overlay
        self.show()
        try:
            self.raise_()
            self.activateWindow()
        except Exception:
            pass
        # Hide minibar if present
        if self._minibar:
            try:
                self._minibar.hide()
            except Exception:
                pass

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
        try:
            enabled = bool(state)
            try:
                # Use config_service to set the specific setting
                config_service.set_setting("ocr_auto_swap_en_ru", enabled)
                logger.info(f"OCR auto-swap setting updated: {enabled}")
            except Exception as e:
                logger.error(f"Failed to save OCR auto-swap setting: {e}")
        except Exception as e:
            logger.debug(f"Error in _on_auto_swap_changed: {e}")

    # --- New handlers for language controls ---

    def _find_index_by_data(self, combo: QComboBox, data_value: str) -> int:
        try:
            for i in range(combo.count()):
                if combo.itemData(i) == data_value:
                    return i
        except Exception:
            pass
        return -1

    # --- ComboBox arrow decoration using qtawesome (font-awesome) ---

    def _decorate_combobox(self, combo: QComboBox):
        """Overlay a small chevron-down icon on the right side of the QComboBox."""
        try:
            from PySide6.QtWidgets import QLabel

            arrow_label = QLabel(combo)
            # Use a subtle color to match UI; adjust size as needed
            try:
                icon = qta.icon("fa5s.chevron-down", color="#666666")
            except Exception:
                # Fallback to angle-down if chevron unavailable
                icon = qta.icon("fa5s.angle-down", color="#666666")
            pix = icon.pixmap(12, 12)
            arrow_label.setPixmap(pix)
            arrow_label.setFixedSize(12, 12)
            # Allow clicks to pass through to the combo
            arrow_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            arrow_label.setObjectName("comboArrow")
            arrow_label.show()

            # Store and install event filter to reposition on resize/style changes
            self._combo_arrows[combo] = arrow_label
            combo.installEventFilter(self)
            self._position_combo_arrow(combo)
        except Exception as e:
            logger.debug(f"_decorate_combobox failed: {e}")

    def _position_combo_arrow(self, combo: QComboBox):
        """Position the overlay arrow label inside the combo (right-aligned, centered vertically)."""
        try:
            label = self._combo_arrows.get(combo)
            if not label:
                return
            aw, ah = label.width(), label.height()
            # Center arrow in the drop-down area (22px wide)
            x = max(0, combo.width() - 22 + (22 - aw) // 2)
            y = max(0, (combo.height() - ah) // 2)
            label.move(x, y)
            label.raise_()
            label.show()
        except Exception as e:
            logger.debug(f"_position_combo_arrow failed: {e}")

    def eventFilter(self, obj, event):
        """Handle events for child widgets."""
        # Reposition combo arrow on resize/show/style changes
        try:
            if isinstance(obj, QComboBox) and event.type() in (QEvent.Resize, QEvent.Show, QEvent.StyleChange):
                self._position_combo_arrow(obj)
        except Exception:
            pass

        # Change close button icon on hover
        try:
            if obj == self.close_btn:
                if event.type() == QEvent.Enter:
                    self.close_btn.setIcon(self.close_icon_hover)
                elif event.type() == QEvent.Leave:
                    self.close_btn.setIcon(self.close_icon_normal)
        except Exception:
            pass

        return super().eventFilter(obj, event)

    def _on_source_changed(self, index: int):
        """User changed Source combo -> persist ui_source_language."""
        try:
            if getattr(self, "_programmatic_combo_change", False):
                return
            code = self.source_combo.currentData()
            config_service.set_setting("ui_source_language", code)
            logger.info(f"UI source language updated: {code}")
        except Exception as e:
            logger.error(f"Failed to persist ui_source_language: {e}")

    def _on_target_changed(self, index: int):
        """User changed Target combo -> persist ui_target_mode/ui_target_language."""
        try:
            if getattr(self, "_programmatic_combo_change", False):
                return
            data = self.target_combo.currentData()
            updates = {"ui_target_mode": "explicit", "ui_target_language": data}
            config_service.update_settings(updates)
            logger.info(f"UI target updated: mode=explicit, lang={data}")
        except Exception as e:
            logger.error(f"Failed to persist target selection: {e}")

    def _on_swap_clicked(self):
        """Swap button behavior"""
        try:
            if not hasattr(self, "source_combo") or not hasattr(self, "target_combo"):
                return

            src_data = self.source_combo.currentData()
            tgt_data = self.target_combo.currentData()

            # If Source is set to 'auto', don't put 'auto' into Target (which doesn't support it).
            # Instead, move the current Target language into Source and keep Target unchanged.
            if src_data == "auto":
                self._programmatic_combo_change = True
                try:
                    self.source_combo.blockSignals(True)
                    idx_s = self._find_index_by_data(self.source_combo, tgt_data)
                    if idx_s != -1:
                        self.source_combo.setCurrentIndex(idx_s)
                finally:
                    try:
                        self.source_combo.blockSignals(False)
                    except Exception:
                        pass
                    self._programmatic_combo_change = False

                try:
                    updates = {
                        "ui_source_language": tgt_data,
                        "ui_target_mode": "explicit",
                        # Keep target as-is; read current data to persist the actual visible target
                        "ui_target_language": self.target_combo.currentData(),
                    }
                    config_service.update_settings(updates)
                    logger.info(
                        f"Swap with 'auto' source: moved target '{tgt_data}' into source; kept target unchanged"
                    )
                except Exception as e:
                    logger.error(f"Failed to save swap with 'auto' source: {e}")
                return

            new_source = tgt_data
            new_target = src_data

            self._programmatic_combo_change = True
            try:
                self.source_combo.blockSignals(True)
                self.target_combo.blockSignals(True)
                idx_s = self._find_index_by_data(self.source_combo, new_source)
                if idx_s != -1:
                    self.source_combo.setCurrentIndex(idx_s)
                idx_t = self._find_index_by_data(self.target_combo, new_target)
                if idx_t != -1:
                    self.target_combo.setCurrentIndex(idx_t)
            finally:
                try:
                    self.source_combo.blockSignals(False)
                    self.target_combo.blockSignals(False)
                except Exception:
                    pass
                self._programmatic_combo_change = False

            try:
                updates = {
                    "ui_source_language": new_source,
                    "ui_target_mode": "explicit",
                    "ui_target_language": new_target,
                }
                config_service.update_settings(updates)
                logger.info(f"Swapped source/target and persisted: source={new_source}, target={new_target}")
            except Exception as e:
                logger.error(f"Failed to save swapped languages: {e}")
        except Exception as e:
            logger.error(f"Error in _on_swap_clicked: {e}")

    def _on_translate_clicked(self):
        """Translate the text from the original_text field and put result into translated_text using a background thread."""
        try:
            text = self.original_text.toPlainText().strip()
            if not text:
                logger.info("Translate button clicked with empty original_text")
                return

            # Disable button and provide feedback
            self.translate_btn.setEnabled(False)
            prev_text = self.translate_btn.text()
            self.translate_btn.setText("  Translating...")
            QApplication.processEvents()

            # Determine detected language from input
            detected = detect_language(text) or "auto"

            # Read all relevant settings
            settings = config_service.get_settings()
            swap_enabled = getattr(settings, "ocr_auto_swap_en_ru", False)

            # Determine effective source language from Source combo
            try:
                source_lang = self.source_combo.currentData() or detected
            except Exception:
                source_lang = detected

            # If 'Auto' is selected in Source, use detected language for the worker call
            if source_lang == "auto":
                source_lang = detected

            # Determine effective target language with checkbox priority
            try:
                ui_target_language = self.target_combo.currentData()
            except Exception:
                ui_target_language = getattr(settings, "ui_target_language", "en")

            if swap_enabled:
                if detected == "en":
                    target_lang = "ru"
                elif detected == "ru":
                    target_lang = "en"
                else:
                    # If auto-swap is on but language is not en/ru, use the explicit UI target
                    target_lang = ui_target_language
            else:
                # If auto-swap is off, use the explicit UI target
                target_lang = ui_target_language

            logger.debug(f"Translate clicked with detected='{detected}', source='{source_lang}', target='{target_lang}'")

            # Worker that runs translation in a separate thread and its own event loop
            class TranslationWorker(QObject):
                finished = Signal(bool, str)  # success, result_or_error

                def __init__(self, text_to_translate: str, source_lang: str, target_lang: str):
                    super().__init__()
                    self.text = text_to_translate
                    self.source_lang = source_lang
                    self.target_lang = target_lang

                def run(self):
                    try:
                        from ..services.translation_service import get_translation_service
                        service = get_translation_service()

                        import asyncio

                        # Create and use a new event loop in this thread to avoid conflicting with Qt's loop
                        loop = asyncio.new_event_loop()
                        try:
                            asyncio.set_event_loop(loop)
                            resp = loop.run_until_complete(
                                service.translate_text_async(
                                    self.text,
                                    source_lang=self.source_lang,
                                    target_lang=self.target_lang,
                                )
                            )
                        finally:
                            try:
                                loop.close()
                            except Exception:
                                pass

                        if resp and getattr(resp, "success", False):
                            self.finished.emit(True, resp.translated_text or "")
                        else:
                            self.finished.emit(False, getattr(resp, "error_message", "Translation failed"))
                    except Exception as e:
                        self.finished.emit(False, str(e))

            # Create worker and thread
            self._translation_worker = TranslationWorker(text, source_lang, target_lang)
            self._translation_thread = QThread()
            self._translation_worker.moveToThread(self._translation_thread)

            # Connect signals
            # Store prev_text on the instance so the slot runs in the main thread and can access it safely
            self._translation_prev_text = prev_text
            self._translation_worker.finished.connect(self._on_translation_finished)
            self._translation_thread.started.connect(self._translation_worker.run)

            # Cleanup
            self._translation_worker.finished.connect(self._translation_thread.quit)
            self._translation_worker.finished.connect(self._translation_worker.deleteLater)
            self._translation_thread.finished.connect(self._translation_thread.deleteLater)

            # Start background translation
            self._translation_thread.start()

        except Exception as e:
            logger.error(f"Error starting translation worker: {e}")
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Error", f"Error starting translation: {e}")
            # Ensure button re-enabled
            try:
                self.translate_btn.setEnabled(True)
                self.translate_btn.setText("Translate")
            except Exception:
                pass

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
            try:
                # Use stored prev_text (set when translation started)
                prev_text = getattr(self, "_translation_prev_text", "Translate")
                self.translate_btn.setEnabled(True)
                self.translate_btn.setText(prev_text)
                # Clean up stored value
                if hasattr(self, "_translation_prev_text"):
                    delattr(self, "_translation_prev_text")
            except Exception:
                pass

    def _copy_translated_to_clipboard(self):
        """Copy translated text to clipboard."""
        self._copy_text_to_clipboard(self.translated_text, self.copy_translated_btn, "Translated")

    def show_overlay(self, original_text: str = "", translated_text: str = "", position: tuple = None):
        """Show the overlay with specified content.

        Args:
            original_text: Original text to display
            translated_text: Translated text to display
            position: (x, y) position for the window (ignored for fullscreen)
        """
        logger.info("Showing overlay window")

        # Update auto-swap checkbox state from settings each time the window is shown
        try:
            cfg = config_service.get_settings()
            current_state = bool(getattr(cfg, "ocr_auto_swap_en_ru", True))
            self.auto_swap_checkbox.setChecked(current_state)
        except Exception:
            logger.debug(
                "Failed to load ocr_auto_swap_en_ru for overlay; defaulting to True"
            )
            self.auto_swap_checkbox.setChecked(True)

        self.original_text.setPlainText(original_text)
        self.translated_text.setPlainText(translated_text)

        # For fullscreen overlay, position is ignored
        self.show()
        self.raise_()
        self.activateWindow()
        logger.debug("Overlay window shown and activated")

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
        # Close minibar if present to avoid orphan window
        try:
            if hasattr(self, "_minibar") and self._minibar:
                self._minibar.close()
                self._minibar = None
        except Exception:
            pass
        self.hide()
        logger.debug("Overlay window hidden")

    def closeEvent(self, event):
        """Intercept window close (X) and hide the overlay instead of exiting the app.

        Additionally ensure any MiniBar is closed to avoid orphan windows.
        """
        try:
            # Close minibar if present to avoid orphan window
            try:
                if hasattr(self, "_minibar") and self._minibar:
                    self._minibar.close()
                    self._minibar = None
            except Exception:
                pass

            logger.info("Overlay closeEvent triggered — hiding overlay instead of closing application")
            # Hide the overlay and ignore the close so application keeps running
            self.hide_overlay()
            event.ignore()
        except Exception as e:
            logger.error(f"Error handling closeEvent on overlay: {e}")
            # As a fallback, accept the event to avoid leaving the app in inconsistent state
            event.accept()

    def is_overlay_visible(self) -> bool:
        """Check if overlay is currently visible.

        Returns:
            bool: True if overlay is visible
        """
        return self.isVisible()
