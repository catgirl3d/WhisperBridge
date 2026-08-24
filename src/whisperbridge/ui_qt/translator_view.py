"""Translator widget tree and its presentation-only state transitions."""

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSpacerItem,
)

from ..core.config import TRANSLATOR_FONT_SIZE_DEFAULT
from .styled_overlay_base import WINDOW_CONTROLS_ICONS
from .widget_factory import apply_custom_dropdown_style as _apply_custom_dropdown_style
from .widget_factory import create_widget as _create_widget
from .widget_factory import make_icon_from_spec
from .widgets.placeholder_text_edit import PlaceholderTextEdit

_ASSETS_BASE = Path(__file__).parent.parent / "assets"

LAYOUT_CONFIG = {
    "info_row_margins": (0, 3, 0, 0),
    "info_row_spacer_width": 10,
    "info_row_spacer_height": 10,
    "footer_margins": (0, 0, 0, 0),
}
ICONS_CONFIG = {
    "utility_icons": {
        "eraser": {"icon": "fa5s.eraser", "color": "black"},
        "copy": {"icon": "fa5.copy", "color": "black"},
        "check_success": {"icon": "fa5s.check", "color": "green"},
        "edit_styles": {"asset": "pen-to-square-solid-full.svg"},
    },
    "window_controls": WINDOW_CONTROLS_ICONS,
    "translate_disabled": {
        "compact": {"icon": "fa5s.lock", "color": "white"},
        "full": {"icon": "fa5s.lock", "color": "#757575"},
    },
    "reader": {
        "compact": {"asset": "book_white.png"},
        "full": {"asset": "book_black.png"},
    },
    "translate": {"all": {"asset": "translation-icon.png"}},
    "swap": {"asset": "arrows-exchange.png"},
}
DEFAULT_DISABLED_TOOLTIP = "API key is not configured. Open Settings to add a key."
LANGUAGE_WIDGET_CONFIG = {
    "source_combo": {"size": (125, 28), "icon_size": (28, 28), "object_name": "sourceLanguageCombo"},
    "target_combo": {"size": (125, 28), "icon_size": (28, 28), "object_name": "targetLanguageCombo"},
    "swap_button": {"size": (35, 28), "icon_size": (20, 24)},
}
FOOTER_WIDGET_CONFIG = {
    "status_label": {"object_name": "statusLabel"},
    "provider_badge": {"object_name": "providerBadge", "text": ""},
    "close_button": {
        "size": (86, 28), "icon_size": (16, 16), "object_name": "closeButton", "text": "Close",
        "icons": {"normal": ICONS_CONFIG["window_controls"]["close"], "hover": ICONS_CONFIG["window_controls"]["close_hover"]},
    },
}
MAIN_BUTTONS_CONFIG = {
    "translate": {"text": "  Translate", "object_name": "translateButton"},
    "reader": {"text": "", "object_name": "readerButton", "utility": False, "enabled": False},
}
UTILITY_BUTTONS_CONFIG = {
    "clear": {"text": "", "tooltip": "Clear text", "utility": True, "icon_key": "eraser"},
    "copy": {"text": "", "tooltip": "Copy text", "utility": True, "icon_key": "copy"},
}
BUTTON_STYLES = {
    "translate_compact": {"text": "", "size": (24, 24), "icon_size": (12, 12), "icon_spec": ICONS_CONFIG["translate"]["all"]},
    "translate_full": {"size": (120, 28), "icon_size": (14, 14), "icon_spec": ICONS_CONFIG["translate"]["all"]},
    "reader_compact": {"text": "", "size": (24, 24), "icon_size": (17, 17), "icon_spec": ICONS_CONFIG["reader"]["compact"]},
    "reader_full": {"text": "", "size": (40, 28), "icon_size": (19, 19), "tooltip": "Open text in reader mode for comfortable reading", "icon_spec": ICONS_CONFIG["reader"]["full"]},
    "default_compact": {"text": "", "size": (24, 24), "icon_size": (15, 15)},
    "default_full": {"text": "", "size": (40, 28), "icon_size": (16, 16)},
}
INFO_WIDGET_CONFIG = {
    "mode_combo": {"size": (95, 28), "object_name": "modeCombo"},
    "style_combo": {"size": (95, 28), "object_name": "styleCombo"},
    "detected_lang_label": {"width": 120},
    "mode_label": {"text": "Mode:"},
    "auto_swap_checkbox": {"text": "Auto-translate EN ↔ RU", "tooltip": "If enabled, English will be translated to Russian, and Russian to English"},
}
TEXT_EDIT_CONFIG = {"object_name": "textEdit"}
LABEL_CONFIG = {
    "bold": {"object_name": "boldLabel"},
    "original": {"text": "Original:", "object_name": "boldLabel"},
    "translation": {"text": "Translation:", "object_name": "boldLabel"},
}


