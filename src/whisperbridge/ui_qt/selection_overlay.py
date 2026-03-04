from typing import cast

from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget
from loguru import logger

from .base_window import BaseWindow


class SelectionOverlayQt(QWidget, BaseWindow):
    selectionCompleted = Signal(QRect)
    selectionCanceled = Signal()

    SIZE_TEXT_MARGIN = 8

    @staticmethod
    def _event_pos_as_qpoint(event) -> QPoint:
        """Return event position as QPoint across Qt mouse-event API variants."""
        position_method = getattr(event, "position", None)
        if callable(position_method):
            position = position_method()
            to_point_method = getattr(position, "toPoint", None)
            if callable(to_point_method):
                return cast(QPoint, to_point_method())
        return cast(QPoint, event.pos())

    def _build_size_label_candidates(self, selection_rect: QRect, text_rect: QRect):
        """Build candidate label rectangles around selection in priority order.

        Priority order:
        1) top-left, 2) top-right, 3) bottom-left, 4) bottom-right.
        """
        text_w = text_rect.width()
        text_h = text_rect.height()

        top_y = selection_rect.top() - text_h - self.SIZE_TEXT_MARGIN
        bottom_y = selection_rect.bottom() + self.SIZE_TEXT_MARGIN + 1

        left_x = selection_rect.left()
        right_x = selection_rect.right() - text_w + 1

        return [
            QRect(left_x, top_y, text_w, text_h),
            QRect(right_x, top_y, text_w, text_h),
            QRect(left_x, bottom_y, text_w, text_h),
            QRect(right_x, bottom_y, text_w, text_h),
        ]

    def _select_size_label_rect(self, selection_rect: QRect, text_rect: QRect):
        """Pick first valid external label rect or return None."""
        overlay_bounds = self.rect()
        for candidate in self._build_size_label_candidates(selection_rect, text_rect):
            if overlay_bounds.contains(candidate) and not candidate.intersects(selection_rect):
                return candidate
        return None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # Don't steal focus from other apps

        # Cover the whole virtual desktop so selection works on all monitors
        # (including monitors with negative coordinates in the virtual space).
        screen = QGuiApplication.primaryScreen() or QApplication.primaryScreen()
        self.virtual_geometry = screen.virtualGeometry() if screen else QRect(0, 0, 0, 0)
        self.setGeometry(self.virtual_geometry)

        self.selection_start: QPoint | None = None
        self.selection_end: QPoint | None = None
        self.is_selecting = False
        self._frozen_background_pixmap = None
        self._frozen_background_qimage = None
        self._frozen_background_buffer = None

        # Colors
        self.mask_color = QColor(0, 0, 0, 128)  # Semi-transparent black
        self.border_color = QColor("#007ACC")  # Selection color
        self.text_color = QColor(255, 255, 255)  # White text

    @staticmethod
    def _resolve_virtual_geometry() -> QRect:
        """Resolve current virtual desktop geometry from Qt screens."""
        screen = QGuiApplication.primaryScreen() or QApplication.primaryScreen()
        return screen.virtualGeometry() if screen else QRect(0, 0, 0, 0)

    @staticmethod
    def _get_qimage_rgba8888_format():
        """Resolve RGBA8888 format constant across PySide6 variants."""
        fmt = getattr(QImage, "Format_RGBA8888", None)
        if fmt is None:
            enum_container = getattr(QImage, "Format", None)
            if enum_container is not None:
                fmt = getattr(enum_container, "Format_RGBA8888", None)
        return fmt

    def _clear_frozen_background(self):
        self._frozen_background_pixmap = None
        self._frozen_background_qimage = None
        self._frozen_background_buffer = None

    def _fit_frozen_image_to_overlay(self, frozen_image):
        """Downscale frozen image to overlay size to reduce UI memory/paint cost."""
        size = getattr(frozen_image, "size", None)
        if not isinstance(size, tuple) or len(size) != 2:
            return frozen_image

        source_width, source_height = size
        target_width = max(1, int(self.virtual_geometry.width()))
        target_height = max(1, int(self.virtual_geometry.height()))

        if source_width <= 0 or source_height <= 0:
            return frozen_image

        if source_width <= target_width and source_height <= target_height:
            return frozen_image

        scale = min(target_width / source_width, target_height / source_height)
        resized_width = max(1, int(round(source_width * scale)))
        resized_height = max(1, int(round(source_height * scale)))

        try:
            resampling = getattr(Image, "Resampling", None)
            filter_mode = (
                resampling.BILINEAR
                if resampling is not None
                else getattr(Image, "BILINEAR", 2)
            )
            logger.debug(
                "Downscaling frozen background for overlay: "
                f"{source_width}x{source_height} -> {resized_width}x{resized_height}"
            )
            return frozen_image.resize((resized_width, resized_height), filter_mode)
        except Exception:
            return frozen_image

    def _set_frozen_background(self, frozen_image):
        """Set frozen screenshot as overlay background.

        Args:
            frozen_image: PIL image instance or None.
        """
        self._clear_frozen_background()
        if frozen_image is None:
            return

        try:
            preview_image = self._fit_frozen_image_to_overlay(frozen_image)
            rgba_image = preview_image.convert("RGBA")
            raw_rgba = rgba_image.tobytes("raw", "RGBA")
            qimage_format = self._get_qimage_rgba8888_format()
            if qimage_format is None:
                logger.warning("QImage RGBA8888 format is unavailable; frozen background disabled")
                return

            # Keep backing buffer alive while QImage/QPixmap are used.
            # This avoids an extra deep-copy (qimage.copy()) and reduces peak memory.
            self._frozen_background_buffer = raw_rgba
            qimage = QImage(
                self._frozen_background_buffer,
                rgba_image.width,
                rgba_image.height,
                rgba_image.width * 4,
                qimage_format,
            )
            if qimage.isNull():
                logger.warning("Failed to build QImage for frozen background")
                self._clear_frozen_background()
                return

            self._frozen_background_qimage = qimage
            pixmap = QPixmap.fromImage(qimage)
            if pixmap.isNull():
                logger.warning("Failed to build QPixmap for frozen background")
                self._clear_frozen_background()
                return

            target_size = self.size()
            if target_size.width() > 0 and target_size.height() > 0 and pixmap.size() != target_size:
                pixmap = pixmap.scaled(
                    target_size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )

            self._frozen_background_pixmap = pixmap
        except Exception as e:
            logger.warning(f"Failed to convert frozen capture to QPixmap: {e}")
            logger.debug("Frozen background conversion error details", exc_info=True)
            self._clear_frozen_background()

    def _draw_frozen_background(self, painter: QPainter, clip_rect: QRect | None = None):
        """Draw frozen background without aspect distortion, center-cropped to overlay."""
        pixmap = self._frozen_background_pixmap
        if pixmap is None or pixmap.isNull():
            return

        target_rect = self.rect()
        if not target_rect.isValid() or target_rect.width() <= 0 or target_rect.height() <= 0:
            return

        source_rect = QRect(0, 0, pixmap.width(), pixmap.height())
        if source_rect.width() != target_rect.width() or source_rect.height() != target_rect.height():
            x_offset = max(0, (source_rect.width() - target_rect.width()) // 2)
            y_offset = max(0, (source_rect.height() - target_rect.height()) // 2)
            source_rect = QRect(
                x_offset,
                y_offset,
                min(target_rect.width(), source_rect.width()),
                min(target_rect.height(), source_rect.height()),
            )

        if clip_rect is not None:
            painter.save()
            painter.setClipRect(clip_rect)

        painter.drawPixmap(target_rect, pixmap, source_rect)

        if clip_rect is not None:
            painter.restore()

    def _selection_dirty_rect(self, previous_end: QPoint | None, new_end: QPoint) -> QRect:
        """Return minimal repaint area for selection updates."""
        start_point = self.selection_start
        if start_point is None:
            return self.rect()

        previous_rect = (
            QRect(start_point, previous_end).normalized()
            if previous_end is not None
            else QRect(start_point, start_point)
        )
        new_rect = QRect(start_point, new_end).normalized()
        dirty = previous_rect.united(new_rect).adjusted(-6, -6, 6, 6)
        return dirty.intersected(self.rect())

    def _finalize_overlay_close(self):
        """Release transient resources and clear selection/frozen state."""
        self.is_selecting = False
        self.selection_start = None
        self.selection_end = None
        self._clear_frozen_background()
        try:
            self.releaseMouse()
        except Exception:
            pass
        try:
            self.releaseKeyboard()
        except Exception:
            pass

    def start(self, frozen_image=None, frozen_rect=None):
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False

        if frozen_rect is not None:
            self.virtual_geometry = QRect(
                int(frozen_rect.x),
                int(frozen_rect.y),
                int(frozen_rect.width),
                int(frozen_rect.height),
            )
        else:
            self.virtual_geometry = self._resolve_virtual_geometry()

        self.setGeometry(self.virtual_geometry)
        self._set_frozen_background(frozen_image)

        self.show()
        self.raise_()
        self.activateWindow()
        self.grabMouse()
        self.grabKeyboard()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._frozen_background_pixmap is not None:
            self._draw_frozen_background(painter)

        # Draw semi-transparent mask
        painter.fillRect(self.rect(), self.mask_color)

        start_point = self.selection_start
        end_point = self.selection_end
        if self.is_selecting and start_point is not None and end_point is not None:
            # Calculate selection rectangle
            rect = QRect(start_point, end_point).normalized()

            if self._frozen_background_pixmap is not None:
                self._draw_frozen_background(painter, clip_rect=rect)
            else:
                # Clear the selection area
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                painter.fillRect(rect, Qt.GlobalColor.transparent)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # Draw border
            pen = QPen(self.border_color, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

            # Draw size indicator if rectangle is big enough
            if rect.width() > 50 and rect.height() > 20:
                size_text = f"{rect.width()} × {rect.height()}"
                font = QFont()
                font.setPointSize(12)
                painter.setFont(font)
                painter.setPen(self.text_color)

                text_rect = painter.boundingRect(
                    self.rect(),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                    size_text,
                )
                label_rect = self._select_size_label_rect(rect, text_rect)
                if label_rect is not None:
                    painter.drawText(
                        label_rect,
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                        size_text,
                    )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            event_pos = self._event_pos_as_qpoint(event)
            self.selection_start = event_pos
            self.selection_end = event_pos
            self.is_selecting = True
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self.selectionCanceled.emit()
            self.close()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            previous_end = self.selection_end
            self.selection_end = self._event_pos_as_qpoint(event)
            dirty_rect = self._selection_dirty_rect(previous_end, self.selection_end)
            if dirty_rect.isValid():
                self.update(dirty_rect)
            else:
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.selection_end = self._event_pos_as_qpoint(event)
            self.is_selecting = False
            start_point = self.selection_start
            end_point = self.selection_end
            if start_point is None or end_point is None:
                self.selectionCanceled.emit()
                self.close()
                return

            rect = QRect(start_point, end_point).normalized()
            if rect.width() > 0 and rect.height() > 0:
                # Convert to virtual desktop coordinates
                global_rect = QRect(
                    self.mapToGlobal(rect.topLeft()),
                    self.mapToGlobal(rect.bottomRight()),
                )
                self.selectionCompleted.emit(global_rect)
            else:
                self.selectionCanceled.emit()
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.selectionCanceled.emit()
            self.close()

    def dismiss(self):
        """Dismiss the selection overlay by closing it."""
        self.close()

    def closeEvent(self, event):
        """Release transient resources on close."""
        self._finalize_overlay_close()
        event.accept()  # For selection overlay, closing is normal
