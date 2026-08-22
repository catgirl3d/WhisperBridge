"""Regression tests for SettingsDialog single ownership and patch-based saving."""

import whisperbridge.ui_qt.settings_dialog as settings_dialog_module
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QDialog

from whisperbridge.core.config import Settings
from whisperbridge.services.config_service import config_service
from whisperbridge.services.ui_service import UIService
from whisperbridge.ui_qt.overlay_window import OverlayWindow
from whisperbridge.ui_qt.settings_dialog import SettingsDialog


def _build_ui_service(mocker) -> UIService:
    """Create UIService with heavy UI initialization disabled."""
    mocker.patch.object(UIService, "_initialize_ui_components", return_value=None)
    ui = UIService(app=Mock())
    ui.logger = Mock()
    ui.main_window = Mock()
    return ui


def test_open_settings_reuses_single_dialog_and_selects_requested_tab(mocker):
    """Repeated open_settings calls reuse one UIService-owned dialog instance."""
    dialog_instance = Mock()
    dialog_cls = mocker.patch(
        "whisperbridge.services.ui_service.SettingsDialog",
        return_value=dialog_instance,
    )
    fake_settings = Mock(spec=Settings)
    mocker.patch.object(config_service, "get_settings", return_value=fake_settings)

    ui = _build_ui_service(mocker)

    ui.open_settings()
    ui.open_settings(tab_title="Stylist")

    dialog_cls.assert_called_once()
    assert ui.settings_dialog is dialog_instance
    assert dialog_instance._load_settings.call_count == 2
    dialog_instance._load_settings.assert_called_with(settings=fake_settings)
    dialog_instance.select_tab_by_title.assert_called_once_with("Stylist")


def test_open_stylist_settings_delegates_to_existing_ui_service(mocker):
    """Overlay must delegate the Stylist path to the canonical UIService owner."""
    ui_service = Mock()
    mocker.patch(
        "whisperbridge.services.ui_service.get_ui_service",
        return_value=ui_service,
    )

    overlay = OverlayWindow.__new__(OverlayWindow)
    overlay._open_stylist_settings()

    ui_service.open_settings.assert_called_once_with(tab_title="Stylist")


def test_open_stylist_settings_without_ui_service_does_not_raise(mocker):
    """Without a UI service the overlay must warn and not create anything."""
    mocker.patch(
        "whisperbridge.services.ui_service.get_ui_service",
        return_value=None,
    )
    overlay = OverlayWindow.__new__(OverlayWindow)

    assert overlay._open_stylist_settings() is None


@pytest.fixture
def dialog(qtbot, mocker):
    """Real SettingsDialog wired to a deterministic default-settings config mock."""
    settings = Settings()
    fake_config = Mock()
    fake_config.get_settings.return_value = settings
    fake_config.get_setting.side_effect = lambda key, **kwargs: getattr(settings, key, None)
    fake_config.update_settings.return_value = True
    mocker.patch("whisperbridge.ui_qt.settings_dialog.config_service", fake_config)

    api_manager = Mock()
    api_manager.is_initialized.return_value = False
    mocker.patch("whisperbridge.ui_qt.settings_dialog.get_api_manager", return_value=api_manager)

    dlg = SettingsDialog(app=Mock(), parent=None)
    qtbot.addWidget(dlg)
    return dlg


def test_select_tab_by_title_selects_visible_tab(dialog):
    assert dialog.select_tab_by_title("Stylist") is True
    assert dialog.tab_widget.tabText(dialog.tab_widget.currentIndex()) == "Stylist"


def test_select_tab_by_unknown_title_keeps_current_tab(dialog):
    dialog.select_tab_by_title("API")
    current_index = dialog.tab_widget.currentIndex()

    assert dialog.select_tab_by_title("NoSuchTab") is False
    assert dialog.tab_widget.currentIndex() == current_index


def test_select_tab_by_hidden_title_keeps_current_tab(dialog):
    stylist_index = dialog.tab_widget.indexOf(dialog._stylist_tab)
    dialog.tab_widget.setTabVisible(stylist_index, False)
    current_index = dialog.tab_widget.currentIndex()

    assert dialog.select_tab_by_title("Stylist") is False
    assert dialog.tab_widget.currentIndex() == current_index


def test_unchanged_form_produces_empty_patch(dialog):
    assert dialog._build_settings_patch() == {}


def test_patch_includes_only_changed_field(dialog):
    dialog.api_timeout_spin.setValue(45)

    assert dialog._build_settings_patch() == {"api_timeout": 45}


def test_patch_includes_api_key_only_when_changed_from_baseline(dialog):
    dialog.api_key_edits["google"].setText("AIza-test-key")

    assert dialog._build_settings_patch() == {"google_api_key": "AIza-test-key"}


