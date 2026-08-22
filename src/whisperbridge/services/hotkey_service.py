"""
Global hotkey service for WhisperBridge.

Owns hotkey registration, VK-based keyboard monitoring, and callback dispatch.
"""

import threading
from typing import Callable, Dict, List, Optional, Set, Tuple

from loguru import logger
from PySide6.QtCore import QRunnable, QThreadPool

try:
    from pynput import keyboard

    PYNPUT_AVAILABLE = True
except ImportError:
    logger.warning("pynput not available. Hotkey service will not function.")
    PYNPUT_AVAILABLE = False
    keyboard = None

from ..core.config import BUILD_OCR_ENABLED
from ..utils.keyboard_utils import KeyboardUtils


class HotkeyRunnable(QRunnable):
    """Run a hotkey callback in Qt's thread pool."""

    def __init__(self, callback: Callable[[], None], combination: str):
        super().__init__()
        self._callback = callback
        self._combination = combination

    def run(self):
        try:
            self._callback()
        except Exception as e:
            logger.error(f"Error executing hotkey callback for '{self._combination}': {e}")


class HotkeyService:
    """Manage global hotkeys using pynput and Windows virtual-key codes."""

    def __init__(self):
        if not PYNPUT_AVAILABLE:
            raise ImportError("pynput is required for hotkey functionality")

        self._lock = threading.RLock()
        self._hotkeys: Dict[str, Callable[[], None]] = {}
        self._vk_hotkeys: List[Tuple[Set[int], str, Callable[[], None]]] = []
        self._current_vks: Set[int] = set()
        self._triggered_combinations: Set[str] = set()
        self._paused = False
        self._running = False
        self._listener: Optional[keyboard.Listener] = None

        self._executor = QThreadPool()
        self._executor.setMaxThreadCount(4)

        logger.info("HotkeyService initialized (Reliable VK Mode)")

    def register_hotkey(self, combination: str, callback: Callable[[], None]) -> bool:
        """Validate and register an application hotkey."""
        with self._lock:
            try:
                is_valid, error = KeyboardUtils.validate_hotkey(combination)
                if not is_valid:
                    logger.error(f"Invalid hotkey '{combination}': {error}")
                    return False

                normalized = KeyboardUtils.normalize_hotkey(combination)
                if normalized in self._hotkeys:
                    logger.warning(f"Hotkey '{normalized}' already registered")
                    return False

                self._hotkeys[normalized] = callback
                logger.info(f"Hotkey registered: {normalized}")
                return True
            except Exception as e:
                logger.error(f"Failed to register hotkey '{combination}': {e}")
                return False

    def clear_hotkeys(self):
        """Remove all registered application hotkeys."""
        with self._lock:
            self._hotkeys.clear()
            logger.info("All hotkeys cleared")

    def set_paused(self, paused: bool):
        """Pause or resume hotkey triggering."""
        with self._lock:
            self._paused = paused
            if paused:
                self._current_vks.clear()
                self._triggered_combinations.clear()
            logger.debug(f"HotkeyService: {'Paused' if paused else 'Resumed'}")

    def start(self) -> bool:
        """Start the global keyboard listener."""
        with self._lock:
            if self._running:
                logger.warning("Hotkey service already running")
                return True

            try:
                self._register_all_hotkeys()
                if not self._vk_hotkeys:
                    logger.warning("No valid hotkeys to register")
                    return False

                self._listener = keyboard.Listener(
                    on_press=self._on_press_raw,
                    on_release=self._on_release_raw,
                )
                self._listener.start()
                self._running = True
                logger.info(f"Hotkey service started with {len(self._vk_hotkeys)} VK-based hotkeys")
                return True
            except Exception as e:
                logger.error(f"Failed to start hotkey service: {e}")
                self._do_cleanup()
                return False

    def stop(self):
        """Stop the global keyboard listener."""
        with self._lock:
            if not self._running:
                return

            logger.info("Stopping hotkey service...")
            self._running = False
            self._do_cleanup()
            logger.info("Hotkey service stopped")

    def register_application_hotkeys(
        self,
        config_service,
        on_translate,
        on_quick_translate,
        on_copy_translate,
    ):
        """Register the application's configured hotkeys."""
        try:
            current_settings = config_service.get_settings()

            if BUILD_OCR_ENABLED:
                self.register_hotkey(current_settings.translate_hotkey, on_translate)

            if current_settings.quick_translate_hotkey != current_settings.translate_hotkey:
                self.register_hotkey(current_settings.quick_translate_hotkey, on_quick_translate)

            self.register_hotkey(current_settings.copy_translate_hotkey, on_copy_translate)
        except Exception as e:
            logger.error(f"Failed to register default hotkeys: {e}")

    def _register_all_hotkeys(self):
        """Resolve registered combinations to VK codes."""
        self._vk_hotkeys.clear()
        for combination, callback in self._hotkeys.items():
            try:
                vks = KeyboardUtils.get_vks_for_hotkey(combination)
                if not vks:
                    logger.warning(
                        f"Could not resolve VK codes for '{combination}', layout dependency might remain."
                    )
                    continue

                self._vk_hotkeys.append((vks, combination, callback))
                logger.debug(f"Registered VK-hotkey: {combination} as VKS {vks}")
            except Exception as e:
                logger.error(f"Failed to register hotkey '{combination}': {e}")

    def _do_cleanup(self):
        """Release listener resources and transient key state."""
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._vk_hotkeys.clear()
        self._current_vks.clear()
        self._triggered_combinations.clear()

    def _on_press_raw(self, key):
        """Track a raw key press and trigger matching callbacks once."""
        if self._paused:
            return

        vk = self._get_vk_from_key(key)
        if vk is None:
            logger.trace(f"HotkeyService: Ignored press of unknown key: {key}")
            return

        with self._lock:
            self._current_vks.add(vk)
            logger.trace(f"HotkeyService: [PRESS] VK={vk} | Active VKS: {self._current_vks}")

            for vks, combination, callback in self._vk_hotkeys:
                if vks.issubset(self._current_vks) and combination not in self._triggered_combinations:
                    logger.info(f"Hotkey TRIGGERED: {combination} (VKS match: {vks})")
                    self._triggered_combinations.add(combination)
                    self._executor.start(HotkeyRunnable(callback, combination))

    def _on_release_raw(self, key):
        """Track a raw key release and re-arm released combinations."""
        vk = self._get_vk_from_key(key)
        if vk is None:
            return

        with self._lock:
            self._current_vks.discard(vk)
            logger.trace(f"HotkeyService: [RELEASE] VK={vk} | Remaining VKS: {self._current_vks}")

            for vks, combination, _ in self._vk_hotkeys:
                if not vks.issubset(self._current_vks):
                    self._triggered_combinations.discard(combination)

    def _get_vk_from_key(self, key) -> Optional[int]:
        """Extract a Windows VK code from a pynput key object."""
        vk = getattr(key, "vk", None)
        if vk is not None:
            return vk

        name = str(key)
        if "ctrl" in name:
            return 17
        if "alt" in name:
            return 18
        if "shift" in name:
            return 16
        if "cmd" in name or "win" in name:
            return 91
        return None

    def reload_hotkeys(self) -> bool:
        """Rebuild VK mappings and restart the listener."""
        with self._lock:
            if not self._running:
                return False

            try:
                self._do_cleanup()
                self._register_all_hotkeys()

                if self._vk_hotkeys:
                    self._listener = keyboard.Listener(
                        on_press=self._on_press_raw,
                        on_release=self._on_release_raw,
                    )
                    self._listener.start()

                logger.info("Hotkeys reloaded (VK-based)")
                return True
            except Exception as e:
                logger.error(f"Failed to reload hotkeys: {e}")
                return False

    def is_running(self) -> bool:
        """Check if the hotkey service is running."""
        return self._running

    def get_registered_hotkeys(self) -> List[str]:
        """Get combinations currently resolved for the listener."""
        with self._lock:
            return [combination for _, combination, _ in self._vk_hotkeys]

    def __del__(self):
        """Ensure listener cleanup during object destruction."""
        self.stop()
