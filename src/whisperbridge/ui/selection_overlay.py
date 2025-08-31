"""
Selection overlay for screen capture in WhisperBridge.

This module provides a full-screen overlay window for selecting
rectangular areas of the screen for capture.
"""

import threading
import time
from typing import Optional, Callable, Tuple
from dataclasses import dataclass

try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except ImportError:
    CTK_AVAILABLE = False
    import tkinter as tk

from loguru import logger
from ..utils.screen_utils import ScreenUtils, Rectangle, Point


@dataclass
class SelectionResult:
    """Result of selection operation."""
    rectangle: Optional[Rectangle]
    cancelled: bool = False


class SelectionOverlay:
    """Full-screen overlay for selecting screen areas."""

    def __init__(self, on_selection_complete: Optional[Callable[[SelectionResult], None]] = None):
        """Initialize the selection overlay.

        Args:
            on_selection_complete: Callback when selection is complete
        """
        if not CTK_AVAILABLE:
            raise ImportError("CustomTkinter is required for SelectionOverlay")

        self.on_selection_complete = on_selection_complete
        self.root: Optional[ctk.CTk] = None
        self.canvas: Optional[ctk.CTkCanvas] = None

        # Selection state
        self.is_selecting = False
        self.start_point: Optional[Point] = None
        self.current_point: Optional[Point] = None
        self.selection_rect: Optional[Rectangle] = None

        # Threading
        self._lock = threading.RLock()
        self._running = False

        # Colors and styling
        self.overlay_color = "#000000"
        self.overlay_alpha = 0.3
        self.selection_color = "#007ACC"
        self.selection_border_width = 2
        self.text_color = "#FFFFFF"
        self.text_bg_color = "#333333"

        logger.info("SelectionOverlay initialized")

    def start_selection(self) -> SelectionResult:
        """Start the selection process.

        Returns:
            SelectionResult: Result of the selection
        """
        with self._lock:
            if self._running:
                logger.warning("Selection already in progress")
                return SelectionResult(None, True)

            try:
                self._running = True
                return self._run_selection()

            except Exception as e:
                logger.error(f"Selection failed: {e}")
                return SelectionResult(None, True)

            finally:
                self._running = False

    def _run_selection(self) -> SelectionResult:
        """Run the selection process."""
        try:
            # Create full-screen window
            self.root = ctk.CTk()
            self.root.attributes("-fullscreen", True)
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", self.overlay_alpha)
            self.root.configure(fg_color=self.overlay_color)

            # Remove window decorations
            self.root.overrideredirect(True)

            # Create canvas for drawing
            self.canvas = ctk.CTkCanvas(
                self.root,
                bg=self.overlay_color,
                highlightthickness=0
            )
            self.canvas.pack(fill="both", expand=True)

            # Bind events
            self.canvas.bind("<ButtonPress-1>", self._on_mouse_press)
            self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
            self.canvas.bind("<ButtonRelease-1>", self._on_mouse_release)
            self.root.bind("<Key>", self._on_key_press)
            self.root.bind("<Escape>", self._on_escape_key)
            self.root.focus_force()

            # Show instructions
            self._draw_instructions()

            # Start event loop
            self.root.mainloop()

            # Return result
            if self.selection_rect:
                return SelectionResult(self.selection_rect, False)
            else:
                return SelectionResult(None, True)

        except Exception as e:
            logger.error(f"Error in _run_selection: {e}")
            return SelectionResult(None, True)

    def _on_mouse_press(self, event):
        """Handle mouse press event."""
        if not self.is_selecting:
            self.is_selecting = True
            self.start_point = Point(event.x, event.y)
            self.current_point = Point(event.x, event.y)
            self._update_selection()

    def _on_mouse_drag(self, event):
        """Handle mouse drag event."""
        if self.is_selecting:
            self.current_point = Point(event.x, event.y)
            self._update_selection()

    def _on_mouse_release(self, event):
        """Handle mouse release event."""
        if self.is_selecting:
            self.is_selecting = False
            self.current_point = Point(event.x, event.y)
            self._finalize_selection()

    def _on_key_press(self, event):
        """Handle key press event."""
        if event.keysym == "Escape":
            self._cancel_selection()

    def _on_escape_key(self, event):
        """Handle Escape key press."""
        self._cancel_selection()

    def _update_selection(self):
        """Update the selection rectangle display."""
        if not self.canvas or not self.start_point or not self.current_point:
            return

        # Clear previous drawings
        self.canvas.delete("selection")
        self.canvas.delete("size_text")

        # Calculate selection rectangle
        x1, y1 = self.start_point.x, self.start_point.y
        x2, y2 = self.current_point.x, self.current_point.y

        self.selection_rect = Rectangle(
            min(x1, x2), min(y1, y2),
            abs(x2 - x1), abs(y2 - y1)
        )

        # Draw selection rectangle
        self.canvas.create_rectangle(
            self.selection_rect.x, self.selection_rect.y,
            self.selection_rect.right, self.selection_rect.bottom,
            outline=self.selection_color,
            width=self.selection_border_width,
            fill="",
            tags="selection"
        )

        # Draw size text
        if self.selection_rect.width > 50 and self.selection_rect.height > 20:
            size_text = f"{self.selection_rect.width} × {self.selection_rect.height}"
            text_x = self.selection_rect.center_x
            text_y = self.selection_rect.center_y

            # Draw text background
            self.canvas.create_rectangle(
                text_x - 40, text_y - 10,
                text_x + 40, text_y + 10,
                fill=self.text_bg_color,
                outline=self.selection_color,
                tags="size_text"
            )

            # Draw text
            self.canvas.create_text(
                text_x, text_y,
                text=size_text,
                fill=self.text_color,
                font=("Arial", 10, "bold"),
                tags="size_text"
            )

    def _finalize_selection(self):
        """Finalize the selection and close overlay."""
        if self.selection_rect and self.selection_rect.width > 0 and self.selection_rect.height > 0:
            logger.info(f"Selection completed: {self.selection_rect}")
            self._close_overlay()
        else:
            self._cancel_selection()

    def _cancel_selection(self):
        """Cancel the selection."""
        logger.info("Selection cancelled")
        self.selection_rect = None
        self._close_overlay()

    def _close_overlay(self):
        """Close the overlay window."""
        # Save the selection result before resetting state
        final_rect = self.selection_rect
        was_cancelled = final_rect is None

        if self.root:
            try:
                # Don't destroy the root window if it's the main application window
                # Just withdraw/hide the overlay
                if hasattr(self.root, 'withdraw'):
                    self.root.withdraw()
                else:
                    # If it's not the main window, we can destroy it
                    self.root.quit()
                    self.root.destroy()
            except Exception as e:
                logger.error(f"Error closing overlay: {e}")

        # Reset selection state
        self.is_selecting = False
        self.start_point = None
        self.current_point = None
        self.selection_rect = None

        # Call completion callback with saved result
        if self.on_selection_complete:
            result = SelectionResult(final_rect, was_cancelled)
            try:
                self.on_selection_complete(result)
            except Exception as e:
                logger.error(f"Error in selection complete callback: {e}")

    def _draw_instructions(self):
        """Draw selection instructions on the overlay."""
        if not self.canvas:
            return

        # Clear any existing instructions
        self.canvas.delete("instructions")

        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Draw instruction text
        instructions = [
            "Click and drag to select an area",
            "Press Escape to cancel"
        ]

        y_offset = 50
        for instruction in instructions:
            self.canvas.create_text(
                screen_width // 2, y_offset,
                text=instruction,
                fill=self.text_color,
                font=("Arial", 12, "bold"),
                anchor="center",
                tags="instructions"
            )
            y_offset += 25

    def set_overlay_color(self, color: str, alpha: float = 0.3):
        """Set overlay color and transparency.

        Args:
            color: Overlay color (hex format)
            alpha: Overlay transparency (0.0-1.0)
        """
        self.overlay_color = color
        self.overlay_alpha = alpha

        if self.root:
            self.root.attributes("-alpha", alpha)
            self.root.configure(fg_color=color)

        if self.canvas:
            self.canvas.configure(bg=color)

    def set_selection_color(self, color: str, border_width: int = 2):
        """Set selection rectangle color and border width.

        Args:
            color: Selection color (hex format)
            border_width: Border width in pixels
        """
        self.selection_color = color
        self.selection_border_width = border_width

    def set_text_colors(self, text_color: str, bg_color: str):
        """Set text colors for size display.

        Args:
            text_color: Text color (hex format)
            bg_color: Background color (hex format)
        """
        self.text_color = text_color
        self.text_bg_color = bg_color


