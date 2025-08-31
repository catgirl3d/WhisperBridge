"""
Integration tests for screen capture system.

This module contains integration tests that verify the entire
screen capture workflow works correctly.
"""

import unittest
from unittest.mock import Mock, patch
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from whisperbridge.services.screen_capture_service import ScreenCaptureService
from whisperbridge.utils.screen_utils import ScreenUtils, Rectangle, Point


class TestScreenCaptureIntegration(unittest.TestCase):
    """Integration tests for screen capture system."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = ScreenCaptureService()

    def tearDown(self):
        """Clean up test fixtures."""
        if hasattr(self.service, '_executor'):
            self.service._executor.shutdown(wait=True)

    @patch('whisperbridge.services.screen_capture_service.PIL_AVAILABLE', True)
    @patch('whisperbridge.services.screen_capture_service.ImageGrab')
    def test_full_workflow_capture_area(self, mock_image_grab):
        """Test complete workflow for capturing a specific area."""
        # Mock PIL Image
        mock_image = Mock()
        mock_image.size = (800, 600)
        mock_image.mode = "RGB"
        mock_image.save = Mock()
        mock_image.resize = Mock(return_value=mock_image)

        mock_image_grab.grab.return_value = mock_image

        # Define capture area
        capture_rect = Rectangle(100, 100, 800, 600)

        # Execute capture
        result = self.service.capture_area(capture_rect)

        # Verify result
        self.assertTrue(result.success)
        self.assertIsNotNone(result.image)
        self.assertEqual(result.rectangle, capture_rect)
        self.assertGreater(result.capture_time, 0)

        # Verify PIL was called with correct coordinates
        mock_image_grab.grab.assert_called_once_with(
            bbox=(100, 100, 900, 700),  # left, top, right, bottom
            include_layered_windows=True
        )

    @patch('whisperbridge.services.screen_capture_service.PIL_AVAILABLE', True)
    @patch('whisperbridge.services.screen_capture_service.ImageGrab')
    def test_monitor_capture_workflow(self, mock_image_grab):
        """Test complete workflow for capturing a monitor."""
        # Mock PIL Image
        mock_image = Mock()
        mock_image.size = (1920, 1080)
        mock_image.mode = "RGB"
        mock_image.save = Mock()
        mock_image.resize = Mock(return_value=mock_image)

        mock_image_grab.grab.return_value = mock_image

        # Mock monitor info
        with patch('whisperbridge.services.screen_capture_service.ScreenUtils') as mock_utils:
            monitor = Mock()
            monitor.x = 0
            monitor.y = 0
            monitor.width = 1920
            monitor.height = 1080
            monitor.is_primary = True

            mock_utils.get_monitors.return_value = [monitor]

            # Execute capture
            result = self.service.capture_monitor(0)

            # Verify result
            self.assertTrue(result.success)
            self.assertIsNotNone(result.image)
            self.assertEqual(result.rectangle.x, 0)
            self.assertEqual(result.rectangle.y, 0)
            self.assertEqual(result.rectangle.width, 1920)
            self.assertEqual(result.rectangle.height, 1080)

    def test_error_handling_workflow(self):
        """Test error handling throughout the workflow."""
        # Test with invalid rectangle
        invalid_rect = Rectangle(0, 0, 0, 0)
        result = self.service.capture_area(invalid_rect)

        self.assertFalse(result.success)
        self.assertIn("Invalid capture area", result.error_message)

    def test_scaling_options(self):
        """Test scaling options configuration."""
        from whisperbridge.services.screen_capture_service import CaptureOptions

        # Test scaling factor validation
        options = CaptureOptions(scale_factor=0.5)
        self.assertEqual(options.scale_factor, 0.5)

        # Test default scaling
        default_options = CaptureOptions()
        self.assertEqual(default_options.scale_factor, 1.0)

    def test_service_lifecycle(self):
        """Test service initialization and cleanup."""
        # Test service creation
        service = ScreenCaptureService()
        self.assertIsNotNone(service)

        # Test service is not capturing initially
        self.assertFalse(service.is_capture_active())

        # Test statistics
        stats = service.get_capture_statistics()
        self.assertIn("pil_available", stats)
        self.assertIn("supported_formats", stats)

        # Test cleanup
        service._executor.shutdown(wait=True)

    def test_coordinate_system_integration(self):
        """Test integration between coordinate systems."""
        # Test point conversions
        monitor = Mock()
        monitor.x = 100
        monitor.y = 200
        monitor.width = 1920
        monitor.height = 1080

        point_local = Point(50, 75)
        point_screen = ScreenUtils.point_to_screen(point_local, monitor)

        self.assertEqual(point_screen.x, 150)  # 50 + 100
        self.assertEqual(point_screen.y, 275)  # 75 + 200

        # Convert back
        point_back = ScreenUtils.point_from_screen(point_screen, monitor)

        self.assertEqual(point_back.x, 50)
        self.assertEqual(point_back.y, 75)

    def test_rectangle_operations_integration(self):
        """Test rectangle operations in capture workflow."""
        from whisperbridge.utils.screen_utils import Rectangle

        # Test rectangle intersection
        rect1 = Rectangle(0, 0, 100, 100)
        rect2 = Rectangle(50, 50, 100, 100)

        self.assertTrue(rect1.intersects(rect2))

        # Test rectangle containment
        point_inside = Point(25, 25)
        point_outside = Point(150, 150)

        self.assertTrue(rect1.contains_point(point_inside))
        self.assertFalse(rect1.contains_point(point_outside))

    def test_monitor_bounds_integration(self):
        """Test monitor bounds integration."""
        with patch('whisperbridge.utils.screen_utils.ScreenUtils.get_monitors') as mock_get:
            # Mock two monitors side by side
            monitors = [
                Mock(x=0, y=0, width=1920, height=1080),
                Mock(x=1920, y=0, width=1920, height=1080)
            ]
            mock_get.return_value = monitors

            bounds = ScreenUtils.get_virtual_screen_bounds()

            self.assertEqual(bounds.x, 0)
            self.assertEqual(bounds.y, 0)
            self.assertEqual(bounds.width, 3840)  # 1920 * 2
            self.assertEqual(bounds.height, 1080)


class TestSystemIntegration(unittest.TestCase):
    """Tests for system-level integration."""

    def test_import_chain(self):
        """Test that all modules can be imported without circular dependencies."""
        try:
            # Test main service imports
            from whisperbridge.services.screen_capture_service import (
                ScreenCaptureService,
                CaptureResult,
                CaptureOptions
            )

            # Test utility imports
            from whisperbridge.utils.screen_utils import (
                ScreenUtils,
                Rectangle,
                Point,
                MonitorInfo
            )

            # Test UI imports (without circular dependency)
            from whisperbridge.ui.selection_overlay import SelectionOverlay

            # All imports successful
            self.assertTrue(True)

        except ImportError as e:
            self.fail(f"Import failed: {e}")

    def test_service_initialization(self):
        """Test service initialization with all dependencies."""
        try:
            service = ScreenCaptureService()

            # Verify service has required attributes
            self.assertTrue(hasattr(service, 'capture_full_screen'))
            self.assertTrue(hasattr(service, 'capture_area'))
            self.assertTrue(hasattr(service, 'capture_monitor'))

            # Verify service can provide statistics
            stats = service.get_capture_statistics()
            self.assertIsInstance(stats, dict)

        except Exception as e:
            self.fail(f"Service initialization failed: {e}")


if __name__ == '__main__':
    unittest.main()