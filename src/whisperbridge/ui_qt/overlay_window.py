"""
Overlay window implementation for Qt-based UI.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QApplication, QPushButton, QFrame
from PySide6.QtCore import Qt, QPoint, QRect, QTimer, QThread, Signal, QObject, QSize
from PySide6.QtGui import QFont, QKeyEvent

import qtawesome as qta

from loguru import logger
from ..services.config_service import config_service


class OverlayWindow(QWidget):
    """Overlay window for displaying translation results."""

    def __init__(self):
        """Initialize the overlay window."""
        super().__init__()

        # Configure window properties — frameless window with resize capability
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint
        )
        # Set object name for CSS styling
        self.setObjectName("OverlayWindow")
        # Enable styled background for proper CSS rendering
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Enable window resizing
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        # No title bar, so no window title needed
        # Default size (width x height). Height set to 430px as requested.
        self.resize(480, 430)
        self.setMouseTracking(True)
        self.setMinimumSize(320, 220)  # Increased minimum height to accommodate footer layout with resize grip

        logger.debug("Overlay window configured as regular translator window")

        # Main vertical layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 2)
        layout.setSpacing(6)

        # Header: title and close button
        header_layout = QVBoxLayout()
        # Use a horizontal layout-like composition (keep simple)
        title_label = QLabel("Переводчик")
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(title_label)

        # Original text label and widget
        self.original_label = QLabel("Оригинал:")
        self.original_label.setFont(QFont("Arial", 10, QFont.Bold))
        self.original_label.setStyleSheet("padding-bottom: 6px;")
        self.original_label.setStyleSheet("padding-bottom: 6px;")
 
        # Row: Original label + detected language + auto-swap checkbox
        from PySide6.QtWidgets import QHBoxLayout, QSpacerItem, QSizePolicy, QCheckBox
        orig_row = QHBoxLayout()
        orig_row.addWidget(self.original_label)
        orig_row.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
 
        # Detected language label (short)
        self.detected_lang_label = QLabel("Язык: —")
        self.detected_lang_label.setFixedWidth(120)
        orig_row.addWidget(self.detected_lang_label)
 
        # Auto-swap checkbox for EN <-> RU behavior
        self.auto_swap_checkbox = QCheckBox("Авто-перевод EN ↔ RU")
        self.auto_swap_checkbox.setToolTip("Если включено, английский будет переводиться на русский, а русский — на английский")
        # Initialize state from settings (fallback True)
        try:
            cfg = config_service.get_settings()
            init_state = bool(getattr(cfg, "ocr_auto_swap_en_ru", True))
            self.auto_swap_checkbox.setChecked(init_state)
        except Exception:
            logger.debug("Failed to load ocr_auto_swap_en_ru from config; defaulting to True")
            self.auto_swap_checkbox.setChecked(True)
        # Persist changes when user toggles the checkbox
        try:
            self.auto_swap_checkbox.stateChanged.connect(self._on_auto_swap_changed)
        except Exception:
            logger.debug("Failed to connect auto_swap_checkbox.stateChanged")
        orig_row.addWidget(self.auto_swap_checkbox)
 
        layout.addLayout(orig_row)
 
        self.original_text = QTextEdit()
        # Make the field interactive (editable) so user can select/modify text
        self.original_text.setReadOnly(False)
        self.original_text.setAcceptRichText(False)
        # Allow vertical expansion within layout
        # Make the text area expand in both directions
        from PySide6.QtWidgets import QSizePolicy
        self.original_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Placeholder test text for manual verification and visibility
        self.original_text.setPlainText("Тестовый оригинал: Здесь будет распознанный текст (заглушка).")
        self.original_text.setPlaceholderText("Здесь появится распознанный текст...")
        # Ensure explicit black text color and white background on the widget (override app palette)
        try:
            self.original_text.setStyleSheet("QTextEdit { color: #111111; background-color: #ffffff; }")
        except Exception:
            logger.debug("Unable to apply style to original_text")
        layout.addWidget(self.original_text)

        # Small spacing before buttons
        layout.addSpacing(6)

        # Buttons row for original text (positioned under the field)
        from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSpacerItem, QSizePolicy
        btn_row_orig = QHBoxLayout()
        btn_row_orig.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
 
        # Translate button under the original field
        self.translate_btn = QPushButton("Перевести")
        self.translate_btn.setFixedHeight(28)
        self.translate_btn.setFixedWidth(120)
        self.translate_btn.setIcon(qta.icon('fa5s.language', color='black'))
        self.translate_btn.setIconSize(QSize(16, 16))
        self.translate_btn.clicked.connect(self._on_translate_clicked)
        btn_row_orig.addWidget(self.translate_btn)
 
        # Copy original button (kept for parity with existing UI)
        self.copy_original_btn = QPushButton("")
        # Ensure button size
        self.copy_original_btn.setFixedHeight(28)
        self.copy_original_btn.setFixedWidth(40)
        self.copy_original_btn.setIcon(qta.icon('fa5.copy', color='black'))
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
        self.translated_label = QLabel("Перевод:")
        self.translated_label.setFont(QFont("Arial", 10, QFont.Bold))
        self.translated_label.setStyleSheet("padding-bottom: 6px;")
        layout.addWidget(self.translated_label)

        self.translated_text = QTextEdit()
        # Make the field interactive (editable) so user can copy/modify text before copying out
        self.translated_text.setReadOnly(False)
        self.translated_text.setAcceptRichText(False)
        # Allow vertical expansion within layout
        from PySide6.QtWidgets import QSizePolicy
        self.translated_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Placeholder test text for manual verification
        self.translated_text.setPlainText("Тестовый перевод: Здесь будет переведённый текст (заглушка).")
        self.translated_text.setPlaceholderText("Здесь появится перевод...")
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
        self.copy_translated_btn = QPushButton("")
        self.copy_translated_btn.setFixedHeight(28)
        self.copy_translated_btn.setFixedWidth(40)
        self.copy_translated_btn.setIcon(qta.icon('fa5.copy', color='black'))
        self.copy_translated_btn.setIconSize(QSize(16, 16))
        self.copy_translated_btn.clicked.connect(self._copy_translated_to_clipboard)
        btn_row_tr.addWidget(self.copy_translated_btn)
        layout.addLayout(btn_row_tr)

        # Footer row with Close button
        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 10)  # Left/right margins, bottom margin
        # Remove the expanding spacer to keep button aligned to the right
        self.close_btn = QPushButton("Закрыть")
        self.close_btn.setIcon(qta.icon('fa5s.times', color='black'))
        self.close_btn.setIconSize(QSize(16, 16))
        self.close_btn.clicked.connect(self.hide_overlay)
        footer_row.addWidget(self.close_btn, alignment=Qt.AlignRight)  # Align to right
        layout.addLayout(footer_row)


        # Add close button in top-right corner
        self.close_btn_top = QPushButton(self)
        self.close_btn_top.setFixedSize(16, 16)
        self.close_btn_top.setIcon(qta.icon('fa5s.times', color='black'))
        self.close_btn_top.setIconSize(QSize(10, 10))
        self.close_btn_top.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
                border-radius: 2px;
            }
            QPushButton:hover {
                background-color: #ff6b6b;
                border-color: #cc5555;
            }
        """)
        self.close_btn_top.clicked.connect(self.hide_overlay)

        # Position buttons initially
        self._position_top_buttons()

        # Set background and styling — solid card with readable text
        self.setStyleSheet("""
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
        """)
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

    def show_loading(self, position: tuple | None = None):
        """Show a minimal loading state at an optional absolute position."""
        try:
            logger.info("OverlayWindow: show_loading() called")
            if position:
                try:
                    x, y = position
                    self.move(x, y)
                except Exception:
                    logger.debug("Failed to position loading overlay")
            # Simple loading placeholder: replace original text with 'Loading...'
            try:
                self.original_text.setPlainText("Загрузка...")
            except Exception:
                pass
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


    def _position_top_buttons(self):
        """Position the close button in the top-right corner."""
        if hasattr(self, 'close_btn_top'):
            close_size = self.close_btn_top.size()

            # Position close button on the rightmost position
            self.close_btn_top.move(
                self.width() - close_size.width(),
                0  # Top of the window
            )

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

    def _copy_original_to_clipboard(self):
        """Copy original text to clipboard."""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.original_text.toPlainText())
            logger.info("Original text copied to clipboard")
            # Preserve current icon and text so we can restore them after transient feedback.
            prev_icon = self.copy_original_btn.icon()
            prev_text = self.copy_original_btn.text()
            # Show a check/done icon as transient feedback
            try:
                self.copy_original_btn.setIcon(qta.icon('fa5s.check', color='green'))
            except Exception:
                # Fallback: if qtawesome icon creation fails, keep existing icon
                pass
            # Clear text (buttons here are usually icon-only)
            self.copy_original_btn.setText("")
            QTimer.singleShot(1200, lambda p_icon=prev_icon, p_text=prev_text: (self.copy_original_btn.setIcon(p_icon), self.copy_original_btn.setText(p_text)))
        except Exception as e:
            logger.error(f"Failed to copy original text: {e}")

    def _on_original_text_changed(self):
        """Update detected language label when original text changes."""
        try:
            from ..utils.api_utils import detect_language, get_language_name
            text = self.original_text.toPlainText().strip()
            if not text:
                self.detected_lang_label.setText("Язык: —")
                return

            # Detect language (may return codes like 'en', 'ru', etc.)
            lang_code = detect_language(text)
            if lang_code:
                lang_name = get_language_name(lang_code)
                # Show short name in Russian UI, e.g., "Язык: English"
                self.detected_lang_label.setText(f"Язык: {lang_name}")
            else:
                self.detected_lang_label.setText("Язык: —")
        except Exception as e:
            logger.debug(f"Failed to update detected language label: {e}")

    def _on_auto_swap_changed(self, state):
        """Persist OCR auto-swap checkbox state to settings when changed."""
        try:
            enabled = bool(state)
            try:
                # Use config_service to get and save settings
                current = config_service.get_settings()
                current.ocr_auto_swap_en_ru = enabled
                # Save via config_service so observers are notified
                config_service.save_settings(current)
                logger.info(f"OCR auto-swap setting updated: {enabled}")
            except Exception as e:
                logger.error(f"Failed to save OCR auto-swap setting: {e}")
        except Exception as e:
            logger.debug(f"Error in _on_auto_swap_changed: {e}")

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
            self.translate_btn.setText("Перевод...")
            QApplication.processEvents()

            # Worker that runs translation in a separate thread and its own event loop
            class TranslationWorker(QObject):
                finished = Signal(bool, str)  # success, result_or_error

                def __init__(self, text_to_translate: str):
                    super().__init__()
                    self.text = text_to_translate

                def run(self):
                    try:
                        from ..services.translation_service import get_translation_service
                        from ..utils.api_utils import detect_language
                        from ..core.config import settings as core_settings
                        service = get_translation_service()

                        # Detect source language from text
                        detected = detect_language(self.text) or "auto"

                        # Choose target language: en <-> ru swap; fallback to configured target
                        if detected == "en":
                            target = "ru"
                        elif detected == "ru":
                            target = "en"
                        else:
                            target = getattr(core_settings, "target_language", "en")

                        logger.debug(f"Detected language '{detected}' for translation request; using target '{target}'")

                        import asyncio
                        # Create and use a new event loop in this thread to avoid conflicting with Qt's loop
                        loop = asyncio.new_event_loop()
                        try:
                            asyncio.set_event_loop(loop)
                            resp = loop.run_until_complete(
                                service.translate_text_async(self.text, source_lang=detected, target_lang=target)
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
            self._translation_worker = TranslationWorker(text)
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
            QMessageBox.critical(self, "Ошибка", f"Ошибка при запуске перевода: {e}")
            # Ensure button re-enabled
            try:
                self.translate_btn.setEnabled(True)
                self.translate_btn.setText("Перевести")
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
                QMessageBox.warning(self, "Перевод не удался", f"Ошибка перевода: {result}")
                logger.error(f"Translation failed: {result}")
        finally:
            try:
                # Use stored prev_text (set when translation started)
                prev_text = getattr(self, "_translation_prev_text", "Перевести")
                self.translate_btn.setEnabled(True)
                self.translate_btn.setText(prev_text)
                # Clean up stored value
                if hasattr(self, "_translation_prev_text"):
                    delattr(self, "_translation_prev_text")
            except Exception:
                pass

    def _copy_translated_to_clipboard(self):
        """Copy translated text to clipboard."""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.translated_text.toPlainText())
            logger.info("Translated text copied to clipboard")
            # Preserve current icon and text so we can restore them after transient feedback.
            prev_icon = self.copy_translated_btn.icon()
            prev_text = self.copy_translated_btn.text()
            # Show a check/done icon as transient feedback
            try:
                self.copy_translated_btn.setIcon(qta.icon('fa5s.check', color='green'))
            except Exception:
                # Fallback: if qtawesome icon creation fails, keep existing icon
                pass
            # Clear text (buttons here are usually icon-only)
            self.copy_translated_btn.setText("")
            QTimer.singleShot(1200, lambda p_icon=prev_icon, p_text=prev_text: (self.copy_translated_btn.setIcon(p_icon), self.copy_translated_btn.setText(p_text)))
        except Exception as e:
            logger.error(f"Failed to copy translated text: {e}")

    def show_overlay(self, original_text: str = "", translated_text: str = "", position: tuple = None):
        """Show the overlay with specified content.

        Args:
            original_text: Original text to display
            translated_text: Translated text to display
            position: (x, y) position for the window (ignored for fullscreen)
        """
        logger.info("Showing overlay window")
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
        self.hide()
        logger.debug("Overlay window hidden")

    def closeEvent(self, event):
        """Intercept window close (X) and hide the overlay instead of exiting the app."""
        try:
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