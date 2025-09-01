"""
Qt-based application class for WhisperBridge.
Provides compatible interface with the existing CTK-based application.
"""

import sys
import threading
from typing import Optional, Dict, Any
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt, QObject, Signal, Slot
from PySide6.QtGui import QPalette, QColor

from .main_window import MainWindow
from .overlay_window import OverlayWindow
from .tray import TrayManager
from .selection_overlay import SelectionOverlayQt
from ..core.config import settings
from ..services.hotkey_service import HotkeyService
from ..services.overlay_service import init_overlay_service, get_overlay_service
from ..core.keyboard_manager import KeyboardManager
from ..services.ocr_service import get_ocr_service, OCRRequest
from ..services.translation_service import get_translation_service
from ..core.api_manager import init_api_manager
from ..utils.screen_utils import Rectangle
from ..services.screen_capture_service import get_capture_service
from loguru import logger


class OcrWorker(QObject):
    """Worker to handle OCR results and signal completion."""
    finished = Signal(str)

    def process_and_emit(self, text):
        self.finished.emit(text)

class QtApp(QObject):
    """Qt-based application class with compatible interface."""

    def __init__(self):
        """Initialize the Qt application."""
        super().__init__()
        self.qt_app = QApplication.instance()
        if self.qt_app is None:
            self.qt_app = QApplication(sys.argv)

        # Configure application
        self.qt_app.setApplicationName("WhisperBridge")
        self.qt_app.setApplicationVersion("1.0.0")
        self.qt_app.setOrganizationName("WhisperBridge")

        # Window instances
        self.main_window: Optional[MainWindow] = None
        self.overlay_windows: Dict[str, OverlayWindow] = {}
        self.selection_overlay: Optional[SelectionOverlayQt] = None

        # Services
        self.tray_manager: Optional[TrayManager] = None
        self.hotkey_service: Optional[HotkeyService] = None
        self.keyboard_manager: Optional[KeyboardManager] = None
        self.overlay_service = None

        # Application state
        self.is_running = False
        self.minimize_to_tray = True
        self.shutdown_requested = threading.Event()

        # Theme settings
        self._current_theme = self._get_theme_from_settings()

        # Apply initial theme
        self._apply_theme()

    def _get_theme_from_settings(self) -> str:
        """Get theme from settings."""
        theme_map = {
            "dark": "dark",
            "light": "light",
            "auto": "system"
        }
        return theme_map.get(settings.theme.lower(), "dark")

    def _apply_theme(self):
        """Apply the current theme to the application."""
        if self._current_theme == "dark":
            self._apply_dark_theme()
        elif self._current_theme == "light":
            self._apply_light_theme()
        else:
            # System theme - for now default to dark
            self._apply_dark_theme()

    def _apply_dark_theme(self):
        """Apply dark theme."""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)

        self.qt_app.setPalette(palette)

    def _apply_light_theme(self):
        """Apply light theme."""
        self.qt_app.setPalette(self.qt_app.style().standardPalette())

    def initialize(self):
        """Initialize application components."""
        try:
            print("Initializing Qt-based WhisperBridge application...")

            # Create main window
            self._create_main_window()

            # Initialize overlay service
            self._initialize_overlay_service()

            # Create selection overlay
            self.selection_overlay = SelectionOverlayQt()
            self.selection_overlay.selectionCompleted.connect(self._on_selection_completed)
            self.selection_overlay.selectionCanceled.connect(self._on_selection_canceled)

            # Create tray manager and connect signals
            self._create_tray_manager()

            # Connect main window close-to-tray signal
            if self.main_window:
                self.main_window.closeToTrayRequested.connect(self.hide_main_window_to_tray)

            # Initialize keyboard services
            self._create_keyboard_services()

            # Initialize OCR service
            self._initialize_ocr_service()

            # Create OCR worker
            self.ocr_worker = OcrWorker()
            self.ocr_worker.finished.connect(self._show_ocr_result)

            # Initialize translation service
            self._initialize_translation_service()

            self.is_running = True
            print("Qt-based WhisperBridge application initialized successfully")

        except Exception as e:
            print(f"Failed to initialize Qt application: {e}")
            raise

    def _create_main_window(self):
        """Create the main settings window."""
        self.main_window = MainWindow(on_save_callback=self._on_settings_saved)

    def _initialize_overlay_service(self):
        """Initialize the overlay service."""
        try:
            # For Qt, we'll use our own overlay windows
            print("Qt overlay service initialized (using Qt windows)")
        except Exception as e:
            print(f"Failed to initialize Qt overlay service: {e}")

    def _create_keyboard_services(self):
        """Create and initialize keyboard services."""
        try:
            # Create keyboard manager
            self.keyboard_manager = KeyboardManager()

            # Create hotkey service
            self.hotkey_service = HotkeyService(self.keyboard_manager)

            # Register default hotkeys
            self._register_default_hotkeys()

            # Start hotkey service
            if not self.hotkey_service.start():
                print("Warning: Failed to start hotkey service")
                self.hotkey_service = None
            else:
                print("Hotkey service started successfully")

        except Exception as e:
            print(f"Failed to create keyboard services: {e}")
            self.keyboard_manager = None
            self.hotkey_service = None

    def _create_tray_manager(self):
        """Create and initialize the system tray manager."""
        try:
            self.tray_manager = TrayManager(
                on_show_main_window=self.show_main_window,
                on_toggle_overlay=self.toggle_overlay,
                on_open_settings=self.open_settings,
                on_exit_app=self.exit_app,
                on_activate_ocr=self.activate_ocr
            )
            if not self.tray_manager.create():
                logger.warning("Failed to initialize system tray")
        except Exception as e:
            logger.error(f"Failed to create tray manager: {e}")
            self.tray_manager = None

    def _register_default_hotkeys(self):
        """Register default hotkeys for the application."""
        if not self.keyboard_manager:
            return

        try:
            # Register main translation hotkey
            self.keyboard_manager.register_hotkey(
                settings.translate_hotkey,
                self._on_translate_hotkey,
                "Main translation hotkey"
            )

            # Register quick translate hotkey if different
            if settings.quick_translate_hotkey != settings.translate_hotkey:
                self.keyboard_manager.register_hotkey(
                    settings.quick_translate_hotkey,
                    self._on_quick_translate_hotkey,
                    "Quick translation hotkey"
                )

            # Register activation hotkey if different
            if (settings.activation_hotkey != settings.translate_hotkey and
                settings.activation_hotkey != settings.quick_translate_hotkey):
                self.keyboard_manager.register_hotkey(
                    settings.activation_hotkey,
                    self._on_activation_hotkey,
                    "Application activation hotkey"
                )

            print(f"Registered hotkeys: {settings.translate_hotkey}, {settings.quick_translate_hotkey}, {settings.activation_hotkey}")

        except Exception as e:
            print(f"Failed to register default hotkeys: {e}")

    def _initialize_ocr_service(self):
        """Initialize OCR service in the background."""
        logger.info("Starting OCR service initialization in Qt app")
        try:
            ocr_service = get_ocr_service()
            logger.debug(f"OCR service instance: {ocr_service}")
            # Start background initialization and provide a callback
            ocr_service.start_background_initialization(
                on_complete=self._on_ocr_service_ready
            )
            # Update tray icon to show loading state
            self.update_tray_status(is_loading=True)
            logger.info("OCR service background initialization started successfully")
        except Exception as e:
            logger.error(f"Failed to start OCR service initialization: {e}")
            logger.debug(f"Initialization error details: {type(e).__name__}: {str(e)}", exc_info=True)
            self.update_tray_status(has_error=True)

    def _on_ocr_service_ready(self):
        """Callback for when OCR service is ready."""
        logger.info("OCR service initialization completed - service is now ready")
        ocr_service = get_ocr_service()
        logger.debug(f"OCR service status: initialized={ocr_service.is_initialized}")

        # Update tray icon to show normal state
        self.update_tray_status(is_loading=False)
        logger.debug("Tray status updated to normal (loading=False)")

        self.show_tray_notification(
            "WhisperBridge",
            "OCR service is ready."
        )
        logger.info("User notification shown: OCR service ready")

    def _initialize_translation_service(self):
        """Initialize translation service."""
        try:
            # Initialize API manager
            api_manager = init_api_manager()
            print("API manager initialized successfully")

            # Initialize translation service
            translation_service = get_translation_service()
            if not translation_service.initialize():
                print("Warning: Failed to initialize translation service")
            else:
                print("Translation service initialized successfully")

        except Exception as e:
            print(f"Warning: Failed to initialize translation service: {e}")

    def _on_settings_saved(self):
        """Handle settings saved event."""
        print("Settings saved, updating Qt application...")

        # Update theme if changed
        new_theme = self._get_theme_from_settings()
        if new_theme != self._current_theme:
            self._current_theme = new_theme
            self._apply_theme()
            print(f"Theme changed to: {new_theme}")

    def _on_translate_hotkey(self):
        """Handle main translation hotkey press."""
        logger.info("Main translation hotkey pressed")
        logger.debug(f"Hotkey: {settings.translate_hotkey}")

        # Check OCR service readiness
        ocr_service = get_ocr_service()
        logger.debug(f"OCR service initialized: {ocr_service.is_initialized}, initializing: {ocr_service.is_initializing}")

        # Run the capture and processing in a separate thread to avoid blocking the UI
        thread = threading.Thread(target=self._capture_and_process)
        thread.daemon = True
        thread.start()

    def _capture_and_process(self):
        """Capture screen area and process it."""
        self.update_tray_status(is_active=True)

        from ..services.screen_capture_service import capture_area_interactive, CaptureResult, CaptureOptions

        # Create a temporary file path
        import tempfile
        import os
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"whisperbridge_capture_{int(time.time())}.png")

        capture_options = CaptureOptions(
            save_to_file=True,
            output_path=temp_path,
            format="PNG"
        )

        def on_capture_complete(result: CaptureResult):
            try:
                if not result.success or not result.image:
                    self._show_capture_error(result.error_message or "Capture failed or was cancelled.")
                    return

                logger.info(f"Image captured and saved to: {result.file_path}")

                # Now, process the OCR and translation
                self._process_ocr_and_translate(result)

            finally:
                self.update_tray_status(is_active=False)

        capture_area_interactive(on_capture_complete, options=capture_options)

    def _process_ocr_and_translate(self, capture_result):
        """Process OCR and translation."""
        logger.info("Starting OCR and translation processing")
        logger.debug(f"Capture result: success={capture_result.success}, image_size={capture_result.image.size if capture_result.image else None}")

        try:
            ocr_service = get_ocr_service()
            if not ocr_service.is_initialized:
                logger.warning("OCR service not ready for processing")
                # Schedule error display on main thread
                QTimer.singleShot(0, lambda: self._show_ocr_error("OCR service not ready."))
                return

            logger.debug("OCR service is ready, creating OCR request")
            ocr_request = OCRRequest(
                image=capture_result.image,
                languages=settings.ocr_languages,
                preprocess=True,
                use_cache=True
            )
            logger.debug(f"OCR request: languages={ocr_request.languages}, preprocess={ocr_request.preprocess}")

            ocr_response = ocr_service.process_image(ocr_request)
            logger.info(f"OCR processing result: success={ocr_response.success}, confidence={ocr_response.confidence:.3f}, text_length={len(ocr_response.text)}")
            logger.debug(f"OCR raw text: '{ocr_response.text}'")

            logger.info("OCR successful, showing overlay with OCR text only (translation disabled)")
            # Show overlay with OCR text only, no translation

            # Use unique overlay_id for each OCR result to avoid conflicts
            import time
            unique_overlay_id = f"ocr_{int(time.time() * 1000)}"
            logger.info(f"Using unique overlay ID: {unique_overlay_id}")

            # Store OCR data for the callback
            ocr_text = ocr_response.text
            ocr_info = f"OCR Result (Translation disabled)\nConfidence: {ocr_response.confidence:.1%}\nEngine: {ocr_response.engine_used.value}"

            def show_overlay():
                logger.info("About to call show_overlay_window from timer -> main thread")
                try:
                    self.show_overlay_window(
                        ocr_text,
                        ocr_info,
                        overlay_id=unique_overlay_id
                    )
                    logger.info("show_overlay_window call completed from timer -> main thread")
                except Exception as e:
                    logger.error(f"Error in show_overlay callback: {e}", exc_info=True)

            # Schedule overlay display on main thread
            QTimer.singleShot(100, show_overlay)
            logger.info("Overlay scheduled for display")

        except Exception as e:
            logger.error(f"Error in processing: {e}", exc_info=True)
            logger.debug(f"Processing error details: {type(e).__name__}: {str(e)}", exc_info=True)
            QTimer.singleShot(0, lambda: self._show_ocr_error(f"An unexpected error occurred: {e}"))

    def _show_capture_error(self, message: str):
        """Show capture error notification."""
        logger.error(f"Capture error: {message}")
        if self.tray_manager:
            self.tray_manager.show_notification(
                "WhisperBridge",
                f"Capture Error: {message}"
            )

    def _show_ocr_error(self, message: str):
        """Show OCR error notification."""
        logger.error(f"OCR error: {message}")
        if self.tray_manager:
            self.tray_manager.show_notification(
                "WhisperBridge",
                f"OCR Error: {message}"
            )

    def _on_quick_translate_hotkey(self):
        """Handle quick translation hotkey press."""
        logger.info("Quick translation hotkey pressed")
        logger.debug(f"Hotkey: {settings.quick_translate_hotkey}")
        # TODO: Implement quick translation (maybe from clipboard)
        if self.tray_manager:
            self.tray_manager.show_notification(
                "WhisperBridge",
                "Quick translation hotkey activated"
            )
            logger.debug("Tray notification shown for quick translation")

    def _on_activation_hotkey(self):
        """Handle application activation hotkey press."""
        logger.info("Application activation hotkey pressed")
        logger.debug(f"Hotkey: {settings.activation_hotkey}")
        self.show_main_window()
        if self.tray_manager:
            self.tray_manager.show_notification(
                "WhisperBridge",
                "Application activated"
            )
            logger.debug("Tray notification shown for application activation")

    def activate_ocr(self):
        """Activate OCR selection overlay."""
        logger.info("Activating OCR selection overlay")
        if self.selection_overlay:
            self.selection_overlay.start()
        else:
            logger.error("Selection overlay not initialized")
            if self.tray_manager:
                self.tray_manager.show_notification(
                    "WhisperBridge",
                    "OCR selection overlay not available"
                )

    def _on_selection_completed(self, rect):
        """Handle selection completion."""
        logger.info(f"Selection completed: {rect}")
        try:
            # Convert logical coordinates to absolute pixels
            x, y, width, height = self._convert_rect_to_pixels(rect)
            logger.debug(f"Converted to pixels: x={x}, y={y}, w={width}, h={height}")

            # Run capture and OCR in background thread
            thread = threading.Thread(target=self._process_selection, args=(x, y, width, height))
            thread.daemon = True
            thread.start()
        except Exception as e:
            logger.error(f"Error processing selection: {e}")
            if self.tray_manager:
                self.tray_manager.show_notification(
                    "WhisperBridge",
                    f"Error processing selection: {e}"
                )

    def _on_selection_canceled(self):
        """Handle selection cancellation."""
        logger.info("Selection canceled")
        if self.tray_manager:
            self.tray_manager.show_notification(
                "WhisperBridge",
                "Отменено"
            )

    def _convert_rect_to_pixels(self, rect):
        """Convert QRect logical coordinates to absolute pixels."""
        # Use screen_utils to handle DPI
        logical_x = rect.x()
        logical_y = rect.y()
        logical_width = rect.width()
        logical_height = rect.height()

        # Get the screen for this rectangle (assume single screen for MVP)
        screen = self.qt_app.screenAt(rect.center())
        if screen:
            dpr = screen.devicePixelRatio()
            # Convert to pixels
            pixel_x = int(logical_x * dpr)
            pixel_y = int(logical_y * dpr)
            pixel_width = int(logical_width * dpr)
            pixel_height = int(logical_height * dpr)
            return pixel_x, pixel_y, pixel_width, pixel_height
        else:
            # Fallback: assume 1.0 DPR
            return logical_x, logical_y, logical_width, logical_height

    def _process_selection(self, x, y, width, height):
        """Process the selected area: capture and OCR."""
        try:
            logger.info("Starting capture and OCR processing")

            # Get screen capture service
            capture_service = get_capture_service()

            # Capture the selected area
            rect = Rectangle(x, y, width, height)
            capture_result = capture_service.capture_area(rect)
            if not capture_result.success or capture_result.image is None:
                logger.error("Failed to capture screen area")
                QTimer.singleShot(0, lambda: self._show_error("Failed to capture screen area"))
                return

            image = capture_result.image
            if image is None:
                logger.error("Failed to capture screen area")
                QTimer.singleShot(0, lambda: self._show_error("Failed to capture screen area"))
                return

            logger.info("Screen capture successful")

            # Get OCR service
            ocr_service = get_ocr_service()
            if not ocr_service.is_initialized:
                logger.warning("OCR service not ready")
                QTimer.singleShot(0, lambda: self._show_error("OCR service not ready"))
                return

            # Process OCR
            ocr_request = OCRRequest(
                image=image,
                languages=settings.ocr_languages,
                preprocess=True,
                use_cache=True
            )
            ocr_response = ocr_service.process_image(ocr_request)

            logger.info(f"OCR processing result: success={ocr_response.success}, text_length={len(ocr_response.text)}")

            if ocr_response.success:
                # Show overlay with OCR text
                self.ocr_worker.process_and_emit(ocr_response.text)
            else:
                logger.error("OCR processing failed")
                QTimer.singleShot(0, lambda: self._show_error("OCR processing failed"))

        except Exception as e:
            logger.error(f"Error in _process_selection: {e}")
            QTimer.singleShot(0, lambda: self._show_error(f"Processing error: {e}"))

    @Slot(str)
    def _show_ocr_result(self, text):
        """Show OCR result in overlay window."""
        try:
            # Get or create overlay window
            if "ocr" not in self.overlay_windows:
                self.overlay_windows["ocr"] = OverlayWindow()

            overlay = self.overlay_windows["ocr"]
            overlay.show_result(text)
        except Exception as e:
            logger.error(f"Error showing OCR result: {e}", exc_info=True)

    def _show_error(self, message):
        """Show error notification."""
        logger.error(f"Showing error: {message}")
        if self.tray_manager:
            self.tray_manager.show_notification(
                "WhisperBridge",
                f"Error: {message}"
            )

    def show_main_window(self):
        """Show the main settings window."""
        logger.info("Showing main window")
        if self.main_window:
            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()
            logger.debug("Main window shown and activated")

    def hide_main_window_to_tray(self):
        """Hide the main window to system tray."""
        logger.info("Hiding main window to tray")
        if self.main_window:
            self.main_window.hide()
            logger.debug("Main window hidden to tray")

    def toggle_overlay(self):
        """Toggle overlay visibility. If no overlay exists, create a basic fullscreen overlay."""
        logger.info("Toggling overlay")
        try:
            if self.overlay_windows:
                overlay_id = next(iter(self.overlay_windows.keys()))
                overlay = self.overlay_windows[overlay_id]
                if overlay.is_overlay_visible():
                    overlay.hide_overlay()
                    logger.debug(f"Overlay {overlay_id} hidden")
                else:
                    overlay.show_overlay("", "")
                    logger.debug(f"Overlay {overlay_id} shown")
                return
        except Exception as e:
            logger.error(f"Error while toggling existing overlay: {e}")

        # No overlays exist — create a basic fullscreen overlay (M0) and show it
        try:
            logger.info("No existing overlay found — creating a basic fullscreen overlay (M0)")
            overlay_id = "main"
            self.overlay_windows[overlay_id] = OverlayWindow()
            self.overlay_windows[overlay_id].show_overlay("", "")
            logger.info(f"Created and showed overlay '{overlay_id}'")
        except Exception as e:
            logger.error(f"Failed to create/show overlay: {e}")

    def exit_app(self):
        """Exit the application."""
        logger.info("Exit application requested from tray")
        self.qt_app.quit()

    def open_settings(self):
        """Open settings window (placeholder for future implementation)."""
        logger.info("Open settings requested from tray")
        # TODO: Implement settings window
        if self.tray_manager:
            self.tray_manager.show_notification(
                "WhisperBridge",
                "Settings window not yet implemented"
            )

    def show_overlay_window(self, original_text: str, translated_text: str,
                           position: Optional[tuple] = None, overlay_id: str = "main"):
        """Show the overlay window with translation results.

        Args:
            original_text: Original text to display
            translated_text: Translated text to display
            position: (x, y) coordinates for window positioning
            overlay_id: Unique identifier for the overlay
        """
        logger.info(f"=== SHOW_OVERLAY_WINDOW CALLED ===")
        logger.info(f"Original text: '{original_text[:50]}{'...' if len(original_text) > 50 else ''}'")
        logger.info(f"Translated text: '{translated_text[:50]}{'...' if len(translated_text) > 50 else ''}'")
        logger.info(f"Position: {position}, Overlay ID: {overlay_id}")

        # Get or create overlay window
        if overlay_id not in self.overlay_windows:
            self.overlay_windows[overlay_id] = OverlayWindow()

        overlay = self.overlay_windows[overlay_id]
        overlay.show_overlay(original_text, translated_text, position)

        logger.info(f"Overlay '{overlay_id}' displayed successfully")

    def hide_overlay_window(self, overlay_id: str = "main"):
        """Hide the overlay window.

        Args:
            overlay_id: Overlay identifier to hide
        """
        if overlay_id in self.overlay_windows:
            self.overlay_windows[overlay_id].hide_overlay()

    def update_theme(self, theme: str):
        """Update application theme.

        Args:
            theme: New theme ('dark', 'light', or 'system')
        """
        self._current_theme = theme.lower()
        self._apply_theme()
        settings.theme = theme
        print(f"Qt application theme updated to: {theme}")

    def update_window_opacity(self, opacity: float):
        """Update window opacity for all windows.

        Args:
            opacity: Opacity value between 0.0 and 1.0
        """
        opacity = max(0.1, min(1.0, opacity))  # Clamp between 0.1 and 1.0

        # Update main window opacity
        if self.main_window:
            self.main_window.setWindowOpacity(opacity)

        # Update overlay windows opacity
        for overlay in self.overlay_windows.values():
            overlay.setWindowOpacity(opacity)

        print(f"Window opacity updated to: {opacity}")

    def run(self):
        """Run the application main loop."""
        if not self.is_running:
            self.initialize()

        # Show main window before starting event loop
        self.show_main_window()

        try:
            print("Starting Qt-based WhisperBridge main loop...")
            return self.qt_app.exec()
        except Exception as e:
            print(f"Qt application error: {e}")
        finally:
            self.shutdown()

    def shutdown(self):
        """Shutdown the application gracefully."""
        if self.shutdown_requested.is_set():
            return
        self.shutdown_requested.set()

        print("Shutting down Qt-based WhisperBridge...")

        self.is_running = False

        # Shutdown hotkey service first
        if self.hotkey_service:
            self.hotkey_service.stop()
            self.hotkey_service = None

        # Shutdown tray manager
        if self.tray_manager:
            self.tray_manager.dispose()
            self.tray_manager = None

        # Shutdown OCR service
        try:
            from ..services.ocr_service import get_ocr_service
            ocr_service = get_ocr_service()
            ocr_service.shutdown()
        except Exception as e:
            print(f"Warning: Error shutting down OCR service: {e}")

        # Shutdown translation service
        try:
            from ..services.translation_service import get_translation_service
            translation_service = get_translation_service()
            translation_service.shutdown()
        except Exception as e:
            print(f"Warning: Error shutting down translation service: {e}")

        # Shutdown API manager
        try:
            from ..core.api_manager import get_api_manager
            api_manager = get_api_manager()
            api_manager.shutdown()
        except Exception as e:
            print(f"Warning: Error shutting down API manager: {e}")

        # Close overlay windows
        for overlay in self.overlay_windows.values():
            overlay.close()
        self.overlay_windows.clear()

        # Close main window
        if self.main_window:
            self.main_window.close()

        print("Qt-based WhisperBridge shutdown complete")

    def is_app_running(self) -> bool:
        """Check if the application is running.

        Returns:
            bool: True if application is running
        """
        return self.is_running and self.qt_app is not None

    def show_tray_notification(self, title: str, message: str):
        """Show a notification through the system tray.

        Args:
            title: Notification title
            message: Notification message
        """
        if self.tray_manager:
            self.tray_manager.show_notification(title, message)

    def update_tray_status(self, is_active: bool = False, has_error: bool = False, is_loading: bool = False):
        """Update the tray icon status.

        Args:
            is_active: Whether the app is actively processing
            has_error: Whether there's an error state
            is_loading: Whether the app is loading resources
        """
        # TODO: Implement status icon updates in TrayManager for future phases
        logger.debug(f"Tray status update requested: active={is_active}, error={has_error}, loading={is_loading}")

    def hide_main_window(self):
        """Hide the main window (minimize to tray)."""
        if self.main_window:
            self.main_window.hide()
            print("Main window hidden (minimized to tray)")

    def toggle_minimize_to_tray(self, enabled: bool):
        """Toggle minimize to tray behavior.

        Args:
            enabled: Whether to minimize to tray on close
        """
        self.minimize_to_tray = enabled
        logger.info(f"Minimize to tray behavior set to: {enabled}")


# Global application instance
_qt_app_instance: Optional[QtApp] = None


def get_qt_app() -> QtApp:
    """Get the global Qt application instance."""
    global _qt_app_instance
    if _qt_app_instance is None:
        _qt_app_instance = QtApp()
    return _qt_app_instance


def init_qt_app() -> QtApp:
    """Initialize and return the Qt application instance."""
    app = get_qt_app()
    if not app.is_running:
        app.initialize()
    return app