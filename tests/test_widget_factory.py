"""Unit tests for shared UI widget factory helpers.

Focus:
- apply_widget_config / create_widget apply common CONFIG keys reliably
- icon helper functions return QIcon objects without raising
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
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
    """apply_custom_dropdown_style should configure a frameless translucent popup view."""
    combo = QComboBox()
    original_view = combo.view()

    widget_factory.apply_custom_dropdown_style(combo)

    view = combo.view()
    assert isinstance(view, QListView)
    assert view is not original_view

    window_flags = view.window().windowFlags()
    assert window_flags & Qt.WindowType.Popup
    assert window_flags & Qt.WindowType.FramelessWindowHint
    assert window_flags & Qt.WindowType.NoDropShadowWindowHint
    assert view.window().testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_settings_factory_creates_reasoning_effort_combo(qapp):
    """The model settings factory should expose all configured reasoning modes."""
    combo = SettingsUIFactory().create_combo("openaiReasoningEffortCombo")

    assert combo.objectName() == "openaiReasoningEffortCombo"
    assert [combo.itemText(index) for index in range(combo.count())] == [
        "No override (model default)",
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
    ]
    assert [combo.itemData(index) for index in range(combo.count())] == [
        "not_set",
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
    ]


def test_settings_factory_creates_editable_openai_vision_combo(qapp):
    """The OpenAI vision model selector should allow API-listed and manual IDs."""
    combo = SettingsUIFactory().create_combo("openaiVisionModelCombo")

    assert combo.objectName() == "openaiVisionModelCombo"
    assert combo.isEditable()


def test_reasoning_effort_restore_falls_back_to_not_set(qapp):
    """Unknown persisted reasoning values must leave a valid selection."""
    combo = SettingsUIFactory().create_combo("openaiReasoningEffortCombo")
    combo.setCurrentIndex(combo.findData("high"))
    assert combo.currentData() == "high"

    SettingsDialog._set_reasoning_effort_combo(combo, "removed-option")

    assert combo.currentData() == "not_set"


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


def test_apply_models_to_ui_restores_current_model_or_selects_first(qapp):
    """The main model selector restores exact and partial matches and defaults otherwise."""
    dialog = SettingsDialog.__new__(SettingsDialog)
    dialog.model_combo = QComboBox()

    dialog._apply_models_to_ui(["gpt-5.4-mini", "gpt-4-turbo"], "gpt-4-turbo", "api")
    assert dialog.model_combo.currentText() == "gpt-4-turbo"

    dialog._apply_models_to_ui(["gpt-4-turbo", "gpt-5.4-mini"], "gpt-4", "api")
    assert [dialog.model_combo.itemText(i) for i in range(dialog.model_combo.count())] == [
        "gpt-4-turbo",
        "gpt-5.4-mini",
    ]
    assert dialog.model_combo.currentText() == "gpt-4-turbo"

    dialog._apply_models_to_ui(["gpt-5.4-mini", "gpt-5.6-luna"], "removed-model", "api")
    assert dialog.model_combo.currentText() == "gpt-5.4-mini"


def test_apply_openai_vision_models_to_ui_populates_and_preserves_custom_model(qapp):
    """The editable OpenAI vision selector keeps a typed model absent from the API list."""
    dialog = SettingsDialog.__new__(SettingsDialog)
    dialog.openai_vision_model_combo = SettingsUIFactory().create_combo("openaiVisionModelCombo")

    dialog._apply_openai_vision_models_to_ui(
        ["gpt-5.4-mini", "gpt-5.6-luna"],
        "custom-vision-model",
        "api",
    )

    assert [dialog.openai_vision_model_combo.itemText(i) for i in range(dialog.openai_vision_model_combo.count())] == [
        "gpt-5.4-mini",
        "gpt-5.6-luna",
    ]
    assert dialog.openai_vision_model_combo.currentText() == "custom-vision-model"


def test_apply_available_models_to_ui_leaves_vision_combo_unchanged_for_non_openai(qapp):
    """Applying another provider's models must not alter the OpenAI vision selector."""
    dialog = SettingsDialog.__new__(SettingsDialog)
    dialog._loaded_model_defaults = {}
    dialog.model_combo = QComboBox()
    dialog.openai_vision_model_combo = SettingsUIFactory().create_combo("openaiVisionModelCombo")
    dialog.openai_vision_model_combo.addItems(["gpt-5.4-mini", "custom-vision-model"])
    dialog.openai_vision_model_combo.setCurrentText("custom-vision-model")
    before = [dialog.openai_vision_model_combo.itemText(i) for i in range(dialog.openai_vision_model_combo.count())]

    dialog._apply_available_models_to_ui(["gemini-2.5-flash"], None, "api", "google")

    assert [dialog.openai_vision_model_combo.itemText(i) for i in range(dialog.openai_vision_model_combo.count())] == before
    assert dialog.openai_vision_model_combo.currentText() == "custom-vision-model"


