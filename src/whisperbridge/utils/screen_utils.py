"""
Screen utilities for WhisperBridge.

This module provides utilities for working with screen coordinates,
monitor information, DPI scaling, and coordinate system conversions.
"""

import platform
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple


try:
    from PySide6.QtGui import QCursor, QGuiApplication

    PYSIDE_AVAILABLE = True
except Exception:
    PYSIDE_AVAILABLE = False

from loguru import logger


@dataclass
class MonitorInfo:
    """Information about a monitor."""

    x: int
    y: int
    width: int
    height: int
    is_primary: bool = False
    name: str = ""
    scale_factor: float = 1.0


@dataclass
class Point:
    """2D point coordinates."""

    x: int
    y: int


@dataclass
class Rectangle:
    """Rectangle coordinates."""

    x: int
    y: int
    width: int
    height: int

    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2

    def contains_point(self, point: Point) -> bool:
        """Check if point is inside rectangle."""
        return self.left <= point.x < self.right and self.top <= point.y < self.bottom

    def intersects(self, other: "Rectangle") -> bool:
        """Check if rectangles intersect."""
        return not (
            self.right <= other.left
            or self.left >= other.right
            or self.bottom <= other.top
            or self.top >= other.bottom
        )

    def clip_to_bounds(self, bounds: "Rectangle") -> "Rectangle":
        """Clip rectangle to fit within bounds."""
        x = max(self.x, bounds.x)
        y = max(self.y, bounds.y)
        right = min(self.right, bounds.right)
        bottom = min(self.bottom, bounds.bottom)

        width = max(0, right - x)
        height = max(0, bottom - y)

        return Rectangle(x, y, width, height)


