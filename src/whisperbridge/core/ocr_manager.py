"""
OCR Engine Manager for WhisperBridge.

This module manages multiple OCR engines, handles automatic switching
between engines, monitors performance, and provides configuration management.
"""

import time
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor
from loguru import logger

class OCREngine(Enum):
    """Supported OCR engines."""
    EASYOCR = "easyocr"
    PADDLEOCR = "paddleocr"


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

        # Initialize stats for all engines
        for engine in OCREngine:
            self.stats[engine] = EngineStats()

    def initialize_engine(self, engine: OCREngine,
                         languages: List[str] = None,
                         **kwargs) -> bool:
        """Initialize specific OCR engine.

        Args:
            engine: OCR engine to initialize
            languages: List of languages for the engine
            **kwargs: Engine-specific initialization parameters

        Returns:
            True if initialization successful
        """
        try:
            if languages is None:
                languages = ['en']

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

                elif engine == OCREngine.PADDLEOCR:
                    try:
                        from paddleocr import PaddleOCR
                    except ImportError:
                        logger.error("PaddleOCR not installed")
                        return False

                    # Initialize PaddleOCR
                    try:
                        logger.info(f"Initializing PaddleOCR with languages: {languages}")
                        # PaddleOCR uses different language format
                        # Use only the first language or default to English
                        paddle_lang = languages[0] if languages else "en"
                        ocr = PaddleOCR(
                            use_angle_cls=True,
                            lang=paddle_lang,
                            **kwargs
                        )
                        self.engines[engine] = ocr
                    except Exception as e:
                        logger.error(f"Failed to initialize PaddleOCR: {e}")
                        return False

                else:
                    logger.error(f"Unknown OCR engine: {engine}")
                    return False

                logger.info(f"Successfully initialized {engine.value}")
                return True

        except Exception as e:
            logger.error(f"Failed to initialize {engine.value}: {e}")
            return False

    def initialize_engines(self, primary_engine: OCREngine,
                          fallback_engine: OCREngine,
                          languages: List[str] = None) -> bool:
        """Initialize primary and fallback OCR engines.

        Args:
            primary_engine: Primary OCR engine
            fallback_engine: Fallback OCR engine
            languages: List of languages

        Returns:
            True if at least one engine initialized successfully
        """
        success = False

        # Initialize primary engine
        if self.initialize_engine(primary_engine, languages):
            success = True

        # Initialize fallback engine
        if fallback_engine != primary_engine:
            if self.initialize_engine(fallback_engine, languages):
                success = True

        return success

    def process_image(self, engine: OCREngine, image_path: str,
                     languages: List[str] = None,
                     timeout: float = 10.0) -> OCRResult:
        """Process image with specific OCR engine.

        Args:
            engine: OCR engine to use
            image_path: Path to image file
            languages: Languages for OCR (optional)
            timeout: Processing timeout in seconds

        Returns:
            OCRResult with processing results
        """
        start_time = time.time()

        try:
            with self.lock:
                if engine not in self.engines:
                    processing_time = time.time() - start_time
                    # Update statistics for unavailable engine
                    self._update_stats(engine, 0.0, processing_time, False)

                    return OCRResult(
                        text="",
                        confidence=0.0,
                        engine=engine,
                        processing_time=processing_time,
                        error_message=f"Engine {engine.value} not initialized",
                        success=False
                    )

                # Process with specific engine
                if engine == OCREngine.EASYOCR:
                    result = self._process_easyocr(image_path, languages)
                elif engine == OCREngine.PADDLEOCR:
                    result = self._process_paddleocr(image_path, languages)
                else:
                    result = "", 0.0

                processing_time = time.time() - start_time

                # Determine success based on actual result
                has_text = bool(result[0].strip()) if len(result) > 0 else False
                confidence = result[1] if len(result) > 1 else 0.0

                # Update statistics
                self._update_stats(engine, confidence, processing_time, has_text)

                return OCRResult(
                    text=result[0],
                    confidence=confidence,
                    engine=engine,
                    processing_time=processing_time,
                    success=has_text
                )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Error processing with {engine.value}: {e}")

            # Update failure statistics
            self._update_stats(engine, 0.0, processing_time, False)

            return OCRResult(
                text="",
                confidence=0.0,
                engine=engine,
                processing_time=processing_time,
                error_message=str(e),
                success=False
            )

    def _process_easyocr(self, image_path: str,
                         languages: List[str] = None) -> Tuple[str, float]:
        """Process image with EasyOCR.

        Args:
            image_path: Path to image
            languages: Languages for OCR

        Returns:
            Tuple of (text, confidence)
        """
        reader = self.engines[OCREngine.EASYOCR]

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
            logger.info(f"EasyOCR Fragment {i+1}: Text='{text}', Confidence={confidence:.3f}")

        combined_text = " ".join(text_parts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        logger.info(f"EasyOCR: Combined text='{combined_text}', Average confidence={avg_confidence:.3f}")

        return combined_text, avg_confidence

    def _process_paddleocr(self, image_path: str,
                          languages: List[str] = None) -> Tuple[str, float]:
        """Process image with PaddleOCR.

        Args:
            image_path: Path to image
            languages: Languages for OCR

        Returns:
            Tuple of (text, confidence)
        """
        ocr = self.engines[OCREngine.PADDLEOCR]

        # PaddleOCR returns list of results
        results = ocr.ocr(image_path)

        if not results or not results[0]:
            return "", 0.0

        # Combine all detected text
        text_parts = []
        confidences = []

        # The result from paddlex is a list containing a single OCRResult object.
        # This object has attributes like `text` and `confidence`.
        # We need to handle this specific structure.
        for detection_result in results[0]:
            # The structure is [bbox, (text, confidence)]
            if len(detection_result) == 2:
                text = detection_result[1][0]
                confidence = detection_result[1][1]
                text_parts.append(text)
                confidences.append(confidence)

        combined_text = " ".join(text_parts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return combined_text, avg_confidence

    def _update_stats(self, engine: OCREngine, confidence: float,
                     processing_time: float, success: bool):
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
            Best performing engine or None
        """
        if not self.engines:
            return None

        best_engine = None
        best_score = -1

        for engine in self.engines:
            stats = self.stats[engine]

            if stats.total_calls == 0:
                continue

            # Calculate performance score
            success_rate = stats.successful_calls / stats.total_calls
            avg_confidence = stats.average_confidence
            avg_time = stats.average_processing_time

            # Score = success_rate * confidence / time (higher is better)
            score = success_rate * avg_confidence / max(avg_time, 0.1)

            if score > best_score:
                best_score = score
                best_engine = engine

        return best_engine

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
            List of available OCR engines
        """
        return list(self.engines.keys())

    async def process_image_async(self, engine: OCREngine, image_path: str,
                                 languages: List[str] = None,
                                 timeout: float = 10.0) -> OCRResult:
        """Asynchronously process image with OCR engine.

        Args:
            engine: OCR engine to use
            image_path: Path to image file
            languages: Languages for OCR
            timeout: Processing timeout

        Returns:
            OCRResult with processing results
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.process_image,
            engine,
            image_path,
            languages,
            timeout
        )

    def shutdown(self):
        """Shutdown the engine manager and cleanup resources."""
        logger.info("Shutting down OCR Engine Manager")

        with self.lock:
            self.engines.clear()

        if hasattr(self, 'executor'):
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