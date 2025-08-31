"""
Logger configuration for WhisperBridge.
"""

import sys
from pathlib import Path
from loguru import logger
from .config import settings


def get_log_path() -> Path:
    """Get the log directory path."""
    return Path.home() / ".whisperbridge" / "logs"


def setup_logging():
    """Configure Loguru logger based on application settings."""
    logger.remove()  # Remove default handler

    # Console logger
    logger.add(
        sys.stderr,
        level=settings.log_level.upper(),
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    if settings.log_to_file:
        log_path = get_log_path()
        log_path.mkdir(parents=True, exist_ok=True)
        log_file = log_path / "whisperbridge.log"

        logger.add(
            log_file,
            level=settings.log_level.upper(),
            rotation=f"{settings.max_log_size} MB",
            retention="10 days",
            compression="zip",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            enqueue=True,  # Make logging non-blocking
            backtrace=True,
            diagnose=True,
        )

    logger.info("Logger initialized")
