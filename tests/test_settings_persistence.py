import json

from whisperbridge.core.config import Settings
from whisperbridge.core.settings_manager import SettingsManager
from whisperbridge.services.config_service import ConfigService, SettingsObserver


class RecordingObserver(SettingsObserver):
    def __init__(self):
        self.changes = []

    def on_settings_changed(self, key, old_value, new_value):
        self.changes.append((key, old_value, new_value))


def test_settings_manager_save_single_setting_persists_canonical_value(tmp_path, mocker):
    """SettingsManager should persist the validated translator font size, not the raw input."""
    manager = SettingsManager()
    settings_file = tmp_path / "settings.json"
    mocker.patch.object(manager, "_get_settings_file", return_value=settings_file)
    manager._settings = Settings()

    assert manager.save_single_setting("translator_font_size", 99)

    persisted_data = json.loads(settings_file.read_text(encoding="utf-8"))
    assert persisted_data["translator_font_size"] == 32
    assert manager.get_settings().translator_font_size == 32


def test_config_service_set_setting_uses_validated_value_for_cache_and_observers(tmp_path, mocker):
    """ConfigService should expose the canonical saved value to cache and observers."""
    manager = SettingsManager()
    settings_file = tmp_path / "settings.json"
    mocker.patch.object(manager, "_get_settings_file", return_value=settings_file)
    manager._settings = Settings()

    config = ConfigService()
    config._settings_manager = manager
    config._settings = manager.get_settings()

    observer = RecordingObserver()
    config.add_observer(observer)

    assert config.set_setting("translator_font_size", 99)
    assert config.get_setting("translator_font_size") == 32
    assert observer.changes == [("translator_font_size", 9, 32)]

    persisted_data = json.loads(settings_file.read_text(encoding="utf-8"))
    assert persisted_data["translator_font_size"] == 32


def test_config_service_update_settings_returns_false_on_save_failure(mocker):
    """update_settings should propagate save failures instead of reporting success."""
    config = ConfigService()
    mock_save_settings = mocker.patch.object(
        config,
        "save_settings",
        return_value=False,
    )

    result = config.update_settings({
        "ui_source_language": "en",
        "ui_target_mode": "explicit",
        "ui_target_language": "ru",
    })

    assert not result
    mock_save_settings.assert_called_once()
