"""
UI package for WhisperBridge.

This package contains all user interface components including
main windows, overlays, system tray, and capture interfaces.
"""

# Import both UI implementations
from .main_window import MainWindow
from .overlay_window import OverlayWindow
from .app import WhisperBridgeApp, get_app, init_app

# Import Qt implementation
try:
    # First check if PySide6 is available
    import PySide6
    from ..ui_qt import QtApp
    from ..ui_qt.app import get_qt_app, init_qt_app
    _qt_available = True
except ImportError:
    _qt_available = False
    QtApp = None
    get_qt_app = None
    init_qt_app = None


def _get_ui_backend():
    """Get the current UI backend from settings."""
    from ..core.config import settings
    return getattr(settings, 'ui_backend', 'ctk').lower()


def get_app_class():
    """Get the appropriate app class based on UI backend setting."""
    backend = _get_ui_backend()

    if backend == 'qt':
        if not _qt_available:
            raise ImportError("Qt UI backend requested but PySide6 is not available")
        return QtApp
    else:
        # Default to CTK
        return WhisperBridgeApp


def get_app_instance():
    """Get the appropriate app instance based on UI backend setting."""
    backend = _get_ui_backend()

    if backend == 'qt':
        if not _qt_available:
            raise ImportError("Qt UI backend requested but PySide6 is not available")
        return get_qt_app()
    else:
        # Default to CTK
        return get_app()


def init_app():
    """Initialize and return the appropriate app instance based on UI backend setting."""
    backend = _get_ui_backend()

    if backend == 'qt':
        if not _qt_available:
            raise ImportError("Qt UI backend requested but PySide6 is not available")
        return init_qt_app()
    else:
        # Default to CTK - import here to avoid circular imports
        from .app import init_app as init_ctk_app
        return init_ctk_app()


__all__ = [
    'MainWindow', 'OverlayWindow',
    'WhisperBridgeApp', 'get_app', 'init_app',
    'QtApp', 'get_qt_app', 'init_qt_app',
    'get_app_class', 'get_app_instance'
]