import weakref
from typing import Callable, Union

import qtawesome as qta
from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


from .base_window import BaseWindow


class MiniBarOverlay(QWidget, BaseWindow):
    """
    Detachable mini companion window for the OverlayWindow.

    - Frameless, always-on-top.
    - Small fixed height, minimal width.
    - Simple layout: "Translator" title + expand button.
    - Draggable by clicking anywhere on its surface.
    """

    def __init__(self, owner_overlay: QWidget, on_expand: Callable[[], None]):
        super().__init__()
        self._on_expand: Callable[[], None] = on_expand
        # Keep a weak reference to the owning overlay; also close when owner is destroyed
        self._owner_ref = weakref.ref(owner_overlay)
        try:
            owner_overlay.destroyed.connect(self._on_owner_destroyed)
        except Exception:
            pass

        # Frameless, always-on-top
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("MiniBarOverlay")

        # Dimensions
        self.setFixedHeight(28)
        self.setMinimumWidth(190)

        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 4, 0)
        layout.setSpacing(2)

        # Title (initialized from owner if available, no hardcoded text)
        self.title_label = QLabel(self)
        self.title_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        try:
            getter = getattr(owner_overlay, "get_title", None)
            if callable(getter):
                title = getter()
                try:
                    # Ensure a string is passed to setText
                    self.title_label.setText(title if isinstance(title, str) else str(title))
                except Exception:
                    pass
        except Exception:
            pass
        layout.addWidget(self.title_label)

        # Spacer-like stretch is implicit with layout spacing; keep compact

        # Expand button (top)
        self.expand_btn = QPushButton(self)
        self.expand_btn.setFixedSize(QSize(22, 22))
        try:
            self.expand_btn.setIcon(qta.icon("fa5s.expand-alt", color="black"))
        except Exception:
            try:
                self.expand_btn.setIcon(qta.icon("fa5s.chevron-up", color="black"))
            except Exception:
                self.expand_btn.setText("Expand")
        self.expand_btn.clicked.connect(self._handle_expand_clicked)
        layout.addWidget(self.expand_btn)

        # Close button(top)
        self.close_btn = QPushButton(self)
        self.close_btn.setObjectName("closeBtnMini")
        self.close_btn.setFixedSize(QSize(22, 22))
        try:
            self.close_btn.setIcon(qta.icon("fa5s.times", color="black"))
        except Exception:
            self.close_btn.setText("X")
        self.close_btn.clicked.connect(self._handle_close_clicked)
        layout.addWidget(self.close_btn)

        # Styling consistent with overlay (light background, subtle border)
        self.setStyleSheet(
            """
            MiniBarOverlay {
                background-color: #ffffff;
                border: 1px solid #f5f5f5;
            }
            QLabel {
                color: #111111;
                border: none;
            }
            QPushButton {
                color: #111111;
                padding: 3px 6px;
                border: none;
                border-radius: 3px;
                background-color: #f0f0f0;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
            }
            QPushButton#closeBtnMini {
                color: #111111;
                padding: 3px 6px;
                border-radius: 3px;
                background-color: #fff;
            }
            QPushButton#closeBtnMini:hover {
                background-color: #ff6b6b;
            }
            """
        )

        # Dragging support (no manual resize)
        self._dragging = False
        self._drag_offset = QPoint(0, 0)
        self.setMouseTracking(True)

    # --- Public API ---

    def show_at(self, pos: Union[QPoint, tuple]):
        """Show the minibar at a specific position (top-left)."""
        try:
            if isinstance(pos, QPoint):
                x, y = pos.x(), pos.y()
            else:
                x, y = pos
            self.move(x, y)
        except Exception:
            pass
        self.show()
        self.raise_()
        self.activateWindow()

    def set_title(self, text: str) -> None:
        """Update the minibar title label."""
        try:
            self.title_label.setText(text)
        except Exception:
            pass

    # --- Internal handlers ---

    def _handle_expand_clicked(self):
        """Invoke the provided expand callback."""
        try:
            if callable(self._on_expand):
                self._on_expand()
        except Exception:
            pass

    def _handle_close_clicked(self):
        """Handle close button click: close minibar and hide/dismiss owner."""
        try:
            self.close()
            owner = self._owner_ref()
            if owner:
                hide = getattr(owner, "hide_overlay", None)
                dismiss = getattr(owner, "dismiss", None)
                if callable(hide):
                    hide()
                elif callable(dismiss):
                    dismiss()
                else:
                    try:
                        owner.hide()
                    except Exception:
                        pass
        except Exception:
            pass

    def _on_owner_destroyed(self, *args, **kwargs):
        """Close minibar when its owner overlay is destroyed."""
        try:
            self.close()
        except Exception:
            pass

    # --- Mouse events for dragging ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to expand the overlay."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._handle_expand_clicked()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    # --- Qt lifecycle ---

    def closeEvent(self, event):
        """Accept close to avoid BaseWindow.closeEvent ignore behavior."""
        event.accept()

    def dismiss(self):
        """Dismiss the mini bar by closing it."""
        self.close()
