#!/usr/bin/env python3
"""
Test real scenario - simulate the actual app workflow
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import customtkinter as ctk
from src.whisperbridge.ui.app import WhisperBridgeApp

def test_real_app_scenario():
    """Test the real application scenario"""
    print("=== TESTING REAL APP SCENARIO ===")
    
    try:
        # Create the app
        app = WhisperBridgeApp()
        
        # Initialize the app
        print("Initializing app...")
        app.initialize()
        
        # Wait a moment for initialization
        app.root.after(1000, lambda: test_overlay_display(app))
        
        # Run for a limited time
        app.root.after(8000, app.root.quit)  # Auto-quit after 8 seconds
        
        print("Starting app main loop...")
        app.run()
        
    except Exception as e:
        print(f"Error in real app test: {e}")
        import traceback
        traceback.print_exc()

def test_overlay_display(app):
    """Test overlay display in the real app"""
    print("=== TESTING OVERLAY DISPLAY ===")
    
    try:
        # Test showing overlay window
        print("Calling show_overlay_window...")
        app.show_overlay_window(
            "Test Original Text from Real App",
            "Test Translation from Real App",
            (400, 300)
        )
        print("show_overlay_window called successfully")
        
        # Check overlay service state
        if app.overlay_service:
            active_overlays = app.overlay_service.get_active_overlays()
            print(f"Active overlays: {active_overlays}")
            
            if active_overlays:
                overlay = app.overlay_service.get_overlay(active_overlays[0])
                if overlay:
                    print(f"Overlay window state: {overlay.state()}")
                    print(f"Overlay geometry: {overlay.geometry()}")
                    print(f"Overlay alpha: {overlay.attributes('-alpha')}")
        
    except Exception as e:
        print(f"Error testing overlay display: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_real_app_scenario()
    print("=== REAL SCENARIO TEST COMPLETED ===")