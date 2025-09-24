"""
Screen capture service for WhisperBridge.

This module provides comprehensive screen capture functionality
including area selection, image capture, and processing.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
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
    file_path: Optional[str] = None


@dataclass
class CaptureOptions:
    """Options for screen capture."""

    format: str = "PNG"
    quality: int = 95
    include_cursor: bool = False
    monitor_index: Optional[int] = None
    scale_factor: float = 1.0
    save_to_file: bool = False
    output_path: Optional[str] = None


class ScreenCaptureError(Exception):
    """Exception raised when screen capture fails."""

    pass


class ScreenCaptureService:
    """Service for capturing screen content."""

    def __init__(self):
        """Initialize the screen capture service."""
        if not PIL_AVAILABLE:
            raise ImportError("Pillow is required for screen capture functionality")

        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="capture")
        self._capture_active = False

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
        logger.debug(f"Capture options: format={options.format}, quality={options.quality}, scale_factor={options.scale_factor}")

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

            # Save to file if requested
            file_path = None
            if options.save_to_file and image:
                file_path = self._save_image(image, options)
                logger.info(f"Image saved to file: {file_path}")

            result = CaptureResult(
                image=image,
                rectangle=clamped_rect,
                success=image is not None,
                capture_time=capture_time,
                file_path=file_path,
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

    def _save_image(self, image: Image.Image, options: CaptureOptions) -> Optional[str]:
        """Save image to file.

        Args:
            image: Image to save
            options: Save options

        Returns:
            Optional[str]: File path if saved successfully
        """
        try:
            logger.debug(f"Saving image: size={image.size}, mode={image.mode}, format={options.format}")
            if not options.output_path:
                # Generate default path
                timestamp = int(time.time())
                options.output_path = f"capture_{timestamp}.{options.format.lower()}"
                logger.debug(f"Generated output path: {options.output_path}")

            output_path = Path(options.output_path)

            # Ensure directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Output directory ensured: {output_path.parent}")

            # Save image
            if options.format.upper() == "JPEG":
                image.save(output_path, options.format.upper(), quality=options.quality)
                logger.debug(f"Image saved as JPEG with quality={options.quality}")
            else:
                image.save(output_path, options.format.upper())
                logger.debug(f"Image saved as {options.format.upper()}")

            logger.info(f"Image saved successfully to: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Failed to save image: {e}")
            logger.debug(f"Save error details: {type(e).__name__}: {str(e)}", exc_info=True)
            return None

    def __del__(self):
        """Cleanup resources."""
        try:
            self._executor.shutdown(wait=True)
        except Exception:
            pass


# Global service instance
_capture_service: Optional[ScreenCaptureService] = None
_service_lock = threading.RLock()


def get_capture_service() -> ScreenCaptureService:
    """Get the global screen capture service instance.

    Returns:
        ScreenCaptureService: Global service instance
    """
    global _capture_service

    with _service_lock:
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
