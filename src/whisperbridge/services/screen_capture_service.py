"""
Screen capture service for WhisperBridge.

This module provides comprehensive screen capture functionality
including area selection, image capture, and processing.
"""

import threading
import time
from dataclasses import dataclass
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
        if not QT_AVAILABLE:
            return ScreenUtils.clamp_rectangle_to_screen(rect)

        qgui_app_cls = QGuiApplication
        if qgui_app_cls is None or self._get_qt_gui_app() is None:
            return ScreenUtils.clamp_rectangle_to_screen(rect)

        screens = list(qgui_app_cls.screens())
        if not screens:
            return Rectangle(rect.x, rect.y, 0, 0)

        geometries = [screen.geometry() for screen in screens]

        min_x = min(geometry.x() for geometry in geometries)
        min_y = min(geometry.y() for geometry in geometries)
        max_x = max(geometry.x() + geometry.width() for geometry in geometries)
        max_y = max(geometry.y() + geometry.height() for geometry in geometries)

        qt_bounds = Rectangle(min_x, min_y, max_x - min_x, max_y - min_y)
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

            qgui_app_cls = QGuiApplication
            qrect_cls = QRect
            qimage_cls = QImage
            qpainter_cls = QPainter
            qt_ns = Qt
            pil_image_module = Image

            if (
                qgui_app_cls is None
                or qrect_cls is None
                or qimage_cls is None
                or qpainter_cls is None
                or qt_ns is None
                or pil_image_module is None
            ):
                logger.error("Qt/PIL runtime objects are unavailable for screen capture")
                return None

            if self._get_qt_gui_app() is None:
                logger.error("QGuiApplication instance is not available")
                return None

            target = qrect_cls(rectangle.x, rectangle.y, rectangle.width, rectangle.height)
            logger.debug(
                "Qt capture target QRect: "
                f"({target.x()}, {target.y()}, {target.width()}, {target.height()})"
            )

            screens = list(qgui_app_cls.screens())
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