class SelectionOverlayManager:
    """Manager for selection overlay operations."""

    def __init__(self):
        self._current_overlay: Optional[SelectionOverlay] = None
        self._lock = threading.RLock()

    def start_selection(self, callback: Optional[Callable[[SelectionResult], None]] = None) -> bool:
        """Start a new selection operation.

        Args:
            callback: Callback for selection result

        Returns:
            bool: True if selection started successfully
        """
        with self._lock:
            if self._current_overlay is not None:
                logger.warning("Selection already in progress")
                return False

            try:
                self._current_overlay = SelectionOverlay(callback)

                # Run selection in separate thread to avoid blocking
                def run_selection():
                    try:
                        result = self._current_overlay.start_selection()
                        if callback:
                            callback(result)
                    except Exception as e:
                        logger.error(f"Selection thread error: {e}")
                    finally:
                        with self._lock:
                            self._current_overlay = None

                thread = threading.Thread(target=run_selection, daemon=True)
                thread.start()

                return True

            except Exception as e:
                logger.error(f"Failed to start selection: {e}")
                self._current_overlay = None
                return False

    def cancel_current_selection(self):
        """Cancel the current selection operation."""
        with self._lock:
            if self._current_overlay:
                # The overlay will clean itself up
                self._current_overlay._cancel_selection()

    def is_selection_active(self) -> bool:
        """Check if a selection is currently active.

        Returns:
            bool: True if selection is active
        """
        with self._lock:
            return self._current_overlay is not None


# Global manager instance
_selection_manager = SelectionOverlayManager()


def start_screen_selection(callback: Optional[Callable[[SelectionResult], None]] = None) -> bool:
    """Start screen area selection.

    Args:
        callback: Callback function for selection result

    Returns:
        bool: True if selection started successfully
    """
    return _selection_manager.start_selection(callback)


def cancel_screen_selection():
    """Cancel current screen selection."""
    _selection_manager.cancel_current_selection()


def is_selection_active() -> bool:
    """Check if screen selection is active.

    Returns:
        bool: True if selection is active
    """
    return _selection_manager.is_selection_active()