class ScreenUtils:
    """Utilities for screen operations and coordinate management."""

    _lock = threading.RLock()
    _monitors_cache: Optional[List[MonitorInfo]] = None
    _cache_timestamp: float = 0
    _cache_timeout: float = 5.0  # Cache for 5 seconds

    @staticmethod
    def get_monitors() -> List[MonitorInfo]:
        """Get information about all monitors.

        Returns:
            List[MonitorInfo]: List of monitor information
        """
        with ScreenUtils._lock:
            import time

            current_time = time.time()

            # Return cached data if still valid
            if (
                ScreenUtils._monitors_cache is not None
                and current_time - ScreenUtils._cache_timestamp
                < ScreenUtils._cache_timeout
            ):
                return ScreenUtils._monitors_cache.copy()

            monitors = []
            system = platform.system()

            try:
                if system == "Windows":
                    monitors = ScreenUtils._get_monitors_windows()
                elif system == "Linux":
                    monitors = ScreenUtils._get_monitors_linux()
                elif system == "Darwin":  # macOS
                    monitors = ScreenUtils._get_monitors_macos()
                else:
                    logger.warning(f"Unsupported platform: {system}")
                    monitors = [ScreenUtils._get_fallback_monitor()]

            except Exception as e:
                logger.error(f"Failed to get monitor information: {e}")
                monitors = [ScreenUtils._get_fallback_monitor()]

            # Cache the results
            ScreenUtils._monitors_cache = monitors
            ScreenUtils._cache_timestamp = current_time

            return monitors.copy()

    @staticmethod
    def _get_monitors_windows() -> List[MonitorInfo]:
        """Get monitor information on Windows."""
        monitors = []

        try:
            import ctypes
            from ctypes import wintypes

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD),
                ]

            def monitor_enum_proc(hmonitor, hdc, lprect, lparam):
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(MONITORINFO)
                ctypes.windll.user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))

                is_primary = bool(info.dwFlags & 1)  # MONITORINFOF_PRIMARY

                monitor = MonitorInfo(
                    x=info.rcMonitor.left,
                    y=info.rcMonitor.top,
                    width=info.rcMonitor.right - info.rcMonitor.left,
                    height=info.rcMonitor.bottom - info.rcMonitor.top,
                    is_primary=is_primary,
                    scale_factor=ScreenUtils._get_scale_factor_windows(hmonitor),
                )
                monitors.append(monitor)
                return True

            MonitorEnumProc = ctypes.WINFUNCTYPE(
                ctypes.c_bool,
                wintypes.HMONITOR,
                wintypes.HDC,
                ctypes.POINTER(wintypes.RECT),
                wintypes.LPARAM,
            )

            ctypes.windll.user32.EnumDisplayMonitors(
                None, None, MonitorEnumProc(monitor_enum_proc), 0
            )

        except Exception as e:
            logger.error(f"Failed to get Windows monitor info: {e}")

        return monitors or [ScreenUtils._get_fallback_monitor()]

    @staticmethod
    def _get_monitors_linux() -> List[MonitorInfo]:
        """Get monitor information on Linux."""
        monitors = []

        try:
            # Try X11 first
            import subprocess

            result = subprocess.run(["xrandr"], capture_output=True, text=True)

            if result.returncode == 0:
                lines = result.stdout.split("\n")

                for line in lines:
                    if " connected " in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            name = parts[0]
                            resolution_part = parts[2] if '+' in parts[2] else parts[3] if len(parts) > 3 else None

                            if resolution_part and "x" in resolution_part:
                                res_parts = resolution_part.split("x")
                                if len(res_parts) >= 2:
                                    width = int(res_parts[0])
                                    height = int(res_parts[1].split("+")[0])

                                    # Get position
                                    pos_part = resolution_part.split("+")
                                    x = int(pos_part[1]) if len(pos_part) > 1 else 0
                                    y = int(pos_part[2]) if len(pos_part) > 2 else 0

                                    monitor = MonitorInfo(
                                        x=x,
                                        y=y,
                                        width=width,
                                        height=height,
                                        is_primary=(
                                            len(monitors) == 0
                                        ),  # First monitor is primary
                                        name=name,
                                    )
                                    monitors.append(monitor)

        except Exception as e:
            logger.error(f"Failed to get Linux monitor info via xrandr: {e}")

        return monitors or [ScreenUtils._get_fallback_monitor()]

    @staticmethod
    def _get_monitors_macos() -> List[MonitorInfo]:
        """Get monitor information on macOS."""
        monitors = []

        try:
            import subprocess

            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                lines = result.stdout.split("\n")

                for line in lines:
                    if "Resolution:" in line:
                        parts = line.split(":")[1].strip().split(" ")
                        if len(parts) >= 3:
                            width = int(parts[0])
                            height = int(parts[2])

                            monitor = MonitorInfo(
                                x=0,
                                y=0,
                                width=width,
                                height=height,
                                is_primary=(len(monitors) == 0),
                                name=f"Display {len(monitors) + 1}",
                            )
                            monitors.append(monitor)

        except Exception as e:
            logger.error(f"Failed to get macOS monitor info: {e}")

        return monitors or [ScreenUtils._get_fallback_monitor()]

    @staticmethod
    def _get_fallback_monitor() -> MonitorInfo:
        """Get fallback monitor information."""
        return MonitorInfo(x=0, y=0, width=1920, height=1080, is_primary=True)

    @staticmethod
    def _get_scale_factor_windows(hmonitor) -> float:
        """Get DPI scale factor on Windows."""
        try:
            import ctypes

            dpi = ctypes.c_uint()
            ctypes.windll.shcore.GetDpiForMonitor(hmonitor, 0, ctypes.byref(dpi), None)
            return dpi.value / 96.0  # 96 is the default DPI
        except Exception:
            return 1.0

    @staticmethod
    def get_primary_monitor() -> MonitorInfo:
        """Get the primary monitor.

        Returns:
            MonitorInfo: Primary monitor information
        """
        monitors = ScreenUtils.get_monitors()
        for monitor in monitors:
            if monitor.is_primary:
                return monitor
        return monitors[0] if monitors else ScreenUtils._get_fallback_monitor()

    @staticmethod
    def get_monitor_at_point(point: Point) -> Optional[MonitorInfo]:
        """Get monitor that contains the given point.

        Args:
            point: Point to check

        Returns:
            Optional[MonitorInfo]: Monitor containing the point, or None
        """
        monitors = ScreenUtils.get_monitors()
        for monitor in monitors:
            rect = Rectangle(monitor.x, monitor.y, monitor.width, monitor.height)
            if rect.contains_point(point):
                return monitor
        return None

    @staticmethod
    def get_virtual_screen_bounds() -> Rectangle:
        """Get bounds of the virtual screen (all monitors combined).

        Returns:
            Rectangle: Virtual screen bounds
        """
        monitors = ScreenUtils.get_monitors()

        if not monitors:
            return Rectangle(0, 0, 1920, 1080)

        min_x = min(m.x for m in monitors)
        min_y = min(m.y for m in monitors)
        max_x = max(m.x + m.width for m in monitors)
        max_y = max(m.y + m.height for m in monitors)

        return Rectangle(min_x, min_y, max_x - min_x, max_y - min_y)

    @staticmethod
    def scale_coordinates(x: int, y: int, from_dpi: float = 1.0, to_dpi: float = 1.0) -> Tuple[int, int]:
        """Scale coordinates between different DPI values.

        Args:
            x: X coordinate
            y: Y coordinate
            from_dpi: Source DPI scale factor
            to_dpi: Target DPI scale factor

        Returns:
            Tuple[int, int]: Scaled coordinates
        """
        if from_dpi == to_dpi:
            return x, y

        scale_factor = to_dpi / from_dpi
        return int(x * scale_factor), int(y * scale_factor)

    @staticmethod
    def get_cursor_position() -> Point:
        """Get current cursor position.

        Returns:
            Point: Current cursor position
        """
        try:
            if PYSIDE_AVAILABLE:
                pos = QCursor.pos()
                return Point(pos.x(), pos.y())
            else:
                # Fallback for systems without PySide6
                return Point(0, 0)
        except Exception as e:
            logger.error(f"Failed to get cursor position: {e}")
            return Point(0, 0)

    @staticmethod
    def point_to_screen(point: Point, monitor: Optional[MonitorInfo] = None) -> Point:
        """Convert point to screen coordinates.

        Args:
            point: Point in local coordinates
            monitor: Target monitor (primary if None)

        Returns:
            Point: Point in screen coordinates
        """
        if monitor is None:
            monitor = ScreenUtils.get_primary_monitor()

        return Point(point.x + monitor.x, point.y + monitor.y)

    @staticmethod
    def point_from_screen(point: Point, monitor: Optional[MonitorInfo] = None) -> Point:
        """Convert point from screen coordinates to monitor coordinates.

        Args:
            point: Point in screen coordinates
            monitor: Source monitor (auto-detect if None)

        Returns:
            Point: Point in monitor coordinates
        """
        if monitor is None:
            monitor = ScreenUtils.get_monitor_at_point(point)
            if monitor is None:
                monitor = ScreenUtils.get_primary_monitor()

        return Point(point.x - monitor.x, point.y - monitor.y)

    @staticmethod
    def rectangle_to_screen(rect: Rectangle, monitor: Optional[MonitorInfo] = None) -> Rectangle:
        """Convert rectangle to screen coordinates.

        Args:
            rect: Rectangle in local coordinates
            monitor: Target monitor (primary if None)

        Returns:
            Rectangle: Rectangle in screen coordinates
        """
        if monitor is None:
            monitor = ScreenUtils.get_primary_monitor()

        return Rectangle(
            rect.x + monitor.x, rect.y + monitor.y, rect.width, rect.height
        )

    @staticmethod
    def rectangle_from_screen(rect: Rectangle, monitor: Optional[MonitorInfo] = None) -> Rectangle:
        """Convert rectangle from screen coordinates to monitor coordinates.

        Args:
            rect: Rectangle in screen coordinates
            monitor: Source monitor (auto-detect if None)

        Returns:
            Rectangle: Rectangle in monitor coordinates
        """
        if monitor is None:
            # Use the monitor where the rectangle starts
            monitor = ScreenUtils.get_monitor_at_point(Point(rect.x, rect.y))
            if monitor is None:
                monitor = ScreenUtils.get_primary_monitor()

        return Rectangle(
            rect.x - monitor.x, rect.y - monitor.y, rect.width, rect.height
        )

    @staticmethod
    def clamp_rectangle_to_screen(rect: Rectangle) -> Rectangle:
        """Clamp rectangle to fit within screen bounds.

        Args:
            rect: Rectangle to clamp

        Returns:
            Rectangle: Clamped rectangle
        """
        screen_bounds = ScreenUtils.get_virtual_screen_bounds()
        return rect.clip_to_bounds(screen_bounds)

    @staticmethod
    def get_system_dpi() -> float:
        """Get system DPI scale factor.

        Returns:
            float: DPI scale factor
        """
        try:
            if PYSIDE_AVAILABLE:
                # Try to get the screen where the cursor is, fallback to primary
                screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
                dpi = screen.logicalDotsPerInch() if screen else 96.0
                return dpi / 72.0  # preserves legacy "pixels-per-point" style scale
            else:
                return 1.0
        except Exception as e:
            logger.error(f"Failed to get system DPI: {e}")
            return 1.0

    @staticmethod
    def invalidate_cache():
        """Invalidate the monitors cache."""
        with ScreenUtils._lock:
            ScreenUtils._monitors_cache = None
            ScreenUtils._cache_timestamp = 0

    @staticmethod
    def get_screen_capture_bounds() -> Rectangle:
        """Get bounds for screen capture (virtual screen).

        Returns:
            Rectangle: Screen capture bounds
        """
        return ScreenUtils.get_virtual_screen_bounds()
