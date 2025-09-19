"""
ThemeService extracted from QtApp._get_theme_from_settings/_apply_theme/_apply_dark_theme/_apply_light_theme. Centralizes theme management.
"""

from typing import Optional

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt

from ..services.config_service import config_service as default_config_service, SettingsObserver
from loguru import logger as default_logger


class ThemeService(SettingsObserver):
    def __init__(self, qt_app: Optional[QApplication] = None, config_service=None, logger=None):
        super().__init__()
        self.qt_app = qt_app or QApplication.instance()
        self.config_service = config_service or default_config_service
        self.logger = logger or default_logger
        self._current_theme = self.get_theme_from_settings()
        self.config_service.add_observer(self)
        self.apply_theme()

    def get_theme_from_settings(self) -> str:
        """Get theme from settings."""
        # Get theme from config service to ensure we have the latest saved value
        current_theme = self.config_service.get_setting("theme", use_cache=False)
        self.logger.debug(f"Retrieved theme from config service: '{current_theme}' (type: {type(current_theme)})")
        theme_map = {
            "dark": "dark",
            "light": "light",
            "auto": "system"
        }
        mapped_theme = theme_map.get(current_theme.lower() if current_theme else None, "light")
        self.logger.debug(f"Mapped theme: '{mapped_theme}'")
        return mapped_theme

    def apply_theme(self, theme: Optional[str] = None) -> None:
        """Apply the current theme to the application."""
        if theme is None:
            theme = self.get_theme_from_settings()
        if theme == "dark":
            self._apply_dark_theme()
        elif theme == "light":
            self._apply_light_theme()
        else:
            # System theme - for now default to dark
            self._apply_dark_theme()
        self._current_theme = theme

    def _apply_dark_theme(self) -> None:
        """Apply dark theme."""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)

        self.qt_app.setPalette(palette)

    def _apply_light_theme(self) -> None:
        """Apply light theme."""
        self.qt_app.setPalette(self.qt_app.style().standardPalette())

    def on_settings_changed(self, key: str, old_value, new_value):
        """Called when a setting value changes."""
        if key == "theme":
            self.logger.debug(f"Theme setting changed from {old_value} to {new_value}")
            new_theme = self.get_theme_from_settings()
            if new_theme != self._current_theme:
                self._current_theme = new_theme
                self.apply_theme(new_theme)

    def on_settings_saved(self, settings):
        """Called when settings are saved."""
        # Re-check and apply theme if changed
        new_theme = self.get_theme_from_settings()
        if new_theme != self._current_theme:
            self._current_theme = new_theme
            self.apply_theme(new_theme)

    def on_settings_loaded(self, settings):
        """Called when settings are loaded."""
        pass