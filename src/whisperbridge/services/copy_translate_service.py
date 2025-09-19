"""
Copy-Translate Service

Extracted from QtApp._on_copy_translate_hotkey in src/whisperbridge/ui_qt/app.py

This service encapsulates the logic for handling the copy-translate hotkey. It performs simulated Ctrl+C copy (fallback), polls the clipboard, detects language, translates if possible, and emits a result signal with the original text, translated text, and auto-copy flag. Preserves all original behavior, including notifications, logging, and error handling.
"""

from PySide6.QtCore import QObject, Signal

from ..services.config_service import config_service as _config_service
from ..services.clipboard_service import get_clipboard_service
from ..services.translation_service import get_translation_service


class CopyTranslateService(QObject):
    result_ready = Signal(str, str, bool)  # (clipboard_text, translated_text, auto_copy)

    def __init__(self, tray_manager=None, clipboard_service=None, config_service=None, translation_service=None, debug_logger=None):
        super().__init__()
        self.tray_manager = tray_manager
        self.clipboard_service = clipboard_service or get_clipboard_service()
        self.config_service = config_service or _config_service  # Use global if not provided
        self.translation_service = translation_service or get_translation_service()
        self.debug_logger = debug_logger

    def run(self):
        import time
        from loguru import logger
        log = self.debug_logger or logger

        log.info("Copy-translate hotkey pressed (fallback-only handler)")
        # Performance timing points (perf_counter for high-resolution timing)
        t_start = time.perf_counter()
        t_after_sim = None
        t_after_poll_success = None
        t_after_translation = None

        try:
            import platform
            # Determine platform once for use in fallback logic
            system = platform.system().lower()

            # Fallback-only approach: simulate Ctrl+C and read clipboard
            try:
                from pynput.keyboard import Controller, Key
                controller = Controller()
            except ImportError:
                log.error("pynput not available for copy-translate fallback")
                if self.tray_manager:
                    self.tray_manager.show_notification(
                        "WhisperBridge",
                        "Copy-translate failed: pynput not installed"
                    )
                # Log final summary with zeros since we didn't proceed
                t_end = time.perf_counter()
                log.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                return

            # Prepare clipboard service and read previous content BEFORE simulating copy
            if self.clipboard_service is None:
                log.error("Clipboard service not available; aborting copy-translate")
                if self.tray_manager:
                    self.tray_manager.show_notification(
                        "WhisperBridge",
                        "Copy-translate failed: clipboard service unavailable"
                    )
                t_end = time.perf_counter()
                log.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                return
            prev_clip = self.clipboard_service.get_clipboard_text() or ""

            # Increased pre-delay to allow user to release modifiers (prevent accidental physical modifiers)
            pre_delay = 0.4  # seconds
            time.sleep(pre_delay)

            # On Windows, wait for physical Ctrl to be released before proceeding
            if system == 'windows':
                try:
                    import ctypes
                    VK_CONTROL = 0x11
                    release_timeout = 1.5
                    release_interval = 0.05
                    release_elapsed = 0.0
                    try:
                        ctrl_down = bool(ctypes.windll.user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                    except Exception:
                        ctrl_down = False
                    if ctrl_down:
                        log.debug("Physical Ctrl detected down; waiting for release before simulating copy")
                        while release_elapsed < release_timeout:
                            try:
                                if not (ctypes.windll.user32.GetAsyncKeyState(VK_CONTROL) & 0x8000):
                                    break
                            except Exception:
                                # If we can't query state, stop waiting and proceed
                                break
                            time.sleep(release_interval)
                            release_elapsed += release_interval
                        # Re-check
                        try:
                            still_down = bool(ctypes.windll.user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                        except Exception:
                            still_down = False
                        if still_down:
                            log.info("Physical Ctrl key still down after waiting; aborting copy-translate to avoid accidental trigger")
                            if self.tray_manager:
                                self.tray_manager.show_notification(
                                    "WhisperBridge",
                                    "Copy-translate aborted: physical Ctrl key held down"
                                )
                            t_end = time.perf_counter()
                            log.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                            return
                except Exception as e_ctrl_wait:
                    log.debug(f"Failed to detect/wait for Ctrl key state: {e_ctrl_wait}")

            try:
                log.debug("Starting fallback simulated Ctrl+C copy")
                # Always send Ctrl down, send 'c', then Ctrl up.
                controller.press(Key.ctrl)
                controller.press('c')
                controller.release('c')
                controller.release(Key.ctrl)
                # Mark after-simulation timepoint
                t_after_sim = time.perf_counter()
            except Exception as e:
                log.error(f"Fallback copy simulation failed: {e}")
                if self.tray_manager:
                    self.tray_manager.show_notification(
                        "WhisperBridge",
                        f"Copy-translate fallback failed: {e}"
                    )
                t_end = time.perf_counter()
                log.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                return

            # Short pause to allow OS to update clipboard
            time.sleep(0.08)

            # Poll clipboard for changed content using exponential backoff and configurable timeout.
            # Read timeout from config (milliseconds) and convert to seconds.
            try:
                timeout_ms = self.config_service.get_setting("clipboard_poll_timeout_ms", use_cache=False)
                timeout_ms = int(timeout_ms) if timeout_ms is not None else 2000
            except Exception as e:
                log.debug(f"Failed to read clipboard_poll_timeout_ms from config; using default 2000ms: {e}")
                timeout_ms = 2000
            timeout = float(timeout_ms) / 1000.0

            # Exponential backoff parameters
            start_delay = 0.05
            max_delay = 0.2
            backoff_factor = 2.0

            log.debug(f"Starting clipboard polling with timeout={timeout:.3f}s (configured {timeout_ms}ms), start_delay={start_delay}s, max_delay={max_delay}s")

            poll_start = time.perf_counter()
            attempts = 0
            delay = start_delay
            new_clip = prev_clip
            # Poll until timeout using exponential backoff
            while True:
                attempts += 1
                elapsed = time.perf_counter() - poll_start
                log.debug(f"Clipboard poll attempt #{attempts}: elapsed={elapsed:.3f}s, delay={delay:.3f}s")

                new_clip = self.clipboard_service.get_clipboard_text() or ""
                if new_clip and new_clip != prev_clip:
                    t_after_poll_success = time.perf_counter()
                    duration = t_after_poll_success - poll_start
                    log.info(f"Fallback simulated copy succeeded after {attempts} attempts in {duration:.3f}s")
                    break

                # Check if we would exceed timeout with the next sleep
                if (time.perf_counter() - poll_start + delay) >= timeout:
                    log.debug(f"Would exceed timeout with next delay ({delay:.3f}s), stopping polling")
                    break

                # Sleep using the current backoff delay
                time.sleep(delay)
                # Increase delay for next attempt
                delay = min(delay * backoff_factor, max_delay)

            # If simulation did not change clipboard, abort — only translate when clipboard changed.
            if not new_clip or new_clip == prev_clip:
                t_after_poll_success = time.perf_counter()
                total_elapsed = t_after_poll_success - t_start
                log.info(f"No new clipboard text detected after polling; timeout reached (elapsed={total_elapsed:.3f}s, attempts={attempts})")
                if self.tray_manager:
                    self.tray_manager.show_notification(
                        "WhisperBridge",
                        "Copy-translate failed: no clipboard text detected"
                    )
                # Performance summary: clipboard time measured from simulation to poll end, translation 0
                clipboard_ms = ((t_after_poll_success - (t_after_sim or t_start)) * 1000) if t_after_sim else 0
                t_end = time.perf_counter()
                total_ms = (t_end - t_start) * 1000
                log.info(f"Copy-translate performance: clipboard={clipboard_ms:.0f}ms, translation=0ms, total={total_ms:.0f}ms")
                return

            # At this point new_clip contains the text to translate (from clipboard)
            text_to_translate = new_clip
            if not text_to_translate:
                log.info("No text to translate (empty selection)")
                if self.tray_manager:
                    self.tray_manager.show_notification(
                        "WhisperBridge",
                        "Copy-translate: no text selected to translate"
                    )
                t_end = time.perf_counter()
                log.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                return

            # Check for API key presence before attempting translation
            api_key = self.config_service.get_setting("openai_api_key", use_cache=False)
            if not api_key:
                log.info("No API key configured, showing original text only")
                # Emit overlay with original text only (no translation attempt)
                # Performance summary: compute clipboard time, translation=0
                clipboard_ms = ((t_after_poll_success - (t_after_sim or t_start)) * 1000) if t_after_poll_success and t_after_sim else 0
                t_end = time.perf_counter()
                total_ms = (t_end - t_start) * 1000
                log.info(f"Copy-translate performance: clipboard={clipboard_ms:.0f}ms, translation=0ms, total={total_ms:.0f}ms")
                self.result_ready.emit(text_to_translate, "", False)
                log.info("Copy-translate overlay shown (original text only) due to missing API key")
                return

            # Translate text synchronously (respect ocr_auto_swap_en_ru setting) — with debug logs and live config check
            try:
                # Try to detect language and apply EN<->RU auto-swap if enabled in settings
                from ..utils.api_utils import detect_language

                log.debug(f"Copy-translate: text length={len(text_to_translate)}")
                detected = detect_language(text_to_translate) or "auto"
                log.debug(f"Copy-translate: detected language='{detected}'")

                # Read current settings live from config_service to respect UI changes
                swap_enabled = bool(self.config_service.get_setting("ocr_auto_swap_en_ru", use_cache=False))
                target_cfg = self.config_service.get_setting("target_language", use_cache=False) or "en"
                log.debug(f"Copy-translate: ocr_auto_swap_en_ru={swap_enabled}, configured target='{target_cfg}'")

                if swap_enabled:
                    if detected == "en":
                        target = "ru"
                    elif detected == "ru":
                        target = "en"
                    else:
                        target = target_cfg
                    log.debug(f"Copy-translate: auto-swap active — translating from '{detected}' to '{target}'")
                    # Show a brief translating notification
                    try:
                        if self.tray_manager:
                            self.tray_manager.show_notification("WhisperBridge", "Translating...")
                    except Exception:
                        pass
                    response = self.translation_service.translate_text_sync(
                        text_to_translate, source_lang=detected, target_lang=target
                    )
                else:
                    log.debug(f"Copy-translate: auto-swap disabled — using configured target '{target_cfg}'")
                    # Show a brief translating notification
                    try:
                        if self.tray_manager:
                            self.tray_manager.show_notification("WhisperBridge", "Translating...")
                    except Exception:
                        pass
                    response = self.translation_service.translate_text_sync(
                        text_to_translate, source_lang=detected if detected != "auto" else None, target_lang=target_cfg
                    )
            except Exception as exc:
                log.error(f"Copy-translate: error during language detection/auto-swap: {exc}", exc_info=True)
                # Fallback to default translation call on any failure
                try:
                    if self.tray_manager:
                        self.tray_manager.show_notification("WhisperBridge", "Translating...")
                except Exception:
                    pass
                response = self.translation_service.translate_text_sync(text_to_translate)

            # Mark translation completion time
            t_after_translation = time.perf_counter()

            translated_text = getattr(response, "translated_text", None) or str(response)

            # Read auto_copy_translated setting live and set pending flag so main thread can copy AFTER overlay is shown
            try:
                auto_copy = bool(self.config_service.get_setting("auto_copy_translated", use_cache=False))
            except Exception as e:
                log.debug(f"Failed to read auto_copy_translated setting: {e}")
                auto_copy = False

            # Performance summary: compute clipboard and translation durations and log once
            clipboard_ms = ((t_after_poll_success - (t_after_sim or t_start)) * 1000) if (t_after_poll_success and t_after_sim) else 0
            translation_ms = ((t_after_translation - t_after_poll_success) * 1000) if (t_after_translation and t_after_poll_success) else 0
            t_end = time.perf_counter()
            total_ms = (t_end - t_start) * 1000
            log.info(f"Copy-translate performance: clipboard={clipboard_ms:.0f}ms, translation={translation_ms:.0f}ms, total={total_ms:.0f}ms")

            # Emit signal to show overlay from main thread
            self.result_ready.emit(text_to_translate, translated_text, auto_copy)
            log.info("Copy-translate hotkey processed successfully (fallback simulated copy path)")
        except Exception as e:
            log.error(f"Error in copy-translate hotkey handler: {e}", exc_info=True)
            if self.tray_manager:
                self.tray_manager.show_notification(
                    "WhisperBridge",
                    f"Copy-translate error: {str(e)}"
                )
            # Ensure we still log performance summary on unexpected errors
            try:
                t_end = time.perf_counter()
                total_ms = (t_end - t_start) * 1000
                # If we had poll or sim times, include them; else set to 0
                clipboard_ms = ((t_after_poll_success - (t_after_sim or t_start)) * 1000) if (t_after_poll_success and t_after_sim) else 0
                translation_ms = ((t_after_translation - t_after_poll_success) * 1000) if (t_after_translation and t_after_poll_success) else 0
                log.info(f"Copy-translate performance: clipboard={clipboard_ms:.0f}ms, translation={translation_ms:.0f}ms, total={total_ms:.0f}ms")
            except Exception:
                pass