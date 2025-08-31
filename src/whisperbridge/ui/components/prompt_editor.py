"""
Prompt editor component for WhisperBridge.

This module provides a reusable prompt editing widget with
templates, validation, and formatting assistance.
"""

import customtkinter as ctk
from typing import Optional, Callable, Dict, List
import tkinter as tk


class PromptEditor(ctk.CTkFrame):
    """Prompt editor component with templates and validation."""

    # Predefined prompt templates
    TEMPLATES = {
        "default": {
            "name": "Стандартный",
            "prompt": "Translate the following text to {target_language}:"
        },
        "formal": {
            "name": "Формальный",
            "prompt": "Translate the following text formally to {target_language}:"
        },
        "casual": {
            "name": "Разговорный",
            "prompt": "Translate the following text in a casual way to {target_language}:"
        },
        "technical": {
            "name": "Технический",
            "prompt": "Translate the following technical text to {target_language}, preserving technical terms:"
        },
        "literary": {
            "name": "Литературный",
            "prompt": "Translate the following text in a literary style to {target_language}:"
        },
        "medical": {
            "name": "Медицинский",
            "prompt": "Translate the following medical text to {target_language}, using appropriate medical terminology:"
        },
        "legal": {
            "name": "Юридический",
            "prompt": "Translate the following legal text to {target_language}, maintaining legal precision:"
        }
    }

    # Available placeholders
    PLACEHOLDERS = {
        "{source_language}": "язык оригинала",
        "{target_language}": "язык перевода",
        "{text}": "текст для перевода"
    }

    def __init__(self, master, label_text: str = "Системный промпт",
                 height: int = 120, command: Optional[Callable] = None, **kwargs):
        """Initialize the prompt editor.

        Args:
            master: Parent widget
            label_text: Label text for the editor
            height: Height of the text box
            command: Callback function when prompt changes
            **kwargs: Additional arguments for CTkFrame
        """
        super().__init__(master, **kwargs)

        self.label_text = label_text
        self.command = command
        self.height = height

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)

        # Create widgets
        self._create_widgets()

        # Bind events
        self._bind_events()

    def _create_widgets(self):
        """Create the component widgets."""
        # Label
        self.label = ctk.CTkLabel(
            self,
            text=self.label_text,
            font=ctk.CTkFont(size=12)
        )
        self.label.grid(row=0, column=0, pady=(0, 5), sticky="w")

        # Text box frame
        text_frame = ctk.CTkFrame(self, fg_color="transparent")
        text_frame.grid(row=1, column=0, sticky="ew")
        text_frame.grid_columnconfigure(0, weight=1)

        # Text box
        self.textbox = ctk.CTkTextbox(
            text_frame,
            wrap="word",
            height=self.height,
            font=ctk.CTkFont(size=11)
        )
        self.textbox.grid(row=0, column=0, sticky="ew")

        # Buttons frame
        buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        buttons_frame.grid(row=2, column=0, pady=(10, 0), sticky="ew")

        # Template button
        self.template_button = ctk.CTkButton(
            buttons_frame,
            text="Шаблоны",
            command=self._show_templates,
            width=80,
            height=28,
            font=ctk.CTkFont(size=10)
        )
        self.template_button.grid(row=0, column=0, padx=(0, 5))

        # Clear button
        self.clear_button = ctk.CTkButton(
            buttons_frame,
            text="Очистить",
            command=self._clear_prompt,
            width=80,
            height=28,
            font=ctk.CTkFont(size=10),
            fg_color="transparent",
            border_width=2,
            text_color=("gray10", "#DCE4EE")
        )
        self.clear_button.grid(row=0, column=1, padx=(0, 5))

        # Insert placeholder button
        self.placeholder_button = ctk.CTkButton(
            buttons_frame,
            text="Плейсхолдеры",
            command=self._show_placeholders,
            width=100,
            height=28,
            font=ctk.CTkFont(size=10)
        )
        self.placeholder_button.grid(row=0, column=2, padx=(0, 5))

        # Validate button
        self.validate_button = ctk.CTkButton(
            buttons_frame,
            text="Проверить",
            command=self._validate_prompt,
            width=80,
            height=28,
            font=ctk.CTkFont(size=10),
            fg_color=("gray75", "gray30")
        )
        self.validate_button.grid(row=0, column=3)

        # Status label
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="gray60"
        )
        self.status_label.grid(row=3, column=0, pady=(5, 0), sticky="w")

    def _bind_events(self):
        """Bind text box events."""
        self.textbox.bind("<KeyRelease>", self._on_text_change)
        self.textbox.bind("<FocusIn>", lambda e: self._clear_status())
        self.textbox.bind("<FocusOut>", lambda e: self._validate_prompt())

    def _on_text_change(self, event=None):
        """Handle text change event."""
        if self.command:
            prompt = self.get_prompt()
            self.command(prompt)

    def _show_templates(self):
        """Show template selection dialog."""
        # Create template dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Выберите шаблон промпта")
        dialog.geometry("400x300")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_rooty() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        # Template list
        template_frame = ctk.CTkScrollableFrame(dialog)
        template_frame.pack(fill="both", expand=True, padx=20, pady=20)

        def select_template(template_key):
            template = self.TEMPLATES[template_key]
            self.set_prompt(template["prompt"])
            dialog.destroy()

        row = 0
        for key, template in self.TEMPLATES.items():
            btn = ctk.CTkButton(
                template_frame,
                text=template["name"],
                command=lambda k=key: select_template(k),
                anchor="w",
                height=35
            )
            btn.grid(row=row, column=0, pady=2, sticky="ew")
            row += 1

        # Close button
        close_btn = ctk.CTkButton(
            dialog,
            text="Отмена",
            command=dialog.destroy
        )
        close_btn.pack(pady=(0, 20))

    def _show_placeholders(self):
        """Show placeholder insertion dialog."""
        # Create placeholder dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Вставьте плейсхолдер")
        dialog.geometry("350x250")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_rootx() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_rooty() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        # Placeholder list
        placeholder_frame = ctk.CTkFrame(dialog)
        placeholder_frame.pack(fill="both", expand=True, padx=20, pady=20)

        def insert_placeholder(placeholder):
            current_text = self.get_prompt()
            cursor_pos = self.textbox.index("insert")

            # Insert placeholder at cursor position
            self.textbox.insert(cursor_pos, placeholder)
            dialog.destroy()

        row = 0
        for placeholder, description in self.PLACEHOLDERS.items():
            frame = ctk.CTkFrame(placeholder_frame, fg_color="transparent")
            frame.grid(row=row, column=0, pady=5, sticky="ew")
            frame.grid_columnconfigure(1, weight=1)

            # Placeholder button
            btn = ctk.CTkButton(
                frame,
                text=placeholder,
                command=lambda p=placeholder: insert_placeholder(p),
                width=120,
                height=30,
                font=ctk.CTkFont(size=10)
            )
            btn.grid(row=0, column=0, padx=(0, 10))

            # Description label
            desc_label = ctk.CTkLabel(
                frame,
                text=description,
                font=ctk.CTkFont(size=10),
                anchor="w"
            )
            desc_label.grid(row=0, column=1, sticky="w")

            row += 1

        # Close button
        close_btn = ctk.CTkButton(
            dialog,
            text="Отмена",
            command=dialog.destroy
        )
        close_btn.pack(pady=(0, 20))

    def _clear_prompt(self):
        """Clear the prompt text."""
        self.textbox.delete("0.0", "end")
        self._clear_status()

    def _validate_prompt(self):
        """Validate the current prompt."""
        prompt = self.get_prompt().strip()

        if not prompt:
            self._set_status("Промпт пуст", "orange")
            return False

        # Check for required placeholders
        has_target_lang = "{target_language}" in prompt

        if not has_target_lang:
            self._set_status("Рекомендуется использовать {target_language}", "orange")
            return True

        # Check length
        if len(prompt) > 1000:
            self._set_status("Промпт слишком длинный (>1000 символов)", "red")
            return False

        self._set_status("Промпт корректен", "green")
        return True

    def _set_status(self, message: str, color: str):
        """Set status message with color.

        Args:
            message: Status message
            color: Color name ('green', 'red', 'orange', 'gray60')
        """
        color_map = {
            "green": ("#00AA00", "#00FF00"),
            "red": ("#AA0000", "#FF0000"),
            "orange": ("#AA5500", "#FF8800"),
            "gray60": ("gray60", "gray40")
        }

        self.status_label.configure(
            text=message,
            text_color=color_map.get(color, "gray60")
        )

    def _clear_status(self):
        """Clear status message."""
        self.status_label.configure(text="", text_color="gray60")

    def get_prompt(self) -> str:
        """Get the current prompt text.

        Returns:
            str: Current prompt
        """
        return self.textbox.get("0.0", "end").strip()

    def set_prompt(self, prompt: str):
        """Set the prompt text.

        Args:
            prompt: Prompt text to set
        """
        self.textbox.delete("0.0", "end")
        self.textbox.insert("0.0", prompt)
        self._validate_prompt()

    def insert_template(self, template_key: str):
        """Insert a template by key.

        Args:
            template_key: Template key from TEMPLATES
        """
        if template_key in self.TEMPLATES:
            template = self.TEMPLATES[template_key]
            self.set_prompt(template["prompt"])

    def get_available_templates(self) -> Dict[str, Dict]:
        """Get available prompt templates.

        Returns:
            Dict[str, Dict]: Template key -> template data mapping
        """
        return self.TEMPLATES.copy()

    def set_enabled(self, enabled: bool):
        """Enable or disable the component.

        Args:
            enabled: Whether the component should be enabled
        """
        state = "normal" if enabled else "disabled"
        self.textbox.configure(state=state)
        self.template_button.configure(state=state)
        self.clear_button.configure(state=state)
        self.placeholder_button.configure(state=state)
        self.validate_button.configure(state=state)

        if enabled:
            self.label.configure(text_color=("gray10", "gray90"))
        else:
            self.label.configure(text_color=("gray60", "gray40"))


if __name__ == "__main__":
    # Test the component
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Prompt Editor Test")
    root.geometry("500x400")

    def on_prompt_change(prompt):
        print(f"Prompt changed: {prompt[:50]}...")

    editor = PromptEditor(
        root,
        label_text="System Prompt:",
        command=on_prompt_change
    )
    editor.grid(row=0, column=0, padx=20, pady=20, sticky="ew")

    # Test setting prompt
    editor.set_prompt("Translate the following text to {target_language}:")

    root.mainloop()