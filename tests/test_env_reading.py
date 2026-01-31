#!/usr/bin/env python3
"""
Simple test to check how Pydantic reads .env files and environment variables.
"""

import os
from pathlib import Path

from whisperbridge.core.config import BUILD_OCR_ENABLED, Settings

def test_env_reading():
    print("=== Testing Environment Variable Reading ===")
    print(f"Current working directory: {os.getcwd()}")
    project_root = Settings.get_project_root()
    print(f"Project root: {project_root}")

    # Check if .env file exists (use absolute path)
    env_file = project_root / '.env'
    print(f".env file exists: {env_file.exists()}")
    if env_file.exists():
        print(f".env file path: {env_file.absolute()}")
        with open(env_file, 'r') as f:
            print(f".env file contents: {f.read().strip()}")

    # Check environment variables (build-time flags)
    print(f"os.environ.get('WHISPERBRIDGE_BUILD_OCR'): {os.environ.get('WHISPERBRIDGE_BUILD_OCR')}")
    print(f"os.environ.get('OCR_ENABLED') [legacy]: {os.environ.get('OCR_ENABLED')}")
    print(f"BUILD_OCR_ENABLED (resolved): {BUILD_OCR_ENABLED}")

    # Test Pydantic settings loading
    print("\n=== Testing Pydantic Settings Loading ===")
    try:
        settings = Settings()
        print(f"Settings loaded successfully")
        print(f"ocr_enabled: {settings.ocr_enabled}")
        print(f"api_provider: {settings.api_provider}")
    except Exception as e:
        print(f"Error loading settings: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_env_reading()