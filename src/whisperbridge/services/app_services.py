"""
Centralized application services manager for WhisperBridge.
Encapsulates creation and lifecycle of UI, hotkeys, copy-translate, and backend services.
"""

from typing import Optional, Callable
from loguru import logger
from PySide6.QtCore import QObject

from .ui_service import UIService
from .hotkey_service import HotkeyService
from ..core.keyboard_manager import KeyboardManager
from .notification_service import get_notification_service
from .copy_translate_service import CopyTranslateService
from .config_service import config_service
from .ocr_service import get_ocr_service
from .translation_service import get_translation_service
from ..core.api_manager import init_api_manager


class AppServices(QObject):
    def __init__(self, app, clipboard_service=None):
        super().__init__()
        self.app = app
        self.clipboard_service = clipboard_service
        self.ui_service: Optional[UIService] = None
        self.notification_service = None
        self.copy_translate_service: Optional[CopyTranslateService] = None
        self.keyboard_manager: Optional[KeyboardManager] = None
        self.hotkey_service: Optional[HotkeyService] = None

    def setup_services(self,
                       on_translate: Callable,
                       on_quick_translate: Callable,
                       on_activate: Callable,
                       on_copy_translate: Callable):
        logger.info("AppServices: setting up services")

        # UI service
        try:
            self.ui_service = UIService(app=self.app, clipboard_service=self.clipboard_service)
        except Exception as e:
            logger.error(f"AppServices: Failed to instantiate UIService: {e}", exc_info=True)
            raise

        # Notification service
        self.notification_service = get_notification_service()
        try:
            if self.ui_service and getattr(self.ui_service, "tray_manager", None):
                self.notification_service.set_tray_manager(self.ui_service.tray_manager)
        except Exception as e:
            logger.debug(f"AppServices: Failed to set tray manager on NotificationService: {e}")

        # Copy-translate service
        self.copy_translate_service = CopyTranslateService(
            tray_manager=(self.ui_service.tray_manager if self.ui_service else None),
            clipboard_service=self.clipboard_service
        )
        try:
            self.copy_translate_service.result_ready.connect(self.app._on_copy_translate_result)
        except Exception:
            logger.debug("AppServices: Failed to connect copy_translate result signal")

        # Keyboard / hotkeys
        self.keyboard_manager = KeyboardManager()
        try:
            self.hotkey_service = HotkeyService(self.keyboard_manager)
        except Exception as e:
            logger.warning(f"AppServices: Hotkey service not available: {e}")
            self.hotkey_service = None

        if self.hotkey_service:
            try:
                self.hotkey_service.register_application_hotkeys(
                    config_service=config_service,
                    on_translate=on_translate,
                    on_quick_translate=on_quick_translate,
                    on_activate=on_activate,
                    on_copy_translate=on_copy_translate
                )
                if not self.hotkey_service.start():
                    logger.warning("AppServices: Failed to start hotkey service")
                    self.hotkey_service = None
                else:
                    logger.info("AppServices: Hotkey service started successfully")
            except Exception as e:
                logger.error(f"AppServices: Failed to create/register hotkeys: {e}")
                self.hotkey_service = None

        # OCR conditional init
        try:
            initialize_ocr = config_service.get_setting("initialize_ocr", use_cache=False)
            if initialize_ocr:
                logger.info("AppServices: OCR initialization enabled; starting background init")
                self.initialize_ocr_async()
            else:
                logger.info("AppServices: OCR initialization disabled by settings")
        except Exception as e:
            logger.warning(f"AppServices: Error checking OCR init setting: {e}")

        # Translation service
        self.initialize_translation_service()

        logger.info("AppServices: services setup completed")

    def initialize_ocr_async(self):
        logger.info("AppServices: starting OCR service initialization")
        try:
            ocr_service = get_ocr_service()

            def on_complete():
                try:
                    # Route to Qt main thread via app's signal
                    self.app.ocr_ready_signal.emit()
                except Exception as e:
                    logger.debug(f"AppServices: Failed to emit OCR ready signal: {e}")

            ocr_service.initialize(on_complete=on_complete)
            logger.info("AppServices: OCR service initialization triggered")
        except Exception as e:
            logger.error(f"AppServices: Failed to start OCR service initialization: {e}", exc_info=True)

    def initialize_translation_service(self):
        try:
            init_api_manager()
            logger.info("AppServices: API manager initialized successfully")
            translation_service = get_translation_service()
            if not translation_service.initialize():
                logger.warning("AppServices: Failed to initialize translation service")
            else:
                logger.info("AppServices: Translation service initialized successfully")
        except Exception as e:
            logger.warning(f"AppServices: Failed to initialize translation service: {e}")

    def stop_hotkeys(self):
        if self.hotkey_service:
            try:
                self.hotkey_service.stop()
            except Exception:
                pass
            self.hotkey_service = None