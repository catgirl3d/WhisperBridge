"""
UI service extracted from QtApp.

This module was extracted from src/whisperbridge/ui_qt/app.py to centralize
window creation, display and lifecycle logic. Methods moved from QtApp:

- show_main_window
- hide_main_window_to_tray
- open_settings
- show_overlay_window
- hide_overlay_window
- _handle_worker_finished -> handle_worker_finished
- _handle_copy_translate -> handle_copy_translate

The service owns:
- main_window (MainWindow)
- tray_manager (TrayManager)
- overlay_windows (dict of OverlayWindow)
- selection_overlay (SelectionOverlayQt)
- settings_dialog (SettingsDialog)

It provides slots/handlers that can be connected to worker signals so UI-related
work happens in the main Qt thread.
"""

from typing import Optional, Dict, Tuple
from PySide6.QtCore import Slot, QThread
from PySide6.QtWidgets import QApplication
from loguru import logger as _default_logger

# UI widgets (import from ui_qt package)
from ..ui_qt.main_window import MainWindow
from ..ui_qt.tray import TrayManager
from ..ui_qt.overlay_window import OverlayWindow
from ..ui_qt.selection_overlay import SelectionOverlayQt
from ..ui_qt.settings_dialog import SettingsDialog

# Clipboard accessor (fallback)
from .clipboard_service import get_clipboard_service


