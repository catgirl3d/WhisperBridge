"""
OCR Translation Coordinator Service

Coordinates the OCR + Translation process, combining:
- OCR text recognition (OCRService)
- Text translation (TranslationService)
"""

from typing import Optional, Tuple

from loguru import logger
from PIL import Image

from .config_service import config_service
from .notification_service import get_notification_service
from .ocr_service import OCRRequest, get_ocr_service
from .translation_service import get_translation_service


class OCRTranslationCoordinator:
    """Coordinator for the OCR + translation process."""

    def __init__(self):
        self.ocr_service = get_ocr_service()
        self.translation_service = get_translation_service(initialize=True)

    def process_image_with_translation(
        self, image: Image.Image, preprocess: bool = True
    ) -> Tuple[str, str, str]:
        """Process image with OCR and translation.

        Args:
            image: PIL image
            preprocess: Whether to apply preprocessing

        Returns:
            Tuple of (original_text, translated_text, error_message)
        """
        logger.info("Starting OCR + translation coordination")
        try:
            ocr_request = OCRRequest(
                image=image,
                preprocess=preprocess,
            )
            ocr_response = self.ocr_service.process_image(ocr_request)
            original_text = ocr_response.text

            if not original_text:
                error_msg = ocr_response.error_message if not ocr_response.success else "OCR detected no text"
                return "", "", error_msg or "OCR detected no text"

            translated_text, error_message = self._translate_if_needed(original_text)
            return original_text, translated_text, error_message
        except Exception as e:
            logger.error(f"Error during OCR/translation processing: {e}")
            return "Processing error", "", str(e)
        
    def _translate_if_needed(self, text: str) -> Tuple[str, str]:
        """Translate text if translation service is available.

        Helper method for process_image_with_translation() that handles the translation
        step. Checks if translation service is available, determines source and target
        languages, and executes the translation.

        Args:
            text: Text to translate

        Returns:
            Tuple of (translated_text, error_message)
        """
        if not text.strip():
            return "", ""
        
        logger.info("OCR completed, checking translation availability")

        # Notify user that OCR is complete and translation is in progress
        notification_service = get_notification_service()
        notification_service.info(
            "OCR completed. Translating...",
            title="WhisperBridge"
        )

        if not self.translation_service.is_available:
            logger.debug("Translation service not available, skipping translation")
            return "", "Translation service not configured"

        # Determine languages
        source_lang, target_lang = self._determine_translation_languages(text)

        # Perform translation
        try:
            response = self.translation_service.translate_text_sync(
                text, source_lang=source_lang, target_lang=target_lang
            )

            if response.success:
                logger.debug("Translation completed successfully")
                return response.translated_text, ""
            else:
                logger.warning(f"Translation failed: {response.error_message}")
                return "", response.error_message

        except Exception as e:
            logger.error(f"Translation error: {e}")
            return "", str(e)
    def _determine_translation_languages(self, text: str) -> Tuple[str, str]:
        """Determine languages for translation based on settings.

        Args:
            text: Text content (used for auto-detection if enabled)

        Returns:
            Tuple of (source_language, target_language)
        """
        settings = config_service.get_settings()
        ocr_auto_swap = getattr(settings, "auto_swap_en_ru", False)

        if ocr_auto_swap:
            # Auto-detection and swapping of EN ↔ RU languages
            try:
                detected = self.translation_service.detect_language_sync(text) or "auto"

                if detected == "en":
                    target = "ru"
                elif detected == "ru":
                    target = "en"
                else:
                    target = "en"  # Default fallback

                logger.debug(f"Auto-swap: detected='{detected}', target='{target}'")
                return detected, target

            except Exception as e:
                logger.warning(f"Auto-swap detection failed: {e}, using defaults")
                return "auto", "en"
        else:
            # Get language pair from UI settings
            ui_source = getattr(settings, "ui_source_language", "auto")
            ui_target = getattr(settings, "ui_target_language", "en")
            return ui_source, ui_target

# Global instance
_coordinator: Optional[OCRTranslationCoordinator] = None


def get_ocr_translation_coordinator() -> OCRTranslationCoordinator:
    """Get global coordinator instance.

    Returns:
        OCRTranslationCoordinator: Global coordinator instance
    """
    global _coordinator
    if _coordinator is None:
        _coordinator = OCRTranslationCoordinator()
    return _coordinator