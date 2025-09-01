"""
Main application class for WhisperBridge GUI.

This module provides the core application class that manages the GUI lifecycle,
theme configuration, and coordination between different windows.
"""

import asyncio
import os
import tempfile
import time
import threading
import customtkinter as ctk
from typing import Optional
from loguru import logger
from .main_window import MainWindow
from ..core.config import settings
from ..services.tray_service import TrayService
from ..services.hotkey_service import HotkeyService
from ..services.overlay_service import init_overlay_service, get_overlay_service
from ..core.keyboard_manager import KeyboardManager
from ..services.ocr_service import get_ocr_service, OCRRequest
from ..services.translation_service import get_translation_service
from ..core.api_manager import init_api_manager


class WhisperBridgeApp:
    """Main application class for WhisperBridge."""

    def __init__(self):
        """Initialize the WhisperBridge application."""
        # Initialize CustomTkinter
        ctk.set_appearance_mode(self._get_appearance_mode())
        ctk.set_default_color_theme("blue")

        # Create main window (hidden initially)
        self.root = ctk.CTk()
        self.root.title("WhisperBridge")
        self.root.geometry("1x1+0+0")  # Minimal size, positioned off-screen
        self.root.withdraw()  # Hide the main window

        # Window instances
        self.main_window: Optional[MainWindow] = None

        # Services
        self.tray_service: Optional[TrayService] = None
        self.hotkey_service: Optional[HotkeyService] = None
        self.keyboard_manager: Optional[KeyboardManager] = None
        self.overlay_service = None

        # Application state
        self.is_running = False
        self.minimize_to_tray = True  # Whether to minimize to tray on close
        self.shutdown_requested = threading.Event()

    def _get_appearance_mode(self) -> str:
        """Get appearance mode from settings.

        Returns:
            str: Appearance mode ('dark', 'light', or 'system')
        """
        theme_map = {
            "dark": "dark",
            "light": "light",
            "auto": "system"
        }
        return theme_map.get(settings.theme.lower(), "dark")

    def initialize(self):
        """Initialize application components."""
        try:
            # Configure root window
            self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

            # Set window icon if available
            # self.root.iconbitmap("path/to/icon.ico")  # TODO: Add icon

            # Initialize windows
            self._create_main_window()
            self._initialize_overlay_service()

            # Initialize keyboard manager and hotkey service
            self._create_keyboard_services()

            # Initialize system tray
            self._create_tray_service()

            # Bind global events
            self._bind_global_events()

            # Initialize OCR service
            self._initialize_ocr_service()

            # Initialize API manager and translation service
            self._initialize_translation_service()

            self.is_running = True
            print("WhisperBridge GUI initialized successfully")

            # Show test overlay immediately after initialization
            self._show_test_overlay_on_startup()

        except Exception as e:
            print(f"Failed to initialize GUI: {e}")
            raise

    def _create_main_window(self):
        """Create the main settings window."""
        self.main_window = MainWindow(on_save_callback=self._on_settings_saved)

    def _initialize_overlay_service(self):
        """Initialize the overlay service."""
        try:
            self.overlay_service = init_overlay_service(self.root)
            print("Overlay service initialized successfully")
        except Exception as e:
            print(f"Failed to initialize overlay service: {e}")
            self.overlay_service = None

    def _create_keyboard_services(self):
        """Create and initialize keyboard services."""
        try:
            # Create keyboard manager
            self.keyboard_manager = KeyboardManager()

            # Create hotkey service
            self.hotkey_service = HotkeyService(self.keyboard_manager)

            # Register default hotkeys
            self._register_default_hotkeys()

            # Start hotkey service
            if not self.hotkey_service.start():
                print("Warning: Failed to start hotkey service")
                self.hotkey_service = None
            else:
                print("Hotkey service started successfully")

        except Exception as e:
            print(f"Failed to create keyboard services: {e}")
            self.keyboard_manager = None
            self.hotkey_service = None

    def _create_tray_service(self):
        """Create and initialize the system tray service."""
        try:
            self.tray_service = TrayService(self)
            if not self.tray_service.initialize():
                print("Warning: Failed to initialize system tray")
        except Exception as e:
            print(f"Failed to create tray service: {e}")
            self.tray_service = None

    def _register_default_hotkeys(self):
        """Register default hotkeys for the application."""
        if not self.keyboard_manager:
            return

        try:
            # Register main translation hotkey
            self.keyboard_manager.register_hotkey(
                settings.translate_hotkey,
                self._on_translate_hotkey,
                "Main translation hotkey"
            )

            # Register quick translate hotkey if different
            if settings.quick_translate_hotkey != settings.translate_hotkey:
                self.keyboard_manager.register_hotkey(
                    settings.quick_translate_hotkey,
                    self._on_quick_translate_hotkey,
                    "Quick translation hotkey"
                )

            # Register activation hotkey if different
            if (settings.activation_hotkey != settings.translate_hotkey and
                settings.activation_hotkey != settings.quick_translate_hotkey):
                self.keyboard_manager.register_hotkey(
                    settings.activation_hotkey,
                    self._on_activation_hotkey,
                    "Application activation hotkey"
                )

            print(f"Registered hotkeys: {settings.translate_hotkey}, {settings.quick_translate_hotkey}, {settings.activation_hotkey}")

        except Exception as e:
            print(f"Failed to register default hotkeys: {e}")

    def _bind_global_events(self):
        """Bind global application events."""
        # Handle theme changes
        self.root.bind("<F12>", self._on_f12_pressed)

    def _initialize_ocr_service(self):
        """Initialize OCR service in the background."""
        logger.info("Starting OCR service initialization in app")
        try:
            ocr_service = get_ocr_service()
            logger.debug(f"OCR service instance: {ocr_service}")
            # Start background initialization and provide a callback
            ocr_service.start_background_initialization(
                on_complete=self._on_ocr_service_ready
            )
            # Update tray icon to show loading state
            self.update_tray_status(is_loading=True)
            logger.info("OCR service background initialization started successfully")
        except Exception as e:
            logger.error(f"Failed to start OCR service initialization: {e}")
            logger.debug(f"Initialization error details: {type(e).__name__}: {str(e)}", exc_info=True)
            self.update_tray_status(has_error=True)

    def _on_ocr_service_ready(self):
        """Callback for when OCR service is ready."""
        logger.info("OCR service initialization completed - service is now ready")
        ocr_service = get_ocr_service()
        logger.debug(f"OCR service status: initialized={ocr_service.is_initialized}")

        # Update tray icon to show normal state
        self.update_tray_status(is_loading=False)
        logger.debug("Tray status updated to normal (loading=False)")

        self.show_tray_notification(
            "WhisperBridge",
            "OCR service is ready."
        )
        logger.info("User notification shown: OCR service ready")

    def _initialize_translation_service(self):
        """Initialize translation service."""
        try:
            # Initialize API manager
            api_manager = init_api_manager()
            print("API manager initialized successfully")

            # Initialize translation service
            translation_service = get_translation_service()
            if not translation_service.initialize():
                print("Warning: Failed to initialize translation service")
            else:
                print("Translation service initialized successfully")

        except Exception as e:
            print(f"Warning: Failed to initialize translation service: {e}")

    def _show_test_overlay_on_startup(self):
        """Show test overlay immediately after app initialization."""
        try:
            print("Showing test overlay on startup...")
            test_original = "WhisperBridge загружен успешно!\nЭто тестовый текст для проверки оверлея."
            test_translated = "WhisperBridge loaded successfully!\nThis is test text for overlay verification.\n\nTranslation: DISABLED (as requested)"

            # Show overlay with test content
            self.show_overlay_window(
                original_text=test_original,
                translated_text=test_translated,
                position=(100, 100),  # Position near top-left corner
                overlay_id="startup_test"
            )
            print("Test overlay displayed successfully")

        except Exception as e:
            print(f"Failed to show test overlay on startup: {e}")

    def _on_settings_saved(self):
        """Handle settings saved event."""
        print("Settings saved, updating application...")

        # Update theme if changed
        current_mode = ctk.get_appearance_mode()
        new_mode = self._get_appearance_mode()

        if current_mode.lower() != new_mode.lower():
            ctk.set_appearance_mode(new_mode)
            print(f"Theme changed to: {new_mode}")

        # Update overlay service timeout
        if self.overlay_service:
            self.overlay_service.overlay_timeout = settings.overlay_timeout

        # Update hotkeys if changed
        self._update_hotkeys()

    def _on_f12_pressed(self, event):
        """Handle F12 key press for theme toggle."""
        self._toggle_theme()

    def _toggle_theme(self):
        """Toggle between light and dark themes."""
        current_mode = ctk.get_appearance_mode().lower()
        new_mode = "light" if current_mode == "dark" else "dark"

        ctk.set_appearance_mode(new_mode)
        print(f"Theme toggled to: {new_mode}")

    def _on_translate_hotkey(self):
        """Handle main translation hotkey press."""
        logger.info("Main translation hotkey pressed")
        logger.debug(f"Hotkey: {settings.translate_hotkey}")

        # Check OCR service readiness
        ocr_service = get_ocr_service()
        logger.debug(f"OCR service initialized: {ocr_service.is_initialized}, initializing: {ocr_service.is_initializing}")

        # Run the capture and processing in a separate thread to avoid blocking the UI
        thread = threading.Thread(target=self._capture_and_process)
        thread.daemon = True
        thread.start()

    def _capture_and_process(self):
        """Capture screen area and process it."""
        self.update_tray_status(is_active=True)

        from ..services.screen_capture_service import capture_area_interactive, CaptureResult, CaptureOptions

        # Create a temporary file path
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"whisperbridge_capture_{int(time.time())}.png")

        capture_options = CaptureOptions(
            save_to_file=True,
            output_path=temp_path,
            format="PNG"
        )

        def on_capture_complete(result: CaptureResult):
            try:
                if not result.success or not result.image:
                    self._show_capture_error(result.error_message or "Capture failed or was cancelled.")
                    return

                logger.info(f"Image captured and saved to: {result.file_path}")

                # Now, process the OCR and translation
                self._process_ocr_and_translate(result)

            finally:
                self.update_tray_status(is_active=False)
        
        capture_area_interactive(on_capture_complete, options=capture_options)

    def _process_ocr_and_translate(self, capture_result: "CaptureResult"):
        """Process OCR and translation."""
        logger.info("Starting OCR and translation processing")
        logger.debug(f"Capture result: success={capture_result.success}, image_size={capture_result.image.size if capture_result.image else None}")

        try:
            ocr_service = get_ocr_service()
            if not ocr_service.is_initialized:
                logger.warning("OCR service not ready for processing")
                self.root.after(0, self._show_ocr_error, "OCR service not ready.")
                return

            logger.debug("OCR service is ready, creating OCR request")
            ocr_request = OCRRequest(
                image=capture_result.image,
                languages=settings.ocr_languages,
                preprocess=True,
                use_cache=True
            )
            logger.debug(f"OCR request: languages={ocr_request.languages}, preprocess={ocr_request.preprocess}")

            ocr_response = ocr_service.process_image(ocr_request)
            logger.info(f"OCR processing result: success={ocr_response.success}, confidence={ocr_response.confidence:.3f}, text_length={len(ocr_response.text)}")
            logger.debug(f"OCR raw text: '{ocr_response.text}'")

            # if not ocr_response.success or not ocr_response.text.strip():
            #     logger.warning(f"OCR failed: success={ocr_response.success}, has_text={bool(ocr_response.text.strip())}, error={ocr_response.error_message}")
            #     self.root.after(0, self._show_ocr_error, ocr_response.error_message or "No text recognized.")
            #     return

            logger.info("OCR successful, showing overlay with OCR text only (translation disabled)")
            # Show overlay with OCR text only, no translation
            self.root.after(0, self.show_overlay_window,
                ocr_response.text,
                f"OCR Result (Translation disabled)\n"
                f"Confidence: {ocr_response.confidence:.1%}\n"
                f"Engine: {ocr_response.engine_used.value}"
            )

        except Exception as e:
            logger.error(f"Error in processing: {e}", exc_info=True)
            logger.debug(f"Processing error details: {type(e).__name__}: {str(e)}", exc_info=True)
            self.root.after(0, self._show_ocr_error, f"An unexpected error occurred: {e}")

    async def _handle_capture_result(self, result):
        """Handle the result of screen capture.
        Args:
            result: Capture result from screen capture service
        """
        try:
            if not result.success:
                self._show_capture_error(f"Screen capture failed: {result.error_message}")
                return

            if result.image is None:
                return

            # Process captured image with OCR
            ocr_service = get_ocr_service()
            ocr_request = OCRRequest(
                image=result.image,
                languages=settings.ocr_languages,
                preprocess=True,
                use_cache=True
            )

            await self._process_ocr_async(ocr_request, result)

        except Exception as e:
            self._show_ocr_error(f"Failed to handle capture result: {e}")
        finally:
            # Reset tray status after processing
            self.update_tray_status(is_active=False)

    def _show_capture_error(self, message: str):
        """Show capture error notification.

        Args:
            message: Error message to display
        """
        print(f"Capture error: {message}")
        if self.tray_service:
            self.tray_service.show_notification(
                "WhisperBridge",
                f"Capture Error: {message}"
            )

    async def _process_ocr_async(self, ocr_request, capture_result):
        """Asynchronously process OCR request.

        Args:
            ocr_request: OCR processing request
            capture_result: Screen capture result
        """
        try:
            print("Starting OCR processing...")

            # Get OCR service and process
            ocr_service = get_ocr_service()
            ocr_response = await ocr_service.process_image_async(ocr_request)

            # Handle OCR result
            await self._handle_ocr_result(ocr_response, capture_result)

        except Exception as e:
            print(f"Error in OCR processing: {e}")
            self._show_ocr_error(f"OCR processing failed: {e}")

    async def _handle_ocr_result(self, ocr_response, capture_result):
        """Handle OCR processing result.

        Args:
            ocr_response: OCR processing response
            capture_result: Original capture result
        """
        try:
            if ocr_response.success and ocr_response.text.strip():
                print(f"OCR successful: confidence={ocr_response.confidence:.2f}, "
                      f"engine={ocr_response.engine_used.value}, "
                      f"time={ocr_response.processing_time:.2f}s")

                # Show success notification
                if self.tray_service:
                    self.tray_service.show_notification(
                        "WhisperBridge",
                        f"Text recognized ({ocr_response.confidence:.1%} confidence)"
                    )

                # Show overlay with recognized text (translation disabled)
                self.show_overlay_window(
                    ocr_response.text,
                    f"OCR Result (Translation disabled)\n"
                    f"Confidence: {ocr_response.confidence:.1%}\n"
                    f"Engine: {ocr_response.engine_used.value}\n"
                    f"Time: {ocr_response.processing_time:.2f}s"
                )

                # Translation disabled - skip translation processing
                logger.info("Translation processing skipped (temporarily disabled)")

            else:
                print(f"OCR failed: {ocr_response.error_message}")
                self._show_ocr_error(
                    f"OCR failed: {ocr_response.error_message or 'No text recognized'}"
                )

                # Show overlay with error info
                self.show_overlay_window(
                    "OCR Failed",
                    f"Error: {ocr_response.error_message or 'No text recognized'}\n"
                    f"Engine: {ocr_response.engine_used.value}\n"
                    f"Time: {ocr_response.processing_time:.2f}s"
                )

        except Exception as e:
            print(f"Error handling OCR result: {e}")
            self._show_ocr_error("Failed to process OCR result")

    async def _process_translation_async(self, recognized_text: str, capture_result):
        """Asynchronously process translation of recognized text."""
        try:
            print("Starting translation processing...")

            # Get translation service
            translation_service = get_translation_service()

            # Translate the text
            translation_response = await translation_service.translate_text_async(
                text=recognized_text,
                source_lang=settings.source_language,
                target_lang=settings.target_language,
                use_cache=True
            )

            # Handle translation result
            await self._handle_translation_result(translation_response, recognized_text, capture_result)

        except Exception as e:
            print(f"Error in translation processing: {e}")
            self._show_translation_error(f"Translation failed: {e}")

    async def _handle_translation_result(self, translation_response, original_text: str, capture_result):
        """Handle translation processing result."""
        try:
            if translation_response.success:
                print(f"Translation successful: {len(translation_response.translated_text)} chars")

                # Show success notification
                if self.tray_service:
                    self.tray_service.show_notification(
                        "WhisperBridge",
                        f"Translation completed ({translation_response.tokens_used} tokens)"
                    )

                # Update overlay with translation
                self.show_overlay_window(
                    original_text,
                    f"Translation: {translation_response.translated_text}\n"
                    f"Source: {translation_response.source_lang} → Target: {translation_response.target_lang}\n"
                    f"Model: {translation_response.model}"
                )

            else:
                print(f"Translation failed: {translation_response.error_message}")
                self._show_translation_error(
                    f"Translation failed: {translation_response.error_message}"
                )

                # Show overlay with error info
                self.show_overlay_window(
                    original_text,
                    f"Translation Failed\n"
                    f"Error: {translation_response.error_message}"
                )

        except Exception as e:
            print(f"Error handling translation result: {e}")
            self._show_translation_error("Failed to process translation result")

    def _show_translation_error(self, message: str):
        """Show translation error notification."""
        print(f"Translation error: {message}")
        if self.tray_service:
            self.tray_service.show_notification(
                "WhisperBridge",
                f"Translation Error: {message}"
            )

    def _show_ocr_error(self, message: str):
        """Show OCR error notification.

        Args:
            message: Error message to display
        """
        print(f"OCR error: {message}")
        if self.tray_service:
            self.tray_service.show_notification(
                "WhisperBridge",
                f"OCR Error: {message}"
            )

    def _on_quick_translate_hotkey(self):
        """Handle quick translation hotkey press."""
        logger.info("Quick translation hotkey pressed")
        logger.debug(f"Hotkey: {settings.quick_translate_hotkey}")
        # TODO: Implement quick translation (maybe from clipboard)
        if self.tray_service:
            self.tray_service.show_notification(
                "WhisperBridge",
                "Quick translation hotkey activated"
            )
            logger.debug("Tray notification shown for quick translation")

    def _on_activation_hotkey(self):
        """Handle application activation hotkey press."""
        logger.info("Application activation hotkey pressed")
        logger.debug(f"Hotkey: {settings.activation_hotkey}")
        self.show_main_window()
        if self.tray_service:
            self.tray_service.show_notification(
                "WhisperBridge",
                "Application activated"
            )
            logger.debug("Tray notification shown for application activation")

    def _update_hotkeys(self):
        """Update hotkeys when settings change."""
        if not self.keyboard_manager or not self.hotkey_service:
            return

        try:
            # Clear existing hotkeys
            self.keyboard_manager.clear_all_hotkeys()

            # Re-register hotkeys with new settings
            self._register_default_hotkeys()

            # Reload hotkey service
            if not self.hotkey_service.reload_hotkeys():
                print("Warning: Failed to reload hotkeys")

            print("Hotkeys updated successfully")

        except Exception as e:
            print(f"Failed to update hotkeys: {e}")

    def _on_window_close(self):
        """Handle main window close event."""
        if self.minimize_to_tray and self.tray_service and self.tray_service.is_running():
            # Minimize to tray instead of closing
            self.hide_main_window()
            if self.tray_service:
                self.tray_service.show_notification(
                    "WhisperBridge",
                    "Приложение свернуто в системный трей"
                )
        else:
            # Normal shutdown
            self.shutdown()

    def show_main_window(self):
        """Show the main settings window."""
        # Check if the root window is still valid (not destroyed)
        if not self.root or not self.root.winfo_exists():
            print("Cannot show main window: Tkinter application has been destroyed")
            return

        if self.main_window:
            try:
                if not self.main_window.winfo_exists():
                    # Recreate window if destroyed
                    self._create_main_window()

                self.main_window.deiconify()
                self.main_window.focus_force()
                self.main_window.lift()
            except Exception as e:
                print(f"Error showing main window: {e}")
                # Try to recreate the window if there was an error
                try:
                    self._create_main_window()
                    if self.main_window:
                        self.main_window.deiconify()
                        self.main_window.focus_force()
                        self.main_window.lift()
                except Exception as e2:
                    print(f"Failed to recreate main window: {e2}")

    def show_overlay_window(self, original_text: str, translated_text: str,
                            position: Optional[tuple] = None, overlay_id: str = "main"):
        """Show the overlay window with translation results.

        Args:
            original_text: Original text to display
            translated_text: Translated text to display
            position: (x, y) coordinates for window positioning
            overlay_id: Unique identifier for the overlay
        """
        logger.debug("Executing show_overlay_window on main thread.")
        logger.debug(f"Attempting to show overlay '{overlay_id}' with position: {position}")

        if not self.overlay_service:
            logger.error("Overlay service is not available. Cannot show overlay.")
            return

        try:
            logger.info(f"Calling overlay_service.show_overlay for '{overlay_id}'")
            success = self.overlay_service.show_overlay(
                overlay_id,
                original_text,
                translated_text,
                position,
                show_loading_first=False  # Assuming direct show
            )
            logger.info(f"overlay_service.show_overlay returned: {success}")

            if success:
                # Schedule multiple verification steps at different intervals
                # to catch transient visibility issues
                self.root.after(100, lambda: self._verify_overlay_visibility(overlay_id, "initial"))
                self.root.after(500, lambda: self._verify_overlay_visibility(overlay_id, "medium"))
                self.root.after(1000, lambda: self._verify_overlay_visibility(overlay_id, "final"))
            else:
                logger.error(f"Failed to show overlay '{overlay_id}' via service.")

        except Exception as e:
            logger.error(f"An exception occurred in show_overlay_window: {e}", exc_info=True)

    def hide_overlay_window(self, overlay_id: str = "main"):
        """Hide the overlay window.

        Args:
            overlay_id: Overlay identifier to hide
        """
        if self.overlay_service:
            self.overlay_service.hide_overlay(overlay_id)

    def update_theme(self, theme: str):
        """Update application theme.

        Args:
            theme: New theme ('dark', 'light', or 'system')
        """
        theme_map = {
            "dark": "dark",
            "light": "light",
            "auto": "system"
        }

        mode = theme_map.get(theme.lower(), "dark")
        ctk.set_appearance_mode(mode)

        # Update settings
        settings.theme = theme

        print(f"Application theme updated to: {mode}")

    def update_window_opacity(self, opacity: float):
        """Update window opacity for all windows.

        Args:
            opacity: Opacity value between 0.0 and 1.0
        """
        opacity = max(0.1, min(1.0, opacity))  # Clamp between 0.1 and 1.0

        # Check if the root window is still valid (not destroyed)
        if not self.root or not self.root.winfo_exists():
            print("Cannot update window opacity: Tkinter application has been destroyed")
            return

        try:
            if self.main_window and self.main_window.winfo_exists():
                self.main_window.attributes("-alpha", opacity)
        except Exception as e:
            print(f"Error updating main window opacity: {e}")

        # Update opacity for all active overlays
        if self.overlay_service:
            try:
                active_overlays = self.overlay_service.get_active_overlays()
                for overlay_id in active_overlays:
                    overlay = self.overlay_service.get_overlay(overlay_id)
                    if overlay:
                        try:
                            if overlay.winfo_exists():
                                overlay.attributes("-alpha", opacity)
                        except Exception as e:
                            print(f"Error updating overlay {overlay_id} opacity: {e}")
            except Exception as e:
                print(f"Error updating overlay opacities: {e}")

        print(f"Window opacity updated to: {opacity}")

    def run(self):
        """Run the application main loop."""
        if not self.is_running:
            self.initialize()

        try:
            print("Starting WhisperBridge GUI main loop...")
            self.root.mainloop()
        except KeyboardInterrupt:
            print("Application interrupted by user")
        except Exception as e:
            print(f"Application error: {e}")
        finally:
            self.shutdown()

    def shutdown(self):
        """Shutdown the application gracefully."""
        if self.shutdown_requested.is_set():
            return
        self.shutdown_requested.set()

        print("Shutting down WhisperBridge GUI...")

        self.is_running = False

        # Shutdown hotkey service first
        if self.hotkey_service:
            self.hotkey_service.stop()
            self.hotkey_service = None

        # Shutdown tray service
        if self.tray_service:
            self.tray_service.shutdown()
            self.tray_service = None

        # Shutdown OCR service
        try:
            from ..services.ocr_service import get_ocr_service
            ocr_service = get_ocr_service()
            ocr_service.shutdown()
        except Exception as e:
            print(f"Warning: Error shutting down OCR service: {e}")

        # Shutdown translation service
        try:
            from ..services.translation_service import get_translation_service
            translation_service = get_translation_service()
            translation_service.shutdown()
        except Exception as e:
            print(f"Warning: Error shutting down translation service: {e}")

        # Shutdown API manager
        try:
            from ..core.api_manager import get_api_manager
            api_manager = get_api_manager()
            api_manager.shutdown()
        except Exception as e:
            print(f"Warning: Error shutting down API manager: {e}")

        # Stop overlay service
        if self.overlay_service:
            self.overlay_service.stop()
            self.overlay_service = None

        # Close main window
        try:
            if self.main_window:
                if self.main_window.winfo_exists():
                    self.main_window.destroy()
                else:
                    print("Main window already destroyed, skipping destruction")
        except Exception as e:
            print(f"Warning: Error destroying main window: {e}")

        # Destroy root window
        if self.root:
            try:
                if self.root.winfo_exists():
                    self.root.quit()
                    self.root.destroy()
            except Exception as e:
                logger.warning(f"Error during root window destruction: {e}")

        print("WhisperBridge GUI shutdown complete")

    def is_app_running(self) -> bool:
        """Check if the application is running.

        Returns:
            bool: True if application is running
        """
        if not self.is_running:
            return False

        try:
            return self.root and self.root.winfo_exists()
        except Exception:
            # If winfo_exists fails, the application has been destroyed
            return False

    def show_tray_notification(self, title: str, message: str):
        """Show a notification through the system tray.

        Args:
            title: Notification title
            message: Notification message
        """
        if self.tray_service:
            self.tray_service.show_notification(title, message)

    def update_tray_status(self, is_active: bool = False, has_error: bool = False, is_loading: bool = False):
        """Update the tray icon status.

        Args:
            is_active: Whether the app is actively processing
            has_error: Whether there's an error state
            is_loading: Whether the app is loading resources
        """
        if self.tray_service:
            self.tray_service.update_status_icon(is_active, has_error, is_loading)

    def hide_main_window(self):
        """Hide the main window (minimize to tray)."""
        # Check if the root window is still valid (not destroyed)
        if not self.root or not self.root.winfo_exists():
            print("Cannot hide main window: Tkinter application has been destroyed")
            return

        if self.main_window:
            try:
                if self.main_window.winfo_exists():
                    self.main_window.withdraw()
                    print("Main window hidden (minimized to tray)")
            except Exception as e:
                print(f"Error hiding main window: {e}")

    def toggle_minimize_to_tray(self, enabled: bool):
        """Toggle minimize to tray behavior.
        Args:
            enabled: Whether to minimize to tray on close
        """
        self.minimize_to_tray = enabled
        logger.info(f"Minimize to tray behavior set to: {enabled}")

    def _verify_overlay_visibility(self, overlay_id: str, check_stage: str):
        """Verify and log the state of the overlay window at different stages after showing it.
        
        Args:
            overlay_id: The ID of the overlay to verify
            check_stage: The verification stage (initial, medium, final)
        """
        logger.info(f"=== VERIFYING OVERLAY '{overlay_id}' VISIBILITY ({check_stage} check) ===")
        
        # Check if the service is available
        if not self.overlay_service:
            logger.error(f"[{check_stage}] Verification failed: Overlay service is gone.")
            return

        # Get the overlay window
        overlay = self.overlay_service.get_overlay(overlay_id)
        if not overlay:
            logger.error(f"[{check_stage}] Verification failed: Overlay '{overlay_id}' not found in service.")
            return

        try:
            # Check if window exists
            if not overlay.winfo_exists():
                logger.error(f"[{check_stage}] Verification failed: Overlay '{overlay_id}' window does not exist.")
                return

            # Gather detailed window state information
            is_visible = overlay.winfo_viewable()
            is_mapped = overlay.winfo_ismapped()
            state = overlay.state()
            geometry = overlay.geometry()
            alpha = overlay.attributes('-alpha')
            topmost = overlay.attributes('-topmost')
            
            # Get window coordinates and sizes
            try:
                x = overlay.winfo_x()
                y = overlay.winfo_y()
                width = overlay.winfo_width()
                height = overlay.winfo_height()
                rootx = overlay.winfo_rootx()
                rooty = overlay.winfo_rooty()
                screen_width = overlay.winfo_screenwidth()
                screen_height = overlay.winfo_screenheight()
                coord_info = f"x={x}, y={y}, width={width}, height={height}, rootx={rootx}, rooty={rooty}"
                screen_info = f"screen={screen_width}x{screen_height}"
            except Exception as e:
                coord_info = f"Error getting coordinates: {e}"
                screen_info = "Unknown"

            # Check for window manager issues
            wm_info = {}
            try:
                wm_info = {
                    "wm_state": overlay.wm_state() if hasattr(overlay, 'wm_state') else "N/A",
                    "override_redirect": overlay.winfo_toplevel().wm_overrideredirect() if hasattr(overlay, 'winfo_toplevel') else "N/A"
                }
            except Exception as e:
                wm_info = {"error": f"Failed to get WM info: {e}"}
            
            # Check Z-order
            z_order_info = "Unknown"
            try:
                if overlay.winfo_exists():
                    # Force the window to the top again, just for verification
                    overlay.lift()
                    overlay.attributes("-topmost", True)
                    z_order_info = "Forced to top (lift + topmost)"
            except Exception as e:
                z_order_info = f"Error checking Z-order: {e}"

            # Check parent window state
            parent_info = {}
            try:
                if overlay.master and overlay.master.winfo_exists():
                    parent_info = {
                        "exists": overlay.master.winfo_exists(),
                        "viewable": overlay.master.winfo_viewable(),
                        "mapped": overlay.master.winfo_ismapped(),
                        "state": overlay.master.state() if hasattr(overlay.master, 'state') else "N/A"
                    }
                else:
                    parent_info = {"exists": False, "error": "Parent window does not exist"}
            except Exception as e:
                parent_info = {"error": f"Failed to get parent info: {e}"}

            # Log detailed visibility report
            logger.info(f"=== OVERLAY '{overlay_id}' VISIBILITY REPORT ({check_stage}) ===")
            logger.info(f"  - Is Viewable: {is_visible}")
            logger.info(f"  - Is Mapped: {is_mapped}")
            logger.info(f"  - State: {state}")
            logger.info(f"  - Geometry: {geometry}")
            logger.info(f"  - Coordinates: {coord_info}")
            logger.info(f"  - Screen: {screen_info}")
            logger.info(f"  - Alpha (Opacity): {alpha}")
            logger.info(f"  - Topmost: {topmost}")
            logger.info(f"  - Z-Order: {z_order_info}")
            logger.info(f"  - Window Manager: {wm_info}")
            logger.info(f"  - Parent Window: {parent_info}")
            
            # Log overall visibility status
            visibility_status = "VISIBLE" if is_visible and is_mapped and state != "withdrawn" else "NOT VISIBLE"
            logger.info(f"  - VISIBILITY STATUS: {visibility_status}")
            
            # Additional checks based on verification stage
            if check_stage == "medium" or check_stage == "final":
                # For medium and final checks, try to force visibility again if not visible
                if not is_visible or not is_mapped or state == "withdrawn":
                    logger.warning(f"[{check_stage}] Overlay not fully visible, attempting to force visibility...")
                    try:
                        # Attempt to bring window back to visibility
                        overlay.deiconify()
                        overlay.lift()
                        overlay.attributes("-topmost", True)
                        overlay.focus_force()
                        overlay.update_idletasks()
                        
                        # Log forced visibility attempt
                        logger.info(f"[{check_stage}] Forced visibility attempt made for '{overlay_id}'")
                    except Exception as e:
                        logger.error(f"[{check_stage}] Error forcing visibility: {e}")
            
            logger.info("=" * 50)

        except Exception as e:
            logger.error(f"Error during overlay verification ({check_stage}) for '{overlay_id}': {e}", exc_info=True)


# Global application instance
_app_instance: Optional[WhisperBridgeApp] = None


def get_app() -> WhisperBridgeApp:
    """Get the global application instance.
    Returns:
        WhisperBridgeApp: Global application instance
    """
    global _app_instance
    if _app_instance is None:
        _app_instance = WhisperBridgeApp()
    return _app_instance


def init_app() -> WhisperBridgeApp:
    """Initialize and return the application instance.

    Returns:
        WhisperBridgeApp: Initialized application instance
    """
    app = get_app()
    if not app.is_running:
        app.initialize()
    return app


if __name__ == "__main__":
    # For testing the application independently
    app = init_app()
    app.show_main_window()
    app.run()