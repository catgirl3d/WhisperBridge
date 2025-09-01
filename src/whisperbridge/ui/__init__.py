"""
UI package for WhisperBridge.

This package contains all user interface components including
main windows, overlays, system tray, and capture interfaces.
"""

# Import both UI implementations
from .main_window import MainWindow
from .overlay_window import OverlayWindow
from .app import WhisperBridgeApp, get_app, init_app

# Import Qt implementation with granular availability checks
_qt_available = False
_qt_app_import_ok = False
QtApp = None
get_qt_app = None
init_qt_app = None

# Step 1: Check if PySide6 is available
try:
    import PySide6
    _qt_available = True
except ImportError:
    _qt_available = False

# Step 2: Try Qt app imports only if PySide6 is available
if _qt_available:
    try:
        from ..ui_qt import QtApp
        _qt_app_import_ok = True
    except ImportError:
        _qt_app_import_ok = False
        QtApp = None

    # Step 3: Try Qt app functions import only if QtApp succeeded
    if _qt_app_import_ok:
        try:
            from ..ui_qt.app import get_qt_app, init_qt_app
        except ImportError:
            get_qt_app = None
            init_qt_app = None
            _qt_app_import_ok = False


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
        if not _qt_app_import_ok:
            raise ImportError("Qt UI backend requested but Qt application imports failed (PySide6 is available)")
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
        if not _qt_app_import_ok:
            raise ImportError("Qt UI backend requested but Qt application imports failed (PySide6 is available)")
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
        if not _qt_app_import_ok:
            raise ImportError("Qt UI backend requested but Qt application imports failed (PySide6 is available)")
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