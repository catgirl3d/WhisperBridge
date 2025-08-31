"""
Screen capture service for WhisperBridge.

This module provides comprehensive screen capture functionality
including area selection, image capture, and processing.
"""

import threading
import time
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import io

try:
    from PIL import Image, ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None
    ImageGrab = None

from loguru import logger
from ..utils.screen_utils import ScreenUtils, Rectangle, Point, MonitorInfo
from ..ui.selection_overlay import start_screen_selection, SelectionResult


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

    def capture_full_screen(self, options: Optional[CaptureOptions] = None) -> CaptureResult:
        """Capture the full screen.

        Args:
            options: Capture options

        Returns:
            CaptureResult: Capture result
        """
        with self._lock:
            if self._capture_active:
                return CaptureResult(None, None, False, "Capture already in progress")

            self._capture_active = True

        try:
            opts = options or self.default_options
            start_time = time.time()

            # Get screen bounds
            screen_bounds = ScreenUtils.get_virtual_screen_bounds()

            # Capture screen
            image = self._capture_screen_area(screen_bounds, opts)

            capture_time = time.time() - start_time

            # Save to file if requested
            file_path = None
            if opts.save_to_file and image:
                file_path = self._save_image(image, opts)

            result = CaptureResult(
                image=image,
                rectangle=screen_bounds,
                success=image is not None,
                capture_time=capture_time,
                file_path=file_path
            )

            if not result.success:
                result.error_message = "Failed to capture screen"

            return result

        except Exception as e:
            logger.error(f"Full screen capture failed: {e}")
            return CaptureResult(None, None, False, str(e))

        finally:
            with self._lock:
                self._capture_active = False

    def capture_monitor(self, monitor_index: int = 0,
                       options: Optional[CaptureOptions] = None) -> CaptureResult:
        """Capture a specific monitor.

        Args:
            monitor_index: Index of monitor to capture
            options: Capture options

        Returns:
            CaptureResult: Capture result
        """
        with self._lock:
            if self._capture_active:
                return CaptureResult(None, None, False, "Capture already in progress")

            self._capture_active = True

        try:
            opts = options or self.default_options
            start_time = time.time()

            # Get monitor info
            monitors = ScreenUtils.get_monitors()
            if monitor_index >= len(monitors):
                return CaptureResult(None, None, False, f"Monitor {monitor_index} not found")

            monitor = monitors[monitor_index]
            monitor_rect = Rectangle(monitor.x, monitor.y, monitor.width, monitor.height)

            # Capture monitor
            image = self._capture_screen_area(monitor_rect, opts)

            capture_time = time.time() - start_time

            # Save to file if requested
            file_path = None
            if opts.save_to_file and image:
                file_path = self._save_image(image, opts)

            result = CaptureResult(
                image=image,
                rectangle=monitor_rect,
                success=image is not None,
                capture_time=capture_time,
                file_path=file_path
            )

            if not result.success:
                result.error_message = "Failed to capture monitor"

            return result

        except Exception as e:
            logger.error(f"Monitor capture failed: {e}")
            return CaptureResult(None, None, False, str(e))

        finally:
            with self._lock:
                self._capture_active = False

    def capture_area_interactive(self,
                                on_capture_complete: Optional[Callable[[CaptureResult], None]] = None,
                                options: Optional[CaptureOptions] = None) -> bool:
        """Capture screen area with interactive selection.

        Args:
            on_capture_complete: Callback when capture is complete
            options: Capture options

        Returns:
            bool: True if selection started successfully
        """
        with self._lock:
            if self._capture_active:
                logger.warning("Capture already in progress")
                return False

            self._capture_active = True

        def on_selection_complete(result: SelectionResult):
            try:
                if result.cancelled or not result.rectangle:
                    capture_result = CaptureResult(
                        None, None, False, "Selection cancelled"
                    )
                else:
                    # Capture the selected area
                    opts = options or self.default_options
                    capture_result = self._capture_selected_area(result.rectangle, opts)

                if on_capture_complete:
                    on_capture_complete(capture_result)

            except Exception as e:
                logger.error(f"Error in capture completion: {e}")
                if on_capture_complete:
                    on_capture_complete(CaptureResult(None, None, False, str(e)))

            finally:
                with self._lock:
                    self._capture_active = False

        # Start selection
        return start_screen_selection(on_selection_complete)

    def capture_area(self, rectangle: Rectangle,
                    options: Optional[CaptureOptions] = None) -> CaptureResult:
        """Capture a specific screen area.

        Args:
            rectangle: Area to capture
            options: Capture options

        Returns:
            CaptureResult: Capture result
        """
        with self._lock:
            if self._capture_active:
                return CaptureResult(None, None, False, "Capture already in progress")

            self._capture_active = True

        try:
            opts = options or self.default_options
            return self._capture_selected_area(rectangle, opts)

        except Exception as e:
            logger.error(f"Area capture failed: {e}")
            return CaptureResult(None, None, False, str(e))

        finally:
            with self._lock:
                self._capture_active = False

    def _capture_selected_area(self, rectangle: Rectangle,
                              options: CaptureOptions) -> CaptureResult:
        """Capture a selected screen area.

        Args:
            rectangle: Area to capture
            options: Capture options

        Returns:
            CaptureResult: Capture result
        """
        start_time = time.time()

        try:
            # Clamp rectangle to screen bounds
            logger.debug(f"Original rectangle: {rectangle}")
            clamped_rect = ScreenUtils.clamp_rectangle_to_screen(rectangle)
            logger.debug(f"Clamped rectangle: {clamped_rect}")

            if clamped_rect.width <= 0 or clamped_rect.height <= 0:
                logger.error(f"Invalid capture area after clamping: width={clamped_rect.width}, height={clamped_rect.height}")
                return CaptureResult(None, None, False, "Invalid capture area")

            # Capture the area
            image = self._capture_screen_area(clamped_rect, options)

            capture_time = time.time() - start_time

            # Save to file if requested
            file_path = None
            if options.save_to_file and image:
                file_path = self._save_image(image, options)

            result = CaptureResult(
                image=image,
                rectangle=clamped_rect,
                success=image is not None,
                capture_time=capture_time,
                file_path=file_path
            )

            if not result.success:
                result.error_message = "Failed to capture area"

            return result

        except Exception as e:
            logger.error(f"Selected area capture failed: {e}")
            return CaptureResult(None, None, False, str(e))

    def _capture_screen_area(self, rectangle: Rectangle,
                           options: CaptureOptions) -> Optional[Image.Image]:
        """Capture a screen area using PIL.

        Args:
            rectangle: Area to capture
            options: Capture options

        Returns:
            Optional[Image.Image]: Captured image or None
        """
        try:
            # Convert rectangle to PIL bbox format (left, top, right, bottom)
            bbox = (
                rectangle.x,
                rectangle.y,
                rectangle.right,
                rectangle.bottom
            )
            logger.debug(f"Screen capture bbox: {bbox}")

            # Capture screen
            image = ImageGrab.grab(bbox=bbox, include_layered_windows=True)
            logger.debug(f"ImageGrab result: {image}")

            if image is None:
                logger.error("PIL returned None image")
                return None

            # Apply scaling if needed
            if options.scale_factor != 1.0:
                new_width = int(image.width * options.scale_factor)
                new_height = int(image.height * options.scale_factor)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            logger.debug(f"Captured image: {image.size}, mode: {image.mode}")
            return image

        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
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
            if not options.output_path:
                # Generate default path
                timestamp = int(time.time())
                options.output_path = f"capture_{timestamp}.{options.format.lower()}"

            output_path = Path(options.output_path)

            # Ensure directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Save image
            if options.format.upper() == "JPEG":
                image.save(output_path, options.format.upper(), quality=options.quality)
            else:
                image.save(output_path, options.format.upper())

            logger.info(f"Image saved to: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Failed to save image: {e}")
            return None

    def get_supported_formats(self) -> List[str]:
        """Get supported image formats.

        Returns:
            List[str]: List of supported formats
        """
        return ["PNG", "JPEG", "BMP", "TIFF", "WEBP"]

    def get_monitor_info(self) -> List[Dict[str, Any]]:
        """Get information about available monitors.

        Returns:
            List[Dict[str, Any]]: Monitor information
        """
        monitors = ScreenUtils.get_monitors()
        return [
            {
                "index": i,
                "x": m.x,
                "y": m.y,
                "width": m.width,
                "height": m.height,
                "is_primary": m.is_primary,
                "name": m.name,
                "scale_factor": m.scale_factor
            }
            for i, m in enumerate(monitors)
        ]

    def is_capture_active(self) -> bool:
        """Check if capture is currently active.

        Returns:
            bool: True if capture is active
        """
        with self._lock:
            return self._capture_active

    def cancel_capture(self):
        """Cancel current capture operation."""
        with self._lock:
            self._capture_active = False
            logger.info("Capture cancelled")

    def get_capture_statistics(self) -> Dict[str, Any]:
        """Get capture service statistics.

        Returns:
            Dict[str, Any]: Statistics
        """
        return {
            "pil_available": PIL_AVAILABLE,
            "capture_active": self.is_capture_active(),
            "supported_formats": self.get_supported_formats(),
            "monitor_count": len(ScreenUtils.get_monitors()),
            "default_options": {
                "format": self.default_options.format,
                "quality": self.default_options.quality,
                "scale_factor": self.default_options.scale_factor
            }
        }

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


