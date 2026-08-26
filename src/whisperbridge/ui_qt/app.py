"""
Qt-based application class for WhisperBridge.
Provides compatible interface with the existing CTK-based application.
"""

import sys
import os
import time
from PySide6.QtGui import QIcon
from typing import Optional, Protocol, cast

from loguru import logger
from ..core.version import get_version
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication

from ..services.config_service import SettingsObserver, config_service
from ..services.theme_service import ThemeService
from ..core.api_manager import get_api_manager
from ..core.config import BUILD_OCR_ENABLED
from ..services.app_services import AppServices
from ..services.ui_service import UIService
from ..services.notification_service import NotificationService
from ..services.copy_translate_service import CopyTranslateService
from .workers import start_qt_worker


class RunnableWorker(Protocol):
    """Protocol for QObject workers that can be run by the factory."""
    finished: Signal

    def run(self): ...
    def moveToThread(self, thread: QThread): ...
    def deleteLater(self): ...


class QtApp(QObject, SettingsObserver):
    """Qt-based application class with compatible interface."""

    # New signals for UI operations
    show_settings_signal = Signal()
    toggle_overlay_signal = Signal()
    activate_ocr_signal = Signal()

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
        self.show_settings_signal.connect(self._show_settings_slot)
        self.toggle_overlay_signal.connect(self._toggle_overlay_slot)
        self.activate_ocr_signal.connect(self._activate_ocr_slot)

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
                on_copy_translate=self._on_copy_translate_hotkey,
            )
            logger.debug(f"initialize: Services set up in {time.time() - init_start:.3f}s")

            # Services are accessible via self.services.* (no aliases created)

            # Connect theme change notifications to UI layer
            try:
                self.theme_service.theme_changed.connect(self._on_theme_changed)
            except Exception as e:
                logger.debug(f"Failed to connect theme_changed signal: {e}")

            self.is_running = True
            logger.info(f"Qt-based WhisperBridge application initialized successfully in {time.time() - init_start:.3f}s")

        except Exception as e:
            logger.error(f"Failed to initialize Qt application: {e}")
            raise

    @Slot(str)
    def _on_theme_changed(self, theme: str):
        """Forward ThemeService theme changes to UIService."""
        try:
            if self.ui:
                # Allow UIService to refresh any widget-level visuals if needed
                self.ui.on_theme_changed(theme)
        except Exception as e:
            logger.debug(f"Error handling theme_changed in QtApp: {e}")

    def _handle_hotkey_setting_change(self, key: str, old_value, new_value):
        """Handle changes to hotkey settings."""
        hotkey_keys = [
            "translate_hotkey",
            "quick_translate_hotkey",
            "copy_translate_hotkey",
        ]

        if key in hotkey_keys:
            logger.debug(f"Setting '{key}' changed from '{old_value}' to '{new_value}'. Reloading hotkeys.")
            if self.services:
                self.services.reload_hotkeys()

    def _handle_ocr_setting_change(self, key: str, old_value, new_value):
        """Handle changes to OCR settings."""
        if key not in ["ocr_enabled"]:
            return

        try:
            self._update_ocr_state()
        except Exception as e:
            logger.error(f"Error handling OCR setting change for key '{key}': {e}", exc_info=True)

    def _update_ocr_state(self):
        """Update OCR state, including the tray menu action."""
        is_available = BUILD_OCR_ENABLED and config_service.get_settings().ocr_enabled

        if self.ui and self.ui.tray_manager:
            self.ui.tray_manager.update_ocr_action_state()

        logger.info(f"OCR state updated. Available: {is_available}")

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

    def _on_translate_hotkey(self):
        """Handle main translation hotkey press."""
        logger.info("Main translation hotkey pressed")
        translate_hotkey = config_service.get_setting("translate_hotkey")
        logger.debug(f"Hotkey: {translate_hotkey}")

        self.activate_ocr_signal.emit()

    def _on_quick_translate_hotkey(self):
        """Handle quick translation hotkey press - shows overlay translator window."""
        logger.info("Quick translation hotkey pressed - showing overlay translator")
        quick_translate_hotkey = config_service.get_setting("quick_translate_hotkey")
        logger.debug(f"Hotkey: {quick_translate_hotkey}")
        self.toggle_overlay_signal.emit()

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

    @Slot(str, str, str, str)
    def _handle_worker_finished(self, original_text: str, translated_text: str, overlay_id: str, error_message: str = ""):
        """Slot to handle worker finished signal — delegate to UIService."""
        if self.ui:
            self.ui.handle_worker_finished(original_text, translated_text, overlay_id, error_message)

    def create_and_run_worker(self, worker: RunnableWorker, on_finished):
        """Centralized creates, configures, and starts a QThread for the worker."""
        started_worker, thread = start_qt_worker(worker, on_finished)
        self._worker_threads.append((thread, started_worker))
        thread.finished.connect(
            lambda: self._worker_threads.remove((thread, started_worker))
            if (thread, started_worker) in self._worker_threads
            else None
        )
        logger.info(f"Started worker {started_worker.__class__.__name__} in a new thread.")
        return thread, started_worker

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

    def hide_overlay_window(self, overlay_id: str = "main"):
        """Hide the overlay window (delegate to UIService)."""
        if self.ui:
            self.ui.hide_overlay_window(overlay_id=overlay_id)

    def run(self):
        """Run the application main loop."""
        if not self.is_running:
            self.initialize()

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

        # Cancel and drain workers before tearing down services that receive their signals.
        worker_threads = list(self._worker_threads)
        shutdown_deadline = time.monotonic() + 5.0

        # Pass 1: signal cancellation and quit for every worker concurrently,
        # so no thread's wait blocks another worker from receiving its cancel.
        for thread, worker in worker_threads:
            try:
                request_cancel = getattr(worker, "request_cancel", None)
                if callable(request_cancel):
                    request_cancel()
            except Exception as e:
                logger.warning(f"Error requesting worker cancellation: {e}")

            try:
                thread.quit()
            except Exception as e:
                logger.warning(f"Error stopping worker thread: {e}")

        # Pass 2: bounded join within the shared deadline.
        threads = [thread for thread, _ in worker_threads]
        while any(thread.isRunning() for thread in threads):
            remaining_ms = int((shutdown_deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                break
            for thread in threads:
                if thread.isRunning():
                    thread.wait(min(100, remaining_ms))

        for thread, worker in worker_threads:
            if thread.isRunning():
                logger.warning(
                    f"Worker thread {worker.__class__.__name__} did not stop during shutdown"
                )

        # Shutdown services managed by AppServices
        if self.services:
            try:
                self.services.stop_hotkeys()
            except Exception:
                pass

            # Delegate UI-specific shutdown to UIService
            if self.ui:
                self.ui.shutdown_ui()

        # Release API manager resources (provider clients hold HTTP connection pools)
        try:
            get_api_manager().shutdown()
        except Exception as e:
            logger.warning(f"Error shutting down API manager: {e}")

        logger.info("Qt-based WhisperBridge shutdown complete")

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
