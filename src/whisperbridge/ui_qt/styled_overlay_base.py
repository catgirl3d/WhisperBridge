"""
Styled Overlay Base module for creating overlay window components.

Configuration Guidelines:
- All widget metadata should be centralized in CONFIG dictionaries.
- Use consistent naming: {COMPONENT_TYPE}_CONFIG.
- Shared widget factory [`src/whisperbridge/ui_qt/widget_factory.py`](src/whisperbridge/ui_qt/widget_factory.py:1) handles low-level creation.
- Python sets identity/state (objectName, properties); QSS handles visuals.
"""


import sys
import os

# Add src to path for direct execution
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from typing import Callable, Optional, Union

from loguru import logger
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from whisperbridge.ui_qt.base_window import BaseWindow
from ..services.config_service import config_service


# Configuration dictionaries for UI components
WINDOW_CONFIG = {
    'minimum_size': (320, 200),
    'default_size': (540, 500),
    'root_layout_margins': (10, 7, 10, 10),
    'root_layout_spacing': 6,
    'content_layout_spacing': 6,
    'title_font': ("Arial", 11, QFont.Weight.Bold),
    'top_button_padding': {
        'top': 3,
        'right': 4,
        'bottom': 0,
        'left': 2,
    },
}

RESIZE_CONFIG = {
    'margin': 8,
}