def test_patch_reports_cleared_api_key_as_none(dialog):
    dialog._form_baseline.google_api_key = "AIza-existing"
    dialog.api_key_edits["google"].setText("")

    assert dialog._build_settings_patch() == {"google_api_key": None}


def test_patch_excludes_model_placeholder_but_includes_real_model(dialog):
    assert dialog.model_combo.currentText() in SettingsDialog.MODEL_PLACEHOLDERS
    assert "openai_model" not in dialog._build_settings_patch()

    dialog.model_combo.setCurrentText("gpt-test-model")

    assert dialog._build_settings_patch() == {"openai_model": "gpt-test-model"}


def test_patch_includes_text_styles_only_when_changed(dialog):
    expected_styles = [dict(style) for style in dialog._form_baseline.text_styles]
    expected_styles[0]["name"] = "Renamed Style"

    dialog.styles_table.item(0, 0).setText("Renamed Style")

    assert dialog._build_settings_patch() == {"text_styles": expected_styles}


def test_baseline_strings_are_normalized_before_comparison(dialog):
    """Stored whitespace must not turn an untouched form into a non-empty patch."""
    dialog._form_baseline.system_prompt = f"  {dialog._form_baseline.system_prompt}  "
    dialog._form_baseline.google_api_key = " AIza-existing "
    dialog.api_key_edits["google"].setText("AIza-existing")
    dialog._form_baseline.text_styles[1]["prompt"] = (
        f"  {dialog._form_baseline.text_styles[1]['prompt']}  "
    )

    assert dialog._build_settings_patch() == {}


def test_baseline_incomplete_style_entries_do_not_create_false_diff(dialog):
    """Stored styles without a name or prompt must not produce a save diff."""
    styles = [dict(style) for style in dialog._form_baseline.text_styles]
    styles.append({"name": "", "prompt": "orphan prompt"})
    styles.append({"name": "   ", "prompt": ""})
    dialog._form_baseline.text_styles = styles

    assert dialog._build_settings_patch() == {}


def test_missing_baseline_refuses_to_build_patch_and_keeps_dialog_open(dialog, mocker):
    """A missing baseline is a programming error: never diff against live settings."""
    critical_mock = mocker.patch("whisperbridge.ui_qt.settings_dialog.QMessageBox.critical")
    dialog.show()
    dialog.api_timeout_spin.setValue(45)
    dialog._form_baseline = None

    with pytest.raises(RuntimeError):
        dialog._build_settings_patch()

    dialog._on_save()

    settings_dialog_module.config_service.update_settings.assert_not_called()
    assert dialog.isVisible()


def test_load_time_model_fallback_is_not_saved_as_user_change(dialog):
    """Auto-selected default model is baseline until the user picks another one."""
    dialog._apply_available_models_to_ui(["m-a", "m-b"], "saved-model", "mock", "openai")

    assert dialog.model_combo.currentText() == "m-a"
    assert "openai_model" not in dialog._build_settings_patch()

    dialog.model_combo.setCurrentText("m-b")

    assert dialog._build_settings_patch() == {"openai_model": "m-b"}


def test_exact_model_restore_clears_recorded_fallback(dialog):
    """Restoring the saved model must not keep a stale fallback baseline."""
    saved_model = dialog._form_baseline.openai_model
    dialog._loaded_model_defaults["openai_model"] = "stale-default"

    dialog._apply_available_models_to_ui(
        [saved_model, "other-model"], saved_model, "mock", "openai"
    )

    assert dialog.model_combo.currentText() == saved_model
    assert dialog._loaded_model_defaults == {}
    assert "openai_model" not in dialog._build_settings_patch()


def test_save_applies_exact_patch_and_closes_on_success(dialog):
    dialog.show()
    dialog.api_timeout_spin.setValue(45)

    dialog._on_save()

    settings_dialog_module.config_service.update_settings.assert_called_once_with(
        {"api_timeout": 45}
    )
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert not dialog.isVisible()


def test_save_without_changes_closes_without_write(dialog):
    dialog.show()

    dialog._on_save()

    settings_dialog_module.config_service.update_settings.assert_not_called()
    assert not dialog.isVisible()


def test_failed_save_keeps_dialog_open(dialog, mocker):
    mocker.patch("whisperbridge.ui_qt.settings_dialog.QMessageBox.critical")
    settings_dialog_module.config_service.update_settings.return_value = False
    dialog.show()
    dialog.api_timeout_spin.setValue(45)

    dialog._on_save()

    settings_dialog_module.config_service.update_settings.assert_called_once_with(
        {"api_timeout": 45}
    )
    assert dialog.isVisible()
