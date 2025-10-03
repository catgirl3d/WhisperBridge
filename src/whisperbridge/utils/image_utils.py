"""
Image processing utilities for OCR optimization.

This module provides comprehensive image preprocessing functions
to improve OCR accuracy including contrast enhancement, noise reduction,
scaling, and format conversion.
"""

from PIL import Image, ImageFilter, ImageEnhance
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from loguru import logger


class ImageProcessor:
    """Image processor for OCR optimization."""

    def __init__(self, max_workers: int = 4):
        """Initialize image processor.

        Args:
            max_workers: Maximum number of worker threads
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def preprocess_image(
        self,
        image: Image.Image,
        enhance_contrast: bool = True,
        reduce_noise: bool = True,
        sharpen: bool = False,
        scale_factor: float = 1.0,
    ) -> Image.Image:
        """Apply comprehensive preprocessing to image for OCR.

        Args:
            image: Input PIL image
            enhance_contrast: Whether to enhance contrast
            reduce_noise: Whether to reduce noise
            sharpen: Whether to sharpen image
            scale_factor: Scaling factor (1.0 = no scaling)

        Returns:
            Preprocessed PIL image
        """
        try:
            # Convert to grayscale if not already
            if image.mode != "L":
                image = image.convert("L")

            # Enhance contrast
            if enhance_contrast:
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(2.0)

            # Reduce noise
            if reduce_noise:
                image = image.filter(ImageFilter.MedianFilter(size=3))

            # Sharpen if requested
            if sharpen:
                image = image.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))

            # Scale image
            if scale_factor != 1.0:
                new_size = (
                    int(image.width * scale_factor),
                    int(image.height * scale_factor),
                )
                image = image.resize(new_size, Image.Resampling.LANCZOS)

            return image

        except Exception as e:
            logger.error(f"Error preprocessing image: {e}")
            return image

    def __del__(self):
        """Cleanup executor on destruction."""
        if hasattr(self, "executor"):
            self.executor.shutdown(wait=False)


# Global image processor instance
_image_processor: Optional[ImageProcessor] = None


def get_image_processor() -> ImageProcessor:
    """Get global image processor instance.

    Returns:
        ImageProcessor: Global image processor
    """
    global _image_processor
    if _image_processor is None:
        _image_processor = ImageProcessor()
    return _image_processor


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """Convenience function for OCR preprocessing.

    Args:
        image: Input PIL image

    Returns:
        Preprocessed PIL image
    """
    processor = get_image_processor()

    # Scale up small images to improve OCR accuracy
    scale_factor = 1.5

    # Apply preprocessing
    processed = processor.preprocess_image(
        image, enhance_contrast=True, reduce_noise=False, scale_factor=scale_factor
    )

    return processed
