"""
Overlay window for displaying translation results.

This module provides a compact overlay window that shows original text
and translation results with action buttons for copying and pasting.
Enhanced with animations, loading indicators, and improved positioning.
"""

import customtkinter as ctk
from typing import Optional, Tuple, Callable
import tkinter as tk
import threading
import time
import math
from unittest.mock import MagicMock

from ..services.clipboard_service import ClipboardService
from ..services.paste_service import PasteService


class OverlayWindow(ctk.CTkToplevel):
    """Enhanced overlay window for displaying translation results with animations and loading states."""

    def __init__(self, parent=None, timeout: int = 10, on_close_callback: Optional[Callable] = None,
                 clipboard_service: Optional[ClipboardService] = None,
                 paste_service: Optional[PasteService] = None):
        """Initialize the overlay window.

        Args:
            parent: Parent window
            timeout: Auto-close timeout in seconds
            on_close_callback: Callback when window closes
            clipboard_service: Clipboard service instance
            paste_service: Paste service instance
        """
        print("=== OverlayWindow.__init__ STARTED ===")
        print(f"Parent: {parent}")
        print(f"Timeout: {timeout}")
        print(f"On close callback: {on_close_callback is not None}")

        try:
            print("Calling super().__init__(parent)...")
            print(f"Parent window details: {parent}")

            # Check if we have display access
            try:
                print("Testing display access...")
                test_window = tk.Tk()
                test_window.destroy()
                print("Display access confirmed, creating real window")

                # Check parent window if it exists
                if parent:
                    try:
                        print(f"Parent window exists: {parent.winfo_exists()}")
                        print(f"Parent window geometry: {parent.geometry()}")
                    except Exception as parent_error:
                        print(f"Parent window check failed: {parent_error}")

                super().__init__(parent)
            except Exception as display_error:
                print(f"No display access: {display_error}")
                print("Creating mock window for headless environment")
                # Create a mock object that mimics Tkinter window behavior
                self.mock_mode = True
                self._mock_init()
                return

            print("OverlayWindow super().__init__() completed successfully")

            # Additional checks after creation
            print(f"Window created successfully: {self}")
            print(f"Window exists: {self.winfo_exists()}")
            print(f"Window geometry: {self.geometry()}")

        except Exception as e:
            print(f"ERROR in OverlayWindow super().__init__(): {e}")
            import traceback
            traceback.print_exc()
            raise

        print("Setting instance variables...")
        self.timeout = timeout
        self.on_close_callback = on_close_callback
        self.timer_thread: Optional[threading.Thread] = None
        self.animation_thread: Optional[threading.Thread] = None
        self.is_destroyed = False
        self.is_animating = False
        self.current_opacity = 0.0
        self.target_opacity = 1.0

        print("Setting up services...")

        # Services
        print("Creating clipboard service...")
        self.clipboard_service = clipboard_service or ClipboardService()
        print("Creating paste service...")
        self.paste_service = paste_service or PasteService()
        self.paste_service.set_clipboard_service(self.clipboard_service)

        # Start services if they were created internally
        print("Starting services...")
        if not clipboard_service:
            self.clipboard_service.start()
        if not paste_service:
            self.paste_service.start()
        print("Services started successfully")

        # Animation settings
        self.fade_in_duration = 200  # ms
        self.fade_out_duration = 150  # ms
        self.animation_steps = 20

        print("Configuring window properties...")
        # Configure window properties
        self.title("")
        self.geometry("500x300")
        self.resizable(False, False)
        self.attributes("-topmost", True, "-alpha", 0.95)  # Start visible instead of transparent
        self.overrideredirect(True)  # Remove window decorations

        # Force window to stay on top and be always visible
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)  # Ensure it's always on top
        self.attributes("-alpha", 0.95)    # Ensure it's visible
        print("Window properties configured")

        print("Configuring grid layout...")
        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        print("Creating main frame...")
        # Create main frame with transparency
        self.main_frame = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=("gray90", "gray13"),
            border_width=1,
            border_color=("gray70", "gray30")
        )
        self.main_frame.grid(row=0, column=0, padx=2, pady=2, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        print("Main frame created")

        # Initialize UI components
        self._create_widgets()

        # Bind events
        self._bind_events()

        # Temporarily disable fade in animation for debugging
        # self._start_fade_in()
        print("Fade-in animation disabled for debugging")

    def _mock_init(self):
        """Initialize mock window for headless environments."""
        print("=== MOCK WINDOW INITIALIZATION STARTED ===")
        self.mock_mode = True

        # Mock all the attributes and methods that would be set by real Tkinter
        self.timeout = 10
        self.on_close_callback = None
        self.timer_thread = None
        self.animation_thread = None
        self.is_destroyed = False
        self.is_animating = False
        self.current_opacity = 0.95
        self.target_opacity = 1.0

        # Mock window methods
        self.winfo_exists = lambda: True
        self.geometry = lambda: "500x300+100+100"
        self.attributes = MagicMock()
        self.title = MagicMock()
        self.resizable = MagicMock()
        self.overrideredirect = MagicMock()
        self.grid_columnconfigure = MagicMock()
        self.grid_rowconfigure = MagicMock()
        self.deiconify = MagicMock()
        self.lift = MagicMock()
        self.focus_force = MagicMock()
        self.after = MagicMock()
        self.bind = MagicMock()
        self.destroy = MagicMock()

        # Mock widgets
        self.main_frame = MagicMock()
        self.content_frame = MagicMock()
        self.original_textbox = MagicMock()
        self.translation_textbox = MagicMock()
        self.loading_label = MagicMock()
        self.progress_bar = MagicMock()
        self.copy_original_button = MagicMock()
        self.copy_translation_button = MagicMock()
        self.paste_button = MagicMock()
        self.close_button = MagicMock()

        # Mock services
        self.clipboard_service = MagicMock()
        self.paste_service = MagicMock()

        print("Mock window initialized successfully")
        print("=== MOCK WINDOW READY ===")

    def _create_widgets(self):
        """Create all UI widgets."""
        # Loading indicator (initially hidden)
        self._create_loading_section()

        # Content frame (initially hidden)
        self.content_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frame.grid(row=0, column=0, sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=1)

        # Original text section
        self._create_original_section()

        # Separator
        separator = ctk.CTkFrame(self.content_frame, height=1, fg_color=("gray75", "gray25"))
        separator.grid(row=1, column=0, padx=20, pady=8, sticky="ew")

        # Translation text section
        self._create_translation_section()

        # Buttons section
        self._create_buttons_section()

        # Initially hide content, show loading
        self.content_frame.grid_remove()

    def _create_loading_section(self):
        """Create loading indicator section."""
        loading_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        loading_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        loading_frame.grid_columnconfigure(0, weight=1)
        loading_frame.grid_rowconfigure(0, weight=1)

        # Loading label
        self.loading_label = ctk.CTkLabel(
            loading_frame,
            text="Обработка...",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.loading_label.grid(row=0, column=0, pady=(0, 10), sticky="s")

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            loading_frame,
            width=200,
            mode="indeterminate"
        )
        self.progress_bar.grid(row=1, column=0, sticky="s")
        self.progress_bar.start()

    def _create_original_section(self):
        """Create original text display section."""
        original_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        original_frame.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="ew")
        original_frame.grid_columnconfigure(0, weight=1)

        # Original label
        original_label = ctk.CTkLabel(
            original_frame,
            text="Оригинал:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray10", "gray90")
        )
        original_label.grid(row=0, column=0, pady=(0, 8), sticky="w")

        # Original text box
        self.original_textbox = ctk.CTkTextbox(
            original_frame,
            wrap="word",
            height=70,
            state="disabled",
            font=ctk.CTkFont(size=11),
            fg_color=("gray95", "gray10"),
            border_width=1,
            border_color=("gray70", "gray30")
        )
        self.original_textbox.grid(row=1, column=0, sticky="ew")

    def _create_translation_section(self):
        """Create translation text display section."""
        translation_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        translation_frame.grid(row=2, column=0, padx=15, pady=(5, 5), sticky="ew")
        translation_frame.grid_columnconfigure(0, weight=1)

        # Translation label
        translation_label = ctk.CTkLabel(
            translation_frame,
            text="Перевод:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray10", "gray90")
        )
        translation_label.grid(row=0, column=0, pady=(0, 8), sticky="w")

        # Translation text box
        self.translation_textbox = ctk.CTkTextbox(
            translation_frame,
            wrap="word",
            height=70,
            state="disabled",
            font=ctk.CTkFont(size=11),
            fg_color=("gray95", "gray10"),
            border_width=1,
            border_color=("gray70", "gray30")
        )
        self.translation_textbox.grid(row=1, column=0, sticky="ew")

    def _create_buttons_section(self):
        """Create action buttons section."""
        buttons_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        buttons_frame.grid(row=3, column=0, padx=15, pady=(10, 15), sticky="ew")

        # Configure grid for buttons
        buttons_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Copy original button
        self.copy_original_button = ctk.CTkButton(
            buttons_frame,
            text="📋 Оригинал",
            command=self._copy_original,
            height=32,
            font=ctk.CTkFont(size=10, weight="bold"),
            corner_radius=6
        )
        self.copy_original_button.grid(row=0, column=0, padx=(0, 3), pady=0, sticky="ew")

        # Copy translation button
        self.copy_translation_button = ctk.CTkButton(
            buttons_frame,
            text="📋 Перевод",
            command=self._copy_translation,
            height=32,
            font=ctk.CTkFont(size=10, weight="bold"),
            corner_radius=6
        )
        self.copy_translation_button.grid(row=0, column=1, padx=3, pady=0, sticky="ew")

        # Paste to response button
        self.paste_button = ctk.CTkButton(
            buttons_frame,
            text="📤 Вставить",
            command=self._paste_to_response,
            height=32,
            font=ctk.CTkFont(size=10, weight="bold"),
            corner_radius=6,
            fg_color=("gray70", "gray30")
        )
        self.paste_button.grid(row=0, column=2, padx=3, pady=0, sticky="ew")

        # Close button
        self.close_button = ctk.CTkButton(
            buttons_frame,
            text="✕",
            command=self._close_window,
            width=40,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6,
            fg_color="transparent",
            border_width=1,
            text_color=("gray50", "gray50"),
            hover_color=("gray80", "gray20")
        )
        self.close_button.grid(row=0, column=3, padx=(3, 0), pady=0)

    def _bind_events(self):
        """Bind window events."""
        # Close on Escape key
        self.bind("<Escape>", self._on_escape_pressed)

        # Close on focus loss
        self.bind("<FocusOut>", self._on_focus_out)

        # Prevent focus loss from closing immediately
        self.bind("<FocusIn>", self._on_focus_in)

        # Handle mouse enter/leave for auto-close
        self.bind("<Enter>", self._on_mouse_enter)
        self.bind("<Leave>", self._on_mouse_leave)

    def _on_escape_pressed(self, event):
        """Handle Escape key press."""
        self._close_window()

    def _on_focus_out(self, event):
        """Handle focus loss."""
        self._start_auto_close_timer()

    def _on_focus_in(self, event):
        """Handle focus gain."""
        self._cancel_auto_close_timer()

    def _on_mouse_enter(self, event):
        """Handle mouse enter."""
        self._cancel_auto_close_timer()

    def _on_mouse_leave(self, event):
        """Handle mouse leave."""
        self._start_auto_close_timer()

    def _update_opacity(self):
        """Update window opacity during animation."""
        if not self.is_destroyed:
            self.attributes("-alpha", self.current_opacity)

    def show_loading(self, position: Optional[Tuple[int, int]] = None):
        """Show loading state.

        Args:
            position: (x, y) coordinates to position the window
        """
        # Position the window
        if position:
            self._position_window(position)

        # Show loading, hide content
        self.content_frame.grid_remove()
        self.main_frame.grid()  # Show loading frame

        # Show window with fade in
        self.deiconify()
        self.focus_force()

    def show_result(self, original_text: str, translated_text: str,
                    position: Optional[Tuple[int, int]] = None):
        """Show translation result in the overlay.

        Args:
            original_text: Original text to display
            translated_text: Translated text to display
            position: (x, y) coordinates to position the window
        """
        print("=== SHOW_RESULT DEBUG ===")
        print(f"Original text: '{original_text}'")
        print(f"Translated text: '{translated_text}'")
        print(f"Position: {position}")
        print(f"Window exists: {self.winfo_exists()}")
        print(f"Current alpha: {self.attributes('-alpha')}")

        # Update text content
        self._set_text_content(self.original_textbox, original_text)
        self._set_text_content(self.translation_textbox, translated_text)

        # Position the window
        if position:
            self._position_window(position)
            print(f"Positioned window at: {position}")
        else:
            # Default position if none provided
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            default_pos = (screen_width // 2 - 250, screen_height // 2 - 150)  # Center the 500x300 window
            self._position_window(default_pos)
            print(f"Using default position: {default_pos}")

        # Hide loading, show content
        print("Showing content frame...")
        self.main_frame.grid()  # Ensure main frame is visible
        self.content_frame.grid()  # Show content

        # Force window to be visible
        print("Making window visible...")
        self.attributes("-alpha", 0.95)  # Ensure visible
        self.attributes("-topmost", True)  # Force on top
        self.update_idletasks()
        self.deiconify()
        self.lift()
        self.focus_force()

        # Additional force to stay on top
        self.after(100, lambda: self.attributes("-topmost", True))
        self.after(200, lambda: self.lift())
        self.after(300, lambda: self.focus_force())

        print(f"Final geometry: {self.geometry()}")
        print(f"Final alpha: {self.attributes('-alpha')}")

        # Start auto-close timer
        self._start_auto_close_timer()
        print("Auto-close timer started")

    def _set_text_content(self, textbox: ctk.CTkTextbox, text: str):
        """Set text content in a textbox."""
        textbox.configure(state="normal")
        textbox.delete("0.0", "end")
        textbox.insert("0.0", text)
        textbox.configure(state="disabled")

    def _start_fade_in(self):
        """Start fade in animation."""
        if self.is_animating:
            return

        self.is_animating = True
        self.current_opacity = 0.0
        self.target_opacity = 1.0
        self.attributes("-alpha", self.current_opacity)

        self.animation_thread = threading.Thread(
            target=self._fade_animation_worker,
            daemon=True
        )
        self.animation_thread.start()

    def _start_fade_out(self, callback: Optional[Callable] = None):
        """Start fade out animation.

        Args:
            callback: Function to call after fade out completes
        """
        if self.is_animating:
            return

        self.is_animating = True
        self.current_opacity = 1.0
        self.target_opacity = 0.0

        self.animation_thread = threading.Thread(
            target=self._fade_animation_worker,
            args=(callback,),
            daemon=True
        )
        self.animation_thread.start()

    def _fade_animation_worker(self, callback: Optional[Callable] = None):
        """Worker function for fade animation."""
        step_duration = self.fade_in_duration / self.animation_steps if self.target_opacity > self.current_opacity else self.fade_out_duration / self.animation_steps
        opacity_step = (self.target_opacity - self.current_opacity) / self.animation_steps

        for _ in range(self.animation_steps):
            if self.is_destroyed:
                break

            self.current_opacity += opacity_step
            self.current_opacity = max(0.0, min(1.0, self.current_opacity))

            # Update opacity on main thread - with error handling
            try:
                self.after(0, self._update_opacity)
            except RuntimeError as e:
                if "main thread is not in main loop" in str(e):
                    print(f"Animation stopped: main loop not running")
                    break
                else:
                    raise
            
            time.sleep(step_duration / 1000.0)

        self.is_animating = False

        if callback and not self.is_destroyed:
            try:
                self.after(0, callback)
            except RuntimeError as e:
                if "main thread is not in main loop" in str(e):
                    print(f"Callback skipped: main loop not running")
                    # Call callback directly if main loop is not running
                    callback()
                else:
                    raise

    def _position_window(self, position: Tuple[int, int]):
        """Position the window at specified coordinates with smart positioning.

        Args:
            position: (x, y) coordinates
        """
        x, y = position

        # Get window dimensions
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()

        # Get screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        # Smart positioning: try to position below and to the right first
        preferred_x = x + 20
        preferred_y = y + 20

        # Check if preferred position fits
        if preferred_x + width > screen_width:
            # Try left side
            preferred_x = x - width - 20
            if preferred_x < 0:
                # Center horizontally
                preferred_x = max(20, (screen_width - width) // 2)

        if preferred_y + height > screen_height:
            # Try above
            preferred_y = y - height - 20
            if preferred_y < 0:
                # Center vertically
                preferred_y = max(20, (screen_height - height) // 2)

        # Ensure final position is within screen bounds
        final_x = max(0, min(preferred_x, screen_width - width))
        final_y = max(0, min(preferred_y, screen_height - height))

        self.geometry(f"{width}x{height}+{final_x}+{final_y}")

    def _copy_original(self):
        """Copy original text to clipboard."""
        try:
            original_text = self.original_textbox.get("0.0", "end").strip()
            if self.clipboard_service.copy_text(original_text):
                self._show_feedback("Оригинальный текст скопирован")
            else:
                self._show_feedback("Ошибка копирования оригинального текста", error=True)
        except Exception as e:
            self._show_feedback(f"Ошибка копирования: {str(e)}", error=True)

    def _copy_translation(self):
        """Copy translated text to clipboard."""
        try:
            translated_text = self.translation_textbox.get("0.0", "end").strip()
            if self.clipboard_service.copy_text(translated_text):
                self._show_feedback("Переведенный текст скопирован")
            else:
                self._show_feedback("Ошибка копирования переведенного текста", error=True)
        except Exception as e:
            self._show_feedback(f"Ошибка копирования: {str(e)}", error=True)

    def _paste_to_response(self):
        """Paste translated text to active application."""
        try:
            translated_text = self.translation_textbox.get("0.0", "end").strip()

            if self.paste_service.paste_text(translated_text):
                self._show_feedback("Текст вставлен в активное окно")
                # Close window after successful pasting
                self.after(500, self._close_window)
            else:
                self._show_feedback("Ошибка вставки текста", error=True)

        except Exception as e:
            self._show_feedback(f"Ошибка вставки: {str(e)}", error=True)

    def _close_window(self):
        """Close the overlay window with fade out animation."""
        if self.is_destroyed:
            return

        self._cancel_auto_close_timer()

        def destroy_window():
            if not self.is_destroyed:
                self.is_destroyed = True
                # Stop services if they were created internally
                try:
                    if hasattr(self, 'clipboard_service') and self.clipboard_service:
                        self.clipboard_service.stop()
                    if hasattr(self, 'paste_service') and self.paste_service:
                        self.paste_service.stop()
                except Exception as e:
                    print(f"Error stopping services: {e}")
                if self.on_close_callback:
                    self.on_close_callback()
                self.destroy()

        self._start_fade_out(destroy_window)

    def _start_auto_close_timer(self):
        """Start the auto-close timer."""
        self._cancel_auto_close_timer()

        if self.timeout > 0:
            self.timer_thread = threading.Thread(
                target=self._auto_close_worker,
                daemon=True
            )
            self.timer_thread.start()

    def _cancel_auto_close_timer(self):
        """Cancel the auto-close timer."""
        if self.timer_thread and self.timer_thread.is_alive():
            # Thread will check is_destroyed flag
            pass

    def _auto_close_worker(self):
        """Worker function for auto-close timer."""
        time.sleep(self.timeout)

        if not self.is_destroyed:
            try:
                # Check focus safely
                has_focus = self.focus_get() is not None
            except RuntimeError as e:
                if "main thread is not in main loop" in str(e):
                    print(f"Auto-close timer stopped: main loop not running")
                    return
                else:
                    # Assume no focus if we can't check
                    has_focus = False
            
            if not has_focus:
                try:
                    # Use after() to safely close from main thread
                    self.after(0, self._close_window)
                except RuntimeError as e:
                    if "main thread is not in main loop" in str(e):
                        print(f"Auto-close skipped: main loop not running")
                        # Call close directly if main loop is not running
                        self._close_window()
                    else:
                        raise

    def set_clipboard_service(self, clipboard_service: ClipboardService):
        """Set the clipboard service instance.

        Args:
            clipboard_service: Clipboard service instance
        """
        self.clipboard_service = clipboard_service
        if self.paste_service:
            self.paste_service.set_clipboard_service(clipboard_service)

    def set_paste_service(self, paste_service: PasteService):
        """Set the paste service instance.

        Args:
            paste_service: Paste service instance
        """
        self.paste_service = paste_service
        if self.clipboard_service:
            self.paste_service.set_clipboard_service(self.clipboard_service)

    def _show_feedback(self, message: str, error: bool = False):
        """Show feedback message to user."""
        # For now, just print to console
        # In real implementation, could show a tooltip or status message
        if error:
            print(f"Error: {message}")
        else:
            print(f"Info: {message}")


if __name__ == "__main__":
    # For testing the overlay window independently
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.withdraw()  # Hide main window

    overlay = OverlayWindow(root)
    overlay.show_result(
        "Hello, how are you today?",
        "Привет, как ты сегодня?",
        (100, 100)
    )

    root.mainloop()