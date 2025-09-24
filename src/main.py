"""
Main entry point for WhisperBridge application.

This module initializes and runs the WhisperBridge desktop application
for quick text translation using OCR and GPT API.
"""

import asyncio
import sys

from .whisperbridge.core.logger import logger, setup_logging
from .whisperbridge.services.config_service import config_service
from .whisperbridge.ui_qt.app import init_qt_app


async def main():
    """Main application entry point."""
    try:
        # Setup logging
        setup_logging(config_service)

        logger.info("Starting WhisperBridge application...")

        # Create and run application using Qt initializer directly
        app = init_qt_app()
        app.run()

    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)
    finally:
        logger.info("WhisperBridge application stopped")


if __name__ == "__main__":
    # Run with asyncio for async operations
    asyncio.run(main())
