"""
Qt-based worker classes for background processing in WhisperBridge.
Provides thread-safe workers for OCR/translation and settings saving operations.
"""

import asyncio
import time
from typing import Any, Dict, Coroutine

from loguru import logger
from PySide6.QtCore import QObject, Signal

from ..core.api_manager import get_api_manager, APIProvider
from ..core.config import Settings
from ..core.settings_manager import settings_manager
from ..services.config_service import config_service
from ..services.ocr_service import get_ocr_service
from ..services.ocr_translation_service import get_ocr_translation_coordinator
from ..services.screen_capture_service import get_capture_service
from ..providers.deepl_adapter import DeepLClientAdapter
from ..core.config import get_deepl_identifier
from ..utils.screen_utils import Rectangle


class CaptureOcrTranslateWorker(QObject):
    """Worker for synchronous capture, OCR, and optional translation."""

    started = Signal()
    progress = Signal(str)
    ocr_finished = Signal(str)
    finished = Signal(str, str, str, str)  # original, translated, overlay_id, error_message
    error = Signal(str)

    def __init__(self, region=None, image=None, capture_options=None):
        super().__init__()
        self.region = region
        self.image = image
        self.capture_options = capture_options or {}
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        logger.info("CaptureOcrTranslateWorker run started")

        try:
            self.started.emit()

            if self._cancel_requested:
                return

            # OCR + Translation processing using centralized ensure_ready in worker thread
            ocr_service = get_ocr_service()
            ready = ocr_service.ensure_ready(timeout=15.0)
            if not ready:
                self.error.emit("OCR service not ready or initialization timed out")
                return

            if self.image is not None:
                logger.debug("Processing pre-captured image")
                self.progress.emit("Starting OCR and translation")
                coordinator = get_ocr_translation_coordinator()
                original_text, translated_text, error_message = coordinator.process_image_with_translation(
                    self.image, preprocess=True
                )
                overlay_id = "ocr"
            elif self.region is not None:
                logger.debug(f"Starting synchronous capture for region {self.region}")
                self.progress.emit("Starting screen capture")
                capture_service = get_capture_service()
                capture_result = capture_service.capture_area(self.region)

                if not capture_result.success or capture_result.image is None:
                    logger.error("Capture failed")
                    self.error.emit("Screen capture failed")
                    return

                logger.debug("Capture completed, starting OCR and translation")
                self.progress.emit("Capture completed, starting OCR and translation")
                coordinator = get_ocr_translation_coordinator()
                original_text, translated_text, error_message = coordinator.process_image_with_translation(
                    capture_result.image, preprocess=True
                )
                overlay_id = "ocr"
            else:
                self.error.emit("No image or region provided")
                return

            if self._cancel_requested:
                return

            self.progress.emit("Processing completed")
            self.ocr_finished.emit(original_text)
            self.finished.emit(original_text, translated_text, overlay_id, error_message)

            logger.info("CaptureOcrTranslateWorker run completed successfully")

        except Exception as e:
            logger.error(f"Error in worker run: {e}", exc_info=True)
            self.error.emit(str(e))

    def process_and_emit(self, text):
        """Backward compatibility method for existing callers in _process_selection."""
        self.ocr_finished.emit(text)
        self.finished.emit(text, "", "", "")


class ApiTestWorker(QObject):
    """Worker for testing API key asynchronously."""

    finished = Signal(bool, str, list, str)  # success, error_message, models, source
    error = Signal(str)

    def __init__(self, provider: str, api_key: str):
        super().__init__()
        self.provider = provider
        self.api_key = api_key

    def run(self):
        """Test the API key by delegating to APIManager with a temporary key and emit models to avoid double fetch."""
        try:
            if self.provider == "deepl":
                # Special handling for DeepL: perform a real translation request
                plan = config_service.get_setting("deepl_plan") or "free"
                client = DeepLClientAdapter(api_key=self.api_key, timeout=10, plan=plan)
                response = client.chat.completions.create(
                    model=get_deepl_identifier(),
                    messages=[{"role": "user", "content": "Hello"}],
                    target_lang="DE"
                )
                if response and response.choices and response.choices[0].message.content:
                    self.finished.emit(True, "", [get_deepl_identifier()], "api")
                else:
                    self.finished.emit(False, "DeepL test failed: empty response", [], "api")
            else:
                # Existing behavior for OpenAI/Google
                api_manager = get_api_manager()
                if not api_manager.is_initialized():
                    api_manager.initialize()
                provider_enum = APIProvider(self.provider)
                models, source = api_manager.get_available_models_sync(
                    provider=provider_enum, temp_api_key=self.api_key
                )
                if source in ("error", "unconfigured"):
                    self.error.emit("API error or invalid key")
                elif not models:
                    self.error.emit("No models available for this API key")
                else:
                    self.finished.emit(True, "", models, source)
        except Exception as e:
            if self.provider == "deepl":
                self.finished.emit(False, f"DeepL test failed: {str(e)}", [], "api")
            else:
                self.error.emit(f"Connection error: {str(e)}")

