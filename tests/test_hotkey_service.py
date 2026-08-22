from threading import Event, Thread
from types import SimpleNamespace

import pytest

from whisperbridge.services.app_services import AppServices
import whisperbridge.services.hotkey_service as hotkey_module
from whisperbridge.services.hotkey_service import HotkeyService
from whisperbridge.utils.keyboard_utils import KeyboardUtils


@pytest.fixture
def hotkey_service(monkeypatch):
    monkeypatch.setattr(hotkey_module, "PYNPUT_AVAILABLE", True)
    service = HotkeyService()
    yield service
    service.stop()


def test_register_hotkey_normalizes_and_rejects_duplicates(hotkey_service, mocker, monkeypatch):
    monkeypatch.setattr(KeyboardUtils, "get_platform", lambda: "windows")
    callback = mocker.Mock()

    assert hotkey_service.register_hotkey("CTRL + SHIFT + A", callback)
    assert list(hotkey_service._hotkeys) == ["ctrl+shift+a"]
    assert not hotkey_service.register_hotkey("shift+ctrl+a", callback)
    assert not hotkey_service.register_hotkey("ctrl+unknown", callback)


def test_register_application_hotkeys_stores_callbacks_directly(
    hotkey_service, mocker, monkeypatch
):
    monkeypatch.setattr(hotkey_module, "BUILD_OCR_ENABLED", True)
    settings = SimpleNamespace(
        translate_hotkey="ctrl+shift+t",
        quick_translate_hotkey="ctrl+shift+q",
        copy_translate_hotkey="ctrl+shift+c",
    )
    config_service = mocker.Mock()
    config_service.get_settings.return_value = settings

    callbacks = [mocker.Mock() for _ in range(3)]
    hotkey_service.register_application_hotkeys(config_service, *callbacks)

    assert hotkey_service._hotkeys == {
        "ctrl+shift+t": callbacks[0],
        "ctrl+shift+q": callbacks[1],
        "ctrl+shift+c": callbacks[2],
    }


def test_hotkey_triggers_once_until_release(hotkey_service, mocker, monkeypatch):
    monkeypatch.setattr(KeyboardUtils, "get_platform", lambda: "windows")
    monkeypatch.setattr(KeyboardUtils, "get_vks_for_hotkey", lambda _: {16, 17, 65})
    callback = mocker.Mock()
    hotkey_service.register_hotkey("ctrl+shift+a", callback)
    hotkey_service._register_all_hotkeys()
    mocker.patch.object(hotkey_service._executor, "start", side_effect=lambda runnable: runnable.run())

    ctrl = SimpleNamespace(vk=17)
    shift = SimpleNamespace(vk=16)
    key_a = SimpleNamespace(vk=65)
    hotkey_service._on_press_raw(ctrl)
    hotkey_service._on_press_raw(shift)
    hotkey_service._on_press_raw(key_a)
    hotkey_service._on_press_raw(key_a)
    callback.assert_called_once_with()

    hotkey_service._on_release_raw(key_a)
    hotkey_service._on_press_raw(key_a)
    assert callback.call_count == 2


def test_multiple_hotkeys_keep_their_callbacks(hotkey_service, mocker, monkeypatch):
    monkeypatch.setattr(KeyboardUtils, "get_platform", lambda: "windows")
    vk_map = {
        "ctrl+shift+a": {16, 17, 65},
        "ctrl+shift+b": {16, 17, 66},
    }
    monkeypatch.setattr(KeyboardUtils, "get_vks_for_hotkey", vk_map.__getitem__)
    callbacks = [mocker.Mock(), mocker.Mock()]
    hotkey_service.register_hotkey("ctrl+shift+a", callbacks[0])
    hotkey_service.register_hotkey("ctrl+shift+b", callbacks[1])
    hotkey_service._register_all_hotkeys()
    queued = []
    mocker.patch.object(hotkey_service._executor, "start", side_effect=queued.append)

    for vk in (17, 16, 65, 66):
        hotkey_service._on_press_raw(SimpleNamespace(vk=vk))

    for runnable in queued:
        runnable.run()

    callbacks[0].assert_called_once_with()
    callbacks[1].assert_called_once_with()


def test_hotkey_callback_does_not_hold_service_lock(hotkey_service):
    callback_started = Event()
    allow_callback_to_finish = Event()

    def callback():
        callback_started.set()
        allow_callback_to_finish.wait(timeout=2)

    callback_thread = Thread(
        target=hotkey_service._run_hotkey_callback,
        args=(callback, "ctrl+shift+a", hotkey_service._generation),
    )
    callback_thread.start()
    assert callback_started.wait(timeout=1)

    pause_thread = Thread(target=lambda: hotkey_service.set_paused(True))
    pause_thread.start()
    try:
        pause_thread.join(timeout=0.2)
        assert not pause_thread.is_alive()
    finally:
        allow_callback_to_finish.set()
        callback_thread.join(timeout=1)
        pause_thread.join(timeout=1)