def test_apply_available_models_to_ui_applies_openai_vision_models(mocker):
    """OpenAI model application should update both selectors with the same source list."""
    dialog = SettingsDialog.__new__(SettingsDialog)
    dialog._loaded_model_defaults = {}
    apply_models = mocker.patch.object(dialog, "_apply_models_to_ui")
    apply_vision_models = mocker.patch.object(dialog, "_apply_openai_vision_models_to_ui")
    vision_model = "gpt-5.6-luna"
    vision_model_getter = mocker.patch.object(
        dialog,
        "_get_openai_vision_model_to_select",
        return_value=vision_model,
    )
    models = ["gpt-5.4-mini", "gpt-5.6-luna"]

    dialog._apply_available_models_to_ui(models, "gpt-5.4-mini", "api", "openai")

    apply_models.assert_called_once_with(models, "gpt-5.4-mini", "api")
    vision_model_getter.assert_called_once_with()
    apply_vision_models.assert_called_once_with(models, vision_model, "api")


def test_apply_available_models_to_ui_skips_openai_vision_for_other_providers(mocker):
    """Non-OpenAI model application should not access or update the vision selector."""
    dialog = SettingsDialog.__new__(SettingsDialog)
    dialog._loaded_model_defaults = {}
    apply_models = mocker.patch.object(dialog, "_apply_models_to_ui")
    apply_vision_models = mocker.patch.object(dialog, "_apply_openai_vision_models_to_ui")
    vision_model_getter = mocker.patch.object(dialog, "_get_openai_vision_model_to_select")
    models = ["gemini-2.5-flash"]

    dialog._apply_available_models_to_ui(models, None, "cache", "google")

    apply_models.assert_called_once_with(models, None, "cache")
    vision_model_getter.assert_not_called()
    apply_vision_models.assert_not_called()


def test_make_qta_icon_returns_qicon(qapp):
    """make_qta_icon should return a usable QIcon for a valid qtawesome spec."""
    icon = widget_factory.make_qta_icon({"icon": "fa5s.times", "color": "black"})
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_make_icon_from_spec_asset_returns_qicon(qapp):
    """make_icon_from_spec should return a QIcon for a PNG asset."""
    # Use absolute path to assets directory
    project_root = Path(__file__).parent.parent
    assets_base = project_root / "src" / "whisperbridge" / "assets"
    icon = widget_factory.make_icon_from_spec({"asset": "translation-icon.png"}, assets_base)
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_make_icon_from_spec_returns_null_icon_for_invalid_asset(qapp):
    """Missing image assets use the null-icon fallback."""
    assets_base = Path(__file__).parent.parent / "src" / "whisperbridge" / "assets"

    icon = widget_factory.make_icon_from_spec({"asset": "does-not-exist.png"}, assets_base)

    assert icon.isNull()


def test_make_qta_icon_returns_null_icon_for_invalid_spec(qapp):
    """Invalid qtawesome specifications use the null-icon fallback."""
    icon = widget_factory.make_qta_icon({"icon": "not-a-real-qtawesome-icon", "color": "black"})

    assert icon.isNull()
