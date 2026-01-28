import sys
import os

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

try:
    from whisperbridge.core.config import Settings
    print("Successfully imported Settings")
except ImportError as e:
    print(f"Failed to import Settings: {e}")
    sys.exit(1)

# Test 1: Valid timeout
try:
    s = Settings(api_timeout=60)
    print("Test 1 Passed: api_timeout=60 is valid")
except Exception as e:
    print(f"Test 1 Failed: {e}")

# Test 2: Invalid timeout (too high)
try:
    s = Settings(api_timeout=61)
    print("Test 2 Failed: api_timeout=61 should raise ValueError")
except ValueError as e:
    print(f"Test 2 Passed: Caught expected error: {e}")
except Exception as e:
    print(f"Test 2 Failed: Caught unexpected error: {e}")

# Test 3: Invalid timeout (too low)
try:
    s = Settings(api_timeout=0)
    print("Test 3 Failed: api_timeout=0 should raise ValueError")
except ValueError as e:
    print(f"Test 3 Passed: Caught expected error: {e}")

# Test 4: Valid timeout (middle value)
try:
    s = Settings(api_timeout=30)
    print("Test 4 Passed: api_timeout=30 is valid")
except Exception as e:
    print(f"Test 4 Failed: {e}")
