"""
Tests for screen capture service.

This module contains unit tests for the screen capture functionality.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from whisperbridge.services.screen_capture_service import (
    ScreenCaptureService,
    CaptureResult,
    CaptureOptions
)
from whisperbridge.utils.screen_utils import Rectangle


class TestScreenCaptureService(unittest.TestCase):
    """Test cases for ScreenCaptureService."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = ScreenCaptureService()

    def tearDown(self):
        """Clean up test fixtures."""
        if hasattr(self.service, '_executor'):
            self.service._executor.shutdown(wait=True)

    @patch('whisperbridge.services.screen_capture_service.PIL_AVAILABLE', True)
    @patch('whisperbridge.services.screen_capture_service.ImageGrab')
    def test_capture_full_screen_success(self, mock_image_grab):
        """Test successful full screen capture."""
        # Mock PIL Image
        mock_image = Mock()
        mock_image.size = (1920, 1080)
        mock_image.mode = "RGB"
        mock_image.save = Mock()
        mock_image.resize = Mock(return_value=mock_image)

        mock_image_grab.grab.return_value = mock_image

        # Mock screen utils
        with patch('whisperbridge.services.screen_capture_service.ScreenUtils') as mock_utils:
            mock_utils.get_virtual_screen_bounds.return_value = Rectangle(0, 0, 1920, 1080)

            result = self.service.capture_full_screen()

            self.assertTrue(result.success)
            self.assertIsNotNone(result.image)
            self.assertEqual(result.rectangle.width, 1920)
            self.assertEqual(result.rectangle.height, 1080)
            self.assertGreater(result.capture_time, 0)

    @patch('whisperbridge.services.screen_capture_service.PIL_AVAILABLE', True)
    @patch('whisperbridge.services.screen_capture_service.ImageGrab')
    def test_capture_full_screen_failure(self, mock_image_grab):
        """Test full screen capture failure."""
        mock_image_grab.grab.return_value = None

        with patch('whisperbridge.services.screen_capture_service.ScreenUtils') as mock_utils:
            mock_utils.get_virtual_screen_bounds.return_value = Rectangle(0, 0, 1920, 1080)

            result = self.service.capture_full_screen()

            self.assertFalse(result.success)
            self.assertIsNone(result.image)
            self.assertIn("Failed to capture", result.error_message)

    @patch('whisperbridge.services.screen_capture_service.PIL_AVAILABLE', False)
    def test_capture_without_pil(self):
        """Test capture service initialization without PIL."""
        with self.assertRaises(ImportError):
            ScreenCaptureService()

    def test_capture_options(self):
        """Test capture options configuration."""
        options = CaptureOptions(
            format="JPEG",
            quality=90,
            scale_factor=0.5,
            save_to_file=True,
            output_path="test.jpg"
        )

        self.assertEqual(options.format, "JPEG")
        self.assertEqual(options.quality, 90)
        self.assertEqual(options.scale_factor, 0.5)
        self.assertTrue(options.save_to_file)
        self.assertEqual(options.output_path, "test.jpg")

    def test_service_statistics(self):
        """Test service statistics retrieval."""
        stats = self.service.get_capture_statistics()

        self.assertIn("pil_available", stats)
        self.assertIn("capture_active", stats)
        self.assertIn("supported_formats", stats)
        self.assertIn("monitor_count", stats)
        self.assertIn("default_options", stats)

        self.assertIsInstance(stats["supported_formats"], list)
        self.assertIn("PNG", stats["supported_formats"])

    @patch('whisperbridge.services.screen_capture_service.PIL_AVAILABLE', True)
    def test_capture_area_validation(self):
        """Test capture area validation."""
        # Test invalid rectangle
        invalid_rect = Rectangle(0, 0, 0, 0)
        result = self.service.capture_area(invalid_rect)

        self.assertFalse(result.success)
        self.assertIn("Invalid capture area", result.error_message)

    def test_thread_safety(self):
        """Test thread-safe operations."""
        # Test that multiple operations don't interfere
        self.assertFalse(self.service.is_capture_active())

        # Simulate active capture
        self.service._capture_active = True
        self.assertTrue(self.service.is_capture_active())

        # Test concurrent access
        with patch.object(self.service, '_lock'):
            result = self.service.capture_full_screen()
            self.assertFalse(result.success)
            self.assertIn("already in progress", result.error_message)


class TestCaptureResult(unittest.TestCase):
    """Test cases for CaptureResult."""

    def test_capture_result_creation(self):
        """Test CaptureResult creation and properties."""
        rect = Rectangle(10, 20, 100, 200)

        result = CaptureResult(
            image=None,
            rectangle=rect,
            success=True,
            capture_time=1.5,
            file_path="/path/to/image.png"
        )

        self.assertTrue(result.success)
        self.assertEqual(result.rectangle, rect)
        self.assertEqual(result.capture_time, 1.5)
        self.assertEqual(result.file_path, "/path/to/image.png")

    def test_capture_result_failure(self):
        """Test failed CaptureResult."""
        result = CaptureResult(
            image=None,
            rectangle=None,
            success=False,
            error_message="Test error"
        )

        self.assertFalse(result.success)
        self.assertIsNone(result.image)
        self.assertIsNone(result.rectangle)
        self.assertEqual(result.error_message, "Test error")


if __name__ == '__main__':
    unittest.main()