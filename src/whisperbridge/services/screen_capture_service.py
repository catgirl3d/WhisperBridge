"""
Screen capture service for WhisperBridge.

This module provides comprehensive screen capture functionality
including area selection, image capture, and processing.
"""

import threading
import time
from dataclasses import dataclass
from typing import Optional

try:
    from PIL import Image, ImageGrab

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None
    ImageGrab = None

from loguru import logger

from ..utils.screen_utils import Rectangle, ScreenUtils

# Minimal types and stub to avoid undefined names in non-UI context


@dataclass
class SelectionResult:
    rectangle: Optional[Rectangle] = None
    cancelled: bool = True


@dataclass
class CaptureResult:
    """Result of screen capture operation."""

    image: Optional[Image.Image]
    rectangle: Optional[Rectangle]
    success: bool
    error_message: str = ""
    capture_time: float = 0.0


@dataclass
class CaptureOptions:
    """Options for screen capture."""

    include_cursor: bool = False
    monitor_index: Optional[int] = None
    scale_factor: float = 1.0


class ScreenCaptureService:
    """Service for capturing screen content."""

    def __init__(self):
        """Initialize the screen capture service."""
        if not PIL_AVAILABLE:
            raise ImportError("Pillow is required for screen capture functionality")

        self._capture_active = False
        self._lock = threading.RLock()

        # Default options
        self.default_options = CaptureOptions()

        logger.info("ScreenCaptureService initialized")

    def capture_area(
        self, rectangle: Rectangle, options: Optional[CaptureOptions] = None
    ) -> CaptureResult:
        """Capture a specific screen area.

        Args:
            rectangle: Area to capture
            options: Capture options

        Returns:
            CaptureResult: Capture result
        """
        logger.info(f"Requested area capture: rectangle={rectangle}")
        with self._lock:
            if self._capture_active:
                logger.warning("Capture already in progress, rejecting new request")
                return CaptureResult(None, None, False, "Capture already in progress")

            self._capture_active = True
            logger.debug("Capture lock acquired")

        try:
            opts = options or self.default_options
            logger.debug(f"Using capture options: {opts}")
            result = self._capture_selected_area(rectangle, opts)
            logger.info(f"Area capture completed: success={result.success}")
            return result

        except Exception as e:
            logger.error(f"Area capture failed: {e}")
            logger.debug(f"Area capture error details: {type(e).__name__}: {str(e)}", exc_info=True)
            return CaptureResult(None, None, False, str(e))

        finally:
            with self._lock:
                self._capture_active = False
                logger.debug("Capture lock released")

    def _capture_selected_area(
        self, rectangle: Rectangle, options: CaptureOptions
    ) -> CaptureResult:
        """Capture a selected screen area.

        Args:
            rectangle: Area to capture
            options: Capture options

        Returns:
            CaptureResult: Capture result
        """
        start_time = time.time()
        logger.info(f"Starting selected area capture: rectangle={rectangle}")
        logger.debug(f"Capture options: include_cursor={options.include_cursor}, monitor_index={options.monitor_index}, scale_factor={options.scale_factor}")

        try:
            # Clamp rectangle to screen bounds
            logger.debug(f"Original rectangle: {rectangle}")
            clamped_rect = ScreenUtils.clamp_rectangle_to_screen(rectangle)
            logger.debug(f"Clamped rectangle: {clamped_rect}")

            if clamped_rect.width <= 0 or clamped_rect.height <= 0:
                logger.error(f"Invalid capture area after clamping: width={clamped_rect.width}, height={clamped_rect.height}")
                return CaptureResult(None, None, False, "Invalid capture area")

            logger.info(f"Valid capture area: {clamped_rect.width}x{clamped_rect.height} at ({clamped_rect.x}, {clamped_rect.y})")

            # Capture the area
            image = self._capture_screen_area(clamped_rect, options)

            capture_time = time.time() - start_time
            logger.info(f"Area capture completed in {capture_time:.2f}s")

            result = CaptureResult(
                image=image,
                rectangle=clamped_rect,
                success=image is not None,
                capture_time=capture_time,
            )

            logger.info(f"Capture result: success={result.success}, image_size={image.size if image else None}")
            if not result.success:
                result.error_message = "Failed to capture area"

            return result

        except Exception as e:
            capture_time = time.time() - start_time
            logger.error(f"Selected area capture failed after {capture_time:.2f}s: {e}")
            logger.debug(f"Capture error details: {type(e).__name__}: {str(e)}", exc_info=True)
            return CaptureResult(None, None, False, str(e))

    def _capture_screen_area(
        self, rectangle: Rectangle, options: CaptureOptions
    ) -> Optional[Image.Image]:
        """Capture a screen area using PIL.

        Args:
            rectangle: Area to capture
            options: Capture options

        Returns:
            Optional[Image.Image]: Captured image or None
        """
        logger.debug(f"Starting screen capture: rectangle={rectangle}, options={options}")
        try:
            # Convert rectangle to PIL bbox format (left, top, right, bottom)
            bbox = (rectangle.x, rectangle.y, rectangle.right, rectangle.bottom)
            logger.debug(
                f"Screen capture bbox: {bbox}, area: {rectangle.width}x{rectangle.height}"
            )

            # Capture screen
            image = ImageGrab.grab(bbox=bbox, include_layered_windows=True)
            logger.debug(f"ImageGrab result: {image}")

            if image is None:
                logger.error("PIL returned None image")
                return None

            logger.info(f"Screen captured successfully: size={image.size}, mode={image.mode}, format={image.format}")

            # Apply scaling if needed
            if options.scale_factor != 1.0:
                original_size = image.size
                new_width = int(image.width * options.scale_factor)
                new_height = int(image.height * options.scale_factor)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.info(f"Image scaled: {original_size} -> {image.size}, factor={options.scale_factor}")

            logger.debug(f"Final captured image: {image.size}, mode: {image.mode}")
            return image

        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            logger.debug(f"Capture error details: {type(e).__name__}: {str(e)}", exc_info=True)
            return None

# Global service instance
_capture_service: Optional[ScreenCaptureService] = None


def get_capture_service() -> ScreenCaptureService:
    """Get the global screen capture service instance.

    Returns:
        ScreenCaptureService: Global service instance
    """
    global _capture_service

    if _capture_service is None:
        _capture_service = ScreenCaptureService()

    return _capture_service


def capture_area(
    rectangle: Rectangle, options: Optional[CaptureOptions] = None
) -> CaptureResult:
    """Capture a specific screen area.

    Args:
        rectangle: Area to capture
        options: Capture options

    Returns:
        CaptureResult: Capture result
    """
    return get_capture_service().capture_area(rectangle, options)
