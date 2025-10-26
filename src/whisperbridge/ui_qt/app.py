"""
Qt-based application class for WhisperBridge.
Provides compatible interface with the existing CTK-based application.
"""

import sys
import os
from PySide6.QtGui import QIcon
from typing import Any, Dict, Optional, Protocol, cast

from loguru import logger
from ..core.version import get_version
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication


class RunnableWorker(Protocol):
    """Protocol for QObject workers that can be run by the factory."""
    finished: Signal
    error: Signal

    def run(self): ...
    def moveToThread(self, thread: QThread): ...
    def deleteLater(self): ...


from ..services.config_service import SettingsObserver, config_service
from ..services.ocr_service import get_ocr_service
from ..services.theme_service import ThemeService
from ..services.translation_service import get_translation_service
from ..core.api_manager import get_api_manager

# UI service extracted to manage window/overlay lifecycle
from ..services.app_services import AppServices
from ..services.ui_service import UIService
from ..services.notification_service import NotificationService
from ..services.copy_translate_service import CopyTranslateService
# UI widgets are managed by UIService; direct imports removed to avoid tight coupling


class QtApp(QObject, SettingsObserver):
    """Qt-based application class with compatible interface."""

    # New signals for UI operations
    show_main_window_signal = Signal()
    show_settings_signal = Signal()
    toggle_overlay_signal = Signal()
    activate_ocr_signal = Signal()
    ocr_ready_signal = Signal()

    def __init__(self):
        """Initialize the Qt application."""
        import time
        start_time = time.time()
        super().__init__()

        logger.debug(f"QtApp.__init__: Starting (timestamp: {start_time:.3f})")

        app_instance = QApplication.instance()
        self.qt_app = cast(QApplication, app_instance if app_instance is not None else QApplication(sys.argv))
        logger.debug(f"QtApp.__init__: QApplication created in {time.time() - start_time:.3f}s")

        # Configure application
        self.qt_app.setApplicationName("WhisperBridge")
        # Defer version setting to initialize() to avoid import delays
        # self.qt_app.setApplicationVersion(get_version())
        self.qt_app.setOrganizationName("WhisperBridge")
        logger.debug(f"QtApp.__init__: Basic app config done in {time.time() - start_time:.3f}s")

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
        logger.debug(f"QtApp.__init__: Icon loaded in {time.time() - start_time:.3f}s")

        # Prevent app from quitting when all windows are closed (tray keeps it running)
        self.qt_app.setQuitOnLastWindowClosed(False)

        # Connect shutdown to Qt's aboutToQuit signal to ensure cleanup on any exit
        self.qt_app.aboutToQuit.connect(self.shutdown)

        # Worker threads (holds (thread, worker) pairs to prevent garbage collection)
        self._worker_threads: list = []  # Holds (thread, worker) pairs to prevent garbage collection

        # Services
        self.services: Optional[AppServices] = None

        # Application state
        self.is_running = False
        self.shutdown_requested = False

        # Register as config service observer first
        config_service.add_observer(self)

        # Connect UI signals to slots
        self.show_main_window_signal.connect(self._show_main_window_slot)
        self.show_settings_signal.connect(self._show_settings_slot)
        self.toggle_overlay_signal.connect(self._toggle_overlay_slot)
        self.activate_ocr_signal.connect(self._activate_ocr_slot)
        self.ocr_ready_signal.connect(self._on_ocr_service_ready)

        # Defer settings loading and theme service initialization to initialize()
        # _ = config_service.get_settings()
        # self.theme_service = ThemeService(qt_app=self.qt_app, config_service=config_service)

        logger.debug(f"QtApp.__init__: Completed in {time.time() - start_time:.3f}s")

    @property
    def ui(self) -> Optional[UIService]:
        """Возвращает ui_service, если он доступен."""
        return self.services.ui_service if self.services else None

    @property
    def notifier(self) -> Optional[NotificationService]:
        """Возвращает notification_service, если он доступен."""
        return self.services.notification_service if self.services else None

    @property
    def copy_translator(self) -> Optional[CopyTranslateService]:
        """Возвращает copy_translate_service, если он доступен."""
        return self.services.copy_translate_service if self.services else None

    def initialize(self):
        """Initialize application components."""
        try:
            import time
            init_start = time.time()
            logger.info("Initializing Qt-based WhisperBridge application...")

            # Set application version (deferred from __init__ to avoid import delays)
            self.qt_app.setApplicationVersion(get_version())
            logger.debug(f"initialize: Version set in {time.time() - init_start:.3f}s")

            # Ensure settings are loaded before getting theme
            _ = config_service.get_settings()
            logger.debug(f"initialize: Settings loaded in {time.time() - init_start:.3f}s")

            # Initialize theme service (centralized theme state lives in ThemeService)
            self.theme_service = ThemeService(qt_app=self.qt_app, config_service=config_service)
            logger.debug(f"initialize: Theme service initialized in {time.time() - init_start:.3f}s")

            # Centralize service creation and lifecycle
            self.services = AppServices(app=self)
            self.services.setup_services(
                on_translate=self._on_translate_hotkey,
                on_quick_translate=self._on_quick_translate_hotkey,
                on_activate=self._on_activation_hotkey,
                on_copy_translate=self._on_copy_translate_hotkey,
            )
            logger.debug(f"initialize: Services set up in {time.time() - init_start:.3f}s")

            # Services are accessible via self.services.* (no aliases created)

            # Connect theme change notifications to UI layer
            try:
                self.theme_service.theme_changed.connect(self._on_theme_changed)
            except Exception as e:
                logger.debug(f"Failed to connect theme_changed signal: {e}")

            # Connect async settings save result from ConfigService to show notifications
            try:
                config_service.saved_async_result.connect(self._on_settings_async_result)
            except Exception as e:
                logger.debug(f"Failed to connect saved_async_result signal: {e}")

            self.is_running = True
            logger.info(f"Qt-based WhisperBridge application initialized successfully in {time.time() - init_start:.3f}s")

        except Exception as e:
            logger.error(f"Failed to initialize Qt application: {e}")
            raise

    @Slot()
    def _on_ocr_service_ready(self):
        """Slot for when OCR service is ready — delegate to UIService."""
        if self.ui:
            self.ui.handle_ocr_service_ready()

    @Slot(str)
    def _on_theme_changed(self, theme: str):
        """Forward ThemeService theme changes to UIService."""
        try:
            if self.ui:
                # Allow UIService to refresh any widget-level visuals if needed
                self.ui.on_theme_changed(theme)
        except Exception as e:
            logger.debug(f"Error handling theme_changed in QtApp: {e}")

    @Slot(bool, str)
    def _on_settings_async_result(self, success: bool, message: str):
        """Handle async settings save result (main thread)."""
        try:
            if self.notifier:
                if success:
                    self.notifier.info(message, "WhisperBridge")
                else:
                    self.notifier.error(f"Error: {message}", "WhisperBridge")
        except Exception as e:
            logger.debug(f"Failed to show async save notification: {e}")

    def _handle_hotkey_setting_change(self, key: str, old_value, new_value):
        """Handle changes to hotkey settings."""
        hotkey_keys = [
            "translate_hotkey",
            "quick_translate_hotkey",
            "activation_hotkey",
            "copy_translate_hotkey",
        ]

        if key in hotkey_keys:
            logger.debug(f"Setting '{key}' changed from '{old_value}' to '{new_value}'. Reloading hotkeys.")
            if self.services:
                self.services.reload_hotkeys()

    def _handle_ocr_setting_change(self, key: str, old_value, new_value):
        """Handle changes to OCR initialization setting."""
        if key != "initialize_ocr":
            return
            
        try:
            if new_value:
                # Initialize OCR via AppServices (guard for None)
                if self.services:
                    self.services.initialize_ocr_async()
                if self.ui and self.ui.tray_manager:
                    self.ui.tray_manager.update_ocr_action_enabled(True)
                logger.info("OCR enabled via settings; initialized service and enabled menu")
            else:
                if self.ui and self.ui.tray_manager:
                    self.ui.tray_manager.update_ocr_action_enabled(False)
                logger.info("OCR disabled via settings; menu disabled (hotkeys remain for on-demand)")
        except Exception as e:
            logger.error(f"Error handling initialize_ocr change: {e}", exc_info=True)

    def _handle_notification_setting_change(self, key: str, old_value, new_value):
        """Handle changes to notification visibility setting."""
        if key != "show_notifications":
            return
        try:
            if self.notifier:
                if bool(new_value):
                    self.notifier.enable()
                else:
                    self.notifier.disable()
            logger.info(f"Notifications {'enabled' if new_value else 'disabled'} via settings")
        except Exception as e:
            logger.error(f"Error handling show_notifications change: {e}", exc_info=True)

    # SettingsObserver methods
    def on_settings_changed(self, key: str, old_value, new_value):
        """Called when a setting value changes."""
        self._handle_hotkey_setting_change(key, old_value, new_value)
        self._handle_ocr_setting_change(key, old_value, new_value)
        self._handle_notification_setting_change(key, old_value, new_value)
        
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

    def _on_quick_translate_hotkey(self):
        """Handle quick translation hotkey press - shows overlay translator window."""
        logger.info("Quick translation hotkey pressed - showing overlay translator")
        quick_translate_hotkey = config_service.get_setting("quick_translate_hotkey", use_cache=False)
        logger.debug(f"Hotkey: {quick_translate_hotkey}")
        self.toggle_overlay_signal.emit()

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
        if self.copy_translator:
            try:
                self.copy_translator.run()
            except Exception as e:
                logger.error(f"CopyTranslateService.run failed: {e}", exc_info=True)
        else:
            logger.warning("CopyTranslateService is not available")

    @Slot()
    def _show_main_window_slot(self):
        if self.ui:
            self.ui.show_main_window()
        # Use centralized NotificationService
        try:
            if self.notifier:
                self.notifier.info("Application activated", "WhisperBridge")
        except Exception as e:
            logger.debug(f"Failed to show activation notification: {e}")
        logger.debug("Tray notification shown for application activation")

    @Slot()
    def _show_settings_slot(self):
        if self.ui:
            self.ui.open_settings()

    @Slot()
    def _toggle_overlay_slot(self):
        if self.ui:
            self.ui.toggle_overlay()

    @Slot()
    def _activate_ocr_slot(self):
        if self.ui:
            self.ui.activate_ocr()

    def activate_ocr(self):
        """Activate OCR selection overlay."""
        if self.ui:
            self.ui.activate_ocr()

    @Slot(str, str, str)
    def _handle_worker_finished(self, original_text: str, translated_text: str, overlay_id: str):
        """Slot to handle worker finished signal — delegate to UIService."""
        try:
            logger.info("Worker finished slot invoked in main thread (delegating to UIService)")
            if self.ui:
                self.ui.handle_worker_finished(original_text, translated_text, overlay_id)
        except Exception as e:
            logger.error(f"Error in _handle_worker_finished delegate: {e}", exc_info=True)

    @Slot(str)
    def _handle_worker_error(self, error_message: str):
        """Slot to handle worker error signal — delegate to UIService."""
        try:
            logger.error("Worker error slot invoked in main thread (delegating to UIService)")
            if self.ui:
                self.ui._handle_worker_error(error_message)
        except Exception as e:
            logger.error(f"Error in _handle_worker_error delegate: {e}", exc_info=True)

    def create_and_run_worker(self, worker: RunnableWorker, on_finished, on_error):
        """Centralized creates, configures, and starts a QThread for the worker."""
        thread = QThread()
        worker.moveToThread(thread)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        worker.finished.connect(worker.deleteLater)
        self._worker_threads.append((thread, worker))
        thread.finished.connect(lambda: self._worker_threads.remove((thread, worker)))
        thread.start()
        logger.info(f"Started worker {worker.__class__.__name__} in a new thread.")
        return thread, worker

    def show_main_window(self):
        """Show the main settings window (delegates to UIService)."""
        if self.ui:
            self.ui.show_main_window()

    def hide_main_window_to_tray(self):
        """Hide the main window to system tray (delegate to UIService)."""
        if self.ui:
            self.ui.hide_main_window_to_tray()

    def toggle_overlay(self):
        """Toggle overlay visibility — delegate to UIService."""
        if self.ui:
            self.ui.toggle_overlay()

    def exit_app(self):
        """Exit the application."""
        logger.info("Exit application requested from tray")
        self.qt_app.quit()

    def open_settings(self):
        """Open settings dialog window (delegate to UIService)."""
        if self.ui:
            self.ui.open_settings()


    def show_overlay_window(
        self,
        original_text: str,
        translated_text: str,
        position: Optional[tuple] = None,
        overlay_id: str = "main",
    ):
        """Show the overlay window with translation results (delegate to UIService)."""
        if self.ui:
            self.ui.show_overlay_window(original_text, translated_text, position=position, overlay_id=overlay_id)

    def hide_overlay_window(self, overlay_id: str = "main"):
        """Hide the overlay window (delegate to UIService)."""
        if self.ui:
            self.ui.hide_overlay_window(overlay_id=overlay_id)

    def update_theme(self, theme: str):
        """Update application theme.

        Args:
            theme: New theme ('dark', 'light', or 'system')
        """
        if self.ui:
            self.ui.update_theme(theme)
        logger.debug(f"Qt application theme updated to: {theme}")

    def update_window_opacity(self, opacity: float):
        """Update window opacity for all windows.

        Args:
            opacity: Opacity value between 0.0 and 1.0
        """
        opacity = max(0.1, min(1.0, opacity))  # Clamp between 0.1 and 1.0
        if self.ui:
            self.ui.update_window_opacity(opacity)

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

    def _safe_shutdown(self, service, service_name: str):
        """Safely shut down a service and log errors."""
        if service:
            try:
                service.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down {service_name}: {e}")

    def shutdown(self):
        """Shutdown the application gracefully."""
        if self.shutdown_requested:
            return
        self.shutdown_requested = True

        logger.info("Shutting down Qt-based WhisperBridge...")

        self.is_running = False

        # Shutdown services managed by AppServices
        if self.services:
            try:
                self.services.stop_hotkeys()
            except Exception:
                pass

            self._safe_shutdown(self.services.clipboard_service, "clipboard service")

            # Delegate UI-specific shutdown to UIService
            if self.ui:
                self.ui.shutdown_ui()

        # Shutdown global singleton services
        global_services = [
            (get_ocr_service(), "OCR service"),
            (get_translation_service(), "translation service"),
            (get_api_manager(), "API manager"),
        ]

        for service, name in global_services:
            self._safe_shutdown(service, name)

        logger.info("Qt-based WhisperBridge shutdown complete")

    def is_app_running(self) -> bool:
        """Check if the application is running.

        Returns:
            bool: True if application is running
        """
        return self.is_running and self.qt_app is not None

    def hide_main_window(self):
        """Hide the main window (minimize to tray)."""
        if self.ui:
            self.ui.hide_main_window_to_tray()


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
