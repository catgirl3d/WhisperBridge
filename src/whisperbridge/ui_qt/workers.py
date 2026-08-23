"""
Qt-based worker classes for background processing in WhisperBridge.
Provides thread-safe workers for OCR/translation and settings saving operations.
"""

from loguru import logger
from PySide6.QtCore import QObject, Signal

from ..core.api_manager import get_api_manager
from ..core.provider_catalog import APIProvider
from ..core.settings_manager import settings_manager
from ..services.config_service import config_service
from ..services.notification_service import get_notification_service
from ..services.ocr_service import OCRRequest, get_ocr_service
from ..services.translation_service import get_translation_service
from ..providers.deepl_adapter import DeepLClientAdapter
from ..core.config import get_deepl_identifier


class CaptureOcrTranslateWorker(QObject):
    """Worker for OCR + translation from a pre-captured image."""

    started = Signal()
    progress = Signal(str)
    ocr_finished = Signal(str)
    finished = Signal(str, str, str, str)  # original, translated, overlay_id, error_message

    def __init__(self, image):
        super().__init__()
        if image is None:
            raise ValueError("image is required")
        self.image = image
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        logger.info("CaptureOcrTranslateWorker run started")

        try:
            self.started.emit()

            if self._cancel_requested:
                self.finished.emit("", "", "", "")
                return

            logger.debug("Processing pre-captured image")
            self.progress.emit("Starting OCR and translation")
            ocr_service = get_ocr_service()
            translation_service = get_translation_service()

            try:
                ocr_response = ocr_service.process_image(
                    OCRRequest(image=self.image, preprocess=True)
                )
                original_text = ocr_response.text

                if not original_text:
                    original_text = ""
                    error_message = (
                        ocr_response.error_message
                        if not ocr_response.success
                        else "OCR detected no text"
                    )
                    error_message = error_message or "OCR detected no text"
                    translated_text = ""
                elif not original_text.strip():
                    translated_text = ""
                    error_message = ""
                else:
                    logger.info("OCR completed, checking translation availability")
                    get_notification_service().info(
                        "OCR completed. Translating...",
                        title="WhisperBridge",
                    )

                    if not translation_service.is_available:
                        logger.debug("Translation service not available, skipping translation")
                        translated_text = ""
                        error_message = "Translation service not configured"
                    else:
                        settings = config_service.get_settings()
                        source_lang = getattr(settings, "ui_source_language", "auto")
                        target_lang = getattr(settings, "ui_target_language", "en")
                        response = translation_service.translate_text(
                            original_text,
                            source_lang=source_lang,
                            target_lang=target_lang,
                        )
                        if response.success:
                            logger.debug("Translation completed successfully")
                            translated_text = response.translated_text
                            error_message = ""
                        else:
                            logger.warning(f"Translation failed: {response.error_message}")
                            translated_text = ""
                            error_message = response.error_message
            except Exception as e:
                logger.error(f"Error during OCR/translation processing: {e}")
                original_text = "Processing error"
                translated_text = ""
                error_message = str(e)
            overlay_id = "ocr"

            if self._cancel_requested:
                self.finished.emit("", "", "", "")
                return

            self.progress.emit("Processing completed")
            self.ocr_finished.emit(original_text)
            self.finished.emit(original_text, translated_text, overlay_id, error_message)

            logger.info("CaptureOcrTranslateWorker run completed successfully")

        except Exception as e:
            logger.error(f"Error in worker run: {e}", exc_info=True)
            self.finished.emit("", "", "", str(e))

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
                    self.finished.emit(False, "API error or invalid key", [], "")
                elif not models:
                    self.finished.emit(False, "No models available for this API key", [], "")
                else:
                    self.finished.emit(True, "", models, source)
        except Exception as e:
            if self.provider == "deepl":
                self.finished.emit(False, f"DeepL test failed: {str(e)}", [], "api")
            else:
                self.finished.emit(False, f"Connection error: {str(e)}", [], "")

class BaseWorker(QObject):
    """Base class for background workers."""

    finished = Signal(bool, str)  # success, result_or_error

    def __init__(self):
        super().__init__()
        self._cancel_requested = False

    def request_cancel(self):
        """Request cancellation of the worker."""
        self._cancel_requested = True


class TranslationWorker(BaseWorker):
    """Worker for translating text in a background QThread."""

    def __init__(self, text_to_translate: str, ui_source_lang: str, ui_target_lang: str):
        super().__init__()
        self.text = text_to_translate
        self.ui_source_lang = ui_source_lang
        self.ui_target_lang = ui_target_lang

    def run(self):
        logger.info("TranslationWorker started")
        try:
            if self._cancel_requested:
                self.finished.emit(False, "Request cancelled")
                return

            from ..services.translation_service import get_translation_service
            service = get_translation_service()

            resp = service.translate_text(
                self.text,
                ui_source_lang=self.ui_source_lang,
                ui_target_lang=self.ui_target_lang,
            )

            if self._cancel_requested:
                self.finished.emit(False, "Request cancelled")
                return

            if resp and getattr(resp, "success", False):
                self.finished.emit(True, resp.translated_text or "")
            else:
                msg = getattr(resp, "error_message", "Translation failed")
                self.finished.emit(False, msg)
        except Exception as e:
            logger.error(f"TranslationWorker failed: {e}", exc_info=True)
            self.finished.emit(False, str(e))


class StyleWorker(BaseWorker):
    """Worker for styling (rewriting) text using presets in a background QThread."""

    def __init__(self, text_to_style: str, style_name: str):
        super().__init__()
        self.text = text_to_style
        self.style_name = style_name

    def run(self):
        logger.info(f"StyleWorker started with style: '{self.style_name}'")
        try:
            if self._cancel_requested:
                self.finished.emit(False, "Request cancelled")
                return

            from ..services.translation_service import get_translation_service
            service = get_translation_service()

            resp = service.style_text(
                self.text,
                style_name=self.style_name,
            )

            if self._cancel_requested:
                self.finished.emit(False, "Request cancelled")
                return

            if resp and getattr(resp, "success", False):
                self.finished.emit(True, resp.translated_text or "")
            else:
                msg = getattr(resp, "error_message", "Styling failed")
                self.finished.emit(False, msg)
        except Exception as e:
            logger.error(f"StyleWorker failed: {e}", exc_info=True)
            self.finished.emit(False, str(e))
