"""
Main settings window for WhisperBridge application.

This module provides the main configuration interface with fields for
API keys, language selection, hotkeys, and system prompts.
"""

import customtkinter as ctk
from typing import Optional, Callable
import tkinter.messagebox as messagebox
from ..core.config import settings


class MainWindow(ctk.CTk):
    """Main settings window for WhisperBridge."""

    def __init__(self, on_save_callback: Optional[Callable] = None):
        """Initialize the main window.

        Args:
            on_save_callback: Callback function called when settings are saved
        """
        super().__init__()

        self.on_save_callback = on_save_callback
        self.title("WhisperBridge - Настройки")
        self.geometry("600x700")
        self.resizable(False, False)

        # Threading communication
        self._test_result = None
        self._test_error_msg = ""

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Create main frame
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Initialize UI components
        self._create_widgets()
        self._load_current_settings()

        # Center window on screen
        self._center_window()

        # Don't start periodic check - we'll check only when needed

    def _create_widgets(self):
        """Create all UI widgets."""
        # Title
        title_label = ctk.CTkLabel(
            self.main_frame,
            text="Настройки WhisperBridge",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.grid(row=0, column=0, pady=(20, 30))

        # API Key section
        self._create_api_section()

        # Language section
        self._create_language_section()

        # Hotkey section
        self._create_hotkey_section()

        # Prompt section
        self._create_prompt_section()

        # Buttons section
        self._create_buttons_section()

    def _create_api_section(self):
        """Create API key input section."""
        api_frame = ctk.CTkFrame(self.main_frame)
        api_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")
        api_frame.grid_columnconfigure(1, weight=1)

        # API Key label
        api_label = ctk.CTkLabel(api_frame, text="OpenAI API Key:")
        api_label.grid(row=0, column=0, padx=(20, 10), pady=(15, 5), sticky="w")

        # API Key entry
        self.api_key_entry = ctk.CTkEntry(
            api_frame,
            placeholder_text="sk-...",
            show="•",
            width=300
        )
        self.api_key_entry.grid(row=0, column=1, padx=(0, 20), pady=(15, 5), sticky="ew")

        # Model selection label
        model_label = ctk.CTkLabel(api_frame, text="Модель:")
        model_label.grid(row=1, column=0, padx=(20, 10), pady=(5, 15), sticky="w")

        # Model selection dropdown
        self.model_combo = ctk.CTkComboBox(
            api_frame,
            values=["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-4o-mini"],
            width=200
        )
        self.model_combo.grid(row=1, column=1, padx=(0, 20), pady=(5, 15), sticky="w")

    def _create_language_section(self):
        """Create language selection section."""
        lang_frame = ctk.CTkFrame(self.main_frame)
        lang_frame.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="ew")
        lang_frame.grid_columnconfigure((0, 1), weight=1)

        # Source language
        source_label = ctk.CTkLabel(lang_frame, text="Язык оригинала:")
        source_label.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")

        self.source_lang_combo = ctk.CTkComboBox(
            lang_frame,
            values=["auto", "en", "ru", "uk", "de", "fr", "es", "it", "ja", "zh"],
            width=150
        )
        self.source_lang_combo.grid(row=1, column=0, padx=20, pady=(0, 15))

        # Target language
        target_label = ctk.CTkLabel(lang_frame, text="Язык перевода:")
        target_label.grid(row=0, column=1, padx=20, pady=(15, 5), sticky="w")

        self.target_lang_combo = ctk.CTkComboBox(
            lang_frame,
            values=["ru", "en", "uk", "de", "fr", "es", "it", "ja", "zh"],
            width=150
        )
        self.target_lang_combo.grid(row=1, column=1, padx=20, pady=(0, 15))

    def _create_hotkey_section(self):
        """Create hotkey configuration section."""
        hotkey_frame = ctk.CTkFrame(self.main_frame)
        hotkey_frame.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")
        hotkey_frame.grid_columnconfigure(1, weight=1)

        # Hotkey label
        hotkey_label = ctk.CTkLabel(hotkey_frame, text="Горячая клавиша:")
        hotkey_label.grid(row=0, column=0, padx=(20, 10), pady=15, sticky="w")

        # Hotkey entry
        self.hotkey_entry = ctk.CTkEntry(
            hotkey_frame,
            placeholder_text="ctrl+shift+t",
            width=200
        )
        self.hotkey_entry.grid(row=0, column=1, padx=(0, 20), pady=15, sticky="ew")

        # Hotkey hint
        hint_label = ctk.CTkLabel(
            hotkey_frame,
            text="Формат: ctrl+shift+t (модификаторы + клавиша)",
            font=ctk.CTkFont(size=10)
        )
        hint_label.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 15), sticky="w")

    def _create_prompt_section(self):
        """Create system prompt editor section."""
        prompt_frame = ctk.CTkFrame(self.main_frame)
        prompt_frame.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="ew")
        prompt_frame.grid_columnconfigure(0, weight=1)
        prompt_frame.grid_rowconfigure(1, weight=1)

        # Prompt label
        prompt_label = ctk.CTkLabel(prompt_frame, text="Системный промпт:")
        prompt_label.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")

        # Prompt text box
        self.prompt_textbox = ctk.CTkTextbox(
            prompt_frame,
            wrap="word",
            height=100
        )
        self.prompt_textbox.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="ew")

    def _create_buttons_section(self):
        """Create action buttons section."""
        buttons_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        buttons_frame.grid(row=5, column=0, padx=20, pady=(0, 20), sticky="ew")

        # Test API button
        self.test_api_button = ctk.CTkButton(
            buttons_frame,
            text="Тест API",
            command=self._on_test_api,
            fg_color="transparent",
            border_width=2,
            text_color=("gray10", "#DCE4EE")
        )
        self.test_api_button.grid(row=0, column=0, padx=(0, 10), pady=10)

        # Cancel button
        self.cancel_button = ctk.CTkButton(
            buttons_frame,
            text="Отмена",
            command=self._on_cancel,
            fg_color="transparent",
            border_width=2,
            text_color=("gray10", "#DCE4EE")
        )
        self.cancel_button.grid(row=0, column=1, padx=10, pady=10)

        # Save button
        self.save_button = ctk.CTkButton(
            buttons_frame,
            text="Сохранить",
            command=self._on_save,
            fg_color=("gray75", "gray30")
        )
        self.save_button.grid(row=0, column=2, padx=(10, 0), pady=10)

    def _load_current_settings(self):
        """Load current settings into UI components."""
        # Load API key (masked)
        if hasattr(settings, 'openai_api_key') and settings.openai_api_key:
            self.api_key_entry.insert(0, settings.openai_api_key)

        # Load model
        self.model_combo.set(settings.model)

        # Load languages
        self.source_lang_combo.set(settings.source_language)
        self.target_lang_combo.set(settings.target_language)

        # Load hotkey
        self.hotkey_entry.insert(0, settings.translate_hotkey)

        # Load default prompt
        default_prompt = "Translate the following text to {target_language}:"
        self.prompt_textbox.insert("0.0", default_prompt)

    def _center_window(self):
        """Center the window on screen."""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _validate_input(self) -> bool:
        """Validate user input.

        Returns:
            bool: True if input is valid, False otherwise
        """
        # Validate API key
        api_key = self.api_key_entry.get().strip()
        if not api_key:
            messagebox.showerror("Ошибка", "Введите API ключ OpenAI")
            return False

        if not api_key.startswith("sk-"):
            messagebox.showerror("Ошибка", "API ключ должен начинаться с 'sk-'")
            return False

        # Validate hotkey
        hotkey = self.hotkey_entry.get().strip()
        if not hotkey:
            messagebox.showerror("Ошибка", "Введите горячую клавишу")
            return False

        # Basic hotkey format validation
        if "+" not in hotkey:
            messagebox.showerror("Ошибка", "Формат горячей клавиши: модификатор+клавиша")
            return False

        return True

    def _on_save(self):
        """Handle save button click."""
        if not self._validate_input():
            return

        try:
            # Get values from UI
            api_key = self.api_key_entry.get().strip()
            model = self.model_combo.get()
            source_lang = self.source_lang_combo.get()
            target_lang = self.target_lang_combo.get()
            hotkey = self.hotkey_entry.get().strip()
            prompt = self.prompt_textbox.get("1.0", "end-1c").strip()

            # Update settings
            from ..core.config import settings, save_settings
            settings.openai_api_key = api_key if api_key else None
            settings.model = model
            settings.source_language = source_lang
            settings.target_language = target_lang
            settings.translate_hotkey = hotkey
            settings.system_prompt = prompt

            # Save settings to file and keyring
            if save_settings(settings):
                messagebox.showinfo("Успех", "Настройки сохранены успешно!")

                if self.on_save_callback:
                    self.on_save_callback()

                self.destroy()
            else:
                messagebox.showerror("Ошибка", "Не удалось сохранить настройки в файл")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки: {str(e)}")

    def _on_cancel(self):
        """Handle cancel button click."""
        self.destroy()

    def _on_test_api(self):
        """Handle test API button click."""
        if not self._validate_input():
            return

        # Show testing message
        self.test_api_button.configure(state="disabled", text="Тестирование...")

        try:
            # Get API key and model from input fields
            api_key = self.api_key_entry.get().strip()
            model = self.model_combo.get()

            # Reset test results
            self._test_result = None
            self._test_error_msg = ""

            # Test the API key by making a simple request
            import threading
            test_thread = threading.Thread(target=self._test_api_async, args=(api_key, model))
            test_thread.daemon = True
            test_thread.start()

            # Start checking for results periodically
            self._start_result_checking()

        except Exception as e:
            self._show_test_result(False, str(e))

    def _test_api_async(self, api_key: str, model: str):
        """Test API key asynchronously."""
        try:
            import openai

            # Create a temporary client for testing
            client = openai.OpenAI(api_key=api_key, timeout=10)

            # Make a simple test request
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )

            # If we get here, the API key is valid
            self._test_result = True
            self._test_error_msg = ""

        except openai.AuthenticationError:
            self._test_result = False
            self._test_error_msg = "Неверный API ключ"
        except openai.RateLimitError:
            self._test_result = False
            self._test_error_msg = "Превышен лимит запросов"
        except openai.APIError as e:
            self._test_result = False
            self._test_error_msg = f"Ошибка API: {str(e)}"
        except Exception as e:
            self._test_result = False
            self._test_error_msg = f"Ошибка подключения: {str(e)}"


    def _start_result_checking(self):
        """Start periodic checking for test results."""
        self._check_count = 0
        self._do_result_check()

    def _do_result_check(self):
        """Check for test results periodically."""
        self._check_count += 1

        try:
            if not self.winfo_exists():
                return  # Window destroyed

            if self._test_result is not None:
                success = self._test_result
                error_msg = self._test_error_msg
                self._test_result = None
                self._test_error_msg = ""
                self._show_test_result(success, error_msg)
                return  # Done checking

            # Continue checking if under timeout (30 seconds = 300 checks * 100ms)
            if self._check_count < 300:
                self.after(100, self._do_result_check)
            else:
                # Timeout
                self._show_test_result(False, "Таймаут ожидания результата")

        except:
            pass  # Window might be destroyed

    def _show_test_result(self, success: bool, error_msg: str = ""):
        """Show API test result."""
        self.test_api_button.configure(state="normal", text="Тест API")

        if success:
            messagebox.showinfo("Успех", "API ключ работает корректно!")
        else:
            messagebox.showerror("Ошибка", f"Ошибка тестирования API: {error_msg}")


if __name__ == "__main__":
    # For testing the window independently
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = MainWindow()
    app.mainloop()