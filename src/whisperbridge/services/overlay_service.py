"""
Overlay service for managing overlay windows lifecycle.

This module provides a service for creating, managing, and coordinating
multiple overlay windows with proper lifecycle management.
"""

import threading
import time
from typing import Optional, Dict, List, Callable, Tuple
import customtkinter as ctk
from loguru import logger
from ..ui.overlay_window import OverlayWindow
from ..utils.overlay_utils import (
    get_screen_bounds,
    calculate_smart_position,
    calculate_adaptive_size,
    ScreenBounds,
    OverlayPosition
)


class OverlayInstance:
    """Represents an overlay window instance."""

    def __init__(self, window: OverlayWindow, overlay_id: str):
        self.window = window
        self.overlay_id = overlay_id
        self.created_at = time.time()
        self.last_shown = time.time()
        self.is_visible = False

    def update_last_shown(self):
        """Update last shown timestamp."""
        self.last_shown = time.time()

    def get_age(self) -> float:
        """Get age of overlay in seconds."""
        return time.time() - self.created_at

    def get_time_since_shown(self) -> float:
        """Get time since last shown in seconds."""
        return time.time() - self.last_shown


class OverlayService:
    """Service for managing overlay windows."""

    def __init__(self, root: ctk.CTk):
        """Initialize overlay service.

        Args:
            root: Main application root window
        """
        self.root = root
        self.overlays: Dict[str, OverlayInstance] = {}
        self.lock = threading.RLock()
        self.cleanup_thread: Optional[threading.Thread] = None
        self.is_running = False

        # Configuration
        self.max_overlays = 5
        self.auto_cleanup_interval = 30  # seconds
        self.overlay_timeout = 10  # seconds
        self.max_overlay_age = 300  # 5 minutes

    def start(self):
        """Start the overlay service."""
        with self.lock:
            if self.is_running:
                return

            self.is_running = True
            self.cleanup_thread = threading.Thread(
                target=self._cleanup_worker,
                daemon=True
            )
            self.cleanup_thread.start()

    def stop(self):
        """Stop the overlay service."""
        with self.lock:
            self.is_running = False

            # Close all overlays
            for overlay_id in list(self.overlays.keys()):
                self._close_overlay(overlay_id)

            self.overlays.clear()

    def create_overlay(
        self,
        overlay_id: str,
        timeout: Optional[int] = None,
        on_close_callback: Optional[Callable] = None
    ) -> OverlayWindow:
        """Create a new overlay window.
        Args:
            overlay_id: Unique identifier for the overlay
            timeout: Auto-close timeout in seconds
            on_close_callback: Callback when overlay closes
        Returns:
            OverlayWindow: Created overlay window
        """
        with self.lock:
            logger.debug(f"Request to create/get overlay '{overlay_id}'.")

            if overlay_id in self.overlays:
                logger.debug(f"Overlay '{overlay_id}' exists. Returning instance.")
                instance = self.overlays[overlay_id]
                instance.update_last_shown()
                return instance.window

            logger.info(f"Creating new overlay '{overlay_id}'.")
            if len(self.overlays) >= self.max_overlays:
                self._cleanup_old_overlays()

            def close_callback_wrapper():
                logger.debug(f"Close callback triggered for overlay '{overlay_id}'.")
                self._on_overlay_closed(overlay_id)
                if on_close_callback:
                    on_close_callback()

            try:
                overlay_window = OverlayWindow(
                    self.root,
                    timeout=(timeout or self.overlay_timeout),
                    on_close_callback=close_callback_wrapper
                )
                logger.debug(f"OverlayWindow for '{overlay_id}' instantiated successfully.")
            except Exception as e:
                logger.error(f"Failed to instantiate OverlayWindow for '{overlay_id}': {e}", exc_info=True)
                return None

            instance = OverlayInstance(overlay_window, overlay_id)
            self.overlays[overlay_id] = instance
            logger.info(f"Overlay '{overlay_id}' created and stored.")
            return overlay_window

    def show_overlay(
        self,
        overlay_id: str,
        original_text: str,
        translated_text: str,
        position: Optional[Tuple[int, int]] = None,
        show_loading_first: bool = False
    ) -> bool:
        """Show an overlay with translation results.

        Args:
            overlay_id: Overlay identifier
            original_text: Original text to display
            translated_text: Translated text to display
            position: Position to show overlay at
            show_loading_first: Whether to show loading state first

        Returns:
            bool: True if overlay was shown successfully
        """
        with self.lock:
            logger.debug(f"Request to show overlay '{overlay_id}'.")

            # Get or create the overlay instance
            overlay = self.create_overlay(overlay_id)
            if not overlay:
                logger.error(f"Failed to create or get overlay '{overlay_id}'. Cannot show.")
                return False

            instance = self.overlays.get(overlay_id)
            if not instance:
                 logger.error(f"Overlay instance for '{overlay_id}' disappeared after creation.")
                 return False

            logger.debug(f"Preparing to show overlay '{overlay_id}'.")

            try:
                # Calculate adaptive size and smart position
                total_text_length = len(original_text) + len(translated_text)
                adaptive_size = calculate_adaptive_size(total_text_length)
                logger.debug(f"Adaptive size for '{overlay_id}': {adaptive_size}")

                screen_bounds = get_screen_bounds(self.root)
                final_position = calculate_smart_position(
                    position or (screen_bounds.width // 2, screen_bounds.height // 2),
                    adaptive_size,
                    screen_bounds
                )
                logger.debug(f"Smart position for '{overlay_id}': {final_position.as_tuple()}")

                # Set geometry before showing
                overlay.geometry(f"{adaptive_size[0]}x{adaptive_size[1]}+{final_position.x}+{final_position.y}")

                if show_loading_first:
                    logger.debug(f"Showing loading state for '{overlay_id}'.")
                    overlay.show_loading(final_position.as_tuple())
                else:
                    logger.debug(f"Showing result for '{overlay_id}'.")
                    overlay.show_result(
                        original_text,
                        translated_text,
                        final_position.as_tuple()
                    )

                instance.update_last_shown()
                instance.is_visible = True
                logger.info(f"Overlay '{overlay_id}' is now marked as visible.")
                return True

            except Exception as e:
                logger.error(f"Exception while showing overlay '{overlay_id}': {e}", exc_info=True)
                return False

    def show_loading_overlay(
        self,
        overlay_id: str,
        position: Optional[Tuple[int, int]] = None
    ) -> bool:
        """Show loading state for an overlay.

        Args:
            overlay_id: Overlay identifier
            position: Position to show overlay at

        Returns:
            bool: True if loading was shown successfully
        """
        with self.lock:
            if overlay_id not in self.overlays:
                return False

            overlay = self.overlays[overlay_id].window

            # Calculate position
            if position is None:
                screen_bounds = get_screen_bounds(self.root)
                position = (
                    screen_bounds.width // 2,
                    screen_bounds.height // 2
                )

            overlay.show_loading(position)
            self.overlays[overlay_id].update_last_shown()
            self.overlays[overlay_id].is_visible = True

            return True

    def hide_overlay(self, overlay_id: str) -> bool:
        """Hide an overlay window.

        Args:
            overlay_id: Overlay identifier

        Returns:
            bool: True if overlay was hidden successfully
        """
        with self.lock:
            if overlay_id not in self.overlays:
                return False

            overlay = self.overlays[overlay_id].window
            overlay._close_window()
            self.overlays[overlay_id].is_visible = False

            return True

    def close_overlay(self, overlay_id: str) -> bool:
        """Close and remove an overlay window.

        Args:
            overlay_id: Overlay identifier

        Returns:
            bool: True if overlay was closed successfully
        """
        with self.lock:
            if overlay_id not in self.overlays:
                return False

            self._close_overlay(overlay_id)
            del self.overlays[overlay_id]

            return True

    def get_overlay(self, overlay_id: str) -> Optional[OverlayWindow]:
        """Get overlay window by ID.

        Args:
            overlay_id: Overlay identifier

        Returns:
            Optional[OverlayWindow]: Overlay window if exists
        """
        with self.lock:
            if overlay_id in self.overlays:
                return self.overlays[overlay_id].window
            return None

    def get_active_overlays(self) -> List[str]:
        """Get list of active overlay IDs.

        Returns:
            List[str]: List of active overlay IDs
        """
        with self.lock:
            return [
                overlay_id for overlay_id, instance in self.overlays.items()
                if instance.is_visible
            ]

    def update_timeout(self, overlay_id: str, timeout: int):
        """Update timeout for an overlay.

        Args:
            overlay_id: Overlay identifier
            timeout: New timeout in seconds
        """
        with self.lock:
            if overlay_id in self.overlays:
                self.overlays[overlay_id].window.timeout = timeout

    def _close_overlay(self, overlay_id: str):
        """Internal method to close overlay."""
        if overlay_id in self.overlays:
            overlay = self.overlays[overlay_id].window
            if not overlay.is_destroyed:
                overlay._close_window()

    def _on_overlay_closed(self, overlay_id: str):
        """Handle overlay close event."""
        with self.lock:
            if overlay_id in self.overlays:
                self.overlays[overlay_id].is_visible = False

    def _cleanup_old_overlays(self):
        """Clean up old overlays to stay within limits."""
        with self.lock:
            # Remove overlays beyond the limit (keep newest)
            if len(self.overlays) > self.max_overlays:
                sorted_overlays = sorted(
                    self.overlays.items(),
                    key=lambda x: x[1].last_shown,
                    reverse=True
                )

                # Close excess overlays
                for overlay_id, _ in sorted_overlays[self.max_overlays:]:
                    self._close_overlay(overlay_id)
                    del self.overlays[overlay_id]

    def _cleanup_worker(self):
        """Background worker for cleaning up old overlays."""
        while self.is_running:
            try:
                time.sleep(self.auto_cleanup_interval)
                self._perform_cleanup()
            except Exception as e:
                print(f"Error in overlay cleanup worker: {e}")

    def _perform_cleanup(self):
        """Perform cleanup of old overlays."""
        with self.lock:
            current_time = time.time()
            to_remove = []

            for overlay_id, instance in self.overlays.items():
                # Remove overlays that are too old
                if instance.get_age() > self.max_overlay_age:
                    to_remove.append(overlay_id)
                    continue

                # Auto-hide overlays that haven't been shown recently
                if (instance.is_visible and
                    instance.get_time_since_shown() > self.overlay_timeout * 2):
                    self._close_overlay(overlay_id)
                    instance.is_visible = False

            # Remove old overlays
            for overlay_id in to_remove:
                if overlay_id in self.overlays:
                    self._close_overlay(overlay_id)
                    del self.overlays[overlay_id]


# Global service instance
_overlay_service: Optional[OverlayService] = None


def get_overlay_service() -> OverlayService:
    """Get the global overlay service instance.

    Returns:
        OverlayService: Global overlay service instance
    """
    global _overlay_service
    if _overlay_service is None:
        raise RuntimeError("Overlay service not initialized. Call init_overlay_service() first.")
    return _overlay_service


def init_overlay_service(root: ctk.CTk) -> OverlayService:
    """Initialize the global overlay service.

    Args:
        root: Main application root window

    Returns:
        OverlayService: Initialized overlay service
    """
    global _overlay_service
    if _overlay_service is None:
        _overlay_service = OverlayService(root)
        _overlay_service.start()
    return _overlay_service