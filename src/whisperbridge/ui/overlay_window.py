"""
Overlay window for displaying translation results.

This module provides a compact overlay window that shows original text
and translation results with action buttons for copying and pasting.
Enhanced with animations, loading indicators, and improved positioning.
"""

import customtkinter as ctk
from typing import Optional, Tuple, Callable
import threading
import time
from loguru import logger

from ..services.clipboard_service import ClipboardService
from ..services.paste_service import PasteService


class OverlayWindow(ctk.CTkToplevel):
    """A simplified overlay window for displaying translation results."""

    def __init__(self, parent, **kwargs):
        """Initialize the simplified overlay window."""
        super().__init__(parent, **kwargs)
        logger.debug("OverlayWindow __init__ started.")

        # Basic window configuration
        self.attributes("-topmost", True)
        self.overrideredirect(True)
        self.geometry("500x300")
        logger.debug("OverlayWindow basic configuration set.")

        # Main frame
        self.main_frame = ctk.CTkFrame(self, corner_radius=10, border_width=1)
        self.main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)
        logger.debug("Main frame created and packed.")
        
        self.content_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frame.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        self.content_frame.grid_columnconfigure(0, weight=1)

        self._create_original_section()
        self._create_translation_section()
        self._create_buttons_section()
        self._bind_events()
        
        self.is_destroyed = False
        self.timeout = 10  # seconds
        self.on_close_callback = None
        self.timer_thread = None
        self.animation_thread = None
        self.is_animating = False
        self.current_opacity = 0.95
        self.target_opacity = 1.0
        self.fade_in_duration = 200  # ms
        self.fade_out_duration = 200  # ms
        self.animation_steps = 20

        self.clipboard_service = ClipboardService()
        self.paste_service = PasteService()
        
        logger.debug("OverlayWindow __init__ finished.")



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
        logger.debug(f"show_result called. Position: {position}")
        logger.debug(f"Original text: '{original_text}'")
        logger.debug(f"Translated text: '{translated_text}'")
        logger.debug(f"Position: {position}")
        logger.debug(f"Window exists: {self.winfo_exists()}")
        logger.debug(f"Current alpha: {self.attributes('-alpha')}")

        # Update text content
        self._set_text_content(self.original_textbox, original_text)
        self._set_text_content(self.translation_textbox, translated_text)

        # Position the window
        if position:
            self._position_window(position)
            logger.debug(f"Positioned window at: {position}")
        else:
            # Default position if none provided
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            default_pos = (screen_width // 2 - 250, screen_height // 2 - 150)  # Center the 500x300 window
            self._position_window(default_pos)
            logger.debug(f"Using default position: {default_pos}")

        # Hide loading, show content
        logger.debug("Showing content frame...")
        
        # Force window to be visible and responsive
        logger.debug("Making window visible.")
        
        # Update window content and make it visible
        self.update_idletasks()
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()

        # Start fade in animation
        self._start_fade_in()

        logger.debug(f"Final geometry: {self.geometry()}")
        logger.debug(f"Final alpha: {self.attributes('-alpha')}")
        logger.debug("Overlay window should now be visible and responsive")

    def _set_text_content(self, textbox, text: str):
        """Set text content in a CTkTextbox."""
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
                    logger.debug("Animation stopped: main loop not running")
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
                    logger.debug("Callback skipped: main loop not running")
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
            original_text = self.original_textbox.get("1.0", "end-1c").strip()
            if self.clipboard_service.copy_text(original_text):
                self._show_feedback("Оригинальный текст скопирован")
            else:
                self._show_feedback("Ошибка копирования оригинального текста", error=True)
        except Exception as e:
            self._show_feedback(f"Ошибка копирования: {str(e)}", error=True)

    def _copy_translation(self):
        """Copy translated text to clipboard."""
        try:
            translated_text = self.translation_textbox.get("1.0", "end-1c").strip()
            if self.clipboard_service.copy_text(translated_text):
                self._show_feedback("Переведенный текст скопирован")
            else:
                self._show_feedback("Ошибка копирования переведенного текста", error=True)
        except Exception as e:
            self._show_feedback(f"Ошибка копирования: {str(e)}", error=True)

    def _paste_to_response(self):
        """Paste translated text to active application."""
        try:
            translated_text = self.translation_textbox.get("1.0", "end-1c").strip()

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
                    logger.error(f"Error stopping services: {e}")
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
                    logger.debug("Auto-close timer stopped: main loop not running")
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
                        logger.debug("Auto-close skipped: main loop not running")
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
        """Show feedback message to user with temporary notification."""
        if error:
            logger.error(f"Overlay feedback: {message}")
        else:
            logger.info(f"Overlay feedback: {message}")
        
        # Create temporary feedback label
        feedback_label = ctk.CTkLabel(
            self.main_frame,
            text=message,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=("red", "red") if error else ("green", "lightgreen"),
            fg_color=("white", "gray20"),
            corner_radius=5
        )
        
        # Position feedback at the bottom of the window
        feedback_label.place(relx=0.5, rely=0.9, anchor="center")
        
        # Auto-hide feedback after 2 seconds
        def hide_feedback():
            try:
                if feedback_label.winfo_exists():
                    feedback_label.destroy()
            except:
                pass
        
        self.after(2000, hide_feedback)


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