"""
OCR Service for WhisperBridge.

This module provides the main OCR service that integrates with multiple OCR engines,
handles image preprocessing, caching, and provides a unified interface for text recognition.
"""

import asyncio
import hashlib
import time
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from PIL import Image
import threading
from concurrent.futures import ThreadPoolExecutor
from loguru import logger

from ..core.ocr_manager import get_ocr_manager, OCREngine, OCRResult
from ..utils.image_utils import get_image_processor, preprocess_for_ocr
from ..core.config import settings
from ..services.config_service import config_service


@dataclass
class OCRRequest:
    """OCR processing request."""
    image: Image.Image
    languages: Optional[List[str]] = None
    preprocess: bool = True
    use_cache: bool = True
    timeout: Optional[float] = None


@dataclass
class OCRResponse:
    """OCR processing response."""
    text: str
    confidence: float
    engine_used: OCREngine
    processing_time: float
    cached: bool = False
    error_message: Optional[str] = None
    success: bool = True


class OCRCache:
    """Simple in-memory cache for OCR results."""

    def __init__(self, max_size: int = 100, ttl: int = 3600):
        """Initialize OCR cache.

        Args:
            max_size: Maximum number of cached items
            ttl: Time-to-live in seconds
        """
        self.cache: Dict[str, Tuple[OCRResponse, float]] = {}
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

    def get(self, image: Image.Image, languages: List[str]) -> Optional[OCRResponse]:
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

    def put(self, image: Image.Image, languages: List[str], response: OCRResponse):
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
                oldest_key = min(self.cache.keys(),
                               key=lambda k: self.cache[k][1])
                del self.cache[oldest_key]

            # Store new entry
            self.cache[key] = (response, time.time())

    def clear(self):
        """Clear all cached entries."""
        with self.lock:
            self.cache.clear()

    def size(self) -> int:
        """Get current cache size.

        Returns:
            Number of cached items
        """
        with self.lock:
            return len(self.cache)