def capture_full_screen(options: Optional[CaptureOptions] = None) -> CaptureResult:
    """Capture the full screen.

    Args:
        options: Capture options

    Returns:
        CaptureResult: Capture result
    """
    return get_capture_service().capture_full_screen(options)


def capture_monitor(monitor_index: int = 0,
                   options: Optional[CaptureOptions] = None) -> CaptureResult:
    """Capture a specific monitor.

    Args:
        monitor_index: Monitor index
        options: Capture options

    Returns:
        CaptureResult: Capture result
    """
    return get_capture_service().capture_monitor(monitor_index, options)


def capture_area_interactive(on_complete: Optional[Callable[[CaptureResult], None]] = None,
                           options: Optional[CaptureOptions] = None) -> bool:
    """Capture screen area with interactive selection.

    Args:
        on_complete: Completion callback
        options: Capture options

    Returns:
        bool: True if selection started
    """
    return get_capture_service().capture_area_interactive(on_complete, options)


def capture_area(rectangle: Rectangle,
                options: Optional[CaptureOptions] = None) -> CaptureResult:
    """Capture a specific screen area.

    Args:
        rectangle: Area to capture
        options: Capture options

    Returns:
        CaptureResult: Capture result
    """
    return get_capture_service().capture_area(rectangle, options)