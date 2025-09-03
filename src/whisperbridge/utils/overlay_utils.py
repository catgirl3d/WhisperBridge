"""
Utilities for overlay windows positioning and animations.

This module provides helper functions for calculating optimal overlay positioning,
handling screen boundaries, and managing smooth animations.
"""

import math
from typing import Tuple, Optional, Any

try:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QWidget, QApplication
    PYSIDE_AVAILABLE = True
except Exception:
    PYSIDE_AVAILABLE = False


class OverlayPosition:
    """Represents a position for overlay window."""

    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

    def as_tuple(self) -> Tuple[int, int]:
        """Return position as tuple."""
        return (self.x, self.y)


class ScreenBounds:
    """Represents screen boundaries."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height


def get_screen_bounds(root: Any = None) -> ScreenBounds:
    """Get screen dimensions.

    Args:
        root: Ignored (kept for compatibility)

    Returns:
        ScreenBounds: Screen dimensions
    """
    try:
        if PYSIDE_AVAILABLE and QGuiApplication.primaryScreen():
            screen = QGuiApplication.primaryScreen()
            rect = screen.availableGeometry()
            return ScreenBounds(width=rect.width(), height=rect.height())
        else:
            # Fallback to a sensible default if Qt not available
            return ScreenBounds(width=1920, height=1080)
    except Exception:
        return ScreenBounds(width=1920, height=1080)


def calculate_smart_position(
    trigger_position: Tuple[int, int],
    window_size: Tuple[int, int],
    screen_bounds: ScreenBounds,
    margin: int = 20
) -> OverlayPosition:
    """Calculate optimal overlay position with smart boundary handling.

    Args:
        trigger_position: (x, y) where overlay was triggered
        window_size: (width, height) of overlay window
        screen_bounds: Screen dimensions
        margin: Margin from screen edges

    Returns:
        OverlayPosition: Calculated position
    """
    trigger_x, trigger_y = trigger_position
    window_width, window_height = window_size

    # Preferred position: below and to the right
    preferred_x = trigger_x + margin
    preferred_y = trigger_y + margin

    # Check horizontal fit
    if preferred_x + window_width > screen_bounds.width - margin:
        # Try left side
        preferred_x = trigger_x - window_width - margin
        if preferred_x < margin:
            # Center horizontally
            preferred_x = (screen_bounds.width - window_width) // 2

    # Check vertical fit
    if preferred_y + window_height > screen_bounds.height - margin:
        # Try above
        preferred_y = trigger_y - window_height - margin
        if preferred_y < margin:
            # Center vertically
            preferred_y = (screen_bounds.height - window_height) // 2

    # Ensure within bounds
    final_x = max(margin, min(preferred_x, screen_bounds.width - window_width - margin))
    final_y = max(margin, min(preferred_y, screen_bounds.height - window_height - margin))

    return OverlayPosition(final_x, final_y)


def calculate_position_with_preference(
    trigger_position: Tuple[int, int],
    window_size: Tuple[int, int],
    screen_bounds: ScreenBounds,
    preferred_direction: str = "southeast",
    margin: int = 20
) -> OverlayPosition:
    """Calculate position with directional preference.

    Args:
        trigger_position: (x, y) where overlay was triggered
        window_size: (width, height) of overlay window
        screen_bounds: Screen dimensions
        preferred_direction: Preferred direction ('southeast', 'southwest', 'northeast', 'northwest')
        margin: Margin from screen edges

    Returns:
        OverlayPosition: Calculated position
    """
    directions = {
        "southeast": (1, 1),
        "southwest": (-1, 1),
        "northeast": (1, -1),
        "northwest": (-1, -1)
    }

    if preferred_direction not in directions:
        preferred_direction = "southeast"

    dir_x, dir_y = directions[preferred_direction]
    trigger_x, trigger_y = trigger_position
    window_width, window_height = window_size

    # Calculate preferred position
    preferred_x = trigger_x + dir_x * (window_width // 2 + margin)
    preferred_y = trigger_y + dir_y * (window_height // 2 + margin)

    # Adjust for boundaries
    if preferred_x < margin:
        preferred_x = margin
    elif preferred_x + window_width > screen_bounds.width - margin:
        preferred_x = screen_bounds.width - window_width - margin

    if preferred_y < margin:
        preferred_y = margin
    elif preferred_y + window_height > screen_bounds.height - margin:
        preferred_y = screen_bounds.height - window_height - margin

    return OverlayPosition(preferred_x, preferred_y)


def get_window_center(window: Any) -> Tuple[int, int]:
    """Get center coordinates of a window.

    Args:
        window: Window object (Tkinter Toplevel kept for signature compatibility, but Any is accepted)

    Returns:
        Tuple[int, int]: (center_x, center_y)
    """
    try:
        # Qt path: QWidget-like objects
        if PYSIDE_AVAILABLE and isinstance(window, QWidget):
            try:
                # Ensure geometry info is up-to-date
                try:
                    QApplication.processEvents()
                except Exception:
                    pass
                geom = window.frameGeometry() if hasattr(window, "frameGeometry") else window.geometry()
                center = geom.center()
                return (center.x(), center.y())
            except Exception:
                pass

        # Tkinter-compatible fallback (duck-typed)
        if hasattr(window, "winfo_x") and hasattr(window, "winfo_width"):
            try:
                # Keep previous semantics
                if hasattr(window, "update_idletasks"):
                    try:
                        window.update_idletasks()
                    except Exception:
                        pass
                x = window.winfo_x() + window.winfo_width() // 2
                y = window.winfo_y() + window.winfo_height() // 2
                return (x, y)
            except Exception:
                pass

        # Default fallback
        return (0, 0)
    except Exception:
        return (0, 0)


def calculate_distance(pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
    """Calculate Euclidean distance between two positions.

    Args:
        pos1: First position (x, y)
        pos2: Second position (x, y)

    Returns:
        float: Distance between positions
    """
    x1, y1 = pos1
    x2, y2 = pos2
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def is_position_visible(
    position: Tuple[int, int],
    window_size: Tuple[int, int],
    screen_bounds: ScreenBounds,
    margin: int = 0
) -> bool:
    """Check if a position is fully visible on screen.

    Args:
        position: (x, y) position
        window_size: (width, height) of window
        screen_bounds: Screen dimensions
        margin: Additional margin

    Returns:
        bool: True if position is fully visible
    """
    x, y = position
    width, height = window_size

    return (
        x >= margin and
        y >= margin and
        x + width <= screen_bounds.width - margin and
        y + height <= screen_bounds.height - margin
    )


def clamp_position(
    position: Tuple[int, int],
    window_size: Tuple[int, int],
    screen_bounds: ScreenBounds,
    margin: int = 0
) -> OverlayPosition:
    """Clamp position to ensure window stays within screen bounds.

    Args:
        position: (x, y) position
        window_size: (width, height) of window
        screen_bounds: Screen dimensions
        margin: Margin from edges

    Returns:
        OverlayPosition: Clamped position
    """
    x, y = position
    width, height = window_size

    clamped_x = max(margin, min(x, screen_bounds.width - width - margin))
    clamped_y = max(margin, min(y, screen_bounds.height - height - margin))

    return OverlayPosition(clamped_x, clamped_y)


class AnimationEasing:
    """Animation easing functions."""

    @staticmethod
    def linear(t: float) -> float:
        """Linear easing."""
        return t

    @staticmethod
    def ease_in_out(t: float) -> float:
        """Ease in out quadratic."""
        return t * t * (3.0 - 2.0 * t)

    @staticmethod
    def ease_out(t: float) -> float:
        """Ease out quadratic."""
        return t * (2.0 - t)


def interpolate_position(
    start_pos: Tuple[int, int],
    end_pos: Tuple[int, int],
    progress: float,
    easing_func: callable = AnimationEasing.linear
) -> Tuple[int, int]:
    """Interpolate between two positions with easing.

    Args:
        start_pos: Starting position (x, y)
        end_pos: Ending position (x, y)
        progress: Progress from 0.0 to 1.0
        easing_func: Easing function to use

    Returns:
        Tuple[int, int]: Interpolated position
    """
    eased_progress = easing_func(progress)

    start_x, start_y = start_pos
    end_x, end_y = end_pos

    current_x = start_x + (end_x - start_x) * eased_progress
    current_y = start_y + (end_y - start_y) * eased_progress

    return (int(current_x), int(current_y))


def calculate_adaptive_size(
    text_length: int,
    max_width: int = 400,
    max_height: int = 300,
    min_width: int = 300,
    min_height: int = 200
) -> Tuple[int, int]:
    """Calculate adaptive window size based on text content.

    Args:
        text_length: Length of text content
        max_width: Maximum window width
        max_height: Maximum window height
        min_width: Minimum window width
        min_height: Minimum window height

    Returns:
        Tuple[int, int]: (width, height) for window
    """
    # Base size calculation
    base_width = min_width
    base_height = min_height

    # Adjust width based on text length
    if text_length > 100:
        width_factor = min(1.5, text_length / 200.0)
        base_width = int(min_width + (max_width - min_width) * width_factor)

    # Adjust height based on text length
    if text_length > 50:
        height_factor = min(1.3, text_length / 150.0)
        base_height = int(min_height + (max_height - min_height) * height_factor)

    return (base_width, base_height)