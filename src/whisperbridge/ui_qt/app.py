"""
Qt-based application class for WhisperBridge.
Provides compatible interface with the existing CTK-based application.
"""

import sys
import os
from PySide6.QtGui import QIcon
from typing import Any, Dict, Optional, cast

from loguru import logger
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication


# Clipboard singleton accessor (used to obtain a shared ClipboardService)
from ..services.clipboard_service import get_clipboard_service
from ..services.config_service import SettingsObserver, config_service
from ..services.copy_translate_service import CopyTranslateService
from ..services.hotkey_service import HotkeyService
from ..services.ocr_service import get_ocr_service
from ..services.theme_service import ThemeService
from ..services.translation_service import get_translation_service

# UI service extracted to manage window/overlay lifecycle
from ..services.app_services import AppServices
# Worker classes for background processing
from .workers import SettingsSaveWorker
# UI widgets are managed by UIService; direct imports removed to avoid tight coupling



class QtApp(QObject, SettingsObserver):
    """Qt-based application class with compatible interface."""

    # Signal for copy-translate hotkey to ensure UI operations happen in main thread
    copy_translate_signal = Signal(str, str)

    # New signals for UI operations
    show_main_window_signal = Signal()
    show_settings_signal = Signal()
    toggle_overlay_signal = Signal()
    activate_ocr_signal = Signal()
    ocr_ready_signal = Signal()

    def __init__(self):
        """Initialize the Qt application."""
        super().__init__()
        app_instance = QApplication.instance()
        self.qt_app = cast(QApplication, app_instance if app_instance is not None else QApplication(sys.argv))

        # Configure application
        self.qt_app.setApplicationName("WhisperBridge")
        self.qt_app.setApplicationVersion("1.0.0")
        self.qt_app.setOrganizationName("WhisperBridge")
        # Set application icon
        icon_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "assets",
            "icons",
            "app_icon.png",
        )
        if os.path.exists(icon_path):
            self.qt_app.setWindowIcon(QIcon(icon_path))
            logger.debug(f"Loaded application icon from: {icon_path}")
        else:
            logger.warning(f"Application icon not found at: {icon_path}")

        # Prevent app from quitting when all windows are closed (tray keeps it running)
        self.qt_app.setQuitOnLastWindowClosed(False)

        # Connect shutdown to Qt's aboutToQuit signal to ensure cleanup on any exit
        self.qt_app.aboutToQuit.connect(self.shutdown)

        # Worker threads (holds (thread, worker) pairs to prevent garbage collection)
        self._worker_threads: list = []  # Holds (thread, worker) pairs to prevent garbage collection

        # Services
        self.hotkey_service: Optional[HotkeyService] = None
        self.keyboard_manager = None
        self.overlay_service = None
        self.services: Optional[AppServices] = None

        # Application state
        self.is_running = False
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
        self.ocr_ready_signal.connect(self._on_ocr_service_ready)

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

            # Initialize overlay service (kept for logging/backward compatibility)
            self._initialize_overlay_service()

            # Centralize service creation and lifecycle
            self.services = AppServices(app=self, clipboard_service=self.clipboard_service)
            self.services.setup_services(
                on_translate=self._on_translate_hotkey,
                on_quick_translate=self._on_quick_translate_hotkey,
                on_activate=self._on_activation_hotkey,
                on_copy_translate=self._on_copy_translate_hotkey,
            )

            # Expose commonly used references for backward-compatibility
            self.ui_service = self.services.ui_service
            self.notification_service = self.services.notification_service
            self.copy_translate_service = self.services.copy_translate_service
            self.keyboard_manager = self.services.keyboard_manager
            self.hotkey_service = self.services.hotkey_service

            self.is_running = True
            logger.info("Qt-based WhisperBridge application initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Qt application: {e}")
            raise


    def _initialize_overlay_service(self):
        """Initialize the overlay service."""
        try:
            # For Qt, we'll use our own overlay windows
            logger.info("Qt overlay service initialized (using Qt windows)")
        except Exception as e:
            logger.error(f"Failed to initialize Qt overlay service: {e}")

    @Slot()
    def _on_ocr_service_ready(self):
        """Slot for when OCR service is ready — delegate to UIService."""
        if self.services and self.services.ui_service:
            self.services.ui_service.handle_ocr_service_ready()


    # SettingsObserver methods
    def on_settings_changed(self, key: str, old_value, new_value):
        """Called when a setting value changes."""
        hotkey_keys = [
            "translate_hotkey",
            "quick_translate_hotkey",
            "activation_hotkey",
            "copy_translate_hotkey",
        ]

        # If a hotkey setting or OCR initialization flag changed, re-register hotkeys
        if key in hotkey_keys or key == "initialize_ocr":
            logger.debug(f"Setting '{key}' changed from '{old_value}' to '{new_value}'. Reloading hotkeys.")
            try:
                # Prefer services-managed instances when available
                km = self.services.keyboard_manager if getattr(self, "services", None) else self.keyboard_manager
                hs = self.services.hotkey_service if getattr(self, "services", None) else self.hotkey_service

                if km:
                    km.clear_all_hotkeys()
                    if hs:
                        hs.register_application_hotkeys(
                            config_service=config_service,
                            on_translate=self._on_translate_hotkey,
                            on_quick_translate=self._on_quick_translate_hotkey,
                            on_activate=self._on_activation_hotkey,
                            on_copy_translate=self._on_copy_translate_hotkey
                        )

                if hs and hs.is_running():
                    if hs.reload_hotkeys():
                        logger.info("Hotkeys reloaded successfully after settings change")
                    else:
                        logger.error("Failed to reload hotkeys after settings change")
            except Exception as e:
                logger.error(f"Error updating hotkeys after settings change: {e}", exc_info=True)

        if key == "initialize_ocr":
            # Handle OCR service initialization/deinitialization
            try:
                if new_value:
                    # Initialize OCR via AppServices
                    self.services.initialize_ocr_async()
                    if self.ui_service and self.ui_service.tray_manager:
                        self.ui_service.tray_manager.update_ocr_action_enabled(True)
                    logger.info("OCR enabled via settings; initialized service and enabled menu")
                else:
                    if self.ui_service and self.ui_service.tray_manager:
                        self.ui_service.tray_manager.update_ocr_action_enabled(False)
                    logger.info("OCR disabled via settings; menu disabled (hotkeys remain for on-demand)")
            except Exception as e:
                logger.error(f"Error handling initialize_ocr change: {e}", exc_info=True)

    def on_settings_loaded(self, settings):
        """Called when settings are loaded."""
        pass

    def on_settings_saved(self, settings):
        """Called when settings are saved."""
        pass

    def _on_translate_hotkey(self):
        """Handle main translation hotkey press."""
        logger.info("Main translation hotkey pressed")
        translate_hotkey = config_service.get_setting("translate_hotkey", use_cache=False)
        logger.debug(f"Hotkey: {translate_hotkey}")

        # Check OCR service readiness
        ocr_service = get_ocr_service()
        logger.debug(f"OCR service engine available: {ocr_service.is_ocr_engine_ready()}")

        self.activate_ocr_signal.emit()

    # def _capture_and_process(self):
    #     """Legacy non-UI capture method - replaced by UI selection overlay."""
    #     pass  # Not used; UI selection handles interactive capture

    def _on_quick_translate_hotkey(self):
        """Handle quick translation hotkey press - triggers OCR capture."""
        logger.info("Quick translation hotkey pressed - starting OCR capture")
        quick_translate_hotkey = config_service.get_setting("quick_translate_hotkey", use_cache=False)
        logger.debug(f"Hotkey: {quick_translate_hotkey}")
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
        if self.services and self.services.ui_service:
            self.services.ui_service.show_main_window()
        # Use centralized NotificationService
        try:
            if self.services and self.services.notification_service:
                self.services.notification_service.info("Application activated", "WhisperBridge")
        except Exception as e:
            logger.debug(f"Failed to show activation notification: {e}")
        logger.debug("Tray notification shown for application activation")

    @Slot()
    def _show_settings_slot(self):
        if self.services and self.services.ui_service:
            self.services.ui_service.open_settings()

    @Slot()
    def _toggle_overlay_slot(self):
        if self.services and self.services.ui_service:
            self.services.ui_service.toggle_overlay()

    @Slot()
    def _activate_ocr_slot(self):
        if self.services and self.services.ui_service:
            self.services.ui_service.activate_ocr()

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
        if self.services and self.services.ui_service:
            self.services.ui_service.activate_ocr()


    @Slot(str, str, str)
    def _handle_worker_finished(self, original_text: str, translated_text: str, overlay_id: str):
        """Slot to handle worker finished signal — delegate to UIService."""
        try:
            logger.info("Worker finished slot invoked in main thread (delegating to UIService)")
            if self.services and self.services.ui_service:
                self.services.ui_service.handle_worker_finished(original_text, translated_text, overlay_id)
        except Exception as e:
            logger.error(f"Error in _handle_worker_finished delegate: {e}", exc_info=True)

    def show_main_window(self):
        """Show the main settings window (delegates to UIService)."""
        if self.services and self.services.ui_service:
            self.services.ui_service.show_main_window()

    def hide_main_window_to_tray(self):
        """Hide the main window to system tray (delegate to UIService)."""
        if self.services and self.services.ui_service:
            self.services.ui_service.hide_main_window_to_tray()

    def toggle_overlay(self):
        """Toggle overlay visibility — delegate to UIService."""
        if self.services and self.services.ui_service:
            self.services.ui_service.toggle_overlay()

    def exit_app(self):
        """Exit the application."""
        logger.info("Exit application requested from tray")
        self.qt_app.quit()

    def open_settings(self):
        """Open settings dialog window (delegate to UIService)."""
        if self.services and self.services.ui_service:
            self.services.ui_service.open_settings()

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
            try:
                if self.services and self.services.notification_service:
                    self.services.notification_service.info(message, "WhisperBridge")
            except Exception as e:
                logger.debug(f"Failed to show success notification: {e}")
        else:
            logger.error(f"Failed to save settings asynchronously: {message}")
            try:
                if self.services and self.services.notification_service:
                    self.services.notification_service.error(f"Error: {message}", "WhisperBridge")
            except Exception as e:
                logger.debug(f"Failed to show error notification: {e}")

    def show_overlay_window(
        self,
        original_text: str,
        translated_text: str,
        position: Optional[tuple] = None,
        overlay_id: str = "main",
    ):
        """Show the overlay window with translation results (delegate to UIService)."""
        if self.services and self.services.ui_service:
            self.services.ui_service.show_overlay_window(original_text, translated_text, position=position, overlay_id=overlay_id)

    def hide_overlay_window(self, overlay_id: str = "main"):
        """Hide the overlay window (delegate to UIService)."""
        if self.services and self.services.ui_service:
            self.services.ui_service.hide_overlay_window(overlay_id=overlay_id)

    def update_theme(self, theme: str):
        """Update application theme.

        Args:
            theme: New theme ('dark', 'light', or 'system')
        """
        if self.services and self.services.ui_service:
            self.services.ui_service.update_theme(theme)
        # Keep local theme state in sync with ThemeService
        self._current_theme = self.theme_service._current_theme
        logger.debug(f"Qt application theme updated to: {theme}")

    def update_window_opacity(self, opacity: float):
        """Update window opacity for all windows.

        Args:
            opacity: Opacity value between 0.0 and 1.0
        """
        opacity = max(0.1, min(1.0, opacity))  # Clamp between 0.1 and 1.0
        if self.services and self.services.ui_service:
            self.services.ui_service.update_window_opacity(opacity)

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
    
        # Shutdown clipboard service
        if self.clipboard_service:
            try:
                self.clipboard_service.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down clipboard service: {e}")
    
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
        if self.services and self.services.ui_service:
            self.services.ui_service.shutdown_ui()
 
        logger.info("Qt-based WhisperBridge shutdown complete")

    def is_app_running(self) -> bool:
        """Check if the application is running.

        Returns:
            bool: True if application is running
        """
        return self.is_running and self.qt_app is not None



    def hide_main_window(self):
        """Hide the main window (minimize to tray)."""
        if self.services and self.services.ui_service:
            self.services.ui_service.hide_main_window_to_tray()

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
