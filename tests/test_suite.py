#!/usr/bin/env python3
"""
WhisperBridge Master Test Suite

This script discovers and runs all unit and integration tests for the application.
"""

import unittest
import sys
import os
from pathlib import Path

def main():
    """Discover and run all tests."""
    print("Starting WhisperBridge Master Test Suite...")
    print("=" * 70)

    # Add src to path to ensure all modules can be imported
    src_path = Path(__file__).parent.parent / 'src'
    sys.path.insert(0, str(src_path))
    print(f"Added to sys.path: {src_path}")

    # Discover tests in the 'tests' directory
    loader = unittest.TestLoader()
    suite = loader.discover('tests')

    # Discover tests in the root directory (test_*.py)
    root_suite = loader.discover('.')
    suite.addTests(root_suite)

    # Run the tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("=" * 70)
    print("Master Test Suite Finished.")

    # Exit with a non-zero status code if tests failed
    if not result.wasSuccessful():
        sys.exit(1)

if __name__ == "__main__":
    # Change working directory to project root to ensure file paths are correct
    os.chdir(Path(__file__).parent.parent)
    main()