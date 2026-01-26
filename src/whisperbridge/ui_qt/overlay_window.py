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
from PySide6.QtGui import QAction, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QMenu,
)

from ..services.config_service import config_service, SettingsObserver
from ..utils.language_utils import detect_language, get_language_name
from ..core.config import validate_api_key_format, SUPPORTED_PROVIDERS
from .styled_overlay_base import StyledOverlayWindow
from .workers import TranslationWorker, StyleWorker
from .overlay_ui_builder import OverlayUIBuilder, TranslatorSettingsDialog


class _OverlaySettingsObserver(SettingsObserver):
    """Lightweight observer to react to settings changes affecting API readiness."""
    def __init__(self, owner):
        self._owner = owner

    def on_settings_changed(self, key, old_value, new_value):
        try:
            if key in ("api_provider", "openai_api_key", "google_api_key", "deepl_api_key", "api_timeout"):
                if hasattr(self._owner, "_update_api_state_and_ui"):
                    self._owner._update_api_state_and_ui()
            elif key == "text_styles":
                # Refresh style combo when user modifies text styles in settings
                if hasattr(self._owner, "ui_builder") and hasattr(self._owner.ui_builder, "refresh_styles"):
                    self._owner.ui_builder.refresh_styles()
        except Exception as e:
            logger.debug(f"Overlay observer change handler error: {e}")

    def on_settings_loaded(self, settings):
        self.on_settings_changed("loaded", None, None)

    def on_settings_saved(self, settings):
        self.on_settings_changed("saved", None, None)