def test_clear_hotkeys_skips_queued_callback(hotkey_service, mocker, monkeypatch):
    monkeypatch.setattr(KeyboardUtils, "get_platform", lambda: "windows")
    monkeypatch.setattr(KeyboardUtils, "get_vks_for_hotkey", lambda _: {16, 17, 65})
    callback = mocker.Mock()
    queued = []
    hotkey_service.register_hotkey("ctrl+shift+a", callback)
    hotkey_service._register_all_hotkeys()
    mocker.patch.object(hotkey_service._executor, "start", side_effect=queued.append)

    hotkey_service._on_press_raw(SimpleNamespace(vk=17))
    hotkey_service._on_press_raw(SimpleNamespace(vk=16))
    hotkey_service._on_press_raw(SimpleNamespace(vk=65))
    hotkey_service.clear_hotkeys()

    queued[0].run()
    callback.assert_not_called()


def test_pause_skips_queued_callback(hotkey_service, mocker, monkeypatch):
    monkeypatch.setattr(KeyboardUtils, "get_platform", lambda: "windows")
    monkeypatch.setattr(KeyboardUtils, "get_vks_for_hotkey", lambda _: {16, 17, 65})
    callback = mocker.Mock()
    queued = []
    hotkey_service.register_hotkey("ctrl+shift+a", callback)
    hotkey_service._register_all_hotkeys()
    mocker.patch.object(hotkey_service._executor, "start", side_effect=queued.append)

    hotkey_service._on_press_raw(SimpleNamespace(vk=17))
    hotkey_service._on_press_raw(SimpleNamespace(vk=16))
    hotkey_service._on_press_raw(SimpleNamespace(vk=65))
    hotkey_service.set_paused(True)

    queued[0].run()
    callback.assert_not_called()


def test_reload_without_resolvable_hotkeys_resets_running_state(hotkey_service, mocker, monkeypatch):
    monkeypatch.setattr(KeyboardUtils, "get_vks_for_hotkey", lambda _: set())
    hotkey_service._running = True
    hotkey_service._listener = mocker.Mock()

    assert not hotkey_service.reload_hotkeys()
    assert not hotkey_service.is_running()
    assert hotkey_service._listener is None


def test_reload_listener_failure_cleans_up(hotkey_service, mocker, monkeypatch):
    monkeypatch.setattr(KeyboardUtils, "get_platform", lambda: "windows")
    monkeypatch.setattr(KeyboardUtils, "get_vks_for_hotkey", lambda _: {16, 17, 65})
    hotkey_service.register_hotkey("ctrl+shift+a", mocker.Mock())
    hotkey_service._running = True
    hotkey_service._listener = mocker.Mock()
    new_listener = mocker.Mock()
    new_listener.start.side_effect = RuntimeError("listener failed")
    mocker.patch.object(hotkey_module.keyboard, "Listener", return_value=new_listener)

    assert not hotkey_service.reload_hotkeys()
    assert not hotkey_service.is_running()
    assert hotkey_service._listener is None


def test_app_services_reload_uses_hotkey_service_as_single_owner(mocker):
    services = AppServices.__new__(AppServices)
    services.hotkey_service = mocker.Mock()
    services.hotkey_service.is_running.return_value = True
    services.hotkey_service.reload_hotkeys.return_value = True
    services.on_translate = mocker.Mock()
    services.on_quick_translate = mocker.Mock()
    services.on_copy_translate = mocker.Mock()
    config_service = mocker.patch("whisperbridge.services.app_services.config_service")

    services.reload_hotkeys()

    services.hotkey_service.clear_hotkeys.assert_called_once_with()
    services.hotkey_service.register_application_hotkeys.assert_called_once_with(
        config_service=config_service,
        on_translate=services.on_translate,
        on_quick_translate=services.on_quick_translate,
        on_copy_translate=services.on_copy_translate,
    )
    services.hotkey_service.reload_hotkeys.assert_called_once_with()


def test_app_services_starts_service_after_failed_reload(mocker):
    services = AppServices.__new__(AppServices)
    services.hotkey_service = mocker.Mock()
    services.hotkey_service.is_running.return_value = False
    services.hotkey_service.start.return_value = True
    services.on_translate = mocker.Mock()
    services.on_quick_translate = mocker.Mock()
    services.on_copy_translate = mocker.Mock()
    config_service = mocker.patch("whisperbridge.services.app_services.config_service")

    services.reload_hotkeys()

    services.hotkey_service.clear_hotkeys.assert_called_once_with()
    services.hotkey_service.start.assert_called_once_with()
    services.hotkey_service.reload_hotkeys.assert_not_called()
    services.hotkey_service.register_application_hotkeys.assert_called_once_with(
        config_service=config_service,
        on_translate=services.on_translate,
        on_quick_translate=services.on_quick_translate,
        on_copy_translate=services.on_copy_translate,
    )
