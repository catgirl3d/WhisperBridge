"""
Qt-based application class for WhisperBridge.
Provides compatible interface with the existing CTK-based application.
"""

import sys
from typing import Optional, Dict, Any
import time
from PySide6.QtWidgets import QApplication

from PySide6.QtCore import Qt, QObject, Signal, Slot, QThread
from PySide6.QtGui import QPalette, QColor

from .main_window import MainWindow
from .overlay_window import OverlayWindow
from .tray import TrayManager
from .selection_overlay import SelectionOverlayQt
from .settings_dialog import SettingsDialog
from ..services.hotkey_service import HotkeyService
from ..services.overlay_service_qt import init_overlay_service, get_overlay_service
from ..core.keyboard_manager import KeyboardManager
from ..services.ocr_service import get_ocr_service, OCRRequest
from ..services.translation_service import get_translation_service
from ..core.api_manager import init_api_manager
from ..utils.screen_utils import Rectangle
from ..services.screen_capture_service import get_capture_service
from ..services.config_service import config_service, SettingsObserver
# Clipboard singleton accessor (used to obtain a shared ClipboardService)
from ..services.clipboard_service import get_clipboard_service
from loguru import logger

try:
    from pynput.keyboard import Controller, Key
    PYNPUT_AVAILABLE = True
except ImportError:
    logger.warning("pynput not available. Copy-translate hotkey will not function.")
    PYNPUT_AVAILABLE = False
    Controller = None
    Key = None


class CaptureOcrTranslateWorker(QObject):
    """Worker for synchronous capture, OCR, and optional translation."""
    started = Signal()
    progress = Signal(str)
    ocr_finished = Signal(str)
    finished = Signal(str, str, str)
    error = Signal(str)

    def __init__(self, region=None, image=None, capture_options=None):
        super().__init__()
        self.region = region
        self.image = image
        self.capture_options = capture_options or {}
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        logger.info("CaptureOcrTranslateWorker run started")
        
        try:
            self.started.emit()
            
            image_to_process = None

            if self.image is not None:
                logger.debug("Processing pre-captured image")
                image_to_process = self.image
            elif self.region is not None:
                logger.debug("Starting synchronous capture for region")
                capture_service = get_capture_service()
                capture_result = capture_service.capture_area(self.region)

                if not capture_result.success or capture_result.image is None:
                    logger.error("Capture failed")
                    self.error.emit("Capture failed")
                    return
                
                image_to_process = capture_result.image
                self.progress.emit("Capture completed, starting OCR")
            else:
                self.error.emit("No image or region provided")
                return

            if self._cancel_requested:
                return

            # OCR
            ocr_service = get_ocr_service()
            if not ocr_service.is_initialized:
                self.error.emit("OCR service not initialized")
                return

            logger.debug("Starting OCR")
            # Get OCR languages from config service to ensure we have the latest saved values
            ocr_languages = config_service.get_setting("ocr_languages", use_cache=False)
            ocr_request = OCRRequest(
                image=image_to_process,
                languages=ocr_languages,
                preprocess=True,
                use_cache=True
            )
            ocr_response = ocr_service.process_image(ocr_request)

            if self._cancel_requested:
                return

            original_text = ocr_response.text

            self.progress.emit("OCR completed, checking translation")

            # Translation
            translated_text = ""
            try:
                api_key = config_service.get_setting("openai_api_key", use_cache=False)
                if api_key:
                    translation_service = get_translation_service()
                    # Guard against uninitialized translation service to reduce exceptions
                    if hasattr(translation_service, "is_initialized") and not translation_service.is_initialized():
                        logger.warning("Translation service not initialized, skipping translation")
                    else:
                        # Determine whether OCR auto-swap is enabled in settings
                        settings = config_service.get_settings()
                        ocr_auto_swap = getattr(settings, "ocr_auto_swap_en_ru", False)

                        # If auto-swap enabled, detect language and swap en<->ru
                        if ocr_auto_swap:
                            try:
                                from ..utils.api_utils import detect_language
                                detected = detect_language(original_text) or "auto"
                                if detected == "en":
                                    target = "ru"
                                elif detected == "ru":
                                    target = "en"
                                else:
                                    target = getattr(settings, "target_language", "en")

                                logger.debug(f"OCR auto-swap enabled: detected='{detected}', target='{target}'")
                                response = translation_service.translate_text_sync(
                                    original_text, source_lang=detected, target_lang=target
                                )
                            except Exception as e:
                                logger.warning(f"OCR auto-swap detection/translation failed: {e}")
                                # Fallback to default translation call
                                response = translation_service.translate_text_sync(original_text)
                        else:
                            # Use the synchronous translation API which returns a TranslationResponse
                            response = translation_service.translate_text_sync(original_text)

                        if response and getattr(response, "success", False):
                            translated_text = getattr(response, "translated_text", "") or ""
                            logger.debug("Translation completed successfully")
                        else:
                            error_msg = getattr(response, "error_message", "") if response else "Unknown error"
                            logger.warning(f"Translation failed or returned empty result: {error_msg}")
                else:
                    logger.debug("No API key, skipping translation")
            except Exception as e:
                logger.warning(f"Translation failed, using empty: {e}")

            overlay_id = f"ocr_{int(time.time() * 1000)}"

            if self._cancel_requested:
                return

            self.progress.emit("Processing completed")
            self.ocr_finished.emit(original_text)
            self.finished.emit(original_text, translated_text, overlay_id)

            logger.info("CaptureOcrTranslateWorker run completed successfully")

        except Exception as e:
            logger.error(f"Error in worker run: {e}", exc_info=True)
            self.error.emit(str(e))

    def process_and_emit(self, text):
        """Backward compatibility method for existing callers in _process_selection."""
        self.ocr_finished.emit(text)
        self.finished.emit(text, "", "")

