"""
Image processing utilities for OCR optimization.

This module provides comprehensive image preprocessing functions
to improve OCR accuracy including contrast enhancement, noise reduction,
scaling, and format conversion.
"""

import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
from typing import Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
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

    def optimize_for_ocr(
        self, image: Image.Image, target_dpi: int = 300, min_width: int = 800
    ) -> Image.Image:
        """Optimize image specifically for OCR engines.

        Args:
            image: Input PIL image
            target_dpi: Target DPI for scaling
            min_width: Minimum width in pixels

        Returns:
            Optimized PIL image
        """
        try:
            # Convert to RGB if needed
            if image.mode not in ["RGB", "L"]:
                image = image.convert("RGB")

            # Calculate scaling factor based on DPI
            current_width = image.width
            if current_width < min_width:
                scale_factor = min_width / current_width
                new_size = (
                    int(image.width * scale_factor),
                    int(image.height * scale_factor),
                )
                image = image.resize(new_size, Image.Resampling.LANCZOS)

            # Ensure minimum dimensions
            min_height = 100
            if image.height < min_height:
                scale_factor = min_height / image.height
                new_size = (
                    int(image.width * scale_factor),
                    int(image.height * scale_factor),
                )
                image = image.resize(new_size, Image.Resampling.LANCZOS)

            return image

        except Exception as e:
            logger.error(f"Error optimizing image for OCR: {e}")
            return image

    def convert_to_cv2(self, image: Image.Image) -> np.ndarray:
        """Convert PIL image to OpenCV format.

        Args:
            image: PIL image

        Returns:
            OpenCV image array
        """
        try:
            # Convert PIL to numpy array
            if image.mode == "RGB":
                cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            elif image.mode == "L":
                cv_image = np.array(image)
            else:
                # Convert to RGB first
                rgb_image = image.convert("RGB")
                cv_image = cv2.cvtColor(np.array(rgb_image), cv2.COLOR_RGB2BGR)

            return cv_image

        except Exception as e:
            logger.error(f"Error converting to OpenCV format: {e}")
            return np.array(image)

    def convert_from_cv2(self, cv_image: np.ndarray, mode: str = "RGB") -> Image.Image:
        """Convert OpenCV image to PIL format.

        Args:
            cv_image: OpenCV image array
            mode: PIL image mode ('RGB', 'L', etc.)

        Returns:
            PIL image
        """
        try:
            if len(cv_image.shape) == 3:
                # Color image
                pil_image = Image.fromarray(cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB))
            else:
                # Grayscale image
                pil_image = Image.fromarray(cv_image)

            if mode != pil_image.mode:
                pil_image = pil_image.convert(mode)

            return pil_image

        except Exception as e:
            logger.error(f"Error converting from OpenCV format: {e}")
            return Image.fromarray(cv_image)

    def rotate_image(self, image: Image.Image, angle: float) -> Image.Image:
        """Rotate image by specified angle.

        Args:
            image: Input PIL image
            angle: Rotation angle in degrees

        Returns:
            Rotated PIL image
        """
        try:
            return image.rotate(angle, expand=True, fillcolor="white")
        except Exception as e:
            logger.error(f"Error rotating image: {e}")
            return image

    def deskew_image(self, image: Image.Image) -> Image.Image:
        """Automatically deskew image to correct text orientation.

        Args:
            image: Input PIL image

        Returns:
            Deskewed PIL image
        """
        try:
            cv_image = self.convert_to_cv2(image)

            # Convert to grayscale if needed
            if len(cv_image.shape) == 3:
                gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            else:
                gray = cv_image

            # Apply threshold to get binary image
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # Find contours
            contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                return image

            # Find the largest contour
            largest_contour = max(contours, key=cv2.contourArea)

            # Get minimum area rectangle
            rect = cv2.minAreaRect(largest_contour)
            angle = rect[2]

            # Correct angle if needed
            if angle < -45:
                angle = 90 + angle

            # Rotate image
            if abs(angle) > 0.5:  # Only rotate if angle is significant
                return self.rotate_image(image, angle)

            return image

        except Exception as e:
            logger.error(f"Error deskewing image: {e}")
            return image

    def enhance_text_contrast(self, image: Image.Image) -> Image.Image:
        """Enhance text contrast using adaptive thresholding.

        Args:
            image: Input PIL image

        Returns:
            Enhanced PIL image
        """
        try:
            cv_image = self.convert_to_cv2(image)

            # Convert to grayscale
            if len(cv_image.shape) == 3:
                gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            else:
                gray = cv_image

            # Apply adaptive thresholding
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )

            return self.convert_from_cv2(binary, "L")

        except Exception as e:
            logger.error(f"Error enhancing text contrast: {e}")
            return image

    def save_intermediate_image(
        self, image: Image.Image, step_name: str, output_dir: Optional[Path] = None
    ) -> Optional[Path]:
        """Save intermediate image for debugging purposes.

        Args:
            image: Image to save
            step_name: Name of processing step
            output_dir: Output directory (optional)

        Returns:
            Path to saved image or None if failed
        """
        try:
            if output_dir is None:
                output_dir = Path.home() / ".whisperbridge" / "debug_images"
                output_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename with hash
            image_hash = hashlib.md5(image.tobytes()).hexdigest()[:8]
            filename = f"{step_name}_{image_hash}.png"
            filepath = output_dir / filename

            image.save(filepath, "PNG")
            logger.debug(f"Saved intermediate image: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Error saving intermediate image: {e}")
            return None

    async def preprocess_async(self, image: Image.Image, **kwargs) -> Image.Image:
        """Asynchronously preprocess image.

        Args:
            image: Input PIL image
            **kwargs: Preprocessing parameters

        Returns:
            Preprocessed PIL image
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor, self.preprocess_image, image, **kwargs
        )

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
