"""
MiniBar Overlay module for creating detachable mini companion windows.

Configuration Guidelines:
- All widget styles should be centralized in CONFIG dictionaries
- Use consistent naming: {COMPONENT_TYPE}_CONFIG
- Include size, style, and any widget-specific properties
- Add objectName for widgets that need styling/testing
- Follow DRY principle - avoid hardcoded values

Key Principles:
1. Centralized Configuration: All styles in CONFIG dictionaries at class level
2. Explicit Mapping: Use explicit button-to-style mappings, not dynamic key generation
3. Unified Factory: Single _create_widget_from_config method for all widgets
4. ObjectName Usage: Set objectName for all testable/stylable widgets
5. Separation of Concerns: Python handles logic, QSS handles appearance
"""

import weakref
from typing import Callable, Union

import qtawesome as qta
from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


from .base_window import BaseWindow

# Configuration dictionaries for UI components
MINIBAR_WINDOW_CONFIG = {
    'fixed_height': 28,
    'minimum_width': 190,
    'layout_margins': (10, 0, 4, 0),
    'layout_spacing': 2,
    'title_font': ("Arial", 10, QFont.Weight.Bold),
}

MINIBAR_BUTTON_CONFIG = {
    'expand': {
        'size': (22, 22),
        'icon': "fa5s.expand-alt",
        'fallback_icon': "fa5s.chevron-up",
        'fallback_text': "Expand",
        'icon_color': "black",
        'object_name': "expandBtnMini",
    },
    'close': {
        'size': (22, 22),
        'icon': "fa5s.times",
        'fallback_text': "X",
        'icon_color': "black",
        'object_name': "closeBtnMini",
    },
}

# Configuration for label widgets
MINIBAR_LABEL_CONFIG = {
    'title': {
        'object_name': "titleLabelMini",
        'font': ("Arial", 10, QFont.Weight.Bold),
    }
}



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
        self.setFixedHeight(MINIBAR_WINDOW_CONFIG['fixed_height'])
        self.setMinimumWidth(MINIBAR_WINDOW_CONFIG['minimum_width'])

        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(*MINIBAR_WINDOW_CONFIG['layout_margins'])
        layout.setSpacing(MINIBAR_WINDOW_CONFIG['layout_spacing'])

        # Title (initialized from owner if available, no hardcoded text)
        self.title_label = self._create_title_label()
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
        self.expand_btn = self._create_expand_button()
        layout.addWidget(self.expand_btn)

        # Close button(top)
        self.close_btn = self._create_close_button()
        layout.addWidget(self.close_btn)

        # Styling is handled by global stylesheet in style.qss

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

    # --- Factory methods ---

    def _create_widget_from_config(self, widget_type: str, config_key: str, widget_class, **kwargs):
        """
        Generic factory method to create widgets from configuration dictionaries.
        
        Args:
            widget_type: Type of widget ('button' or 'label')
            config_key: Key within the configuration dictionary
            widget_class: The widget class to instantiate
            **kwargs: Additional arguments to pass to the widget constructor
            
        Returns:
            Tuple of (widget, config)
        """
        config_maps = {
            'button': MINIBAR_BUTTON_CONFIG,
            'label': MINIBAR_LABEL_CONFIG
        }
        
        config = config_maps[widget_type][config_key]
        widget = widget_class(**kwargs)
        
        # Apply common configuration properties
        if 'object_name' in config:
            widget.setObjectName(config['object_name'])
        if 'size' in config:
            widget.setFixedSize(*config['size'])
        if 'font' in config:
            widget.setFont(QFont(*config['font']))
            
        return widget, config

    def _create_expand_button(self) -> QPushButton:
        """Create the expand button using configuration."""
        btn, config = self._create_widget_from_config('button', 'expand', QPushButton)
        
        # Apply button-specific configuration
        try:
            btn.setIcon(qta.icon(config['icon'], color=config['icon_color']))
        except Exception:
            try:
                btn.setIcon(qta.icon(config['fallback_icon'], color=config['icon_color']))
            except Exception:
                btn.setText(config['fallback_text'])
        
        btn.clicked.connect(self._handle_expand_clicked)
        return btn

    def _create_close_button(self) -> QPushButton:
        """Create the close button using configuration."""
        btn, config = self._create_widget_from_config('button', 'close', QPushButton)
        
        # Apply button-specific configuration
        try:
            btn.setIcon(qta.icon(config['icon'], color=config['icon_color']))
        except Exception:
            btn.setText(config['fallback_text'])
        
        btn.clicked.connect(self._handle_close_clicked)
        return btn

    def _create_title_label(self) -> QLabel:
        """Create the title label using configuration."""
        label, _ = self._create_widget_from_config('label', 'title', QLabel)
        return label

