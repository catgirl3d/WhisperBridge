"""
Logger configuration for WhisperBridge.
"""

import sys
from pathlib import Path

from loguru import logger

from ..services.config_service import ConfigService


def get_log_path() -> Path:
    """Get the log directory path."""
    return Path.home() / ".whisperbridge" / "logs"


def setup_logging(config_service: ConfigService):
    """Configure Loguru logger based on application settings."""
    logger.remove()  # Remove default handler

    log_level = config_service.get_setting("log_level", use_cache=False)
    log_to_file = config_service.get_setting("log_to_file", use_cache=False)
    max_log_size = config_service.get_setting("max_log_size", use_cache=False)

    # Console logger
    logger.add(
        sys.stderr,
        level=log_level.upper(),
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    if log_to_file:
        log_path = get_log_path()
        log_path.mkdir(parents=True, exist_ok=True)
        log_file = log_path / "whisperbridge.log"

        logger.add(
            log_file,
            level=log_level.upper(),
            rotation=f"{max_log_size} MB",
            retention="10 days",
            compression="zip",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            enqueue=True,  # Make logging non-blocking
            backtrace=True,
            diagnose=True,
        )

    logger.info("Logger initialized")
