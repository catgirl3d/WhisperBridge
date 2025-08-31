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
        self.cache = OCRCache(
            max_size=settings.cache_enabled and settings.max_cache_size or 0,
            ttl=settings.cache_ttl
        )
        self.executor = ThreadPoolExecutor(max_workers=settings.thread_pool_size)
        self.is_initializing = False
        self.is_initialized = False
        self._initialization_lock = threading.Lock()

    def _initialize_engines(self):
        """Initialize OCR engines based on settings."""
        try:
            languages = settings.ocr_languages

            # Initialize primary engine
            primary_engine = OCREngine(settings.primary_ocr_engine)
            primary_success = False
            if not self.manager.is_engine_available(primary_engine):
                primary_success = self.manager.initialize_engine(primary_engine, languages)

            # Initialize fallback engine
            fallback_engine = OCREngine(settings.fallback_ocr_engine)
            fallback_success = False
            if fallback_engine != primary_engine and not self.manager.is_engine_available(fallback_engine):
                fallback_success = self.manager.initialize_engine(fallback_engine, languages)

            # Try to initialize PaddleOCR if available and not already initialized
            paddle_success = False
            if (fallback_engine != OCREngine.PADDLEOCR and
                primary_engine != OCREngine.PADDLEOCR and
                not self.manager.is_engine_available(OCREngine.PADDLEOCR)):
                try:
                    from paddleocr import PaddleOCR
                    if PaddleOCR is not None:
                        paddle_success = self.manager.initialize_engine(OCREngine.PADDLEOCR, languages)
                except ImportError:
                    pass

            success = primary_success or fallback_success or paddle_success
            logger.info(f"OCR initialization results: primary={primary_success}, fallback={fallback_success}, paddle={paddle_success}, success={success}")

            if success:
                logger.info("OCR engines initialized successfully")
                available = self.manager.get_available_engines()
                logger.info(f"Available engines: {[e.value for e in available]}")
                self.is_initialized = True
                logger.info(f"OCR service marked as initialized: {self.is_initialized}")
            else:
                logger.error("Failed to initialize any OCR engines")

        except Exception as e:
            logger.error(f"Error initializing OCR engines: {e}")

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
        self._initialize_engines()

        with self._initialization_lock:
            self.is_initializing = False
            self.is_initialized = True

        logger.info("Background OCR initialization complete.")
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

        if not self.is_initialized:
            error_msg = "OCR service is still initializing." if self.is_initializing else "OCR service is not initialized."
            logger.warning(error_msg)
            return OCRResponse(
                text="",
                confidence=0.0,
                engine_used=OCREngine.EASYOCR,
                processing_time=time.time() - start_time,
                success=False,
                error_message=error_msg
            )

        try:
            # Check cache first
            if request.use_cache and settings.cache_enabled:
                cached_result = self.cache.get(request.image, request.languages or [])
                if cached_result:
                    logger.debug("OCR result retrieved from cache")
                    return cached_result

            # Preprocess image if requested
            processed_image = request.image
            if request.preprocess:
                processed_image = preprocess_for_ocr(
                    request.image,
                    enhance_contrast=True,
                    reduce_noise=True,
                    deskew=True
                )

            # Save processed image to temporary file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_path = temp_file.name
                processed_image.save(temp_path, 'PNG')

            try:
                # Try primary engine first
                primary_engine = OCREngine(settings.primary_ocr_engine)
                result = self._process_with_engine(
                    primary_engine, temp_path,
                    request.languages or settings.ocr_languages,
                    request.timeout or settings.ocr_timeout
                )

                # Determine if result is actually successful
                has_valid_text = bool(result.text.strip())
                meets_confidence = result.confidence >= settings.ocr_confidence_threshold

                if result.success and has_valid_text and meets_confidence:
                    response = OCRResponse(
                        text=result.text,
                        confidence=result.confidence,
                        engine_used=result.engine,
                        processing_time=time.time() - start_time,
                        success=True
                    )
                else:
                    # Try fallback engines in order of preference
                    tried_engines = [primary_engine]

                    # First try the configured fallback engine
                    fallback_engine = OCREngine(settings.fallback_ocr_engine)
                    if fallback_engine != primary_engine and self.manager.is_engine_available(fallback_engine):
                        logger.info(f"Primary engine failed or low confidence, trying {fallback_engine.value}")
                        tried_engines.append(fallback_engine)
                        fallback_result = self._process_with_engine(
                            fallback_engine, temp_path,
                            request.languages or settings.ocr_languages,
                            request.timeout or settings.ocr_timeout
                        )

                        # Check if fallback result is better
                        fallback_has_text = bool(fallback_result.text.strip())
                        fallback_meets_confidence = fallback_result.confidence >= settings.ocr_confidence_threshold

                        if fallback_result.success and fallback_has_text and fallback_meets_confidence:
                            result = fallback_result

                    # If still no good result, try other available engines
                    for engine in [OCREngine.EASYOCR, OCREngine.PADDLEOCR]:
                        if engine not in tried_engines and self.manager.is_engine_available(engine):
                            logger.info(f"Trying additional engine: {engine.value}")
                            tried_engines.append(engine)
                            additional_result = self._process_with_engine(
                                engine, temp_path,
                                request.languages or settings.ocr_languages,
                                request.timeout or settings.ocr_timeout
                            )

                            # Check if this result is better
                            additional_has_text = bool(additional_result.text.strip())
                            additional_meets_confidence = additional_result.confidence >= settings.ocr_confidence_threshold

                            if additional_result.success and additional_has_text and additional_meets_confidence:
                                result = additional_result
                                break

                    # Create final response
                    final_has_text = bool(result.text.strip())
                    final_success = result.success and final_has_text

                    response = OCRResponse(
                        text=result.text,
                        confidence=result.confidence,
                        engine_used=result.engine,
                        processing_time=time.time() - start_time,
                        success=final_success,
                        error_message=result.error_message if not final_success else None
                    )

                # Cache successful results with valid text
                if response.success and response.text.strip() and request.use_cache and settings.cache_enabled:
                    self.cache.put(request.image, request.languages or [], response)

                return response

            finally:
                # Clean up temporary file
                Path(temp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Error in OCR processing: {e}")
            return OCRResponse(
                text="",
                confidence=0.0,
                engine_used=OCREngine.EASYOCR,  # Default
                processing_time=time.time() - start_time,
                success=False,
                error_message=str(e)
            )

    def _process_with_engine(self, engine: OCREngine, image_path: str,
                           languages: List[str], timeout: float) -> OCRResult:
        """Process image with specific OCR engine.

        Args:
            engine: OCR engine to use
            image_path: Path to image file
            languages: Languages for OCR
            timeout: Processing timeout

        Returns:
            OCR result from engine
        """
        try:
            # Check if engine is available
            if not self.manager.is_engine_available(engine):
                return OCRResult(
                    text="",
                    confidence=0.0,
                    engine=engine,
                    processing_time=0.0,
                    error_message=f"Engine {engine.value} not available",
                    success=False
                )

            # Process with engine
            result = self.manager.process_image(
                engine, image_path, languages, timeout
            )

            return result

        except Exception as e:
            logger.error(f"Error processing with {engine.value}: {e}")
            return OCRResult(
                text="",
                confidence=0.0,
                engine=engine,
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

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "size": self.cache.size(),
            "max_size": self.cache.max_size,
            "enabled": settings.cache_enabled
        }

    def get_engine_stats(self) -> Dict[str, Any]:
        """Get OCR engine statistics.

        Returns:
            Dictionary with engine statistics
        """
        stats = {}
        for engine in OCREngine:
            engine_stats = self.manager.get_engine_stats(engine)
            stats[engine.value] = {
                "total_calls": engine_stats.total_calls,
                "successful_calls": engine_stats.successful_calls,
                "failed_calls": engine_stats.failed_calls,
                "average_processing_time": engine_stats.average_processing_time,
                "average_confidence": engine_stats.average_confidence,
                "consecutive_failures": engine_stats.consecutive_failures,
                "available": self.manager.is_engine_available(engine)
            }
        return stats

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