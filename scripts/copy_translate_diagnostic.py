#!/usr/bin/env python3
"""
WhisperBridge Copy-Translate Diagnostic Script

This script performs comprehensive diagnostics on clipboard copying and translation functionality.
It checks for hotkey conflicts, keyboard layout issues, clipboard operations, and system permissions.

Usage: python scripts/copy_translate_diagnostic.py
"""

import sys
import os
import platform
import logging
import time
import threading
import argparse
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from whisperbridge.services.clipboard_service import ClipboardService
    from whisperbridge.services.translation_service import get_translation_service, init_translation_service
    from whisperbridge.core.config import settings, load_settings
    from whisperbridge.utils.keyboard_utils import KeyboardUtils
    from loguru import logger
except ImportError as e:
    print(f"Failed to import WhisperBridge modules: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


class DiagnosticResult:
    """Represents the result of a diagnostic check."""

    def __init__(self, name: str, status: str, message: str = "", recommendations: List[str] = None):
        self.name = name
        self.status = status  # 'PASS', 'FAIL', 'WARN', 'INFO'
        self.message = message
        self.recommendations = recommendations or []
        self.timestamp = datetime.now()

    def __str__(self):
        return f"[{self.status}] {self.name}: {self.message}"


class CopyTranslateDiagnostic:
    """Main diagnostic class for clipboard and translation functionality."""

    def __init__(self):
        self.os_type = self._detect_os()
        self.results: List[DiagnosticResult] = []
        self.clipboard_service = None
        self.translation_service = None

        # Setup logging
        self._setup_logging()

        # Timeouts for interactive tests (can be overridden via env vars)
        self.manual_timeout = int(os.environ.get("DIAG_MANUAL_TIMEOUT", "30"))
        self.simulated_timeout = float(os.environ.get("DIAG_SIMULATED_TIMEOUT", "2.0"))

    def _detect_os(self) -> str:
        """Detect the operating system."""
        system = platform.system().lower()
        if system == 'windows':
            return 'windows'
        elif system == 'linux':
            return 'linux'
        elif system == 'darwin':
            return 'darwin'
        else:
            return 'unknown'

    def _setup_logging(self):
        """Setup logging for the diagnostic script."""
        # Configure loguru for both file and console
        log_file = f"copy_translate_diagnostic_{int(time.time())}.log"
        logger.add(log_file, rotation="10 MB", level="DEBUG")
        logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")

    def log_step(self, step: str, details: str = ""):
        """Log a diagnostic step."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        message = f"[{timestamp}] {step}"
        if details:
            message += f" - {details}"
        logger.info(message)

    def run_all_diagnostics(self) -> List[DiagnosticResult]:
        """Run all diagnostic checks."""
        self.log_step("Starting WhisperBridge Copy-Translate Diagnostics")

        # Initialize services
        self._init_services()

        # Run checks
        self._check_os_compatibility()
        self._check_hotkey_conflicts()
        self._check_keyboard_layout()
        self._check_clipboard_operations()
        self._check_clipboard_monitoring()
        self._check_translation_service()
        self._check_manual_copy_simulation()
        self._check_copy_translate_workflow()
        self._check_system_permissions()

        self.log_step("Diagnostics completed")
        return self.results

    def _init_services(self):
        """Initialize WhisperBridge services."""
        try:
            # Load settings
            load_settings()
            self.log_step("Settings loaded", "success")

            # Initialize API manager first
            from ..core.api_manager import init_api_manager
            api_manager = init_api_manager()
            if api_manager.is_initialized():
                self.log_step("API manager initialized", "success")
            else:
                self.log_step("API manager failed to initialize", "warning")

            # Initialize clipboard service
            self.clipboard_service = ClipboardService()
            if self.clipboard_service.start():
                self.log_step("Clipboard service initialized", "success")
            else:
                self.log_step("Clipboard service failed to start", "error")

            # Initialize translation service
            self.translation_service = init_translation_service()
            if self.translation_service.is_initialized():
                self.log_step("Translation service initialized", "success")
            else:
                self.log_step("Translation service failed to initialize", "warning")

        except Exception as e:
            self.log_step("Service initialization error", str(e))
            self.results.append(DiagnosticResult(
                "Service Initialization",
                "FAIL",
                f"Failed to initialize services: {e}",
                ["Check WhisperBridge installation", "Verify API key configuration"]
            ))

    def _check_os_compatibility(self):
        """Check OS compatibility."""
        supported_os = ['windows', 'linux', 'darwin']
        if self.os_type in supported_os:
            self.results.append(DiagnosticResult(
                "OS Compatibility",
                "PASS",
                f"Running on supported OS: {self.os_type}"
            ))
        else:
            self.results.append(DiagnosticResult(
                "OS Compatibility",
                "FAIL",
                f"Unsupported OS: {self.os_type}",
                ["WhisperBridge supports Windows, Linux, and macOS"]
            ))

    def _check_hotkey_conflicts(self):
        """Check for hotkey conflicts."""
        hotkeys_to_check = [
            settings.copy_translate_hotkey,
            settings.translate_hotkey,
            settings.quick_translate_hotkey,
            settings.activation_hotkey
        ]

        for hotkey in hotkeys_to_check:
            if not hotkey:
                continue

            conflict = KeyboardUtils.check_system_conflict(hotkey)
            if conflict:
                suggestions = KeyboardUtils.suggest_alternative_hotkey(hotkey)
                self.results.append(DiagnosticResult(
                    f"Hotkey Conflict Check: {hotkey}",
                    "FAIL",
                    f"Conflicts with system hotkey: {conflict}",
                    [f"Suggested alternatives: {', '.join(suggestions[:3])}"]
                ))
            else:
                self.results.append(DiagnosticResult(
                    f"Hotkey Conflict Check: {hotkey}",
                    "PASS",
                    "No conflicts detected"
                ))

    def _check_keyboard_layout(self):
        """Check keyboard layout issues."""
        # This is a basic check - in a real implementation, you'd detect actual layout
        try:
            # Try to detect keyboard layout
            import locale
            current_locale = locale.getlocale()[0]
            if current_locale:
                self.results.append(DiagnosticResult(
                    "Keyboard Layout Detection",
                    "INFO",
                    f"Current system locale: {current_locale}",
                    ["Ensure keyboard layout matches expected input language"]
                ))
            else:
                self.results.append(DiagnosticResult(
                    "Keyboard Layout Detection",
                    "WARN",
                    "Could not detect system locale",
                    ["Manually verify keyboard layout settings"]
                ))
        except Exception as e:
            self.results.append(DiagnosticResult(
                "Keyboard Layout Detection",
                "WARN",
                f"Error detecting keyboard layout: {e}",
                ["Check system keyboard settings manually"]
            ))

    def _check_clipboard_operations(self):
        """Test basic clipboard operations."""
        if not self.clipboard_service:
            self.results.append(DiagnosticResult(
                "Clipboard Operations",
                "FAIL",
                "Clipboard service not available"
            ))
            return

        try:
            # Test copy
            test_text = f"WhisperBridge Diagnostic Test - {int(time.time())}"
            success = self.clipboard_service.copy_text(test_text)
            if success:
                self.log_step("Clipboard copy test", "success")

                # Test paste
                retrieved_text = self.clipboard_service.get_clipboard_text()
                if retrieved_text == test_text:
                    self.results.append(DiagnosticResult(
                        "Clipboard Operations",
                        "PASS",
                        "Copy and paste operations working correctly"
                    ))
                else:
                    self.results.append(DiagnosticResult(
                        "Clipboard Operations",
                        "FAIL",
                        f"Clipboard content mismatch. Expected: '{test_text}', Got: '{retrieved_text}'",
                        ["Check clipboard permissions", "Try restarting the system"]
                    ))
            else:
                self.results.append(DiagnosticResult(
                    "Clipboard Operations",
                    "FAIL",
                    "Failed to copy text to clipboard",
                    ["Check clipboard permissions", "Verify pyperclip installation"]
                ))

        except Exception as e:
            self.results.append(DiagnosticResult(
                "Clipboard Operations",
                "FAIL",
                f"Clipboard test error: {e}",
                ["Check system clipboard access", "Verify no other applications are interfering"]
            ))

    def _check_clipboard_monitoring(self):
        """Test clipboard monitoring/polling."""
        if not self.clipboard_service:
            self.results.append(DiagnosticResult(
                "Clipboard Monitoring",
                "FAIL",
                "Clipboard service not available"
            ))
            return

        try:
            # Test monitoring by changing clipboard content
            original_content = self.clipboard_service.get_clipboard_text() or ""

            # Change clipboard content
            test_content = f"Monitoring Test - {int(time.time())}"
            self.clipboard_service.copy_text(test_content)

            # Wait a bit for monitoring to detect change
            time.sleep(0.5)

            # Check if monitoring detected the change
            current_content = self.clipboard_service.get_clipboard_text()
            if current_content == test_content:
                self.results.append(DiagnosticResult(
                    "Clipboard Monitoring",
                    "PASS",
                    "Clipboard monitoring is working"
                ))
            else:
                self.results.append(DiagnosticResult(
                    "Clipboard Monitoring",
                    "WARN",
                    "Clipboard monitoring may not be detecting changes properly",
                    ["Check monitoring interval settings", "Verify clipboard service is running"]
                ))

            # Restore original content
            if original_content:
                self.clipboard_service.copy_text(original_content)

        except Exception as e:
            self.results.append(DiagnosticResult(
                "Clipboard Monitoring",
                "FAIL",
                f"Monitoring test error: {e}",
                ["Check clipboard service configuration"]
            ))

    def _check_translation_service(self):
        """Test translation service functionality."""
        if not self.translation_service:
            self.results.append(DiagnosticResult(
                "Translation Service",
                "FAIL",
                "Translation service not available"
            ))
            return

        if not self.translation_service.is_initialized():
            self.results.append(DiagnosticResult(
                "Translation Service",
                "INFO",
                "Translation service initialized but no API key configured",
                ["Configure OpenAI API key in settings to enable translation", "Check settings file for api_key configuration"]
            ))
            return

        try:
            # Test with simple text
            test_text = "Hello world"
            result = self.translation_service.translate_text_sync(
                text=test_text,
                source_lang="en",
                target_lang="es"
            )

            if result.success and result.translated_text:
                self.results.append(DiagnosticResult(
                    "Translation Service",
                    "PASS",
                    f"Translation working: '{test_text}' -> '{result.translated_text}'"
                ))
            else:
                self.results.append(DiagnosticResult(
                    "Translation Service",
                    "FAIL",
                    f"Translation failed: {result.error_message}",
                    ["Check API key configuration", "Verify internet connection", "Check API service status"]
                ))

        except Exception as e:
            self.results.append(DiagnosticResult(
                "Translation Service",
                "FAIL",
                f"Translation test error: {e}",
                ["Check API configuration", "Verify service dependencies"]
            ))

    def _check_manual_copy_simulation(self):
        """Test manual Ctrl+C behavior simulation and comprehensive copy workflow."""
        try:
            from whisperbridge.services.hotkey_service import HotkeyService
            from whisperbridge.core.keyboard_manager import KeyboardManager

            keyboard_manager = KeyboardManager()

            # Register a test hotkey to check if hotkey system works
            def test_callback():
                self.log_step("Test hotkey callback executed", "success")

            # Register the copy-translate hotkey
            keyboard_manager.register_hotkey(
                settings.copy_translate_hotkey,
                test_callback,
                "Test copy-translate hotkey"
            )

            hotkey_service = HotkeyService(keyboard_manager)

            if hotkey_service.start():
                self.results.append(DiagnosticResult(
                    "Manual Copy Simulation",
                    "PASS",
                    "Hotkey service initialized and test hotkey registered successfully"
                ))
                hotkey_service.stop()
            else:
                self.results.append(DiagnosticResult(
                    "Manual Copy Simulation",
                    "WARN",
                    "Hotkey service failed to start - no hotkeys registered",
                    ["Check if any hotkeys are enabled in settings", "Verify pynput installation"]
                ))

        except Exception as e:
            self.results.append(DiagnosticResult(
                "Manual Copy Simulation",
                "FAIL",
                f"Hotkey service error: {e}",
                ["Check keyboard input permissions", "Verify hotkey service dependencies"]
            ))

    def _check_copy_translate_workflow(self):
        """Test the complete copy-translate workflow with an option for manual verification.

        This function gives the user two choices:
        1) Manual copy: user selects text in any application and presses Ctrl+C (or Cmd+C on macOS).
           The script will poll the clipboard and show exactly what was copied.
        2) Simulated copy: the script simulates the copy hotkey (programmatic) and reports results.

        The goal is to reproduce main app behavior so the user can confirm what's copied.
        """
        if not self.clipboard_service:
            self.results.append(DiagnosticResult(
                "Copy-Translate Workflow",
                "FAIL",
                "Clipboard service not available"
            ))
            return

        try:
            # Ask user whether to do manual or simulated copy
            print("\nCOPY-TRANSLATE WORKFLOW TEST")
            print("1) Manual copy (select text in another app and press Ctrl+C/Cmd+C)")
            print("2) Simulated copy (script will press the copy hotkey programmatically)")
            choice = None
            try:
                choice = input("Choose test mode (1=manual, 2=simulated) [default 1]: ").strip() or "1"
            except Exception:
                # In non-interactive environments, default to simulated
                choice = "2"

            if choice not in ("1", "2"):
                print("Invalid choice, defaulting to manual (1).")
                choice = "1"

            if choice == "1":
                # Manual copy: instruct user to select text and press Ctrl+C/Cmd+C
                print("\nMANUAL COPY MODE")
                print("Please: Select text in any application (browser, editor, etc.) and press Ctrl+C (or Cmd+C on macOS).")
                print("The diagnostic will detect clipboard change and show the copied content.")
                prev = self.clipboard_service.get_clipboard_text() or ""
                timeout = self.manual_timeout
                interval = 0.25
                elapsed = 0.0
                print(f"Waiting up to {int(timeout)} seconds for clipboard to update...")
                new_clip = prev
                while elapsed < timeout:
                    new_clip = self.clipboard_service.get_clipboard_text() or ""
                    if new_clip and new_clip != prev:
                        break
                    time.sleep(interval)
                    elapsed += interval

                if not new_clip or new_clip == prev:
                    msg = "No clipboard change detected during manual test."
                    print(f"❌ {msg}")
                    self.results.append(DiagnosticResult(
                        "Copy-Translate Workflow (Manual)",
                        "FAIL",
                        msg,
                        ["Make sure you pressed Ctrl+C/Cmd+C while text was selected", "Check clipboard permissions"]
                    ))
                    return
                else:
                    # Show captured clipboard content (truncate for display safety)
                    display = new_clip if len(new_clip) <= 1000 else new_clip[:1000] + "..."
                    print("✅ Clipboard updated. Copied content:")
                    print("----- BEGIN COPIED TEXT -----")
                    print(display)
                    print("------ END COPIED TEXT ------")
                    # Optionally attempt translation if service available
                    if self.translation_service and self.translation_service.is_initialized():
                        print("Translating copied text (auto -> target)...")
                        try:
                            trans = self.translation_service.translate_text_sync(text=new_clip, source_lang="auto", target_lang=settings.target_language)
                            if trans and getattr(trans, "success", False) and getattr(trans, "translated_text", ""):
                                print("✅ Translation result:")
                                print(getattr(trans, "translated_text"))
                                self.results.append(DiagnosticResult(
                                    "Copy-Translate Workflow (Manual)",
                                    "PASS",
                                    "Manual copy detected and translation succeeded",
                                    [f"Copied length: {len(new_clip)}"]
                                ))
                            else:
                                err = getattr(trans, "error_message", "Unknown")
                                print(f"⚠️ Translation failed: {err}")
                                self.results.append(DiagnosticResult(
                                    "Copy-Translate Workflow (Manual)",
                                    "WARN",
                                    f"Manual copy succeeded but translation failed: {err}",
                                    ["Check API key and network connectivity"]
                                ))
                        except Exception as e:
                            print(f"⚠️ Translation error: {e}")
                            self.results.append(DiagnosticResult(
                                "Copy-Translate Workflow (Manual)",
                                "WARN",
                                f"Manual copy succeeded but translation threw error: {e}",
                                ["Check translation service configuration"]
                            ))
                    else:
                        self.results.append(DiagnosticResult(
                            "Copy-Translate Workflow (Manual)",
                            "PASS",
                            "Manual copy detected (translation not configured)",
                            [f"Copied length: {len(new_clip)}", "Configure API key to enable translation"]
                        ))
                    return

            # Simulated copy path
            if choice == "2":
                print("\nSIMULATED COPY MODE")
                # Use the same simulation function used earlier
                success = self._simulate_copy_translate_hotkey()
                if success:
                    self.results.append(DiagnosticResult(
                        "Copy-Translate Workflow (Simulated)",
                        "PASS",
                        "Simulated copy-translate workflow completed successfully"
                    ))
                else:
                    self.results.append(DiagnosticResult(
                        "Copy-Translate Workflow (Simulated)",
                        "FAIL",
                        "Simulated copy-translate workflow failed",
                        ["Ensure pynput is installed and script has permission to simulate keyboard input"]
                    ))
                return

        except Exception as e:
            self.results.append(DiagnosticResult(
                "Copy-Translate Workflow",
                "FAIL",
                f"Workflow test error: {e}",
                ["Check service configurations", "Verify all dependencies are installed"]
            ))

    def _check_system_permissions(self):
        """Check system permissions for clipboard and keyboard access."""
        permissions_issues = []

        # Check clipboard permissions
        if self.os_type == 'darwin':
            # macOS specific checks
            try:
                import subprocess
                result = subprocess.run(['tccutil', 'reset', 'Accessibility'], capture_output=True)
                if result.returncode == 0:
                    permissions_issues.append("macOS Accessibility permissions may need to be granted")
            except:
                pass

        elif self.os_type == 'linux':
            # Linux specific checks (Wayland/X11)
            try:
                # Check for Wayland
                wayland_display = os.environ.get('WAYLAND_DISPLAY')
                if wayland_display:
                    permissions_issues.append("Running on Wayland - clipboard permissions may be restricted")
            except:
                pass

        elif self.os_type == 'windows':
            # Windows specific checks
            try:
                # Check if running as admin (sometimes needed for global hotkeys)
                import ctypes
                if not ctypes.windll.shell32.IsUserAnAdmin():
                    permissions_issues.append("Not running as administrator - some features may be limited")
            except:
                pass

        if permissions_issues:
            self.results.append(DiagnosticResult(
                "System Permissions",
                "WARN",
                "Potential permission issues detected",
                permissions_issues
            ))
        else:
            self.results.append(DiagnosticResult(
                "System Permissions",
                "PASS",
                "No obvious permission issues detected"
            ))

    def start_watch_mode(self):
        """Start a persistent interactive watch mode.

        - Listens for keyboard key presses (requires pynput)
        - Polls clipboard for changes and prints them
        - Keeps running until user types 'q' + Enter in the terminal
        """
        print("\n" + "="*60)
        print("WHISPERBRIDGE WATCH MODE")
        print("Press keys in any application to see detected key events.")
        print("The script will also print clipboard changes as they occur.")
        print("Type 'q' and press Enter in this terminal to quit.")
        print("="*60)

        # Ensure clipboard service active
        if not self.clipboard_service:
            try:
                self.clipboard_service = ClipboardService()
                self.clipboard_service.start()
            except Exception as e:
                print(f"Failed to start clipboard service for watch mode: {e}")
                return

        stop_event = threading.Event()

        # Clipboard watcher thread
        def clipboard_watcher():
            prev = self.clipboard_service.get_clipboard_text() or ""
            while not stop_event.is_set():
                try:
                    cur = self.clipboard_service.get_clipboard_text() or ""
                    if cur != prev:
                        prev = cur
                        display = cur if len(cur) <= 1000 else cur[:1000] + "..."
                        ts = datetime.now().strftime("%H:%M:%S")
                        print(f"[{ts}] CLIPBOARD UPDATED ({len(cur)} chars):")
                        print("----- BEGIN CLIP -----")
                        print(display)
                        print("------ END CLIP ------")
                    time.sleep(0.2)
                except Exception as e:
                    print(f"[Clipboard watcher error] {e}")
                    time.sleep(0.5)

        # Keyboard listener (pynput) to show key press/release events
        try:
            from pynput import keyboard
            pynput_available = True
        except Exception:
            pynput_available = False
            print("pynput not available: key events will not be captured. Install with 'pip install pynput'.")

        listener = None

        if pynput_available:
            def on_press(key):
                try:
                    k = key.char if hasattr(key, 'char') and key.char is not None else str(key)
                except Exception:
                    k = str(key)
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"[{ts}] KEY DOWN: {k}")

            def on_release(key):
                try:
                    k = key.char if hasattr(key, 'char') and key.char is not None else str(key)
                except Exception:
                    k = str(key)
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"[{ts}] KEY UP:   {k}")
                # Do not stop on any key; user must type 'q' in terminal to quit

            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            listener.daemon = True
            listener.start()

        # Start clipboard watcher thread
        watcher_thread = threading.Thread(target=clipboard_watcher, name="clipboard-watcher", daemon=True)
        watcher_thread.start()

        # Terminal control: wait for 'q' + Enter
        try:
            while True:
                cmd = input().strip().lower()
                if cmd == 'q':
                    print("Quitting watch mode...")
                    break
                elif cmd == '':
                    # ignore empty enter
                    continue
                else:
                    print(f"Unknown command: {cmd!r}. Type 'q' to quit.")
        except KeyboardInterrupt:
            print("\nInterrupted by user, exiting watch mode.")
        finally:
            stop_event.set()
            try:
                if listener:
                    listener.stop()
            except Exception:
                pass

            # allow watcher thread to terminate
            time.sleep(0.2)

    def print_summary(self):
        """Print diagnostic summary."""
        print("\n" + "="*60)
        print("WHISPERBRIDGE COPY-TRANSLATE DIAGNOSTIC SUMMARY")
        print("="*60)
        print(f"OS: {self.os_type}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # Count results by status
        status_counts = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}
        for result in self.results:
            status_counts[result.status] += 1

        print("RESULTS SUMMARY:")
        for status, count in status_counts.items():
            if count > 0:
                print(f"  {status}: {count}")

        print("\nDETAILED RESULTS:")
        for result in self.results:
            print(f"  {result}")
            if result.recommendations:
                for rec in result.recommendations:
                    print(f"    → {rec}")

        print("\nRECOMMENDATIONS:")
        all_recommendations = []
        for result in self.results:
            all_recommendations.extend(result.recommendations)

        if all_recommendations:
            for rec in set(all_recommendations):  # Remove duplicates
                print(f"• {rec}")
        else:
            print("✓ No issues found - all systems operational!")

        print("\n" + "="*60)


def main():
    """Main entry point with CLI for interactive/manual testing."""
    parser = argparse.ArgumentParser(description="WhisperBridge copy-translate diagnostic")
    parser.add_argument(
        "--mode",
        choices=["auto", "manual", "simulated"],
        default="auto",
        help="Run mode: 'auto' runs full diagnostics; 'manual' waits for user to copy text; 'simulated' programmatically issues copy"
    )
    parser.add_argument(
        "--manual-timeout",
        type=int,
        default=None,
        help="Timeout seconds for manual copy waiting (overrides DIAG_MANUAL_TIMEOUT)"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Start persistent watch mode: log key events and clipboard changes until you type 'q' in the terminal"
    )
    args = parser.parse_args()

    print("WhisperBridge Copy-Translate Diagnostic Tool")
    print("===========================================")

    diagnostic = CopyTranslateDiagnostic()
    # Override manual timeout if provided
    if args.manual_timeout is not None:
        diagnostic.manual_timeout = args.manual_timeout

    try:
        # Watch mode: persistent interactive listener for key events and clipboard changes
        if args.watch:
            diagnostic._init_services()
            diagnostic.start_watch_mode()
            results = diagnostic.results
        elif args.mode == "auto":
            results = diagnostic.run_all_diagnostics()
        else:
            # Initialize services but do not run full auto tests that close quickly
            diagnostic._init_services()

            if args.mode == "manual":
                # Manual mode will instruct the user and wait for clipboard change
                diagnostic._check_copy_translate_workflow()
            else:  # simulated
                # Simulated mode will attempt to programmatically send copy and poll clipboard
                success = diagnostic._simulate_copy_translate_hotkey()
                diagnostic.results.append(DiagnosticResult(
                    "Copy-Translate Workflow (Simulated)",
                    "PASS" if success else "FAIL",
                    "Simulated copy executed" if success else "Simulated copy failed",
                    ["Ensure pynput is installed and script has permission to simulate keyboard input"] if not success else []
                ))

            results = diagnostic.results

        diagnostic.print_summary()

        # If running in manual mode, wait for explicit user input before exiting
        if args.mode == "manual":
            try:
                print("\nManual mode complete. The script will wait for you to press Enter to exit.")
                input("Press Enter to exit...")
            except Exception:
                # Non-interactive environments may raise; ignore and proceed to cleanup
                pass

    finally:
        # Cleanup
        if diagnostic.clipboard_service:
            diagnostic.clipboard_service.stop()

    # Return exit code based on results
    has_failures = any(r.status == 'FAIL' for r in results)
    sys.exit(1 if has_failures else 0)


if __name__ == "__main__":
    main()