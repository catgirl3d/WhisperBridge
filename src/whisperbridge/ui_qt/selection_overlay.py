from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from .base_window import BaseWindow


class SelectionOverlayQt(QWidget, BaseWindow):
    selectionCompleted = Signal(QRect)
    selectionCanceled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # Don't steal focus from other apps

        # Get virtual desktop geometry using the new PySide6 API
        screen = QApplication.primaryScreen()
        self.virtual_geometry = screen.availableGeometry()
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

                # Position text at bottom-right of selection
                text_rect = painter.boundingRect(rect, Qt.AlignCenter, size_text)
                text_pos = QPoint(rect.right() - text_rect.width() - 5, rect.bottom() - 5)
                painter.drawText(text_pos, size_text)

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
        """Стандартизованный closeEvent, вызывающий dismiss()."""
        self.dismiss()
        event.accept()  # For selection overlay, closing is normal
