"""
Paste Service for WhisperBridge.

This module provides automatic text pasting functionality using keyboard simulation.
Handles window detection, focus management, and cross-platform paste operations.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from loguru import logger

try:
    from pynput import keyboard
    from pynput.keyboard import Controller, Key

    PYNPUT_AVAILABLE = True
except ImportError:
    logger.warning("pynput not available. Paste service will not function.")
    PYNPUT_AVAILABLE = False
    keyboard = None
    Controller = None

from ..utils.window_utils import WindowUtils
from .clipboard_service import ClipboardService


class PasteError(Exception):
    """Exception raised when paste operations fail."""

    pass


class PasteService:
    """Service for automatic text pasting using keyboard simulation."""

    def __init__(self, clipboard_service: Optional[ClipboardService] = None):
        """Initialize the paste service.

        Args:
            clipboard_service: Optional clipboard service instance
        """
        if not PYNPUT_AVAILABLE:
            raise ImportError("pynput is required for paste functionality")

        self.clipboard_service = clipboard_service
        self._lock = threading.RLock()
        self._running = False
        self._keyboard_controller: Optional[Controller] = None
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="paste")
        self._platform = WindowUtils.get_platform()

        logger.info("PasteService initialized")

    def start(self) -> bool:
        """Start the paste service.

        Returns:
            bool: True if started successfully, False otherwise
        """
        with self._lock:
            if self._running:
                logger.warning("Paste service already running")
                return True

            try:
                # Initialize keyboard controller
                self._keyboard_controller = Controller()

                self._running = True
                logger.info("Paste service started successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to start paste service: {e}")
                return False

    def stop(self):
        """Stop the paste service."""
        with self._lock:
            if not self._running:
                return

            logger.info("Stopping paste service...")
            self._running = False

            # Shutdown executor
            self._executor.shutdown(wait=True)

            logger.info("Paste service stopped")

    def paste_text(self, text: str) -> bool:
        """Paste text to the active window.

        Args:
            text: Text to paste

        Returns:
            bool: True if successful, False otherwise
        """
        if not text:
            logger.warning("Cannot paste empty text")
            return False

        if not self._running:
            logger.warning("Paste service not running")
            return False

        try:
            with self._lock:
                # Get active window
                active_window = WindowUtils.get_active_window()
                if not active_window:
                    logger.warning("No active window found")
                    return False

                # Check if window likely has input fields
                if not WindowUtils.is_input_field(active_window):
                    logger.warning("Active window may not have input fields")
                    # Continue anyway, as detection is not perfect

                # Copy text to clipboard first
                if self.clipboard_service:
                    success = self.clipboard_service.copy_text(text)
                    if not success:
                        logger.error("Failed to copy text to clipboard")
                        return False
                else:
                    # Fallback: use pyperclip directly
                    try:
                        import pyperclip

                        pyperclip.copy(text)
                    except Exception as e:
                        logger.error(f"Failed to copy text to clipboard: {e}")
                        return False

                # Small delay to ensure clipboard is updated
                time.sleep(0.1)

                # Simulate paste shortcut
                self._simulate_paste_shortcut()

                logger.debug(f"Text pasted to active window: {len(text)} characters")
                return True

        except Exception as e:
            logger.error(f"Failed to paste text: {e}")
            return False

    def paste_to_active_window(self) -> bool:
        """Paste clipboard content to the active window.

        Returns:
            bool: True if successful, False otherwise
        """
        if not self._running:
            logger.warning("Paste service not running")
            return False

        try:
            with self._lock:
                # Get active window
                active_window = WindowUtils.get_active_window()
                if not active_window:
                    logger.warning("No active window found")
                    return False

                # Check if window likely has input fields
                if not WindowUtils.is_input_field(active_window):
                    logger.warning("Active window may not have input fields")

                # Simulate paste shortcut
                self._simulate_paste_shortcut()

                logger.debug("Clipboard content pasted to active window")
                return True

        except Exception as e:
            logger.error(f"Failed to paste to active window: {e}")
            return False

    def paste_to_specific_window(self, window: Any, text: Optional[str] = None) -> bool:
        """Paste text to a specific window.

        Args:
            window: Target window object
            text: Text to paste (if None, uses clipboard content)

        Returns:
            bool: True if successful, False otherwise
        """
        if not self._running:
            logger.warning("Paste service not running")
            return False

        if not window:
            logger.warning("No target window provided")
            return False

        try:
            with self._lock:
                # Focus the target window
                focus_success = WindowUtils.focus_window(window)
                if not focus_success:
                    logger.warning("Failed to focus target window")
                    return False

                # Small delay after focus
                time.sleep(0.2)

                if text:
                    # Copy text to clipboard first
                    if self.clipboard_service:
                        success = self.clipboard_service.copy_text(text)
                        if not success:
                            logger.error("Failed to copy text to clipboard")
                            return False
                    else:
                        try:
                            import pyperclip

                            pyperclip.copy(text)
                        except Exception as e:
                            logger.error(f"Failed to copy text to clipboard: {e}")
                            return False

                    # Delay for clipboard update
                    time.sleep(0.1)

                # Simulate paste shortcut
                self._simulate_paste_shortcut()

                logger.debug(f"Text pasted to specific window: {window.title}")
                return True

        except Exception as e:
            logger.error(f"Failed to paste to specific window: {e}")
            return False

    def _simulate_paste_shortcut(self):
        """Simulate the paste keyboard shortcut for current platform."""
        try:
            if self._platform == "darwin":
                # Cmd+V on macOS
                with self._keyboard_controller.pressed(Key.cmd):
                    self._keyboard_controller.press("v")
                    self._keyboard_controller.release("v")
            else:
                # Ctrl+V on Windows/Linux
                with self._keyboard_controller.pressed(Key.ctrl):
                    self._keyboard_controller.press("v")
                    self._keyboard_controller.release("v")

            # Small delay after paste
            time.sleep(0.1)

        except Exception as e:
            logger.error(f"Failed to simulate paste shortcut: {e}")
            raise PasteError(f"Paste simulation failed: {e}")

    def set_clipboard_service(self, clipboard_service: ClipboardService):
        """Set the clipboard service instance.

        Args:
            clipboard_service: Clipboard service instance
        """
        with self._lock:
            self.clipboard_service = clipboard_service
            logger.debug("Clipboard service set")

    def is_running(self) -> bool:
        """Check if the paste service is running.

        Returns:
            bool: True if running, False otherwise
        """
        return self._running

    def get_service_status(self) -> Dict[str, Any]:
        """Get detailed status of the paste service.

        Returns:
            Dict[str, Any]: Service status information
        """
        with self._lock:
            return {
                "running": self._running,
                "platform": self._platform,
                "pynput_available": PYNPUT_AVAILABLE,
                "clipboard_service_available": self.clipboard_service is not None,
            }

    def get_active_window_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the currently active window.

        Returns:
            Optional[Dict[str, Any]]: Active window information or None
        """
        active_window = WindowUtils.get_active_window()
        if active_window:
            return WindowUtils.get_window_info(active_window)
        return None
