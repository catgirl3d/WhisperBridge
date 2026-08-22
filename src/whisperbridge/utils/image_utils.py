"""
Image processing utilities for OCR optimization.

This module provides comprehensive image preprocessing functions
to improve OCR accuracy including contrast enhancement, noise reduction,
scaling, and format conversion.
"""

import base64
from io import BytesIO

from PIL import Image


def resize_long_edge(image: "Image.Image", max_edge: int = 1280) -> "Image.Image":
    """Resize image by longest edge while preserving aspect ratio.

    Args:
        image: Input PIL image
        max_edge: Maximum length for the longest edge

    Returns:
        Resized PIL image or original if already within limits

    Raises:
        ValueError: If max_edge is not positive
    """
    if max_edge <= 0:
        raise ValueError("max_edge must be positive")

    width, height = image.size
    if max(width, height) <= max_edge:
        return image

    if width > height:
        new_width = max_edge
        new_height = int(height * max_edge / width)
    else:
        new_height = max_edge
        new_width = int(width * max_edge / height)

    return image.resize((new_width, new_height), Image.LANCZOS)


def encode_jpeg(image: "Image.Image", quality: int = 80) -> bytes:
    """Encode image to JPEG bytes.

    Args:
        image: Input PIL image
        quality: JPEG quality (1-100)

    Returns:
        JPEG encoded bytes

    Raises:
        ValueError: If quality is not between 1 and 100
    """
    if not (1 <= quality <= 100):
        raise ValueError("quality must be between 1 and 100")

    # Convert to RGB if needed
    if image.mode != "RGB":
        image = image.convert("RGB")

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buffer.getvalue()


def to_data_url_jpeg(image: "Image.Image", max_edge: int = 1280, quality: int = 80) -> str:
    """Convert image to JPEG data URL string.

    Args:
        image: Input PIL image
        max_edge: Maximum length for the longest edge
        quality: JPEG quality (1-100)

    Returns:
        Data URL string: "data:image/jpeg;base64,..."

    Raises:
        ValueError: If max_edge is not positive or quality is not between 1 and 100
    """
    if max_edge <= 0:
        raise ValueError("max_edge must be positive")
    if not (1 <= quality <= 100):
        raise ValueError("quality must be between 1 and 100")

    resized = resize_long_edge(image, max_edge)
    jpeg_bytes = encode_jpeg(resized, quality)
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"
