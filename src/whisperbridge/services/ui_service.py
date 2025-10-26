"""
UI service

It provides slots/handlers that can be connected to worker signals so UI-related
work happens in the main Qt thread.
"""

import functools
from typing import Dict, Optional, Tuple

from loguru import logger as _default_logger
from PySide6.QtCore import QThread, Slot, Qt
from PySide6.QtWidgets import QApplication

# UI widgets (import from ui_qt package)
from ..ui_qt.main_window import MainWindow
from ..ui_qt.overlay_window import OverlayWindow
from ..ui_qt.reader_window import ReaderWindow
from ..ui_qt.selection_overlay import SelectionOverlayQt
from ..ui_qt.settings_dialog import SettingsDialog
from ..ui_qt.tray import TrayManager
from ..ui_qt.workers import CaptureOcrTranslateWorker
from ..utils.screen_utils import ScreenUtils, Rectangle

# Clipboard accessor (fallback)
from .clipboard_service import get_clipboard_service
from .notification_service import get_notification_service


def main_thread_only(func):
    """
    Decorator that ensures the method is called only from the main Qt thread.
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # 'self' - this is an instance of UIService
        app = QApplication.instance()
        if app and QThread.currentThread() != app.thread():
            if hasattr(self, 'logger'):
                self.logger.error(
                    f"Method '{func.__name__}' was called from a background thread! "
                    f"This may cause the application to crash. Call blocked."
                )
            return  # Block execution

        return func(self, *args, **kwargs)
    return wrapper


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
        overlay_windows: Optional[Dict[str, OverlayWindow]] = None,
        clipboard_service=None,
        logger=None,
        app=None,
    ):
        # Accept injected dependencies for easier wiring/testing
        self.main_window = main_window
        self.tray_manager = tray_manager
        self.selection_overlay = selection_overlay
        self.settings_dialog = None
        # Use provided dict or initialize empty dict
        self.overlay_windows: Dict[str, OverlayWindow] = overlay_windows if overlay_windows is not None else {}
        self.reader_window = None
        # Clipboard service may be None; fallback to get_clipboard_service() inside methods
        self._clipboard_service = clipboard_service
        # Logger fallback
        self.logger = logger or _default_logger
        self.app = app

        # Initialize UI components
        self._initialize_ui_components()

    def _initialize_ui_components(self):
        """Initialize all UI components managed by this service."""
        # Create tray manager first as it's needed for notifications
        if self.tray_manager is None:
            self._create_tray_manager()

        # Create main window
        if self.main_window is None:
            self._create_main_window()

        # Create selection overlay
        if self.selection_overlay is None:
            self._create_selection_overlay()

    def _create_tray_manager(self):
        """Create and initialize the system tray manager."""
        try:
            # Use app methods as callbacks if available, otherwise no-op lambdas
            # Build safe callbacks that emit Qt signals only if present
            def _emit_if_signal(name: str):
                def _cb():
                    try:
                        sig = getattr(self.app, name, None)
                        if sig:
                            sig.emit()
                    except Exception:
                        pass
                return _cb

            on_toggle = _emit_if_signal("toggle_overlay_signal")
            on_open = _emit_if_signal("show_settings_signal")
            on_exit = getattr(self.app, "exit_app", None) or (lambda: None)
            on_activate = getattr(self.app, "activate_ocr", None) or (lambda: None)

            self.tray_manager = TrayManager(
                on_toggle_overlay=on_toggle,
                on_open_settings=on_open,
                on_exit_app=on_exit,
                on_activate_ocr=on_activate,
            )
            if not self.tray_manager.create():
                self.logger.warning("UIService: Failed to initialize system tray")
            else:
                self.logger.debug("UIService: TrayManager created and shown")
        except Exception as e:
            self.logger.error(f"UIService: Failed to create TrayManager: {e}", exc_info=True)
            self.tray_manager = None

    # --- Main window operations ------------------------------------------------

    @main_thread_only
    def _create_main_window(self):
        """Create the main window (called lazily in main thread)."""
        try:
            self.main_window = MainWindow()
            # Connect close-to-tray signal
            if self.app and hasattr(self.app, "hide_main_window_to_tray"):
                try:
                    self.main_window.closeToTrayRequested.connect(self.app.hide_main_window_to_tray)
                except Exception:
                    pass
            self.logger.debug("UIService: MainWindow created")
        except Exception as e:
            self.logger.error(f"UIService: Failed to create MainWindow: {e}", exc_info=True)
            self.main_window = None

    @main_thread_only
    def _create_selection_overlay(self):
        """Create the selection overlay (called lazily in main thread)."""
        try:
            self.selection_overlay = SelectionOverlayQt()
            # Connect signals to ui_service handlers
            if hasattr(self.selection_overlay, "selectionCompleted"):
                try:
                    self.selection_overlay.selectionCompleted.connect(self._on_selection_completed)
                except Exception:
                    pass
            if hasattr(self.selection_overlay, "selectionCanceled"):
                try:
                    self.selection_overlay.selectionCanceled.connect(self._on_selection_canceled)
                except Exception:
                    pass
            self.logger.debug("UIService: SelectionOverlayQt created")
        except Exception as e:
            self.logger.error(f"UIService: Failed to create SelectionOverlayQt: {e}", exc_info=True)
            self.selection_overlay = None

    @main_thread_only
    def show_main_window(self):
        """Show and activate the main settings window."""
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

    @main_thread_only
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

    @main_thread_only
    def open_settings(self):
        """Open (or create) the settings dialog and bring it to front."""
        self.logger.info("UIService: open_settings() called")
        try:
            # Create dialog if it doesn't exist or was closed
            if self.settings_dialog is None:
                # Ensure main_window exists for parenting
                if self.main_window is None:
                    self._create_main_window()
                # Parent to main_window if available
                parent = self.main_window if self.main_window else None
                try:
                    self.settings_dialog = SettingsDialog(app=self.app, parent=parent)
                except Exception as e:
                    self.logger.error(f"UIService: Failed to create SettingsDialog: {e}", exc_info=True)
                    # Notify user via tray if possible
                    notification_service = get_notification_service()
                    notification_service.error(f"Failed to open settings: {e}", "WhisperBridge")
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
            notification_service = get_notification_service()
            try:
                notification_service.error(f"Settings dialog error: {e}", "WhisperBridge")
            except Exception:
                self.logger.debug("Failed to show tray notification for settings error")

    # --- Overlay windows -------------------------------------------------------

    @main_thread_only
    def show_overlay_window(
        self,
        original_text: str,
        translated_text: str,
        position: Optional[Tuple[int, int]] = None,
        overlay_id: str = "main",
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
            if overlay_id not in self.overlay_windows:
                try:
                    self.overlay_windows[overlay_id] = OverlayWindow()
                    self.logger.debug(f"UIService: Created OverlayWindow for id '{overlay_id}'")
                except Exception as e:
                    self.logger.error(
                        f"UIService: Failed to create OverlayWindow '{overlay_id}': {e}",
                        exc_info=True,
                    )
                    notification_service = get_notification_service()
                    notification_service.error(f"Overlay creation failed: {e}", "WhisperBridge")
                    return

            overlay = self.overlay_windows[overlay_id]
            try:
                pos = position
                overlay.show_overlay(
                    original_text or "", translated_text or "", pos
                )
                self.logger.info(
                    f"Overlay '{overlay_id}' displayed successfully by UIService"
                )
            except Exception as e:
                self.logger.error(
                    f"UIService: Failed to show overlay '{overlay_id}': {e}",
                    exc_info=True,
                )
                if self.tray_manager:
                    try:
                        notification_service = get_notification_service()
                        notification_service.error(f"Overlay display error: {e}", "WhisperBridge")
                    except Exception:
                        self.logger.debug(
                            "Failed to show tray notification for overlay display error"
                        )

        except Exception as e:
            self.logger.error(
                f"Unexpected error in UIService.show_overlay_window: {e}", exc_info=True
            )

    @main_thread_only
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
            self.logger.error(
                f"UIService.hide_overlay_window error for id '{overlay_id}': {e}",
                exc_info=True,
            )

    @main_thread_only
    def toggle_overlay(self):
        """Toggle overlay visibility. If no overlay exists, create a basic fullscreen overlay."""
        self.logger.info("UIService: toggling overlay")
        main_overlay_id = "main"
        try:
            if main_overlay_id in self.overlay_windows:
                overlay = self.overlay_windows[main_overlay_id]
                try:
                    if getattr(overlay, "is_overlay_visible", lambda: False)():
                        # Hide the overlay
                        try:
                            overlay.hide_overlay()
                        except AttributeError:
                            overlay.hide()
                        self.logger.debug(f"Overlay {main_overlay_id} hidden")
                    else:
                        # Show the overlay
                        overlay.show_overlay("", "")
                        self.logger.debug(f"Overlay {main_overlay_id} shown")
                    return
                except Exception as e:
                    self.logger.error(
                        f"UIService: Error while toggling existing overlay: {e}",
                        exc_info=True,
                    )
                    # If toggle failed, remove the broken overlay and create a new one
                    del self.overlay_windows[main_overlay_id]
        except Exception as e:
            self.logger.error(
                f"UIService: Error while accessing overlay_windows: {e}", exc_info=True
            )

        # No overlays exist or toggle failed — create a basic fullscreen overlay and show it
        try:
            self.logger.info(
                "UIService: No existing overlay found — creating a basic fullscreen overlay"
            )
            self.overlay_windows[main_overlay_id] = OverlayWindow()
            self.overlay_windows[main_overlay_id].show_overlay("", "")
            self.logger.info(f"Created and showed overlay '{main_overlay_id}'")
        except Exception as e:
            self.logger.error(
                f"UIService: Failed to create/show overlay: {e}", exc_info=True
            )

    @main_thread_only
    def show_reader_window(self, text: str):
        """Show the reader window with the provided text."""
        self.logger.info("UIService: show_reader_window() called")
        try:
            # Create reader window if it doesn't exist
            if self.reader_window is None:
                try:
                    self.reader_window = ReaderWindow()
                    self.logger.debug("UIService: ReaderWindow created")
                except Exception as e:
                    self.logger.error(f"UIService: Failed to create ReaderWindow: {e}", exc_info=True)
                    notification_service = get_notification_service()
                    notification_service.error(f"Reader window creation failed: {e}", "WhisperBridge")
                    return

            # Show text in reader window
            try:
                self.reader_window.show_text(text)
                self.logger.info("Reader window displayed successfully by UIService")
            except Exception as e:
                self.logger.error(f"UIService: Failed to show reader window: {e}", exc_info=True)
                notification_service = get_notification_service()
                notification_service.error(f"Reader window display error: {e}", "WhisperBridge")

        except Exception as e:
            self.logger.error(f"Unexpected error in UIService.show_reader_window: {e}", exc_info=True)

    @main_thread_only
    def activate_ocr(self):
        """Activate OCR selection overlay in the main Qt thread."""
        try:
            from ..services.config_service import config_service
            settings = config_service.get_settings()
            ocr_build_enabled = getattr(settings, 'ocr_enabled', True)
            if not ocr_build_enabled:
                self.logger.warning("OCR activation blocked: OCR not enabled at build time (OCR_ENABLED=0)")
                return

            # Ensure OCR overlay exists (created in main thread)
            if 'ocr' not in self.overlay_windows:
                self.overlay_windows['ocr'] = OverlayWindow()
                self.logger.debug("OCR overlay created in main thread")

            if self.selection_overlay is None:
                # Lazily create and wire selection overlay
                self._create_selection_overlay()
                if self.selection_overlay is None:
                    self.logger.error("Failed to create selection_overlay")
                    return
            self.selection_overlay.start()
            self.logger.debug("Selection overlay started")
        except Exception as e:
            self.logger.error(f"UIService.activate_ocr error: {e}", exc_info=True)

    # --- Slots / handlers -----------------------------------------------------

    @main_thread_only
    @Slot(str, str, str)
    def handle_worker_finished(
        self, original_text: str, translated_text: str, overlay_id: str
    ):
        """
        Handler for worker finished events.

        Preserves QtApp._handle_worker_finished semantics: normalize overlay id -> "ocr"
        to avoid creating duplicate windows for OCR results.
        """
        try:
            self.logger.info("UIService.handle_worker_finished invoked in main thread")
            canonical_overlay_id = "ocr"
            # Always show OCR results in canonical overlay
            self.show_overlay_window(
                original_text, translated_text, overlay_id=canonical_overlay_id
            )
        except Exception as e:
            self.logger.error(
                f"UIService.handle_worker_finished error: {e}", exc_info=True
            )

    @main_thread_only
    @Slot(str, str, bool)
    def handle_copy_translate(
        self, clipboard_text: str, translated_text: str, auto_copy: bool = False
    ):
        """
        Handle copy->translate results.

        - Show overlay (overlay_id='copy_translate')
        - Optionally copy translated_text to clipboard AFTER overlay is shown
        - Use tray_manager for notifications on errors (same as QtApp)
        """
        try:
            # Show overlay first
            self.show_overlay_window(
                clipboard_text, translated_text, overlay_id="copy_translate"
            )

            # If auto-copy requested, copy AFTER overlay is shown
            if auto_copy:
                clipboard_service = self._clipboard_service or get_clipboard_service()
                try:
                    if clipboard_service and clipboard_service.copy_text(
                        translated_text
                    ):
                        self.logger.info("Translated text copied to clipboard (auto_copy_translated enabled)")
                    else:
                        self.logger.warning(
                            "Failed to copy translated text to clipboard (ClipboardService.copy_text returned False or service unavailable)"
                        )
                except Exception as e:
                    self.logger.error(f"UIService: Auto-copy failed: {e}", exc_info=True)

            self.logger.info("Copy-translate overlay shown successfully by UIService")

        except Exception as e:
            self.logger.error(f"UIService.handle_copy_translate error: {e}", exc_info=True)
            if self.tray_manager:
                try:
                    notification_service = get_notification_service()
                    notification_service.error(f"Copy-translate overlay error: {e}", "WhisperBridge")
                except Exception:
                    self.logger.debug("Failed to show tray notification for copy-translate error")

    # --- Additional UI helpers --------------------------------

    @main_thread_only
    def handle_ocr_service_ready(self):
        """Handle OCR service ready event: show notification."""
        try:
            notification_service = get_notification_service()
            notification_service.info("OCR service is ready.", "WhisperBridge")
            self.logger.info("Handled OCR service ready: showed notification.")
        except Exception as e:
            self.logger.error(f"UIService.handle_ocr_service_ready error: {e}", exc_info=True)



    @main_thread_only
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
            self.logger.error(
                f"UIService.update_window_opacity error: {e}", exc_info=True
            )


    @main_thread_only
    def update_theme(self, theme: str):
        """Persist theme setting and log (keeps parity with QtApp.update_theme)."""
        try:
            from ..services.config_service import config_service

            config_service.set_setting("theme", theme)
            self.logger.debug(f"UIService: theme updated to: {theme}")
        except Exception as e:
            self.logger.error(f"UIService.update_theme error: {e}", exc_info=True)

    @main_thread_only
    @Slot(str)
    def on_theme_changed(self, theme: str):
        """React to ThemeService notifications by refreshing widget visuals."""
        self.logger.info(f"UIService: on_theme_changed -> {theme}")
        try:
            app = QApplication.instance()
            if not app:
                return

            # Collect known widgets to refresh
            widgets = []
            if self.main_window:
                widgets.append(self.main_window)
            if self.settings_dialog:
                widgets.append(self.settings_dialog)
            if self.selection_overlay:
                widgets.append(self.selection_overlay)
            widgets.extend(list(self.overlay_windows.values()))

            # Re-apply palette and force re-polish/repaint
            for w in widgets:
                try:
                    w.setPalette(app.palette())
                    try:
                        s = w.style()
                        # Some styles need explicit unpolish/polish to pick up palette/stylesheet changes
                        s.unpolish(w)
                        s.polish(w)
                    except Exception:
                        pass
                    w.update()
                except Exception:
                    pass

            # Tray can be updated here if theme-specific assets are used (placeholder hook)
            # if self.tray_manager: self.tray_manager.update_theme(theme)

            self.logger.debug(f"UIService: Applied theme change to widgets: {theme}")
        except Exception as e:
            self.logger.error(f"UIService.on_theme_changed error: {e}", exc_info=True)

    @main_thread_only
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

    @main_thread_only
    def _on_selection_canceled(self):
        """Handle selection cancellation."""
        self.logger.info("Selection canceled")
        try:
            notification_service = get_notification_service()
            notification_service.info("Canceled", "WhisperBridge")
        except Exception as e:
            self.logger.error(f"Error showing selection canceled notification: {e}", exc_info=True)

    @main_thread_only
    def _on_selection_completed(self, rect):
        """Handle selection completion."""
        self.logger.info(f"Selection completed: {rect}")
        try:
            # Convert logical coordinates to absolute pixels
            x, y, width, height = ScreenUtils.convert_rect_to_pixels(rect)
            self.logger.info(f"Converted to pixels: x={x}, y={y}, w={width}, h={height}")

            # Create region rectangle for capture
            region = Rectangle(x, y, width, height)

            # Create and start worker for OCR + translation
            self._start_ocr_worker(region)

            self.logger.debug("Selection completed processed by UIService")
        except Exception as e:
            self.logger.error(f"Error processing selection: {e}")

    def _start_ocr_worker(self, region: Rectangle):
        """Start OCR worker for the selected region."""
        try:
            from ..services.config_service import config_service
            settings = config_service.get_settings()
            ocr_build_enabled = getattr(settings, 'ocr_enabled', True)
            if not ocr_build_enabled:
                self.logger.warning("OCR worker blocked: OCR not enabled at build time (OCR_ENABLED=0)")
                notification_service = get_notification_service()
                notification_service.error("OCR is not available in this build.", "WhisperBridge")
                return

            self.logger.info(f"Starting OCR worker for region: {region}")

            worker = CaptureOcrTranslateWorker(region=region)
            self.app.create_and_run_worker(worker, self.app._handle_worker_finished, self.app._handle_worker_error)

            self.logger.info("OCR worker started successfully")

        except Exception as e:
            self.logger.error(f"Error starting OCR worker: {e}", exc_info=True)
            notification_service = get_notification_service()
            notification_service.error(f"Failed to start OCR processing: {e}", "WhisperBridge")

    @main_thread_only
    @Slot(str)
    def _handle_worker_error(self, error_message: str):
        """Handle worker error."""
        self.logger.error(f"Worker error: {error_message}")
        notification_service = get_notification_service()
        notification_service.error(f"Processing error: {error_message}", "WhisperBridge")


# Global UI service instance (set by AppServices)
_ui_service_instance: Optional[UIService] = None


def get_ui_service() -> Optional[UIService]:
    """Get the global UI service instance."""
    return _ui_service_instance


def set_ui_service(ui_service: UIService) -> None:
    """Set the global UI service instance."""
    global _ui_service_instance
    _ui_service_instance = ui_service
