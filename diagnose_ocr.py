import asyncio
import os
import threading
import time
from pathlib import Path

from loguru import logger

from whisperbridge.core.ocr_manager import OCREngine
from whisperbridge.services.ocr_service import OCRService, OCRRequest
from PIL import Image

def create_test_image(path: Path, text: str = "Hello, world!"):
    """Create a dummy image for testing."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.error("Pillow is not installed. Please install it with 'pip install Pillow'.")
        return

    image = Image.new("RGB", (400, 100), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font = ImageFont.load_default()
    draw.text((10, 10), text, fill="black", font=font)
    image.save(path)


async def main():
    """Main diagnostic script."""
    # Create a dummy image for testing
    test_image_path = Path("test_image.png")
    create_test_image(test_image_path)

    # Initialize the OCR service
    ocr_service = OCRService()

    # --- Test Case 1: Attempt to use unsupported engines ---
    logger.info("--- Running Test Case 1: Attempt to use unsupported engines ---")
    for engine in [OCREngine.PADDLEOCR, OCREngine.TESSERACT]:
        try:
            request = OCRRequest(
                image=Image.open(test_image_path),
                languages=["en"],
                engine=engine,
            )
            response = await ocr_service.process_image_async(request)
            if not response.success:
                logger.error(f"Unsupported engine test for {engine.value}: {response.error_message}")
            else:
                logger.info(f"Unsupported engine test for {engine.value}: Unexpected success!")
        except Exception as e:
            logger.error(f"Unsupported engine test for {engine.value}: {e}")

    # --- Test Case 2: Trigger race condition ---
    logger.info("--- Running Test Case 2: Trigger race condition ---")

    # Reset the OCR service
    ocr_service.shutdown()
    ocr_service = OCRService()

    # Start background initialization
    ocr_service.start_background_initialization()

    # Immediately try to process an image
    logger.info("Immediately processing image after starting background initialization...")
    request = OCRRequest(
        image=Image.open(test_image_path),
        languages=["en"],
    )
    response = await ocr_service.process_image_async(request)
    if not response.success:
        logger.warning(f"Race condition test: {response.error_message}")
    else:
        logger.info("Race condition test: Unexpected success!")

    # Wait for initialization to complete and try again
    await asyncio.sleep(15)
    logger.info("Processing image after waiting for initialization to complete...")
    response = await ocr_service.process_image_async(request)
    if response.success:
        logger.info("Processing after wait: Success!")
    else:
        logger.error(f"Processing after wait: {response.error_message}")

    # --- Test Case 3: Log engine stats ---
    logger.info("--- Running Test Case 3: Log engine stats ---")
    stats = ocr_service.get_engine_stats()
    logger.info(f"Engine stats: {stats}")

    # Clean up
    os.remove(test_image_path)
    ocr_service.shutdown()


if __name__ == "__main__":
    # Configure logger for this script
    log_path = Path("diagnose_ocr.log")
    logger.add(log_path, level="DEBUG")

    asyncio.run(main())