"""
OCR Service for WhisperBridge.

This module provides the main OCR service that integrates with EasyOCR engine,
handles image preprocessing, and provides a unified interface for text recognition.
"""

import threading
import time
from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from typing import Any, List, Optional

from loguru import logger
from PIL import Image
from PySide6.QtCore import QThread

from ..core.api_manager import get_api_manager
from ..services.config_service import config_service
from ..utils.image_utils import preprocess_for_ocr, to_data_url_jpeg
import numpy as np


class OCREngineInitializer(QThread):
    """QThread for background OCR engine initialization."""

    def __init__(self, ocr_service, on_complete):
        super().__init__()
        self.ocr_service = ocr_service
        self.on_complete = on_complete

    def run(self):
        self.ocr_service._background_init_task(self.on_complete)


class OCREngine(Enum):
    """Supported OCR engines."""

    EASYOCR = "easyocr"
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


@dataclass(frozen=True)
class OCRSettings:
    """OCR configuration settings (immutable).

    Attributes:
        ocr_languages: Languages for text recognition
        ocr_confidence_threshold: Minimum confidence for valid results
    """

    ocr_languages: List[str]
    ocr_confidence_threshold: float


class OCRService:
    """Main OCR service for text recognition."""

    def __init__(self, config_service, settings: Optional[OCRSettings] = None):
        """Initialize OCR service.

        Args:
            config_service: Config service instance for settings access.
            settings: OCR settings. If None, loads from config_service.
        """
        self.config_service = config_service
        self._settings = settings or self._load_settings()

        self._easyocr_reader: Optional[Any] = None
        self._lock = threading.RLock()
        self._is_initializing = False
        self._ready_event = threading.Event()
        self._init_thread: Optional[OCREngineInitializer] = None

    def _load_settings(self) -> OCRSettings:
        """Load and validate OCR settings from config service.

        Returns:
            OCRSettings instance with validated configuration.
        """
        threshold = self.config_service.get_setting("ocr_confidence_threshold")
        return OCRSettings(
            ocr_languages=self.config_service.get_setting("ocr_languages"),
            ocr_confidence_threshold=min(max(threshold, 0.0), 1.0),
        )

    def _handle_ocr_error(self, e: Exception, start_time: float, context: str) -> OCRResult:
        """Unified error handling for OCR operations."""
        processing_time = time.time() - start_time
        error_msg = str(e)
        logger.error(f"Error in {context}: {error_msg}")
        logger.debug(f"Error details: {type(e).__name__}: {error_msg}", exc_info=True)

        return OCRResult(
            text="",
            confidence=0.0,
            engine=OCREngine.EASYOCR,
            processing_time=processing_time,
            error_message=error_msg,
            success=False,
        )

    def _initialize_engines(self):
        """Initialize EasyOCR engine."""
        start_time = time.time()
        logger.info("Starting OCR service engine initialization")

        # Check if OCR is enabled at runtime
        ocr_enabled = self.config_service.get_setting("ocr_enabled", use_cache=False)
        if not ocr_enabled:
            logger.warning("OCR disabled - skipping initialization")
            return False

        # Lazy import EasyOCR
        try:
            import easyocr
        except ImportError:
            logger.warning("EasyOCR not available - skipping initialization")
            return False

        # Get OCR languages from settings
        languages = self._settings.ocr_languages
        logger.debug(f"OCR languages from settings: {languages}")

        try:
            with self._lock:
                logger.info(f"Initializing EasyOCR with languages: {languages}")
                self._easyocr_reader = easyocr.Reader(languages)

            initialization_time = time.time() - start_time
            logger.info(f"EasyOCR engine initialized successfully in {initialization_time:.2f}s")
            logger.debug(f"OCR service ready with {len(languages)} languages: {languages}")
            return True

        except Exception as e:
            initialization_time = time.time() - start_time
            logger.error(f"Error initializing OCR engines after {initialization_time:.2f}s: {e}")
            logger.debug(f"Initialization error details: {type(e).__name__}: {str(e)}", exc_info=True)
            self._easyocr_reader = None
            return False

    def is_ocr_engine_ready(self) -> bool:
        """Check if OCR engine is ready for use.

        Returns:
            True if engine is available and ready for use
        """
        return self._easyocr_reader is not None

    def _process_easyocr_array(self, image_array: Any, ocr_confidence_threshold: float) -> OCRResult:
        """Process image array with EasyOCR.

        Args:
            image_array: Numpy array of image
            ocr_confidence_threshold: Minimum confidence threshold for success

        Returns:
            OCRResult with processing results
        """
        start_time = time.time()
        logger.debug("Processing image array with EasyOCR")
        logger.debug(f"Image array shape: {image_array.shape}, dtype: {image_array.dtype}")

        try:
            with self._lock:
                # EasyOCR can process numpy arrays directly
                results = self._easyocr_reader.readtext(image_array)

                processing_time = time.time() - start_time

                if not results:
                    logger.info("EasyOCR: No text detected in image array")
                    return OCRResult(
                        text="",
                        confidence=0.0,
                        engine=OCREngine.EASYOCR,
                        processing_time=processing_time,
                        error_message="No text detected",
                        success=False,
                    )

                logger.info(f"EasyOCR: Found {len(results)} text fragments in image array")

                # Combine all detected text
                text_parts = []
                confidences = []

                for i, detection in enumerate(results):
                    bbox, text, confidence = detection
                    text_parts.append(text)
                    confidences.append(confidence)
                    logger.debug(f"EasyOCR Fragment {i+1}: bbox={bbox}, text='{text}', confidence={confidence:.3f}")

                combined_text = " ".join(text_parts)
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
                success = bool(combined_text.strip()) and avg_confidence >= ocr_confidence_threshold

                logger.info(f"EasyOCR: Combined text length={len(combined_text)}, average confidence={avg_confidence:.3f}, success={success}")
                logger.debug(f"EasyOCR: Full combined text='{combined_text}'")

                return OCRResult(
                    text=combined_text,
                    confidence=avg_confidence,
                    engine=OCREngine.EASYOCR,
                    processing_time=processing_time,
                    success=success,
                )

        except Exception as e:
            return self._handle_ocr_error(e, start_time, "_process_easyocr_array")

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

            logger.debug(f"Extracted text from LLM response: '{extracted_text}' (length: {len(extracted_text)})")

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

    def _background_init_task(self, on_complete):
        """Task to initialize engines and call completion callback.

        Background thread task that initializes OCR engines and executes
        the completion callback when done. Handles exceptions in callback.

        Args:
            on_complete: Optional callback function to call when initialization completes
        """
        try:
            success = self._initialize_engines()
            logger.debug(f"Background init task completed (success={success})")

            if success:
                self._ready_event.set()

            if on_complete:
                try:
                    on_complete()
                except Exception as e:
                    logger.error(f"Init callback error: {e}")
        except Exception as e:
            logger.error(f"Background init task error: {e}")
        finally:
            self._is_initializing = False

    def _start_background_initialization(self, on_complete=None):
        """Start background initialization of OCR engines.

        Args:
            on_complete: Callback when complete
        """
        logger.info("Starting background initialization of OCR engines...")
        with self._lock:
            if not self._is_initializing:
                self._is_initializing = True
                self._ready_event.clear()
                self._init_thread = OCREngineInitializer(self, on_complete)
                self._init_thread.finished.connect(self._on_init_finished)
                self._init_thread.start()

    def _on_init_finished(self):
        """Called when initialization thread finishes."""
        self._init_thread = None

    def initialize(self, on_complete=None) -> None:
        """Initialize OCR engine (always asynchronous).

        Starts background initialization of OCR engines. This method never blocks
        and always returns immediately. The optional on_complete callback will be
        invoked from the background thread upon completion; use Qt signals to
        notify the UI thread if needed.

        Args:
            on_complete: Optional callback invoked when initialization completes.

        Returns:
            None
        """
        logger.info("Starting background OCR initialization (async-only)")
        self._start_background_initialization(on_complete)
        return None

    def _process_with_easyocr(self, request: OCRRequest, start_time: float, context: str = "OCR") -> OCRResult:
        """Process image with EasyOCR engine.

        Common helper for both primary EasyOCR path and LLM fallback path.

        Args:
            request: OCR request with image and preprocessing flag
            start_time: Processing start time for timing
            context: Context string for logging ("OCR" or "EasyOCR fallback")

        Returns:
            OCRResult with EasyOCR processing results
        """
        # Preprocess image if requested
        processed_image = request.image
        if request.preprocess:
            logger.debug(f"Applying image preprocessing for {context}")
            processed_image = preprocess_for_ocr(request.image)
            logger.debug(f"Preprocessed image size: {processed_image.size}")

        # Convert PIL image to numpy array for EasyOCR
        image_array = np.array(processed_image)
        logger.debug(f"Converted to numpy array: shape={image_array.shape}, dtype={image_array.dtype}")

        # Process with EasyOCR engine using settings
        result = self._process_easyocr_array(image_array, self._settings.ocr_confidence_threshold)

        # Update processing time to include preprocessing and conversion
        result.processing_time = time.time() - start_time

        logger.info(f"{context} processing completed in {result.processing_time:.2f}s")
        logger.info(f"{context} results: confidence={result.confidence:.3f}, success={result.success}")
        if context == "OCR":
            logger.debug(f"{context} text length: {len(result.text)} characters")

        return result

    def _ensure_easyocr_fallback_ready(self, timeout: float = 5.0) -> bool:
        """Ensure EasyOCR reader is ready for fallback use.

        Private helper for LLM fallback path. Checks OCR settings, verifies
        reader readiness, and initializes if needed using existing mechanisms.

        Args:
            timeout: Maximum time to wait for initialization.

        Returns:
            True if EasyOCR reader is ready, False otherwise.
        """
        # Check if OCR is enabled
        if not self.config_service.get_setting("ocr_enabled"):
            logger.debug("OCR disabled, skipping EasyOCR fallback initialization")
            return False

        # Check if already ready
        if self.is_ocr_engine_ready():
            logger.debug("EasyOCR reader already initialized for fallback")
            return True

        # Start initialization if not already started
        logger.debug("Starting EasyOCR initialization for fallback")
        self._start_background_initialization(None)

        # Wait for readiness
        ready = self._ready_event.wait(timeout)
        if ready:
            logger.debug("EasyOCR fallback initialization completed successfully")
        else:
            logger.warning(f"EasyOCR fallback initialization timed out after {timeout}s")
        return ready

    def ensure_ready(self, timeout: Optional[float] = 15.0) -> bool:
        """Ensure OCR engine is initialized and ready for use.

        Lazy initialization method.
        - Call only from worker/background threads before using OCR.
        - Never starts or blocks in the main/UI thread.
        - Idempotent and safe to call multiple times.

        Args:
            timeout: Maximum time to wait for initialization to complete. None = wait indefinitely.

        Returns:
            True if the engine is ready by the end of wait, False otherwise.
        """
        # Fast path for LLM engine
        engine = self.config_service.get_setting("ocr_engine")
        if engine == "llm":
            return True

        # Fast path
        if self.is_ocr_engine_ready():
            return True

        # Start initialization if not already started
        self._start_background_initialization(None)

        # Wait for readiness
        return self._ready_event.wait(timeout)

    def process_image(self, request: OCRRequest) -> OCRResult:
        """Process image with OCR."""

        start_time = time.time()

        logger.debug(
            "Starting OCR processing. Request: "
            f"image_size={request.image.size}, image_mode='{request.image.mode}', "
            f"preprocess={request.preprocess}"
        )

        try:
            # Get engine from settings
            engine = self.config_service.get_setting("ocr_engine")

            if engine == "llm":
                # Use LLM vision API without EasyOCR preprocessing
                result = self._process_llm_image(request.image)

                # Check if LLM succeeded
                if result.success and result.text.strip():
                    logger.info(f"LLM OCR succeeded: confidence={result.confidence:.3f}, text_length={len(result.text)}")
                    return result
                else:
                    logger.warning(f"LLM OCR failed or empty: {result.error_message}")

                    # Fallback to EasyOCR if enabled
                    ocr_enabled = self.config_service.get_setting("ocr_enabled", True)
                    if ocr_enabled:
                        logger.info("Falling back to EasyOCR")
                        # Ensure EasyOCR is ready before proceeding
                        if not self._ensure_easyocr_fallback_ready(timeout=5.0):
                            logger.warning("EasyOCR fallback initialization failed, returning LLM failure result")
                            return result

                        # Process with EasyOCR fallback
                        result = self._process_with_easyocr(request, start_time, "EasyOCR fallback")
                        return result
                    else:
                        logger.warning("EasyOCR disabled, returning LLM failure result")
                        return result
            else:
                # Original EasyOCR path - ensure ready before processing
                if not self.ensure_ready(timeout=15.0):
                    error_msg = "OCR service is not initialized or engines not loaded."
                    logger.warning(f"OCR service not ready: {error_msg}")
                    return OCRResult(
                        text="",
                        confidence=0.0,
                        engine=OCREngine.EASYOCR,
                        processing_time=time.time() - start_time,
                        error_message=error_msg,
                        success=False,
                    )
                return self._process_with_easyocr(request, start_time, "OCR")

        except Exception as e:
            return self._handle_ocr_error(e, start_time, "process_image")

    def shutdown(self):
        """Shutdown OCR service and cleanup resources."""
        logger.info("Shutting down OCR service")

        # Clear EasyOCR reader
        with self._lock:
            self._easyocr_reader = None

        self._ready_event.clear()
        self._is_initializing = False
        logger.info("OCR service shutdown complete")


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
