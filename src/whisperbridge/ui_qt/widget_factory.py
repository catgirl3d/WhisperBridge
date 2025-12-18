"""
Shared widget factory helpers.

Goal:
- Keep window-specific builders/layouts independent
- Deduplicate low-level widget creation from CONFIG dictionaries
- Keep visuals in QSS; Python only sets identity/state (objectName, properties, sizes, etc.)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Tuple, Type, TypeVar

import qtawesome as qta
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import QComboBox, QListView

TWidget = TypeVar("TWidget")


def apply_widget_config(widget: Any, config: Mapping[str, Any]) -> None:
    """Apply common widget properties from a config mapping.

    Supported keys (best-effort, applied only if the widget supports it):
    - object_name, text, tooltip
    - size: (w, h) where either can be None
    - width, height, fixed_width, fixed_height
    - minimum_width, minimum_height, minimum_size
    - maximum_size
    - icon_size: (w, h)
    - font: tuple suitable for QFont(*font)
    - placeholder
    """
    if not config:
        return

    # Identity / text
    if "object_name" in config and hasattr(widget, "setObjectName"):
        widget.setObjectName(config["object_name"])
    if "text" in config and hasattr(widget, "setText"):
        widget.setText(config["text"])
    if "tooltip" in config and hasattr(widget, "setToolTip"):
        widget.setToolTip(config["tooltip"])

    # Sizes
    if "size" in config and config["size"] is not None:
        w, h = config["size"]
        if hasattr(widget, "setFixedSize") and w is not None and h is not None:
            widget.setFixedSize(w, h)
        else:
            if w is not None and hasattr(widget, "setFixedWidth"):
                widget.setFixedWidth(w)
            if h is not None and hasattr(widget, "setFixedHeight"):
                widget.setFixedHeight(h)

    if "width" in config and hasattr(widget, "setFixedWidth"):
        widget.setFixedWidth(config["width"])
    if "height" in config and hasattr(widget, "setFixedHeight"):
        widget.setFixedHeight(config["height"])
    if "fixed_width" in config and hasattr(widget, "setFixedWidth"):
        widget.setFixedWidth(config["fixed_width"])
    if "fixed_height" in config and hasattr(widget, "setFixedHeight"):
        widget.setFixedHeight(config["fixed_height"])

    if "minimum_width" in config and hasattr(widget, "setMinimumWidth"):
        widget.setMinimumWidth(config["minimum_width"])
    if "minimum_height" in config and hasattr(widget, "setMinimumHeight"):
        widget.setMinimumHeight(config["minimum_height"])
    if "minimum_size" in config and hasattr(widget, "setMinimumSize"):
        widget.setMinimumSize(*config["minimum_size"])
    if "maximum_size" in config and hasattr(widget, "setMaximumSize"):
        widget.setMaximumSize(*config["maximum_size"])

    # Icons / font / placeholder
    if "icon_size" in config and hasattr(widget, "setIconSize"):
        widget.setIconSize(QSize(*config["icon_size"]))
    if "font" in config and hasattr(widget, "setFont"):
        widget.setFont(QFont(*config["font"]))
    if "placeholder" in config and hasattr(widget, "setPlaceholderText"):
        widget.setPlaceholderText(config["placeholder"])


def create_widget(
    config_maps: Mapping[str, Mapping[str, Mapping[str, Any]]],
    widget_type: str,
    config_key: str,
    widget_class: Type[TWidget],
    **kwargs: Any,
) -> Tuple[TWidget, Mapping[str, Any]]:
    """Create a widget and apply config from a nested config map."""
    config = config_maps[widget_type][config_key]
    widget = widget_class(**kwargs)
    apply_widget_config(widget, config)
    return widget, config


def apply_custom_dropdown_style(combo: QComboBox) -> None:
    """Apply custom styling to the dropdown view of a QComboBox (frameless popup)."""
    view = QListView()
    combo.setView(view)
    view.window().setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
    view.window().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def load_icon(icon_name: str, assets_base: Path) -> QIcon:
    """Load icon from assets/icons/ directory."""
    try:
        return QIcon(QPixmap(str(assets_base / "icons" / icon_name)))
    except Exception:
        return QIcon()


def make_qta_icon(spec: Mapping[str, Any]) -> QIcon:
    """Create a qtawesome icon from spec {'icon': str, 'color': str}."""
    if not spec:
        return QIcon()
    try:
        return qta.icon(spec["icon"], color=spec.get("color"))
    except Exception:
        return QIcon()


def make_icon_from_spec(spec: Mapping[str, Any] | None, assets_base: Path) -> QIcon:
    """Create QIcon from spec.

    Supported:
    - {'icon','color'} for qtawesome
    - {'asset'} for PNG from assets/icons/
    """
    if not spec:
        return QIcon()
    if "asset" in spec:
        return load_icon(str(spec["asset"]), assets_base)
    return make_qta_icon(spec)
