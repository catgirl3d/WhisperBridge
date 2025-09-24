#!/usr/bin/env python3
"""
Small launcher to start WhisperBridge with the Qt UI backend.

Usage (PowerShell):
  PS> cd C:\\git\\WhisperBridge
  PS> python .\\scripts\\run_qt_app.py

Usage (cmd):
  C:\\> cd /d C:\\git\\WhisperBridge
  C:\\> python scripts\\run_qt_app.py

This script sets UI_BACKEND=qt and invokes the application's entry point.
It runs the async main() properly via asyncio.run and prints helpful diagnostics.
"""
import os
import sys
import traceback
import asyncio

from loguru import logger
# Ensure project root is on sys.path
this_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(this_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set UI backend to Qt
os.environ["UI_BACKEND"] = "qt"

logger.info(f"Starting WhisperBridge (UI_BACKEND=qt) from: {project_root}")
try:
    # Import main entrypoint
    from src.main import main as app_main
except Exception as e:
    logger.exception("Failed to import application entry point (src.main.main).")
    sys.exit(2)

try:
    # main in src.main is async — run it via asyncio.run
    if asyncio.iscoroutinefunction(app_main):
        asyncio.run(app_main())
    else:
        # fallback for non-async entrypoints
        app_main()
except Exception as e:
    logger.exception("Application raised an exception during runtime:")
    sys.exit(1)