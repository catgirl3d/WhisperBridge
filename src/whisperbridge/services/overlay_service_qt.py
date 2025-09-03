"""
Qt-native overlay service for managing overlay windows lifecycle.

This mirrors the public API of the legacy Tk-based overlay service but uses
Qt widgets and avoids any tkinter/customtkinter imports.
"""
from typing import Optional, Dict, List, Callable, Tuple, Any
import threading
import time
from loguru import logger
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt, QObject, QMetaObject, Slot
from PySide6.QtGui import QCursor

# Lazy import of default overlay window to avoid import cycles during module import
DEFAULT_OVERLAY_MODULE = "..ui_qt.overlay_window"
DEFAULT_OVERLAY_CLASS = "OverlayWindow"


class OverlayInstance:
    """Represents a Qt overlay window instance."""

    def __init__(self, window: Any, overlay_id: str):
        self.window = window
        self.overlay_id = overlay_id
        self.created_at = time.time()
        self.last_shown = time.time()
        self.is_visible = False

    def update_last_shown(self):
        self.last_shown = time.time()

    def get_age(self) -> float:
        return time.time() - self.created_at

    def get_time_since_shown(self) -> float:
        return time.time() - self.last_shown


class OverlayServiceQt:
    """Qt-native overlay service."""

    def __init__(self, root: QApplication):
        self.root = root
        self.overlays: Dict[str, OverlayInstance] = {}
        self.lock = threading.RLock()

        # Configuration defaults (can be updated later)
        self.max_overlays = 5
        self.overlay_timeout = 10
        self.max_overlay_age = 300

        logger.info("OverlayServiceQt initialized")

    def start(self):
        """Start service (no background thread required for now)."""
        logger.debug("OverlayServiceQt start() called (no-op)")

    def stop(self):
        """Stop service and close overlays."""
        with self.lock:
            # Cancel pending callbacks on overlays
            for overlay_id, instance in list(self.overlays.items()):
                try:
                    if instance.window and hasattr(instance.window, "_cancel_pending_callbacks"):
                        instance.window._cancel_pending_callbacks()
                except Exception as e:
                    logger.warning(f"Failed to cancel callbacks for overlay {overlay_id}: {e}")
            # Close overlays
            for overlay_id in list(self.overlays.keys()):
                self._close_overlay(overlay_id)
            self.overlays.clear()
            logger.info("OverlayServiceQt stopped and overlays cleared")

    def _resolve_default_class(self):
        # Lazy import the default overlay class
        try:
            mod = __import__(DEFAULT_OVERLAY_MODULE, fromlist=[DEFAULT_OVERLAY_CLASS])
            return getattr(mod, DEFAULT_OVERLAY_CLASS)
        except Exception as e:
            logger.error(f"Failed to import default overlay class: {e}")
            raise

    def create_overlay(
        self,
        overlay_id: str,
        timeout: Optional[int] = None,
        on_close_callback: Optional[Callable] = None,
        overlay_window_class: Optional[type] = None
    ) -> Optional[Any]:
        """Create or return an existing overlay window (Qt)."""
        with self.lock:
            logger.info(f"Creating/getting overlay '{overlay_id}' (Qt)")
            # Return existing overlay if valid
            if overlay_id in self.overlays:
                instance = self.overlays[overlay_id]
                # Basic validity check: widget exists and not destroyed
                try:
                    if instance.window and (not getattr(instance.window, "is_destroyed", False)):
                        instance.update_last_shown()
                        logger.debug(f"Returning existing overlay '{overlay_id}'")
                        return instance.window
                except Exception:
                    logger.warning(f"Existing overlay '{overlay_id}' invalid; recreating")

            # Enforce max overlays
            if len(self.overlays) >= self.max_overlays:
                logger.info(f"Max overlays reached ({self.max_overlays}), cleaning up oldest")
                self._cleanup_old_overlays()

            # Prepare close callback wrapper
            def close_callback_wrapper():
                logger.info(f"Overlay {overlay_id} close callback wrapper triggered")
                try:
                    self._on_overlay_closed(overlay_id)
                except Exception as e:
                    logger.warning(f"Error in close callback wrapper: {e}")
                if on_close_callback:
                    try:
                        on_close_callback()
                    except Exception as e:
                        logger.warning(f"User on_close_callback raised: {e}")

            # Determine overlay class
            overlay_cls = overlay_window_class or self._resolve_default_class()

            try:
                # Instantiate overlay (assume constructor without root is acceptable)
                overlay_window = overlay_cls()
            except Exception as e:
                logger.error(f"Failed to instantiate overlay window class for '{overlay_id}': {e}")
                return None

            # Attach close callback if widget supports it; otherwise user of overlay should call service methods
            # Store instance
            instance = OverlayInstance(overlay_window, overlay_id)
            self.overlays[overlay_id] = instance
            logger.info(f"Overlay '{overlay_id}' created (Qt) and stored")
            return overlay_window

    def show_overlay(
        self,
        overlay_id: str,
        original_text: str,
        translated_text: str,
        position: Optional[Tuple[int, int]] = None,
        show_loading_first: bool = False
    ) -> bool:
        """Show overlay with content. Must be called from Qt main thread or will invoke via QMetaObject."""
        try:
            overlay = self.create_overlay(overlay_id)
            if not overlay:
                logger.error(f"Cannot show overlay '{overlay_id}' because creation failed")
                return False

            # Ensure we run widget operations on the main Qt thread
            def _show():
                try:
                    # Positioning: if position given, move widget center to that pos
                    if position:
                        try:
                            x, y = position
                            # Move to position (top-left)
                            overlay.move(x, y)
                        except Exception:
                            logger.debug("Failed to move overlay to given position")
                    if show_loading_first and hasattr(overlay, "show_loading"):
                        overlay.show_loading(position)
                    else:
                        # Prefer show_result if available; fallback to show_overlay
                        if hasattr(overlay, "show_result"):
                            overlay.show_result(original_text, translated_text)
                        else:
                            overlay.show_overlay(original_text, translated_text, position)
                    overlay.show()
                    overlay.raise_()
                    overlay.activateWindow()
                    logger.info(f"Overlay '{overlay_id}' shown")
                    # Update metadata
                    with self.lock:
                        inst = self.overlays.get(overlay_id)
                        if inst:
                            inst.update_last_shown()
                            inst.is_visible = True
                    return True
                except Exception as e:
                    logger.error(f"Error while showing overlay '{overlay_id}': {e}")
                    return False

            if QMetaObject.invokeMethod:
                # Ensure execution on main thread
                success = QMetaObject.invokeMethod(
                    QApplication.instance(),
                    lambda: _show(),
                    Qt.ConnectionType.BlockingQueuedConnection
                )
                # invokeMethod returns bool about invocation; actual return value likely lost, but assume success
                return True
            else:
                # Fallback direct call (if already in main thread)
                return _show()
        except Exception as e:
            logger.error(f"Exception in show_overlay: {e}")
            return False

    def show_loading_overlay(self, overlay_id: str, position: Optional[Tuple[int, int]] = None) -> bool:
        with self.lock:
            if overlay_id not in self.overlays:
                return False
            overlay = self.overlays[overlay_id].window
            try:
                if hasattr(overlay, "show_loading"):
                    overlay.show_loading(position)
                else:
                    # Fallback: set placeholder text and show
                    if hasattr(overlay, "original_text"):
                        overlay.original_text.setPlainText("Loading...")
                    overlay.show()
                self.overlays[overlay_id].update_last_shown()
                self.overlays[overlay_id].is_visible = True
                return True
            except Exception as e:
                logger.error(f"Failed to show loading overlay '{overlay_id}': {e}")
                return False

    def hide_overlay(self, overlay_id: str) -> bool:
        with self.lock:
            if overlay_id not in self.overlays:
                return False
            try:
                overlay = self.overlays[overlay_id].window
                if hasattr(overlay, "_close_window"):
                    overlay._close_window()
                else:
                    overlay.hide()
                    try:
                        overlay.is_destroyed = True
                    except Exception:
                        pass
                self.overlays[overlay_id].is_visible = False
                return True
            except Exception as e:
                logger.error(f"Failed to hide overlay '{overlay_id}': {e}")
                return False

    def close_overlay(self, overlay_id: str) -> bool:
        with self.lock:
            if overlay_id not in self.overlays:
                return False
            try:
                self._close_overlay(overlay_id)
                del self.overlays[overlay_id]
                return True
            except Exception as e:
                logger.error(f"Failed to close overlay '{overlay_id}': {e}")
                return False

    def get_overlay(self, overlay_id: str) -> Optional[Any]:
        with self.lock:
            if overlay_id in self.overlays:
                return self.overlays[overlay_id].window
            return None

    def get_active_overlays(self) -> List[str]:
        with self.lock:
            return [overlay_id for overlay_id, inst in self.overlays.items() if inst.is_visible]

    def update_timeout(self, overlay_id: str, timeout: int):
        with self.lock:
            if overlay_id in self.overlays:
                try:
                    setattr(self.overlays[overlay_id].window, "timeout", timeout)
                except Exception as e:
                    logger.debug(f"Failed to update timeout on overlay '{overlay_id}': {e}")

    def _close_overlay(self, overlay_id: str):
        with self.lock:
            if overlay_id in self.overlays:
                overlay = self.overlays[overlay_id].window
                try:
                    if hasattr(overlay, "_close_window"):
                        overlay._close_window()
                    else:
                        overlay.close()
                        overlay.is_destroyed = True
                except Exception as e:
                    logger.warning(f"Error closing overlay '{overlay_id}': {e}")

    def _on_overlay_closed(self, overlay_id: str):
        with self.lock:
            if overlay_id in self.overlays:
                self.overlays[overlay_id].is_visible = False

    def _cleanup_old_overlays(self):
        with self.lock:
            if len(self.overlays) <= self.max_overlays:
                return
            # Sort by last_shown ascending (oldest first)
            sorted_items = sorted(self.overlays.items(), key=lambda x: x[1].last_shown)
            for overlay_id, _ in sorted_items[: max(0, len(self.overlays) - self.max_overlays)]:
                self._close_overlay(overlay_id)
                try:
                    del self.overlays[overlay_id]
                except KeyError:
                    pass


# Global service instance
_overlay_service_qt: Optional[OverlayServiceQt] = None


def get_overlay_service() -> OverlayServiceQt:
    global _overlay_service_qt
    if _overlay_service_qt is None:
        raise RuntimeError("Qt Overlay service not initialized. Call init_overlay_service() first.")
    return _overlay_service_qt


def init_overlay_service(root: Optional[QApplication] = None) -> OverlayServiceQt:
    """Initialize and return the global Qt overlay service.

    Args:
        root: QApplication instance (optional). If not provided, will use QApplication.instance().
    """
    global _overlay_service_qt
    if _overlay_service_qt is None:
        if root is None:
            root = QApplication.instance()
        if root is None:
            raise RuntimeError("No QApplication instance available to initialize overlay service.")
        _overlay_service_qt = OverlayServiceQt(root)
        _overlay_service_qt.start()
    return _overlay_service_qt