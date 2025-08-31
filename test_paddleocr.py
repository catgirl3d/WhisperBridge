#!/usr/bin/env python3
"""
Test for PaddleOCR integration
"""

import unittest
import os
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# This check is to prevent PaddleOCR from being a hard dependency.
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False

def create_test_image(text: str = "Hello Paddle!", width: int = 600, height: int = 150) -> Image.Image:
    """Create a test image with text."""
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except IOError:
        font = ImageFont.load_default()
    draw.text((20, 20), text, fill='black', font=font)
    return image

@unittest.skipIf(not PADDLEOCR_AVAILABLE, "PaddleOCR is not installed")
class TestPaddleOCRIntegration(unittest.TestCase):
    """Test case for PaddleOCR."""

    def test_ocr_from_file(self):
        """Test basic OCR functionality from a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            image = create_test_image()
            image_path = Path(tmpdir) / "test_image.png"
            image.save(image_path)

            ocr = PaddleOCR(use_angle_cls=True, lang='en')
            result = ocr.ocr(str(image_path))

            self.assertIsNotNone(result)
            self.assertIsInstance(result, list)

            # Extract text from the OCRResult object by converting it to a string
            recognized_text = ""
            if result and result[0]:
                # The result is a list containing a single OCRResult object.
                # The __str__ representation of this object should be the recognized text.
                ocr_result = result[0]
                recognized_text = str(ocr_result)

            self.assertIn("Hello", recognized_text)
            self.assertIn("Paddle", recognized_text)

if __name__ == "__main__":
    unittest.main()