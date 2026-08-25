"""
Overlay window implementation for Qt-based UI.
"""

import time
from typing import Optional

from loguru import logger
from PySide6.QtCore import (
    QEvent,
    QSize,
    Qt,
    QThread,
    QTimer,
)
from PySide6.QtGui import QAction, QTextCursor, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QMenu,
    QLabel,
)

from ..services.config_service import config_service, SettingsObserver
from ..utils.language_utils import detect_language, get_language_name, get_supported_languages
from ..core.config import (
    API_TIMEOUT_DEFAULT,
    API_TIMEOUT_MAX,
    API_TIMEOUT_MIN,
    validate_api_key_format,
)
from ..core.provider_catalog import APIProvider
from .styled_overlay_base import StyledOverlayWindow
from .workers import TranslationWorker, StyleWorker
from .translator_settings_dialog import TranslatorSettingsDialog
from .translator_view import TranslatorView


class _OverlaySettingsObserver(SettingsObserver):
    """Lightweight observer to react to settings changes affecting API readiness."""
    def __init__(self, owner):
        self._owner = owner

    def on_settings_changed(self, key, old_value, new_value):
        try:
            if key in ("api_provider", "openai_api_key", "google_api_key", "deepl_api_key", "api_timeout"):
                if hasattr(self._owner, "_update_api_state_and_ui"):
                    self._owner._update_api_state_and_ui()
            elif key == "translator_font_size":
                if hasattr(self._owner, "_apply_translator_font_size"):
                    self._owner._apply_translator_font_size(new_value)
            elif key == "text_styles":
                settings = config_service.get_settings()
                self._owner.view.refresh_styles(getattr(settings, "text_styles", []))
        except Exception as e:
            logger.debug(f"Overlay observer change handler error: {e}")

