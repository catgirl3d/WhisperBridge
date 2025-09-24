"""
Hotkey Service for WhisperBridge.

This module provides global hotkey registration and management using pynput.
Handles background keyboard monitoring, hotkey activation, and system integration.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

try:
    from pynput import keyboard

    PYNPUT_AVAILABLE = True
except ImportError:
    logger.warning("pynput not available. Hotkey service will not function.")
    PYNPUT_AVAILABLE = False
    keyboard = None

from ..core.keyboard_manager import KeyboardManager
from ..utils.keyboard_utils import KeyboardUtils


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
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="hotkey")
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

            # Shutdown executor
            self._executor.shutdown(wait=True)

            logger.info("Hotkey service stopped")

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
                self._executor.submit(self._handle_hotkey_press, combination)

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

    def get_service_status(self) -> Dict[str, Any]:
        """Get detailed status of the hotkey service.

        Returns:
            Dict[str, Any]: Service status information
        """
        with self._lock:
            return {
                "running": self._running,
                "platform": self._platform,
                "registered_hotkeys": len(self._hotkeys),
                "keyboard_manager_stats": self.keyboard_manager.get_hotkey_statistics(),
                "pynput_available": PYNPUT_AVAILABLE,
            }

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
