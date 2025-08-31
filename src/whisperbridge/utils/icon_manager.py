"""
Icon Manager for WhisperBridge.

This module provides icon management functionality for the system tray,
including loading icons from resources, creating status indicators,
and supporting different icon formats and sizes.
"""

import base64
import io
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
from PIL import Image, ImageDraw
import pkg_resources

from loguru import logger


class IconManager:
    """Manager for system tray icons with status indication support."""

    def __init__(self):
        """Initialize the icon manager."""
        self._icon_cache: Dict[str, Any] = {}
        self._base_icons: Dict[str, Image.Image] = {}
        self._load_base_icons()

    def _load_base_icons(self):
        """Load base icons from package resources."""
        try:
            # Try to load icons from package resources
            # For now, we'll create simple programmatic icons
            # In production, replace with actual icon files
            self._create_default_icons()
            logger.info("Base icons loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load base icons: {e}")
            self._create_fallback_icons()

    def _create_default_icons(self):
        """Create default icons programmatically."""
        # Main application icon (blue circle with W)
        self._base_icons['main'] = self._create_main_icon()

        # Active/processing icon (with indicator)
        self._base_icons['active'] = self._create_active_icon()

        # Error icon (red indicator)
        self._base_icons['error'] = self._create_error_icon()

        # Idle icon (gray)
        self._base_icons['idle'] = self._create_idle_icon()

        # Loading icon (with animated dots or similar)
        self._base_icons['loading'] = self._create_loading_icon()

    def _create_main_icon(self) -> Image.Image:
        """Create the main application icon."""
        size = (64, 64)
        img = Image.new('RGBA', size, (59, 130, 246, 255))  # Blue background
        draw = ImageDraw.Draw(img)

        # Draw white 'W'
        draw.text((32, 32), 'W', fill='white', anchor='mm', font=None)

        return img

    def _create_active_icon(self) -> Image.Image:
        """Create the active/processing icon."""
        base = self._create_main_icon()
        draw = ImageDraw.Draw(base)

        # Add green indicator dot
        draw.ellipse([45, 45, 55, 55], fill=(34, 197, 94, 255))

        return base

    def _create_error_icon(self) -> Image.Image:
        """Create the error icon."""
        base = self._create_main_icon()
        draw = ImageDraw.Draw(base)

        # Add red indicator dot
        draw.ellipse([45, 45, 55, 55], fill=(239, 68, 68, 255))

        return base

    def _create_idle_icon(self) -> Image.Image:
        """Create the idle icon."""
        base = self._create_main_icon()
        draw = ImageDraw.Draw(base)

        # Add gray indicator dot
        draw.ellipse([45, 45, 55, 55], fill=(156, 163, 175, 255))

        return base

    def _create_loading_icon(self) -> Image.Image:
        """Create the loading icon."""
        base = self._create_main_icon()
        draw = ImageDraw.Draw(base)

        # Add yellow indicator dot for loading
        draw.ellipse([45, 45, 55, 55], fill=(250, 204, 21, 255))

        return base

    def _create_fallback_icons(self):
        """Create minimal fallback icons if loading fails."""
        size = (32, 32)

        # Simple colored squares as fallbacks
        self._base_icons['main'] = Image.new('RGBA', size, (59, 130, 246, 255))
        self._base_icons['active'] = Image.new('RGBA', size, (34, 197, 94, 255))
        self._base_icons['error'] = Image.new('RGBA', size, (239, 68, 68, 255))
        self._base_icons['idle'] = Image.new('RGBA', size, (156, 163, 175, 255))
        self._base_icons['loading'] = Image.new('RGBA', size, (250, 204, 21, 255))

    def get_icon(self, icon_type: str = 'main', size: Tuple[int, int] = (32, 32)) -> Optional[Any]:
        """
        Get an icon of specified type and size.

        Args:
            icon_type: Type of icon ('main', 'active', 'error', 'idle')
            size: Desired icon size as (width, height)

        Returns:
            Icon object suitable for system tray, or None if failed
        """
        try:
            cache_key = f"{icon_type}_{size[0]}x{size[1]}"

            if cache_key in self._icon_cache:
                return self._icon_cache[cache_key]

            if icon_type not in self._base_icons:
                logger.warning(f"Unknown icon type: {icon_type}, using main")
                icon_type = 'main'

            base_icon = self._base_icons[icon_type]

            # Resize if necessary
            if base_icon.size != size:
                resized_icon = base_icon.resize(size, Image.Resampling.LANCZOS)
            else:
                resized_icon = base_icon

            # Convert to format suitable for pystray
            icon_bytes = self._pil_to_icon_bytes(resized_icon)

            # Cache the result
            self._icon_cache[cache_key] = icon_bytes

            return icon_bytes

        except Exception as e:
            logger.error(f"Failed to get icon {icon_type}: {e}")
            return None

    def _pil_to_icon_bytes(self, img: Image.Image) -> bytes:
        """
        Convert PIL Image to bytes suitable for system tray.

        Args:
            img: PIL Image object

        Returns:
            Icon data as bytes
        """
        try:
            # Convert to ICO format for Windows, PNG for others
            import platform
            if platform.system() == 'Windows':
                output = io.BytesIO()
                img.save(output, format='ICO')
                return output.getvalue()
            else:
                output = io.BytesIO()
                img.save(output, format='PNG')
                return output.getvalue()
        except Exception as e:
            logger.error(f"Failed to convert PIL image to bytes: {e}")
            # Return empty bytes as fallback
            return b''

    def get_status_icon(self, is_active: bool = False, has_error: bool = False, is_loading: bool = False) -> Optional[Any]:
        """
        Get appropriate status icon based on application state.

        Args:
            is_active: Whether the application is actively processing
            has_error: Whether there's an error state
            is_loading: Whether the application is loading resources

        Returns:
            Status icon for system tray
        """
        if has_error:
            return self.get_icon('error')
        elif is_loading:
            return self.get_icon('loading')
        elif is_active:
            return self.get_icon('active')
        else:
            return self.get_icon('idle')

    def clear_cache(self):
        """Clear the icon cache to free memory."""
        self._icon_cache.clear()
        logger.debug("Icon cache cleared")

    def preload_icons(self, sizes: list = None):
        """
        Preload icons in common sizes to improve performance.

        Args:
            sizes: List of (width, height) tuples for preloading
        """
        if sizes is None:
            sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)]

        icon_types = ['main', 'active', 'error', 'idle', 'loading']

        for icon_type in icon_types:
            for size in sizes:
                self.get_icon(icon_type, size)

        logger.info(f"Preloaded {len(icon_types) * len(sizes)} icons")


# Global icon manager instance
icon_manager = IconManager()