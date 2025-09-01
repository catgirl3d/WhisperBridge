#!/usr/bin/env python3
"""
Debug test for overlay window issue
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import customtkinter as ctk
from src.whisperbridge.ui.overlay_window import OverlayWindow
from src.whisperbridge.services.overlay_service import init_overlay_service

def test_direct_overlay():
    """Test direct overlay creation (should work)"""
    print("=== TESTING DIRECT OVERLAY CREATION ===")
    
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    
    root = ctk.CTk()
    root.withdraw()
    
    print("Creating overlay directly...")
    overlay = OverlayWindow(root, timeout=30)
    
    print("Showing result...")
    overlay.show_result(
        "Direct Test Original",
        "Direct Test Translation",
        (200, 200)
    )
    
    print("Direct overlay test started. Window should be visible.")
    root.after(5000, root.quit)  # Auto-close after 5 seconds
    root.mainloop()
    
    print("Direct test completed.")

def test_service_overlay():
    """Test overlay through service (problematic)"""
    print("\n=== TESTING SERVICE OVERLAY CREATION ===")
    
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    
    root = ctk.CTk()
    root.withdraw()
    
    print("Initializing overlay service...")
    overlay_service = init_overlay_service(root)
    
    print("Creating overlay through service...")
    overlay_service.create_overlay("test_service")
    
    print("Showing overlay through service...")
    success = overlay_service.show_overlay(
        "test_service",
        "Service Test Original",
        "Service Test Translation",
        (300, 300)
    )
    
    print(f"Service show_overlay returned: {success}")
    
    # Check if overlay exists
    overlay = overlay_service.get_overlay("test_service")
    print(f"Retrieved overlay: {overlay}")
    
    if overlay:
        print(f"Overlay exists: {overlay.winfo_exists()}")
        print(f"Overlay geometry: {overlay.geometry()}")
        print(f"Overlay alpha: {overlay.attributes('-alpha')}")
        print(f"Overlay state: {overlay.state()}")
    
    print("Service overlay test started. Window should be visible.")
    root.after(5000, root.quit)  # Auto-close after 5 seconds
    root.mainloop()
    
    print("Service test completed.")

if __name__ == "__main__":
    print("=== OVERLAY DEBUG TEST ===")
    
    # Test 1: Direct overlay creation
    test_direct_overlay()
    
    # Test 2: Service overlay creation
    test_service_overlay()
    
    print("=== ALL TESTS COMPLETED ===")