class OverlayWindow(StyledOverlayWindow):
    """Overlay window for displaying translation results."""

    def __init__(self):
        """Initialize the overlay window.

        Uses OverlayUIBuilder to create all UI components, then assembles them into the layout.
        The overlay manages signals, settings, and business logic; builder handles pure UI construction.
        """
        super().__init__(title="Translator")
        self._translator_settings_dialog = None
        self._translation_start_time = None

        # Create UI builder
        self.ui_builder = OverlayUIBuilder()
        
        # Build UI and unpack DTO
        ui = self.ui_builder.build_ui(self)
        
        # === Unpack all 35 components from DTO ===
        # Layout containers
        self.info_row_widget = ui.info_row
        self.footer_widget = ui.footer_widget
        
        # Info row widgets
        self.mode_label = ui.mode_label
        self.mode_combo = ui.mode_combo
        self.style_combo = ui.style_combo
        self.edit_styles_btn = ui.edit_styles_btn
        self.detected_lang_label = ui.detected_lang_label
        self.auto_swap_checkbox = ui.auto_swap_checkbox
        
        # Language row widgets
        self.source_combo = ui.source_combo
        self.target_combo = ui.target_combo
        self.swap_btn = ui.swap_btn
        self.original_label = ui.original_label
        self.language_spacer = ui.language_spacer
        
        # Text panels
        self.original_text = ui.original_text
        self.translated_text = ui.translated_text
        self.translated_label = ui.translated_label
        self.original_panel = ui.original_panel
        self.translated_panel = ui.translated_panel
        
        # Action buttons
        self.translate_btn = ui.translate_btn
        self.reader_mode_btn = ui.reader_mode_btn
        self.clear_original_btn = ui.clear_original_btn
        self.copy_original_btn = ui.copy_original_btn
        self.clear_translated_btn = ui.clear_translated_btn
        self.copy_translated_btn = ui.copy_translated_btn
        self.original_buttons = ui.original_buttons
        self.translated_buttons = ui.translated_buttons
        
        # Footer
        self.status_label = ui.status_label
        self.provider_badge = ui.provider_badge
        self.close_btn = ui.close_btn
        
        # Icons
        self.icon_translation = ui.icon_translation
        self.icon_check_green = ui.icon_check_green
        self.close_icon_normal = ui.close_icon_normal
        self.close_icon_hover = ui.close_icon_hover
        
        # Hideable elements
        self.hideable_elements = ui.hideable_elements

        # Initialize provider menu
        self._setup_provider_menu()

        # Assemble the built UI into the window's content layout
        layout = self.content_layout
        layout.setSpacing(6)
        layout.addWidget(self.info_row_widget)
        layout.addLayout(ui.language_row)
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
        if hasattr(self, "edit_styles_btn") and self.edit_styles_btn:
            self.edit_styles_btn.clicked.connect(self._open_stylist_settings)
        if self.translate_btn:
            self.translate_btn.clicked.connect(self._on_translate_clicked)
        self.reader_mode_btn.clicked.connect(self._on_reader_mode_clicked)
        self.clear_original_btn.clicked.connect(self._clear_original_text)
        self.copy_original_btn.clicked.connect(self._copy_original_to_clipboard)
        self.clear_translated_btn.clicked.connect(self._clear_translated_text)
        self.copy_translated_btn.clicked.connect(self._copy_translated_to_clipboard)
        self.close_btn.clicked.connect(self.dismiss)
        self.close_btn.installEventFilter(self)
        # Install event filter on original_text to capture Ctrl+Enter for translation
        self.original_text.installEventFilter(self)

    def _on_mode_changed(self, index: int):
        """Handle mode combo box changes (Translate vs Style)."""
        try:
            mode_text = self.mode_combo.currentText().strip().lower()
            self._apply_mode_visibility(mode_text)
        except Exception as e:
            logger.debug(f"Failed to handle mode change: {e}")



    def _open_stylist_settings(self):
        """Open the main settings dialog and navigate to the Stylist tab."""
        try:
            from .settings_dialog import SettingsDialog
            from .app import get_qt_app
            
            app = get_qt_app()
            if not app:
                logger.warning("Qt app not available")
                return
            
            # Create settings dialog if needed
            if not hasattr(app, '_main_settings_dialog') or app._main_settings_dialog is None:
                app._main_settings_dialog = SettingsDialog(app, parent=None)
            
            dialog = app._main_settings_dialog
            
            # Find and select the Stylist tab
            if hasattr(dialog, 'tab_widget'):
                for i in range(dialog.tab_widget.count()):
                    if dialog.tab_widget.tabText(i) == "Stylist":
                        dialog.tab_widget.setCurrentIndex(i)
                        logger.debug("Switched to Stylist tab")
                        break
            
            # Show the dialog
            if dialog.isHidden():
                dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            logger.info("Opened settings dialog on Stylist tab")
                
        except Exception as e:
            logger.error(f"Failed to open stylist settings: {e}", exc_info=True)

    def _apply_mode_visibility(self, mode: str):
        """Apply visibility changes based on selected mode."""
        try:
            mode = (mode or "").strip().lower()
            is_style = mode == "style"

            # Show/hide style combo based on mode
            if hasattr(self, "style_combo") and self.style_combo:
                self.style_combo.setVisible(is_style)
            
            if hasattr(self, "edit_styles_btn") and self.edit_styles_btn:
                self.edit_styles_btn.setVisible(is_style)

            # Update translate button text and icon
            if hasattr(self, "translate_btn") and self.translate_btn:
                try:
                    compact = getattr(getattr(self, "_cached_settings", None), "compact_view", False)
                    if not compact:
                        new_text = self.ui_builder.get_translate_button_text(is_style)
                        self.translate_btn.setText(new_text)
                    # Only set icon if button is enabled (not in disabled state)
                    if self.translate_btn.isEnabled():
                        self.translate_btn.setIcon(self.icon_translation)
                        self.translate_btn.setIconSize(QSize(14, 14))
                    # Force a style refresh to reflect label changes instantly
                    self.translate_btn.style().unpolish(self.translate_btn)
                    self.translate_btn.style().polish(self.translate_btn)
                    self.translate_btn.update()
                except Exception:
                    pass

            logger.debug(f"Mode visibility applied: mode='{mode}', is_style={is_style}")

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

            # Force layout recalculation to eliminate spacing artifacts
            self.content_layout.invalidate()

            logger.debug(f"Language controls visibility updated: auto_swap={auto_swap}, show_controls={show_controls}")
        except Exception as e:
            logger.debug(f"Failed to update language controls visibility: {e}")




    def _is_api_ready(self) -> tuple[bool, str]:
        """Check whether API calls can proceed given current provider/key settings."""
        try:
            provider = (config_service.get_setting("api_provider") or "openai").strip().lower()
            if provider not in SUPPORTED_PROVIDERS:
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

            self.ui_builder.apply_disabled_translate_visuals(self.translate_btn, reason_msg, compact)
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

            # Determine compact mode safely
            compact = False
            try:
                compact = bool(getattr(getattr(self, "_cached_settings", None), "compact_view", False))
            except Exception:
                compact = False

            self.ui_builder.restore_enabled_translate_visuals(self.translate_btn, compact)
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
            if not hasattr(self, "provider_badge") or not self.provider_badge:
                return

            provider = (config_service.get_setting("api_provider") or "openai").strip().lower()
            if provider not in SUPPORTED_PROVIDERS:
                provider = "openai"

            # Map provider to display name and property
            provider_map = {
                "openai": ("OpenAI", "openai"),
                "google": ("Google", "google"),
                "deepl": ("DeepL", "deepl")
            }
            display_name, prop_value = provider_map[provider]

            self.provider_badge.setText(display_name)
            self.provider_badge.setProperty("provider", prop_value)
            self.provider_badge.setToolTip(f"Using {display_name}. Click to change provider.")

            # Force style refresh to apply QSS
            self.provider_badge.style().unpolish(self.provider_badge)
            self.provider_badge.style().polish(self.provider_badge)
            self.provider_badge.update()
        except Exception as e:
            logger.debug(f"Failed to update provider badge: {e}")

    def _setup_provider_menu(self):
        """Setup the dropdown menu for the provider badge."""
        try:
            if not hasattr(self, "provider_badge") or not self.provider_badge:
                return

            menu = QMenu(self.provider_badge)
            menu.setObjectName("providerMenu")
            # Enable translucent background for rounded corners in QSS
            menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            # Remove standard window frame/shadow to allow QSS control (matches ComboBox dropdowns)
            menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
            
            # OpenAI Action
            openai_action = QAction("OpenAI", self)
            openai_action.triggered.connect(lambda: self._switch_provider("openai"))
            menu.addAction(openai_action)

            # Google Action
            google_action = QAction("Google", self)
            google_action.triggered.connect(lambda: self._switch_provider("google"))
            menu.addAction(google_action)

            # DeepL Action
            deepl_action = QAction("DeepL", self)
            deepl_action.triggered.connect(lambda: self._switch_provider("deepl"))
            menu.addAction(deepl_action)

            self.provider_badge.setMenu(menu)
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
            if hasattr(self, "status_label") and self.status_label:
                if not ready:
                    self.ui_builder.apply_status_style(self.status_label, 'error')
                    self.status_label.setText(msg)
                else:
                    # Restore default style only if we are clearing an API key error
                    if "API key" in (self.status_label.text() or ""):
                        self.ui_builder.apply_status_style(self.status_label, 'default')
                        self.status_label.setText("")

            # Update provider badge
            self._update_provider_badge()

            # Enforce provider capabilities (disable Style mode for DeepL)
            try:
                provider = (config_service.get_setting("api_provider") or "openai").strip().lower()
                if hasattr(self, "mode_combo") and self.mode_combo:
                    style_idx = self._find_index_by_text(self.mode_combo, "Style")
                    if provider == "deepl":
                        # If currently on Style, switch to Translate before removing the item
                        try:
                            if (self.mode_combo.currentText() or "").strip().lower() == "style":
                                trans_idx = self._find_index_by_text(self.mode_combo, "Translate")
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

        # Re-apply mode-dependent UI so the Translate button text is restored in full mode
        if hasattr(self, "mode_combo"):
            self._apply_mode_visibility(self.mode_combo.currentText())

        logger.debug(f"Layout updated: compact={compact}, autohide={autohide}")

    def eventFilter(self, obj, event):
        """Handle events for child widgets, including hover for compact buttons."""
        if not hasattr(self, "original_text"):
            return super().eventFilter(obj, event)

        # Handle Ctrl+Enter in original_text to trigger translation
        if obj == self.original_text and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                logger.debug("Ctrl+Enter pressed in original_text, triggering translation")
                self._on_translate_clicked()
                return True

        # PanelWidget handles its own hover-based autohide; no-op here

        if obj == self.close_btn:
            if event.type() == QEvent.Type.Enter:
                self.close_btn.setIcon(self.close_icon_hover)
            elif event.type() == QEvent.Type.Leave:
                self.close_btn.setIcon(self.close_icon_normal)

        return super().eventFilter(obj, event)

    def show_overlay(self, original_text: str = "", translated_text: str = "", position: tuple[int, int] | None = None, error_message: str = ""):
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

        # Update status based on error or success
        if error_message:
            # Re-use the existing error parsing logic for consistent messages
            status_text = "Failed"
            err_lower = error_message.lower()
            if "quota" in err_lower:
                status_text = "Quota exceeded"
            elif "rate limit" in err_lower or "429" in err_lower:
                status_text = "Rate limit exceeded"
            elif "timeout" in err_lower:
                status_text = "Request timed out"
            elif "connection" in err_lower or "network" in err_lower:
                status_text = "Network error"
            elif "server error" in err_lower or "500" in err_lower:
                status_text = "Server error"
            elif "503" in err_lower:
                status_text = "Service unavailable"
            
            self.status_label.setText(status_text)
            self.ui_builder.apply_status_style(self.status_label, 'error')
        elif original_text:
            self.status_label.setText("Completed")
            self.ui_builder.apply_status_style(self.status_label, 'default')
        else:
            self.status_label.setText("")

        # Update reader button state after setting text
        self._update_reader_button_state()

        # Set focus to original text for quick typing
        self.original_text.setFocus()
        cursor = self.original_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.original_text.setTextCursor(cursor)

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
            self.ui_builder.set_combo_data(self.source_combo, new_source)
            logger.info(f"Swap with 'auto' source: source set to '{new_source}'")
        else:
            new_source = tgt_data
            new_target = src_data
            self.ui_builder.set_combo_data(self.source_combo, new_source)
            self.ui_builder.set_combo_data(self.target_combo, new_target)
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
        # Check if button is logically disabled (fake disabled state to preserve cursor events)
        if hasattr(self, "translate_btn") and self.translate_btn and self.translate_btn.property("logically_disabled"):
            logger.debug("Translate button clicked but is logically disabled")
            return
            
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
        self._translation_start_time = time.time()
        self.status_label.setText("Request sent...")
        self.ui_builder.apply_status_style(self.status_label, 'default')

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
                # Check if the result is empty
                if not result.strip():
                    self.status_label.setText("Model returned empty response")
                    self.ui_builder.apply_status_style(self.status_label, 'error')
                    self.translated_text.setPlainText("")
                    logger.warning("Model returned empty translation response")
                else:
                    self.translated_text.setPlainText(result)
                    self.ui_builder.apply_status_style(self.status_label, 'default')
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
            # Parse error message for status label
            status_text = "Failed"
            err_lower = error_message.lower()
            
            if "quota" in err_lower:
                status_text = "Quota exceeded"
            elif "rate limit" in err_lower or "429" in err_lower:
                status_text = "Rate limit exceeded"
            elif "timeout" in err_lower:
                status_text = "Request timed out"
            elif "connection" in err_lower or "network" in err_lower:
                status_text = "Network error"
            elif "server error" in err_lower or "500" in err_lower:
                status_text = "Server error"
            elif "503" in err_lower:
                status_text = "Service unavailable"

            # Only show popup for unknown errors; suppress for known API issues
            if status_text == "Failed":
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Translation failed", f"Translation error: {error_message}")
            
            logger.error(f"Translation failed: {error_message}")
        finally:
            # Update status with error indication
            if self._translation_start_time is not None:
                elapsed = time.time() - self._translation_start_time
                self.status_label.setText(f"{status_text} ({elapsed:.1f}s)")
                self._translation_start_time = None
            else:
                self.status_label.setText(status_text)
            
            # UX: emphasize error state in red (same styling priority as key-missing)
            try:
                self.ui_builder.apply_status_style(self.status_label, 'error')
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
                self.status_label.setText("Reader mode unavailable")
        except Exception as e:
            logger.error(f"Failed to open reader mode: {e}")
            self.status_label.setText("Failed to open reader")


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