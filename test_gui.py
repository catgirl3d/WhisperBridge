#!/usr/bin/env python3
"""
Simple test script for WhisperBridge GUI components.

This script tests imports and basic class instantiation without creating GUI windows.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """Test that all GUI modules can be imported."""
    print("Testing imports...")

    try:
        # Test basic imports
        from whisperbridge.ui.main_window import MainWindow
        from whisperbridge.ui.overlay_window import OverlayWindow
        from whisperbridge.ui.app import WhisperBridgeApp
        from whisperbridge.ui.components.language_selector import LanguageSelector
        from whisperbridge.ui.components.hotkey_input import HotkeyInput
        from whisperbridge.ui.components.prompt_editor import PromptEditor

        print("✓ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

def test_class_instantiation():
    """Test that classes can be instantiated (without GUI)."""
    print("Testing class instantiation...")

    try:
        from whisperbridge.ui.app import WhisperBridgeApp
        from whisperbridge.ui.components.language_selector import LanguageSelector
        from whisperbridge.ui.components.hotkey_input import HotkeyInput
        from whisperbridge.ui.components.prompt_editor import PromptEditor

        # Test app class
        app = WhisperBridgeApp()
        assert hasattr(app, 'initialize'), "App missing initialize method"
        assert hasattr(app, 'run'), "App missing run method"
        assert hasattr(app, 'shutdown'), "App missing shutdown method"

        # Test component classes (just check they have expected methods)
        # We can't instantiate them without tkinter root, but we can check class attributes
        assert hasattr(LanguageSelector, 'LANGUAGES'), "LanguageSelector missing LANGUAGES"
        assert hasattr(HotkeyInput, 'MODIFIERS'), "HotkeyInput missing MODIFIERS"
        assert hasattr(PromptEditor, 'TEMPLATES'), "PromptEditor missing TEMPLATES"

        print("✓ Class instantiation test passed")
        return True
    except Exception as e:
        print(f"❌ Class instantiation failed: {e}")
        return False

def test_language_data():
    """Test language selector data."""
    print("Testing language data...")

    try:
        from whisperbridge.ui.components.language_selector import LanguageSelector

        languages = LanguageSelector.LANGUAGES
        assert isinstance(languages, dict), "Languages should be dict"
        assert "ru" in languages, "Russian should be available"
        assert "en" in languages, "English should be available"
        assert "auto" in languages, "Auto should be available"

        print("✓ Language data test passed")
        return True
    except Exception as e:
        print(f"❌ Language data test failed: {e}")
        return False

def test_hotkey_data():
    """Test hotkey input data."""
    print("Testing hotkey data...")

    try:
        from whisperbridge.ui.components.hotkey_input import HotkeyInput

        modifiers = HotkeyInput.MODIFIERS
        assert isinstance(modifiers, list), "Modifiers should be list"
        assert "ctrl" in modifiers, "Ctrl should be in modifiers"
        assert "shift" in modifiers, "Shift should be in modifiers"
        assert "alt" in modifiers, "Alt should be in modifiers"

        print("✓ Hotkey data test passed")
        return True
    except Exception as e:
        print(f"❌ Hotkey data test failed: {e}")
        return False

def test_prompt_data():
    """Test prompt editor data."""
    print("Testing prompt data...")

    try:
        from whisperbridge.ui.components.prompt_editor import PromptEditor

        templates = PromptEditor.TEMPLATES
        assert isinstance(templates, dict), "Templates should be dict"
        assert "default" in templates, "Default template should exist"
        assert "formal" in templates, "Formal template should exist"

        placeholders = PromptEditor.PLACEHOLDERS
        assert isinstance(placeholders, dict), "Placeholders should be dict"
        assert "{target_language}" in placeholders, "Target language placeholder should exist"

        print("✓ Prompt data test passed")
        return True
    except Exception as e:
        print(f"❌ Prompt data test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("Starting WhisperBridge GUI component tests...\n")

    tests = [
        test_imports,
        test_class_instantiation,
        test_language_data,
        test_hotkey_data,
        test_prompt_data
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")

    print(f"\n{'='*50}")
    print(f"Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All GUI component tests passed successfully!")
        return True
    else:
        print("❌ Some tests failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)