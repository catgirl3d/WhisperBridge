"""
Clipboard Service for WhisperBridge.

This module provides clipboard management functionality using pyperclip.
Handles text copying, reading, and cross-platform support.
"""

import threading
from typing import Optional

from loguru import logger

try:
    import pyperclip

    PYPERCLIP_AVAILABLE = True
except ImportError:
    logger.warning("pyperclip not available. Clipboard service will not function.")
    PYPERCLIP_AVAILABLE = False
    pyperclip = None


class ClipboardService:
    """Service for managing clipboard operations using pyperclip."""

    def __init__(self):
        """Initialize the clipboard service."""
        if not PYPERCLIP_AVAILABLE:
            raise ImportError("pyperclip is required for clipboard functionality")

        self._lock = threading.RLock()
        self._running = False
        self._shutdown_event = threading.Event()

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
                self._running = True
                logger.info("Clipboard service started successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to start clipboard service: {e}")
                return False

    def shutdown(self):
        """Shutdown the clipboard service."""
        with self._lock:
            if not self._running:
                return

            logger.info("Shutting down clipboard service...")
            self._running = False
            self._shutdown_event.set()

            logger.info("Clipboard service shut down")

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


    def __del__(self):
        """Destructor to ensure cleanup."""
        self.shutdown()


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
