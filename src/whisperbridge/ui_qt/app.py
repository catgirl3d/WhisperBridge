"""
Qt-based application class for WhisperBridge.
Provides compatible interface with the existing CTK-based application.
"""

import sys
import time
from typing import Any, Dict, Optional

from loguru import logger
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication

from ..core.api_manager import init_api_manager
from ..core.keyboard_manager import KeyboardManager
from ..core.config import validate_api_key_format

# Clipboard singleton accessor (used to obtain a shared ClipboardService)
from ..services.clipboard_service import get_clipboard_service
from ..services.config_service import SettingsObserver, config_service
from ..services.copy_translate_service import CopyTranslateService
from ..services.hotkey_service import HotkeyService
from ..services.ocr_service import OCRRequest, get_ocr_service
from ..services.screen_capture_service import get_capture_service
from ..services.theme_service import ThemeService
from ..services.translation_service import get_translation_service

# UI service extracted to manage window/overlay lifecycle
from ..services.ui_service import UIService
from ..utils.screen_utils import Rectangle
from .main_window import MainWindow
from .overlay_window import OverlayWindow
from .selection_overlay import SelectionOverlayQt
from .settings_dialog import SettingsDialog
from .tray import TrayManager

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

    import time  # Import at class level for worker thread access

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
                logger.info("OCR not ready, triggering on-demand initialization")
                ocr_service.start_background_initialization()
                max_wait = 15.0
                wait_start = self.time.time()
                while self.time.time() - wait_start < max_wait:
                    if ocr_service.is_initialized:
                        break
                    self.time.sleep(0.2)
                if not ocr_service.is_initialized:
                    self.error.emit("OCR service initialization timed out during capture")
                    return
                logger.info("On-demand OCR initialization completed successfully")

            logger.debug("Starting OCR")
            # Get OCR languages from config service to ensure we have the latest saved values
            ocr_languages = config_service.get_setting("ocr_languages", use_cache=False)
            ocr_request = OCRRequest(
                image=image_to_process,
                languages=ocr_languages,
                preprocess=True,
                use_cache=True,
            )
            ocr_response = ocr_service.process_image(ocr_request)

            if self._cancel_requested:
                return

            original_text = ocr_response.text

            self.progress.emit("OCR completed, checking translation")

            # Translation
            translated_text = ""
            try:
                # Check presence of API key depending on selected provider (with legacy compatibility)
                provider = (config_service.get_setting("api_provider", use_cache=False) or "openai").strip().lower()
                openai_key = config_service.get_setting("openai_api_key", use_cache=False)
                google_key = config_service.get_setting("google_api_key", use_cache=False)

                def _has_valid_key(p: str) -> bool:
                    """
                    Validate API key presence and format using centralized core validation only.
                    """
                    provider = (p or "").strip().lower()
                    if provider == "google":
                        key = google_key
                    elif provider == "openai":
                        key = openai_key
                    else:
                        return False
                    return bool(key and validate_api_key_format(key, provider))

                if _has_valid_key(provider):
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
                                from ..utils.language_utils import detect_language

                                detected = detect_language(original_text) or "auto"
                                if detected == "en":
                                    target = "ru"
                                elif detected == "ru":
                                    target = "en"
                                else:
                                    target = "en"  # Default fallback

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
                            # When auto-swap is disabled, use UI-selected languages instead of global settings
                            ui_source = getattr(settings, "ui_source_language", "auto")
                            ui_target = getattr(settings, "ui_target_language", "en")
                            response = translation_service.translate_text_sync(
                                original_text, source_lang=ui_source, target_lang=ui_target
                            )

                        if response and getattr(response, "success", False):
                            translated_text = getattr(response, "translated_text", "") or ""
                            logger.debug("Translation completed successfully")
                        else:
                            error_msg = getattr(response, "error_message", "") if response else "Unknown error"
                            logger.warning(f"Translation failed or returned empty result: {error_msg}")
                else:
                    logger.debug("No valid API key for selected provider, skipping translation")
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


class SettingsSaveWorker(QObject):
    """Worker for saving settings asynchronously."""

    finished = Signal(bool, str)  # success, error_message

    def __init__(self, settings_to_save: Dict[str, Any]):
        super().__init__()
        self.settings_to_save = settings_to_save

    def run(self):
        """Save settings using the settings manager."""
        try:
            from ..core.config import Settings

            new_settings = Settings(**self.settings_to_save)
            if config_service.save_settings(new_settings):
                self.finished.emit(True, "Settings saved successfully.")
            else:
                self.finished.emit(False, "Failed to save settings.")
        except Exception as e:
            logger.error(f"Error in SettingsSaveWorker: {e}", exc_info=True)
            self.finished.emit(False, f"An error occurred: {e}")


