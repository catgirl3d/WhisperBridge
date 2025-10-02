"""
Qt-based worker classes for background processing in WhisperBridge.
Provides thread-safe workers for OCR/translation and settings saving operations.
"""

import asyncio
import time
from typing import Any, Dict

from loguru import logger
from PySide6.QtCore import QObject, Signal

from ..core.api_manager import get_api_manager, APIProvider
from ..core.config import Settings
from ..services.config_service import config_service
from ..services.ocr_service import get_ocr_service
from ..services.ocr_translation_service import get_ocr_translation_coordinator
from ..services.screen_capture_service import get_capture_service
from ..utils.screen_utils import Rectangle


class CaptureOcrTranslateWorker(QObject):
    """Worker for synchronous capture, OCR, and optional translation."""

    started = Signal()
    progress = Signal(str)
    ocr_finished = Signal(str)
    finished = Signal(str, str, str)
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
                original_text, translated_text = coordinator.process_image_with_translation(
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
                original_text, translated_text = coordinator.process_image_with_translation(
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
            self.finished.emit(original_text, translated_text, overlay_id)

            logger.info("CaptureOcrTranslateWorker run completed successfully")

        except Exception as e:
            logger.error(f"Error in worker run: {e}", exc_info=True)
            self.error.emit(str(e))

    def process_and_emit(self, text):
        """Backward compatibility method for existing callers in _process_selection."""
        self.ocr_finished.emit(text)
        self.finished.emit(text, "", "")


class SettingsSaveWorker(QObject):
    """Worker for saving settings asynchronously."""

    finished = Signal(bool, str)  # success, error_message

    def __init__(self, settings_to_save: Dict[str, Any]):
        super().__init__()
        self.settings_to_save = settings_to_save

    def run(self):
        """Save settings using the settings manager."""
        try:
            new_settings = Settings(**self.settings_to_save)
            if config_service.save_settings(new_settings):
                self.finished.emit(True, "Settings saved successfully.")
            else:
                self.finished.emit(False, "Failed to save settings.")
        except Exception as e:
            logger.error(f"Error in SettingsSaveWorker: {e}", exc_info=True)
            self.finished.emit(False, f"An error occurred: {e}")


class ApiTestWorker(QObject):
    """Worker for testing API key asynchronously."""

    finished = Signal(bool, str, list, str)  # success, error_message, models, source

    def __init__(self, provider: str, api_key: str):
        super().__init__()
        self.provider = provider
        self.api_key = api_key

    def run(self):
        """Test the API key by delegating to APIManager with a temporary key and emit models to avoid double fetch."""
        try:
            api_manager = get_api_manager()
            if not api_manager.is_initialized():
                api_manager.initialize()
            provider_enum = APIProvider(self.provider)
            models, source = api_manager.get_available_models_sync(
                provider=provider_enum, temp_api_key=self.api_key
            )
            if source in ("error", "unconfigured"):
                self.finished.emit(False, "API error or invalid key", [], source)
            elif not models:
                self.finished.emit(False, "No models available for this API key", [], source)
            else:
                self.finished.emit(True, "", models, source)
        except Exception as e:
            self.finished.emit(False, f"Ошибка подключения: {str(e)}", [], "error")


class TranslationWorker(QObject):
    """Worker for translating text asynchronously."""

    finished = Signal(bool, str)  # success, result_or_error

    def __init__(self, text_to_translate: str, source_lang: str, target_lang: str):
        super().__init__()
        self.text = text_to_translate
        self.source_lang = source_lang
        self.target_lang = target_lang

    def run(self):
        try:
            from ..services.translation_service import get_translation_service
            service = get_translation_service()

            # Create and use a new event loop in this thread to avoid conflicting with Qt's loop
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                resp = loop.run_until_complete(
                    service.translate_text_async(
                        self.text,
                        source_lang=self.source_lang,
                        target_lang=self.target_lang,
                    )
                )
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

            if resp and getattr(resp, "success", False):
                self.finished.emit(True, resp.translated_text or "")
            else:
                self.finished.emit(False, getattr(resp, "error_message", "Translation failed"))
        except Exception as e:
            self.finished.emit(False, str(e))