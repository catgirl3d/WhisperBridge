"""
Tests for screen utilities.

This module contains unit tests for screen utility functions.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from whisperbridge.utils.screen_utils import (
    ScreenUtils,
    Rectangle,
    Point,
    MonitorInfo
)


class TestScreenUtils(unittest.TestCase):
    """Test cases for ScreenUtils."""

    def setUp(self):
        """Set up test fixtures."""
        # Clear any cached data
        ScreenUtils.invalidate_cache()

    def tearDown(self):
        """Clean up test fixtures."""
        ScreenUtils.invalidate_cache()

    @patch('whisperbridge.utils.screen_utils.platform.system')
    @patch('whisperbridge.utils.screen_utils.ScreenUtils._get_monitors_windows')
    def test_get_monitors_windows(self, mock_get_monitors, mock_platform):
        """Test monitor detection on Windows."""
        mock_platform.return_value = "Windows"
        mock_get_monitors.return_value = [
            MonitorInfo(0, 0, 1920, 1080, True),
            MonitorInfo(1920, 0, 1920, 1080, False)
        ]

        monitors = ScreenUtils.get_monitors()

        self.assertEqual(len(monitors), 2)
        self.assertTrue(monitors[0].is_primary)
        self.assertFalse(monitors[1].is_primary)

    @patch('whisperbridge.utils.screen_utils.platform.system')
    @patch('whisperbridge.utils.screen_utils.ScreenUtils._get_monitors_linux')
    def test_get_monitors_linux(self, mock_get_monitors, mock_platform):
        """Test monitor detection on Linux."""
        mock_platform.return_value = "Linux"
        mock_get_monitors.return_value = [
            MonitorInfo(0, 0, 1920, 1080, True)
        ]

        monitors = ScreenUtils.get_monitors()

        self.assertEqual(len(monitors), 1)
        self.assertTrue(monitors[0].is_primary)

    def test_monitor_caching(self):
        """Test monitor information caching."""
        with patch('whisperbridge.utils.screen_utils.ScreenUtils._get_monitors_windows') as mock_get:
            mock_get.return_value = [MonitorInfo(0, 0, 1920, 1080, True)]

            with patch('whisperbridge.utils.screen_utils.platform.system', return_value="Windows"):
                # First call
                monitors1 = ScreenUtils.get_monitors()
                # Second call should use cache
                monitors2 = ScreenUtils.get_monitors()

                # Should only call once due to caching
                self.assertEqual(mock_get.call_count, 1)
                self.assertEqual(monitors1, monitors2)

    def test_get_primary_monitor(self):
        """Test primary monitor detection."""
        with patch('whisperbridge.utils.screen_utils.ScreenUtils.get_monitors') as mock_get:
            monitors = [
                MonitorInfo(1920, 0, 1920, 1080, False),
                MonitorInfo(0, 0, 1920, 1080, True)
            ]
            mock_get.return_value = monitors

            primary = ScreenUtils.get_primary_monitor()

            self.assertTrue(primary.is_primary)
            self.assertEqual(primary.x, 0)
            self.assertEqual(primary.y, 0)

    def test_get_monitor_at_point(self):
        """Test finding monitor at specific point."""
        with patch('whisperbridge.utils.screen_utils.ScreenUtils.get_monitors') as mock_get:
            monitors = [
                MonitorInfo(0, 0, 1920, 1080, True),
                MonitorInfo(1920, 0, 1920, 1080, False)
            ]
            mock_get.return_value = monitors

            # Point in first monitor
            monitor = ScreenUtils.get_monitor_at_point(Point(100, 100))
            self.assertEqual(monitor.x, 0)

            # Point in second monitor
            monitor = ScreenUtils.get_monitor_at_point(Point(2000, 100))
            self.assertEqual(monitor.x, 1920)

            # Point not in any monitor
            monitor = ScreenUtils.get_monitor_at_point(Point(-100, -100))
            self.assertIsNone(monitor)

    def test_get_virtual_screen_bounds(self):
        """Test virtual screen bounds calculation."""
        with patch('whisperbridge.utils.screen_utils.ScreenUtils.get_monitors') as mock_get:
            monitors = [
                MonitorInfo(0, 0, 1920, 1080, True),
                MonitorInfo(1920, 0, 1920, 1080, False),
                MonitorInfo(0, 1080, 1920, 1080, False)
            ]
            mock_get.return_value = monitors

            bounds = ScreenUtils.get_virtual_screen_bounds()

            self.assertEqual(bounds.x, 0)
            self.assertEqual(bounds.y, 0)
            self.assertEqual(bounds.width, 3840)  # 1920 + 1920
            self.assertEqual(bounds.height, 2160)  # 1080 + 1080

    def test_coordinate_scaling(self):
        """Test coordinate scaling between DPI values."""
        # Scale up
        x, y = ScreenUtils.scale_coordinates(100, 200, 1.0, 2.0)
        self.assertEqual(x, 200)
        self.assertEqual(y, 400)

        # Scale down
        x, y = ScreenUtils.scale_coordinates(200, 400, 2.0, 1.0)
        self.assertEqual(x, 100)
        self.assertEqual(y, 200)

        # No scaling
        x, y = ScreenUtils.scale_coordinates(100, 200, 1.0, 1.0)
        self.assertEqual(x, 100)
        self.assertEqual(y, 200)

    def test_point_coordinate_conversion(self):
        """Test point coordinate conversions."""
        monitor = MonitorInfo(100, 200, 1920, 1080, True)

        # Screen to monitor
        point_screen = Point(300, 400)
        point_monitor = ScreenUtils.point_from_screen(point_screen, monitor)

        self.assertEqual(point_monitor.x, 200)  # 300 - 100
        self.assertEqual(point_monitor.y, 200)  # 400 - 200

        # Monitor to screen
        point_screen2 = ScreenUtils.point_to_screen(point_monitor, monitor)

        self.assertEqual(point_screen2.x, 300)
        self.assertEqual(point_screen2.y, 400)

    def test_rectangle_operations(self):
        """Test rectangle operations."""
        rect = Rectangle(10, 20, 100, 200)

        # Test properties
        self.assertEqual(rect.left, 10)
        self.assertEqual(rect.top, 20)
        self.assertEqual(rect.right, 110)
        self.assertEqual(rect.bottom, 220)
        self.assertEqual(rect.center_x, 60)
        self.assertEqual(rect.center_y, 120)

        # Test point containment
        self.assertTrue(rect.contains_point(Point(50, 100)))
        self.assertFalse(rect.contains_point(Point(5, 100)))
        self.assertFalse(rect.contains_point(Point(50, 300)))

        # Test intersection
        rect2 = Rectangle(50, 100, 100, 200)
        self.assertTrue(rect.intersects(rect2))

        rect3 = Rectangle(200, 300, 100, 200)
        self.assertFalse(rect.intersects(rect3))

    def test_rectangle_clipping(self):
        """Test rectangle clipping to bounds."""
        bounds = Rectangle(0, 0, 100, 100)

        # Rectangle completely inside bounds
        rect = Rectangle(10, 10, 50, 50)
        clipped = rect.clip_to_bounds(bounds)
        self.assertEqual(clipped, rect)

        # Rectangle partially outside bounds
        rect = Rectangle(-10, -10, 50, 50)
        clipped = rect.clip_to_bounds(bounds)
        self.assertEqual(clipped.x, 0)
        self.assertEqual(clipped.y, 0)
        self.assertEqual(clipped.width, 40)
        self.assertEqual(clipped.height, 40)

        # Rectangle completely outside bounds
        rect = Rectangle(200, 200, 50, 50)
        clipped = rect.clip_to_bounds(bounds)
        self.assertEqual(clipped.width, 0)
        self.assertEqual(clipped.height, 0)

    def test_clamp_rectangle_to_screen(self):
        """Test clamping rectangle to screen bounds."""
        with patch('whisperbridge.utils.screen_utils.ScreenUtils.get_virtual_screen_bounds') as mock_bounds:
            mock_bounds.return_value = Rectangle(0, 0, 1920, 1080)

            rect = Rectangle(-10, -10, 100, 100)
            clamped = ScreenUtils.clamp_rectangle_to_screen(rect)

            self.assertEqual(clamped.x, 0)
            self.assertEqual(clamped.y, 0)
            self.assertEqual(clamped.width, 90)
            self.assertEqual(clamped.height, 90)


class TestDataClasses(unittest.TestCase):
    """Test cases for data classes."""

    def test_point_creation(self):
        """Test Point creation."""
        point = Point(10, 20)
        self.assertEqual(point.x, 10)
        self.assertEqual(point.y, 20)

    def test_rectangle_creation(self):
        """Test Rectangle creation."""
        rect = Rectangle(10, 20, 100, 200)
        self.assertEqual(rect.x, 10)
        self.assertEqual(rect.y, 20)
        self.assertEqual(rect.width, 100)
        self.assertEqual(rect.height, 200)

    def test_monitor_info_creation(self):
        """Test MonitorInfo creation."""
        monitor = MonitorInfo(0, 0, 1920, 1080, True, "Display 1", 1.5)
        self.assertEqual(monitor.x, 0)
        self.assertEqual(monitor.y, 0)
        self.assertEqual(monitor.width, 1920)
        self.assertEqual(monitor.height, 1080)
        self.assertTrue(monitor.is_primary)
        self.assertEqual(monitor.name, "Display 1")
        self.assertEqual(monitor.scale_factor, 1.5)


if __name__ == '__main__':
    unittest.main()