class QtApp(QObject, SettingsObserver):
    """Qt-based application class with compatible interface."""

    # Signal for copy-translate hotkey to ensure UI operations happen in main thread
    copy_translate_signal = Signal(str, str)

    # New signals for UI operations
    show_main_window_signal = Signal()
    show_settings_signal = Signal()
    toggle_overlay_signal = Signal()
    activate_ocr_signal = Signal()

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
        # Prevent app from quitting when all windows are closed (tray keeps it running)
        self.qt_app.setQuitOnLastWindowClosed(False)

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

        # Connect UI signals to slots
        self.show_main_window_signal.connect(self._show_main_window_slot)
        self.show_settings_signal.connect(self._show_settings_slot)
        self.toggle_overlay_signal.connect(self._toggle_overlay_slot)
        self.activate_ocr_signal.connect(self._activate_ocr_slot)

        # Initialize clipboard service singleton (if available)
        try:
            self.clipboard_service = get_clipboard_service()
            if self.clipboard_service:
                logger.info("ClipboardService initialized and started in QtApp")
            else:
                logger.warning(
                    "ClipboardService not available; clipboard-backed features may be limited"
                )
        except Exception as e:
            self.clipboard_service = None
            logger.warning(f"Failed to initialize ClipboardService in QtApp: {e}")

        # Ensure settings are loaded before getting theme
        _ = config_service.get_settings()

        # Initialize theme service
        self.theme_service = ThemeService(qt_app=self.qt_app, config_service=config_service)
        self._current_theme = self.theme_service._current_theme

    def initialize(self):
        """Initialize application components."""
        try:
            logger.info("Initializing Qt-based WhisperBridge application...")

            # Initialize overlay service
            self._initialize_overlay_service()

            # Instantiate UIService to centralize window/overlay management.
            # Pass app=self so UIService can create and manage all UI components.
            try:
                self.ui_service = UIService(app=self, clipboard_service=self.clipboard_service)
                # Ensure key UI components are created in main thread for references and connections
                if self.ui_service.main_window is None:
                    self.ui_service._create_main_window()
                self.main_window = self.ui_service.main_window
                if self.ui_service.selection_overlay is None:
                    self.ui_service._create_selection_overlay(self)
                self.selection_overlay = self.ui_service.selection_overlay
                self.tray_manager = self.ui_service.tray_manager
                self.overlay_windows = self.ui_service.overlay_windows
                # Connect main window close-to-tray signal if main_window exists
                if self.main_window:
                    self.main_window.closeToTrayRequested.connect(self.hide_main_window_to_tray)
            except Exception as e:
                logger.error(f"Failed to instantiate UIService: {e}", exc_info=True)
                raise

            # Create copy-translate service
            self.copy_translate_service = CopyTranslateService(
                tray_manager=self.tray_manager, clipboard_service=self.clipboard_service
            )
            self.copy_translate_service.result_ready.connect(self._on_copy_translate_result)
    
            # Connect main window close-to-tray signal (UIService has created main_window)
            if self.main_window:
                self.main_window.closeToTrayRequested.connect(self.hide_main_window_to_tray)

            # Initialize keyboard services
            self._create_keyboard_services()

            # Initialize OCR service conditionally
            try:
                initialize_ocr = config_service.get_setting("initialize_ocr", use_cache=False)
                if initialize_ocr:
                    logger.info("OCR initialization enabled, starting background init...")
                    self._initialize_ocr_service()
                else:
                    logger.info("OCR initialization disabled by setting, skipping...")
            except Exception as e:
                logger.warning(f"Error checking OCR init setting: {e}")
                # Fallback: don't init

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
                on_activate_ocr=self.activate_ocr,
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

            # Check whether OCR features should be enabled
            initialize_ocr = bool(getattr(current_settings, "initialize_ocr", False))

            # Register main translation hotkey only if OCR is enabled
            if initialize_ocr:
                self.keyboard_manager.register_hotkey(
                    current_settings.translate_hotkey,
                    self._on_translate_hotkey,
                    "Main translation (OCR) hotkey",
                )
                logger.info(f"Registered OCR-dependent hotkey: {current_settings.translate_hotkey}")
            else:
                logger.info("OCR disabled: skipping registration of main translate hotkey")

            # Register quick translate hotkey only if OCR is enabled (OCR-dependent)
            if initialize_ocr and current_settings.quick_translate_hotkey != current_settings.translate_hotkey:
                self.keyboard_manager.register_hotkey(
                    current_settings.quick_translate_hotkey,
                    self._on_quick_translate_hotkey,
                    "Quick translation hotkey (OCR capture)",
                )
                logger.info(f"Registered OCR-dependent hotkey: {current_settings.quick_translate_hotkey}")
            elif not initialize_ocr:
                logger.info("OCR disabled: skipping registration of quick translate hotkey")

            # Register activation hotkey if different
            if (current_settings.activation_hotkey != current_settings.translate_hotkey and
                current_settings.activation_hotkey != current_settings.quick_translate_hotkey):
                self.keyboard_manager.register_hotkey(
                    current_settings.activation_hotkey,
                    self._on_activation_hotkey,
                    "Application activation hotkey",
                )

            # Register copy-translate hotkey
            self.keyboard_manager.register_hotkey(
                current_settings.copy_translate_hotkey,
                self._on_copy_translate_hotkey,
                "Copy->Translate hotkey",
            )

            # Log based on flag
            translate_status = (
                current_settings.translate_hotkey if initialize_ocr else "SKIPPED"
            )
            quick_status = (
                current_settings.quick_translate_hotkey
                if (
                    initialize_ocr
                    and current_settings.quick_translate_hotkey
                    != current_settings.translate_hotkey
                )
                else "SKIPPED"
            )
            logger.info(
                f"Registered hotkeys (OCR flag={initialize_ocr}): "
                f"translate={translate_status}, quick={quick_status}, "
                f"activation={current_settings.activation_hotkey}, "
                f"copy_translate={current_settings.copy_translate_hotkey}"
            )

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
        ocr_service = get_ocr_service()
        if not ocr_service.is_initialized:
            logger.info("OCR service initialization skipped (disabled)")
            return

        logger.info("OCR service initialization completed - service is now ready")
        logger.debug(f"OCR service status: initialized={ocr_service.is_initialized}")

        # If this was on-demand init and flag was False, update to True
        current_flag = config_service.get_setting("initialize_ocr", use_cache=False)
        if not current_flag:
            config_service.set_setting("initialize_ocr", True)
            logger.info("On-demand OCR init completed; updated initialize_ocr flag to True (persisted)")

        # Update tray icon to show normal state
        self.update_tray_status(is_loading=False)
        logger.debug("Tray status updated to normal (loading=False)")

        self.show_tray_notification("WhisperBridge", "OCR service is ready.")
        logger.info("User notification shown: OCR service ready")

    def _initialize_translation_service(self):
        """Initialize translation service."""
        try:
            # Initialize API manager
            init_api_manager()
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

        # Theme is handled by ThemeService observer

    def _on_config_settings_saved(self, saved_settings):
        """Handle settings saved through config service (e.g., from settings dialog)."""
        logger.info("Config settings saved, checking for theme changes...")

        # Theme is handled by ThemeService observer

    # SettingsObserver methods
    def on_settings_changed(self, key: str, old_value, new_value):
        """Called when a setting value changes."""
        hotkey_keys = [
            "translate_hotkey",
            "quick_translate_hotkey",
            "activation_hotkey",
            "copy_translate_hotkey",
        ]
        if key in hotkey_keys:
            logger.debug(f"Hotkey setting '{key}' changed from '{old_value}' to '{new_value}'")
            try:
                # Update KeyboardManager registrations to reflect the new combinations.
                # KeyboardManager holds the mapping of combinations -> callbacks, so we need
                # to clear and re-register the callbacks before reloading the HotkeyService.
                if hasattr(self, "keyboard_manager") and self.keyboard_manager:
                    self.keyboard_manager.clear_all_hotkeys()
                    self._register_default_hotkeys()

                # Reload hotkeys in the running HotkeyService to apply new registrations.
                if self.hotkey_service and self.hotkey_service.is_running():
                    if self.hotkey_service.reload_hotkeys():
                        logger.info("Hotkeys reloaded successfully after settings change")
                    else:
                        logger.error("Failed to reload hotkeys after settings change")
            except Exception as e:
                logger.error(f"Error updating hotkeys after settings change: {e}", exc_info=True)

        if key == "initialize_ocr":
            try:
                if new_value:
                    self._initialize_ocr_service()
                    if self.tray_manager:
                        self.tray_manager.update_ocr_action_enabled(True)
                    logger.info("OCR enabled via settings; initialized service and enabled menu")
                else:
                    if self.tray_manager:
                        self.tray_manager.update_ocr_action_enabled(False)
                    logger.info("OCR disabled via settings; menu disabled (hotkeys remain for on-demand)")
            except Exception as e:
                logger.error(f"Error handling initialize_ocr change: {e}", exc_info=True)

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

        # Emit to main thread for UI operations
        self.update_tray_status(is_active=True)
        self.activate_ocr_signal.emit()

    # def _capture_and_process(self):
    #     """Legacy non-UI capture method - replaced by UI selection overlay."""
    #     pass  # Not used; UI selection handles interactive capture

    def _show_capture_error(self, message: str):
        """Show capture error notification."""
        logger.error(f"Capture error: {message}")
        try:
            self.ui_service.show_tray_notification("WhisperBridge", f"Capture Error: {message}")
        except Exception as e:
            logger.error(f"Error showing capture notification: {e}", exc_info=True)

    def _show_ocr_error(self, message: str):
        """Show OCR error notification."""
        logger.error(f"OCR error: {message}")
        self.ui_service.show_tray_notification("WhisperBridge", f"OCR Error: {message}")

    def _on_quick_translate_hotkey(self):
        """Handle quick translation hotkey press - triggers OCR capture."""
        logger.info("Quick translation hotkey pressed - starting OCR capture")
        quick_translate_hotkey = config_service.get_setting("quick_translate_hotkey", use_cache=False)
        logger.debug(f"Hotkey: {quick_translate_hotkey}")
        self.update_tray_status(is_active=True)
        self.activate_ocr_signal.emit()

    def _on_activation_hotkey(self):
        """Handle application activation hotkey press."""
        logger.info("Application activation hotkey pressed")
        activation_hotkey = config_service.get_setting("activation_hotkey", use_cache=False)
        logger.debug(f"Hotkey: {activation_hotkey}")
        self.show_main_window_signal.emit()

    def _on_copy_translate_hotkey(self):
        """Handle copy-translate hotkey press using a simulated Ctrl+C copy.

        Added: API key presence check and structured performance logging.
        """
        logger.info("Copy-translate hotkey pressed (simulated copy handler)")
        self.copy_translate_service.run()

    @Slot(str, str)
    def _handle_copy_translate(self, clipboard_text: str, translated_text: str):
        """Slot to handle copy-translate signal in main thread — delegate to UIService."""
        try:
            auto_copy = getattr(self, "_pending_auto_copy_translated", False)
            # Delegate full handling to UIService
            self.ui_service.handle_copy_translate(clipboard_text, translated_text, auto_copy=auto_copy)
            # Clear pending flag regardless to preserve previous semantics
            try:
                self._pending_auto_copy_translated = False
            except Exception:
                pass
            logger.info("Copy-translate overlay shown successfully (delegated)")
        except Exception as e:
            logger.error(f"Error showing copy-translate overlay: {e}")

    @Slot()
    def _show_main_window_slot(self):
        self.ui_service.show_main_window()
        self.ui_service.show_tray_notification("WhisperBridge", "Application activated")
        logger.debug("Tray notification shown for application activation")

    @Slot()
    def _show_settings_slot(self):
        self.ui_service.open_settings()

    @Slot()
    def _toggle_overlay_slot(self):
        self.ui_service.toggle_overlay()

    @Slot()
    def _activate_ocr_slot(self):
        self.ui_service.activate_ocr()

    @Slot(str, str, bool)
    def _on_copy_translate_result(self, clipboard_text: str, translated_text: str, auto_copy: bool):
        """Slot to handle copy-translate service result in main thread."""
        try:
            self._pending_auto_copy_translated = auto_copy
            self._handle_copy_translate(clipboard_text, translated_text)
        except Exception as e:
            logger.error(f"Error handling copy-translate result: {e}")

    def activate_ocr(self):
        """Activate OCR selection overlay."""
        self.ui_service.activate_ocr()

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

    def _on_selection_canceled(self):
        """Handle selection cancellation."""
        logger.info("Selection canceled")
        try:
            self.ui_service.show_tray_notification("WhisperBridge", "Отменено")
        except Exception as e:
            logger.error(f"Error showing selection canceled notification: {e}", exc_info=True)

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
        """Slot to handle worker finished signal — delegate to UIService."""
        try:
            logger.info("Worker finished slot invoked in main thread (delegating to UIService)")
            self.ui_service.handle_worker_finished(original_text, translated_text, overlay_id)
        except Exception as e:
            logger.error(f"Error in _handle_worker_finished delegate: {e}", exc_info=True)


    def _show_error(self, message):
        """Show error notification."""
        logger.error(f"Showing error: {message}")
        try:
            self.ui_service.show_tray_notification("WhisperBridge", f"Error: {message}")
        except Exception as e:
            logger.error(f"Error showing generic notification: {e}", exc_info=True)

    def show_main_window(self):
        """Show the main settings window (delegates to UIService)."""
        self.ui_service.show_main_window()

    def hide_main_window_to_tray(self):
        """Hide the main window to system tray (delegate to UIService)."""
        self.ui_service.hide_main_window_to_tray()

    def toggle_overlay(self):
        """Toggle overlay visibility — delegate to UIService."""
        self.ui_service.toggle_overlay()

    def exit_app(self):
        """Exit the application."""
        logger.info("Exit application requested from tray")
        self.qt_app.quit()

    def open_settings(self):
        """Open settings dialog window (delegate to UIService)."""
        self.ui_service.open_settings()

    def save_settings_async(self, settings_data: Dict[str, Any]):
        """Save settings asynchronously using a worker thread."""
        logger.info("Starting asynchronous settings save.")
        worker = SettingsSaveWorker(settings_data)
        thread = QThread()
        worker.moveToThread(thread)

        worker.finished.connect(self._on_settings_saved_async)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start()
        self._worker_threads.append((thread, worker))

    def _on_settings_saved_async(self, success: bool, message: str):
        """Handle the result of the asynchronous settings save."""
        if success:
            logger.info(message)
            self.show_tray_notification("WhisperBridge", message)
        else:
            logger.error(f"Failed to save settings asynchronously: {message}")
            self.show_tray_notification("WhisperBridge", f"Error: {message}")

    def show_overlay_window(
        self,
        original_text: str,
        translated_text: str,
        position: Optional[tuple] = None,
        overlay_id: str = "main",
    ):
        """Show the overlay window with translation results (delegate to UIService)."""
        self.ui_service.show_overlay_window(original_text, translated_text, position=position, overlay_id=overlay_id)

    def hide_overlay_window(self, overlay_id: str = "main"):
        """Hide the overlay window (delegate to UIService)."""
        self.ui_service.hide_overlay_window(overlay_id=overlay_id)

    def update_theme(self, theme: str):
        """Update application theme.

        Args:
            theme: New theme ('dark', 'light', or 'system')
        """
        self.ui_service.update_theme(theme)
        # Keep local theme state in sync with ThemeService
        self._current_theme = self.theme_service._current_theme
        logger.debug(f"Qt application theme updated to: {theme}")

    def update_window_opacity(self, opacity: float):
        """Update window opacity for all windows.

        Args:
            opacity: Opacity value between 0.0 and 1.0
        """
        opacity = max(0.1, min(1.0, opacity))  # Clamp between 0.1 and 1.0
        self.ui_service.update_window_opacity(opacity)

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
            try:
                self.hotkey_service.stop()
            except Exception:
                pass
            self.hotkey_service = None

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

        # Delegate UI-specific shutdown to UIService to centralize lifecycle management
        self.ui_service.shutdown_ui()
 
        logger.info("Qt-based WhisperBridge shutdown complete")

    def is_app_running(self) -> bool:
        """Check if the application is running.

        Returns:
            bool: True if application is running
        """
        return self.is_running and self.qt_app is not None

    def show_tray_notification(self, title: str, message: str):
        """Show a notification through the system tray."""
        self.ui_service.show_tray_notification(title, message)

    def update_tray_status(self, is_active: bool = False, has_error: bool = False, is_loading: bool = False):
        """Update the tray icon status."""
        try:
            self.ui_service.update_tray_status(is_active=is_active, has_error=has_error, is_loading=is_loading)
        except Exception as e:
            logger.error(f"Error updating tray status: {e}", exc_info=True)

    def hide_main_window(self):
        """Hide the main window (minimize to tray)."""
        self.ui_service.hide_main_window()

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
