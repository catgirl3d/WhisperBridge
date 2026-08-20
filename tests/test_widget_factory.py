"""Unit tests for shared UI widget factory helpers.

Focus:
- apply_widget_config / create_widget apply common CONFIG keys reliably
- icon helper functions return QIcon objects without raising
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QListView, QPushButton

from whisperbridge.ui_qt import widget_factory
from whisperbridge.ui_qt.settings_dialog import SettingsDialog
from whisperbridge.ui_qt.settings_ui_factory import SettingsUIFactory


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


def test_settings_factory_creates_editable_openai_vision_combo(qapp):
    """The OpenAI vision model selector should allow API-listed and manual IDs."""
    combo = SettingsUIFactory().create_combo("openaiVisionModelCombo")

    assert combo.objectName() == "openaiVisionModelCombo"
    assert combo.isEditable()

def test_vision_model_restore_prefers_unsaved_combo_value(qapp, mocker):
    """Refreshing models must preserve a vision model edited but not saved yet."""
    combo = SettingsUIFactory().create_combo("openaiVisionModelCombo")
    combo.addItems(["gpt-5.4-mini", "gpt-5.6-luna"])
    combo.setCurrentText("gpt-5.6-luna")

    dialog = SettingsDialog.__new__(SettingsDialog)
    dialog.openai_vision_model_combo = combo
    dialog.current_settings = SimpleNamespace(openai_vision_model="gpt-5.4-mini")
    mocker.patch(
        "whisperbridge.ui_qt.settings_dialog.config_service.get_setting",
        return_value="gpt-5.4-mini",
    )

    assert dialog._get_openai_vision_model_to_select() == "gpt-5.6-luna"


def test_make_qta_icon_returns_qicon(qapp):
    """make_qta_icon should return a QIcon (may be null depending on environment)."""
    icon = widget_factory.make_qta_icon({"icon": "fa5s.times", "color": "black"})
    assert isinstance(icon, QIcon)


def test_make_icon_from_spec_asset_returns_qicon(qapp):
    """make_icon_from_spec should return a QIcon for a PNG asset."""
    # Use absolute path to assets directory
    project_root = Path(__file__).parent.parent
    assets_base = project_root / "src" / "whisperbridge" / "assets"
    icon = widget_factory.make_icon_from_spec({"asset": "translation-icon.png"}, assets_base)
    assert isinstance(icon, QIcon)
