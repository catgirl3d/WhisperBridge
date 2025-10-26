import os
import sys
from unittest.mock import patch, MagicMock

# Add the project root to Python paths for correct module imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from src.whisperbridge.core.config import Settings

# Define a fake _build_flags module structure for mocking
class FakeBuildFlags:
    def __init__(self, enabled):
        self.OCR_ENABLED = enabled

def test_ocr_enabled_from_build_flags_true():
    """
    Case 1: _build_flags.py exists and OCR_ENABLED is True.
    """
    # Mock the import to return a fake module with OCR_ENABLED = True
    mock_build_flags = FakeBuildFlags(True)
    with patch.dict('sys.modules', {'_build_flags': mock_build_flags}):
        settings = Settings()
        print(f"Case 1: ocr_enabled = {settings.ocr_enabled}")
        assert settings.ocr_enabled is True

def test_ocr_enabled_from_build_flags_false():
    """
    Case 2: _build_flags.py exists and OCR_ENABLED is False.
    """
    # Mock the import to return a fake module with OCR_ENABLED = False
    mock_build_flags = FakeBuildFlags(False)
    with patch.dict('sys.modules', {'_build_flags': mock_build_flags}):
        settings = Settings()
        print(f"Case 2: ocr_enabled = {settings.ocr_enabled}")
        assert settings.ocr_enabled is False

def test_ocr_enabled_from_env_var_true():
    """
    Case 3: _build_flags.py does not exist, use OCR_ENABLED env var (True).
    """
    # Remove _build_flags from sys.modules if it exists
    if '_build_flags' in sys.modules:
        del sys.modules['_build_flags']

    # Also remove the actual file if it exists
    import os
    if os.path.exists('_build_flags.py'):
        os.remove('_build_flags.py')

    with patch.dict(os.environ, {'OCR_ENABLED': '1'}):
        settings = Settings()
        print(f"Case 3: ocr_enabled = {settings.ocr_enabled}")
        assert settings.ocr_enabled is True

def test_ocr_enabled_from_env_var_false():
    """
    Case 4: _build_flags.py does not exist, use OCR_ENABLED env var (False).
    """
    # Remove _build_flags from sys.modules if it exists
    if '_build_flags' in sys.modules:
        del sys.modules['_build_flags']

    # Also remove the actual file if it exists
    import os
    if os.path.exists('_build_flags.py'):
        os.remove('_build_flags.py')

    with patch.dict(os.environ, {'OCR_ENABLED': '0'}):
        settings = Settings()
        print(f"Case 4: ocr_enabled = {settings.ocr_enabled}")
        assert settings.ocr_enabled is False

def test_ocr_enabled_from_env_var_string_true():
    """
    Case 5: _build_flags.py does not exist, use OCR_ENABLED env var (string 'true').
    """
    # Remove _build_flags from sys.modules if it exists
    if '_build_flags' in sys.modules:
        del sys.modules['_build_flags']

    # Also remove the actual file if it exists
    import os
    if os.path.exists('_build_flags.py'):
        os.remove('_build_flags.py')

    with patch.dict(os.environ, {'OCR_ENABLED': 'true'}):
        settings = Settings()
        print(f"Case 5: ocr_enabled = {settings.ocr_enabled}")
        assert settings.ocr_enabled is True

def test_ocr_enabled_default_true():
    """
    Case 6: Neither _build_flags.py nor OCR_ENABLED env var exist, default to True.
    """
    # Remove _build_flags from sys.modules if it exists
    if '_build_flags' in sys.modules:
        del sys.modules['_build_flags']

    # Also remove the actual file if it exists
    import os
    if os.path.exists('_build_flags.py'):
        os.remove('_build_flags.py')

    # Clear OCR_ENABLED from env if it exists
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings()
        print(f"Case 6: ocr_enabled = {settings.ocr_enabled}")
        assert settings.ocr_enabled is True

# Run tests if this file is executed directly
if __name__ == "__main__":
    print("Running OCR flag tests directly...")
    print("=" * 50)

    # Run each test manually
    try:
        test_ocr_enabled_from_build_flags_true()
        print("✓ Case 1 passed")
    except Exception as e:
        print(f"✗ Case 1 failed: {e}")

    try:
        test_ocr_enabled_from_build_flags_false()
        print("✓ Case 2 passed")
    except Exception as e:
        print(f"✗ Case 2 failed: {e}")

    try:
        test_ocr_enabled_from_env_var_true()
        print("✓ Case 3 passed")
    except Exception as e:
        print(f"✗ Case 3 failed: {e}")

    try:
        test_ocr_enabled_from_env_var_false()
        print("✓ Case 4 passed")
    except Exception as e:
        print(f"✗ Case 4 failed: {e}")

    try:
        test_ocr_enabled_from_env_var_string_true()
        print("✓ Case 5 passed")
    except Exception as e:
        print(f"✗ Case 5 failed: {e}")

    try:
        test_ocr_enabled_default_true()
        print("✓ Case 6 passed")
    except Exception as e:
        print(f"✗ Case 6 failed: {e}")

    print("=" * 50)
    print("All tests completed!")