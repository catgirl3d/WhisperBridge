"""
OCR Diagnostics Tests for WhisperBridge.

This module contains comprehensive tests for isolating and diagnosing OCR-related issues,
including race conditions, image quality problems, and configuration issues.
"""

import pytest
import asyncio
import time
import tempfile
import threading
from pathlib import Path
from typing import List, Tuple
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Import WhisperBridge components
from src.whisperbridge.core.ocr_manager import OCREngineManager, OCREngine, OCRResult
from src.whisperbridge.services.ocr_service import OCRService, OCRRequest, OCRResponse
from src.whisperbridge.core.config import settings


class TestImageGenerator:
    """Helper class for generating test images with known text."""

    @staticmethod
    def create_text_image(text: str, width: int = 400, height: int = 100,
                         font_size: int = 20, bg_color: str = 'white',
                         text_color: str = 'black') -> Image.Image:
        """Create a PIL image with specified text.

        Args:
            text: Text to render
            width: Image width
            height: Image height
            font_size: Font size
            bg_color: Background color
            text_color: Text color

        Returns:
            PIL Image with text
        """
        # Create image
        image = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(image)

        # Try to use a system font, fallback to default
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
            except OSError:
                font = ImageFont.load_default()

        # Calculate text position (centered)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2

        # Draw text
        draw.text((x, y), text, fill=text_color, font=font)

        return image

    @staticmethod
    def create_test_images() -> List[Tuple[str, Image.Image]]:
        """Create a set of test images with known text.

        Returns:
            List of (expected_text, image) tuples
        """
        test_cases = [
            ("HELLO WORLD", "white", "black"),
            ("Test 123", "white", "black"),
            ("Mixed Case Text", "lightgray", "black"),
            ("Numbers: 42", "white", "blue"),
            ("Symbols: @#$%", "white", "red"),
        ]

        images = []
        for text, bg, fg in test_cases:
            image = TestImageGenerator.create_text_image(text, bg_color=bg, text_color=fg)
            images.append((text, image))

        return images

    @staticmethod
    def save_test_images(directory: Path) -> List[Tuple[str, Path]]:
        """Save test images to files in different formats.

        Args:
            directory: Directory to save images

        Returns:
            List of (expected_text, file_path) tuples
        """
        directory.mkdir(exist_ok=True)
        test_images = TestImageGenerator.create_test_images()
        saved_files = []

        for i, (text, image) in enumerate(test_images):
            # Save as PNG
            png_path = directory / f"test_{i}.png"
            image.save(png_path, 'PNG')
            saved_files.append((text, png_path))

            # Save as JPEG
            jpeg_path = directory / f"test_{i}.jpg"
            image.save(jpeg_path, 'JPEG', quality=95)
            saved_files.append((text, jpeg_path))

        return saved_files


