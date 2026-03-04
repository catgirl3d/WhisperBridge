"""
Screen capture service for WhisperBridge.

This module provides comprehensive screen capture functionality
including area selection, image capture, and processing.
"""

import threading
import time
from dataclasses import dataclass
import math
from typing import Any, Optional, cast

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None

try:
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter

    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False
    QRect = None
    Qt = None
    QGuiApplication = None
    QImage = None
    QPainter = None

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

    image: Optional["Image.Image"]
    rectangle: Optional[Rectangle]
    success: bool
    error_message: str = ""
    capture_time: float = 0.0


@dataclass
class CaptureOptions:
    """Options for screen capture."""

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

    @staticmethod
    def _get_qt_gui_app():
        """Return active QGuiApplication instance (isolated for testability)."""
        if not QT_AVAILABLE:
            return None
        return QGuiApplication.instance()

    def _get_qt_virtual_bounds(self) -> Optional[Rectangle]:
        """Return virtual desktop bounds from active Qt screens when available."""
        if not QT_AVAILABLE:
            return None

        qt_app = self._get_qt_gui_app()
        if qt_app is None:
            return None

        screens = list(qt_app.screens())
        if not screens:
            return None

        geometries = [screen.geometry() for screen in screens]
        min_x = min(geometry.x() for geometry in geometries)
        min_y = min(geometry.y() for geometry in geometries)
        max_x = max(geometry.x() + geometry.width() for geometry in geometries)
        max_y = max(geometry.y() + geometry.height() for geometry in geometries)

        return Rectangle(min_x, min_y, max_x - min_x, max_y - min_y)

    def capture_area(
        self, rectangle: Rectangle, options: Optional[CaptureOptions] = None
    ) -> CaptureResult:
        """Capture a specific screen area.

        Args:
            rectangle: Area to capture in Qt logical virtual-desktop coordinates.
                Coordinates must be in the same space as ``QScreen.geometry()``.
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

    def capture_virtual_desktop(self, options: Optional[CaptureOptions] = None) -> CaptureResult:
        """Capture the full virtual desktop in one shot.

        Intended for freeze-frame workflows where selection should happen on a
        static screenshot captured at hotkey press time.
        """
        try:
            virtual_bounds = self._get_qt_virtual_bounds() or ScreenUtils.get_screen_capture_bounds()
            if virtual_bounds.width <= 0 or virtual_bounds.height <= 0:
                logger.error(f"Invalid virtual bounds for capture: {virtual_bounds}")
                return CaptureResult(
                    image=None,
                    rectangle=None,
                    success=False,
                    error_message="Invalid virtual screen bounds",
                )

            logger.info(
                "Capturing virtual desktop: "
                f"x={virtual_bounds.x}, y={virtual_bounds.y}, "
                f"w={virtual_bounds.width}, h={virtual_bounds.height}"
            )
            return self.capture_area(virtual_bounds, options)
        except Exception as e:
            logger.error(f"Virtual desktop capture failed: {e}")
            logger.debug("Virtual desktop capture error details", exc_info=True)
            return CaptureResult(None, None, False, str(e))

    def crop_captured_image(
        self,
        captured_image: Optional["Image.Image"],
        captured_rectangle: Optional[Rectangle],
        target_rectangle: Rectangle,
    ) -> CaptureResult:
        """Crop a pre-captured image using logical virtual-desktop coordinates."""
        start_time = time.time()

        if captured_image is None or captured_rectangle is None:
            return CaptureResult(
                image=None,
                rectangle=None,
                success=False,
                error_message="Missing captured image or source rectangle",
            )

        try:
            clipped_target = target_rectangle.clip_to_bounds(captured_rectangle)
            if clipped_target.width <= 0 or clipped_target.height <= 0:
                return CaptureResult(
                    image=None,
                    rectangle=None,
                    success=False,
                    error_message="Invalid crop area",
                )

            crop_box = self._build_pixel_crop_box(
                captured_image=captured_image,
                captured_rectangle=captured_rectangle,
                clipped_target=clipped_target,
            )
            if crop_box is None:
                return CaptureResult(
                    image=None,
                    rectangle=None,
                    success=False,
                    error_message="Invalid crop area after DPI scaling",
                )

            crop_left, crop_top, crop_right, crop_bottom = crop_box

            cropped_image = captured_image.crop((crop_left, crop_top, crop_right, crop_bottom))
            return CaptureResult(
                image=cropped_image,
                rectangle=clipped_target,
                success=True,
                capture_time=time.time() - start_time,
            )
        except Exception as e:
            logger.error(f"Failed to crop captured image: {e}")
            logger.debug("Crop captured image error details", exc_info=True)
            return CaptureResult(
                image=None,
                rectangle=None,
                success=False,
                error_message=str(e),
                capture_time=time.time() - start_time,
            )

    @staticmethod
    def _build_pixel_crop_box(
        captured_image: "Image.Image",
        captured_rectangle: Rectangle,
        clipped_target: Rectangle,
    ) -> Optional[tuple[int, int, int, int]]:
        """Translate logical crop rectangle into image pixel coordinates.

        Captured image dimensions can differ from logical capture bounds on mixed-DPI
        systems, so we map coordinates by per-axis ratios.
        """
        logical_width = captured_rectangle.width
        logical_height = captured_rectangle.height
        if logical_width <= 0 or logical_height <= 0:
            logger.error(
                "Cannot crop captured image: invalid source logical bounds "
                f"{captured_rectangle}"
            )
            return None

        image_width, image_height = captured_image.size
        if image_width <= 0 or image_height <= 0:
            logger.error(
                "Cannot crop captured image: invalid source image size "
                f"{captured_image.size}"
            )
            return None

        ratio_x = image_width / logical_width
        ratio_y = image_height / logical_height
        if not math.isfinite(ratio_x) or not math.isfinite(ratio_y) or ratio_x <= 0 or ratio_y <= 0:
            logger.error(
                "Cannot crop captured image: invalid logical→pixel ratios "
                f"ratio_x={ratio_x}, ratio_y={ratio_y}"
            )
            return None

        if abs(ratio_x - 1.0) > 0.01 or abs(ratio_y - 1.0) > 0.01:
            logger.debug(
                "Applying HiDPI crop ratios for frozen frame: "
                f"ratio_x={ratio_x:.4f}, ratio_y={ratio_y:.4f}, "
                f"logical_bounds={captured_rectangle}, image_size={captured_image.size}"
            )

        logical_left = clipped_target.x - captured_rectangle.x
        logical_top = clipped_target.y - captured_rectangle.y
        logical_right = logical_left + clipped_target.width
        logical_bottom = logical_top + clipped_target.height

        # Use floor for origin and ceil for far edge to avoid losing edge pixels
        # on fractional DPR mappings (e.g. 1.25x / 1.5x / 1.75x).
        pixel_left = int(math.floor(logical_left * ratio_x))
        pixel_top = int(math.floor(logical_top * ratio_y))
        pixel_right = int(math.ceil(logical_right * ratio_x))
        pixel_bottom = int(math.ceil(logical_bottom * ratio_y))

        pixel_left = max(0, min(image_width, pixel_left))
        pixel_top = max(0, min(image_height, pixel_top))
        pixel_right = max(0, min(image_width, pixel_right))
        pixel_bottom = max(0, min(image_height, pixel_bottom))

        if pixel_right <= pixel_left or pixel_bottom <= pixel_top:
            logger.warning(
                "Mapped frozen-frame crop is empty after scaling/clamp: "
                f"box=({pixel_left}, {pixel_top}, {pixel_right}, {pixel_bottom}), "
                f"logical_target={clipped_target}, source_logical={captured_rectangle}, "
                f"source_image_size={captured_image.size}"
            )
            return None

        return pixel_left, pixel_top, pixel_right, pixel_bottom

    def _capture_selected_area(
        self, rectangle: Rectangle, options: CaptureOptions
    ) -> CaptureResult:
        """Capture a selected screen area.

        Args:
            rectangle: Area to capture in Qt logical virtual-desktop coordinates
            options: Capture options

        Returns:
            CaptureResult: Capture result
        """
        start_time = time.time()
        logger.info(f"Starting selected area capture: rectangle={rectangle}")
        logger.debug(f"Capture options: scale_factor={options.scale_factor}")

        try:
            # Clamp rectangle using Qt screen geometries to preserve logical-space
            # consistency with the Qt capture path on mixed-DPI/multi-monitor setups.
            logger.debug(f"Original rectangle: {rectangle}")
            clamped_rect = self._clamp_rectangle_to_qt_screens(rectangle)
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

    def _clamp_rectangle_to_qt_screens(self, rect: Rectangle) -> Rectangle:
        """Clamp a rectangle to Qt logical virtual-screen bounds.

        Uses ``QScreen.geometry()`` from the current Qt runtime as the authoritative
        coordinate source. Falls back to ``ScreenUtils`` only when Qt runtime data
        is unavailable.
        """
        qt_bounds = self._get_qt_virtual_bounds()
        if qt_bounds is None:
            return ScreenUtils.clamp_rectangle_to_screen(rect)
        return rect.clip_to_bounds(qt_bounds)

    def _capture_screen_area(
        self, rectangle: Rectangle, options: CaptureOptions
    ) -> Optional["Image.Image"]:
        """Capture a screen area using Qt multi-monitor aware APIs.

        Args:
            rectangle: Area to capture
            options: Capture options

        Returns:
            Optional[Image.Image]: Captured image or None
        """
        logger.debug(f"Starting screen capture: rectangle={rectangle}, options={options}")
        try:
            if not QT_AVAILABLE:
                logger.error("Qt is required for robust multi-monitor capture")
                return None

            qrect_cls = QRect
            qimage_cls = QImage
            qpainter_cls = QPainter
            qt_ns = Qt
            pil_image_module = Image
            qt_app = self._get_qt_gui_app()

            if (
                qt_app is None
                or qrect_cls is None
                or qimage_cls is None
                or qpainter_cls is None
                or qt_ns is None
                or pil_image_module is None
            ):
                logger.error("Qt/PIL runtime objects are unavailable for screen capture")
                return None

            target = qrect_cls(rectangle.x, rectangle.y, rectangle.width, rectangle.height)
            logger.debug(
                "Qt capture target QRect: "
                f"({target.x()}, {target.y()}, {target.width()}, {target.height()})"
            )

            screens = list(qt_app.screens())
            if not screens:
                logger.error("No screens available for capture")
                return None

            # Compose result from all intersecting screens to support virtual desktop
            # coordinates (including negative offsets and mixed-DPI setups).
            argb32_format = getattr(qimage_cls, "Format_ARGB32", None)
            if argb32_format is None and hasattr(qimage_cls, "Format"):
                argb32_format = qimage_cls.Format.Format_ARGB32
            if argb32_format is None:
                logger.error("QImage ARGB32 format is unavailable")
                return None

            transparent_color = getattr(qt_ns, "transparent", None)
            if transparent_color is None and hasattr(qt_ns, "GlobalColor"):
                transparent_color = qt_ns.GlobalColor.transparent
            if transparent_color is None:
                logger.error("Qt transparent color constant is unavailable")
                return None

            composed = qimage_cls(target.size(), argb32_format)
            composed.fill(transparent_color)
            painter = qpainter_cls(composed)

            drawn = False
            try:
                for screen in screens:
                    screen_geom = screen.geometry()
                    intersection = screen_geom.intersected(target)
                    if intersection.isEmpty():
                        continue

                    pixmap = screen.grabWindow(
                        0,
                        intersection.x() - screen_geom.x(),
                        intersection.y() - screen_geom.y(),
                        intersection.width(),
                        intersection.height(),
                    )
                    if pixmap.isNull():
                        continue

                    dst_x = intersection.x() - target.x()
                    dst_y = intersection.y() - target.y()

                    # Draw into an explicit logical destination size.
                    # This normalizes source pixmaps from mixed-DPI screens,
                    # preventing oversized fragments from high-DPI monitors.
                    painter.drawPixmap(
                        dst_x,
                        dst_y,
                        intersection.width(),
                        intersection.height(),
                        pixmap,
                    )
                    drawn = True
            finally:
                painter.end()

            if not drawn:
                logger.error("Qt screen capture failed: no pixels were captured")
                return None

            width = composed.width()
            height = composed.height()
            ptr = composed.bits()
            # PySide can return either sip.voidptr (with setsize) or memoryview.
            # Handle both forms safely.
            if hasattr(ptr, "setsize"):
                cast(Any, ptr).setsize(composed.sizeInBytes())
            raw = bytes(ptr)
            image = pil_image_module.frombytes("RGBA", (width, height), raw, "raw", "BGRA")
            image = image.convert("RGB")

            logger.info(
                f"Screen captured successfully (Qt): size={image.size}, mode={image.mode}"
            )

            # Apply scaling if needed
            scale_factor = options.scale_factor
            if scale_factor <= 0:
                logger.warning(f"Invalid scale_factor={scale_factor}; using 1.0")
                scale_factor = 1.0

            if scale_factor != 1.0:
                original_size = image.size
                new_width = max(1, int(image.width * scale_factor))
                new_height = max(1, int(image.height * scale_factor))

                resampling = getattr(pil_image_module, "Resampling", None)
                resample_filter = resampling.LANCZOS if resampling is not None else pil_image_module.LANCZOS
                image = image.resize((new_width, new_height), resample_filter)
                logger.info(
                    f"Image scaled: {original_size} -> {image.size}, factor={scale_factor}"
                )

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
