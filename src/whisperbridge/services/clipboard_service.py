"""
Clipboard Service for WhisperBridge.

Provides simple clipboard access functionality using pyperclip.
"""

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

    def copy_text(self, text: str) -> bool:
        """Copy text to clipboard.

        Args:
            text: Text to copy

        Returns:
            bool: True if successful, False otherwise
        """
        if text is None or not isinstance(text, str):
            logger.warning("Cannot copy invalid or non-string text")
            return False

        try:
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
            content = pyperclip.paste()
            return content if content is not None else ""
        except Exception as e:
            logger.warning(f"Failed to access clipboard: {e}")
            return None

    def start(self) -> bool:
        """Compatibility no-op start."""
        return True

    def shutdown(self) -> None:
        """Compatibility no-op shutdown."""
        pass


# Singleton accessor for ClipboardService
_clipboard_service_instance: Optional[ClipboardService] = None


def get_clipboard_service() -> Optional[ClipboardService]:
    """Return a singleton ClipboardService instance or None if unavailable."""
    global _clipboard_service_instance
    if _clipboard_service_instance is not None:
        return _clipboard_service_instance

    if not PYPERCLIP_AVAILABLE:
        logger.warning("ClipboardService unavailable (pyperclip not installed)")
        return None

    try:
        _clipboard_service_instance = ClipboardService()
        logger.info("ClipboardService singleton created")
        return _clipboard_service_instance
    except Exception as e:
        logger.error(f"Failed to create ClipboardService singleton: {e}")
        return None
