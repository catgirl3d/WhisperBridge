"""
Overlay service for managing overlay windows lifecycle.

This module provides a service for creating, managing, and coordinating
multiple overlay windows with proper lifecycle management.
"""

import threading
import time
from typing import Optional, Dict, List, Callable, Tuple
import customtkinter as ctk
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
        print(f"=== CREATE_OVERLAY STARTED: {overlay_id} ===")
        with self.lock:
            print(f"Checking if overlay {overlay_id} already exists...")
            # Check if overlay already exists
            if overlay_id in self.overlays:
                print(f"Overlay {overlay_id} already exists, returning existing")
                existing = self.overlays[overlay_id]
                existing.update_last_shown()
                return existing.window

            print(f"Creating new overlay {overlay_id}")
            # Create new overlay
            timeout = timeout or self.overlay_timeout
            print(f"Using timeout: {timeout}")

            def close_callback():
                print(f"Close callback called for overlay {overlay_id}")
                self._on_overlay_closed(overlay_id)
                if on_close_callback:
                    on_close_callback()

            print("Creating OverlayWindow...")
            try:
                overlay = OverlayWindow(
                    parent=self.root,
                    timeout=timeout,
                    on_close_callback=close_callback
                )
                print(f"OverlayWindow created: {overlay}")
                print(f"OverlayWindow type: {type(overlay)}")
            except Exception as e:
                print(f"ERROR creating OverlayWindow: {e}")
                import traceback
                traceback.print_exc()
                raise

            print("Creating OverlayInstance...")
            instance = OverlayInstance(overlay, overlay_id)
            self.overlays[overlay_id] = instance
            print(f"Overlay stored with ID: {overlay_id}")

            # Cleanup old overlays if limit exceeded
            self._cleanup_old_overlays()
            print(f"Overlay {overlay_id} creation completed")

            return overlay

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
            if overlay_id not in self.overlays:
                return False

            overlay = self.overlays[overlay_id].window
            instance = self.overlays[overlay_id]

            # Calculate adaptive size
            total_text_length = len(original_text) + len(translated_text)
            adaptive_size = calculate_adaptive_size(total_text_length)
            overlay.geometry(f"{adaptive_size[0]}x{adaptive_size[1]}")

            # Calculate smart position if not provided
            if position is None:
                # Use center of screen as fallback
                screen_bounds = get_screen_bounds(self.root)
                position = (
                    screen_bounds.width // 2,
                    screen_bounds.height // 2
                )

            smart_position = calculate_smart_position(
                position,
                adaptive_size,
                get_screen_bounds(self.root)
            )

            if show_loading_first:
                overlay.show_loading(smart_position.as_tuple())
            else:
                overlay.show_result(
                    original_text,
                    translated_text,
                    smart_position.as_tuple()
                )

            instance.update_last_shown()
            instance.is_visible = True

            return True

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