"""
Overlay window implementation for Qt-based UI.
"""

from loguru import logger
from PySide6.QtCore import (
    QEvent,
    QSize,
    Qt,
    QThread,
    QTimer,
)
from PySide6.QtGui import QFont, QIcon, QPixmap
import qtawesome as qta
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
)

from ..services.config_service import config_service, SettingsObserver
from ..utils.language_utils import detect_language, get_language_name, get_supported_languages
from ..core.config import validate_api_key_format
from typing import Optional
from .styled_overlay_base import StyledOverlayWindow
from .workers import TranslationWorker, StyleWorker
from .overlay_ui_builder import OverlayUIBuilder, TranslatorSettingsDialog

# Base path for assets
_ASSETS_BASE = Path(__file__).parent.parent / "assets"


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

        # Create UI builder and build UI components
        self.ui_builder = OverlayUIBuilder()
        ui_components = self.ui_builder.build_ui(self)

        # Assign UI components to self
        self.info_row_widget = ui_components['info_row']
        self.mode_label = self.ui_builder.mode_label
        self.mode_combo = self.ui_builder.mode_combo
        self.style_combo = self.ui_builder.style_combo
        self.detected_lang_label = self.ui_builder.detected_lang_label
        self.auto_swap_checkbox = self.ui_builder.auto_swap_checkbox
        self.source_combo = self.ui_builder.source_combo
        self.target_combo = self.ui_builder.target_combo
        self.swap_btn = self.ui_builder.swap_btn
        self.language_spacer = self.ui_builder.language_spacer
        self.original_label = self.ui_builder.original_label
        self.original_text = self.ui_builder.original_text
        self.translated_text = self.ui_builder.translated_text
        self.translated_label = self.ui_builder.translated_label
        self.translate_btn = self.ui_builder.translate_btn
        self.reader_mode_btn = self.ui_builder.reader_mode_btn
        self.clear_original_btn = self.ui_builder.clear_original_btn
        self.copy_original_btn = self.ui_builder.copy_original_btn
        self.clear_translated_btn = self.ui_builder.clear_translated_btn
        self.copy_translated_btn = self.ui_builder.copy_translated_btn
        self.original_buttons = self.ui_builder.original_buttons
        self.translated_buttons = self.ui_builder.translated_buttons
        self.original_panel = self.ui_builder.original_panel
        self.translated_panel = self.ui_builder.translated_panel
        self.footer_widget = ui_components['footer_widget']
        self.close_btn = ui_components['close_btn']
        self.status_label = self.ui_builder.status_label
        self.close_icon_normal = self.ui_builder.close_icon_normal
        self.close_icon_hover = self.ui_builder.close_icon_hover
        self.hideable_elements = ui_components['hideable_elements']

        # Mirror builder-provided assets and cached texts for downstream logic
        self.icon_translation = self.ui_builder.icon_translation
        self.icon_book_black = self.ui_builder.icon_book_black
        self.icon_book_white = self.ui_builder.icon_book_white
        self.icon_arrows_exchange = self.ui_builder.icon_arrows_exchange
        self.icon_eraser = self.ui_builder.icon_eraser
        self.icon_copy = self.ui_builder.icon_copy
        self.icon_check_green = self.ui_builder.icon_check_green
        self.icon_lock_white = self.ui_builder.icon_lock_white
        self.icon_lock_grey = self.ui_builder.icon_lock_grey
        self.close_icon_normal = self.ui_builder.close_icon_normal
        self.close_icon_hover = self.ui_builder.close_icon_hover

        # Initialize language controls
        self.ui_builder._init_language_controls()

        # Assemble the built UI into the window's content layout
        layout = self.content_layout
        layout.setSpacing(6)
        # Keep a reference to the info row widget
        self.info_row_widget = ui_components['info_row']
        layout.addWidget(self.info_row_widget)
        layout.addLayout(ui_components['language_row'])
        # Apply initial mode visibility now that all controls exist
        if hasattr(self, "mode_combo"):
            try:
                self._apply_mode_visibility(self.mode_combo.currentText())
            except Exception:
                pass
        layout.addWidget(self.original_panel)
        layout.addWidget(self.translated_label)
        layout.addWidget(self.translated_panel)
        layout.addWidget(ui_components['footer_widget'])

        # Set stretch factors
        layout.setStretch(layout.indexOf(self.original_panel), 1)
        layout.setStretch(layout.indexOf(self.translated_panel), 1)

        self.hideable_elements.extend(ui_components['hideable_elements'])
        self.add_settings_button(self._open_translator_settings)

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

    def _apply_button_style(self, button: QPushButton, compact: bool):
        """Delegate button styling to the UI builder."""
        self.ui_builder._apply_button_style(button, compact)


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
        self.reader_mode_btn.clicked.connect(self._on_reader_mode_clicked)
        self.clear_original_btn.clicked.connect(self._clear_original_text)
        self.copy_original_btn.clicked.connect(self._copy_original_to_clipboard)
        self.clear_translated_btn.clicked.connect(self._clear_translated_text)
        self.copy_translated_btn.clicked.connect(self._copy_translated_to_clipboard)
        self.close_btn.clicked.connect(self.dismiss)
        self.close_btn.installEventFilter(self)

    def _on_mode_changed(self, index: int):
        """Handle mode combo box changes (Translate vs Style)."""
        try:
            mode_text = self.mode_combo.currentText().strip().lower()
            self._apply_mode_visibility(mode_text)
        except Exception as e:
            logger.debug(f"Failed to handle mode change: {e}")

    def _apply_mode_visibility(self, mode: str):
        """Apply visibility changes based on selected mode."""
        try:
            mode = (mode or "").strip().lower()
            is_style = mode == "style"

            # Show/hide style combo based on mode
            if hasattr(self, "style_combo") and self.style_combo:
                self.style_combo.setVisible(is_style)

            # Update translate button text and icon
            if hasattr(self, "translate_btn") and self.translate_btn:
                try:
                    compact = getattr(getattr(self, "_cached_settings", None), "compact_view", False)
                    if not compact:
                        self.translate_btn.setText("Style" if is_style else "Translate")
                    self.translate_btn.setIcon(self.icon_translation)
                    self.translate_btn.setIconSize(QSize(14, 14))
                except Exception:
                    pass

            logger.debug(f"Mode visibility applied: mode='{mode}', is_style={is_style}")
        except Exception as e:
            logger.debug(f"Failed to apply mode visibility: {e}")

    def _update_language_controls_visibility(self):
        """Update visibility of language controls based on auto-swap setting."""
        try:
            settings = config_service.get_settings()
            auto_swap = getattr(settings, "auto_swap_en_ru", True)

            # Show language controls when auto-swap is disabled
            show_controls = not auto_swap

            if hasattr(self, "source_combo") and self.source_combo:
                self.source_combo.setVisible(show_controls)
            if hasattr(self, "target_combo") and self.target_combo:
                self.target_combo.setVisible(show_controls)
            if hasattr(self, "swap_btn") and self.swap_btn:
                self.swap_btn.setVisible(show_controls)
            if hasattr(self, "language_spacer") and self.language_spacer:
                # Adjust spacer size based on visibility
                size = 0 if show_controls else 34  # Hide spacer when controls are visible
                self.language_spacer.changeSize(size, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

            logger.debug(f"Language controls visibility updated: auto_swap={auto_swap}, show_controls={show_controls}")
        except Exception as e:
            logger.debug(f"Failed to update language controls visibility: {e}")




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
                        # Hide mode controls for DeepL provider
                        if hasattr(self, "mode_label") and self.mode_label:
                            self.mode_label.setVisible(False)
                        if hasattr(self, "mode_combo") and self.mode_combo:
                            self.mode_combo.setVisible(False)
                    else:
                        # Ensure Style option exists for LLM providers
                        if style_idx == -1:
                            try:
                                self.mode_combo.addItem("Style")
                            except Exception:
                                pass
                        # Ensure mode controls are visible for non-DeepL providers
                        if hasattr(self, "mode_label") and self.mode_label:
                            self.mode_label.setVisible(True)
                        if hasattr(self, "mode_combo") and self.mode_combo:
                            self.mode_combo.setVisible(True)
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

    def keyPressEvent(self, event):
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
        current_state = getattr(settings, "auto_swap_en_ru", True)
        self.auto_swap_checkbox.setChecked(current_state)

        self._update_layout()
        # Re-assert API state after layout restyles
        self._update_api_state_and_ui()

        # Update language controls visibility after layout is set up
        self._update_language_controls_visibility()

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

    def _copy_text_to_clipboard(self, text_widget, button: QPushButton, text_name: str):
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

    def _clear_text(self, text_widget, button: QPushButton, label_to_reset: Optional[QLabel] = None):
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
        """Persist Auto-swap checkbox state to settings when changed."""
        enabled = bool(state)
        if config_service.set_setting("auto_swap_en_ru", enabled):
            logger.info(f"Auto-swap setting updated: {enabled}")
            # Update language controls visibility when auto-swap setting changes
            self._update_language_controls_visibility()

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
                # Check if the result is empty (indicating safety filter block)
                if not result.strip():
                    self.status_label.setText("Response blocked by safety filters")
                    self.status_label.setStyleSheet("color: #c62828; font-weight: 600; font-size: 10px;")
                    self.translated_text.setPlainText("")
                    logger.warning("Translation was blocked by API safety filters")
                else:
                    self.translated_text.setPlainText(result)
                    logger.info("Translation completed and inserted into translated_text")

                    # Auto-copy translated text to clipboard if enabled for main window
                    try:
                        settings = self._cached_settings
                        auto_copy_main_window = getattr(settings, "auto_copy_translated_main_window", False)
                        if auto_copy_main_window:
                            from PySide6.QtWidgets import QApplication
                            clipboard = QApplication.clipboard()
                            clipboard.setText(result)
                            logger.info("Translated text automatically copied to clipboard (main window)")
                            self._show_button_feedback(self.copy_translated_btn)
                    except Exception as e:
                        logger.debug(f"Failed to auto-copy translated text: {e}")
            else:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Translation failed", f"Translation error: {result}")
                logger.error(f"Translation failed: {result}")
        finally:
            # Update status with completion time (only if not blocked by safety)
            if self._translation_start_time is not None:
                import time
                elapsed = time.time() - self._translation_start_time
                # Only show completion time if we didn't already set safety block message
                if "safety" not in (self.status_label.text() or "").lower():
                    self.status_label.setText(f"Completed in {elapsed:.1f}s")
                self._translation_start_time = None
            else:
                # Only clear if not showing safety message
                if "safety" not in (self.status_label.text() or "").lower():
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