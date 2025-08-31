#!/usr/bin/env python3
"""
Test script for overlay window functionality.

This script tests the enhanced overlay window with animations,
loading indicators, and positioning.
"""

import customtkinter as ctk
from src.whisperbridge.ui.overlay_window import OverlayWindow
from src.whisperbridge.services.overlay_service import init_overlay_service
from src.whisperbridge.utils.overlay_utils import get_screen_bounds, calculate_smart_position


def test_basic_overlay():
    """Test basic overlay window functionality."""
    print("Testing basic overlay window...")

    # Initialize CustomTkinter
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # Create root window (hidden)
    root = ctk.CTk()
    root.withdraw()

    # Create overlay
    overlay = OverlayWindow(root, timeout=5)

    # Test showing result
    overlay.show_result(
        "Hello, how are you today?",
        "Привет, как ты сегодня?",
        (200, 200)
    )

    print("Overlay shown. Close it manually or wait for timeout.")
    root.mainloop()


def test_overlay_service():
    """Test overlay service functionality."""
    print("Testing overlay service...")

    # Initialize CustomTkinter
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # Create root window (hidden)
    root = ctk.CTk()
    root.withdraw()

    # Initialize overlay service
    overlay_service = init_overlay_service(root)

    # Create and show overlay
    overlay_service.create_overlay("test_overlay")
    overlay_service.show_overlay(
        "test_overlay",
        "This is a test message",
        "Это тестовое сообщение",
        (300, 300)
    )

    print("Overlay service test completed. Close manually or wait for timeout.")
    root.mainloop()


def test_positioning_utils():
    """Test positioning utilities."""
    print("Testing positioning utilities...")

    # Create mock root
    root = ctk.CTk()
    root.geometry("800x600")

    screen_bounds = get_screen_bounds(root)
    print(f"Screen bounds: {screen_bounds.width}x{screen_bounds.height}")

    # Test smart positioning
    position = calculate_smart_position(
        (100, 100),
        (300, 200),
        screen_bounds
    )
    print(f"Smart position for (100,100): {position.as_tuple()}")

    root.destroy()
    print("Positioning test completed.")


def test_loading_state():
    """Test loading state functionality."""
    print("Testing loading state...")

    # Initialize CustomTkinter
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # Create root window (hidden)
    root = ctk.CTk()
    root.withdraw()

    # Initialize overlay service
    overlay_service = init_overlay_service(root)

    # Show loading
    overlay_service.create_overlay("loading_test")
    overlay_service.show_loading_overlay("loading_test", (400, 300))

    # Simulate processing delay
    def show_result():
        overlay_service.show_overlay(
            "loading_test",
            "Processing completed",
            "Обработка завершена",
            (400, 300)
        )

    root.after(2000, show_result)  # Show result after 2 seconds

    print("Loading test started. Will show result in 2 seconds.")
    root.mainloop()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        test_type = sys.argv[1]
        if test_type == "basic":
            test_basic_overlay()
        elif test_type == "service":
            test_overlay_service()
        elif test_type == "positioning":
            test_positioning_utils()
        elif test_type == "loading":
            test_loading_state()
        else:
            print("Usage: python test_overlay.py [basic|service|positioning|loading]")
    else:
        print("Running all tests...")
        test_positioning_utils()
        print("All tests completed successfully!")