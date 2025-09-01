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
            logger.info(f"=== CREATE OVERLAY REQUEST: '{overlay_id}' ===")
            
            # Log thread information for debugging
            thread_info = {
                "thread_id": threading.get_ident(),
                "thread_name": threading.current_thread().name,
                "is_main_thread": threading.current_thread() is threading.main_thread()
            }
            logger.info(f"Creating overlay in thread: {thread_info}")
            
            # Check if Tkinter is in mainloop by attempting a harmless operation
            in_mainloop = True
            try:
                self.root.winfo_exists()  # Will raise if not in mainloop
            except RuntimeError as e:
                if "main thread is not in main loop" in str(e):
                    in_mainloop = False
                    logger.error("WARNING: Tkinter not in mainloop during overlay creation!")
            
            logger.info(f"Tkinter mainloop active: {in_mainloop}")
            
            # Check root window state
            logger.info(f"Root window state:")
            try:
                logger.info(f"  - Root exists: {self.root.winfo_exists()}")
                logger.info(f"  - Root is mapped: {self.root.winfo_ismapped()}")
                logger.info(f"  - Root is viewable: {self.root.winfo_viewable()}")
            except Exception as e:
                logger.error(f"Error checking root window state: {e}")

            # Return existing overlay if it already exists
            if overlay_id in self.overlays:
                logger.info(f"Overlay '{overlay_id}' exists. Returning existing instance.")
                instance = self.overlays[overlay_id]
                
                # Check if the window still exists (might have been destroyed)
                if instance.window.winfo_exists():
                    logger.debug(f"Existing overlay window is valid.")
                    instance.update_last_shown()
                    return instance.window
                else:
                    logger.warning(f"Existing overlay window for '{overlay_id}' is invalid! Recreating.")
                    # Continue to recreate the window
            else:
                logger.info(f"Creating new overlay '{overlay_id}'.")
                
            # Clean up old overlays if needed
            if len(self.overlays) >= self.max_overlays:
                logger.info(f"Max overlays ({self.max_overlays}) reached, cleaning up old overlays")
                self._cleanup_old_overlays()

            # Define close callback
            def close_callback_wrapper():
                logger.info(f"Close callback triggered for overlay '{overlay_id}'.")
                self._on_overlay_closed(overlay_id)
                if on_close_callback:
                    on_close_callback()

            # Create the overlay window
            try:
                # Log creation parameters
                logger.debug(f"Creating overlay with parameters: timeout={timeout or self.overlay_timeout}s")
                
                # Create the window
                overlay_window = OverlayWindow(
                    self.root,
                    timeout=(timeout or self.overlay_timeout),
                    on_close_callback=close_callback_wrapper
                )
                
                # Verify window creation
                if overlay_window.winfo_exists():
                    logger.info(f"OverlayWindow for '{overlay_id}' instantiated successfully.")
                    logger.debug(f"New overlay window: exists={overlay_window.winfo_exists()}, mapped={overlay_window.winfo_ismapped()}")
                else:
                    logger.error(f"OverlayWindow for '{overlay_id}' created but does not exist!")
                    return None
                    
            except Exception as e:
                logger.error(f"Failed to instantiate OverlayWindow for '{overlay_id}': {e}", exc_info=True)
                return None

            # Create overlay instance and store it
            instance = OverlayInstance(overlay_window, overlay_id)
            self.overlays[overlay_id] = instance
            logger.info(f"Overlay '{overlay_id}' created and stored in service dictionary.")
            
            # Final verification
            try:
                geometry = overlay_window.geometry()
                state = overlay_window.state()
                is_mapped = overlay_window.winfo_ismapped()
                logger.info(f"New overlay verification: geometry={geometry}, state={state}, mapped={is_mapped}")
            except Exception as e:
                logger.warning(f"Error during final overlay verification: {e}")
                
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
            logger.info(f"=== REQUEST TO SHOW OVERLAY '{overlay_id}' ===")
            logger.debug(f"Position: {position}, show_loading_first: {show_loading_first}")
            logger.debug(f"Text lengths: original={len(original_text)}, translated={len(translated_text)}")
            
            # Get the current thread information
            thread_info = {
                "thread_id": threading.get_ident(),
                "thread_name": threading.current_thread().name,
                "is_main_thread": threading.current_thread() is threading.main_thread()
            }
            logger.info(f"Executing in thread: {thread_info}")

            # Get or create the overlay instance
            logger.info(f"Attempting to create/get overlay '{overlay_id}'...")
            overlay = self.create_overlay(overlay_id)
            if not overlay:
                logger.error(f"Failed to create or get overlay '{overlay_id}'. Cannot show.")
                return False

            instance = self.overlays.get(overlay_id)
            if not instance:
                 logger.error(f"Overlay instance for '{overlay_id}' disappeared after creation.")
                 return False

            logger.info(f"Preparing to show overlay '{overlay_id}'.")
            
            # Log the overlay window state before showing
            try:
                if overlay.winfo_exists():
                    logger.info(f"Overlay Window State (pre-show):")
                    logger.info(f"  - Exists: {overlay.winfo_exists()}")
                    logger.info(f"  - Is mapped: {overlay.winfo_ismapped()}")
                    logger.info(f"  - Is viewable: {overlay.winfo_viewable()}")
                    logger.info(f"  - Current geometry: {overlay.geometry()}")
                    logger.info(f"  - Alpha: {overlay.attributes('-alpha')}")
                    logger.info(f"  - State: {overlay.state()}")
                else:
                    logger.warning(f"Overlay window does not exist before showing")
            except Exception as e:
                logger.error(f"Error checking overlay window state: {e}")

            try:
                # Calculate adaptive size and smart position
                total_text_length = len(original_text) + len(translated_text)
                logger.info(f"Calculating adaptive size for total text length: {total_text_length}")
                adaptive_size = calculate_adaptive_size(total_text_length)
                logger.info(f"Adaptive size for '{overlay_id}': {adaptive_size}")

                # Get screen bounds
                screen_bounds = get_screen_bounds(self.root)
                logger.debug(f"Screen bounds: width={screen_bounds.width}, height={screen_bounds.height}")
                
                # Calculate position
                default_position = (screen_bounds.width // 2, screen_bounds.height // 2)
                requested_position = position or default_position
                logger.info(f"Calculating smart position: requested={requested_position}, default={default_position}")
                
                final_position = calculate_smart_position(
                    requested_position,
                    adaptive_size,
                    screen_bounds
                )
                logger.info(f"Smart position for '{overlay_id}': {final_position.as_tuple()}")

                # Set geometry before showing
                geometry_str = f"{adaptive_size[0]}x{adaptive_size[1]}+{final_position.x}+{final_position.y}"
                logger.info(f"Setting geometry: {geometry_str}")
                overlay.geometry(geometry_str)
                
                # Verify geometry was set correctly
                actual_geometry = overlay.geometry()
                logger.info(f"Actual geometry after setting: {actual_geometry}")
                
                # Force window to update geometry before showing
                try:
                    overlay.update_idletasks()
                    logger.debug("Called update_idletasks() to ensure geometry is applied")
                except Exception as e:
                    logger.warning(f"Error in update_idletasks: {e}")

                # Show the overlay
                if show_loading_first:
                    logger.info(f"Showing loading state for '{overlay_id}'.")
                    overlay.show_loading(final_position.as_tuple())
                else:
                    logger.info(f"Showing result for '{overlay_id}'.")
                    overlay.show_result(
                        original_text,
                        translated_text,
                        final_position.as_tuple(),
                        adaptive_size
                    )

                # Update instance metadata
                instance.update_last_shown()
                instance.is_visible = True
                logger.info(f"Overlay '{overlay_id}' is now marked as visible.")
                
                # Verify window state after showing
                try:
                    if overlay.winfo_exists():
                        logger.info(f"Overlay Window State (post-show):")
                        logger.info(f"  - Exists: {overlay.winfo_exists()}")
                        logger.info(f"  - Is mapped: {overlay.winfo_ismapped()}")
                        logger.info(f"  - Is viewable: {overlay.winfo_viewable()}")
                        logger.info(f"  - Current geometry: {overlay.geometry()}")
                        logger.info(f"  - Alpha: {overlay.attributes('-alpha')}")
                        logger.info(f"  - State: {overlay.state()}")
                        logger.info(f"  - Topmost: {overlay.attributes('-topmost')}")
                    else:
                        logger.warning(f"Overlay window does not exist after showing!")
                except Exception as e:
                    logger.error(f"Error checking overlay window state after showing: {e}")
                
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