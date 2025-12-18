"""Unit tests for shared UI widget factory helpers.

Focus:
- apply_widget_config / create_widget apply common CONFIG keys reliably
- icon helper functions return QIcon objects without raising
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QListView, QPushButton

from whisperbridge.ui_qt import widget_factory


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QApplication exists for Qt widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_create_widget_applies_common_keys(qapp):
    """create_widget should apply common config keys to widgets (best-effort)."""
    config_maps = {
        "test": {
            "btn": {
                "object_name": "myButton",
                "text": "Click",
                "tooltip": "Help",
                "size": (40, 20),
                "icon_size": (16, 16),
            },
            "edit": {
                "object_name": "myEdit",
                "placeholder": "Type here",
                "minimum_width": 123,
            },
        }
    }

    btn, btn_cfg = widget_factory.create_widget(config_maps, "test", "btn", QPushButton)
    assert btn_cfg["object_name"] == "myButton"
    assert btn.objectName() == "myButton"
    assert btn.text() == "Click"
    assert btn.toolTip() == "Help"
    assert btn.size().width() == 40
    assert btn.size().height() == 20
    assert btn.iconSize().width() == 16
    assert btn.iconSize().height() == 16

    edit, edit_cfg = widget_factory.create_widget(config_maps, "test", "edit", QLineEdit)
    assert edit_cfg["object_name"] == "myEdit"
    assert edit.objectName() == "myEdit"
    assert edit.placeholderText() == "Type here"
    assert edit.minimumWidth() == 123


def test_apply_custom_dropdown_style_sets_list_view(qapp):
    """apply_custom_dropdown_style should install a QListView as the combo view."""
    combo = QComboBox()
    widget_factory.apply_custom_dropdown_style(combo)

    view = combo.view()
    assert isinstance(view, QListView)


def test_make_qta_icon_returns_qicon(qapp):
    """make_qta_icon should return a QIcon (may be null depending on environment)."""
    icon = widget_factory.make_qta_icon({"icon": "fa5s.times", "color": "black"})
    assert isinstance(icon, QIcon)


def test_make_icon_from_spec_asset_returns_qicon(qapp):
    """make_icon_from_spec should return a QIcon for a PNG asset."""
    assets_base = Path("src/whisperbridge/assets")
    icon = widget_factory.make_icon_from_spec({"asset": "translation-icon.png"}, assets_base)
    assert isinstance(icon, QIcon)
