"""
Copy-Translate Service

This service encapsulates the logic for handling the copy-translate hotkey. It performs
a simulated Ctrl+C copy to capture the selected text, polls the clipboard, detects language,
translates if possible, and emits a result signal with the original text, translated text, and
auto-copy flag. Preserves all original behavior, including notifications, logging,
and error handling.
"""

from PySide6.QtCore import QObject, Signal

from ..services.clipboard_service import get_clipboard_service
from ..services.config_service import config_service as _config_service
from ..services.translation_service import get_translation_service


class CopyTranslateService(QObject):
    result_ready = Signal(str, str, bool)  # (clipboard_text, translated_text, auto_copy)

    def __init__(
        self,
        tray_manager=None,
        clipboard_service=None,
        config_service=None,
        translation_service=None,
        debug_logger=None,
    ):
        super().__init__()
        self.tray_manager = tray_manager
        self.clipboard_service = clipboard_service or get_clipboard_service()
        self.config_service = config_service or _config_service  # Use global if not provided
        self.translation_service = translation_service or get_translation_service()
        self.debug_logger = debug_logger
        self._notification_service = None

    @property
    def notification_service(self):
        """Lazy getter for notification service to avoid circular imports."""
        if self._notification_service is None:
            from ..services.notification_service import get_notification_service
            self._notification_service = get_notification_service()
        return self._notification_service

    def run(self):
        import time

        from loguru import logger

        log = self.debug_logger or logger

        log.info("Copy-translate hotkey pressed (simulated copy handler)")
        # Performance timing points (perf_counter for high-resolution timing)
        t_start = time.perf_counter()
        t_after_sim = None
        t_after_poll_success = None
        t_after_translation = None

        try:
            import platform

            # Determine platform once for use in platform-specific logic
            system = platform.system().lower()

            # Fallback-only approach: simulate Ctrl+C and read clipboard
            try:
                from pynput.keyboard import Controller, Key

                controller = Controller()
            except ImportError:
                log.error("pynput not available for copy-translate simulated copy")
                self.notification_service.error("Copy-translate failed: pynput not installed", "WhisperBridge")
                # Log final summary with zeros since we didn't proceed
                t_end = time.perf_counter()
                log.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                return

            # Prepare clipboard service and read previous content BEFORE simulating copy
            if self.clipboard_service is None:
                log.error("Clipboard service not available; aborting copy-translate")
                self.notification_service.error("Copy-translate failed: clipboard service unavailable", "WhisperBridge")
                t_end = time.perf_counter()
                log.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                return
            prev_clip = self.clipboard_service.get_clipboard_text() or ""

            # Increased pre-delay to allow user to release modifiers (prevent accidental physical modifiers)
            pre_delay = 0.4  # seconds
            time.sleep(pre_delay)

            # On Windows, wait for physical Ctrl to be released before proceeding
            if system == "windows":
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
                            self.notification_service.warning("Copy-translate aborted: physical Ctrl key held down", "WhisperBridge")
                            t_end = time.perf_counter()
                            log.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                            return
                except Exception as e_ctrl_wait:
                    log.debug(f"Failed to detect/wait for Ctrl key state: {e_ctrl_wait}")

            try:
                log.debug("Starting simulated Ctrl+C copy")
                sim_start = time.perf_counter()
                log.debug("Simulated copy step: press ctrl")
                controller.press(Key.ctrl)
                log.debug("Simulated copy step: press c")
                controller.press("c")
                log.debug("Simulated copy step: release c")
                controller.release("c")
                log.debug("Simulated copy step: release ctrl")
                controller.release(Key.ctrl)
                # Mark after-simulation timepoint
                t_after_sim = time.perf_counter()
                log.debug(f"Simulated copy sequence finished in {(t_after_sim - sim_start) * 1000:.2f}ms")
            except Exception as e:
                log.error(f"Fallback copy simulation failed: {e}")
                self.notification_service.error(f"Copy-translate copy simulation failed: {e}", "WhisperBridge")
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
                    log.info(f"Simulated copy succeeded after {attempts} attempts in {duration:.3f}s")
                    prev_len = len(prev_clip)
                    new_len = len(new_clip)
                    prev_sample = prev_clip[:40] + ("…" if prev_len > 40 else "")
                    new_sample = new_clip[:40] + ("…" if new_len > 40 else "")
                    log.debug(
                        "Clipboard content changed: prev_len={} new_len={} prev_sample={!r} new_sample={!r}",
                        prev_len,
                        new_len,
                        prev_sample,
                        new_sample,
                    )
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
                prev_len = len(prev_clip)
                prev_sample = prev_clip[:40] + ("…" if prev_len > 40 else "")
                log.debug(
                    "Clipboard content unchanged; prev_len={} prev_sample={!r}",
                    prev_len,
                    prev_sample,
                )
                self.notification_service.warning("Copy-translate failed: no clipboard text detected", "WhisperBridge")
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
                self.notification_service.warning("Copy-translate: no text selected to translate", "WhisperBridge")
                t_end = time.perf_counter()
                log.info(f"Copy-translate performance: clipboard=0ms, translation=0ms, total={(t_end - t_start) * 1000:.0f}ms")
                return

            # Check for API key presence before attempting translation
            provider = (self.config_service.get_setting("api_provider", use_cache=False) or "openai").strip().lower()
            openai_key = self.config_service.get_setting("openai_api_key", use_cache=False)
            google_key = self.config_service.get_setting("google_api_key", use_cache=False)
            has_openai_key = bool(openai_key)
            has_google_key = bool(google_key)
            log.debug(
                "Copy-translate configuration: provider={} has_openai_key={} has_google_key={}",
                provider,
                has_openai_key,
                has_google_key,
            )
            # Backward compatibility: if provider is google but dedicated key is missing, allow fallback to openai key
            has_api_key = has_openai_key if provider == "openai" else bool(google_key or openai_key)
            if not has_api_key:
                log.info("No API key configured for the selected provider, showing original text only")
                # Emit overlay with original text only (no translation attempt)
                # Performance summary: compute clipboard time, translation=0
                clipboard_ms = ((t_after_poll_success - (t_after_sim or t_start)) * 1000) if t_after_poll_success and t_after_sim else 0
                t_end = time.perf_counter()
                total_ms = (t_end - t_start) * 1000
                log.info(f"Copy-translate performance: clipboard={clipboard_ms:.0f}ms, translation=0ms, total={total_ms:.0f}ms")
                self.result_ready.emit(text_to_translate, "", False)
                log.info("Copy-translate overlay shown (original text only) due to missing API key")
                return

            # Translate text synchronously (respect auto_swap_en_ru setting) — with debug logs and live config check
            try:
                # Try to detect language and apply EN<->RU auto-swap if enabled in settings
                log.debug(f"Copy-translate: text length={len(text_to_translate)}")
                detected = self.translation_service.detect_language_sync(text_to_translate) or "auto"
                log.debug(f"Copy-translate: detected language='{detected}'")

                # Read all relevant settings
                settings = self.config_service.get_settings()
                swap_enabled = getattr(settings, "auto_swap_en_ru", False)
                ui_source_language = getattr(settings, "ui_source_language", "en")
                ui_target_language = getattr(settings, "ui_target_language", "en")

                # Determine effective source language
                source_lang = ui_source_language

                # Determine effective target language with checkbox priority
                if swap_enabled:
                    if detected == "en":
                        target_lang = "ru"
                    elif detected == "ru":
                        target_lang = "en"
                    else:
                        # If auto-swap is on but language is not en/ru, use the explicit UI target
                        target_lang = ui_target_language
                else:
                    # If auto-swap is off, use the explicit UI target
                    target_lang = ui_target_language

                log.debug(f"Copy-translate: swap_enabled={swap_enabled}. Source='{source_lang}', Target='{target_lang}'")

                # Show a brief translating notification
                self.notification_service.info("Translating...", "WhisperBridge")

                response = self.translation_service.translate_text_sync(
                    text_to_translate, source_lang=source_lang, target_lang=target_lang
                )
            except Exception as exc:
                log.error(f"Copy-translate: error during language detection/auto-swap: {exc}", exc_info=True)
                # Fallback to default translation call on any failure
                self.notification_service.info("Translating...", "WhisperBridge")
                response = self.translation_service.translate_text_sync(text_to_translate)

            # Mark translation completion time
            t_after_translation = time.perf_counter()

            translated_text = getattr(response, "translated_text", None) or str(response)

            # Read auto_copy_translated setting live and set pending flag so main thread can copy AFTER overlay is shown
            try:
                auto_copy = bool(self.config_service.get_setting("auto_copy_translated", use_cache=False))
                log.debug("Auto-copy setting resolved to {}", auto_copy)
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
            log.info("Copy-translate hotkey processed successfully (simulated copy path)")
        except Exception as e:
            log.error(f"Error in copy-translate hotkey handler: {e}", exc_info=True)
            self.notification_service.error(f"Copy-translate error: {str(e)}", "WhisperBridge")
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
