"""
OCR Service for WhisperBridge.

This module provides the main OCR service that integrates with EasyOCR engine,
handles image preprocessing, caching, and provides a unified interface for text recognition.
"""

import hashlib
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from PIL import Image

from ..services.config_service import SettingsObserver, config_service
from ..utils.image_utils import get_image_processor, preprocess_for_ocr


class OCREngine(Enum):
    """Supported OCR engines."""

    EASYOCR = "easyocr"


class InitializationState(Enum):
    """OCR service initialization states."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class OCRResult:
    """OCR processing result."""

    text: str
    confidence: float
    engine: OCREngine
    processing_time: float
    cached: bool = False
    error_message: Optional[str] = None
    success: bool = True


@dataclass
class OCRRequest:
    """OCR processing request."""

    image: Image.Image
    languages: Optional[List[str]] = None
    preprocess: bool = True
    use_cache: bool = True
    timeout: Optional[float] = None


class OCRCache:
    """Simple in-memory cache for OCR results."""

    def __init__(self, max_size: int = 100, ttl: int = 3600):
        """Initialize OCR cache.

        Args:
            max_size: Maximum number of cached items
            ttl: Time-to-live in seconds
        """
        self.cache: Dict[str, Tuple[OCRResult, float]] = {}
        self.max_size = max_size
        self.ttl = ttl
        self.lock = threading.RLock()

    def _generate_key(self, image: Image.Image, languages: List[str]) -> str:
        """Generate cache key for image and languages.

        Args:
            image: PIL image
            languages: List of languages

        Returns:
            Cache key string
        """
        # Create hash from image content and languages
        image_hash = hashlib.md5(image.tobytes()).hexdigest()
        lang_str = ",".join(sorted(languages or []))
        return f"{image_hash}:{lang_str}"

    def get(self, image: Image.Image, languages: List[str]) -> Optional[OCRResult]:
        """Get cached OCR result.

        Args:
            image: PIL image
            languages: List of languages

        Returns:
            Cached OCR response or None
        """
        key = self._generate_key(image, languages)

        with self.lock:
            if key in self.cache:
                response, timestamp = self.cache[key]

                # Check if cache entry is still valid
                if time.time() - timestamp < self.ttl:
                    response.cached = True
                    return response
                else:
                    # Remove expired entry
                    del self.cache[key]

        return None

    def put(self, image: Image.Image, languages: List[str], response: OCRResult):
        """Store OCR result in cache.

        Args:
            image: PIL image
            languages: List of languages
            response: OCR response to cache
        """
        key = self._generate_key(image, languages)

        with self.lock:
            # Remove oldest entries if cache is full
            if len(self.cache) >= self.max_size:
                oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
                del self.cache[oldest_key]

            # Store new entry
            self.cache[key] = (response, time.time())

    def clear(self):
        """Clear all cached entries."""
        with self.lock:
            self.cache.clear()


class OCRService(SettingsObserver):
    """Main OCR service for text recognition."""

    def __init__(self):
        """Initialize OCR service."""
        self.image_processor = get_image_processor()

        # Load and cache settings initially
        self._load_and_cache_settings()

        self.cache = OCRCache(
            max_size=self.cache_enabled and self.max_cache_size or 0, ttl=self.cache_ttl
        )
        self._init_state = InitializationState.NOT_STARTED
        self._initialization_lock = threading.Lock()
        self._easyocr_reader: Optional[Any] = None
        self._lock = threading.RLock()

        # Register as an observer for settings changes
        config_service.add_observer(self)

    def _load_and_cache_settings(self):
        """Load all relevant settings from config_service and cache them as instance attributes."""
        logger.debug("Loading and caching OCR settings.")
        self.cache_enabled = config_service.get_setting("cache_enabled")
        self.max_cache_size = config_service.get_setting("max_cache_size")
        self.cache_ttl = config_service.get_setting("cache_ttl")
        self.initialize_ocr = config_service.get_setting("initialize_ocr")
        self.ocr_languages = config_service.get_setting("ocr_languages")
        self.ocr_confidence_threshold = config_service.get_setting(
            "ocr_confidence_threshold"
        )
        self.ocr_timeout = config_service.get_setting("ocr_timeout")

    def on_settings_changed(self, key: str, old_value: Any, new_value: Any):
        """Handle settings changes from ConfigService."""
        relevant_settings = [
            "cache_enabled",
            "max_cache_size",
            "cache_ttl",
            "initialize_ocr",
            "ocr_languages",
            "ocr_confidence_threshold",
            "ocr_timeout",
        ]
        if key in relevant_settings:
            logger.info(f"OCRService updating setting '{key}' to '{new_value}'")
            setattr(self, key, new_value)

            if key in ["max_cache_size", "cache_ttl", "cache_enabled"]:
                self._reconfigure_cache()

    def _reconfigure_cache(self):
        """Reconfigure the cache with updated settings."""
        if not hasattr(self, "cache"):
            return
        logger.info("Reconfiguring OCR cache with new settings.")
        with self.cache.lock:
            self.cache.max_size = self.cache_enabled and self.max_cache_size or 0
            self.cache.ttl = self.cache_ttl

    def _handle_ocr_error(self, e: Exception, start_time: float, context: str) -> OCRResult:
        """Unified error handling for OCR operations."""
        processing_time = time.time() - start_time
        logger.error(f"Error in {context}: {e}")
        logger.debug(f"Error details: {type(e).__name__}: {str(e)}", exc_info=True)
        
        return OCRResult(
            text="",
            confidence=0.0,
            engine=OCREngine.EASYOCR,
            processing_time=processing_time,
            error_message=str(e),
            success=False,
        )
    @property
    def is_initialized(self) -> bool:
        """Check if OCR service is initialized (backwards compatibility)."""
        return self._init_state == InitializationState.COMPLETED

    @property
    def is_initializing(self) -> bool:
        """Check if OCR service is currently initializing (backwards compatibility)."""
        return self._init_state == InitializationState.IN_PROGRESS

    def _initialize_engines(self):
        """Initialize EasyOCR engine."""
        # Check if OCR initialization is enabled
        if not self.initialize_ocr:
            logger.info("OCR initialization disabled by setting 'initialize_ocr=False'")
            self._init_state = InitializationState.NOT_STARTED
            return False

        start_time = time.time()
        logger.info("Starting OCR service engine initialization")
        # Get OCR languages from local cache
        logger.debug(f"OCR languages from settings: {self.ocr_languages}")

        try:
            languages = self.ocr_languages or ["en"]

            with self._lock:
                try:
                    import easyocr
                except ImportError:
                    logger.error("EasyOCR not installed")
                    self._init_state = InitializationState.FAILED
                    return False

                logger.info(f"Initializing EasyOCR with languages: {languages}")
                self._easyocr_reader = easyocr.Reader(languages)
                success = True

            initialization_time = time.time() - start_time

            if success:
                logger.info(f"EasyOCR engine initialized successfully in {initialization_time:.2f}s")
                self._init_state = InitializationState.COMPLETED
                logger.info(f"OCR service marked as initialized: {self._init_state.value}")
                logger.debug(f"OCR service ready with {len(languages)} languages: {languages}")
                return True
            else:
                logger.error(f"Failed to initialize EasyOCR engine after {initialization_time:.2f}s")
                self._init_state = InitializationState.FAILED
                return False

        except Exception as e:
            initialization_time = time.time() - start_time
            logger.error(f"Error initializing OCR engines after {initialization_time:.2f}s: {e}")
            logger.debug(f"Initialization error details: {type(e).__name__}: {str(e)}", exc_info=True)
            self._init_state = InitializationState.FAILED
            return False

    def is_engine_available(self) -> bool:
        """Check if EasyOCR engine is available and initialized.

        Returns:
            True if engine is available
        """
        return self._easyocr_reader is not None

    def _process_easyocr_array(
        self, image_array: Any, languages: List[str] = None
    ) -> OCRResult:
        """Process image array with EasyOCR.

        Args:
            image_array: Numpy array of image
            languages: Languages for OCR

        Returns:
            OCRResult with processing results
        """
        start_time = time.time()
        logger.debug("Processing image array with EasyOCR")

        # Log image array details
        try:
            logger.debug(f"Image array shape: {image_array.shape}, dtype: {image_array.dtype}")
        except Exception as e:
            logger.debug(f"Could not read array info: {e}")

        try:
            with self._lock:
                if self._easyocr_reader is None:
                    processing_time = time.time() - start_time
                    logger.warning("EasyOCR engine not initialized - processing aborted")
                    return OCRResult(
                        text="",
                        confidence=0.0,
                        engine=OCREngine.EASYOCR,
                        processing_time=processing_time,
                        error_message="Engine not initialized",
                        success=False,
                    )

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

                logger.info(f"EasyOCR: Combined text length={len(combined_text)}, average confidence={avg_confidence:.3f}")
                logger.debug(f"EasyOCR: Full combined text='{combined_text}'")

                # Determine success based on actual result
                has_text = bool(combined_text.strip())

                return OCRResult(
                    text=combined_text,
                    confidence=avg_confidence,
                    engine=OCREngine.EASYOCR,
                    processing_time=processing_time,
                    success=has_text,
                )

        except Exception as e:
            return self._handle_ocr_error(e, start_time, "_process_easyocr_array")

    def start_background_initialization(self, on_complete=None):
        """Start OCR engine initialization in a background thread."""
        with self._initialization_lock:
            if self._init_state in (InitializationState.COMPLETED, InitializationState.IN_PROGRESS):
                return

            self._init_state = InitializationState.IN_PROGRESS
            logger.info("Starting background initialization of OCR engines...")

            init_thread = threading.Thread(
                target=self._background_init_task,
                args=(on_complete,),
                daemon=True,
                name="OCREngineInitializer",
            )
            init_thread.start()

    def _background_init_task(self, on_complete):
        """Task to initialize engines and call a completion callback."""
        success = self._initialize_engines()

        with self._initialization_lock:
            self._init_state = InitializationState.COMPLETED if success else InitializationState.FAILED

        logger.info(f"Background OCR initialization complete (success={success}).")
        if on_complete:
            try:
                on_complete()
            except Exception as e:
                logger.error(f"Error in OCR initialization completion callback: {e}")

    def process_image(self, request: OCRRequest) -> OCRResult:
        """Process image with OCR.

        Args:
            request: OCR processing request

        Returns:
            OCR processing response
        """
        start_time = time.time()
        logger.debug("Starting OCR service image processing")
        logger.debug(f"Request parameters: preprocess={request.preprocess}, use_cache={request.use_cache}, timeout={request.timeout}")

        # Log image details
        logger.debug(f"Input image size: {request.image.size}, mode: {request.image.mode}")
        # Get OCR languages from local cache for logging
        logger.debug(f"OCR languages: {request.languages or self.ocr_languages}")

        if self._init_state != InitializationState.COMPLETED:
            error_msg = "OCR service is not initialized or engines not loaded (check 'initialize_ocr' setting)."
            if self._init_state == InitializationState.IN_PROGRESS:
                error_msg += " (still initializing)"
            logger.warning(f"OCR service not ready: {error_msg}")
            return OCRResult(
                text="",
                confidence=0.0,
                engine=OCREngine.EASYOCR,
                processing_time=time.time() - start_time,
                success=False,
                error_message=error_msg,
            )

        try:
            # Check cache first
            if request.use_cache and self.cache_enabled:
                cached_result = self.cache.get(request.image, request.languages or [])
                if cached_result:
                    logger.info("OCR result retrieved from cache")
                    logger.debug(f"Cached result: confidence={cached_result.confidence:.3f}, text_length={len(cached_result.text)}")
                    return cached_result

            # Preprocess image if requested
            processed_image = request.image
            if request.preprocess:
                logger.debug("Applying image preprocessing")
                processed_image = preprocess_for_ocr(
                    request.image, enhance_contrast=True, reduce_noise=True, deskew=True
                )
                logger.debug(f"Preprocessed image size: {processed_image.size}")

            # Convert PIL image to numpy array for EasyOCR
            import numpy as np

            image_array = np.array(processed_image)
            logger.debug(f"Converted to numpy array: shape={image_array.shape}, dtype={image_array.dtype}")

            # Process with EasyOCR engine using cached settings
            result = self._process_with_numpy_array(
                image_array,
                request.languages or self.ocr_languages,
                request.timeout or self.ocr_timeout,
            )

            # Determine if result is actually successful
            has_valid_text = bool(result.text.strip())
            meets_confidence = result.confidence >= self.ocr_confidence_threshold
            final_success = result.success and has_valid_text and meets_confidence

            processing_time = time.time() - start_time
            logger.info(f"OCR processing completed in {processing_time:.2f}s")
            logger.info(f"OCR results: confidence={result.confidence:.3f}, has_text={has_valid_text}, meets_threshold={meets_confidence}, final_success={final_success}")
            logger.debug(f"OCR text length: {len(result.text)} characters")

            response = OCRResult(
                text=result.text,
                confidence=result.confidence,
                engine=result.engine,
                processing_time=processing_time,
                success=final_success,
                error_message=result.error_message if not final_success else None,
            )

            # Cache successful results with valid text
            if (
                response.success
                and response.text.strip()
                and request.use_cache
                and self.cache_enabled
            ):
                self.cache.put(request.image, request.languages or [], response)
                logger.debug("OCR result cached")

            return response

        except Exception as e:
            return self._handle_ocr_error(e, start_time, "process_image")

    def _process_with_numpy_array(
        self, image_array: Any, languages: List[str], timeout: float
    ) -> OCRResult:
        """Process image with EasyOCR engine using numpy array.

        Args:
            image_array: Numpy array of image
            languages: Languages for OCR
            timeout: Processing timeout

        Returns:
            OCR result from engine
        """
        logger.debug(f"Processing numpy array with EasyOCR: shape={image_array.shape}, languages={languages}, timeout={timeout}s")

        start_time = time.time()

        try:
            # Check if EasyOCR is available
            if not self.is_engine_available():
                logger.warning("EasyOCR engine not available for processing")
                return OCRResult(
                    text="",
                    confidence=0.0,
                    engine=OCREngine.EASYOCR,
                    processing_time=0.0,
                    error_message="EasyOCR engine not available",
                    success=False,
                )

            logger.debug("EasyOCR engine is available, starting processing")
            # Process with EasyOCR engine
            result = self._process_easyocr_array(image_array, languages)

            logger.debug(f"EasyOCR processing result: success={result.success}, confidence={result.confidence:.3f}, text_length={len(result.text)}")
            return result

        except Exception as e:
            return self._handle_ocr_error(e, start_time, "_process_with_numpy_array")

    def process_image_with_translation(self, image: Image.Image, preprocess: bool = True, use_cache: bool = True) -> Tuple[str, str, str]:
        """Process image with OCR and optional translation.

        Args:
            image: PIL image to process
            preprocess: Whether to preprocess image
            use_cache: Whether to use caching

        Returns:
            Tuple of (original_text, translated_text, overlay_id)
        """
        from ..services.translation_service import get_translation_service

        logger.info("Starting OCR + translation processing")

        # OCR processing
        ocr_request = OCRRequest(
            image=image,
            languages=self.ocr_languages,
            preprocess=preprocess,
            use_cache=use_cache,
        )
        ocr_response = self.process_image(ocr_request)

        original_text = ocr_response.text
        translated_text = ""

        if original_text.strip():
            logger.info("OCR completed, checking translation availability")

            # Get translation service and check if available (uses api_manager for key validation)
            translation_service = get_translation_service(initialize=True)

            if translation_service.is_available:
                # Determine whether OCR auto-swap is enabled in settings
                settings = config_service.get_settings()
                ocr_auto_swap = getattr(settings, "ocr_auto_swap_en_ru", False)

                # If auto-swap enabled, detect language and swap en<->ru
                if ocr_auto_swap:
                    try:
                        detected = translation_service.detect_language_sync(original_text) or "auto"
                        if detected == "en":
                            target = "ru"
                        elif detected == "ru":
                            target = "en"
                        else:
                            target = "en"  # Default fallback

                        logger.debug(f"OCR auto-swap enabled: detected='{detected}', target='{target}'")
                        response = translation_service.translate_text_sync(
                            original_text, source_lang=detected, target_lang=target
                        )
                    except Exception as e:
                        logger.warning(f"OCR auto-swap detection/translation failed: {e}")
                        # Fallback to default translation call
                        response = translation_service.translate_text_sync(original_text)
                else:
                    # Use the synchronous translation API which returns a TranslationResponse
                    # When auto-swap is disabled, use UI-selected languages instead of global settings
                    ui_source = getattr(settings, "ui_source_language", "auto")
                    ui_target = getattr(settings, "ui_target_language", "en")
                    response = translation_service.translate_text_sync(
                        original_text, source_lang=ui_source, target_lang=ui_target
                    )

                if response and getattr(response, "success", False):
                    translated_text = getattr(response, "translated_text", "") or ""
                    logger.debug("Translation completed successfully")
                else:
                    error_msg = getattr(response, "error_message", "") if response else "Unknown error"
                    logger.warning(f"Translation failed or returned empty result: {error_msg}")
            else:
                logger.debug("Translation service not available (no valid API keys), skipping translation")
        else:
            logger.info("No text detected by OCR, skipping translation")

        overlay_id = f"ocr_{int(time.time() * 1000)}"

        logger.info(f"OCR + translation processing completed: text_length={len(original_text)}, translated_length={len(translated_text)}")
        return original_text, translated_text, overlay_id

    def initialize_ocr_service(self, on_complete=None):
        """Initialize OCR service in the background.

        Args:
            on_complete: Callback to call when initialization is complete
        """
        logger.info("Starting OCR service initialization in service")
        try:
            # Start background initialization and provide a callback
            self.start_background_initialization(on_complete=on_complete)
            logger.info("OCR service background initialization started successfully")
        except Exception as e:
            logger.error(f"Failed to start OCR service initialization: {e}")
            logger.debug(f"Initialization error details: {type(e).__name__}: {str(e)}", exc_info=True)

    def on_ocr_service_ready(self):
        """Callback for when OCR service is ready."""
        if self._init_state != InitializationState.COMPLETED:
            logger.info("OCR service initialization skipped (disabled)")
            return

        logger.info("OCR service initialization completed - service is now ready")
        logger.debug(f"OCR service status: state={self._init_state.value}")

        # If this was on-demand init and flag was False, update to True
        if not self.initialize_ocr:
            config_service.set_setting("initialize_ocr", True)
            logger.info("On-demand OCR init completed; updated initialize_ocr flag to True (persisted)")

    def clear_cache(self):
        """Clear OCR result cache."""
        self.cache.clear()
        logger.info("OCR cache cleared")

    def shutdown(self):
        """Shutdown OCR service and cleanup resources."""
        logger.info("Shutting down OCR service")

        # Clear cache
        self.clear_cache()

        # Clear EasyOCR reader
        with self._lock:
            self._easyocr_reader = None

        self._init_state = InitializationState.NOT_STARTED
        logger.info("OCR service shutdown complete")

    def __del__(self):
        """Cleanup on destruction."""
        self.shutdown()


# Global OCR service instance
_ocr_service: Optional[OCRService] = None


def get_ocr_service() -> OCRService:
    """Get global OCR service instance.

    Returns:
        OCRService: Global OCR service
    """
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service