def _make_icon(spec):
    return make_icon_from_spec(spec, _ASSETS_BASE)


def _refresh_widget_style(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _apply_status_style(status_label, style_type):
    if status_label:
        status_label.setProperty("status", style_type)
        _refresh_widget_style(status_label)


def _apply_button_style(button, compact):
    mode = "compact" if compact else "full"
    role = (button.property("role") or button.objectName() or "").strip()
    role_configs = {
        "translateButton": {"compact": BUTTON_STYLES["translate_compact"], "full": BUTTON_STYLES["translate_full"]},
        "readerButton": {"compact": BUTTON_STYLES["reader_compact"], "full": BUTTON_STYLES["reader_full"]},
    }
    config = (role_configs.get(role, {}).get(mode) or BUTTON_STYLES[f"default_{mode}"]).copy()
    if "text" in config:
        button.setText(config["text"])
    if config.get("tooltip"):
        button.setToolTip(config["tooltip"])
    button.setFixedSize(*config["size"])
    button.setIconSize(QSize(*config["icon_size"]))
    if "icon_spec" in config:
        button.setIcon(_make_icon(config["icon_spec"]))
    button.setProperty("mode", mode)
    if button.property("utility") is None:
        button.setProperty("utility", False)
    _refresh_widget_style(button)


class PanelWidget(QFrame):
    """Text panel that switches between side and bottom action presentation."""

    LAYOUT_CONFIG = {
        "main_vertical_spacing": 4,
        "main_vertical_margins": (0, 0, 0, 0),
        "top_horizontal_margins": (0, 0, 0, 0),
        "side_panel_expanded_width": 28,
        "side_panel_collapsed_width": 1,
        "side_panel_spacing": 3,
        "side_panel_margins": (0, 0, 0, 0),
        "btn_row_margins": (0, 0, 0, 0),
    }

    def __init__(self, text_edit: QTextEdit, buttons: List[QPushButton], parent=None):
        super().__init__(parent)
        self.text_edit = text_edit
        self.buttons = buttons
        self.side_panel: Optional[QFrame] = None
        self.btn_row: Optional[QHBoxLayout] = None
        self._autohide = False
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.installEventFilter(self)
        self._main_v = QVBoxLayout(self)
        self._main_v.setContentsMargins(*self.LAYOUT_CONFIG["main_vertical_margins"])
        self._main_v.setSpacing(self.LAYOUT_CONFIG["main_vertical_spacing"])
        self._top_h = QHBoxLayout()
        self._top_h.setContentsMargins(*self.LAYOUT_CONFIG["top_horizontal_margins"])
        self._top_h.addWidget(self.text_edit, 1)
        self._main_v.addLayout(self._top_h, 1)

    def _ensure_side_panel(self):
        if self.side_panel is not None:
            return
        panel = QFrame(self)
        panel.setFrameStyle(QFrame.Shape.NoFrame)
        panel.setFixedWidth(self.LAYOUT_CONFIG["side_panel_expanded_width"])
        layout = QVBoxLayout(panel)
        layout.setSpacing(self.LAYOUT_CONFIG["side_panel_spacing"])
        layout.setContentsMargins(*self.LAYOUT_CONFIG["side_panel_margins"])
        layout.addStretch()
        layout.addStretch()
        panel.setMouseTracking(True)
        panel.installEventFilter(self)
        for button in self.buttons:
            layout.insertWidget(layout.count() - 1, button, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._top_h.addWidget(panel)
        self.side_panel = panel

    def _remove_side_panel(self):
        if self.side_panel is not None:
            for button in self.buttons:
                self.side_panel.layout().removeWidget(button)
            self._top_h.removeWidget(self.side_panel)
            self.side_panel.deleteLater()
            self.side_panel = None

    def _ensure_btn_row(self):
        if self.btn_row is None:
            row = QHBoxLayout()
            row.setContentsMargins(*self.LAYOUT_CONFIG["btn_row_margins"])
            row.addStretch(1)
            for button in self.buttons:
                row.addWidget(button)
            self._main_v.addLayout(row)
            self.btn_row = row

    def _remove_btn_row(self):
        if self.btn_row is not None:
            for button in self.buttons:
                self.btn_row.removeWidget(button)
            self._main_v.removeItem(self.btn_row)
            self.btn_row = None

    def configure(self, compact: bool, autohide: bool):
        self._autohide = autohide
        if compact:
            self._remove_btn_row()
            self._ensure_side_panel()
            self.side_panel.setFixedWidth(self.LAYOUT_CONFIG["side_panel_collapsed_width"] if autohide else self.LAYOUT_CONFIG["side_panel_expanded_width"])
            for button in self.buttons:
                button.setVisible(not autohide)
                _apply_button_style(button, True)
        else:
            self._remove_side_panel()
            self._ensure_btn_row()
            for button in self.buttons:
                button.setVisible(True)
                _apply_button_style(button, False)

    def eventFilter(self, obj, event):
        if self._autohide and self.side_panel and obj in (self, self.side_panel):
            if event.type() == QEvent.Type.Enter:
                self.side_panel.setFixedWidth(self.LAYOUT_CONFIG["side_panel_expanded_width"])
                for button in self.buttons:
                    button.setVisible(True)
            elif event.type() == QEvent.Type.Leave and not self.side_panel.underMouse() and not self.underMouse():
                self.side_panel.setFixedWidth(self.LAYOUT_CONFIG["side_panel_collapsed_width"])
                for button in self.buttons:
                    button.setVisible(False)
        return False


class TranslatorView(QWidget):
    """Owns the complete translator widget tree and presentation state."""

    def __init__(self, supported_languages, styles, source_language="en", target_language="en", compact=False, autohide=False, font_size=TRANSLATOR_FONT_SIZE_DEFAULT, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._styles = styles or []
        self._supported_languages = supported_languages
        self._create_widgets()
        self._populate_languages(source_language, target_language)
        self.refresh_styles(self._styles)
        self.configure(compact, autohide, font_size)

    def _create_widget(self, widget_type, key, widget_class, **kwargs):
        return _create_widget({"info": INFO_WIDGET_CONFIG, "language": LANGUAGE_WIDGET_CONFIG, "footer": FOOTER_WIDGET_CONFIG, "label": LABEL_CONFIG, "main_buttons": MAIN_BUTTONS_CONFIG, "utility_buttons": UTILITY_BUTTONS_CONFIG}, widget_type, key, widget_class, **kwargs)

    def _create_text_edit(self, placeholder):
        text_edit = PlaceholderTextEdit()
        text_edit.setReadOnly(False)
        text_edit.setAcceptRichText(False)
        text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        text_edit.setPlaceholderText(placeholder)
        text_edit.setObjectName(TEXT_EDIT_CONFIG["object_name"])
        return text_edit

    def _create_widgets(self):
        self.info_row = QFrame(self)
        self.info_row.setFrameStyle(QFrame.Shape.NoFrame)
        info_layout = QHBoxLayout(self.info_row)
        info_layout.setContentsMargins(*LAYOUT_CONFIG["info_row_margins"])
        self.mode_label, _ = self._create_widget("info", "mode_label", QLabel)
        info_layout.addWidget(self.mode_label)
        self.mode_combo, _ = self._create_widget("info", "mode_combo", QComboBox)
        self.mode_combo.addItems(["Translate", "Style"])
        _apply_custom_dropdown_style(self.mode_combo)
        info_layout.addWidget(self.mode_combo)
        self.style_combo, _ = self._create_widget("info", "style_combo", QComboBox)
        self.style_combo.setVisible(False)
        _apply_custom_dropdown_style(self.style_combo)
        info_layout.addWidget(self.style_combo)
        self.edit_styles_btn = QPushButton(self)
        self.edit_styles_btn.setObjectName("editStylesButton")
        self.edit_styles_btn.setFixedSize(28, 28)
        self.edit_styles_btn.setIcon(_make_icon(ICONS_CONFIG["utility_icons"]["edit_styles"]))
        self.edit_styles_btn.setIconSize(QSize(16, 16))
        self.edit_styles_btn.setToolTip("Edit Styles")
        self.edit_styles_btn.setVisible(False)
        info_layout.addWidget(self.edit_styles_btn)
        info_layout.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        self.detected_lang_label, _ = self._create_widget("info", "detected_lang_label", QLabel, text="Language: —")
        info_layout.addWidget(self.detected_lang_label)
        self.auto_swap_checkbox, _ = self._create_widget("info", "auto_swap_checkbox", QCheckBox)
        info_layout.addWidget(self.auto_swap_checkbox)

        self.language_row = QHBoxLayout()
        self.original_label, _ = self._create_widget("label", "original", QLabel)
        self.language_row.addWidget(self.original_label, alignment=Qt.AlignmentFlag.AlignBottom)
        self.language_row.addStretch()
        self.source_combo, _ = self._create_widget("language", "source_combo", QComboBox)
        self.target_combo, _ = self._create_widget("language", "target_combo", QComboBox)
        for combo in (self.source_combo, self.target_combo):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            combo.setMaxVisibleItems(12)
            _apply_custom_dropdown_style(combo)
        self.swap_btn, _ = self._create_widget("language", "swap_button", QPushButton)
        self.swap_btn.setIcon(_make_icon(ICONS_CONFIG["swap"]))
        self.language_row.addWidget(self.source_combo)
        self.language_row.addWidget(self.swap_btn)
        self.language_row.addWidget(self.target_combo)
        self.language_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.language_row.addItem(self.language_spacer)

        self.original_text = self._create_text_edit("Recognized text will appear here...")
        self.translated_text = self._create_text_edit("Translation will appear here...")
        self.translated_label, _ = self._create_widget("label", "translation", QLabel)
        self.translate_btn, _ = self._create_widget("main_buttons", "translate", QPushButton)
        self.translate_btn.setProperty("role", "translateButton")
        self.reader_mode_btn, reader_config = self._create_widget("main_buttons", "reader", QPushButton)
        self.reader_mode_btn.setProperty("role", "readerButton")
        self.reader_mode_btn.setProperty("utility", reader_config.get("utility", False))
        self.reader_mode_btn.setEnabled(reader_config.get("enabled", False))
        self.clear_original_btn = self._create_utility_button("clear")
        self.copy_original_btn = self._create_utility_button("copy")
        self.clear_translated_btn = self._create_utility_button("clear")
        self.copy_translated_btn = self._create_utility_button("copy")
        self.original_panel = PanelWidget(self.original_text, [self.translate_btn, self.clear_original_btn, self.copy_original_btn], self)
        self.translated_panel = PanelWidget(self.translated_text, [self.reader_mode_btn, self.clear_translated_btn, self.copy_translated_btn], self)

        self.footer_widget = QFrame(self)
        self.footer_widget.setFrameStyle(QFrame.Shape.NoFrame)
        footer_layout = QHBoxLayout(self.footer_widget)
        footer_layout.setContentsMargins(*LAYOUT_CONFIG["footer_margins"])
        self.provider_badge, _ = self._create_widget("footer", "provider_badge", QToolButton, text="")
        self.provider_badge.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.provider_badge.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.status_label, _ = self._create_widget("footer", "status_label", QLabel, text="")
        self.close_btn, _ = self._create_widget("footer", "close_button", QPushButton, text="Close")
        icons = FOOTER_WIDGET_CONFIG["close_button"]["icons"]
        self.close_icon_normal = _make_icon(icons["normal"])
        self.close_icon_hover = _make_icon(icons["hover"])
        self.close_btn.setIcon(self.close_icon_normal)
        footer_layout.addWidget(self.provider_badge)
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()
        footer_layout.addWidget(self.close_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.icon_translation = _make_icon(ICONS_CONFIG["translate"]["all"])
        self.icon_check_green = _make_icon(ICONS_CONFIG["utility_icons"]["check_success"])
        self.hideable_elements = [self.info_row, self.original_label, self.translated_label, self.footer_widget]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.info_row)
        layout.addLayout(self.language_row)
        layout.addWidget(self.original_panel, 1)
        layout.addWidget(self.translated_label)
        layout.addWidget(self.translated_panel, 1)
        layout.addWidget(self.footer_widget)

    def _create_utility_button(self, key):
        button, config = self._create_widget("utility_buttons", key, QPushButton)
        button.setIcon(_make_icon(ICONS_CONFIG["utility_icons"][config["icon_key"]]))
        button.setProperty("utility", config.get("utility", False))
        return button

    def _populate_languages(self, source, target):
        flags_path = _ASSETS_BASE / "icons" / "flags"
        self.source_combo.addItem("Auto", userData="auto")
        for language in self._supported_languages:
            icon = QIcon(QPixmap(str(flags_path / language.icon_name)))
            self.source_combo.addItem(icon, language.name, userData=language.code)
            self.target_combo.addItem(icon, language.name, userData=language.code)
        self.set_language_selection(source, target)

    def set_language_selection(self, source=None, target=None):
        for combo, value, fallback in ((self.source_combo, source, "en"), (self.target_combo, target, "en")):
            if value is None:
                value = combo.currentData()
            combo.blockSignals(True)
            try:
                for index in range(combo.count()):
                    if combo.itemData(index) == value:
                        combo.setCurrentIndex(index)
                        break
                if combo.currentData() != value:
                    for index in range(combo.count()):
                        if combo.itemData(index) == fallback:
                            combo.setCurrentIndex(index)
                            break
            finally:
                combo.blockSignals(False)

    def refresh_styles(self, styles=None):
        current = self.style_combo.currentText()
        self.style_combo.clear()
        self._styles = self._styles if styles is None else (styles or [])
        names = [((item.get("name") or "").strip() if isinstance(item, dict) else str(item)) for item in self._styles]
        names = [name for name in names if name]
        self.style_combo.addItems(names or ["Improve"])
        if current:
            index = self.style_combo.findText(current)
            if index >= 0:
                self.style_combo.setCurrentIndex(index)

    def configure(self, compact, autohide, font_size):
        self.set_font_size(font_size)
        for element in self.hideable_elements:
            element.setVisible(not compact)
        self.language_spacer.changeSize(34 if compact else 0, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.original_panel.configure(compact, autohide)
        self.translated_panel.configure(compact, autohide)

    def set_font_size(self, font_size):
        size = font_size or TRANSLATOR_FONT_SIZE_DEFAULT
        for text_edit in (self.original_text, self.translated_text):
            if hasattr(text_edit, "apply_font_point_size"):
                text_edit.apply_font_point_size(size)
            else:
                font = text_edit.font()
                font.setPointSize(size)
                text_edit.setFont(font)

    def set_language_controls_visible(self, visible):
        for widget in (self.source_combo, self.target_combo, self.swap_btn):
            widget.setVisible(visible)
        self.language_spacer.changeSize(0 if visible else 34, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.layout().invalidate()

    def set_mode_visibility(self, mode, compact):
        is_style = (mode or "").strip().lower() == "style"
        self.style_combo.setVisible(is_style)
        self.edit_styles_btn.setVisible(is_style)
        if not compact:
            self.translate_btn.setText("  Style" if is_style else "  Translate")
        if self.translate_btn.isEnabled():
            self.translate_btn.setIcon(self.icon_translation)
            self.translate_btn.setIconSize(QSize(14, 14))
            _refresh_widget_style(self.translate_btn)

    def set_style_mode_available(self, available):
        if available:
            if self.mode_combo.findText("Style") < 0:
                self.mode_combo.addItem("Style")
            self.mode_label.setVisible(True)
            self.mode_combo.setVisible(True)
        else:
            if self.mode_combo.currentText().strip().lower() == "style":
                self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findText("Translate")))
            index = self.mode_combo.findText("Style")
            if index >= 0:
                self.mode_combo.removeItem(index)
            self.style_combo.setVisible(False)
            self.mode_label.setVisible(False)
            self.mode_combo.setVisible(False)

    def set_status(self, text, style_type=None):
        self.status_label.setText(text)
        if style_type is not None:
            _apply_status_style(self.status_label, style_type)

    def set_translate_disabled(self, reason, compact):
        self.translate_btn.setProperty("logically_disabled", True)
        self.translate_btn.setCursor(Qt.CursorShape.ForbiddenCursor)
        self.translate_btn.setToolTip(reason or DEFAULT_DISABLED_TOOLTIP)
        self.translate_btn.setProperty("mode", "compact" if compact else "full")
        self.translate_btn.setIcon(_make_icon(ICONS_CONFIG["translate_disabled"]["compact" if compact else "full"]))
        _refresh_widget_style(self.translate_btn)

    def restore_translate(self, compact):
        self.translate_btn.setProperty("logically_disabled", False)
        self.translate_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self.translate_btn.setToolTip("")
        _apply_button_style(self.translate_btn, compact)
        self.translate_btn.setIcon(self.icon_translation)
        _refresh_widget_style(self.translate_btn)

    def set_provider_badge(self, display_name, provider_key):
        self.provider_badge.setText(display_name)
        self.provider_badge.setProperty("provider", provider_key)
        self.provider_badge.setToolTip(f"Using {display_name}. Click to change provider.")
        _refresh_widget_style(self.provider_badge)

    def show_button_feedback(self, button):
        previous_icon, previous_text = button.icon(), button.text()
        button.setIcon(self.icon_check_green)
        button.setText("")
        from PySide6.QtCore import QTimer

        def restore_button():
            try:
                button.setIcon(previous_icon)
                button.setText(previous_text)
            except RuntimeError:
                pass

        QTimer.singleShot(1200, restore_button)

    def set_close_hovered(self, hovered):
        self.close_btn.setIcon(self.close_icon_hover if hovered else self.close_icon_normal)
