"""
Main entry point for WhisperBridge application.

This module initializes and runs the WhisperBridge desktop application
for quick text translation using OCR and GPT API.
"""

import asyncio
import sys
import os
import threading
import traceback
from datetime import datetime
from pathlib import Path

# Early crash logging for frozen builds
def _get_crash_log_path() -> Path:
    try:
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent / "crash.log"
        else:
            return Path.home() / ".whisperbridge" / "logs" / "crash.log"
    except Exception:
        return Path.cwd() / "crash.log"

def log_crash(error: Exception):
    """Log unhandled exceptions to crash.log"""
    try:
        crash_path = _get_crash_log_path()
        crash_path.parent.mkdir(parents=True, exist_ok=True)
        with open(crash_path, 'a', encoding='utf-8') as f:
            f.write(f"{os.linesep}=== CRASH ==={os.linesep}")
            f.write(f"Time: {datetime.now().isoformat()}{os.linesep}")
            f.write(f"Frozen: {getattr(sys, 'frozen', False)}; Executable: {getattr(sys, 'executable', None)}{os.linesep}")
            f.write(f"Error: {repr(error)}{os.linesep}")
            # Use explicit exception formatting to capture correct traceback
            tb_str = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
            f.write(f"Traceback:{os.linesep}{tb_str}{os.linesep}")
    except Exception:
        pass  # Silent fail for crash logging

try:
    from whisperbridge.core.logger import logger, setup_logging
    from whisperbridge.services.config_service import config_service
    # Disable tooltip fade animation for instant display
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    # Disable desktop settings awareness to allow full control over effects
    app.setDesktopSettingsAware(False)
    # Disable the fade effect for tooltips
    app.setEffectEnabled(Qt.UI_FadeTooltip, False)
    # Optionally, also disable animation
    app.setEffectEnabled(Qt.UI_AnimateTooltip, False)
except Exception as e:
    log_crash(e)
    raise


async def _async_main():
    """Main application entry point."""
    try:
        # Setup logging
        setup_logging(config_service)

        logger.info("Starting WhisperBridge application...")

        # Import Qt app after logging is set up to avoid delays in module imports
        from whisperbridge.ui_qt.app import init_qt_app

        # Create and run application using Qt initializer directly
        app = init_qt_app()
        app.run()

    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        log_crash(e)
        sys.exit(1)
    finally:
        logger.info("WhisperBridge application stopped")


def main():
    """Console script entry point wrapper for setuptools."""
    try:
        asyncio.run(_async_main())
    except Exception as e:
        log_crash(e)
        raise


if __name__ == "__main__":
    # Route uncaught exceptions to crash.log (main and threads)
    try:
        def _excepthook(exc_type, exc, tb):
            try:
                log_crash(exc)
            finally:
                # Also print to stderr if available
                traceback.print_exception(exc_type, exc, tb)
        sys.excepthook = _excepthook

        def _thread_excepthook(args):
            try:
                log_crash(args.exc_value)
            finally:
                # Also print to stderr if available
                traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
        threading.excepthook = _thread_excepthook
    except Exception:
        pass

    try:
        # Run with asyncio for async operations
        main()
    except Exception as e:
        log_crash(e)
        raise
