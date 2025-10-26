import sys
import os

# Add src to path for direct execution
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from typing import Optional, Union

try:
    import qtawesome as qta
except Exception:  # pragma: no cover - optional
    qta = None  # type: ignore

from PySide6.QtCore import Qt, QPoint, QTimer, QSize
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import QLabel, QTextEdit, QHBoxLayout, QPushButton, QSizePolicy, QApplication

from whisperbridge.ui_qt.styled_overlay_base import StyledOverlayWindow


class SimpleTextWindow(StyledOverlayWindow):
    """Single-field overlay window with resize, minibar, and unified styling."""

    def __init__(self, title: str = "Text"):
        super().__init__(title=title or "Text")

        # Label
        self.text_label = QLabel("Text:", self)
        self.text_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.content_layout.addWidget(self.text_label)

        # Text area
        self.text_edit = QTextEdit(self)
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setPlaceholderText("Enter text...")
        self.text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        try:
            self.text_edit.setStyleSheet("QTextEdit { color: #111111; background-color: #ffffff; }")
        except Exception:
            pass
        self.content_layout.addWidget(self.text_edit)

        # Buttons row (right-aligned): Clear, Copy
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self.clear_btn = QPushButton("", self)
        self.clear_btn.setFixedHeight(28)
        self.clear_btn.setFixedWidth(40)
        if qta:
            try:
                self.clear_btn.setIcon(qta.icon("fa5s.eraser", color="black"))
            except Exception:
                self.clear_btn.setText("Clear")
        else:
            self.clear_btn.setText("Clear")
        self.clear_btn.setIconSize(QSize(16, 16))
        self.clear_btn.setToolTip("Clear text")
        self.clear_btn.clicked.connect(self._clear_text)
        btn_row.addWidget(self.clear_btn)

        self.copy_btn = QPushButton("", self)
        self.copy_btn.setFixedHeight(28)
        self.copy_btn.setFixedWidth(40)
        if qta:
            try:
                self.copy_btn.setIcon(qta.icon("fa5.copy", color="black"))
            except Exception:
                self.copy_btn.setText("Copy")
        else:
            self.copy_btn.setText("Copy")
        try:
            self.copy_btn.setIconSize(QSize(16, 16))
        except Exception:
            pass
        self.copy_btn.setToolTip("Copy text to clipboard")
        self.copy_btn.clicked.connect(self._copy_text)
        btn_row.addWidget(self.copy_btn)

        self.content_layout.addLayout(btn_row)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
            event.accept()
            return
        super().keyPressEvent(event)

    # Public API
    def set_text(self, text: str) -> None:
        self.text_edit.setPlainText(text or "")

    def get_text(self) -> str:
        return self.text_edit.toPlainText()

    def show_with_text(self, text: str = "", position: Optional[Union[QPoint, tuple[int, int]]] = None) -> None:
        self.set_text(text)
        self.show_window(position=position)

    # Internal handlers
    def _clear_text(self) -> None:
        try:
            self.text_edit.clear()
        except Exception:
            pass

    def _copy_text(self) -> None:
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.get_text())
            prev_icon = self.copy_btn.icon()
            prev_text = self.copy_btn.text()
            if qta:
                try:
                    self.copy_btn.setIcon(qta.icon("fa5s.check", color="green"))
                except Exception:
                    pass
            self.copy_btn.setText("")
            QTimer.singleShot(900, lambda: (self.copy_btn.setIcon(prev_icon), self.copy_btn.setText(prev_text)))
        except Exception:
            pass


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("SimpleTextWindow Test")

    # Create and show the test window
    window = SimpleTextWindow(title="Direct Test")
    window.set_text("This is a test run directly from the file.\n\n"
                    "Features:\n"
                    "- Drag the window by clicking anywhere\n"
                    "- Resize by dragging edges/corners\n"
                    "- Double-click to collapse to minibar\n"
                    "- Use top-right buttons to collapse/close\n"
                    "- Press Escape to dismiss\n"
                    "- Clear/Copy buttons work on the text")

    # Show at a reasonable position
    window.show_with_text(position=(200, 200))

    print("Test window shown. Close it manually.")
    sys.exit(app.exec())