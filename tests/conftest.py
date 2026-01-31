"""
Pytest configuration for WhisperBridge test suite.

This file provides common fixtures for all tests.
Note: Python path is configured via pyproject.toml's pythonpath setting.
"""

import logging
from pathlib import Path

import pytest
from loguru import logger


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for Qt tests."""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app
    except ImportError:
        # Qt not available - skip fixture
        pytest.skip("PySide6 not available")


@pytest.fixture
def loguru_caplog(caplog):
    """Fixture to bridge loguru to pytest caplog with proper cleanup."""
    # Remove all handlers to avoid duplicate logs or side effects
    logger.remove()
    
    # Add caplog handler
    handler_id = logger.add(caplog.handler, format="{message}")
    caplog.set_level(logging.WARNING)
    
    yield caplog
    
    # Cleanup: remove caplog handler
    try:
        logger.remove(handler_id)
    except ValueError:
        # Handler already removed
        pass
