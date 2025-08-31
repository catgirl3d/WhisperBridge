"""
UI package for WhisperBridge.

This package contains all user interface components including
main windows, overlays, system tray, and capture interfaces.
"""

from .main_window import MainWindow
from .overlay_window import OverlayWindow
from .app import WhisperBridgeApp, get_app, init_app

__all__ = ['MainWindow', 'OverlayWindow', 'WhisperBridgeApp', 'get_app', 'init_app']