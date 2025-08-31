"""
Test script for clipboard and paste integration.

This script tests the basic functionality of the clipboard and paste services
to ensure they work correctly with the overlay window.
"""

import sys
import os
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from whisperbridge.services.clipboard_service import ClipboardService
from whisperbridge.services.paste_service import PasteService
from whisperbridge.utils.window_utils import WindowUtils


def test_clipboard_service():
    """Test clipboard service functionality."""
    print("Testing ClipboardService...")

    service = ClipboardService()

    # Start service
    if not service.start():
        print("❌ Failed to start clipboard service")
        return False

    # Test copying text
    test_text = "Hello, this is a test text for clipboard!"
    if not service.copy_text(test_text):
        print("❌ Failed to copy text")
        service.stop()
        return False

    # Test reading text
    read_text = service.get_clipboard_text()
    if read_text != test_text:
        print(f"❌ Text mismatch: expected '{test_text}', got '{read_text}'")
        service.stop()
        return False

    print("✅ Clipboard service test passed")
    service.stop()
    return True


def test_paste_service():
    """Test paste service functionality."""
    print("Testing PasteService...")

    clipboard_service = ClipboardService()
    paste_service = PasteService(clipboard_service)

    # Start services
    if not clipboard_service.start():
        print("❌ Failed to start clipboard service")
        return False

    if not paste_service.start():
        print("❌ Failed to start paste service")
        clipboard_service.stop()
        return False

    # Test paste text
    test_text = "Test paste text"
    if not paste_service.paste_text(test_text):
        print("❌ Failed to paste text")
        paste_service.stop()
        clipboard_service.stop()
        return False

    print("✅ Paste service test passed")
    paste_service.stop()
    clipboard_service.stop()
    return True


def test_window_utils():
    """Test window utilities."""
    print("Testing WindowUtils...")

    # Test getting active window
    active_window = WindowUtils.get_active_window()
    if active_window is None:
        print("⚠️  No active window found (this may be normal)")
    else:
        print(f"✅ Active window found: {active_window.title}")

    # Test window info
    if active_window:
        info = WindowUtils.get_window_info(active_window)
        if info:
            print(f"✅ Window info retrieved: {info['title']}")
        else:
            print("❌ Failed to get window info")

    print("✅ Window utils test completed")
    return True


def test_overlay_window():
    """Test overlay window with services."""
    print("Testing OverlayWindow integration...")

    try:
        import tkinter as tk
        import customtkinter as ctk
        from whisperbridge.ui.overlay_window import OverlayWindow

        # Create root window
        root = tk.Tk()
        root.withdraw()

        # Create overlay with services
        overlay = OverlayWindow(root)

        # Test showing result
        overlay.show_result(
            "Hello world",
            "Привет мир",
            (100, 100)
        )

        print("✅ Overlay window created successfully")

        # Clean up
        overlay._close_window()
        root.destroy()

        return True

    except Exception as e:
        print(f"❌ Overlay window test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("Starting Clipboard and Paste Integration Tests")
    print("=" * 50)

    tests = [
        ("Clipboard Service", test_clipboard_service),
        ("Paste Service", test_paste_service),
        ("Window Utils", test_window_utils),
        ("Overlay Window", test_overlay_window)
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\nRunning {test_name}...")
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} failed")
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")

    print("\n" + "=" * 50)
    print(f"Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())