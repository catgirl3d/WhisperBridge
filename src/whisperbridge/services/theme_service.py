"""
ThemeService extracted from QtApp._get_theme_from_settings/_apply_theme/_apply_dark_theme/_apply_light_theme. Centralizes theme management.
"""

import os
from typing import Optional

from loguru import logger as default_logger
from PySide6.QtCore import Qt, QObject, Signal, QThread, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from ..services.config_service import (
    SettingsObserver,
)
from ..services.config_service import config_service as default_config_service


class ThemeService(QObject, SettingsObserver):
    # Emitted after theme is applied and internal state is updated
    theme_changed = Signal(str)
    def __init__(
        self, qt_app: Optional[QApplication] = None, config_service=None, logger=None
    ):
        # Initialize QObject explicitly due to multiple inheritance
        QObject.__init__(self)
        # SettingsObserver may be a plain class, but call for clarity
        SettingsObserver.__init__(self)

        self.qt_app = qt_app or QApplication.instance()
        self.config_service = config_service or default_config_service
        self.logger = logger or default_logger

        # Initialize current theme from settings and subscribe for changes
        self._current_theme = self.get_theme_from_settings()
        self.config_service.add_observer(self)

        # Apply theme on startup
        self.apply_theme()

    def get_theme_from_settings(self) -> str:
        """Get theme from settings."""
        # Get theme from config service to ensure we have the latest saved value
        current_theme = self.config_service.get_setting("theme", use_cache=False)
        self.logger.debug(
            f"Retrieved theme from config service: '{current_theme}' (type: {type(current_theme)})"
        )
        theme_map = {"dark": "dark", "light": "light", "auto": "system"}
        mapped_theme = theme_map.get(
            current_theme.lower() if current_theme else None, "light"
        )
        self.logger.debug(f"Mapped theme: '{mapped_theme}'")
        return mapped_theme

    def apply_theme(self, theme: Optional[str] = None) -> None:
        """Apply the current theme to the application; guarantees execution on Qt main thread."""
        if theme is None:
            theme = self.get_theme_from_settings()
        self._apply_theme_safe(theme)

    def _apply_theme_safe(self, theme: str) -> None:
        """Ensure theme application runs on the Qt main thread."""
        app = QApplication.instance()
        if app is not None and QThread.currentThread() != app.thread():
            # Defer to main thread
            QTimer.singleShot(0, lambda t=theme: self._apply_theme_impl(t))
            return
        self._apply_theme_impl(theme)

    def _apply_theme_impl(self, theme: str) -> None:
        """Apply theme palette and notify listeners (executes in main thread)."""
        if theme == "dark":
            self._apply_dark_theme()
        elif theme == "light":
            self._apply_light_theme()
        else:
            # System theme - for now default to dark
            self._apply_dark_theme()

        # Load CSS styles from file
        self._load_stylesheet()

        self._current_theme = theme

        # Notify listeners that theme has changed
        try:
            self.theme_changed.emit(theme)
        except Exception:
            # If used outside of a Qt signal context, avoid crashing
            pass

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

    def _load_stylesheet(self) -> None:
        """Load and apply CSS stylesheet from file."""
        try:
            # Path to the assets directory
            assets_path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), "..", "assets"
            ))
            # Path for URL needs forward slashes
            assets_url_path = assets_path.replace(os.sep, '/')

            # Path to the stylesheet file
            style_path = os.path.join(assets_path, "style.qss")

            if os.path.exists(style_path):
                with open(style_path, 'r', encoding='utf-8') as f:
                    stylesheet_template = f.read()

                # Replace the placeholder with the actual path
                stylesheet = stylesheet_template.replace("{assets_path}", assets_url_path)

                self.qt_app.setStyleSheet(stylesheet)
                self.logger.debug(f"Loaded stylesheet from: {style_path}")
            else:
                self.logger.warning(f"Stylesheet file not found: {style_path}")
        except Exception as e:
            self.logger.error(f"Failed to load stylesheet: {e}")

    def on_settings_changed(self, key: str, old_value, new_value):
        """Called when a setting value changes."""
        if key == "theme":
            self.logger.debug(f"Theme setting changed from {old_value} to {new_value}")
            new_theme = self.get_theme_from_settings()
            if new_theme != self._current_theme:
                self.apply_theme(new_theme)

    def on_settings_saved(self, settings):
        """Called when settings are saved."""
        # Re-check and apply theme if changed
        new_theme = self.get_theme_from_settings()
        if new_theme != self._current_theme:
            self.apply_theme(new_theme)

    def on_settings_loaded(self, settings):
        """Called when settings are loaded."""
        pass
