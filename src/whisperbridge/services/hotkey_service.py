"""
Hotkey Service for WhisperBridge.

This module provides global hotkey registration and management using pynput.
Handles background keyboard monitoring, hotkey activation, and system integration.
"""

import threading
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from loguru import logger
from PySide6.QtCore import QThreadPool, QRunnable, Signal, QObject

try:
    from pynput import keyboard

    PYNPUT_AVAILABLE = True
except ImportError:
    logger.warning("pynput not available. Hotkey service will not function.")
    PYNPUT_AVAILABLE = False
    keyboard = None

from ..core.keyboard_manager import KeyboardManager
from ..utils.keyboard_utils import KeyboardUtils
from ..core.config import BUILD_OCR_ENABLED


class HotkeyRunnable(QRunnable):
    """QRunnable for executing hotkey handlers in QThreadPool."""

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        self.func(*self.args, **self.kwargs)


class HotkeyRegistrationError(Exception):
    """Exception raised when hotkey registration fails."""

    pass


class HotkeyService:
    """Service for managing global hotkeys using pynput with VK-reliability."""

    def __init__(self, keyboard_manager: Optional[KeyboardManager] = None):
        """Initialize the hotkey service.

        Args:
            keyboard_manager: Optional keyboard manager instance
        """
        if not PYNPUT_AVAILABLE:
            raise ImportError("pynput is required for hotkey functionality")

        self.keyboard_manager = keyboard_manager or KeyboardManager()
        self._lock = threading.RLock()
        self._running = False
        self._listener: Optional[keyboard.Listener] = None
        
        # VK-based hotkey storage
        # List of tuples: (set_of_vks, original_combination, callback)
        self._vk_hotkeys: List[Tuple[Set[int], str, Callable]] = []
        self._current_vks: Set[int] = set()
        self._triggered_combinations: Set[str] = set()
        self._paused = False

        self._executor = QThreadPool()
        self._executor.setMaxThreadCount(4)
        self._shutdown_event = threading.Event()

        # Platform-specific setup
        self._platform = KeyboardUtils.get_platform()
        self._setup_platform_specifics()

        logger.info("HotkeyService initialized (Reliable VK Mode)")

    def set_paused(self, paused: bool):
        """Pause or resume hotkey triggering.
        
        When paused, the listener still tracks key states but won't trigger any callbacks.
        """
        with self._lock:
            self._paused = paused
            if paused:
                self._current_vks.clear()
                self._triggered_combinations.clear()
            logger.debug(f"HotkeyService: {'Paused' if paused else 'Resumed'}")

    def _setup_platform_specifics(self):
        """Setup platform-specific configurations."""
        pass

    def start(self) -> bool:
        """Start the hotkey service.

        Returns:
            bool: True if started successfully, False otherwise
        """
        with self._lock:
            if self._running:
                logger.warning("Hotkey service already running")
                return True

            try:
                # Register all enabled hotkeys
                self._register_all_hotkeys()

                # Start the keyboard listener
                if self._vk_hotkeys:
                    self._listener = keyboard.Listener(
                        on_press=self._on_press_raw,
                        on_release=self._on_release_raw
                    )
                    self._listener.start()
                    self._running = True
                    logger.info(f"Hotkey service started with {len(self._vk_hotkeys)} VK-based hotkeys")
                    return True
                else:
                    logger.warning("No valid hotkeys to register")
                    return False

            except Exception as e:
                logger.error(f"Failed to start hotkey service: {e}")
                self._do_cleanup()
                return False

    def _do_cleanup(self):
        """Internal cleanup of resources (no state checks).
        
        This method only cleans up resources and should be called from
        stop(), reload_hotkeys(), and error handling in start().
        """
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._vk_hotkeys.clear()
        self._current_vks.clear()
        self._triggered_combinations.clear()

    def stop(self):
        """Stop the hotkey service."""
        with self._lock:
            if not self._running:
                return

            logger.info("Stopping hotkey service...")
            self._running = False
            self._shutdown_event.set()

            self._do_cleanup()

            logger.info("Hotkey service stopped")

    def register_application_hotkeys(self, config_service, on_translate, on_quick_translate, on_copy_translate):
        """Register default application hotkeys based on configuration.

        Args:
            config_service: The configuration service instance
            on_translate: Callback for translate hotkey
            on_quick_translate: Callback for quick translate hotkey
            on_copy_translate: Callback for copy-translate hotkey
        """
        if not self.keyboard_manager:
            return

        try:
            # Get current settings for hotkeys
            current_settings = config_service.get_settings()

            # Check whether OCR features should be enabled
            ocr_build_enabled = BUILD_OCR_ENABLED

            # Register main translation hotkey
            if ocr_build_enabled:
                self.keyboard_manager.register_hotkey(
                    current_settings.translate_hotkey,
                    on_translate,
                    "Main translation (OCR) hotkey",
                )
            
            # Register quick translate hotkey
            if current_settings.quick_translate_hotkey != current_settings.translate_hotkey:
                self.keyboard_manager.register_hotkey(
                    current_settings.quick_translate_hotkey,
                    on_quick_translate,
                    "Quick translation hotkey (overlay translator)",
                )

            # Register copy-translate hotkey
            self.keyboard_manager.register_hotkey(
                current_settings.copy_translate_hotkey,
                on_copy_translate,
                "Copy->Translate hotkey",
            )

        except Exception as e:
            logger.error(f"Failed to register default hotkeys: {e}")

    def _register_all_hotkeys(self):
        """Register all enabled hotkeys from the keyboard manager."""
        enabled_hotkeys = self.keyboard_manager.get_enabled_hotkeys()
        self._vk_hotkeys.clear()

        for combination in enabled_hotkeys:
            try:
                self._register_single_hotkey(combination)
            except Exception as e:
                logger.error(f"Failed to register hotkey '{combination}': {e}")

    def _register_single_hotkey(self, combination: str):
        """Register a single hotkey using VK codes.

        Args:
            combination: Hotkey combination to register
        """
        try:
            vks = KeyboardUtils.get_vks_for_hotkey(combination)
            if not vks:
                logger.warning(f"Could not resolve VK codes for '{combination}', layout dependency might remain.")
                return

            def on_activate():
                self._executor.start(HotkeyRunnable(self._handle_hotkey_press, combination))

            self._vk_hotkeys.append((vks, combination, on_activate))
            logger.debug(f"Registered VK-hotkey: {combination} as VKS {vks}")

        except Exception as e:
            logger.error(f"Error resolving hotkey '{combination}': {e}")

    def _on_press_raw(self, key):
        """Raw key press handler for VK state tracking."""
        if self._paused:
            return

        vk = self._get_vk_from_key(key)
        if vk is None:
            logger.trace(f"HotkeyService: Ignored press of unknown key: {key}")
            return

        with self._lock:
            self._current_vks.add(vk)
            logger.trace(f"HotkeyService: [PRESS] VK={vk} | Active VKS: {self._current_vks}")
            
            # Check for matches
            for vks, combination, callback in self._vk_hotkeys:
                if vks.issubset(self._current_vks):
                    if combination not in self._triggered_combinations:
                        logger.info(f"Hotkey TRIGGERED: {combination} (VKS match: {vks})")
                        self._triggered_combinations.add(combination)
                        callback()

    def _on_release_raw(self, key):
        """Raw key release handler for VK state tracking."""
        vk = self._get_vk_from_key(key)
        if vk is None:
            return

        with self._lock:
            self._current_vks.discard(vk)
            logger.trace(f"HotkeyService: [RELEASE] VK={vk} | Remaining VKS: {self._current_vks}")
            
            # Reset triggered state for hotkeys that are no longer fully pressed
            for vks, combination, _ in self._vk_hotkeys:
                if not vks.issubset(self._current_vks):
                    if combination in self._triggered_combinations:
                        logger.debug(f"Hotkey RELEASED: {combination}")
                        self._triggered_combinations.discard(combination)

    def _get_vk_from_key(self, key) -> Optional[int]:
        """Extract Windows VK code from a pynput key object."""
        # 1. Direct VK attribute (for characters)
        vk = getattr(key, 'vk', None)
        if vk is not None:
            return vk
        
        # 2. Virtual mapping for modifiers
        name = str(key)
        if 'ctrl' in name: return 17
        if 'alt' in name: return 18
        if 'shift' in name: return 16
        if 'cmd' in name or 'win' in name: return 91
        
        return None

    def _handle_hotkey_press(self, combination: str):
        """Handle a hotkey press event."""
        try:
            logger.debug(f"Hotkey signal: {combination}")
            self.keyboard_manager._on_hotkey_pressed_internal(combination)
        except Exception as e:
            logger.error(f"Error handling hotkey signal '{combination}': {e}")

    def reload_hotkeys(self) -> bool:
        """Reload all hotkeys."""
        with self._lock:
            if not self._running:
                return False

            try:
                self._do_cleanup()
                
                self._register_all_hotkeys()

                if self._vk_hotkeys:
                    self._listener = keyboard.Listener(
                        on_press=self._on_press_raw,
                        on_release=self._on_release_raw
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
        """Get list of currently registered hotkeys."""
        with self._lock:
            return [combo for _, combo, _ in self._vk_hotkeys]

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.stop()
