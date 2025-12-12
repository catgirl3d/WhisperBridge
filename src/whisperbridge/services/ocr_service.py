"""
OCR Service for WhisperBridge.

This module provides the main OCR service using LLM vision capabilities.
"""

import time
from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from typing import Optional

from loguru import logger
from PIL import Image

from ..core.api_manager import get_api_manager
from ..services.config_service import config_service
from ..utils.image_utils import to_data_url_jpeg


class OCREngine(Enum):
    """Supported OCR engines."""

    LLM = "llm"


@dataclass
class OCRResult:
    """OCR processing result."""

    text: str
    confidence: float
    engine: OCREngine
    processing_time: float
    error_message: Optional[str] = None
    success: bool = True


@dataclass
class OCRRequest:
    """OCR processing request."""

    image: Image.Image
    preprocess: bool = True


class OCRService:
    """Main OCR service for text recognition."""

    def __init__(self, config_service):
        """Initialize OCR service.

        Args:
            config_service: Config service instance for settings access.
        """
        self.config_service = config_service

    def _handle_ocr_error(self, e: Exception, start_time: float, context: str) -> OCRResult:
        """Unified error handling for OCR operations."""
        processing_time = time.time() - start_time
        error_msg = str(e)
        logger.error(f"Error in {context}: {error_msg}")
        logger.debug(f"Error details: {type(e).__name__}: {error_msg}", exc_info=True)

        return OCRResult(
            text="",
            confidence=0.0,
            engine=OCREngine.LLM,
            processing_time=processing_time,
            error_message=error_msg,
            success=False,
        )

    def _process_llm_image(self, image: "Image.Image") -> OCRResult:
        """Process image with LLM vision API.

        Args:
            image: Input PIL image

        Returns:
            OCRResult with LLM processing results
        """
        start_time = perf_counter()
        logger.debug("Processing image with LLM vision API")

        try:
            # Build image data URL
            data_url = to_data_url_jpeg(image, max_edge=1280, quality=80)

            # Compose messages
            system_prompt = self.config_service.get_setting("ocr_llm_prompt") or "Extract the text as-is. Keep natural reading order. Return only the text."
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract the text as-is. Keep natural reading order. Return only the text."},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]
                }
            ]

            # Determine provider and model
            provider = self.config_service.get_setting("api_provider")
            if provider == "openai":
                model_hint = self.config_service.get_setting("openai_vision_model")
            elif provider == "google":
                model_hint = self.config_service.get_setting("google_vision_model")
            else:
                raise ValueError("Selected provider does not support vision OCR")

            # Call vision API
            api_manager = get_api_manager()
            response, _ = api_manager.make_vision_request(messages, model_hint)

            logger.debug(f"LLM vision API response: {response}")

            # Extract text from unified response format using safe helper
            extracted_text = api_manager.extract_text_from_response(response)
            logger.debug(f"Extracted text: '{extracted_text}' (length: {len(extracted_text)})")

            extracted_text = extracted_text.strip()
            processing_time = perf_counter() - start_time

            # Create result
            success = bool(extracted_text)
            result = OCRResult(
                text=extracted_text,
                confidence=0.90 if success else 0.0,
                engine=OCREngine.LLM,
                processing_time=processing_time,
                success=success,
                error_message=None if success else "Empty OCR text from LLM"
            )

            logger.info(f"LLM OCR completed in {processing_time:.2f}s, success={success}")
            return result

        except Exception as e:
            processing_time = perf_counter() - start_time
            logger.error(f"LLM OCR failed: {e}")
            return OCRResult(
                text="",
                confidence=0.0,
                engine=OCREngine.LLM,
                processing_time=processing_time,
                error_message=str(e),
                success=False,
            )

    def initialize(self, on_complete=None) -> None:
        """Initialize OCR engine.

        For LLM-only mode, this is a no-op as no background initialization is needed.
        The callback is called immediately.

        Args:
            on_complete: Optional callback invoked when initialization completes.
        """
        if on_complete:
            on_complete()
        return None

    def ensure_ready(self, timeout: Optional[float] = 15.0) -> bool:
        """Ensure OCR engine is initialized and ready for use.

        For LLM-only mode, this always returns True as no initialization is needed.

        Args:
            timeout: Ignored in LLM-only mode.

        Returns:
            True always.
        """
        return True

    def is_ocr_engine_ready(self) -> bool:
        """Check if OCR engine is ready (compatibility method)."""
        return True

    def is_ocr_available(self) -> bool:
        """Check if OCR is available (compatibility method)."""
        return True

    def process_image(self, request: OCRRequest) -> OCRResult:
        """Process image with OCR using LLM vision API."""

        start_time = time.time()

        logger.debug(
            "Starting OCR processing. Request: "
            f"image_size={request.image.size}, image_mode='{request.image.mode}', "
            f"preprocess={request.preprocess}"
        )

        try:
            # Use LLM vision API
            # Note: request.preprocess is ignored for LLM as it handles raw images better
            result = self._process_llm_image(request.image)

            if result.success and result.text.strip():
                logger.info(f"LLM OCR succeeded: confidence={result.confidence:.3f}, text_length={len(result.text)}")
            else:
                logger.warning(f"LLM OCR failed or empty: {result.error_message}")

            return result

        except Exception as e:
            return self._handle_ocr_error(e, start_time, "process_image")

    def shutdown(self):
        """Shutdown OCR service."""
        logger.info("Shutting down OCR service")


# Global OCR service instance
_ocr_service: Optional[OCRService] = None


def get_ocr_service() -> OCRService:
    """Get global OCR service instance.

    Returns:
        OCRService: Global OCR service
    """
    global _ocr_service
    if _ocr_service is None:
        from ..services.config_service import config_service
        _ocr_service = OCRService(config_service)
    return _ocr_service
