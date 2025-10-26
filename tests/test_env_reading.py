#!/usr/bin/env python3
"""
Simple test to check how Pydantic reads .env files and environment variables.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from whisperbridge.core.config import Settings

def test_env_reading():
    print("=== Testing Environment Variable Reading ===")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Project root: {Settings.get_project_root()}")

    # Check if .env file exists
    env_file = Path('.env')
    print(f".env file exists: {env_file.exists()}")
    if env_file.exists():
        print(f".env file path: {env_file.absolute()}")
        with open(env_file, 'r') as f:
            print(f".env file contents: {f.read().strip()}")

    # Check environment variables
    print(f"os.environ.get('OCR_ENABLED'): {os.environ.get('OCR_ENABLED')}")
    print(f"os.environ.get('OCR_ENABLED', '1'): {os.environ.get('OCR_ENABLED', '1')}")

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