class OverlayWindow(StyledOverlayWindow):
    """Overlay window for displaying translation results."""

    def __init__(self):
        """Initialize the overlay window.

        The overlay owns orchestration, settings policy, signals, and business logic;
        TranslatorView owns the translator widget tree and its presentation state.
        """
        super().__init__(title="Translator")
        self._translator_settings_dialog = None
        self._translation_start_time = None
        self._translation_worker = None
        self._translation_thread = None
        self._style_worker = None
        self._style_thread = None

        # Animation state for loading spinner + dots
        self._loading_timer: Optional[QTimer] = None
        self._loading_rotation = 0
        self._loading_dots_count = 0
        self._loading_base_text = ""

        settings = config_service.get_settings()
        self.view = TranslatorView(
            get_supported_languages(),
            getattr(settings, "text_styles", []),
            getattr(settings, "ui_source_language", "en"),
            getattr(settings, "ui_target_language", "en"),
            getattr(settings, "compact_view", False),
            getattr(settings, "overlay_side_buttons_autohide", False),
            getattr(settings, "translator_font_size", None),
            parent=self,
        )
        self.content_layout.addWidget(self.view, 1)

        # Initialize provider menu
        self._setup_provider_menu()

        self.add_settings_button(self._open_translator_settings)

        self._connect_signals()

        # Observe settings changes to react to provider/key updates
        try:
            self._settings_observer = _OverlaySettingsObserver(self)
            config_service.add_observer(self._settings_observer)
        except Exception as e:
            logger.debug(f"Failed to add settings observer: {e}")

        # Initial API state check for button/status
        self._update_api_state_and_ui()

        logger.debug("OverlayWindow initialized")



    def _apply_translator_font_size(self, font_size: Optional[int] = None) -> None:
        """Delegate translator font presentation to the view."""
        self.view.set_font_size(font_size)

    def _connect_signals(self):
        """Connect all UI signals to their slots."""
        self.view.auto_swap_checkbox.stateChanged.connect(self._on_auto_swap_changed)
        self.view.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.view.target_combo.currentIndexChanged.connect(self._on_target_changed)
        self.view.swap_btn.clicked.connect(self._on_swap_clicked)
        self.view.original_text.textChanged.connect(self._on_original_text_changed)
        self.view.translated_text.textChanged.connect(self._update_reader_button_state)
        self.view.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.view.edit_styles_btn.clicked.connect(self._open_stylist_settings)
        self.view.translate_btn.clicked.connect(self._on_translate_clicked)
        self.view.reader_mode_btn.clicked.connect(self._on_reader_mode_clicked)
        self.view.clear_original_btn.clicked.connect(self._clear_original_text)
        self.view.copy_original_btn.clicked.connect(self._copy_original_to_clipboard)
        self.view.clear_translated_btn.clicked.connect(self._clear_translated_text)
        self.view.copy_translated_btn.clicked.connect(self._copy_translated_to_clipboard)
        self.view.close_btn.clicked.connect(self.dismiss)
        self.view.close_btn.installEventFilter(self)
        # Install event filter on original_text to capture Ctrl+Enter for translation
        self.view.original_text.installEventFilter(self)

    def _classify_request_error(self, error_message: str) -> tuple[str, bool]:
        """Map backend error text to a short UI status and whether it is a known API issue."""
        err_lower = (error_message or "").lower()

        if "quota" in err_lower:
            return "Quota exceeded", True
        if "rate limit" in err_lower or "429" in err_lower:
            return "Rate limit exceeded", True
        if "timeout" in err_lower:
            return "Request timed out", True
        if "cancel" in err_lower:
            return "Cancelled", True
        if "connection" in err_lower or "network" in err_lower:
            return "Network error", True
        if "server error" in err_lower or "500" in err_lower:
            return "Server error", True
        if "503" in err_lower:
            return "Service unavailable", True

        return "Failed", False

    def _apply_request_error_status(self, error_message: str, *, show_popup_for_unknown: bool) -> None:
        """Apply a stable error status without letting the generic finish path overwrite it."""
        status_text, is_known_error = self._classify_request_error(error_message)

        if show_popup_for_unknown and not is_known_error:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Translation failed", f"Translation error: {error_message}")

        logger.error(f"Translation failed: {error_message}")

        if self._translation_start_time is not None:
            elapsed = time.time() - self._translation_start_time
            self.view.set_status(f"{status_text} ({elapsed:.1f}s)")
        else:
            self.view.set_status(status_text)

        try:
            self.view.set_status(self.view.status_label.text(), "error")
        except Exception:
            pass

    def _apply_successful_translation_result(self, result: str) -> None:
        """Render a successful translation/style result into the UI."""
        if not result.strip():
            self.view.set_status("Model returned empty response", "error")
            self.view.translated_text.setPlainText("")
            logger.warning("Model returned empty translation response")
            return

        self.view.translated_text.setPlainText(result)
        self.view.set_status(self.view.status_label.text(), "default")
        logger.info("Translation completed and inserted into translated_text")

        try:
            settings = config_service.get_settings()
            auto_copy = getattr(settings, "auto_copy_translated_overlay", False)
            if auto_copy:
                clipboard = QApplication.clipboard()
                clipboard.setText(result)
                logger.info("Translated text automatically copied to clipboard (translator overlay)")
                self.view.show_button_feedback(self.view.copy_translated_btn)
        except Exception as e:
            logger.debug(f"Failed to auto-copy translated text: {e}")

    def _apply_success_completion_status(self) -> None:
        """Replace the in-flight status with the standard completion message."""
        if self._translation_start_time is not None:
            elapsed = time.time() - self._translation_start_time
            if "safety" not in (self.view.status_label.text() or "").lower():
                self.view.set_status(f"Completed in {elapsed:.1f}s")
            return

        if "safety" not in (self.view.status_label.text() or "").lower():
            self.view.set_status("")

    def _restore_request_controls(self) -> None:
        """Stop request affordances and restore the translate/style button text."""
        settings = config_service.get_settings()
        compact = getattr(settings, "compact_view", False)
        prev_text = getattr(self, "_translation_prev_text", "Translate")

        self._stop_loading_animation()
        if self.view.translate_btn:
            self.view.translate_btn.setEnabled(True)
            if not compact:
                self.view.translate_btn.setText(prev_text)

        if hasattr(self, "_translation_prev_text"):
            delattr(self, "_translation_prev_text")

    def _finalize_translation_request(self, *, success: bool, refresh_api_state: bool) -> None:
        """Run request cleanup after the terminal finished signal."""
        if success:
            self._apply_success_completion_status()

        self._translation_start_time = None
        self._restore_request_controls()

        if refresh_api_state:
            try:
                self._update_api_state_and_ui()
            except Exception:
                pass

    def _is_style_mode_selected(self) -> bool:
        """Return whether the current request should use Style mode."""
        return self.view.mode_combo.currentText().strip().lower() == "style"

    def _begin_request_ui_state(self, *, is_style: bool):
        """Initialize request state and loading UI before starting a worker."""
        self._translation_start_time = time.time()
        self.view.set_status("Request sent", "default")

        settings = config_service.get_settings()
        compact = getattr(settings, "compact_view", False)

        if self.view.translate_btn:
            prev_text = self.view.translate_btn.text()
            base_text = "Styling" if is_style else "Translating"
            self._start_loading_animation(base_text, compact)
        else:
            prev_text = "Style" if is_style else "Translate"

        self._translation_prev_text = prev_text
        return settings

    def _resolve_style_name(self, settings) -> str:
        """Resolve the current style preset name with the same fallback order as the UI."""
        style_name = ""
        try:
            style_name = self.view.style_combo.currentText().strip()
        except Exception:
            pass

        if style_name:
            return style_name

        try:
            styles = getattr(settings, "text_styles", []) or []
            if styles:
                first_style = styles[0]
                return (first_style.get("name") or "Improve") if isinstance(first_style, dict) else str(first_style)
        except Exception:
            pass

        return "Improve"

    def _start_style_request(self, text: str, settings) -> None:
        """Start a style worker for the current request."""
        style_name = self._resolve_style_name(settings)
        logger.debug(f"Style mode selected. Style='{style_name}'")
        self._style_worker, self._style_thread = self._setup_worker(StyleWorker, text, style_name)

    def _start_translation_request(self, text: str) -> None:
        """Start a translation worker using the current UI language selections."""
        ui_source_lang = self.view.source_combo.currentData()
        ui_target_lang = self.view.target_combo.currentData()
        logger.debug(f"Translate mode selected with UI languages: source='{ui_source_lang}', target='{ui_target_lang}'")
        self._translation_worker, self._translation_thread = self._setup_worker(
            TranslationWorker,
            text,
            ui_source_lang,
            ui_target_lang,
        )

    def _on_mode_changed(self, index: int):
        """Handle mode combo box changes (Translate vs Style)."""
        try:
            mode_text = self.view.mode_combo.currentText().strip().lower()
            self._apply_mode_visibility(mode_text)
        except Exception as e:
            logger.debug(f"Failed to handle mode change: {e}")



    def _open_stylist_settings(self):
        """Open the main settings dialog on the Stylist tab via UIService."""
        try:
            from ..services.ui_service import get_ui_service

            ui_service = get_ui_service()
            if ui_service is None:
                logger.warning("UIService is not available; cannot open Stylist settings")
                return

            ui_service.open_settings(tab_title="Stylist")
            logger.info("Opened settings dialog on Stylist tab")
        except Exception as e:
            logger.error(f"Failed to open stylist settings: {e}", exc_info=True)

    def _apply_mode_visibility(self, mode: str):
        """Apply visibility changes based on selected mode."""
        try:
            mode = (mode or "").strip().lower()
            compact = getattr(config_service.get_settings(), "compact_view", False)
            self.view.set_mode_visibility(mode, compact)

            logger.debug(f"Mode visibility applied: mode='{mode}'")

            # Ensure API state is correctly reflected after mode change
            self._update_api_state_and_ui()
        except Exception as e:
            logger.debug(f"Failed to apply mode visibility: {e}")

    def _update_language_controls_visibility(self):
        """Update visibility of language controls based on auto-swap setting."""
        try:
            settings = config_service.get_settings()
            auto_swap = getattr(settings, "auto_swap_en_ru", True)

            # Show language controls when auto-swap is disabled
            show_controls = not auto_swap

            self.view.set_language_controls_visible(show_controls)

            logger.debug(f"Language controls visibility updated: auto_swap={auto_swap}, show_controls={show_controls}")
        except Exception as e:
            logger.debug(f"Failed to update language controls visibility: {e}")




    def _is_api_ready(self) -> tuple[bool, str]:
        """Check whether API calls can proceed given current provider/key settings."""
        try:
            provider = (config_service.get_setting("api_provider") or APIProvider.OPENAI.value).strip().lower()
            try:
                provider = APIProvider(provider).value
            except ValueError:
                return False, f"Unsupported API provider: {provider}"

            key = config_service.get_setting(f"{provider}_api_key")
            if not key:
                return False, f"{provider.capitalize()} API key is not configured"

            if validate_api_key_format(key, provider):
                return True, ""
            return False, f"{provider.capitalize()} API key format is invalid"
        except Exception as e:
            logger.debug(f"API readiness check failed: {e}")
            return False, "API key is not configured"

    def _apply_disabled_translate_visuals(self, reason_msg: str) -> None:
        """Apply strong disabled visuals for the Translate/Style button."""
        try:
            compact = bool(getattr(config_service.get_settings(), "compact_view", False))
            self.view.set_translate_disabled(reason_msg, compact)
        except Exception as e:
            logger.debug(f"Failed to apply disabled translate visuals: {e}")

    def _restore_enabled_translate_visuals(self) -> None:
        """Restore normal visuals for the Translate/Style button."""
        try:
            # Avoid re-enabling visuals during an active request
            if getattr(self, "_translation_start_time", None) is None:
                self.view.translate_btn.setEnabled(True)
            compact = bool(getattr(config_service.get_settings(), "compact_view", False))
            self.view.restore_translate(compact)
        except Exception as e:
            logger.debug(f"Failed to restore enabled translate visuals: {e}")

    def _find_index_by_text(self, combo, text: str) -> int:
        """Helper to find index by visible text."""
        for i in range(combo.count()):
            if (combo.itemText(i) or "").strip().lower() == text.lower():
                return i
        return -1

    def _update_provider_badge(self) -> None:
        """Update the provider badge to reflect the current API provider."""
        try:
            provider = (config_service.get_setting("api_provider") or APIProvider.OPENAI.value).strip().lower()
            try:
                provider_enum = APIProvider(provider)
            except ValueError:
                return

            # Map provider to display name and property
            provider_map = {
                APIProvider.OPENAI: "OpenAI",
                APIProvider.GOOGLE: "Google",
                APIProvider.DEEPL: "DeepL",
            }
            display_name = provider_map[provider_enum]
            prop_value = provider_enum.value

            self.view.set_provider_badge(display_name, prop_value)
        except Exception as e:
            logger.debug(f"Failed to update provider badge: {e}")

    def _setup_provider_menu(self):
        """Setup the dropdown menu for the provider badge."""
        try:
            menu = QMenu(self.view.provider_badge)
            menu.setObjectName("providerMenu")
            # Enable translucent background for rounded corners in QSS
            menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            # Remove standard window frame/shadow to allow QSS control (matches ComboBox dropdowns)
            menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
            
            provider_labels = {
                APIProvider.OPENAI: "OpenAI",
                APIProvider.GOOGLE: "Google",
                APIProvider.DEEPL: "DeepL",
            }
            for provider, label in provider_labels.items():
                action = QAction(label, self)
                action.triggered.connect(lambda checked=False, value=provider.value: self._switch_provider(value))
                menu.addAction(action)

            self.view.provider_badge.setMenu(menu)
            logger.debug("Provider menu setup completed")

        except Exception as e:
            logger.error(f"Failed to setup provider menu: {e}")

    def _switch_provider(self, provider_key: str):
        """Switch the API provider and persist the setting."""
        try:
            logger.info(f"Switching provider to: {provider_key}")
            if config_service.set_setting("api_provider", provider_key):
                # UI update will happen automatically via _SettingsObserver -> _update_api_state_and_ui
                pass
        except Exception as e:
            logger.error(f"Failed to switch provider: {e}")

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
            if not ready:
                self.view.set_status(msg, "error")
            elif "API key" in (self.view.status_label.text() or ""):
                self.view.set_status("", "default")

            # Update provider badge
            self._update_provider_badge()

            # Enforce provider capabilities (disable Style mode for DeepL)
            try:
                provider = (config_service.get_setting("api_provider") or APIProvider.OPENAI.value).strip().lower()
                style_idx = self._find_index_by_text(self.view.mode_combo, "Style")
                if provider == "deepl":
                    # If currently on Style, switch to Translate before removing the item
                    try:
                        if (self.view.mode_combo.currentText() or "").strip().lower() == "style":
                            trans_idx = self._find_index_by_text(self.view.mode_combo, "Translate")
                            if trans_idx != -1:
                                self.view.mode_combo.setCurrentIndex(trans_idx)
                                self._apply_mode_visibility("Translate")
                    except Exception:
                        pass
                    # Remove Style option
                    if style_idx != -1:
                        self.view.mode_combo.removeItem(style_idx)
                    self.view.set_style_mode_available(False)
                else:
                    # Ensure Style option exists for LLM providers
                    if style_idx == -1:
                        try:
                            self.view.mode_combo.addItem("Style")
                        except Exception:
                            pass
                    self.view.set_style_mode_available(True)
            except Exception as e:
                logger.debug(f"Provider capability enforcement failed: {e}")
        except Exception as e:
            logger.debug(f"Failed to update API state/UI: {e}")

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
                dialog.layout_settings_changed.connect(self._update_layout)
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

        self.view.configure(compact, autohide, getattr(settings, "translator_font_size", None))

        # Re-apply API state after layout changes to override any button style resets
        self._update_api_state_and_ui()

        # Re-apply mode-dependent UI so the Translate button text is restored in full mode
        self._apply_mode_visibility(self.view.mode_combo.currentText())

        logger.debug(f"Layout updated: compact={compact}, autohide={autohide}")

    def eventFilter(self, obj, event):
        """Handle events for child widgets, including hover for compact buttons."""
        if obj == self.view.original_text and event.type() == QEvent.Type.KeyPress:

        # Handle Ctrl+Enter in original_text to trigger translation
            if event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                logger.debug("Ctrl+Enter pressed in original_text, triggering translation")
                self._on_translate_clicked()
                return True

        # PanelWidget handles its own hover-based autohide; no-op here

        if obj == self.view.close_btn:
            if event.type() == QEvent.Type.Enter:
                self.view.set_close_hovered(True)
            elif event.type() == QEvent.Type.Leave:
                self.view.set_close_hovered(False)

        return super().eventFilter(obj, event)

    def show_overlay(self, original_text: str = "", translated_text: str = "", error_message: str = ""):
        """Show the overlay with specified content."""
        logger.info("Showing overlay window")
        # Ensure button/state reflect API key presence at time of showing
        self._update_api_state_and_ui()

        settings = config_service.get_settings()
        current_state = getattr(settings, "auto_swap_en_ru", True)
        self.view.auto_swap_checkbox.setChecked(current_state)

        self._update_layout()
        # Re-assert API state after layout restyles
        self._update_api_state_and_ui()

        # Update language controls visibility after layout is set up
        self._update_language_controls_visibility()

        self.view.original_text.setPlainText(original_text)
        self.view.translated_text.setPlainText(translated_text)

        # Update status based on error or success
        if error_message:
            status_text, _is_known_error = self._classify_request_error(error_message)
            self.view.set_status(status_text, "error")
        elif original_text:
            self.view.set_status("Completed", "default")
        else:
            self.view.set_status("")

        # Update reader button state after setting text
        self._update_reader_button_state()

        # Set focus to original text for quick typing
        self.view.original_text.setFocus()
        cursor = self.view.original_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.view.original_text.setTextCursor(cursor)

        self.show()
        self.raise_()
        self.activateWindow()
        logger.debug("Overlay window shown and activated")

    def _copy_text_to_clipboard(self, text_widget, button: QPushButton, text_name: str):
        """Copy text from a QTextEdit to clipboard and provide visual feedback on a button."""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(text_widget.toPlainText())
            logger.info(f"{text_name} text copied to clipboard")
            self.view.show_button_feedback(button)
        except Exception as e:
            logger.error(f"Failed to copy {text_name} text: {e}")

    def _copy_original_to_clipboard(self):
        """Copy original text to clipboard."""
        self._copy_text_to_clipboard(self.view.original_text, self.view.copy_original_btn, "Original")

    def _clear_text(self, text_widget, button: QPushButton, label_to_reset: Optional[QLabel] = None):
        """Clear text from a QTextEdit widget and optionally reset a label, with visual feedback on button."""
        try:
            text_widget.clear()
            if label_to_reset:
                label_to_reset.setText("Language: —")
            self.view.show_button_feedback(button)
        except Exception as e:
            logger.error(f"Failed to clear text: {e}")

    def _clear_original_text(self):
        """Clear original text area and reset language label."""
        self._clear_text(self.view.original_text, self.view.clear_original_btn, self.view.detected_lang_label)
        self.view.set_status("")
        # Re-assert API state warning if needed
        self._update_api_state_and_ui()

    def _clear_translated_text(self):
        """Clear translated text area."""
        self._clear_text(self.view.translated_text, self.view.clear_translated_btn)
        self.view.set_status("")
        # Re-assert API state warning if needed
        self._update_api_state_and_ui()


    def _on_original_text_changed(self):
        """Update detected language label when original text changes."""
        try:
            text = self.view.original_text.toPlainText().strip()
            if not text:
                self.view.detected_lang_label.setText("Language: —")
                return

            lang_code = detect_language(text)
            if lang_code:
                lang_name = get_language_name(lang_code)
                self.view.detected_lang_label.setText(f"Language: {lang_name}")
            else:
                self.view.detected_lang_label.setText("Language: —")
        except Exception as e:
            logger.debug(f"Failed to update detected language label: {e}")

    def _update_reader_button_state(self):
        """Update the reader mode button state based on translated text presence."""
        try:
            translated_text = self.view.translated_text.toPlainText().strip()
            self.view.reader_mode_btn.setEnabled(bool(translated_text))
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
        code = self.view.source_combo.currentData()
        if config_service.set_setting("ui_source_language", code):
            logger.info(f"UI source language updated: {code}")

    def _on_target_changed(self, index: int):
        """User changed Target combo -> persist ui_target_language."""
        data = self.view.target_combo.currentData()
        updates = {"ui_target_language": data}
        try:
            previous_target = getattr(config_service.get_settings(), "ui_target_language", data)
            if config_service.update_settings(updates):
                logger.info(f"UI target updated: lang={data}")
            else:
                self.view.set_language_selection(target=previous_target)
                logger.error(f"Failed to persist target selection: {data}")
        except Exception as e:
            logger.error(f"Failed to persist target selection: {e}")

    def _perform_language_swap(self):
        """Perform the language swap logic and persist changes."""
        src_data = self.view.source_combo.currentData()
        tgt_data = self.view.target_combo.currentData()

        if src_data == "auto":
            new_source = tgt_data
            new_target = tgt_data
            self.view.set_language_selection(source=new_source)
            logger.info(f"Swap with 'auto' source: source set to '{new_source}'")
        else:
            new_source = tgt_data
            new_target = src_data
            self.view.set_language_selection(source=new_source, target=new_target)
            logger.info(f"Swapped languages: source='{new_source}', target='{new_target}'")

        # Common settings update logic
        updates = {
            "ui_source_language": new_source,
            "ui_target_language": new_target,
        }
        try:
            if not config_service.update_settings(updates):
                self.view.set_language_selection(source=src_data, target=tgt_data)
                logger.error("Failed to persist swap")
        except Exception as e:
            logger.error(f"Failed to persist swap: {e}")


    def _on_swap_clicked(self):
        """Swap button behavior"""
        self._perform_language_swap()

    def _setup_worker(self, worker_class, *args):
        """Generic method to set up and start a worker in a background thread."""
        worker = worker_class(*args)
        thread = QThread()
        worker.moveToThread(thread)

        worker.finished.connect(self._on_translation_finished)
        thread.started.connect(worker.run)

        # Stop the worker thread from the worker thread so GUI event-loop load
        # cannot delay delivery of the completion request.
        worker.finished.connect(thread.quit, Qt.DirectConnection)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        # Watchdog timer setup
        api_timeout = config_service.get_setting("api_timeout")
        try:
            api_timeout = int(api_timeout)
        except (TypeError, ValueError):
            api_timeout = None
        if api_timeout is None or not API_TIMEOUT_MIN <= api_timeout <= API_TIMEOUT_MAX:
            api_timeout = API_TIMEOUT_DEFAULT
        watchdog_timeout = max(api_timeout * 2, 60)  # Reduced minimum to 60 seconds
        
        watchdog = QTimer(self)
        watchdog.setSingleShot(True)
        watchdog_active = [True]  # Mutable flag for closure
        
        def _force_thread_termination():
            if not watchdog_active[0]:
                return
            try:
                if not thread.isRunning():
                    logger.debug("Watchdog triggered but thread already finished")
                    return
                
                # Disconnect self to prevent re-entry
                try:
                    watchdog.timeout.disconnect(_force_thread_termination)
                except (RuntimeError, TypeError):
                    pass
                    
                logger.error(f"Watchdog timeout: forcing thread termination after {watchdog_timeout}s")
                thread.quit()
                thread.wait(1000)
                if thread.isRunning():
                    logger.warning("Thread still running after quit, forcing termination")
                    thread.terminate()
                    thread.wait(1000)
                    if thread.isRunning():
                        logger.error("Thread still running after terminate! System instability possible.")
            except Exception as e:
                logger.error(f"Exception during watchdog thread termination: {e}")
        
        def cleanup_watchdog():
            """Stop watchdog and clean up resources."""
            if not watchdog_active[0]:
                return
            watchdog_active[0] = False
            try:
                logger.debug("Cleaning up watchdog timer")
                # Disconnect signals to prevent dangling references
                try:
                    thread.finished.disconnect(cleanup_watchdog)
                except (RuntimeError, TypeError):
                    pass
                # Schedule deletion
                watchdog.deleteLater()
                logger.debug("Watchdog cleanup completed")
            except Exception as e:
                logger.debug(f"Watchdog cleanup error: {e}")
        
        watchdog.timeout.connect(_force_thread_termination)
        

        
        # Connect cleanup signals
        thread.finished.connect(cleanup_watchdog)
        
        # Start watchdog immediately BEFORE thread ensures 100% coverage
        if watchdog_active[0]:
            logger.debug(f"Starting watchdog with {watchdog_timeout}s timeout")
            watchdog.start(watchdog_timeout * 1000)
            
        # Now start the thread
        thread.start()
        return worker, thread



    def _on_translate_clicked(self):
        """Translate or Style the text from the original_text field based on mode."""
        if self._translation_start_time is not None:
            self._cancel_active_request()
            return

        # Check if button is logically disabled (fake disabled state to preserve cursor events)
        if self.view.translate_btn and self.view.translate_btn.property("logically_disabled"):
            ready, _msg = self._is_api_ready()
            if not ready:
                logger.debug("Translate button clicked but is logically disabled")
                return
            self._restore_enabled_translate_visuals()
            
        text = self.view.original_text.toPlainText().strip()
        if not text:
            logger.info("Translate/Style button clicked with empty original_text")
            return

        # Guard: API must be ready (key configured/valid)
        ready, _msg = self._is_api_ready()
        if not ready:
            self._update_api_state_and_ui()
            return

        is_style = self._is_style_mode_selected()
        settings = self._begin_request_ui_state(is_style=is_style)

        if is_style:
            self._start_style_request(text, settings)
            return

        self._start_translation_request(text)

    def _on_translation_finished(self, success: bool, result: str):
        """Handle completion of background translation."""
        try:
            if success:
                self._apply_successful_translation_result(result)
            else:
                self._apply_request_error_status(result, show_popup_for_unknown=True)
        finally:
            self._finalize_translation_request(
                success=success,
                refresh_api_state=not success,
            )

    def _cancel_active_request(self):
        """Cancel active translation/style request and restore UI state."""
        translation_worker = getattr(self, "_translation_worker", None)
        translation_thread = getattr(self, "_translation_thread", None)
        style_worker = getattr(self, "_style_worker", None)
        style_thread = getattr(self, "_style_thread", None)

        try:
            translation_running = translation_thread is not None and translation_thread.isRunning()
        except RuntimeError:  # C++ object already deleted
            translation_running = False
        try:
            style_running = style_thread is not None and style_thread.isRunning()
        except RuntimeError:
            style_running = False

        if translation_running or not style_running:
            worker = translation_worker
            thread = translation_thread
        else:
            worker = style_worker
            thread = style_thread

        if worker is not None:
            for signal, handler in (
                (worker.finished, self._on_translation_finished),
            ):
                try:
                    signal.disconnect(handler)
                except (RuntimeError, TypeError):
                    pass

            if hasattr(worker, "request_cancel"):
                try:
                    worker.request_cancel()
                except Exception as e:
                    logger.debug(f"Failed to request worker cancellation: {e}")

        if thread is not None:
            try:
                if thread.isRunning():
                    thread.quit()
            except Exception as e:
                logger.debug(f"Failed to quit worker thread: {e}")

        self._translation_start_time = None
        self.view.set_status("Cancelled", "error")
        self._restore_request_controls()

    def shutdown_workers(self):
        """Cancel and wait for all live request worker threads during application shutdown."""
        pairs = (
            (getattr(self, "_translation_worker", None), getattr(self, "_translation_thread", None)),
            (getattr(self, "_style_worker", None), getattr(self, "_style_thread", None)),
        )

        threads = []
        for worker, thread in pairs:
            if worker is not None and hasattr(worker, "request_cancel"):
                try:
                    worker.request_cancel()
                except Exception as e:
                    logger.debug(f"Failed to request worker cancellation during shutdown: {e}")
            try:
                if thread is not None and thread.isRunning():
                    thread.quit()
                    threads.append(thread)
            except RuntimeError:  # C++ object already deleted
                pass

        deadline = time.monotonic() + 5.0
        while any(thread.isRunning() for thread in threads):
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                break
            for thread in threads:
                if thread.isRunning():
                    thread.wait(min(100, remaining_ms))

        for thread in threads:
            if thread.isRunning():
                logger.warning("Overlay worker thread did not stop during shutdown")

    def _start_loading_animation(self, base_text: str, compact: bool):
        """Start the loading animation with spinning icon and animated dots."""
        try:
            self._loading_base_text = base_text
            self._loading_rotation = 0
            self._loading_dots_count = 0
            self._loading_compact = compact

            # Store original icon for restoration
            if self.view.translate_btn:
                self._original_icon = self.view.translate_btn.icon()

            # Create and start timer (60ms interval for smooth animation)
            if self._loading_timer is None:
                self._loading_timer = QTimer(self)
                self._loading_timer.timeout.connect(self._update_loading_animation)
            self._loading_timer.start(60)

            # Initial update
            self._update_loading_animation()
            logger.debug("Loading animation started")
        except Exception as e:
            logger.debug(f"Failed to start loading animation: {e}")

    def _stop_loading_animation(self):
        """Stop the loading animation and restore original icon."""
        try:
            if self._loading_timer is not None:
                self._loading_timer.stop()

            # Restore original icon
            if self.view.translate_btn and hasattr(self, "_original_icon"):
                self.view.translate_btn.setIcon(self._original_icon)

            logger.debug("Loading animation stopped")
        except Exception as e:
            logger.debug(f"Failed to stop loading animation: {e}")

    def _update_loading_animation(self):
        """Update the loading animation: rotate icon and cycle dots."""
        try:
            if not self.view.translate_btn:
                return

            # Update rotation (15 degrees per tick for slower animation)
            self._loading_rotation = (self._loading_rotation + 15) % 360

            # Rotate the icon (only in compact mode)
            is_compact = getattr(self, "_loading_compact", False)
            if is_compact and hasattr(self, "_original_icon") and self._original_icon:
                # Get pixmap from original icon
                pixmap = self._original_icon.pixmap(QSize(16, 16))
                if not pixmap.isNull():
                    # Apply rotation transform
                    transform = QTransform()
                    transform.rotate(self._loading_rotation)
                    rotated_pixmap = pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
                    from PySide6.QtGui import QIcon
                    self.view.translate_btn.setIcon(QIcon(rotated_pixmap))

            # Update dots (cycle every 90 degrees / 6 ticks for slower animation)
            if self._loading_rotation % 90 == 0:
                self._loading_dots_count = (self._loading_dots_count + 1) % 4

            # Update text with animated dots (only in non-compact mode)
            if not getattr(self, "_loading_compact", False):
                # Use fixed width: dots + spaces to prevent text jumping
                dots = "." * self._loading_dots_count + " " * (3 - self._loading_dots_count)
                self.view.translate_btn.setText(f"  {self._loading_base_text}{dots}")

            # Update status label with animated dots
            if self.view.status_label:
                dots = "." * self._loading_dots_count + " " * (3 - self._loading_dots_count)
                self.view.status_label.setText(f"Request sent{dots}")

        except Exception as e:
            logger.debug(f"Failed to update loading animation: {e}")

    def _copy_translated_to_clipboard(self):
        """Copy translated text to clipboard."""
        self._copy_text_to_clipboard(self.view.translated_text, self.view.copy_translated_btn, "Translated")

    def _on_reader_mode_clicked(self):
        """Handle reader mode button click."""
        try:
            translated_text = self.view.translated_text.toPlainText().strip()
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
                self.view.set_status("Reader mode unavailable")
        except Exception as e:
            logger.error(f"Failed to open reader mode: {e}")
            self.view.set_status("Failed to open reader")


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