class UIService:
    """
    Service responsible for managing UI windows and overlay lifecycle.

    Public methods:
      - show_main_window()
      - hide_main_window_to_tray()
      - open_settings()
      - show_overlay_window(original_text, translated_text, position=None, overlay_id="main")
      - hide_overlay_window(overlay_id="main")
      - handle_worker_finished(original_text, translated_text, overlay_id)
      - handle_copy_translate(clipboard_text, translated_text, auto_copy=False)
    """

    def __init__(
        self,
        main_window: Optional[MainWindow] = None,
        tray_manager: Optional[TrayManager] = None,
        selection_overlay: Optional[SelectionOverlayQt] = None,
        settings_dialog: Optional[SettingsDialog] = None,
        overlay_windows: Optional[Dict[str, OverlayWindow]] = None,
        clipboard_service=None,
        logger=None,
        app=None
    ):
        # Accept injected dependencies for easier wiring/testing
        self.main_window = main_window
        self.tray_manager = tray_manager
        self.selection_overlay = selection_overlay
        self.settings_dialog = settings_dialog
        # Use provided dict or initialize empty dict
        self.overlay_windows: Dict[str, OverlayWindow] = overlay_windows if overlay_windows is not None else {}
        # Clipboard service may be None; fallback to get_clipboard_service() inside methods
        self._clipboard_service = clipboard_service
        # Logger fallback
        self.logger = logger or _default_logger

        # Lazy initialization: set to None if not provided
        if self.main_window is None:
            self.main_window = None
        if self.selection_overlay is None:
            self.selection_overlay = None
        if self.tray_manager is None:
            # Create tray manager early as it's lightweight and needed for notifications
            try:
                # Use app methods as callbacks if available, otherwise no-op lambdas
                on_show = getattr(app, "show_main_window_signal", None).emit if app else (lambda: None)
                on_toggle = getattr(app, "toggle_overlay_signal", None).emit if app else (lambda: None)
                on_open = getattr(app, "show_settings_signal", None).emit if app else (lambda: None)
                on_exit = getattr(app, "exit_app", None) or (lambda: None)
                on_activate = getattr(app, "activate_ocr", None) or (lambda: None)

                self.tray_manager = TrayManager(
                    on_show_main_window=on_show,
                    on_toggle_overlay=on_toggle,
                    on_open_settings=on_open,
                    on_exit_app=on_exit,
                    on_activate_ocr=on_activate
                )
                if not self.tray_manager.create():
                    self.logger.warning("UIService: Failed to initialize system tray")
                else:
                    self.logger.debug("UIService: TrayManager created and shown")
            except Exception as e:
                self.logger.error(f"UIService: Failed to create TrayManager: {e}", exc_info=True)

    # --- Main window operations ------------------------------------------------

    def _create_main_window(self):
        """Create the main window (called lazily in main thread)."""
        try:
            from ..ui_qt.app import get_qt_app  # To get app for callbacks
            app = get_qt_app()
            on_save_cb = getattr(app, "_on_settings_saved", None)
            self.main_window = MainWindow(on_save_callback=on_save_cb)
            # Connect close-to-tray signal
            if app and hasattr(app, "hide_main_window_to_tray"):
                try:
                    self.main_window.closeToTrayRequested.connect(app.hide_main_window_to_tray)
                except Exception:
                    pass
            self.logger.debug("UIService: MainWindow created")
        except Exception as e:
            self.logger.error(f"UIService: Failed to create MainWindow: {e}", exc_info=True)
            self.main_window = None

    def _create_selection_overlay(self, app):
        """Create the selection overlay (called lazily in main thread)."""
        try:
            self.selection_overlay = SelectionOverlayQt()
            # Connect signals to app handlers if available
            if app:
                if hasattr(self.selection_overlay, "selectionCompleted") and hasattr(app, "_on_selection_completed"):
                    try:
                        self.selection_overlay.selectionCompleted.connect(app._on_selection_completed)
                    except Exception:
                        pass
                if hasattr(self.selection_overlay, "selectionCanceled") and hasattr(app, "_on_selection_canceled"):
                    try:
                        self.selection_overlay.selectionCanceled.connect(app._on_selection_canceled)
                    except Exception:
                        pass
            self.logger.debug("UIService: SelectionOverlayQt created")
        except Exception as e:
            self.logger.error(f"UIService: Failed to create SelectionOverlayQt: {e}", exc_info=True)
            self.selection_overlay = None

    def show_main_window(self):
        """Show and activate the main settings window."""
        # Thread check
        if QThread.currentThread() != QApplication.instance().thread():
            self.logger.error("show_main_window called from wrong thread!")
            return

        self.logger.info("UIService: show_main_window() called")
        try:
            # Lazy creation
            if self.main_window is None:
                self._create_main_window()
                if self.main_window is None:
                    self.logger.error("Failed to create main_window")
                    return

            self.main_window.show()
            # Keep same activation behavior as QtApp
            try:
                self.main_window.raise_()
                self.main_window.activateWindow()
            except Exception:
                # Some platforms may not support raise_/activateWindow
                pass
            self.logger.debug("Main window shown and activated by UIService")
        except Exception as e:
            self.logger.error(f"UIService.show_main_window error: {e}", exc_info=True)

    def hide_main_window_to_tray(self):
        """Hide the main window (minimize to tray)."""
        self.logger.info("UIService: hide_main_window_to_tray() called")
        try:
            if self.main_window:
                self.main_window.hide()
                self.logger.debug("Main window hidden by UIService")
        except Exception as e:
            self.logger.error(f"UIService.hide_main_window_to_tray error: {e}", exc_info=True)

    # --- Settings dialog ------------------------------------------------------

    def open_settings(self):
        """Open (or create) the settings dialog and bring it to front."""
        # Thread check
        if QThread.currentThread() != QApplication.instance().thread():
            self.logger.error("open_settings called from wrong thread!")
            return

        self.logger.info("UIService: open_settings() called")
        try:
            # Create dialog if it doesn't exist or was closed
            if self.settings_dialog is None or not getattr(self.settings_dialog, "isVisible", lambda: False)():
                # Ensure main_window exists for parenting
                if self.main_window is None:
                    self._create_main_window()
                # Parent to main_window if available
                parent = self.main_window if self.main_window else None
                try:
                    self.settings_dialog = SettingsDialog(parent=parent)
                    # Reset reference when dialog finishes
                    self.settings_dialog.finished.connect(lambda: setattr(self, "settings_dialog", None))
                except Exception as e:
                    self.logger.error(f"UIService: Failed to create SettingsDialog: {e}", exc_info=True)
                    # Notify user via tray if possible
                    if self.tray_manager:
                        self.tray_manager.show_notification("WhisperBridge", f"Failed to open settings: {e}")
                    return

            # Show and activate dialog
            try:
                self.settings_dialog.show()
                self.settings_dialog.raise_()
                self.settings_dialog.activateWindow()
            except Exception:
                # Best-effort activation
                pass

        except Exception as e:
            self.logger.error(f"UIService.open_settings error: {e}", exc_info=True)
            if self.tray_manager:
                try:
                    self.tray_manager.show_notification("WhisperBridge", f"Settings dialog error: {e}")
                except Exception:
                    self.logger.debug("Failed to show tray notification for settings error")

    # --- Overlay windows -------------------------------------------------------

    def show_overlay_window(
        self,
        original_text: str,
        translated_text: str,
        position: Optional[Tuple[int, int]] = None,
        overlay_id: str = "main"
    ):
        """Show or create an overlay window with translation results.

        Preserves create-if-not-exist semantics from QtApp.
        """
        self.logger.info("UIService: === SHOW_OVERLAY_WINDOW CALLED ===")
        try:
            # Log truncated versions for parity with previous implementation
            self.logger.info(f"Original text: '{(original_text or '')[:50]}{'...' if original_text and len(original_text) > 50 else ''}'")
            self.logger.info(f"Translated text: '{(translated_text or '')[:50]}{'...' if translated_text and len(translated_text) > 50 else ''}'")
            self.logger.info(f"Position: {position}, Overlay ID: {overlay_id}")

            # Create overlay window if missing
            if overlay_id not in self.overlay_windows or getattr(self.overlay_windows.get(overlay_id), "is_destroyed", False):
                try:
                    self.overlay_windows[overlay_id] = OverlayWindow()
                    self.logger.debug(f"UIService: Created OverlayWindow for id '{overlay_id}'")
                except Exception as e:
                    self.logger.error(f"UIService: Failed to create OverlayWindow '{overlay_id}': {e}", exc_info=True)
                    if self.tray_manager:
                        self.tray_manager.show_notification("WhisperBridge", f"Overlay creation failed: {e}")
                    return

            overlay = self.overlay_windows[overlay_id]
            try:
                overlay.show_overlay(original_text or "", translated_text or "", position)
                self.logger.info(f"Overlay '{overlay_id}' displayed successfully by UIService")
            except Exception as e:
                self.logger.error(f"UIService: Failed to show overlay '{overlay_id}': {e}", exc_info=True)
                if self.tray_manager:
                    try:
                        self.tray_manager.show_notification("WhisperBridge", f"Overlay display error: {e}")
                    except Exception:
                        self.logger.debug("Failed to show tray notification for overlay display error")

        except Exception as e:
            self.logger.error(f"Unexpected error in UIService.show_overlay_window: {e}", exc_info=True)

    def hide_overlay_window(self, overlay_id: str = "main"):
        """Hide an overlay window if present."""
        try:
            if overlay_id in self.overlay_windows:
                try:
                    self.overlay_windows[overlay_id].hide_overlay()
                except Exception:
                    # Best-effort hide
                    try:
                        self.overlay_windows[overlay_id].hide()
                    except Exception:
                        pass
        except Exception as e:
            self.logger.error(f"UIService.hide_overlay_window error for id '{overlay_id}': {e}", exc_info=True)

    def toggle_overlay(self):
        """Toggle overlay visibility. If no overlay exists, create a basic fullscreen overlay."""
        self.logger.info("UIService: toggling overlay")
        try:
            if self.overlay_windows:
                overlay_id = next(iter(self.overlay_windows.keys()))
                overlay = self.overlay_windows[overlay_id]
                try:
                    if getattr(overlay, "is_overlay_visible", lambda: False)():
                        overlay.hide_overlay()
                        self.logger.debug(f"Overlay {overlay_id} hidden")
                    else:
                        overlay.show_overlay("", "")
                        self.logger.debug(f"Overlay {overlay_id} shown")
                    return
                except Exception as e:
                    self.logger.error(f"UIService: Error while toggling existing overlay: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"UIService: Error while accessing overlay_windows: {e}", exc_info=True)

        # No overlays exist — create a basic fullscreen overlay (M0) and show it
        try:
            self.logger.info("UIService: No existing overlay found — creating a basic fullscreen overlay (M0)")
            overlay_id = "main"
            self.overlay_windows[overlay_id] = OverlayWindow()
            self.overlay_windows[overlay_id].show_overlay("", "")
            self.logger.info(f"Created and showed overlay '{overlay_id}'")
        except Exception as e:
            self.logger.error(f"UIService: Failed to create/show overlay: {e}", exc_info=True)

    def activate_ocr(self):
        """Activate OCR selection overlay in the main Qt thread."""
        # Thread check
        if QThread.currentThread() != QApplication.instance().thread():
            self.logger.error("activate_ocr called from wrong thread!")
            return
        try:
            if self.selection_overlay is None:
                # Lazily create and wire selection overlay
                try:
                    from ..ui_qt.app import get_qt_app
                    app = get_qt_app()
                except Exception:
                    app = None
                self._create_selection_overlay(app)
                if self.selection_overlay is None:
                    self.logger.error("Failed to create selection_overlay")
                    return
            self.selection_overlay.start()
            self.logger.debug("Selection overlay started")
        except Exception as e:
            self.logger.error(f"UIService.activate_ocr error: {e}", exc_info=True)

    # --- Slots / handlers -----------------------------------------------------

    @Slot(str, str, str)
    def handle_worker_finished(self, original_text: str, translated_text: str, overlay_id: str):
        """
        Handler for worker finished events.

        Preserves QtApp._handle_worker_finished semantics: normalize overlay id -> "ocr"
        to avoid creating duplicate windows for OCR results.
        """
        try:
            self.logger.info("UIService.handle_worker_finished invoked in main thread")
            canonical_overlay_id = "ocr"
            # Always show OCR results in canonical overlay
            self.show_overlay_window(original_text, translated_text, overlay_id=canonical_overlay_id)
        except Exception as e:
            self.logger.error(f"UIService.handle_worker_finished error: {e}", exc_info=True)

    @Slot(str, str, bool)
    def handle_copy_translate(self, clipboard_text: str, translated_text: str, auto_copy: bool = False):
        """
        Handle copy->translate results.

        - Show overlay (overlay_id='copy_translate')
        - Optionally copy translated_text to clipboard AFTER overlay is shown
        - Use tray_manager for notifications on errors (same as QtApp)
        """
        try:
            # Show overlay first
            self.show_overlay_window(clipboard_text, translated_text, overlay_id="copy_translate")

            # If auto-copy requested, copy AFTER overlay is shown
            if auto_copy:
                clipboard_service = self._clipboard_service or get_clipboard_service()
                try:
                    if clipboard_service and clipboard_service.copy_text(translated_text):
                        self.logger.info("Translated text copied to clipboard (auto_copy_translated enabled)")
                    else:
                        self.logger.warning("Failed to copy translated text to clipboard (ClipboardService.copy_text returned False or service unavailable)")
                except Exception as e:
                    self.logger.error(f"UIService: Auto-copy failed: {e}", exc_info=True)
 
            self.logger.info("Copy-translate overlay shown successfully by UIService")
 
        except Exception as e:
            self.logger.error(f"UIService.handle_copy_translate error: {e}", exc_info=True)
            if self.tray_manager:
                try:
                    self.tray_manager.show_notification("WhisperBridge", f"Copy-translate overlay error: {e}")
                except Exception:
                    self.logger.debug("Failed to show tray notification for copy-translate error")
 
    # --- Additional UI helpers moved from QtApp --------------------------------
    def show_tray_notification(self, title: str, message: str):
        """Show a notification through the tray manager (if available)."""
        try:
            if self.tray_manager:
                self.tray_manager.show_notification(title, message)
                self.logger.debug(f"Tray notification shown: {title}")
        except Exception as e:
            self.logger.error(f"UIService.show_tray_notification error: {e}", exc_info=True)
 
    def update_tray_status(self, is_active: bool = False, has_error: bool = False, is_loading: bool = False):
        """Update the tray icon status (kept for parity with QtApp.update_tray_status)."""
        # Keep behavior minimal (QtApp previously just logged); expose hook for future TrayManager behavior
        try:
            self.logger.debug(f"UIService.update_tray_status requested: active={is_active}, error={has_error}, loading={is_loading}")
            # Optionally, the tray manager could reflect status here in future
        except Exception as e:
            self.logger.error(f"UIService.update_tray_status error: {e}", exc_info=True)
 
    def update_window_opacity(self, opacity: float):
        """Update window opacity for all managed windows."""
        try:
            opacity = max(0.1, min(1.0, opacity))
            # Update main window opacity
            if self.main_window:
                try:
                    self.main_window.setWindowOpacity(opacity)
                except Exception:
                    pass
            # Update overlay windows opacity
            for overlay in list(self.overlay_windows.values()):
                try:
                    overlay.setWindowOpacity(opacity)
                except Exception:
                    pass
            self.logger.debug(f"UIService: Window opacity updated to: {opacity}")
        except Exception as e:
            self.logger.error(f"UIService.update_window_opacity error: {e}", exc_info=True)
 
    def hide_main_window(self):
        """Hide the main window (minimize to tray)."""
        try:
            if self.main_window:
                try:
                    self.main_window.hide()
                    self.logger.debug("UIService: Main window hidden")
                except Exception:
                    pass
        except Exception as e:
            self.logger.error(f"UIService.hide_main_window error: {e}", exc_info=True)
 
    def update_theme(self, theme: str):
        """Persist theme setting and log (keeps parity with QtApp.update_theme)."""
        try:
            from ..services.config_service import config_service
            config_service.set_setting("theme", theme)
            self.logger.debug(f"UIService: theme updated to: {theme}")
        except Exception as e:
            self.logger.error(f"UIService.update_theme error: {e}", exc_info=True)
 
    def shutdown_ui(self):
        """Shutdown/cleanup UI-specific resources: tray, overlays, main window."""
        try:
            self.logger.info("UIService: shutting down UI resources")
            # Dispose tray manager
            try:
                if self.tray_manager:
                    self.tray_manager.dispose()
                    self.logger.debug("UIService: Tray manager disposed")
            except Exception as e:
                self.logger.warning(f"UIService: Error disposing tray manager: {e}")
            # Close overlay windows
            try:
                for overlay in list(self.overlay_windows.values()):
                    try:
                        overlay.close()
                    except Exception:
                        pass
                self.overlay_windows.clear()
                self.logger.debug("UIService: Overlay windows closed and cleared")
            except Exception as e:
                self.logger.warning(f"UIService: Error closing overlay windows: {e}")
            # Close main window
            try:
                if self.main_window:
                    try:
                        self.main_window.close()
                        self.logger.debug("UIService: Main window closed")
                    except Exception:
                        pass
            except Exception as e:
                self.logger.warning(f"UIService: Error closing main window: {e}")
        except Exception as e:
            self.logger.error(f"UIService.shutdown_ui error: {e}", exc_info=True)