class QtApp(QObject, SettingsObserver):
    """Qt-based application class with compatible interface."""

    # Signal for copy-translate hotkey to ensure UI operations happen in main thread
    copy_translate_signal = Signal(str, str)

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
        self.settings_dialog: Optional[SettingsDialog] = None
        self._worker_threads: list = []  # Holds (thread, worker) pairs to prevent garbage collection

        # Services
        self.tray_manager: Optional[TrayManager] = None
        self.hotkey_service: Optional[HotkeyService] = None
        self.keyboard_manager: Optional[KeyboardManager] = None
        self.overlay_service = None

        # Application state
        self.is_running = False
        self.minimize_to_tray = True
        self.shutdown_requested = False

        # Pending actions (set by hotkey handler and consumed in main thread)
        self._pending_auto_copy_translated = False
 
        # Register as config service observer first
        config_service.add_observer(self)
 
        # Connect copy-translate signal to slot
        self.copy_translate_signal.connect(self._handle_copy_translate)
 
        # Initialize clipboard service singleton (if available)
        try:
            self.clipboard_service = get_clipboard_service()
            if self.clipboard_service:
                logger.info("ClipboardService initialized and started in QtApp")
            else:
                logger.warning("ClipboardService not available; clipboard-backed features may be limited")
        except Exception as e:
            self.clipboard_service = None
            logger.warning(f"Failed to initialize ClipboardService in QtApp: {e}")
 
        # Ensure settings are loaded before getting theme
        _ = config_service.get_settings()
 
        # Theme settings
        self._current_theme = self._get_theme_from_settings()

        # Apply initial theme
        self._apply_theme()

    def _get_theme_from_settings(self) -> str:
        """Get theme from settings."""
        # Get theme from config service to ensure we have the latest saved value
        current_theme = config_service.get_setting("theme", use_cache=False)
        logger.debug(f"Retrieved theme from config service: '{current_theme}' (type: {type(current_theme)})")

        theme_map = {
            "dark": "dark",
            "light": "light",
            "auto": "system"
        }

        mapped_theme = theme_map.get(current_theme.lower() if current_theme else None, "light")
        logger.debug(f"Mapped theme: '{mapped_theme}'")
        return mapped_theme

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
            logger.info("Initializing Qt-based WhisperBridge application...")

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

            # Initialize OCR service (Temporarily disabled)
            # self._initialize_ocr_service()

            # Initialize translation service
            self._initialize_translation_service()

            self.is_running = True
            logger.info("Qt-based WhisperBridge application initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Qt application: {e}")
            raise

    def _create_main_window(self):
        """Create the main settings window."""
        self.main_window = MainWindow(on_save_callback=self._on_settings_saved)

    def _initialize_overlay_service(self):
        """Initialize the overlay service."""
        try:
            # For Qt, we'll use our own overlay windows
            logger.info("Qt overlay service initialized (using Qt windows)")
        except Exception as e:
            logger.error(f"Failed to initialize Qt overlay service: {e}")

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
                logger.warning("Failed to start hotkey service")
                self.hotkey_service = None
            else:
                logger.info("Hotkey service started successfully")

        except Exception as e:
            logger.error(f"Failed to create keyboard services: {e}")
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
            # Get current settings for hotkeys
            current_settings = config_service.get_settings()

            # Register main translation hotkey
            self.keyboard_manager.register_hotkey(
                current_settings.translate_hotkey,
                self._on_translate_hotkey,
                "Main translation hotkey"
            )

            # Register quick translate hotkey if different
            if current_settings.quick_translate_hotkey != current_settings.translate_hotkey:
                self.keyboard_manager.register_hotkey(
                    current_settings.quick_translate_hotkey,
                    self._on_quick_translate_hotkey,
                    "Quick translation hotkey"
                )

            # Register activation hotkey if different
            if (current_settings.activation_hotkey != current_settings.translate_hotkey and
                current_settings.activation_hotkey != current_settings.quick_translate_hotkey):
                self.keyboard_manager.register_hotkey(
                    current_settings.activation_hotkey,
                    self._on_activation_hotkey,
                    "Application activation hotkey"
                )

            # Register copy-translate hotkey
            self.keyboard_manager.register_hotkey(
                current_settings.copy_translate_hotkey,
                self._on_copy_translate_hotkey,
                "Copy->Translate hotkey"
            )

            logger.info(f"Registered hotkeys: {current_settings.translate_hotkey}, {current_settings.quick_translate_hotkey}, {current_settings.activation_hotkey}, {current_settings.copy_translate_hotkey}")

        except Exception as e:
            logger.error(f"Failed to register default hotkeys: {e}")

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
            logger.info("API manager initialized successfully")

            # Initialize translation service
            translation_service = get_translation_service()
            if not translation_service.initialize():
                logger.warning("Failed to initialize translation service")
            else:
                logger.info("Translation service initialized successfully")

        except Exception as e:
            logger.warning(f"Failed to initialize translation service: {e}")

    def _on_settings_saved(self):
        """Handle settings saved event."""
        logger.info("Settings saved, updating Qt application...")

        # Update theme if changed
        new_theme = self._get_theme_from_settings()
        if new_theme != self._current_theme:
            self._current_theme = new_theme
            self._apply_theme()
            logger.debug(f"Theme changed to: {new_theme}")

    def _on_config_settings_saved(self, saved_settings):
        """Handle settings saved through config service (e.g., from settings dialog)."""
        logger.info("Config settings saved, checking for theme changes...")

        # Update theme if changed - use the passed settings object for immediate update
        if saved_settings and hasattr(saved_settings, 'theme'):
            new_theme = self._get_theme_from_settings()
            if new_theme != self._current_theme:
                self._current_theme = new_theme
                self._apply_theme()
                logger.debug(f"Theme changed to: {new_theme}")

    # SettingsObserver methods
    def on_settings_changed(self, key: str, old_value, new_value):
        """Called when a setting value changes."""
        if key == "theme":
            logger.debug(f"Theme setting changed from {old_value} to {new_value}")
            new_theme = self._get_theme_from_settings()
            if new_theme != self._current_theme:
                self._current_theme = new_theme
                self._apply_theme()
        elif key in ["translate_hotkey", "quick_translate_hotkey", "activation_hotkey", "copy_translate_hotkey"]:
            logger.debug(f"Hotkey setting '{key}' changed from '{old_value}' to '{new_value}'")
            # Reload hotkeys if service is running
            if self.hotkey_service and self.hotkey_service.is_running():
                if self.hotkey_service.reload_hotkeys():
                    logger.info("Hotkeys reloaded successfully after settings change")
                else:
                    logger.error("Failed to reload hotkeys after settings change")

    def on_settings_loaded(self, settings):
        """Called when settings are loaded."""
        pass

    def on_settings_saved(self, settings):
        """Called when settings are saved."""
        self._on_config_settings_saved(settings)

    def _on_translate_hotkey(self):
        """Handle main translation hotkey press."""
        logger.info("Main translation hotkey pressed")
        translate_hotkey = config_service.get_setting("translate_hotkey", use_cache=False)
        logger.debug(f"Hotkey: {translate_hotkey}")

        # Check OCR service readiness
        ocr_service = get_ocr_service()
        logger.debug(f"OCR service initialized: {ocr_service.is_initialized}, initializing: {ocr_service.is_initializing}")

        # Run the capture and processing in a separate thread to avoid blocking the UI
        self._capture_and_process()

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
                logger.info("Creating CaptureOcrTranslateWorker with pre-captured image")

                # Create worker with pre-captured image
                worker = CaptureOcrTranslateWorker(image=result.image)
                thread = QThread()
                logger.info("Moving worker to QThread")
                worker.moveToThread(thread)

                # Add info/debug logging for worker signals with named slots
                def on_worker_started():
                    logger.info("Worker started successfully")

                def on_worker_progress(msg):
                    logger.info(f"Worker progress: {msg}")

                def on_worker_error(msg):
                    logger.error(f"Worker error: {msg}")

                worker.started.connect(on_worker_started)
                worker.progress.connect(on_worker_progress)
                worker.error.connect(on_worker_error)

                logger.info("Connecting worker.run to thread.started and starting thread")
                thread.started.connect(worker.run)

                # Ensure UI actions are executed on the main thread via Qt slots on self
                worker.finished.connect(self._handle_worker_finished)
                worker.error.connect(self._show_ocr_error)

                # Resource management - mirror the selection path
                worker.finished.connect(thread.quit)
                worker.finished.connect(worker.deleteLater)
                thread.finished.connect(thread.deleteLater)
                
                # Store (thread, worker) in self._worker_threads for lifecycle tracking
                self._worker_threads.append((thread, worker))
                logger.info(f"QThread starting and worker-thread pair stored in self._worker_threads (count: {len(self._worker_threads)})")
                
                thread.start()

            finally:
                self.update_tray_status(is_active=False)

        capture_area_interactive(on_capture_complete, options=capture_options)

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
        quick_translate_hotkey = config_service.get_setting("quick_translate_hotkey", use_cache=False)
        logger.debug(f"Hotkey: {quick_translate_hotkey}")
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
        activation_hotkey = config_service.get_setting("activation_hotkey", use_cache=False)
        logger.debug(f"Hotkey: {activation_hotkey}")
        self.show_main_window()
        if self.tray_manager:
            self.tray_manager.show_notification(
                "WhisperBridge",
                "Application activated"
            )
            logger.debug("Tray notification shown for application activation")

    def _on_copy_translate_hotkey(self):
        """Handle copy-translate hotkey press — fallback-only simulated Ctrl+C copy.
        
        Added: API key presence check and structured performance logging.
        """
        logger.info("Copy-translate hotkey pressed (fallback-only handler)")
        # Performance timing points (perf_counter for high-resolution timing)
        t_start = time.perf_counter()
        t_after_sim = None
        t_after_poll_success = None
        t_after_translation = None

        try:
            import platform
            # Determine platform once for use in fallback logic
            system = platform.system().lower()

            # Fallback-only approach: simulate Ctrl+C and read clipboard
            if not PYNPUT_AVAILABLE:
                logger.error("pynput not available for copy-translate fallback")
                if self.tray_manager:
                    self.tray_manager.show_notification(
                        "WhisperBridge",
                        "Copy-translate failed: pynput not installed"
                    )
                # Log final summary with zeros since we didn't proceed
                t_end = time.perf_counter()
                logger.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                return

            from pynput.keyboard import Controller, Key
            controller = Controller()

            # Prepare clipboard service and read previous content BEFORE simulating copy
            clipboard_service = getattr(self, "clipboard_service", None)
            if clipboard_service is None:
                clipboard_service = get_clipboard_service()
            if clipboard_service is None:
                logger.error("Clipboard service not available; aborting copy-translate")
                if self.tray_manager:
                    self.tray_manager.show_notification(
                        "WhisperBridge",
                        "Copy-translate failed: clipboard service unavailable"
                    )
                t_end = time.perf_counter()
                logger.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                return
            prev_clip = clipboard_service.get_clipboard_text() or ""

            # Increased pre-delay to allow user to release modifiers (prevent accidental physical modifiers)
            pre_delay = 0.4  # seconds
            time.sleep(pre_delay)

            # On Windows, wait for physical Ctrl to be released before proceeding
            if system == 'windows':
                try:
                    import ctypes
                    VK_CONTROL = 0x11
                    release_timeout = 1.5
                    release_interval = 0.05
                    release_elapsed = 0.0
                    try:
                        ctrl_down = bool(ctypes.windll.user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                    except Exception:
                        ctrl_down = False
                    if ctrl_down:
                        logger.debug("Physical Ctrl detected down; waiting for release before simulating copy")
                        while release_elapsed < release_timeout:
                            try:
                                if not (ctypes.windll.user32.GetAsyncKeyState(VK_CONTROL) & 0x8000):
                                    break
                            except Exception:
                                # If we can't query state, stop waiting and proceed
                                break
                            time.sleep(release_interval)
                            release_elapsed += release_interval
                        # Re-check
                        try:
                            still_down = bool(ctypes.windll.user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                        except Exception:
                            still_down = False
                        if still_down:
                            logger.info("Physical Ctrl key still down after waiting; aborting copy-translate to avoid accidental trigger")
                            if self.tray_manager:
                                self.tray_manager.show_notification(
                                    "WhisperBridge",
                                    "Copy-translate aborted: physical Ctrl key held down"
                                )
                            t_end = time.perf_counter()
                            logger.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                            return
                except Exception as e_ctrl_wait:
                    logger.debug(f"Failed to detect/wait for Ctrl key state: {e_ctrl_wait}")

            try:
                logger.debug("Starting fallback simulated Ctrl+C copy")
                # Always send Ctrl down, send 'c', then Ctrl up.
                controller.press(Key.ctrl)
                controller.press('c')
                controller.release('c')
                controller.release(Key.ctrl)
                # Mark after-simulation timepoint
                t_after_sim = time.perf_counter()
            except Exception as e:
                logger.error(f"Fallback copy simulation failed: {e}")
                if self.tray_manager:
                    self.tray_manager.show_notification(
                        "WhisperBridge",
                        f"Copy-translate fallback failed: {e}"
                    )
                t_end = time.perf_counter()
                logger.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                return

            # Short pause to allow OS to update clipboard
            time.sleep(0.08)

            # Poll clipboard for changed content using exponential backoff and configurable timeout.
            # Read timeout from config (milliseconds) and convert to seconds.
            try:
                timeout_ms = config_service.get_setting("clipboard_poll_timeout_ms", use_cache=False)
                timeout_ms = int(timeout_ms) if timeout_ms is not None else 2000
            except Exception as e:
                logger.debug(f"Failed to read clipboard_poll_timeout_ms from config; using default 2000ms: {e}")
                timeout_ms = 2000
            timeout = float(timeout_ms) / 1000.0

            # Exponential backoff parameters
            start_delay = 0.05
            max_delay = 0.2
            backoff_factor = 2.0

            logger.debug(f"Starting clipboard polling with timeout={timeout:.3f}s (configured {timeout_ms}ms), start_delay={start_delay}s, max_delay={max_delay}s")

            poll_start = time.perf_counter()
            attempts = 0
            delay = start_delay
            new_clip = prev_clip
            # Poll until timeout using exponential backoff
            while True:
                attempts += 1
                elapsed = time.perf_counter() - poll_start
                logger.debug(f"Clipboard poll attempt #{attempts}: elapsed={elapsed:.3f}s, delay={delay:.3f}s")

                new_clip = clipboard_service.get_clipboard_text() or ""
                if new_clip and new_clip != prev_clip:
                    t_after_poll_success = time.perf_counter()
                    duration = t_after_poll_success - poll_start
                    logger.info(f"Fallback simulated copy succeeded after {attempts} attempts in {duration:.3f}s")
                    break

                # Check if we would exceed timeout with the next sleep
                if (time.perf_counter() - poll_start + delay) >= timeout:
                    logger.debug(f"Would exceed timeout with next delay ({delay:.3f}s), stopping polling")
                    break

                # Sleep using the current backoff delay
                time.sleep(delay)
                # Increase delay for next attempt
                delay = min(delay * backoff_factor, max_delay)

            # If simulation did not change clipboard, abort — only translate when clipboard changed.
            if not new_clip or new_clip == prev_clip:
                t_after_poll_success = time.perf_counter()
                total_elapsed = t_after_poll_success - t_start
                logger.info(f"No new clipboard text detected after polling; timeout reached (elapsed={total_elapsed:.3f}s, attempts={attempts})")
                if self.tray_manager:
                    self.tray_manager.show_notification(
                        "WhisperBridge",
                        "Copy-translate failed: no clipboard text detected"
                    )
                # Performance summary: clipboard time measured from simulation to poll end, translation 0
                clipboard_ms = ((t_after_poll_success - (t_after_sim or t_start)) * 1000) if t_after_sim else 0
                t_end = time.perf_counter()
                total_ms = (t_end - t_start) * 1000
                logger.info(f"Copy-translate performance: clipboard={clipboard_ms:.0f}ms, translation=0ms, total={total_ms:.0f}ms")
                return

            # At this point new_clip contains the text to translate (from clipboard)
            text_to_translate = new_clip
            if not text_to_translate:
                logger.info("No text to translate (empty selection)")
                if self.tray_manager:
                    self.tray_manager.show_notification(
                        "WhisperBridge",
                        "Copy-translate: no text selected to translate"
                    )
                t_end = time.perf_counter()
                logger.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                return

            # Check for API key presence before attempting translation
            api_key = config_service.get_setting("openai_api_key", use_cache=False)
            if not api_key:
                logger.info("No API key configured, showing original text only")
                # Emit overlay with original text only (no translation attempt)
                # Performance summary: compute clipboard time, translation=0
                clipboard_ms = ((t_after_poll_success - (t_after_sim or t_start)) * 1000) if t_after_poll_success and t_after_sim else 0
                t_end = time.perf_counter()
                total_ms = (t_end - t_start) * 1000
                logger.info(f"Copy-translate performance: clipboard={clipboard_ms:.0f}ms, translation=0ms, total={total_ms:.0f}ms")
                self.copy_translate_signal.emit(text_to_translate, "")
                logger.info("Copy-translate overlay shown (original text only) due to missing API key")
                return

            # Translate text synchronously (respect ocr_auto_swap_en_ru setting) — with debug logs and live config check
            translation_service = get_translation_service()
            try:
                # Try to detect language and apply EN<->RU auto-swap if enabled in settings
                from ..utils.api_utils import detect_language

                logger.debug(f"Copy-translate: text length={len(text_to_translate)}")
                detected = detect_language(text_to_translate) or "auto"
                logger.debug(f"Copy-translate: detected language='{detected}'")

                # Read current settings live from config_service to respect UI changes
                swap_enabled = bool(config_service.get_setting("ocr_auto_swap_en_ru", use_cache=False))
                target_cfg = config_service.get_setting("target_language", use_cache=False) or "en"
                logger.debug(f"Copy-translate: ocr_auto_swap_en_ru={swap_enabled}, configured target='{target_cfg}'")

                if swap_enabled:
                    if detected == "en":
                        target = "ru"
                    elif detected == "ru":
                        target = "en"
                    else:
                        target = target_cfg
                    logger.debug(f"Copy-translate: auto-swap active — translating from '{detected}' to '{target}'")
                    # Show a brief translating notification
                    try:
                        if self.tray_manager:
                            self.tray_manager.show_notification("WhisperBridge", "Translating...")
                    except Exception:
                        pass
                    response = translation_service.translate_text_sync(
                        text_to_translate, source_lang=detected, target_lang=target
                    )
                else:
                    logger.debug(f"Copy-translate: auto-swap disabled — using configured target '{target_cfg}'")
                    # Show a brief translating notification
                    try:
                        if self.tray_manager:
                            self.tray_manager.show_notification("WhisperBridge", "Translating...")
                    except Exception:
                        pass
                    response = translation_service.translate_text_sync(
                        text_to_translate, source_lang=detected if detected != "auto" else None, target_lang=target_cfg
                    )
            except Exception as exc:
                logger.error(f"Copy-translate: error during language detection/auto-swap: {exc}", exc_info=True)
                # Fallback to default translation call on any failure
                try:
                    if self.tray_manager:
                        self.tray_manager.show_notification("WhisperBridge", "Translating...")
                except Exception:
                    pass
                response = translation_service.translate_text_sync(text_to_translate)

            # Mark translation completion time
            t_after_translation = time.perf_counter()

            translated_text = getattr(response, "translated_text", None) or str(response)

            # Read auto_copy_translated setting live and set pending flag so main thread can copy AFTER overlay is shown
            try:
                auto_copy = bool(config_service.get_setting("auto_copy_translated", use_cache=False))
            except Exception as e:
                logger.debug(f"Failed to read auto_copy_translated setting: {e}")
                auto_copy = False

            self._pending_auto_copy_translated = auto_copy
            logger.debug(f"auto_copy_translated={auto_copy}; pending flag set={self._pending_auto_copy_translated}")

            # Performance summary: compute clipboard and translation durations and log once
            clipboard_ms = ((t_after_poll_success - (t_after_sim or t_start)) * 1000) if (t_after_poll_success and t_after_sim) else 0
            translation_ms = ((t_after_translation - t_after_poll_success) * 1000) if (t_after_translation and t_after_poll_success) else 0
            t_end = time.perf_counter()
            total_ms = (t_end - t_start) * 1000
            logger.info(f"Copy-translate performance: clipboard={clipboard_ms:.0f}ms, translation={translation_ms:.0f}ms, total={total_ms:.0f}ms")

            # Emit signal to show overlay from main thread
            self.copy_translate_signal.emit(text_to_translate, translated_text)
            logger.info("Copy-translate hotkey processed successfully (fallback simulated copy path)")
        except Exception as e:
            logger.error(f"Error in copy-translate hotkey handler: {e}", exc_info=True)
            if self.tray_manager:
                self.tray_manager.show_notification(
                    "WhisperBridge",
                    f"Copy-translate error: {str(e)}"
                )
            # Ensure we still log performance summary on unexpected errors
            try:
                t_end = time.perf_counter()
                total_ms = (t_end - t_start) * 1000
                # If we had poll or sim times, include them; else set to 0
                clipboard_ms = ((t_after_poll_success - (t_after_sim or t_start)) * 1000) if (t_after_poll_success and t_after_sim) else 0
                translation_ms = ((t_after_translation - t_after_poll_success) * 1000) if (t_after_translation and t_after_poll_success) else 0
                logger.info(f"Copy-translate performance: clipboard={clipboard_ms:.0f}ms, translation={translation_ms:.0f}ms, total={total_ms:.0f}ms")
            except Exception:
                pass

    @Slot(str, str)
    def _handle_copy_translate(self, clipboard_text: str, translated_text: str):
        """Slot to handle copy-translate signal in main thread.

        This slot is called from the hotkey handler via Qt signal to ensure
        that overlay window creation happens in the main Qt thread, avoiding
        threading issues with Qt widgets.
        """
        try:
            self.show_overlay_window(clipboard_text, translated_text, overlay_id="copy_translate")

            # If auto-copy was requested, copy translated_text to clipboard AFTER overlay is shown
            try:
                if getattr(self, "_pending_auto_copy_translated", False):
                    clipboard_service = getattr(self, "clipboard_service", None)
                    if clipboard_service is None:
                        clipboard_service = get_clipboard_service()
                    try:
                        if clipboard_service and clipboard_service.copy_text(translated_text):
                            logger.info("Translated text copied to clipboard (auto_copy_translated enabled)")
                        else:
                            logger.warning("Failed to copy translated text to clipboard (ClipboardService.copy_text returned False or service unavailable)")
                    except Exception as e:
                        logger.error(f"Auto-copy failed: {e}", exc_info=True)
                    finally:
                        # Clear the pending flag regardless of result to avoid repeated copies
                        self._pending_auto_copy_translated = False
            except Exception as e:
                logger.error(f"Error during auto-copy handling: {e}", exc_info=True)

            logger.info("Copy-translate overlay shown successfully")
        except Exception as e:
            logger.error(f"Error showing copy-translate overlay: {e}")
            if self.tray_manager:
                self.tray_manager.show_notification(
                    "WhisperBridge",
                    f"Copy-translate overlay error: {str(e)}"
                )

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
            logger.info(f"Converted to pixels: x={x}, y={y}, w={width}, h={height}")

            # Run capture and OCR in background thread
            region = Rectangle(x, y, width, height)
            logger.info(f"Creating CaptureOcrTranslateWorker with region: {region}")
            worker = CaptureOcrTranslateWorker(region=region)
            thread = QThread()
            logger.info("Moving worker to QThread")
            worker.moveToThread(thread)

            # Add info/debug logging for worker signals with named slots
            def on_worker_started():
                logger.info("Worker started successfully")

            def on_worker_progress(msg):
                logger.info(f"Worker progress: {msg}")

            def on_worker_error(msg):
                logger.error(f"Worker error: {msg}")

            worker.started.connect(on_worker_started)
            worker.progress.connect(on_worker_progress)
            worker.error.connect(on_worker_error)

            logger.info("Connecting worker.run to thread.started and starting thread")
            thread.started.connect(worker.run)

            # Ensure UI actions are executed on the main thread via a Qt slot on self
            worker.finished.connect(self._handle_worker_finished)
            worker.error.connect(self._show_ocr_error)

            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.start()
            self._worker_threads.append((thread, worker))  # Store both to prevent GC
            logger.info(f"QThread started and worker-thread pair stored in self._worker_threads (count: {len(self._worker_threads)})")
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

    @Slot(str, str, str)
    def _handle_worker_finished(self, original_text: str, translated_text: str, overlay_id: str):
        """Slot to handle worker finished signal — guaranteed to run in QtApp (main) thread.

        Use a canonical overlay id for OCR results to avoid creating duplicate windows.
        """
        try:
            logger.info("Worker finished slot invoked in main thread")
            # Normalize to a single OCR overlay to avoid duplicates shown by other legacy slots
            canonical_overlay_id = "ocr"
            self.show_overlay_window(original_text, translated_text, overlay_id=canonical_overlay_id)
        except Exception as e:
            logger.error(f"Error in _handle_worker_finished slot: {e}", exc_info=True)


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
        """Open settings dialog window."""
        logger.info("Open settings requested from tray")

        # Create dialog if it doesn't exist or was closed
        if self.settings_dialog is None or not self.settings_dialog.isVisible():
            self.settings_dialog = SettingsDialog(parent=self.main_window if self.main_window else None)

            # Connect finished signal to reset dialog reference
            self.settings_dialog.finished.connect(lambda: setattr(self, 'settings_dialog', None))

        # Show and activate the dialog
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

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
        config_service.set_setting("theme", theme)
        logger.debug(f"Qt application theme updated to: {theme}")

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

        logger.debug(f"Window opacity updated to: {opacity}")

    def run(self):
        """Run the application main loop."""
        if not self.is_running:
            self.initialize()

        # Main window is created but starts hidden to tray
        # Only accessible through tray menu or hotkeys

        try:
            logger.info("Starting Qt-based WhisperBridge main loop...")
            return self.qt_app.exec()
        except Exception as e:
            logger.error(f"Qt application error: {e}")
        finally:
            self.shutdown()

    def shutdown(self):
        """Shutdown the application gracefully."""
        if self.shutdown_requested:
            return
        self.shutdown_requested = True

        logger.info("Shutting down Qt-based WhisperBridge...")

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
            logger.warning(f"Error shutting down OCR service: {e}")

        # Shutdown translation service
        try:
            translation_service = get_translation_service()
            translation_service.shutdown()
        except Exception as e:
            logger.warning(f"Error shutting down translation service: {e}")

        # Shutdown API manager
        try:
            from ..core.api_manager import get_api_manager
            api_manager = get_api_manager()
            api_manager.shutdown()
        except Exception as e:
            logger.warning(f"Error shutting down API manager: {e}")

        # Close overlay windows
        for overlay in self.overlay_windows.values():
            overlay.close()
        self.overlay_windows.clear()

        # Close main window
        if self.main_window:
            self.main_window.close()

        logger.info("Qt-based WhisperBridge shutdown complete")

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
            logger.debug("Main window hidden (minimized to tray)")

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