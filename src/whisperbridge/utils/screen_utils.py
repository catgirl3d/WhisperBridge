"""
Screen utilities for WhisperBridge.

This module provides utilities for working with screen coordinates,
monitor information, and virtual desktop geometry.
"""

import platform
from dataclasses import dataclass
from typing import List

from loguru import logger


@dataclass
class MonitorInfo:
    """Information about a monitor."""

    x: int
    y: int
    width: int
    height: int


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
    """Utilities for screen operations."""

    @staticmethod
    def get_monitors() -> List[MonitorInfo]:
        """Get information about all monitors.

        Returns:
            List[MonitorInfo]: List of monitor information
        """
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

        return monitors

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

                monitor = MonitorInfo(
                    x=info.rcMonitor.left,
                    y=info.rcMonitor.top,
                    width=info.rcMonitor.right - info.rcMonitor.left,
                    height=info.rcMonitor.bottom - info.rcMonitor.top,
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
                            )
                            monitors.append(monitor)

        except Exception as e:
            logger.error(f"Failed to get macOS monitor info: {e}")

        return monitors or [ScreenUtils._get_fallback_monitor()]

    @staticmethod
    def _get_fallback_monitor() -> MonitorInfo:
        """Get fallback monitor information."""
        return MonitorInfo(x=0, y=0, width=1920, height=1080)

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
    def get_screen_capture_bounds() -> Rectangle:
        """Get bounds for screen capture (virtual screen).

        Returns:
            Rectangle: Screen capture bounds
        """
        return ScreenUtils.get_virtual_screen_bounds()