class StyledOverlayWindow(QWidget, BaseWindow):
    """
    Base class for lightweight, stylized, frameless overlay windows with:
      - unified close/dismiss behavior (via BaseWindow)
      - drag + edge-resize support
      - minibar collapse/restore support
      - top-right control buttons (collapse/close) + optional settings
      - consistent styling and margins

    Subclasses should:
      - call super().__init__()
      - use self.content_layout to place their specific UI
      - optionally call add_settings_button() to attach a settings button
    """

    def __init__(self, title: str = "Overlay"):
        super().__init__()

        # ----- Window configuration -----
        # Frameless, always-on-top, resizable
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("StyledOverlayWindow")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.setMouseTracking(True)

        # Reasonable defaults, subclasses may adjust
        self.setMinimumSize(*WINDOW_CONFIG['minimum_size'])
        self.resize(*WINDOW_CONFIG['default_size'])

        # ----- Layout skeleton -----
        # Root vertical layout with default margins/spacings
        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(*WINDOW_CONFIG['root_layout_margins'])
        self._root_layout.setSpacing(WINDOW_CONFIG['root_layout_spacing'])

        # Title (simple header label)
        from .overlay_ui_builder import OverlayUIBuilder
        self._top_ui = OverlayUIBuilder()
        self._title_label = self._top_ui.create_top_label(text=title)
        self._title_label.setFont(QFont(*WINDOW_CONFIG['title_font']))
        self.set_title(title)
        self._root_layout.addWidget(self._title_label)

        # Content layout for subclasses to populate
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(WINDOW_CONFIG['content_layout_spacing'])
        self._root_layout.addLayout(self.content_layout)


        # ----- Top-right control buttons (settings is optional) -----
        self.settings_btn_top: Optional[QPushButton] = None
        self.collapse_btn_top: Optional[QPushButton] = None
        self.close_btn_top: Optional[QPushButton] = None
        self._top_button_padding = WINDOW_CONFIG['top_button_padding']
        self._create_default_top_buttons()

        # ----- Drag/Resize state -----
        self._dragging = False
        self._drag_start_pos = QPoint()

        self._resizing = False
        self._resize_start_pos = QPoint()
        self._resize_start_geometry = QRect()
        self._resize_margin = RESIZE_CONFIG['margin']
        self._resize_mode: Optional[str] = None  # e.g., "right", "bottom-right", etc.

        # ----- Minibar integration -----
        self._minibar = None  # type: ignore[assignment]
        self._expanded_geometry: Optional[QRect] = None

        # Restore geometry on initialization
        self.restore_geometry()

    # -------------------------------------------------------------------------
    # Public helpers
    # -------------------------------------------------------------------------

    def set_title(self, text: str) -> None:
        """Set window header title."""
        self._title_label.setText(text)

    def get_title(self) -> str:
        """Get window header title."""
        return self._title_label.text()

    def set_top_button_padding(self, *, top: int = WINDOW_CONFIG['top_button_padding']['top'], right: int = WINDOW_CONFIG['top_button_padding']['right'], bottom: int = WINDOW_CONFIG['top_button_padding']['bottom'], left: int = WINDOW_CONFIG['top_button_padding']['left']) -> None:
        """Adjust padding for top-right buttons positioning."""
        self._top_button_padding = {"top": top, "right": right, "bottom": bottom, "left": left}
        self._position_top_buttons()

    def add_settings_button(self, on_click: Optional[Callable[[], None]] = None) -> QPushButton:
        """
        Add a settings button to the top-right controls.
        Returns the created button so subclasses can further customize (icon/tooltip).
        """
        if self.settings_btn_top is None:
            btn = self._top_ui.create_top_button('settings_button')
            btn.setParent(self)
            if callable(on_click):
                btn.clicked.connect(on_click)
            self.settings_btn_top = btn
            self._position_top_buttons()
        return self.settings_btn_top

    def show_window(self, position: Optional[Union[QPoint, tuple[int, int]]] = None) -> None:
        """Show the window at optional position and bring to front."""
        if position is not None:
            if isinstance(position, QPoint):
                self.move(position)
            else:
                x, y = position
                self.move(x, y)
        self.show()
        try:
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    def restore_geometry(self) -> None:
        """Restore window geometry from settings."""
        try:
            settings = config_service.get_settings()
            if settings.overlay_window_geometry and len(settings.overlay_window_geometry) == 4:
                geometry = QRect(*settings.overlay_window_geometry)
                self.setGeometry(geometry)
                logger.debug(f"Overlay window geometry restored: {geometry}")
            else:
                logger.debug("No saved overlay window geometry found, using defaults")
        except Exception as e:
            logger.error(f"Failed to restore overlay window geometry: {e}")

    def capture_geometry(self) -> None:
        """Capture and save current window geometry."""
        try:
            geometry = self.geometry()
            geometry_data = [geometry.x(), geometry.y(), geometry.width(), geometry.height()]

            # Update settings only if geometry changed to avoid unnecessary full writes
            try:
                current = config_service.get_settings()
                current_geometry = getattr(current, "overlay_window_geometry", None)
            except Exception:
                current_geometry = None

            if current_geometry != geometry_data:
                # Use update_settings to change a single field (validates and saves safely)
                config_service.update_settings({"overlay_window_geometry": geometry_data})
                logger.debug(f"Overlay window geometry captured and saved: {geometry_data}")
            else:
                logger.debug("Overlay window geometry unchanged; skipping save.")
        except Exception as e:
            logger.error(f"Failed to capture overlay window geometry: {e}")

    # -------------------------------------------------------------------------
    # Default control buttons
    # -------------------------------------------------------------------------

    def _create_default_top_buttons(self) -> None:
        """Create collapse and close buttons in the top-right corner."""
        # Close button
        self.close_btn_top = self._top_ui.create_top_button('close_button')
        self.close_btn_top.setParent(self)
        self.close_btn_top.clicked.connect(self.dismiss)

        # Collapse button (to the left of close)
        self.collapse_btn_top = self._top_ui.create_top_button('collapse_button')
        self.collapse_btn_top.setParent(self)
        self.collapse_btn_top.clicked.connect(self.collapse_to_minibar)

        # Calculate initial positions
        self._position_top_buttons()

    def _position_top_buttons(self) -> None:
        """Position the top-right control buttons with padding."""
        padding = getattr(self, "_top_button_padding", WINDOW_CONFIG['top_button_padding'])
        top_offset = padding.get("top", WINDOW_CONFIG['top_button_padding']['top'])
        right_offset = padding.get("right", WINDOW_CONFIG['top_button_padding']['right'])
        spacing = padding.get("left", WINDOW_CONFIG['top_button_padding']['left'])

        buttons = [self.close_btn_top, self.collapse_btn_top, self.settings_btn_top]
        current_x = self.width() - right_offset

        for button in buttons:
            if not button:
                continue
            size = button.size()
            current_x -= size.width()
            button.move(max(0, current_x), top_offset)
            current_x -= spacing

    # -------------------------------------------------------------------------
    # Drag + edge-resize support (frameless)
    # -------------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Determine resize mode on press to support immediate edge press
            pos = event.position().toPoint()
            mode = self._hit_test_resize(pos)
            if mode is not None:
                self._resize_mode = mode
                self._resizing = True
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geometry = self.geometry()
                self._update_cursor_for_mode(mode)
                event.accept()
                return
            # Otherwise start window drag
            self._dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_start_pos)
            event.accept()
            return

        if self._resizing and event.buttons() & Qt.MouseButton.LeftButton:
            # Compute new geometry based on original geometry (immutable baseline)
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            dx, dy = delta.x(), delta.y()

            s_geo = self._resize_start_geometry
            s_left, s_top, s_w, s_h = s_geo.left(), s_geo.top(), s_geo.width(), s_geo.height()
            min_w, min_h = self.minimumWidth(), self.minimumHeight()

            new_left, new_top, new_w, new_h = s_left, s_top, s_w, s_h
            mode = self._resize_mode or ""

            # Horizontal
            if "left" in mode:
                new_w = max(min_w, s_w - dx)
                new_left = s_left + (s_w - new_w)
            elif "right" in mode:
                new_w = max(min_w, s_w + dx)

            # Vertical
            if "top" in mode:
                new_h = max(min_h, s_h - dy)
                new_top = s_top + (s_h - new_h)
            elif "bottom" in mode:
                new_h = max(min_h, s_h + dy)

            self.setGeometry(QRect(new_left, new_top, new_w, new_h))
            event.accept()
            return

        # Update hover cursor/mode when not dragging/resizing
        pos = event.position().toPoint()
        mode = self._hit_test_resize(pos)
        self._resize_mode = mode
        self._update_cursor_for_mode(mode)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._resizing = False
            self._resize_mode = None
            # Update cursor according to current hover position
            try:
                pos = event.position().toPoint()
                self._update_cursor_for_mode(self._hit_test_resize(pos))
            except Exception:
                self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click to collapse to minibar."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.collapse_to_minibar()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _hit_test_resize(self, pos: QPoint) -> Optional[str]:
        r = self.rect()
        margin = getattr(self, "_resize_margin", RESIZE_CONFIG['margin'])

        left = pos.x() <= margin
        right = pos.x() >= r.width() - margin
        top = pos.y() <= margin
        bottom = pos.y() >= r.height() - margin

        if left and bottom:
            return "bottom-left"
        if right and bottom:
            return "bottom-right"
        if left and top:
            return "top-left"
        if right and top:
            return "top-right"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"
        return None

    def _update_cursor_for_mode(self, mode: Optional[str]) -> None:
        if mode == "bottom-left":
            self.setCursor(Qt.SizeBDiagCursor)
        elif mode == "bottom-right":
            self.setCursor(Qt.SizeFDiagCursor)
        elif mode == "top-left":
            self.setCursor(Qt.SizeFDiagCursor)
        elif mode == "top-right":
            self.setCursor(Qt.SizeBDiagCursor)
        elif mode in ("left", "right"):
            self.setCursor(Qt.SizeHorCursor)
        elif mode in ("top", "bottom"):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_top_buttons()

    # -------------------------------------------------------------------------
    # Minibar support
    # -------------------------------------------------------------------------

    def collapse_to_minibar(self) -> None:
        """Collapse the window to a detachable MiniBar."""
        # Save current geometry to restore later
        try:
            self._expanded_geometry = QRect(self.geometry())
        except Exception:
            self._expanded_geometry = self.geometry()

        # Create MiniBar if not existing
        if self._minibar is None:
            # Lazy import to avoid cycles
            from whisperbridge.ui_qt.minibar_overlay import MiniBarOverlay  # local import
            self._minibar = MiniBarOverlay(self, self.restore_from_minibar)
            try:
                # Sync minibar title with the owner's title
                try:
                    self._minibar.set_title(self.get_title())
                except Exception:
                    pass
                self._minibar.adjustSize()
            except Exception:
                pass

        # Position minibar so its right edge aligns with window's right edge
        g = self.geometry()
        minibar_w = self._minibar.width() if self._minibar else 180
        minibar_x = g.x() + g.width() - minibar_w
        minibar_y = g.y()
        if self._minibar:
            try:
                # Sync minibar title with current window title
                self._minibar.set_title(self.get_title())
            except Exception:
                pass
            self._minibar.show_at((minibar_x, minibar_y))

        # Hide this window (do NOT mark destroyed)
        self.hide()

    def restore_from_minibar(self) -> None:
        """Restore the window from the MiniBar to its last geometry; align top-right."""
        minibar_geom = None
        try:
            if self._minibar:
                try:
                    minibar_geom = self._minibar.frameGeometry()
                except Exception:
                    minibar_geom = self._minibar.geometry()
        except Exception:
            minibar_geom = None

        if self._expanded_geometry is not None:
            g = QRect(self._expanded_geometry)
            if minibar_geom is not None:
                minibar_right = minibar_geom.x() + minibar_geom.width()
                minibar_top = minibar_geom.y()
                left = minibar_right - g.width()
                g.moveTopLeft(QPoint(left, minibar_top))
            self.setGeometry(g)
        elif minibar_geom is not None:
            minibar_right = minibar_geom.x() + minibar_geom.width()
            minibar_top = minibar_geom.y()
            left = minibar_right - self.width()
            self.move(left, minibar_top)

        self.show()
        try:
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

        if self._minibar:
            try:
                self._minibar.hide()
            except Exception:
                pass


    # -------------------------------------------------------------------------
    # Unified dismiss/close behavior
    # -------------------------------------------------------------------------

    def dismiss(self) -> None:
        """
        Default dismiss behavior for overlay windows:
        - close minibar if present
        - capture geometry before hiding
        - hide self (do not destroy)
        Subclasses may override to provide different policy.
        """
        # Capture geometry before hiding
        self.capture_geometry()

        try:
            if hasattr(self, "_minibar") and self._minibar:
                try:
                    self._minibar.close()
                finally:
                    self._minibar = None
        except Exception:
            pass
        self.hide()