class BaseAsyncWorker(QObject):
    """Base class for workers that need an asyncio event loop.
    
    Signals:
        finished(bool, str): Always emitted on completion. First param is success flag, second is result or error message.
        error(str): Emitted on error.
    """

    finished = Signal(bool, str)  # success, result_or_error
    error = Signal(str)

    def _run_async_task(self, coro: Coroutine[Any, Any, Any], worker_name: str):
        """Run an async coroutine in a new event loop with timeout and cleanup."""
        # Get timeout from settings (default to 60 seconds)
        timeout = config_service.get_setting("api_timeout") or 60
        # Validate timeout is positive
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            logger.warning(f"Invalid api_timeout value: {timeout}, using default 60")
            timeout = 60
        start_time = time.time()

        # Create and use a new event loop in this thread to avoid conflicting with Qt's loop
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)

            # Wrap async call with timeout to prevent indefinite hanging
            async def with_timeout():
                return await asyncio.wait_for(coro, timeout=timeout)

            resp = loop.run_until_complete(with_timeout())

            elapsed = time.time() - start_time
            logger.info(f"{worker_name} completed successfully in {elapsed:.2f}s")
            return resp
        except asyncio.TimeoutError:
            logger.error(f"{worker_name} timed out after {timeout}s")
            msg = f"Request timed out after {timeout} seconds"
            self.error.emit(msg)
            self.finished.emit(False, msg)
            return None
        except Exception as e:
            logger.error(f"{worker_name} failed: {e}", exc_info=True)
            msg = str(e)
            self.error.emit(msg)
            self.finished.emit(False, msg)
            return None
        finally:
            # Cancel all pending tasks before closing loop to prevent hanging
            try:
                pending = asyncio.all_tasks(loop)
                if pending:
                    logger.debug(f"Cancelling {len(pending)} pending tasks")
                    # Note: Main task (with_timeout) is already finished here, so we only cancel 
                    # lingering background tasks started by the service.
                    for task in pending:
                        task.cancel()
                    # Give tasks a chance to handle cancellation with timeout to prevent infinite hang
                    try:
                        loop.run_until_complete(asyncio.wait_for(
                            asyncio.gather(*pending, return_exceptions=True),
                            timeout=5.0  # 5 second grace period for task cancellation
                        ))
                    except asyncio.TimeoutError:
                        logger.warning("Task cancellation timed out after 5 seconds, proceeding with loop cleanup")
            except Exception as e:
                logger.debug(f"Error during task cancellation: {e}")
            finally:
                try:
                    loop.close()
                except Exception as e:
                    logger.debug(f"Error closing event loop: {e}")
                finally:
                    # Detach loop from thread
                    asyncio.set_event_loop(None)


class TranslationWorker(BaseAsyncWorker):
    """Worker for translating text asynchronously."""

    def __init__(self, text_to_translate: str, ui_source_lang: str, ui_target_lang: str):
        super().__init__()
        self.text = text_to_translate
        self.ui_source_lang = ui_source_lang
        self.ui_target_lang = ui_target_lang

    def run(self):
        logger.info("TranslationWorker started")
        try:
            from ..services.translation_service import get_translation_service
            service = get_translation_service()

            coro = service.translate_text_async(
                self.text,
                ui_source_lang=self.ui_source_lang,
                ui_target_lang=self.ui_target_lang,
            )

            resp = self._run_async_task(coro, "TranslationWorker")
            if resp is None:
                return  # Error already emitted by _run_async_task

            if resp and getattr(resp, "success", False):
                self.finished.emit(True, resp.translated_text or "")
            else:
                msg = getattr(resp, "error_message", "Translation failed")
                self.error.emit(msg)
                self.finished.emit(False, msg)
        except Exception as e:
            logger.error(f"TranslationWorker failed: {e}", exc_info=True)
            msg = str(e)
            self.error.emit(msg)
            self.finished.emit(False, msg)


class StyleWorker(BaseAsyncWorker):
    """Worker for styling (rewriting) text asynchronously using presets."""

    def __init__(self, text_to_style: str, style_name: str):
        super().__init__()
        self.text = text_to_style
        self.style_name = style_name

    def run(self):
        logger.info(f"StyleWorker started with style: '{self.style_name}'")
        try:
            from ..services.translation_service import get_translation_service
            service = get_translation_service()

            coro = service.style_text_async(
                self.text,
                style_name=self.style_name,
                use_cache=True,
            )

            resp = self._run_async_task(coro, "StyleWorker")
            if resp is None:
                return  # Error already emitted by _run_async_task

            if resp and getattr(resp, "success", False):
                self.finished.emit(True, resp.translated_text or "")
            else:
                msg = getattr(resp, "error_message", "Styling failed")
                self.error.emit(msg)
                self.finished.emit(False, msg)
        except Exception as e:
            logger.error(f"StyleWorker failed: {e}", exc_info=True)
            msg = str(e)
            self.error.emit(msg)
            self.finished.emit(False, msg) 
