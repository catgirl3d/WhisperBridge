#!/usr/bin/env python3
"""
Simple test to debug OCR and overlay functionality
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from PIL import Image, ImageDraw
from whisperbridge.services.ocr_service import get_ocr_service
from whisperbridge.services.translation_service import get_translation_service
from whisperbridge.core.config import settings

def create_test_image():
    """Create a simple test image with text."""
    # Create a white image
    img = Image.new('RGB', (300, 100), color='white')
    draw = ImageDraw.Draw(img)

    # Draw some text
    draw.text((10, 30), "Hello World", fill='black')

    return img

def test_ocr():
    """Test OCR functionality."""
    print("Testing OCR functionality...")

    # Create test image
    test_image = create_test_image()
    print(f"Created test image: {test_image.size}")

    # Get OCR service
    ocr_service = get_ocr_service()
    print(f"OCR service initialized: {ocr_service.is_initialized}")

    if not ocr_service.is_initialized:
        print("OCR service not initialized, initializing...")
        ocr_service._initialize_engines()

    # Create OCR request
    from whisperbridge.services.ocr_service import OCRRequest
    request = OCRRequest(
        image=test_image,
        languages=['en'],
        preprocess=True,
        use_cache=False
    )

    # Process image
    print("Processing OCR...")
    result = ocr_service.process_image(request)

    print(f"OCR Result: success={result.success}, text='{result.text}', confidence={result.confidence}")

    return result

def test_translation(text):
    """Test translation functionality."""
    print(f"\nTesting translation for: '{text}'")

    translation_service = get_translation_service()
    print(f"Translation service initialized: {translation_service.is_initialized}")

    if not translation_service.is_initialized:
        print("Translation service not initialized")
        return None

    # Translate
    result = translation_service.translate_text(
        text=text,
        source_lang='en',
        target_lang='ru',
        use_cache=False
    )

    print(f"Translation Result: success={result.success}, text='{result.translated_text}'")

    return result

def test_overlay():
    """Test overlay functionality."""
    print("\nTesting overlay functionality...")

    try:
        from whisperbridge.ui.overlay_window import OverlayWindow
        import customtkinter as ctk

        print("Creating overlay window...")

        # Create root window
        root = ctk.CTk()
        root.withdraw()  # Hide main window

        # Create overlay
        overlay = OverlayWindow(root)
        overlay.show_result("Test Original", "Test Translation")

        print("Overlay created successfully")

        # Keep window open briefly
        root.after(2000, root.quit)
        root.mainloop()

        print("Overlay test completed")

    except Exception as e:
        print(f"Overlay test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=== OCR and Translation Test ===")

    # Test OCR
    ocr_result = test_ocr()

    if ocr_result and ocr_result.success and ocr_result.text.strip():
        # Test translation
        translation_result = test_translation(ocr_result.text)

        # Test overlay
        test_overlay()
    else:
        print("OCR failed, skipping translation and overlay tests")

    print("=== Test Complete ===")