class OCRService:
    """Main OCR service for text recognition."""

    def __init__(self):
        """Initialize OCR service."""
        self.manager = get_ocr_manager()
        self.image_processor = get_image_processor()
        # Get cache settings from config service
        cache_enabled = config_service.get_setting("cache_enabled", use_cache=False)
        max_cache_size = config_service.get_setting("max_cache_size", use_cache=False)
        cache_ttl = config_service.get_setting("cache_ttl", use_cache=False)
        thread_pool_size = config_service.get_setting("thread_pool_size", use_cache=False)

        self.cache = OCRCache(
            max_size=cache_enabled and max_cache_size or 0,
            ttl=cache_ttl
        )
        self.executor = ThreadPoolExecutor(max_workers=thread_pool_size)
        self.is_initializing = False
        self.is_initialized = False
        self._initialization_lock = threading.Lock()
        self._engines_initialized = False

    def _initialize_engines(self):
        """Initialize EasyOCR engine."""
        # Check if OCR initialization is enabled
        initialize_ocr = config_service.get_setting("initialize_ocr", use_cache=False)
        if not initialize_ocr:
            logger.info("OCR initialization disabled by setting 'initialize_ocr=False'")
            self.is_initialized = False
            self._engines_initialized = False
            return False

        start_time = time.time()
        logger.info("Starting OCR service engine initialization")
        # Get OCR languages from config service to ensure we have the latest saved values
        ocr_languages = config_service.get_setting("ocr_languages", use_cache=False)
        logger.debug(f"OCR languages from settings: {ocr_languages}")

        try:
            languages = ocr_languages

            # Initialize EasyOCR engine
            success = self.manager.initialize_engines(languages)

            initialization_time = time.time() - start_time

            if success:
                logger.info(f"EasyOCR engine initialized successfully in {initialization_time:.2f}s")
                self.is_initialized = True
                self._engines_initialized = True
                logger.info(f"OCR service marked as initialized: {self.is_initialized}")
                logger.debug(f"OCR service ready with {len(languages)} languages: {languages}")
                return True
            else:
                logger.error(f"Failed to initialize EasyOCR engine after {initialization_time:.2f}s")
                self._engines_initialized = False
                return False

        except Exception as e:
            initialization_time = time.time() - start_time
            logger.error(f"Error initializing OCR engines after {initialization_time:.2f}s: {e}")
            logger.debug(f"Initialization error details: {type(e).__name__}: {str(e)}", exc_info=True)
            self._engines_initialized = False
            return False

    def start_background_initialization(self, on_complete=None):
        """Start OCR engine initialization in a background thread."""
        with self._initialization_lock:
            if self.is_initialized or self.is_initializing:
                return

            self.is_initializing = True
            logger.info("Starting background initialization of OCR engines...")

            init_thread = threading.Thread(
                target=self._background_init_task,
                args=(on_complete,),
                daemon=True,
                name="OCREngineInitializer"
            )
            init_thread.start()

    def _background_init_task(self, on_complete):
        """Task to initialize engines and call a completion callback."""
        success = self._initialize_engines()

        with self._initialization_lock:
            self.is_initializing = False
            self.is_initialized = success

        logger.info(f"Background OCR initialization complete (success={success}).")
        if on_complete:
            try:
                on_complete()
            except Exception as e:
                logger.error(f"Error in OCR initialization completion callback: {e}")

    def process_image(self, request: OCRRequest) -> OCRResponse:
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
        # Get OCR languages from config service for logging
        ocr_languages = config_service.get_setting("ocr_languages", use_cache=False)
        logger.debug(f"OCR languages: {request.languages or ocr_languages}")

        if not self.is_initialized or not self._engines_initialized:
            error_msg = "OCR service is not initialized or engines not loaded (check 'initialize_ocr' setting)."
            if self.is_initializing:
                error_msg += " (still initializing)"
            logger.warning(f"OCR service not ready: {error_msg}")
            return OCRResponse(
                text="",
                confidence=0.0,
                engine_used=OCREngine.EASYOCR,
                processing_time=time.time() - start_time,
                success=False,
                error_message=error_msg
            )

        try:
            # Get cache settings from config service
            cache_enabled = config_service.get_setting("cache_enabled", use_cache=False)

            # Check cache first
            if request.use_cache and cache_enabled:
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
                    request.image,
                    enhance_contrast=True,
                    reduce_noise=True,
                    deskew=True
                )
                logger.debug(f"Preprocessed image size: {processed_image.size}")

            # Convert PIL image to numpy array for EasyOCR
            import numpy as np
            image_array = np.array(processed_image)
            logger.debug(f"Converted to numpy array: shape={image_array.shape}, dtype={image_array.dtype}")

            # Get OCR settings from config service
            ocr_languages = config_service.get_setting("ocr_languages", use_cache=False)
            ocr_confidence_threshold = config_service.get_setting("ocr_confidence_threshold", use_cache=False)
            ocr_timeout = config_service.get_setting("ocr_timeout", use_cache=False)

            # Process with EasyOCR engine
            result = self._process_with_numpy_array(
                image_array,
                request.languages or ocr_languages,
                request.timeout or ocr_timeout
            )

            # Determine if result is actually successful
            has_valid_text = bool(result.text.strip())
            meets_confidence = result.confidence >= ocr_confidence_threshold
            final_success = result.success and has_valid_text and meets_confidence

            processing_time = time.time() - start_time
            logger.info(f"OCR processing completed in {processing_time:.2f}s")
            logger.info(f"OCR results: confidence={result.confidence:.3f}, has_text={has_valid_text}, meets_threshold={meets_confidence}, final_success={final_success}")
            logger.debug(f"OCR text length: {len(result.text)} characters")

            response = OCRResponse(
                text=result.text,
                confidence=result.confidence,
                engine_used=result.engine,
                processing_time=processing_time,
                success=final_success,
                error_message=result.error_message if not final_success else None
            )

            # Cache successful results with valid text
            if response.success and response.text.strip() and request.use_cache and cache_enabled:
                self.cache.put(request.image, request.languages or [], response)
                logger.debug("OCR result cached")

            return response

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Error in OCR processing after {processing_time:.2f}s: {e}")
            logger.debug(f"Processing error details: {type(e).__name__}: {str(e)}", exc_info=True)
            return OCRResponse(
                text="",
                confidence=0.0,
                engine_used=OCREngine.EASYOCR,  # Default
                processing_time=processing_time,
                success=False,
                error_message=str(e)
            )

    def _process_with_numpy_array(self, image_array: Any,
                                  languages: List[str], timeout: float) -> OCRResult:
        """Process image with EasyOCR engine using numpy array.

        Args:
            image_array: Numpy array of image
            languages: Languages for OCR
            timeout: Processing timeout

        Returns:
            OCR result from engine
        """
        logger.debug(f"Processing numpy array with EasyOCR: shape={image_array.shape}, languages={languages}, timeout={timeout}s")

        try:
            # Check if EasyOCR is available
            if not self.manager.is_engine_available(OCREngine.EASYOCR):
                logger.warning("EasyOCR engine not available for processing")
                return OCRResult(
                    text="",
                    confidence=0.0,
                    engine=OCREngine.EASYOCR,
                    processing_time=0.0,
                    error_message="EasyOCR engine not available",
                    success=False
                )

            logger.debug("EasyOCR engine is available, starting processing")
            # Process with EasyOCR engine
            result = self.manager.process_image_array(
                image_array, languages, timeout
            )

            logger.debug(f"EasyOCR processing result: success={result.success}, confidence={result.confidence:.3f}, text_length={len(result.text)}")
            return result

        except Exception as e:
            logger.error(f"Error processing with EasyOCR: {e}")
            logger.debug(f"EasyOCR processing error details: {type(e).__name__}: {str(e)}", exc_info=True)
            return OCRResult(
                text="",
                confidence=0.0,
                engine=OCREngine.EASYOCR,
                processing_time=0.0,
                error_message=str(e),
                success=False
            )

    async def process_image_async(self, request: OCRRequest) -> OCRResponse:
        """Asynchronously process image with OCR.

        Args:
            request: OCR processing request

        Returns:
            OCR processing response
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.process_image,
            request
        )

    async def process_image_array_async(self, image_array: Any,
                                       languages: List[str] = None,
                                       preprocess: bool = True,
                                       use_cache: bool = True) -> OCRResponse:
        """Asynchronously process image array with OCR.

        Args:
            image_array: Numpy array of image
            languages: Languages for OCR
            preprocess: Whether to preprocess image
            use_cache: Whether to use caching

        Returns:
            OCR processing response
        """
        # Create a mock PIL image for caching purposes
        # This is a simplified approach - in production you might want to hash the array
        import numpy as np
        from PIL import Image

        # Convert numpy array back to PIL for caching compatibility
        pil_image = Image.fromarray(image_array)

        request = OCRRequest(
            image=pil_image,
            languages=languages,
            preprocess=preprocess,
            use_cache=use_cache
        )

        return await self.process_image_async(request)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        # Get cache enabled status from config service
        cache_enabled = config_service.get_setting("cache_enabled", use_cache=False)
        return {
            "size": self.cache.size(),
            "max_size": self.cache.max_size,
            "enabled": cache_enabled
        }

    def get_engine_stats(self) -> Dict[str, Any]:
        """Get OCR engine statistics.

        Returns:
            Dictionary with engine statistics for EasyOCR
        """
        engine = OCREngine.EASYOCR
        engine_stats = self.manager.get_engine_stats(engine)
        return {
            engine.value: {
                "total_calls": engine_stats.total_calls,
                "successful_calls": engine_stats.successful_calls,
                "failed_calls": engine_stats.failed_calls,
                "average_processing_time": engine_stats.average_processing_time,
                "average_confidence": engine_stats.average_confidence,
                "consecutive_failures": engine_stats.consecutive_failures,
                "available": self.manager.is_engine_available(engine)
            }
        }

    def clear_cache(self):
        """Clear OCR result cache."""
        self.cache.clear()
        logger.info("OCR cache cleared")

    def reload_settings(self):
        """Reload OCR settings and reinitialize engines if needed."""
        logger.info("Reloading OCR settings")

        # Clear cache
        self.clear_cache()

        # Reinitialize engines with new settings
        self._initialize_engines()

    def shutdown(self):
        """Shutdown OCR service and cleanup resources."""
        logger.info("Shutting down OCR service")

        # Clear cache
        self.clear_cache()

        # Shutdown manager
        self.manager.shutdown()

        # Shutdown executor
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)

        self.is_initialized = False
        self._engines_initialized = False
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


async def recognize_text(image: Image.Image,
                         languages: Optional[List[str]] = None,
                         preprocess: bool = True,
                         use_cache: bool = True) -> OCRResponse:
    """Convenience function for text recognition.

    Args:
        image: PIL image to process
        languages: Languages for OCR (optional)
        preprocess: Whether to preprocess image
        use_cache: Whether to use caching

    Returns:
        OCR response with recognized text
    """
    service = get_ocr_service()

    request = OCRRequest(
        image=image,
        languages=languages,
        preprocess=preprocess,
        use_cache=use_cache
    )

    return await service.process_image_async(request)


def recognize_text_sync(image: Image.Image,
                       languages: Optional[List[str]] = None,
                       preprocess: bool = True,
                       use_cache: bool = True) -> OCRResponse:
    """Synchronous convenience function for text recognition.

    Args:
        image: PIL image to process
        languages: Languages for OCR (optional)
        preprocess: Whether to preprocess image
        use_cache: Whether to use caching

    Returns:
        OCR response with recognized text
    """
    service = get_ocr_service()

    request = OCRRequest(
        image=image,
        languages=languages,
        preprocess=preprocess,
        use_cache=use_cache
    )

    return service.process_image(request)