class TestRaceCondition:
    """Tests for race condition issues in OCR initialization."""

    def test_ocr_before_initialization(self):
        """Test OCR processing before engine initialization."""
        service = OCRService()

        # Don't initialize the service
        test_image = TestImageGenerator.create_text_image("Test")

        request = OCRRequest(
            image=test_image,
            languages=['en'],
            preprocess=False,
            use_cache=False
        )

        response = service.process_image(request)

        # Should fail with initialization error
        assert not response.success
        assert response.error_message is not None
        assert "not initialized" in response.error_message.lower()

    def test_concurrent_initialization(self):
        """Test multiple threads trying to initialize simultaneously."""
        results = []
        errors = []

        def init_worker(service, results, errors):
            try:
                service._initialize_engines()
                results.append(True)
            except Exception as e:
                errors.append(str(e))
                results.append(False)

        # Create multiple services
        services = [OCRService() for _ in range(3)]

        # Start initialization in parallel
        threads = []
        for service in services:
            thread = threading.Thread(
                target=init_worker,
                args=(service, results, errors)
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # All should succeed (no race condition)
        assert all(results), f"Initialization failures: {errors}"

    def test_initialization_timing(self):
        """Test timing of OCR initialization process."""
        service = OCRService()

        start_time = time.time()
        service._initialize_engines()
        init_time = time.time() - start_time

        # Initialization should complete within reasonable time
        assert init_time < 30.0, f"Initialization took too long: {init_time:.2f}s"

        # Service should be marked as initialized
        assert service.is_initialized

    def test_background_initialization_callback(self):
        """Test background initialization with completion callback."""
        service = OCRService()

        callback_called = False
        callback_error = None

        def on_complete():
            nonlocal callback_called, callback_error
            try:
                callback_called = True
                assert service.is_initialized
            except Exception as e:
                callback_error = str(e)

        # Start background initialization
        service.start_background_initialization(on_complete)

        # Wait for initialization to complete
        timeout = 30
        start_time = time.time()
        while not service.is_initialized and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        assert service.is_initialized, "Background initialization did not complete"
        assert callback_called, "Completion callback was not called"
        assert callback_error is None, f"Callback error: {callback_error}"


class TestImageQuality:
    """Tests for OCR performance with different image qualities."""

    @pytest.fixture
    def ocr_service(self):
        """Fixture to provide initialized OCR service."""
        service = OCRService()
        service._initialize_engines()
        return service

    @pytest.fixture
    def test_images(self):
        """Fixture to provide test images."""
        return TestImageGenerator.create_test_images()

    def test_basic_text_recognition(self, ocr_service, test_images):
        """Test OCR on basic text images."""
        for expected_text, image in test_images:
            request = OCRRequest(
                image=image,
                languages=['en'],
                preprocess=False,
                use_cache=False
            )

            response = ocr_service.process_image(request)

            # Should successfully recognize text
            assert response.success, f"Failed to recognize text in image: {expected_text}"
            assert response.confidence > 0.0
            assert len(response.text.strip()) > 0

            # Text should contain expected content (case-insensitive)
            recognized_lower = response.text.lower()
            expected_lower = expected_text.lower()
            assert expected_lower in recognized_lower, \
                f"Expected '{expected_text}' not found in '{response.text}'"

    def test_image_formats(self, ocr_service):
        """Test OCR with different image formats."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_files = TestImageGenerator.save_test_images(Path(temp_dir))

            for expected_text, file_path in test_files:
                # Load image from file
                image = Image.open(file_path)

                request = OCRRequest(
                    image=image,
                    languages=['en'],
                    preprocess=False,
                    use_cache=False
                )

                response = ocr_service.process_image(request)

                assert response.success, f"Failed to process {file_path.suffix} format"
                assert len(response.text.strip()) > 0

    def test_image_resolutions(self, ocr_service):
        """Test OCR with different image resolutions."""
        base_text = "Resolution Test"
        resolutions = [(200, 50), (400, 100), (800, 200)]

        for width, height in resolutions:
            image = TestImageGenerator.create_text_image(
                base_text, width=width, height=height
            )

            request = OCRRequest(
                image=image,
                languages=['en'],
                preprocess=False,
                use_cache=False
            )

            response = ocr_service.process_image(request)

            # Should work at all resolutions
            assert response.success, f"Failed at resolution {width}x{height}"
            assert len(response.text.strip()) > 0

    def test_preprocessing_effects(self, ocr_service):
        """Test the impact of image preprocessing on OCR quality."""
        # Create a low-quality image (noisy, low contrast)
        image = TestImageGenerator.create_text_image(
            "Preprocessing Test",
            bg_color='lightgray',
            text_color='gray'
        )

        # Test without preprocessing
        request_no_prep = OCRRequest(
            image=image,
            languages=['en'],
            preprocess=False,
            use_cache=False
        )

        response_no_prep = ocr_service.process_image(request_no_prep)

        # Test with preprocessing
        request_with_prep = OCRRequest(
            image=image,
            languages=['en'],
            preprocess=True,
            use_cache=False
        )

        response_with_prep = ocr_service.process_image(request_with_prep)

        # Both should work, but preprocessing might improve results
        assert response_no_prep.success or response_with_prep.success
        if response_no_prep.success and response_with_prep.success:
            # Preprocessing should not make results worse
            assert response_with_prep.confidence >= response_no_prep.confidence * 0.8

    def test_image_array_processing(self, ocr_service):
        """Test OCR processing with numpy arrays."""
        test_text = "Array Test"
        image = TestImageGenerator.create_text_image(test_text)
        image_array = np.array(image)

        # Process via service (converts to array internally)
        request = OCRRequest(
            image=image,
            languages=['en'],
            preprocess=False,
            use_cache=False
        )

        response = ocr_service.process_image(request)

        assert response.success
        assert len(response.text.strip()) > 0


class TestOCRSettings:
    """Tests for OCR configuration and settings."""

    @pytest.fixture
    def ocr_service(self):
        """Fixture to provide initialized OCR service."""
        service = OCRService()
        service._initialize_engines()
        return service

    def test_language_settings(self, ocr_service):
        """Test OCR with different language settings."""
        test_text = "Hello World"
        image = TestImageGenerator.create_text_image(test_text)

        languages_to_test = [
            ['en'],  # English only
            ['en', 'es'],  # English + Spanish
            ['en', 'fr', 'de'],  # Multiple languages
        ]

        for languages in languages_to_test:
            request = OCRRequest(
                image=image,
                languages=languages,
                preprocess=False,
                use_cache=False
            )

            response = ocr_service.process_image(request)

            # Should work with different language configurations
            assert response.success, f"Failed with languages: {languages}"

    def test_confidence_threshold(self, ocr_service):
        """Test OCR confidence threshold behavior."""
        test_text = "Confidence Test"
        image = TestImageGenerator.create_text_image(test_text)

        # Test with different confidence thresholds
        thresholds = [0.0, 0.5, 0.8, 0.95]

        for threshold in thresholds:
            # Temporarily modify settings
            original_threshold = settings.ocr_confidence_threshold
            settings.ocr_confidence_threshold = threshold

            try:
                request = OCRRequest(
                    image=image,
                    languages=['en'],
                    preprocess=False,
                    use_cache=False
                )

                response = ocr_service.process_image(request)

                # Success depends on threshold
                if response.confidence >= threshold:
                    assert response.success, f"Should succeed with confidence {response.confidence} >= {threshold}"
                else:
                    assert not response.success, f"Should fail with confidence {response.confidence} < {threshold}"

            finally:
                # Restore original threshold
                settings.ocr_confidence_threshold = original_threshold

    def test_cache_functionality(self, ocr_service):
        """Test OCR caching functionality."""
        test_text = "Cache Test"
        image = TestImageGenerator.create_text_image(test_text)

        # First request (should not be cached)
        request1 = OCRRequest(
            image=image,
            languages=['en'],
            preprocess=False,
            use_cache=True
        )

        response1 = ocr_service.process_image(request1)
        assert response1.success
        assert not response1.cached

        # Second request (should be cached)
        request2 = OCRRequest(
            image=image,
            languages=['en'],
            preprocess=False,
            use_cache=True
        )

        response2 = ocr_service.process_image(request2)
        assert response2.success
        assert response2.cached

        # Results should be identical
        assert response1.text == response2.text
        assert response1.confidence == response2.confidence

    def test_timeout_handling(self, ocr_service):
        """Test OCR timeout handling."""
        test_text = "Timeout Test"
        image = TestImageGenerator.create_text_image(test_text)

        # Test with very short timeout
        request = OCRRequest(
            image=image,
            languages=['en'],
            preprocess=False,
            use_cache=False,
            timeout=0.001  # Very short timeout
        )

        start_time = time.time()
        response = ocr_service.process_image(request)
        processing_time = time.time() - start_time

        # Should either succeed quickly or fail gracefully
        assert processing_time < 1.0, "Processing took too long even with short timeout"


class TestIntegration:
    """Integration tests for full OCR workflow."""

    @pytest.fixture
    def ocr_service(self):
        """Fixture to provide initialized OCR service."""
        service = OCRService()
        service._initialize_engines()
        return service

    def test_full_workflow_sync(self, ocr_service):
        """Test complete OCR workflow synchronously."""
        # Create test image
        test_text = "Integration Test Sync"
        image = TestImageGenerator.create_text_image(test_text)

        # Process through service
        request = OCRRequest(
            image=image,
            languages=['en'],
            preprocess=True,
            use_cache=True
        )

        response = ocr_service.process_image(request)

        # Verify results
        assert response.success
        assert response.confidence > 0.0
        assert len(response.text.strip()) > 0
        assert response.processing_time > 0.0
        assert response.engine_used == OCREngine.EASYOCR

    @pytest.mark.asyncio
    async def test_full_workflow_async(self, ocr_service):
        """Test complete OCR workflow asynchronously."""
        # Create test image
        test_text = "Integration Test Async"
        image = TestImageGenerator.create_text_image(test_text)

        # Process asynchronously
        request = OCRRequest(
            image=image,
            languages=['en'],
            preprocess=True,
            use_cache=True
        )

        response = await ocr_service.process_image_async(request)

        # Verify results
        assert response.success
        assert response.confidence > 0.0
        assert len(response.text.strip()) > 0
        assert response.processing_time > 0.0
        assert response.engine_used == OCREngine.EASYOCR

    def test_multiple_images_batch(self, ocr_service):
        """Test processing multiple images in sequence."""
        test_cases = [
            "First Image",
            "Second Image",
            "Third Image"
        ]

        results = []
        for test_text in test_cases:
            image = TestImageGenerator.create_text_image(test_text)

            request = OCRRequest(
                image=image,
                languages=['en'],
                preprocess=False,
                use_cache=False
            )

            response = ocr_service.process_image(request)
            results.append((test_text, response))

        # All should succeed
        for expected_text, response in results:
            assert response.success, f"Failed to process: {expected_text}"
            assert len(response.text.strip()) > 0

    def test_error_recovery(self, ocr_service):
        """Test error recovery and continued operation."""
        # Create valid image
        valid_text = "Valid Image"
        valid_image = TestImageGenerator.create_text_image(valid_text)

        # Create invalid image (empty)
        invalid_image = Image.new('RGB', (100, 100), 'white')

        # Process valid image first
        request1 = OCRRequest(
            image=valid_image,
            languages=['en'],
            preprocess=False,
            use_cache=False
        )

        response1 = ocr_service.process_image(request1)
        assert response1.success

        # Process invalid image
        request2 = OCRRequest(
            image=invalid_image,
            languages=['en'],
            preprocess=False,
            use_cache=False
        )

        response2 = ocr_service.process_image(request2)
        # May or may not succeed, but should not crash

        # Process valid image again (should still work)
        request3 = OCRRequest(
            image=valid_image,
            languages=['en'],
            preprocess=False,
            use_cache=False
        )

        response3 = ocr_service.process_image(request3)
        assert response3.success, "Service should recover after processing invalid image"


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])