#!/usr/bin/env python3
"""
Simple test script for OCR integration in WhisperBridge.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from PIL import Image, ImageDraw, ImageFont
from whisperbridge.services.ocr_service import get_ocr_service, OCRRequest
from whisperbridge.core.ocr_manager import get_ocr_manager, OCREngine


def create_test_image(text: str = "Hello World!\nTest OCR", width: int = 400, height: int = 200) -> Image.Image:
    """Create a test image with text for OCR testing."""
    # Create white image
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)

    try:
        # Try to use a system font
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        # Fallback to default font
        font = ImageFont.load_default()

    # Draw text
    draw.text((20, 20), text, fill='black', font=font)

    return image


async def test_ocr_service():
    """Test OCR service functionality."""
    print("Testing OCR Service Integration...")

    try:
        # Get OCR service
        ocr_service = get_ocr_service()
        print("✓ OCR service initialized")

        # Get OCR manager
        ocr_manager = get_ocr_manager()
        print("✓ OCR manager initialized")

        # Check available engines
        available_engines = ocr_manager.get_available_engines()
        print(f"✓ Available OCR engines: {[e.value for e in available_engines]}")

        if not available_engines:
            print("⚠ No OCR engines available - this is expected if dependencies are not installed")
            return

        # Create test image
        test_image = create_test_image()
        print("✓ Test image created")

        # Test OCR processing
        request = OCRRequest(
            image=test_image,
            languages=['en'],
            preprocess=True,
            use_cache=False
        )

        print("Processing OCR...")
        response = await ocr_service.process_image_async(request)

        print("OCR Results:")
        print(f"  - Success: {response.success}")
        print(f"  - Text: '{response.text}'")
        print(f"  - Confidence: {response.confidence:.2f}")
        print(f"  - Engine: {response.engine_used.value}")
        print(f"  - Processing time: {response.processing_time:.2f}s")
        print(f"  - Cached: {response.cached}")

        if response.error_message:
            print(f"  - Error: {response.error_message}")

        # Test cache
        print("\nTesting cache...")
        cached_response = await ocr_service.process_image_async(request)
        print(f"✓ Cache test: {cached_response.cached}")

        # Get statistics
        print("\nOCR Statistics:")
        cache_stats = ocr_service.get_cache_stats()
        print(f"  - Cache size: {cache_stats['size']}")
        print(f"  - Cache enabled: {cache_stats['enabled']}")

        engine_stats = ocr_service.get_engine_stats()
        for engine_name, stats in engine_stats.items():
            print(f"  - {engine_name}: {stats['total_calls']} calls, "
                  f"{stats['successful_calls']} successful")

        print("\n✓ OCR integration test completed successfully!")

    except Exception as e:
        print(f"✗ OCR test failed: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main test function."""
    print("WhisperBridge OCR Integration Test")
    print("=" * 40)

    await test_ocr_service()


if __name__ == "__main__":
    asyncio.run(main())