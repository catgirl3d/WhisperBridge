"""
Centralized application services manager for WhisperBridge.
Encapsulates creation and lifecycle of UI, hotkeys, copy-translate, and backend services.
"""

from typing import Optional, Callable
from loguru import logger
from PySide6.QtCore import QObject, Slot

from .ui_service import UIService
from .hotkey_service import HotkeyService
from ..core.keyboard_manager import KeyboardManager
from .notification_service import get_notification_service
from .copy_translate_service import CopyTranslateService
from .config_service import config_service

from .ocr_service import get_ocr_service
from .translation_service import get_translation_service
from ..core.api_manager import init_api_manager
from .clipboard_service import get_clipboard_service


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

        # Hotkey callbacks
        self.on_translate: Optional[Callable] = None
        self.on_quick_translate: Optional[Callable] = None
        self.on_copy_translate: Optional[Callable] = None

    def setup_services(self,
                        on_translate: Callable,
                        on_quick_translate: Callable,
                        on_copy_translate: Callable):
        logger.info("AppServices: setting up services")

        # Store hotkey callbacks for reloading
        self.on_translate = on_translate
        self.on_quick_translate = on_quick_translate
        self.on_copy_translate = on_copy_translate

        # Initialize clipboard service singleton
        if self.clipboard_service is None:
            try:
                self.clipboard_service = get_clipboard_service()
                if self.clipboard_service:
                    logger.info("AppServices: ClipboardService initialized and started")
                else:
                    logger.warning("AppServices: ClipboardService not available; clipboard-backed features may be limited")
            except Exception as e:
                logger.warning(f"AppServices: Failed to initialize ClipboardService: {e}")
                self.clipboard_service = None

        # UI service
        try:
            self.ui_service = UIService(app=self.app, clipboard_service=self.clipboard_service)
            # Set global UI service instance for access from UI components
            from .ui_service import set_ui_service
            set_ui_service(self.ui_service)
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
        
        # Apply initial 'show_notifications' setting
        try:
            show = bool(config_service.get_setting("show_notifications", use_cache=False))
            if show:
                self.notification_service.enable()
            else:
                self.notification_service.disable()
            logger.debug(f"AppServices: NotificationService initial state &#45;> {'enabled' if show else 'disabled'}")
        except Exception as e:
            logger.debug(f"AppServices: Failed to apply show_notifications setting: {e}")
        
        # Keyboard / hotkeys
        self.keyboard_manager = KeyboardManager()
        try:
            self.hotkey_service = HotkeyService(self.keyboard_manager)
        except Exception as e:
            logger.warning(f"AppServices: Hotkey service not available: {e}")
            self.hotkey_service = None

        # Copy-translate service
        self.copy_translate_service = CopyTranslateService(
            tray_manager=(self.ui_service.tray_manager if self.ui_service else None),
            clipboard_service=self.clipboard_service,
            hotkey_service=self.hotkey_service
        )
        try:
            self.copy_translate_service.result_ready.connect(self.on_copy_translate_result)
        except Exception:
            logger.debug("AppServices: Failed to connect copy_translate result signal")

        if self.hotkey_service:
            try:
                self.hotkey_service.register_application_hotkeys(
                    config_service=config_service,
                    on_translate=on_translate,
                    on_quick_translate=on_quick_translate,
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

        # Translation service
        self.initialize_translation_service()

        logger.info("AppServices: services setup completed")

    def initialize_ocr_async(self):
        """Deprecated: OCR service (LLM) does not require initialization."""
        pass

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

    def reload_hotkeys(self):
        """Reload hotkeys after settings change."""
        if not self.keyboard_manager or not self.hotkey_service:
            logger.warning("AppServices: Cannot reload hotkeys - services not available")
            return

        try:
            self.keyboard_manager.clear_all_hotkeys()
            self.hotkey_service.register_application_hotkeys(
                config_service=config_service,
                on_translate=self.on_translate,
                on_quick_translate=self.on_quick_translate,
                on_copy_translate=self.on_copy_translate
            )

            if not self.hotkey_service.is_running():
                logger.warning("AppServices: Hotkey service not running")
                return

            success = self.hotkey_service.reload_hotkeys()
            if success:
                logger.info("AppServices: Hotkeys reloaded successfully")
            else:
                logger.error("AppServices: Failed to reload hotkeys")

        except Exception as e:
            logger.error(f"AppServices: Error reloading hotkeys: {e}", exc_info=True)

    @Slot(str, str, bool)
    def on_copy_translate_result(self, clipboard_text: str, translated_text: str, auto_copy: bool):
        """Slot to handle copy-translate results from background thread."""
        if self.ui_service:
            self.ui_service.handle_copy_translate(clipboard_text, translated_text, auto_copy)