#!/usr/bin/env python3
"""
Final test for overlay functionality - minimal setup
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import customtkinter as ctk
from src.whisperbridge.services.overlay_service import init_overlay_service

def test_minimal_overlay():
    """Test overlay with minimal setup"""
    print("=== TESTING MINIMAL OVERLAY SETUP ===")
    
    # Set up CustomTkinter
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    
    # Create root window
    root = ctk.CTk()
    root.title("Overlay Test")
    root.geometry("300x200")
    root.withdraw()  # Hide main window
    
    # Initialize overlay service
    print("Initializing overlay service...")
    overlay_service = init_overlay_service(root)
    
    def show_test_overlay():
        """Show test overlay after delay"""
        print("Creating and showing overlay...")
        
        # Create overlay
        overlay_service.create_overlay("test", timeout=30)
        
        # Show overlay
        success = overlay_service.show_overlay(
            "test",
            "Тестовый оригинальный текст для проверки работы оверлея",
            "Test translated text to verify overlay functionality",
            (200, 150)
        )
        
        print(f"Overlay show result: {success}")
        
        # Get overlay info
        overlay = overlay_service.get_overlay("test")
        if overlay:
            print(f"Overlay exists: {overlay.winfo_exists()}")
            print(f"Overlay geometry: {overlay.geometry()}")
            print(f"Overlay alpha: {overlay.attributes('-alpha')}")
            print("✅ Overlay should be visible now!")
        else:
            print("❌ Overlay not found")
    
    # Show overlay after 1 second
    root.after(1000, show_test_overlay)
    
    # Auto-close after 10 seconds
    root.after(10000, root.quit)
    
    print("Starting test... Overlay should appear in 1 second")
    root.mainloop()
    
    print("Test completed")

if __name__ == "__main__":
    test_minimal_overlay()