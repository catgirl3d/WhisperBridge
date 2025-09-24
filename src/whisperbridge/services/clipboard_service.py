"""
Clipboard Service for WhisperBridge.

This module provides clipboard management functionality using pyperclip.
Handles text copying, reading, monitoring clipboard changes, and cross-platform support.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from loguru import logger

try:
    import pyperclip

    PYPERCLIP_AVAILABLE = True
except ImportError:
    logger.warning("pyperclip not available. Clipboard service will not function.")
    PYPERCLIP_AVAILABLE = False
    pyperclip = None


class ClipboardError(Exception):
    """Exception raised when clipboard operations fail."""

    pass


class ClipboardService:
    """Service for managing clipboard operations using pyperclip."""

    def __init__(self):
        """Initialize the clipboard service."""
        if not PYPERCLIP_AVAILABLE:
            raise ImportError("pyperclip is required for clipboard functionality")

        self._lock = threading.RLock()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="clipboard")
        self._last_clipboard_content = ""
        self._change_callbacks: Dict[str, Callable[[str], None]] = {}
        self._monitor_interval = 0.5  # seconds

        logger.info("ClipboardService initialized")

    def start(self) -> bool:
        """Start the clipboard service.

        Returns:
            bool: True if started successfully, False otherwise
        """
        with self._lock:
            if self._running:
                logger.warning("Clipboard service already running")
                return True

            try:
                # Initialize clipboard content
                with self._lock:
                    self._last_clipboard_content = self._get_clipboard_content_safe()

                # Start monitoring thread
                self._monitor_thread = threading.Thread(
                    target=self._monitor_clipboard_changes,
                    name="clipboard-monitor",
                    daemon=True,
                )
                self._monitor_thread.start()

                self._running = True
                logger.info("Clipboard service started successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to start clipboard service: {e}")
                self._cleanup()
                return False

    def stop(self):
        """Stop the clipboard service."""
        with self._lock:
            if not self._running:
                return

            logger.info("Stopping clipboard service...")
            self._running = False
            self._shutdown_event.set()

            # Wait for monitor thread to finish
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=2.0)

            # Shutdown executor
            self._executor.shutdown(wait=True)

            logger.info("Clipboard service stopped")

    def copy_text(self, text: str) -> bool:
        """Copy text to clipboard.

        Args:
            text: Text to copy

        Returns:
            bool: True if successful, False otherwise
        """
        if not text:
            logger.warning("Cannot copy empty text")
            return False

        try:
            with self._lock:
                pyperclip.copy(text)
                self._last_clipboard_content = text
                logger.debug(f"Text copied to clipboard: {len(text)} characters")
                return True
        except Exception as e:
            logger.error(f"Failed to copy text to clipboard: {e}")
            return False

    def get_clipboard_text(self) -> Optional[str]:
        """Get text from clipboard.

        Returns:
            Optional[str]: Clipboard text or None if error
        """
        try:
            with self._lock:
                content = self._get_clipboard_content_safe()
                return content
        except Exception as e:
            logger.error(f"Failed to get clipboard text: {e}")
            return None

    def _get_clipboard_content_safe(self) -> str:
        """Safely get clipboard content with error handling.

        Returns:
            str: Clipboard content
        """
        try:
            content = pyperclip.paste()
            return content if content else ""
        except Exception as e:
            logger.warning(f"Failed to access clipboard: {e}")
            return ""

    def register_change_callback(self, name: str, callback: Callable[[str], None]):
        """Register a callback for clipboard changes.

        Args:
            name: Unique name for the callback
            callback: Function to call when clipboard changes (receives new content)
        """
        with self._lock:
            self._change_callbacks[name] = callback
            logger.debug(f"Registered clipboard change callback: {name}")

    def unregister_change_callback(self, name: str):
        """Unregister a clipboard change callback.

        Args:
            name: Name of the callback to remove
        """
        with self._lock:
            if name in self._change_callbacks:
                del self._change_callbacks[name]
                logger.debug(f"Unregistered clipboard change callback: {name}")

    def _monitor_clipboard_changes(self):
        """Monitor clipboard for changes in a separate thread."""
        logger.debug("Starting clipboard monitoring")

        while not self._shutdown_event.is_set():
            try:
                with self._lock:
                    current_content = self._get_clipboard_content_safe()

                    if current_content != self._last_clipboard_content:
                        self._last_clipboard_content = current_content
                        self._notify_change_callbacks(current_content)

                # Wait before next check
                self._shutdown_event.wait(self._monitor_interval)

            except Exception as e:
                logger.error(f"Error in clipboard monitoring: {e}")
                # Brief pause before retrying
                time.sleep(1.0)

        logger.debug("Clipboard monitoring stopped")

    def _notify_change_callbacks(self, new_content: str):
        """Notify all registered callbacks about clipboard changes.

        Args:
            new_content: New clipboard content
        """
        # Create a copy of callbacks to avoid modification during iteration
        callbacks = dict(self._change_callbacks)

        for name, callback in callbacks.items():
            try:
                self._executor.submit(callback, new_content)
            except Exception as e:
                logger.error(f"Error in clipboard change callback '{name}': {e}")

    def is_running(self) -> bool:
        """Check if the clipboard service is running.

        Returns:
            bool: True if running, False otherwise
        """
        return self._running

    def get_service_status(self) -> Dict[str, Any]:
        """Get detailed status of the clipboard service.

        Returns:
            Dict[str, Any]: Service status information
        """
        with self._lock:
            return {
                "running": self._running,
                "pyperclip_available": PYPERCLIP_AVAILABLE,
                "monitor_interval": self._monitor_interval,
                "registered_callbacks": len(self._change_callbacks),
                "last_clipboard_length": len(self._last_clipboard_content),
            }

    def _cleanup(self):
        """Clean up resources."""
        try:
            self._shutdown_event.set()
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=1.0)
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.stop()


# Singleton accessor for ClipboardService
# Provides a single started instance that can be reused across the application.
_clipboard_service_instance: Optional[ClipboardService] = None


def get_clipboard_service() -> Optional[ClipboardService]:
    """
    Return a singleton ClipboardService instance. If pyperclip is not available
    or initialization fails, returns None.
    """
    global _clipboard_service_instance
    if _clipboard_service_instance is not None:
        return _clipboard_service_instance
    try:
        svc = ClipboardService()
        try:
            started = svc.start()
        except Exception as e_start:
            logger.error(f"ClipboardService.start() raised an exception: {e_start}")
            started = False
        if not started:
            logger.warning("ClipboardService failed to start; clipboard functionality may be limited")
            return None
        _clipboard_service_instance = svc
        logger.info("ClipboardService singleton created and started")
        return _clipboard_service_instance
    except Exception as e:
        logger.error(f"Failed to create ClipboardService singleton: {e}")
        return None
