from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from .base_window import BaseWindow


class SelectionOverlayQt(QWidget, BaseWindow):
    selectionCompleted = Signal(QRect)
    selectionCanceled = Signal()

    SIZE_TEXT_MARGIN = 8

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
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # Don't steal focus from other apps

        # Cover the whole virtual desktop so selection works on all monitors
        # (including monitors with negative coordinates in the virtual space).
        screen = QGuiApplication.primaryScreen() or QApplication.primaryScreen()
        self.virtual_geometry = screen.virtualGeometry() if screen else QRect(0, 0, 0, 0)
        self.setGeometry(self.virtual_geometry)

        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False

        # Colors
        self.mask_color = QColor(0, 0, 0, 128)  # Semi-transparent black
        self.border_color = QColor("#007ACC")  # Selection color
        self.text_color = QColor(255, 255, 255)  # White text

    def start(self):
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.show()
        self.raise_()
        self.activateWindow()
        self.grabMouse()
        self.grabKeyboard()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw semi-transparent mask
        painter.fillRect(self.rect(), self.mask_color)

        if self.is_selecting and self.selection_start and self.selection_end:
            # Calculate selection rectangle
            rect = QRect(self.selection_start, self.selection_end).normalized()

            # Clear the selection area
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(rect, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # Draw border
            pen = QPen(self.border_color, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)

            # Draw size indicator if rectangle is big enough
            if rect.width() > 50 and rect.height() > 20:
                size_text = f"{rect.width()} × {rect.height()}"
                font = QFont()
                font.setPointSize(12)
                painter.setFont(font)
                painter.setPen(self.text_color)

                text_rect = painter.boundingRect(self.rect(), Qt.AlignLeft | Qt.AlignTop, size_text)
                label_rect = self._select_size_label_rect(rect, text_rect)
                if label_rect is not None:
                    painter.drawText(label_rect, Qt.AlignLeft | Qt.AlignTop, size_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selection_start = event.pos()
            self.selection_end = event.pos()
            self.is_selecting = True
            self.update()
        elif event.button() == Qt.RightButton:
            self.selectionCanceled.emit()
            self.close()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.selection_end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.selection_end = event.pos()
            self.is_selecting = False
            rect = QRect(self.selection_start, self.selection_end).normalized()
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
        if event.key() == Qt.Key_Escape:
            self.selectionCanceled.emit()
            self.close()

    def dismiss(self):
        """Dismiss the selection overlay by closing it."""
        self.close()

    def closeEvent(self, event):
        """Standardized closeEvent that triggers dismiss()."""
        self.dismiss()
        event.accept()  # For selection overlay, closing is normal
