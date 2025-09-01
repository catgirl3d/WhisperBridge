#!/usr/bin/env python3
"""
Simple test for overlay functionality - direct usage
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import customtkinter as ctk

def test_simple_overlay():
    """Test overlay with direct import"""
    print("=== TESTING SIMPLE OVERLAY ===")
    
    # Set up CustomTkinter
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    
    # Create root window
    root = ctk.CTk()
    root.title("Overlay Test")
    root.geometry("300x200")
    root.withdraw()  # Hide main window
    
    def show_test_overlay():
        """Show test overlay after delay"""
        print("Creating overlay...")
        
        # Import here to avoid circular imports
        from src.whisperbridge.ui.overlay_window import OverlayWindow
        
        # Create overlay directly
        overlay = OverlayWindow(root, timeout=30)
        
        print("Showing overlay...")
        overlay.show_result(
            "Тестовый оригинальный текст для проверки работы оверлея. Этот текст должен быть виден в окне оверлея.",
            "Test translated text to verify overlay functionality. This text should be visible in the overlay window.",
            (200, 150)
        )
        
        print("✅ Overlay should be visible now!")
        print(f"Overlay geometry: {overlay.geometry()}")
        print(f"Overlay alpha: {overlay.attributes('-alpha')}")
        print(f"Overlay state: {overlay.state()}")
    
    # Show overlay after 1 second
    root.after(1000, show_test_overlay)
    
    # Auto-close after 15 seconds
    root.after(15000, root.quit)
    
    print("Starting test... Overlay should appear in 1 second and stay for 15 seconds")
    root.mainloop()
    
    print("Test completed")

if __name__ == "__main__":
    test_simple_overlay()