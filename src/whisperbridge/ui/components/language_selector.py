"""
Language selector component for WhisperBridge.

This module provides a reusable language selection widget with
predefined language options and validation.
"""

import customtkinter as ctk
from typing import Optional, List, Dict, Callable


class LanguageSelector(ctk.CTkFrame):
    """Language selection component with predefined options."""

    # Language mappings (code -> display name)
    LANGUAGES = {
        "auto": "Автоопределение",
        "en": "English",
        "ru": "Русский",
        "uk": "Українська",
        "de": "Deutsch",
        "fr": "Français",
        "es": "Español",
        "it": "Italiano",
        "ja": "日本語",
        "zh": "中文",
        "ko": "한국어",
        "pt": "Português",
        "ar": "العربية",
        "hi": "हिन्दी",
        "tr": "Türkçe",
        "pl": "Polski",
        "nl": "Nederlands",
        "sv": "Svenska",
        "da": "Dansk",
        "no": "Norsk",
        "fi": "Suomi",
        "cs": "Čeština",
        "sk": "Slovenčina",
        "hu": "Magyar",
        "ro": "Română",
        "bg": "Български",
        "hr": "Hrvatski",
        "sl": "Slovenščina",
        "et": "Eesti",
        "lv": "Latviešu",
        "lt": "Lietuvių",
        "el": "Ελληνικά",
        "he": "עברית",
        "th": "ไทย",
        "vi": "Tiếng Việt",
        "id": "Bahasa Indonesia",
        "ms": "Bahasa Melayu",
        "tl": "Filipino",
        "sw": "Kiswahili"
    }

    def __init__(self, master, label_text: str = "Выберите язык",
                 include_auto: bool = True, width: int = 200,
                 command: Optional[Callable] = None, **kwargs):
        """Initialize the language selector.

        Args:
            master: Parent widget
            label_text: Label text for the selector
            include_auto: Whether to include auto-detection option
            width: Width of the combobox
            command: Callback function when selection changes
            **kwargs: Additional arguments for CTkFrame
        """
        super().__init__(master, **kwargs)

        self.label_text = label_text
        self.include_auto = include_auto
        self.command = command

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)

        # Create widgets
        self._create_widgets(width)

    def _create_widgets(self, width: int):
        """Create the component widgets."""
        # Label
        self.label = ctk.CTkLabel(
            self,
            text=self.label_text,
            font=ctk.CTkFont(size=12)
        )
        self.label.grid(row=0, column=0, pady=(0, 5), sticky="w")

        # Combobox
        values = self._get_language_values()
        self.combobox = ctk.CTkComboBox(
            self,
            values=values,
            width=width,
            command=self._on_selection_change
        )
        self.combobox.grid(row=1, column=0, sticky="ew")

    def _get_language_values(self) -> List[str]:
        """Get the list of language values for the combobox."""
        languages = self.LANGUAGES.copy()

        if not self.include_auto:
            languages.pop("auto", None)

        # Sort by display name, but keep "auto" first if included
        sorted_items = []
        if self.include_auto and "auto" in languages:
            sorted_items.append(languages["auto"])

        # Sort remaining languages by display name
        other_langs = {k: v for k, v in languages.items() if k != "auto"}
        sorted_others = sorted(other_langs.items(), key=lambda x: x[1])

        sorted_items.extend([display for _, display in sorted_others])

        return sorted_items

    def _on_selection_change(self, selection: str):
        """Handle combobox selection change."""
        if self.command:
            # Convert display name back to language code
            lang_code = self._get_code_from_display(selection)
            self.command(lang_code)

    def _get_code_from_display(self, display_name: str) -> str:
        """Get language code from display name.

        Args:
            display_name: Display name of the language

        Returns:
            str: Language code
        """
        for code, display in self.LANGUAGES.items():
            if display == display_name:
                return code
        return ""

    def get_selected_language(self) -> str:
        """Get the currently selected language code.

        Returns:
            str: Selected language code
        """
        display_name = self.combobox.get()
        return self._get_code_from_display(display_name)

    def set_selected_language(self, language_code: str):
        """Set the selected language by code.

        Args:
            language_code: Language code to select
        """
        if language_code in self.LANGUAGES:
            display_name = self.LANGUAGES[language_code]
            self.combobox.set(display_name)
        else:
            print(f"Warning: Unknown language code '{language_code}'")

    def get_available_languages(self) -> Dict[str, str]:
        """Get dictionary of available languages.

        Returns:
            Dict[str, str]: Language code -> display name mapping
        """
        return self.LANGUAGES.copy()

    def set_enabled(self, enabled: bool):
        """Enable or disable the component.

        Args:
            enabled: Whether the component should be enabled
        """
        state = "normal" if enabled else "disabled"
        self.combobox.configure(state=state)

        # Update label color for visual feedback
        if enabled:
            self.label.configure(text_color=("gray10", "gray90"))
        else:
            self.label.configure(text_color=("gray60", "gray40"))

    def reset_to_default(self, default_language: str = "auto"):
        """Reset selection to default language.

        Args:
            default_language: Default language code
        """
        if default_language in self.LANGUAGES or (not self.include_auto and default_language != "auto"):
            self.set_selected_language(default_language)
        else:
            # Fallback to first available option
            values = self._get_language_values()
            if values:
                self.combobox.set(values[0])


if __name__ == "__main__":
    # Test the component
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Language Selector Test")
    root.geometry("300x150")

    def on_language_change(lang_code):
        print(f"Selected language: {lang_code}")

    selector = LanguageSelector(
        root,
        label_text="Source Language:",
        include_auto=True,
        command=on_language_change
    )
    selector.grid(row=0, column=0, padx=20, pady=20, sticky="ew")

    # Test setting language
    selector.set_selected_language("ru")

    root.mainloop()