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

    def __init__(self, parent, timeout: int = 10, on_close_callback: Optional[Callable] = None, **kwargs):
        """Initialize the simplified overlay window.

        Args:
            parent: Parent window
            timeout: Auto-close timeout in seconds
            on_close_callback: Callback function when window closes
        """
        super().__init__(parent, **kwargs)
        logger.debug("OverlayWindow __init__ started.")
        
        # Log parent window state
        logger.info("Parent window state:")
        if parent:
            try:
                logger.info(f"  - Parent exists: {parent.winfo_exists()}")
                logger.info(f"  - Parent is mapped: {parent.winfo_ismapped() if parent.winfo_exists() else 'N/A'}")
                logger.info(f"  - Parent is viewable: {parent.winfo_viewable() if parent.winfo_exists() else 'N/A'}")
                logger.info(f"  - Parent geometry: {parent.geometry() if parent.winfo_exists() else 'N/A'}")
            except Exception as e:
                logger.warning(f"Could not log parent window state: {e}")
        else:
            logger.warning("No parent window provided")

        # Basic window configuration
        self.attributes("-topmost", True)
        # Don't set overrideredirect here - will be set in show_result after geometry
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
        self.timeout = timeout  # seconds
        self.on_close_callback = on_close_callback
        self.timer_thread = None
        self.animation_thread = None
        self.is_animating = False
        self.current_opacity = 0.95
        self.target_opacity = 1.0
        self.fade_in_duration = 200  # ms
        self.fade_out_duration = 200  # ms
        self.animation_steps = 20
        self.pending_callbacks = []  # Track scheduled callbacks

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
        if not self.is_destroyed and self.winfo_exists():
            try:
                # Set the opacity
                self.attributes("-alpha", self.current_opacity)

                # If this is the first or last step, do more thorough logging
                if self.current_opacity <= 0.05 or self.current_opacity >= 0.95:
                    logger.debug(f"Setting window opacity to {self.current_opacity:.3f}")
            except Exception as e:
                logger.warning(f"Failed to update opacity: {e}")
                # Stop animation if window is invalid
                self.is_animating = False
    
    def _verify_opacity_step(self, step, expected_opacity):
        """Verify the opacity was properly set during animation."""
        if not self.is_destroyed and self.winfo_exists():
            try:
                actual_opacity = self.attributes("-alpha")
                # Only log if there's a significant difference
                if abs(float(actual_opacity) - expected_opacity) > 0.05:
                    logger.warning(f"Opacity verification at step {step}: expected={expected_opacity:.3f}, actual={actual_opacity}")
                    logger.warning(f"Window state: exists={self.winfo_exists()}, viewable={self.winfo_viewable()}")
            except Exception as e:
                logger.warning(f"Error verifying opacity at step {step}: {e}")
                # Stop animation if window is invalid
                self.is_animating = False

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
                    position: Optional[Tuple[int, int]] = None, size: Optional[Tuple[int, int]] = None):
        """Show translation result in the overlay.

        Args:
            original_text: Original text to display
            translated_text: Translated text to display
            position: (x, y) coordinates to position the window
            size: Optional (width, height) tuple for window size
        """
        logger.info(f"=== OVERLAY WINDOW SHOW_RESULT CALLED ===")
        logger.debug(f"Original text: '{original_text[:50]}{'...' if len(original_text) > 50 else ''}'")
        logger.debug(f"Translated text: '{translated_text[:50]}{'...' if len(translated_text) > 50 else ''}'")
        logger.debug(f"Position: {position}")
        
        # Log detailed window state before changes
        logger.info(f"PRE-DISPLAY WINDOW STATE:")
        logger.info(f"  - Window exists: {self.winfo_exists()}")
        logger.info(f"  - Window viewable: {self.winfo_viewable() if self.winfo_exists() else 'N/A'}")
        logger.info(f"  - Current alpha: {self.attributes('-alpha')}")
        logger.info(f"  - Window state: {self.state()}")
        logger.info(f"  - Current geometry: {self.geometry()}")
        logger.info(f"  - Is mapped: {self.winfo_ismapped() if self.winfo_exists() else 'N/A'}")
        logger.info(f"  - Is visible: {self.winfo_viewable() if self.winfo_exists() else 'N/A'}")
        logger.info(f"  - Parent visibility: {self.master.winfo_viewable() if self.master and self.master.winfo_exists() else 'N/A'}")

        # Update text content
        self._set_text_content(self.original_textbox, original_text)
        self._set_text_content(self.translation_textbox, translated_text)
        logger.debug("Text content updated in textboxes")

        # Position the window
        if position:
            logger.info(f"Positioning window at requested position: {position}")
            self._position_window(position, size)
            logger.debug(f"Window positioned at: {position}")
        else:
            # Default position if none provided
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            default_pos = (screen_width // 2 - 250, screen_height // 2 - 150)  # Center the 500x300 window
            logger.info(f"Using default center position: {default_pos}")
            self._position_window(default_pos, size)
            logger.debug(f"Window positioned at default center")

        # Log window dimensions after positioning
        w, h = self.winfo_width(), self.winfo_height()
        logger.info(f"Window dimensions after positioning: width={w}, height={h}")
        
        # Hide loading, show content - add frame visibility logging
        logger.info("Showing content frame...")
        if hasattr(self, 'content_frame'):
            self.content_frame.grid()
            logger.debug(f"Content frame visibility: configured={self.content_frame.grid_info() != {}}")
        
        # Force window to be visible and responsive
        logger.info("Making window visible with explicit commands...")
        
        # Update window content and make it visible
        logger.debug("Calling update_idletasks()...")
        self.update_idletasks()
        
        logger.debug("Calling deiconify()...")
        self.deiconify()
        
        logger.debug("Calling lift()...")
        self.lift()
        
        logger.debug("Setting topmost attribute...")
        self.attributes("-topmost", True)
        
        logger.debug("Forcing focus...")
        self.focus_force()

        # Log window state after visibility commands
        logger.info(f"POST-COMMANDS WINDOW STATE:")
        logger.info(f"  - Window exists: {self.winfo_exists()}")
        logger.info(f"  - Window viewable: {self.winfo_viewable() if self.winfo_exists() else 'N/A'}")
        logger.info(f"  - Alpha value: {self.attributes('-alpha')}")
        logger.info(f"  - Window state: {self.state()}")
        logger.info(f"  - Window geometry: {self.geometry()}")
        logger.info(f"  - Z-order index: Top (forced with lift and topmost)")
        logger.info(f"  - Is mapped: {self.winfo_ismapped() if self.winfo_exists() else 'N/A'}")
        
        # Start fade in animation
        logger.debug("Starting fade-in animation...")
        self._start_fade_in()

        # Final verification logs
        logger.info(f"=== FINAL OVERLAY WINDOW STATE ===")
        logger.info(f"  - Final geometry: {self.geometry()}")
        logger.info(f"  - Final alpha before animation: {self.attributes('-alpha')}")
        logger.info(f"  - Window mapped: {self.winfo_ismapped() if self.winfo_exists() else 'N/A'}")
        logger.info(f"  - Window viewable: {self.winfo_viewable() if self.winfo_exists() else 'N/A'}")
        logger.info(f"  - Overlay window display sequence completed")

    def _set_text_content(self, textbox, text: str):
        """Set text content in a CTkTextbox."""
        textbox.configure(state="normal")
        textbox.delete("0.0", "end")
        textbox.insert("0.0", text)
        textbox.configure(state="disabled")

    def _start_fade_in(self):
        """Start fade in animation."""
        logger.info("=== STARTING FADE-IN ANIMATION ===")
        
        if self.is_animating:
            logger.warning("Animation already in progress, skipping new fade-in request")
            return

        # Log pre-animation state
        logger.info(f"Pre-animation window state:")
        logger.info(f"  - Current opacity: {self.attributes('-alpha')}")
        logger.info(f"  - Window exists: {self.winfo_exists()}")
        logger.info(f"  - Window viewable: {self.winfo_viewable() if self.winfo_exists() else 'N/A'}")

        self.is_animating = True
        self.current_opacity = 0.0  # Start fully transparent
        self.target_opacity = 1.0   # End fully opaque
        
        # Set initial transparent state
        logger.debug(f"Setting initial alpha to {self.current_opacity}")
        self.attributes("-alpha", self.current_opacity)
        
        # Verify alpha was set correctly
        actual_alpha = self.attributes("-alpha")
        logger.debug(f"Actual alpha after setting: {actual_alpha}")
        
        # Create and start animation thread
        logger.debug(f"Creating animation thread with parameters: steps={self.animation_steps}, duration={self.fade_in_duration}ms")
        self.animation_thread = threading.Thread(
            target=self._fade_animation_worker,
            daemon=True,
            name="OverlayFadeInThread"
        )
        
        logger.debug("Starting animation thread...")
        self.animation_thread.start()
        logger.info(f"Fade-in animation thread started: {self.animation_thread.name}")

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
        logger.info(f"Fade animation worker started")
        
        # Calculate animation parameters
        is_fade_in = self.target_opacity > self.current_opacity
        animation_type = "fade-in" if is_fade_in else "fade-out"
        step_duration = self.fade_in_duration / self.animation_steps if is_fade_in else self.fade_out_duration / self.animation_steps
        opacity_step = (self.target_opacity - self.current_opacity) / self.animation_steps
        
        logger.debug(f"Animation parameters: type={animation_type}, steps={self.animation_steps}, " +
                     f"step_duration={step_duration:.2f}ms, opacity_step={opacity_step:.3f}")
        logger.debug(f"Starting opacity: {self.current_opacity}, target opacity: {self.target_opacity}")

        for step in range(self.animation_steps):
            if self.is_destroyed:
                logger.warning("Window destroyed during animation, stopping animation")
                break

            # Calculate new opacity
            self.current_opacity += opacity_step
            self.current_opacity = max(0.0, min(1.0, self.current_opacity))
            
            # Log animation progress every few steps
            if step == 0 or step == self.animation_steps - 1 or step % 5 == 0:
                logger.debug(f"Animation step {step+1}/{self.animation_steps}: opacity={self.current_opacity:.3f}")

            # Update opacity on main thread - with error handling
            try:
                callback_id = self.after(0, self._update_opacity)
                self.pending_callbacks.append(callback_id)
                
                # Verify opacity was actually applied (log every few steps)
                if step == 0 or step == self.animation_steps - 1 or step % 5 == 0:
                    # This verification would need to run on the main thread too
                    callback_id = self.after(10, lambda s=step: self._verify_opacity_step(s, self.current_opacity))
                    self.pending_callbacks.append(callback_id)
                    
            except RuntimeError as e:
                if "main thread is not in main loop" in str(e):
                    logger.warning(f"Animation step {step+1} failed: main loop not running")
                    break
                else:
                    logger.error(f"Animation error: {e}", exc_info=True)
                    raise
            
            # Sleep for the step duration
            time.sleep(step_duration / 1000.0)

        # Animation completed or interrupted
        self.is_animating = False
        logger.info(f"Animation completed: final opacity={self.current_opacity:.3f}")
        
        # Execute callback if provided
        if callback and not self.is_destroyed:
            logger.debug("Executing animation completion callback")
            try:
                callback_id = self.after(0, callback)
                self.pending_callbacks.append(callback_id)
            except RuntimeError as e:
                if "main thread is not in main loop" in str(e):
                    logger.warning("Callback scheduling failed: main loop not running")
                    # Call callback directly if main loop is not running
                    logger.debug("Attempting to call callback directly")
                    callback()
                else:
                    logger.error(f"Callback error: {e}", exc_info=True)
                    raise

    def _position_window(self, position: Tuple[int, int], size: Optional[Tuple[int, int]] = None):
        """Position the window at specified coordinates with smart positioning.

        Args:
            position: (x, y) coordinates
            size: Optional (width, height) tuple. If not provided, uses current window size.
        """
        x, y = position

        # Get window dimensions
        if size:
            width, height = size
            logger.debug(f"Using provided size: {width}x{height}")
        else:
            self.update_idletasks()
            width = self.winfo_width()
            height = self.winfo_height()
            logger.debug(f"Using current window size: {width}x{height}")

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

        logger.debug(f"Final positioning: {width}x{height}+{final_x}+{final_y}")
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
                callback_id = self.after(500, self._close_window)
                self.pending_callbacks.append(callback_id)
            else:
                self._show_feedback("Ошибка вставки текста", error=True)

        except Exception as e:
            self._show_feedback(f"Ошибка вставки: {str(e)}", error=True)

    def _cancel_pending_callbacks(self):
        """Cancel all pending callbacks to prevent invalid command errors."""
        for callback_id in self.pending_callbacks:
            try:
                self.after_cancel(callback_id)
            except Exception as e:
                logger.warning(f"Failed to cancel callback {callback_id}: {e}")
        self.pending_callbacks.clear()

    def _close_window(self):
        """Close the overlay window with fade out animation."""
        if self.is_destroyed:
            return

        self._cancel_auto_close_timer()
        self._cancel_pending_callbacks()

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
                    callback_id = self.after(0, self._close_window)
                    self.pending_callbacks.append(callback_id)
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
        
        callback_id = self.after(2000, hide_feedback)
        self.pending_callbacks.append(callback_id)


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