"""
Hotkey Service for WhisperBridge.

This module provides global hotkey registration and management using pynput.
Handles background keyboard monitoring, hotkey activation, and system integration.
"""

import threading
from typing import Any, Callable, Dict, List, Optional

from loguru import logger
from PySide6.QtCore import QThreadPool, QRunnable, Signal, QObject

try:
    from pynput import keyboard

    PYNPUT_AVAILABLE = True
except ImportError:
    logger.warning("pynput not available. Hotkey service will not function.")
    PYNPUT_AVAILABLE = False
    keyboard = None

from ..core.keyboard_manager import KeyboardManager
from ..utils.keyboard_utils import KeyboardUtils


class HotkeyRunnable(QRunnable):
    """QRunnable for executing hotkey handlers in QThreadPool."""

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        self.func(*self.args, **self.kwargs)


class HotkeyRegistrationError(Exception):
    """Exception raised when hotkey registration fails."""

    pass


class HotkeyService:
    """Service for managing global hotkeys using pynput."""

    def __init__(self, keyboard_manager: Optional[KeyboardManager] = None):
        """Initialize the hotkey service.

        Args:
            keyboard_manager: Optional keyboard manager instance
        """
        if not PYNPUT_AVAILABLE:
            raise ImportError("pynput is required for hotkey functionality")

        self.keyboard_manager = keyboard_manager or KeyboardManager()
        self._lock = threading.RLock()
        self._running = False
        self._listener: Optional[keyboard.GlobalHotKeys] = None
        self._hotkeys: Dict[str, Callable] = {}
        self._executor = QThreadPool()
        self._executor.setMaxThreadCount(4)
        self._shutdown_event = threading.Event()

        # Platform-specific setup
        self._platform = KeyboardUtils.get_platform()
        self._setup_platform_specifics()

        logger.info("HotkeyService initialized")

    def _setup_platform_specifics(self):
        """Setup platform-specific configurations."""
        if self._platform == "windows":
            # Windows-specific settings
            pass
        elif self._platform == "linux":
            # Linux-specific settings (may need X11 or Wayland handling)
            pass
        elif self._platform == "darwin":
            # macOS-specific settings
            pass

    def start(self) -> bool:
        """Start the hotkey service.

        Returns:
            bool: True if started successfully, False otherwise
        """
        with self._lock:
            if self._running:
                logger.warning("Hotkey service already running")
                return True

            try:
                # Register all enabled hotkeys
                self._register_all_hotkeys()

                # Start the keyboard listener only if there are hotkeys
                if self._hotkeys:
                    self._listener = keyboard.GlobalHotKeys(self._hotkeys)
                    self._listener.start()
                    self._running = True
                    logger.info("Hotkey service started successfully")
                    return True
                else:
                    logger.warning("No valid hotkeys to register")
                    return False

            except Exception as e:
                logger.error(f"Failed to start hotkey service: {e}")
                self._cleanup()
                return False

    def stop(self):
        """Stop the hotkey service."""
        with self._lock:
            if not self._running:
                return

            logger.info("Stopping hotkey service...")
            self._running = False
            self._shutdown_event.set()

            # Stop the listener
            if self._listener:
                self._listener.stop()
                self._listener = None

            self._hotkeys.clear()

            # QThreadPool will be cleaned up automatically

            logger.info("Hotkey service stopped")

    def register_application_hotkeys(self, config_service, on_translate, on_quick_translate, on_activate, on_copy_translate):
        """Register default application hotkeys based on configuration.

        Args:
            config_service: The configuration service instance
            on_translate: Callback for translate hotkey
            on_quick_translate: Callback for quick translate hotkey
            on_activate: Callback for activation hotkey
            on_copy_translate: Callback for copy-translate hotkey
        """
        if not self.keyboard_manager:
            return

        try:
            # Get current settings for hotkeys
            current_settings = config_service.get_settings()

            # Check whether OCR features should be enabled
            initialize_ocr = bool(getattr(current_settings, "initialize_ocr", False))
            ocr_build_enabled = getattr(current_settings, 'ocr_enabled', True)

            # Register main translation hotkey only if OCR is enabled at build AND runtime
            if ocr_build_enabled and initialize_ocr:
                self.keyboard_manager.register_hotkey(
                    current_settings.translate_hotkey,
                    on_translate,
                    "Main translation (OCR) hotkey",
                )
                logger.info(f"Registered OCR-dependent hotkey: {current_settings.translate_hotkey}")
            else:
                logger.info(f"OCR disabled (build: {ocr_build_enabled}, runtime: {initialize_ocr}): skipping registration of main translate hotkey")

            # Register quick translate hotkey (shows overlay translator window)
            if current_settings.quick_translate_hotkey != current_settings.translate_hotkey:
                self.keyboard_manager.register_hotkey(
                    current_settings.quick_translate_hotkey,
                    on_quick_translate,
                    "Quick translation hotkey (overlay translator)",
                )
                logger.info(f"Registered overlay translator hotkey: {current_settings.quick_translate_hotkey}")

            # Register activation hotkey if different
            if (current_settings.activation_hotkey != current_settings.translate_hotkey and
                current_settings.activation_hotkey != current_settings.quick_translate_hotkey):
                self.keyboard_manager.register_hotkey(
                    current_settings.activation_hotkey,
                    on_activate,
                    "Application activation hotkey",
                )

            # Register copy-translate hotkey
            self.keyboard_manager.register_hotkey(
                current_settings.copy_translate_hotkey,
                on_copy_translate,
                "Copy->Translate hotkey",
            )

            # Log based on flag
            translate_status = (
                current_settings.translate_hotkey if (ocr_build_enabled and initialize_ocr) else "SKIPPED"
            )
            quick_status = (
                current_settings.quick_translate_hotkey
                if current_settings.quick_translate_hotkey != current_settings.translate_hotkey
                else "SKIPPED"
            )
            logger.info(
                f"Registered hotkeys (OCR build={ocr_build_enabled}, runtime={initialize_ocr}): "
                f"translate={translate_status}, quick={quick_status}, "
                f"activation={current_settings.activation_hotkey}, "
                f"copy_translate={current_settings.copy_translate_hotkey}"
            )

        except Exception as e:
            logger.error(f"Failed to register default hotkeys: {e}")

    def _register_all_hotkeys(self):
        """Register all enabled hotkeys from the keyboard manager."""
        enabled_hotkeys = self.keyboard_manager.get_enabled_hotkeys()

        for combination in enabled_hotkeys:
            try:
                self._register_single_hotkey(combination)
            except Exception as e:
                logger.error(f"Failed to register hotkey '{combination}': {e}")

    def _register_single_hotkey(self, combination: str):
        """Register a single hotkey.

        Args:
            combination: Hotkey combination to register

        Raises:
            HotkeyRegistrationError: If registration fails
        """
        try:

            def on_activate():
                self._executor.start(HotkeyRunnable(self._handle_hotkey_press, combination))

            # Format for GlobalHotKeys
            normalized_hotkey = KeyboardUtils.normalize_hotkey(combination)
            if normalized_hotkey:
                pynput_hotkey = KeyboardUtils.format_hotkey_for_pynput(normalized_hotkey)
                if pynput_hotkey:
                    self._hotkeys[pynput_hotkey] = on_activate
                    logger.debug(f"Registered hotkey: {combination} as {pynput_hotkey}")
                else:
                    logger.warning(
                        f"Skipping invalid hotkey combination: '{combination}'"
                    )
            else:
                logger.warning(
                    f"Skipping invalid or empty hotkey combination: '{combination}'"
                )

        except Exception as e:
            raise HotkeyRegistrationError(f"Failed to register '{combination}': {e}") from e


    def _handle_hotkey_press(self, combination: str):
        """Handle a hotkey press event.

        Args:
            combination: The hotkey combination that was pressed
        """
        try:
            logger.debug(f"Hotkey pressed: {combination}")

            # Notify keyboard manager
            self.keyboard_manager._on_hotkey_pressed_internal(combination)

        except Exception as e:
            logger.error(f"Error handling hotkey press '{combination}': {e}")

    def reload_hotkeys(self) -> bool:
        """Reload all hotkeys (useful when settings change).

        Returns:
            bool: True if reload successful, False otherwise
        """
        with self._lock:
            if not self._running:
                logger.warning("Cannot reload hotkeys: service not running")
                return False

            try:
                # Stop the current listener
                if self._listener:
                    self._listener.stop()

                # Clear old hotkeys and register new ones
                self._hotkeys.clear()
                self._register_all_hotkeys()

                # Start a new listener
                if self._hotkeys:  # Only start if there are hotkeys
                    self._listener = keyboard.GlobalHotKeys(self._hotkeys)
                    self._listener.start()
                else:
                    logger.warning("No valid hotkeys to register")

                logger.info("Hotkeys reloaded successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to reload hotkeys: {e}")
                return False

    def is_running(self) -> bool:
        """Check if the hotkey service is running.

        Returns:
            bool: True if running, False otherwise
        """
        return self._running

    def get_registered_hotkeys(self) -> List[str]:
        """Get list of currently registered hotkeys.

        Returns:
            List[str]: List of registered hotkey combinations
        """
        with self._lock:
            return list(self._hotkeys.keys())

    def _cleanup(self):
        """Clean up resources."""
        try:
            if self._listener:
                self._listener.stop()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.stop()
