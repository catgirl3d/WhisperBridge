#!/usr/bin/env python3
"""
Debug PaddleOCR output format
"""

from paddleocr import PaddleOCR
from PIL import Image, ImageDraw, ImageFont

# Create test image
def create_test_image(text: str = "Hello World!\nTest OCR", width: int = 400, height: int = 200) -> str:
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

    # Save to file
    image_path = 'test_image.png'
    image.save(image_path, 'PNG')
    return image_path

# Test PaddleOCR
print('Initializing PaddleOCR...')
ocr = PaddleOCR(use_angle_cls=True, lang='en')

print('Creating test image...')
image_path = create_test_image()

print('Running OCR...')
result = ocr.ocr(image_path)

print('Raw result structure:')
print(f'Type: {type(result)}')
print(f'Length: {len(result) if result else 0}')

if result and result[0]:
    ocr_result = result[0]
    print(f'First element type: {type(ocr_result)}')
    print(f'Result object attributes: {dir(ocr_result)}')

    if hasattr(ocr_result, 'text'):
        print(f"Recognized Text: {ocr_result.text}")
    if hasattr(ocr_result, 'confidence'):
        print(f"Confidence: {ocr_result.confidence}")
    if hasattr(ocr_result, 'bboxes'):
        print(f"Bounding boxes: {ocr_result.bboxes}")

    # To inspect the raw structure if it's different
    if isinstance(ocr_result, list) and ocr_result:
         for i, line in enumerate(ocr_result):
            print(f"Line {i}: {line}")

else:
    print("No result from OCR")