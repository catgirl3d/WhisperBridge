"""
OCR Engine Manager for WhisperBridge.

This module manages multiple OCR engines, handles automatic switching
between engines, monitors performance, and provides configuration management.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


class OCREngine(Enum):
    """Supported OCR engines."""

    EASYOCR = "easyocr"


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
class EngineStats:
    """OCR engine performance statistics."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    average_processing_time: float = 0.0
    average_confidence: float = 0.0
    last_used: Optional[float] = None
    consecutive_failures: int = 0


class OCREngineManager:
    """Manager for OCR engines with automatic switching and monitoring."""

    def __init__(self, max_workers: int = 4):
        """Initialize OCR engine manager.

        Args:
            max_workers: Maximum number of worker threads
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.engines: Dict[OCREngine, Any] = {}
        self.stats: Dict[OCREngine, EngineStats] = {}
        self.lock = threading.RLock()

        # Initialize stats for EasyOCR engine
        self.stats[OCREngine.EASYOCR] = EngineStats()

    def initialize_engine(
        self, engine: OCREngine, languages: List[str] = None, **kwargs
    ) -> bool:
        """Initialize specific OCR engine.

        Args:
            engine: OCR engine to initialize
            languages: List of languages for the engine
            **kwargs: Engine-specific initialization parameters

        Returns:
            True if initialization successful
        """
        start_time = time.time()
        logger.info(f"Starting initialization of {engine.value} OCR engine")
        logger.debug(f"Initialization parameters: languages={languages}, kwargs={kwargs}")

        try:
            if languages is None:
                languages = ["en"]

            with self.lock:
                if engine == OCREngine.EASYOCR:
                    try:
                        import easyocr
                    except ImportError:
                        logger.error("EasyOCR not installed")
                        return False

                    logger.info(f"Initializing EasyOCR with languages: {languages}")
                    reader = easyocr.Reader(languages, **kwargs)
                    self.engines[engine] = reader

                else:
                    logger.error(f"Unknown OCR engine: {engine}")
                    return False

                initialization_time = time.time() - start_time
                logger.info(f"Successfully initialized {engine.value} in {initialization_time:.2f}s")
                logger.debug(f"EasyOCR reader created with {len(languages)} languages: {languages}")
                return True

        except Exception as e:
            initialization_time = time.time() - start_time
            logger.error(f"Failed to initialize {engine.value} after {initialization_time:.2f}s: {e}")
            logger.debug(f"Initialization error details: {type(e).__name__}: {str(e)}", exc_info=True)
            return False

    def initialize_engines(self, languages: List[str] = None) -> bool:
        """Initialize EasyOCR engine.

        Args:
            languages: List of languages

        Returns:
            True if engine initialized successfully
        """
        logger.info("Starting OCR engines initialization")
        if languages:
            logger.debug(f"Requested languages: {languages}")
        success = self.initialize_engine(OCREngine.EASYOCR, languages)
        if success:
            logger.info("OCR engines initialization completed successfully")
        else:
            logger.error("OCR engines initialization failed")
        return success

    def process_image(
        self, image_path: str, languages: List[str] = None, timeout: float = 10.0
    ) -> OCRResult:
        """Process image with EasyOCR engine.

        Args:
            image_path: Path to image file
            languages: Languages for OCR (optional)
            timeout: Processing timeout in seconds

        Returns:
            OCRResult with processing results
        """
        start_time = time.time()
        engine = OCREngine.EASYOCR
        logger.debug(f"Starting OCR processing for image: {image_path}")
        logger.debug(f"Processing parameters: languages={languages}, timeout={timeout}s")

        try:
            with self.lock:
                if engine not in self.engines:
                    processing_time = time.time() - start_time
                    logger.warning(f"OCR engine {engine.value} not initialized - processing aborted")
                    # Update statistics for unavailable engine
                    self._update_stats(engine, 0.0, processing_time, False)

                    return OCRResult(
                        text="",
                        confidence=0.0,
                        engine=engine,
                        processing_time=processing_time,
                        error_message=f"Engine {engine.value} not initialized",
                        success=False,
                    )

                logger.info(f"OCR engine {engine.value} is available, starting processing")
                # Process with EasyOCR engine
                result = self._process_easyocr(image_path, languages)

                processing_time = time.time() - start_time

                # Determine success based on actual result
                has_text = bool(result[0].strip()) if len(result) > 0 else False
                confidence = result[1] if len(result) > 1 else 0.0

                logger.info(f"OCR processing completed in {processing_time:.2f}s, confidence: {confidence:.3f}, has_text: {has_text}")
                logger.debug(f"OCR result text length: {len(result[0])} characters")

                # Update statistics
                self._update_stats(engine, confidence, processing_time, has_text)

                return OCRResult(
                    text=result[0],
                    confidence=confidence,
                    engine=engine,
                    processing_time=processing_time,
                    success=has_text,
                )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Error processing with {engine.value}: {e}")
            logger.debug(f"Processing error details: {type(e).__name__}: {str(e)}", exc_info=True)

            # Update failure statistics
            self._update_stats(engine, 0.0, processing_time, False)

            return OCRResult(
                text="",
                confidence=0.0,
                engine=engine,
                processing_time=processing_time,
                error_message=str(e),
                success=False,
            )

    def process_image_array(
        self, image_array: Any, languages: List[str] = None, timeout: float = 10.0
    ) -> OCRResult:
        """Process image array with EasyOCR engine.

        Args:
            image_array: Numpy array of image
            languages: Languages for OCR (optional)
            timeout: Processing timeout in seconds

        Returns:
            OCRResult with processing results
        """
        start_time = time.time()
        engine = OCREngine.EASYOCR
        logger.debug("Starting OCR processing for image array")
        logger.debug(f"Processing parameters: languages={languages}, timeout={timeout}s")

        # Log image array details
        try:
            import numpy as np
            logger.debug(f"Image array shape: {image_array.shape}, dtype: {image_array.dtype}")
        except Exception as e:
            logger.debug(f"Could not read array info: {e}")

        try:
            with self.lock:
                if engine not in self.engines:
                    processing_time = time.time() - start_time
                    logger.warning(f"OCR engine {engine.value} not initialized - processing aborted")
                    # Update statistics for unavailable engine
                    self._update_stats(engine, 0.0, processing_time, False)

                    return OCRResult(
                        text="",
                        confidence=0.0,
                        engine=engine,
                        processing_time=processing_time,
                        error_message=f"Engine {engine.value} not initialized",
                        success=False,
                    )

                logger.info(f"OCR engine {engine.value} is available, starting processing")
                # Process with EasyOCR engine
                result = self._process_easyocr_array(image_array, languages)

                processing_time = time.time() - start_time

                # Determine success based on actual result
                has_text = bool(result[0].strip()) if len(result) > 0 else False
                confidence = result[1] if len(result) > 1 else 0.0

                logger.info(f"OCR processing completed in {processing_time:.2f}s, confidence: {confidence:.3f}, has_text: {has_text}")
                logger.debug(f"OCR result text length: {len(result[0])} characters")

                # Update statistics
                self._update_stats(engine, confidence, processing_time, has_text)

                return OCRResult(
                    text=result[0],
                    confidence=confidence,
                    engine=engine,
                    processing_time=processing_time,
                    success=has_text,
                )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Error processing with {engine.value}: {e}")
            logger.debug(f"Processing error details: {type(e).__name__}: {str(e)}", exc_info=True)

            # Update failure statistics
            self._update_stats(engine, 0.0, processing_time, False)

            return OCRResult(
                text="",
                confidence=0.0,
                engine=engine,
                processing_time=processing_time,
                error_message=str(e),
                success=False,
            )

    def _process_easyocr(
        self, image_path: str, languages: List[str] = None
    ) -> Tuple[str, float]:
        """Process image with EasyOCR.

        Args:
            image_path: Path to image
            languages: Languages for OCR

        Returns:
            Tuple of (text, confidence)
        """
        reader = self.engines[OCREngine.EASYOCR]
        logger.debug(f"Processing image file: {image_path}")

        # Get image info if possible
        try:
            from PIL import Image

            with Image.open(image_path) as img:
                logger.debug(f"Image dimensions: {img.size}, mode: {img.mode}, format: {img.format}")
        except Exception as e:
            logger.debug(f"Could not read image info: {e}")

        # EasyOCR returns list of detections
        results = reader.readtext(image_path)

        if not results:
            logger.info(f"EasyOCR: No text detected in image {image_path}")
            return "", 0.0

        logger.info(f"EasyOCR: Found {len(results)} text fragments in image {image_path}")

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

        return combined_text, avg_confidence

    def _process_easyocr_array(
        self, image_array: Any, languages: List[str] = None
    ) -> Tuple[str, float]:
        """Process image array with EasyOCR.

        Args:
            image_array: Numpy array of image
            languages: Languages for OCR

        Returns:
            Tuple of (text, confidence)
        """
        reader = self.engines[OCREngine.EASYOCR]
        logger.debug("Processing image array with EasyOCR")

        # EasyOCR can process numpy arrays directly
        results = reader.readtext(image_array)

        if not results:
            logger.info("EasyOCR: No text detected in image array")
            return "", 0.0

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

        return combined_text, avg_confidence

    def _update_stats(
        self,
        engine: OCREngine,
        confidence: float,
        processing_time: float,
        success: bool,
    ):
        """Update engine statistics.

        Args:
            engine: OCR engine
            confidence: OCR confidence score
            processing_time: Processing time in seconds
            success: Whether processing was successful
        """
        stats = self.stats[engine]
        stats.total_calls += 1
        stats.last_used = time.time()

        if success:
            stats.successful_calls += 1
            stats.consecutive_failures = 0

            # Update averages
            total_time = stats.average_processing_time * (stats.successful_calls - 1)
            stats.average_processing_time = (total_time + processing_time) / stats.successful_calls

            total_conf = stats.average_confidence * (stats.successful_calls - 1)
            stats.average_confidence = (total_conf + confidence) / stats.successful_calls
        else:
            stats.failed_calls += 1
            stats.consecutive_failures += 1

    def get_engine_stats(self, engine: OCREngine) -> EngineStats:
        """Get statistics for specific engine.

        Args:
            engine: OCR engine

        Returns:
            Engine statistics
        """
        return self.stats.get(engine, EngineStats())

    def get_best_engine(self) -> Optional[OCREngine]:
        """Get the best performing engine based on statistics.

        Returns:
            EasyOCR engine if available, None otherwise
        """
        return OCREngine.EASYOCR if OCREngine.EASYOCR in self.engines else None

    def is_engine_available(self, engine: OCREngine) -> bool:
        """Check if engine is available and initialized.

        Args:
            engine: OCR engine to check

        Returns:
            True if engine is available
        """
        return engine in self.engines

    def get_available_engines(self) -> List[OCREngine]:
        """Get list of available engines.

        Returns:
            List of available OCR engines (only EasyOCR)
        """
        return [OCREngine.EASYOCR] if OCREngine.EASYOCR in self.engines else []

    async def process_image_async(self, image_path: str,
                                  languages: List[str] = None,
                                  timeout: float = 10.0) -> OCRResult:
        """Asynchronously process image with EasyOCR engine.

        Args:
            image_path: Path to image file
            languages: Languages for OCR
            timeout: Processing timeout

        Returns:
            OCRResult with processing results
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor, self.process_image, image_path, languages, timeout
        )

    async def process_image_array_async(
        self, image_array: Any, languages: List[str] = None, timeout: float = 10.0
    ) -> OCRResult:
        """Asynchronously process image array with EasyOCR engine.

        Args:
            image_array: Numpy array of image
            languages: Languages for OCR
            timeout: Processing timeout

        Returns:
            OCRResult with processing results
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor, self.process_image_array, image_array, languages, timeout
        )

    def shutdown(self):
        """Shutdown the engine manager and cleanup resources."""
        logger.info("Shutting down OCR Engine Manager")

        with self.lock:
            self.engines.clear()

        if hasattr(self, "executor"):
            self.executor.shutdown(wait=False)

        logger.info("OCR Engine Manager shutdown complete")

    def __del__(self):
        """Cleanup on destruction."""
        self.shutdown()


# Global OCR manager instance
_ocr_manager: Optional[OCREngineManager] = None


def get_ocr_manager() -> OCREngineManager:
    """Get global OCR manager instance.

    Returns:
        OCREngineManager: Global OCR manager
    """
    global _ocr_manager
    if _ocr_manager is None:
        _ocr_manager = OCREngineManager()
    return _ocr_manager
