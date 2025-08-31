"""
Hotkey input component for WhisperBridge.

This module provides a reusable hotkey input widget with
real-time validation and key capture functionality.
"""

import customtkinter as ctk
from typing import Optional, Callable, List
import tkinter as tk


class HotkeyInput(ctk.CTkFrame):
    """Hotkey input component with validation and key capture."""

    # Valid modifier keys
    MODIFIERS = ["ctrl", "alt", "shift", "cmd", "win", "super"]
    # Valid function keys
    FUNCTION_KEYS = [f"f{i}" for i in range(1, 13)]
    # Valid special keys
    SPECIAL_KEYS = ["space", "enter", "tab", "esc", "backspace", "delete", "insert",
                   "home", "end", "pageup", "pagedown", "up", "down", "left", "right"]

    def __init__(self, master, label_text: str = "Горячая клавиша",
                 placeholder: str = "ctrl+shift+t", width: int = 200,
                 command: Optional[Callable] = None, **kwargs):
        """Initialize the hotkey input.

        Args:
            master: Parent widget
            label_text: Label text for the input
            placeholder: Placeholder text
            width: Width of the entry
            command: Callback function when hotkey changes
            **kwargs: Additional arguments for CTkFrame
        """
        super().__init__(master, **kwargs)

        self.label_text = label_text
        self.placeholder = placeholder
        self.command = command
        self.is_capturing = False
        self.current_keys = set()

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)

        # Create widgets
        self._create_widgets(width)

        # Bind events
        self._bind_events()

    def _create_widgets(self, width: int):
        """Create the component widgets."""
        # Label
        self.label = ctk.CTkLabel(
            self,
            text=self.label_text,
            font=ctk.CTkFont(size=12)
        )
        self.label.grid(row=0, column=0, pady=(0, 5), sticky="w")

        # Frame for entry and buttons
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.grid(row=1, column=0, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        # Entry
        self.entry = ctk.CTkEntry(
            input_frame,
            placeholder_text=self.placeholder,
            width=width,
            state="readonly"
        )
        self.entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        # Record button
        self.record_button = ctk.CTkButton(
            input_frame,
            text="Записать",
            command=self._start_recording,
            width=80,
            height=28,
            font=ctk.CTkFont(size=10)
        )
        self.record_button.grid(row=0, column=1, padx=(0, 5))

        # Clear button
        self.clear_button = ctk.CTkButton(
            input_frame,
            text="Очистить",
            command=self._clear_hotkey,
            width=80,
            height=28,
            font=ctk.CTkFont(size=10),
            fg_color="transparent",
            border_width=2,
            text_color=("gray10", "#DCE4EE")
        )
        self.clear_button.grid(row=0, column=2)

        # Status label
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="gray60"
        )
        self.status_label.grid(row=2, column=0, pady=(5, 0), sticky="w")

    def _bind_events(self):
        """Bind keyboard events for hotkey capture."""
        # Bind to the root window to capture global key events
        root = self.winfo_toplevel()

        # Key press event
        root.bind("<KeyPress>", self._on_key_press, add="+")
        root.bind("<KeyRelease>", self._on_key_release, add="+")

        # Focus events
        self.entry.bind("<FocusIn>", lambda e: self._on_focus_in())
        self.entry.bind("<FocusOut>", lambda e: self._on_focus_out())

    def _start_recording(self):
        """Start recording a new hotkey."""
        self.is_capturing = True
        self.current_keys.clear()
        self.entry.configure(state="normal")
        self.entry.delete(0, "end")
        self.entry.insert(0, "Нажмите клавиши...")
        self.entry.configure(state="readonly")

        self.record_button.configure(
            text="Остановить",
            fg_color=("gray75", "gray30")
        )

        self.status_label.configure(
            text="Нажмите комбинацию клавиш",
            text_color=("gray10", "#DCE4EE")
        )

        # Focus the entry to capture keys
        self.entry.focus_force()

    def _stop_recording(self):
        """Stop recording hotkey."""
        self.is_capturing = False
        self.record_button.configure(
            text="Записать",
            fg_color=("gray75", "gray25")
        )
        self.status_label.configure(text="", text_color="gray60")

    def _on_key_press(self, event):
        """Handle key press event."""
        if not self.is_capturing:
            return

        # Prevent default behavior
        event.widget.focus_set()

        key = self._normalize_key(event.keysym.lower())

        if key:
            self.current_keys.add(key)
            self._update_display()

    def _on_key_release(self, event):
        """Handle key release event."""
        if not self.is_capturing:
            return

        # If we have a valid hotkey combination, stop recording
        if len(self.current_keys) >= 2:  # At least modifier + key
            hotkey_str = self._keys_to_string()
            if self._validate_hotkey(hotkey_str):
                self._set_hotkey(hotkey_str)
                self._stop_recording()
                if self.command:
                    self.command(hotkey_str)

    def _on_focus_in(self):
        """Handle focus in event."""
        if self.is_capturing:
            self.status_label.configure(
                text="Нажмите комбинацию клавиш",
                text_color=("gray10", "#DCE4EE")
            )

    def _on_focus_out(self):
        """Handle focus out event."""
        if self.is_capturing:
            # Stop recording if focus is lost
            self._stop_recording()
            self.status_label.configure(
                text="Запись отменена",
                text_color="red"
            )

    def _normalize_key(self, key: str) -> Optional[str]:
        """Normalize key name for consistent representation.

        Args:
            key: Raw key symbol

        Returns:
            Optional[str]: Normalized key name or None if invalid
        """
        # Handle modifiers
        if key in ["control_l", "control_r"]:
            return "ctrl"
        elif key in ["alt_l", "alt_r"]:
            return "alt"
        elif key in ["shift_l", "shift_r"]:
            return "shift"
        elif key in ["super_l", "super_r", "meta_l", "meta_r"]:
            return "super"
        elif key in ["command_l", "command_r"]:
            return "cmd"

        # Handle special keys
        elif key == "space":
            return "space"
        elif key == "return":
            return "enter"
        elif key == "escape":
            return "esc"
        elif key == "backspace":
            return "backspace"
        elif key == "delete":
            return "delete"
        elif key == "insert":
            return "insert"
        elif key == "home":
            return "home"
        elif key == "end":
            return "end"
        elif key == "next":
            return "pagedown"
        elif key == "prior":
            return "pageup"
        elif key in ["up", "down", "left", "right"]:
            return key

        # Handle function keys
        elif key.startswith("f") and key[1:].isdigit():
            num = int(key[1:])
            if 1 <= num <= 12:
                return f"f{num}"

        # Handle alphanumeric keys
        elif len(key) == 1 and (key.isalnum() or key in "!@#$%^&*()_+-=[]{}|;:,.<>?"):
            return key.lower()

        return None

    def _update_display(self):
        """Update the entry display with current keys."""
        if not self.current_keys:
            return

        hotkey_str = self._keys_to_string()
        self.entry.configure(state="normal")
        self.entry.delete(0, "end")
        self.entry.insert(0, hotkey_str)
        self.entry.configure(state="readonly")

    def _keys_to_string(self) -> str:
        """Convert current keys set to hotkey string.

        Returns:
            str: Formatted hotkey string
        """
        modifiers = []
        main_key = None

        for key in sorted(self.current_keys):
            if key in self.MODIFIERS:
                modifiers.append(key)
            else:
                main_key = key

        if not main_key:
            return "+".join(sorted(modifiers))
        elif modifiers:
            return "+".join(sorted(modifiers) + [main_key])
        else:
            return main_key

    def _validate_hotkey(self, hotkey: str) -> bool:
        """Validate hotkey format.

        Args:
            hotkey: Hotkey string to validate

        Returns:
            bool: True if valid
        """
        if not hotkey:
            return False

        parts = hotkey.lower().split("+")

        # Must have at least one modifier and one main key
        if len(parts) < 2:
            return False

        modifiers = parts[:-1]
        main_key = parts[-1]

        # Check modifiers
        for mod in modifiers:
            if mod not in self.MODIFIERS:
                return False

        # Check main key
        if (main_key not in self.FUNCTION_KEYS and
            main_key not in self.SPECIAL_KEYS and
            not (len(main_key) == 1 and main_key.isalnum())):
            return False

        return True

    def _set_hotkey(self, hotkey: str):
        """Set the hotkey value.

        Args:
            hotkey: Hotkey string
        """
        self.entry.configure(state="normal")
        self.entry.delete(0, "end")
        self.entry.insert(0, hotkey)
        self.entry.configure(state="readonly")

    def _clear_hotkey(self):
        """Clear the current hotkey."""
        self.entry.configure(state="normal")
        self.entry.delete(0, "end")
        self.entry.configure(state="readonly")
        self.current_keys.clear()

        if self.command:
            self.command("")

    def get_hotkey(self) -> str:
        """Get the current hotkey.

        Returns:
            str: Current hotkey string
        """
        return self.entry.get().strip()

    def set_hotkey(self, hotkey: str):
        """Set the hotkey value.

        Args:
            hotkey: Hotkey string to set
        """
        if self._validate_hotkey(hotkey):
            self._set_hotkey(hotkey)
        else:
            print(f"Warning: Invalid hotkey format '{hotkey}'")

    def set_enabled(self, enabled: bool):
        """Enable or disable the component.

        Args:
            enabled: Whether the component should be enabled
        """
        state = "normal" if enabled else "disabled"
        self.record_button.configure(state=state)
        self.clear_button.configure(state=state)

        if enabled:
            self.entry.configure(state="readonly")
            self.label.configure(text_color=("gray10", "gray90"))
        else:
            self.entry.configure(state="disabled")
            self.label.configure(text_color=("gray60", "gray40"))


if __name__ == "__main__":
    # Test the component
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Hotkey Input Test")
    root.geometry("400x150")

    def on_hotkey_change(hotkey):
        print(f"Hotkey changed: {hotkey}")

    hotkey_input = HotkeyInput(
        root,
        label_text="Translation Hotkey:",
        command=on_hotkey_change
    )
    hotkey_input.grid(row=0, column=0, padx=20, pady=20, sticky="ew")

    # Test setting hotkey
    hotkey_input.set_hotkey("ctrl+shift+t")

    root.mainloop()