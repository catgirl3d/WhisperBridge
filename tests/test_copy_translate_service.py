from types import ModuleType, SimpleNamespace
from unittest.mock import call

from whisperbridge.services.copy_translate_service import CopyTranslateService


def _make_get_setting(values):
    def _get_setting(key, use_cache=False):
        value = values.get(key)
        if isinstance(value, Exception):
            raise value
        return value

    return _get_setting


def _patch_copy_environment(mocker):
    controller = mocker.Mock(name="controller")
    c_key = object()

    keyboard_module = ModuleType("pynput.keyboard")
    setattr(keyboard_module, "Controller", mocker.Mock(return_value=controller))
    setattr(keyboard_module, "Key", SimpleNamespace(ctrl="ctrl"))
    setattr(keyboard_module, "KeyCode", SimpleNamespace(from_vk=mocker.Mock(return_value=c_key)))

    pynput_module = ModuleType("pynput")
    setattr(pynput_module, "__path__", [])
    setattr(pynput_module, "keyboard", keyboard_module)

    keyboard_utils_module = ModuleType("whisperbridge.utils.keyboard_utils")
    setattr(keyboard_utils_module, "WIN_VK_MAP", {"c": 67})

    mocker.patch.dict(
        "sys.modules",
        {
            "pynput": pynput_module,
            "pynput.keyboard": keyboard_module,
            "whisperbridge.utils.keyboard_utils": keyboard_utils_module,
        },
    )
    mocker.patch("time.sleep", return_value=None)
    mocker.patch("platform.system", return_value="linux")

    return SimpleNamespace(controller=controller, c_key=c_key)


def _build_service(qapp, mocker):
    patched = _patch_copy_environment(mocker)

    clipboard_service = mocker.Mock()
    config_service = mocker.Mock()
    config_service.get_settings.return_value = SimpleNamespace(
        auto_swap_en_ru=False,
        ui_source_language="auto",
        ui_target_language="uk",
    )
    translation_service = mocker.Mock()
    hotkey_service = mocker.Mock()
    logger = mocker.Mock()
    notification_service = mocker.Mock()

    service = CopyTranslateService(
        clipboard_service=clipboard_service,
        config_service=config_service,
        translation_service=translation_service,
        hotkey_service=hotkey_service,
        debug_logger=logger,
    )
    service._notification_service = notification_service

    emitted = []
    service.result_ready.connect(lambda original, translated, auto_copy: emitted.append((original, translated, auto_copy)))

    return SimpleNamespace(
        service=service,
        clipboard_service=clipboard_service,
        config_service=config_service,
        translation_service=translation_service,
        hotkey_service=hotkey_service,
        logger=logger,
        notification_service=notification_service,
        emitted=emitted,
        controller=patched.controller,
        c_key=patched.c_key,
    )


def test_run_emits_original_text_when_api_key_is_missing(qapp, mocker):
    ctx = _build_service(qapp, mocker)
    ctx.clipboard_service.get_clipboard_text.side_effect = ["old text", "selected text"]
    ctx.config_service.get_setting.side_effect = _make_get_setting(
        {
            "clipboard_poll_timeout_ms": 200,
            "api_provider": "openai",
            "openai_api_key": None,
            "google_api_key": None,
        }
    )

    ctx.service.run()

    assert ctx.emitted == [("selected text", "", False)]
    ctx.translation_service.detect_language_sync.assert_not_called()
    ctx.translation_service.translate_text_sync.assert_not_called()
    assert ctx.hotkey_service.set_paused.call_args_list == [call(True), call(False)]
    ctx.notification_service.info.assert_not_called()
    ctx.notification_service.warning.assert_not_called()
    ctx.notification_service.error.assert_not_called()


def test_run_translates_with_auto_swap_and_auto_copy(qapp, mocker):
    ctx = _build_service(qapp, mocker)
    ctx.clipboard_service.get_clipboard_text.side_effect = ["old text", "selected text"]
    ctx.config_service.get_setting.side_effect = _make_get_setting(
        {
            "clipboard_poll_timeout_ms": 200,
            "api_provider": "openai",
            "openai_api_key": "sk-test",
            "google_api_key": None,
            "auto_copy_translated": True,
        }
    )
    ctx.config_service.get_settings.return_value = SimpleNamespace(
        auto_swap_en_ru=True,
        ui_source_language="auto",
        ui_target_language="uk",
    )
    ctx.translation_service.detect_language_sync.return_value = "en"
    ctx.translation_service.translate_text_sync.return_value = SimpleNamespace(translated_text="Привіт")

    ctx.service.run()

    ctx.translation_service.detect_language_sync.assert_called_once_with("selected text")
    ctx.translation_service.translate_text_sync.assert_called_once_with(
        "selected text",
        source_lang="auto",
        target_lang="ru",
    )
    assert ctx.emitted == [("selected text", "Привіт", True)]
    assert ctx.hotkey_service.set_paused.call_args_list == [call(True), call(False)]
    ctx.notification_service.info.assert_called_once_with("Translating...", "WhisperBridge")
    ctx.notification_service.warning.assert_not_called()
    ctx.notification_service.error.assert_not_called()


def test_run_falls_back_to_default_translation_when_detection_fails(qapp, mocker):
    ctx = _build_service(qapp, mocker)
    ctx.clipboard_service.get_clipboard_text.side_effect = ["old text", "selected text"]
    ctx.config_service.get_setting.side_effect = _make_get_setting(
        {
            "clipboard_poll_timeout_ms": 200,
            "api_provider": "openai",
            "openai_api_key": "sk-test",
            "google_api_key": None,
            "auto_copy_translated": RuntimeError("config read failed"),
        }
    )
    ctx.translation_service.detect_language_sync.side_effect = RuntimeError("detect failed")
    ctx.translation_service.translate_text_sync.return_value = "Fallback translation"

    ctx.service.run()

    ctx.translation_service.translate_text_sync.assert_called_once_with("selected text")
    assert ctx.emitted == [("selected text", "Fallback translation", False)]
    ctx.notification_service.info.assert_called_once_with("Translating...", "WhisperBridge")
    ctx.notification_service.warning.assert_not_called()
    ctx.notification_service.error.assert_not_called()


def test_run_warns_when_clipboard_content_does_not_change(qapp, mocker):
    ctx = _build_service(qapp, mocker)
    ctx.clipboard_service.get_clipboard_text.side_effect = ["same text", "same text"]
    ctx.config_service.get_setting.side_effect = _make_get_setting(
        {
            "clipboard_poll_timeout_ms": 0,
        }
    )

    ctx.service.run()

    assert ctx.emitted == []
    ctx.translation_service.detect_language_sync.assert_not_called()
    ctx.translation_service.translate_text_sync.assert_not_called()
    assert ctx.hotkey_service.set_paused.call_args_list == [call(True), call(False)]
    ctx.notification_service.warning.assert_called_once_with(
        "Copy-translate failed: no clipboard text detected",
        "WhisperBridge",
    )
    ctx.notification_service.info.assert_not_called()
    ctx.notification_service.error.assert_not_called()


def test_run_reports_missing_clipboard_service(qapp, mocker):
    ctx = _build_service(qapp, mocker)
    ctx.service.clipboard_service = None

    ctx.service.run()

    assert ctx.emitted == []
    ctx.hotkey_service.set_paused.assert_not_called()
    ctx.notification_service.error.assert_called_once_with(
        "Copy-translate failed: clipboard service unavailable",
        "WhisperBridge",
    )
    ctx.notification_service.info.assert_not_called()
    ctx.notification_service.warning.assert_not_called()
