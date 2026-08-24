"""
Overlay window implementation for Qt-based UI.
"""

import time
from pathlib import Path
from typing import Optional

from loguru import logger
from PySide6.QtCore import (
    QEvent,
    QSize,
    Qt,
    QThread,
    QTimer,
)
from PySide6.QtGui import QAction, QIcon, QTextCursor, QPixmap, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpacerItem,
    QSizePolicy,
    QMenu,
    QToolButton,
)

from ..services.config_service import config_service, SettingsObserver
from ..utils.language_utils import detect_language, get_language_name, get_supported_languages
from ..core.config import (
    API_TIMEOUT_DEFAULT,
    API_TIMEOUT_MAX,
    API_TIMEOUT_MIN,
    TRANSLATOR_FONT_SIZE_DEFAULT,
    validate_api_key_format,
)
from ..core.provider_catalog import APIProvider
from .styled_overlay_base import StyledOverlayWindow, WINDOW_CONTROLS_ICONS
from .workers import TranslationWorker, StyleWorker
from .overlay_ui_builder import PanelWidget, TranslatorSettingsDialog
from .widgets.placeholder_text_edit import PlaceholderTextEdit
from .widget_factory import apply_custom_dropdown_style as _apply_custom_dropdown_style
from .widget_factory import create_widget as _create_widget
from .widget_factory import make_icon_from_spec

_ASSETS_BASE = Path(__file__).parent.parent / "assets"

LAYOUT_CONFIG = {
    'info_row_margins': (0, 3, 0, 0),
    'info_row_spacer_width': 10,
    'info_row_spacer_height': 10,
    'footer_margins': (0, 0, 0, 0)
}

ICONS_CONFIG = {
    'utility_icons': {
        'eraser': {'icon': 'fa5s.eraser', 'color': 'black'},
        'copy': {'icon': 'fa5.copy', 'color': 'black'},
        'check_success': {'icon': 'fa5s.check', 'color': 'green'},
        'edit_styles': {'asset': 'pen-to-square-solid-full.svg'},
    },
    'window_controls': WINDOW_CONTROLS_ICONS,
    'translate_disabled': {
        'compact': {'icon': 'fa5s.lock', 'color': 'white'},
        'full': {'icon': 'fa5s.lock', 'color': '#757575'},
    },
    'reader': {
        'compact': {'asset': 'book_white.png'},
        'full': {'asset': 'book_black.png'},
    },
    'translate': {
        'all': {'asset': 'translation-icon.png'},
    },
    'swap': {'asset': 'arrows-exchange.png'},
}

DEFAULT_DISABLED_TOOLTIP = "API key is not configured. Open Settings to add a key."

LANGUAGE_WIDGET_CONFIG = {
    'source_combo': {'size': (125, 28), 'icon_size': (28, 28), 'object_name': 'sourceLanguageCombo'},
    'target_combo': {'size': (125, 28), 'icon_size': (28, 28), 'object_name': 'targetLanguageCombo'},
    'swap_button': {'size': (35, 28), 'icon_size': (20, 24)}
}

FOOTER_WIDGET_CONFIG = {
    'status_label': {'object_name': "statusLabel"},
    'provider_badge': {'object_name': "providerBadge", 'text': ""},
    'close_button': {
        'size': (86, 28), 'icon_size': (16, 16), 'object_name': "closeButton", 'text': "Close",
        'icons': {'normal': ICONS_CONFIG['window_controls']['close'], 'hover': ICONS_CONFIG['window_controls']['close_hover']}
    }
}

MAIN_BUTTONS_CONFIG = {
    'translate': {'text': "  Translate", 'object_name': "translateButton"},
    'reader': {'text': "", 'object_name': "readerButton", 'utility': False, 'enabled': False}
}

UTILITY_BUTTONS_CONFIG = {
    'clear': {'text': "", 'tooltip': "Clear text", 'utility': True, 'icon_key': 'eraser'},
    'copy': {'text': "", 'tooltip': "Copy text", 'utility': True, 'icon_key': 'copy'}
}

BUTTON_STYLES = {
    'translate_compact': {'text': '', 'size': (24, 24), 'icon_size': (12, 12), 'icon_spec': ICONS_CONFIG['translate']['all']},
    'translate_full': {'size': (120, 28), 'icon_size': (14, 14), 'icon_spec': ICONS_CONFIG['translate']['all']},
    'reader_compact': {'text': '', 'size': (24, 24), 'icon_size': (17, 17), 'icon_spec': ICONS_CONFIG['reader']['compact']},
    'reader_full': {'text': '', 'size': (40, 28), 'icon_size': (19, 19), 'tooltip': 'Open text in reader mode for comfortable reading', 'icon_spec': ICONS_CONFIG['reader']['full']},
    'default_compact': {'text': '', 'size': (24, 24), 'icon_size': (15, 15)},
    'default_full': {'text': '', 'size': (40, 28), 'icon_size': (16, 16)}
}

INFO_WIDGET_CONFIG = {
    'mode_combo': {'size': (95, 28), 'object_name': 'modeCombo'},
    'style_combo': {'size': (95, 28), 'object_name': 'styleCombo'},
    'detected_lang_label': {'width': 120},
    'mode_label': {'text': 'Mode:'},
    'auto_swap_checkbox': {'text': 'Auto-translate EN ↔ RU', 'tooltip': 'If enabled, English will be translated to Russian, and Russian to English'}
}

TEXT_EDIT_CONFIG = {'object_name': 'textEdit'}

LABEL_CONFIG = {
    'bold': {'object_name': 'boldLabel'},
    'original': {'text': 'Original:', 'object_name': 'boldLabel'},
    'translation': {'text': 'Translation:', 'object_name': 'boldLabel'}
}


def _make_icon(spec):
    return make_icon_from_spec(spec, _ASSETS_BASE)


def _refresh_widget_style(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_combo_data(combo, data_value):
    """Set combo to the index matching the data value, with signal blocking."""
    combo.blockSignals(True)
    try:
        for i in range(combo.count()):
            if combo.itemData(i) == data_value:
                combo.setCurrentIndex(i)
                break
    finally:
        combo.blockSignals(False)


def _apply_status_style(status_label, style_type):
    if not status_label:
        return
    try:
        status_label.setProperty("status", style_type)
        _refresh_widget_style(status_label)
    except Exception as e:
        logger.debug(f"Failed to apply status style: {e}")


def translate_button_text(is_style):
    return "  Style" if is_style else "  Translate"


def _apply_button_style(button, compact):
    mode = 'compact' if compact else 'full'
    try:
        role = button.property("role")
    except Exception:
        role = None
    role = (role or getattr(button, "objectName", lambda: "")() or "").strip()
    role_configs = {
        "translateButton": {"compact": BUTTON_STYLES["translate_compact"], "full": BUTTON_STYLES["translate_full"]},
        "readerButton": {"compact": BUTTON_STYLES["reader_compact"], "full": BUTTON_STYLES["reader_full"]},
    }
    config = role_configs.get(role, {}).get(mode) or BUTTON_STYLES[f"default_{mode}"]
    config = config.copy()
    if "text" in config and config["text"] is not None:
        button.setText(config["text"])
    if "tooltip" in config and config["tooltip"]:
        button.setToolTip(config["tooltip"])
    button.setFixedSize(*config["size"])
    button.setIconSize(QSize(*config["icon_size"]))
    if "icon_spec" in config:
        button.setIcon(_make_icon(config["icon_spec"]))
    try:
        button.setProperty("mode", mode)
        if button.property("utility") is None:
            button.setProperty("utility", False)
        _refresh_widget_style(button)
    except Exception:
        pass


def _disable_translate_button_visuals(button, reason_msg, compact):
    if not button:
        return
    try:
        button.setProperty("logically_disabled", True)
        button.setCursor(Qt.CursorShape.ForbiddenCursor)
        button.setToolTip(reason_msg or DEFAULT_DISABLED_TOOLTIP)
        mode = 'compact' if compact else 'full'
        button.setProperty("mode", mode)
        icon_spec = ICONS_CONFIG['translate_disabled'].get(mode)
        if icon_spec:
            button.setIcon(_make_icon(icon_spec))
        _refresh_widget_style(button)
    except Exception as e:
        logger.debug(f"Failed to apply disabled translate visuals: {e}")


def _enable_translate_button_visuals(button, compact):
    if not button:
        return
    try:
        button.setProperty("logically_disabled", False)
        button.setCursor(Qt.CursorShape.ArrowCursor)
        button.setToolTip("")
        _apply_button_style(button, compact)
        try:
            role = button.property("role")
        except Exception:
            role = None
        role = (role or getattr(button, "objectName", lambda: "")() or "").strip()
        if role == "translateButton":
            button.setIcon(_make_icon(ICONS_CONFIG['translate']['all']))
        _refresh_widget_style(button)
    except Exception as e:
        logger.debug(f"Failed to restore enabled translate visuals: {e}")


class _OverlaySettingsObserver(SettingsObserver):
    """Lightweight observer to react to settings changes affecting API readiness."""
    def __init__(self, owner):
        self._owner = owner

    def on_settings_changed(self, key, old_value, new_value):
        try:
            if key in ("api_provider", "openai_api_key", "google_api_key", "deepl_api_key", "api_timeout"):
                if hasattr(self._owner, "_update_api_state_and_ui"):
                    self._owner._update_api_state_and_ui()
            elif key == "translator_font_size":
                if hasattr(self._owner, "_apply_translator_font_size"):
                    self._owner._apply_translator_font_size(new_value)
            elif key == "text_styles":
                # Refresh style combo when user modifies text styles in settings
                if hasattr(self._owner, "refresh_styles"):
                    self._owner.refresh_styles()
        except Exception as e:
            logger.debug(f"Overlay observer change handler error: {e}")

class OverlayWindow(StyledOverlayWindow):
    """Overlay window for displaying translation results."""

    def _create_widget_from_config(self, widget_type, config_key, widget_class, **kwargs):
        config_maps = {
            'info': INFO_WIDGET_CONFIG,
            'language': LANGUAGE_WIDGET_CONFIG,
            'footer': FOOTER_WIDGET_CONFIG,
            'label': LABEL_CONFIG,
            'main_buttons': MAIN_BUTTONS_CONFIG,
            'utility_buttons': UTILITY_BUTTONS_CONFIG,
        }
        return _create_widget(config_maps, widget_type, config_key, widget_class, **kwargs)

    def _create_text_edit(self, placeholder):
        text_edit = PlaceholderTextEdit()
        text_edit.setReadOnly(False)
        text_edit.setAcceptRichText(False)
        text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        text_edit.setPlaceholderText(placeholder)
        text_edit.setObjectName(TEXT_EDIT_CONFIG['object_name'])
        return text_edit

    def _create_mode_combo(self):
        combo, _ = self._create_widget_from_config('info', 'mode_combo', QComboBox)
        combo.addItem("Translate")
        combo.addItem("Style")
        _apply_custom_dropdown_style(combo)
        return combo

    def _create_style_combo(self):
        combo, _ = self._create_widget_from_config('info', 'style_combo', QComboBox)
        self._populate_styles(combo)
        combo.setVisible(False)
        _apply_custom_dropdown_style(combo)
        return combo

    def _create_edit_styles_button(self):
        button = QPushButton()
        button.setObjectName("editStylesButton")
        button.setFixedSize(28, 28)
        button.setIcon(_make_icon(ICONS_CONFIG['utility_icons']['edit_styles']))
        button.setIconSize(QSize(16, 16))
        button.setVisible(False)
        button.setToolTip("Edit Styles")
        return button

    def _create_detected_lang_label(self):
        label, _ = self._create_widget_from_config('info', 'detected_lang_label', QLabel, text="Language: —")
        return label

    def _create_info_row(self):
        container = QFrame()
        container.setFrameStyle(QFrame.Shape.NoFrame)
        info_row = QHBoxLayout(container)
        info_row.setContentsMargins(*LAYOUT_CONFIG['info_row_margins'])
        self.mode_label, _ = self._create_widget_from_config('info', 'mode_label', QLabel)
        info_row.addWidget(self.mode_label)
        self.mode_combo = self._create_mode_combo()
        info_row.addWidget(self.mode_combo)
        self.style_combo = self._create_style_combo()
        info_row.addWidget(self.style_combo)
        self.edit_styles_btn = self._create_edit_styles_button()
        info_row.addWidget(self.edit_styles_btn)
        info_row.addItem(QSpacerItem(
            LAYOUT_CONFIG['info_row_spacer_width'], LAYOUT_CONFIG['info_row_spacer_height'],
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        ))
        self.detected_lang_label = self._create_detected_lang_label()
        info_row.addWidget(self.detected_lang_label)
        self.auto_swap_checkbox, _ = self._create_widget_from_config('info', 'auto_swap_checkbox', QCheckBox)
        info_row.addWidget(self.auto_swap_checkbox)
        return container

    def _create_swap_button(self):
        swap_btn, _ = self._create_widget_from_config('language', 'swap_button', QPushButton)
        swap_btn.setIcon(_make_icon(ICONS_CONFIG['swap']))
        return swap_btn

    def _create_language_row(self):
        language_row = QHBoxLayout()
        self.original_label, _ = self._create_widget_from_config('label', 'original', QLabel)
        language_row.addWidget(self.original_label, alignment=Qt.AlignmentFlag.AlignBottom)
        language_row.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        self.source_combo, _ = self._create_widget_from_config('language', 'source_combo', QComboBox)
        self.source_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.source_combo.setMaxVisibleItems(12)
        _apply_custom_dropdown_style(self.source_combo)
        self.target_combo, _ = self._create_widget_from_config('language', 'target_combo', QComboBox)
        self.target_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.target_combo.setMaxVisibleItems(12)
        _apply_custom_dropdown_style(self.target_combo)
        self.swap_btn = self._create_swap_button()
        language_row.addWidget(self.source_combo)
        language_row.addWidget(self.swap_btn)
        language_row.addWidget(self.target_combo)
        self.language_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        language_row.addItem(self.language_spacer)
        return language_row

    def _populate_styles(self, combo):
        try:
            combo.clear()
            settings = config_service.get_settings()
            styles = getattr(settings, "text_styles", []) or []
            if not styles:
                combo.addItem("Improve")
            else:
                for s in styles:
                    name = (s.get("name") or "").strip() if isinstance(s, dict) else str(s)
                    if name:
                        combo.addItem(name)
        except Exception as e:
            logger.warning(f"Failed to populate styles: {e}")

    def refresh_styles(self):
        if hasattr(self, "style_combo") and self.style_combo:
            current_text = self.style_combo.currentText()
            self._populate_styles(self.style_combo)
            if current_text:
                index = self.style_combo.findText(current_text)
                if index >= 0:
                    self.style_combo.setCurrentIndex(index)

    def _create_status_label(self):
        status_label, _ = self._create_widget_from_config('footer', 'status_label', QLabel, text="")
        return status_label

    def _create_provider_badge(self):
        provider_badge, _ = self._create_widget_from_config('footer', 'provider_badge', QToolButton, text="")
        provider_badge.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        provider_badge.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        return provider_badge

    def _create_close_button(self):
        config = FOOTER_WIDGET_CONFIG['close_button']
        close_btn, _ = self._create_widget_from_config('footer', 'close_button', QPushButton, text=config['text'])
        icons = config.get('icons', {})
        self.close_icon_normal = _make_icon(icons.get('normal'))
        self.close_icon_hover = _make_icon(icons.get('hover'))
        try:
            close_btn.setIcon(self.close_icon_normal)
        except Exception:
            pass
        return close_btn

    def _create_footer(self):
        footer_widget = QFrame()
        footer_widget.setFrameStyle(QFrame.Shape.NoFrame)
        footer_row = QHBoxLayout(footer_widget)
        footer_row.setContentsMargins(*LAYOUT_CONFIG['footer_margins'])
        self.provider_badge = self._create_provider_badge()
        footer_row.addWidget(self.provider_badge)
        self.status_label = self._create_status_label()
        footer_row.addWidget(self.status_label)
        footer_row.addStretch()
        self.close_btn = self._create_close_button()
        footer_row.addWidget(self.close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        return footer_widget

    def _init_language_controls(self):
        supported_languages = get_supported_languages()
        flags_path = _ASSETS_BASE / "icons" / "flags"
        self.source_combo.insertItem(0, "Auto", userData="auto")
        for lang in supported_languages:
            icon_path = flags_path / lang.icon_name
            icon = QIcon(QPixmap(str(icon_path)))
            self.source_combo.addItem(icon, lang.name, userData=lang.code)
            self.target_combo.addItem(icon, lang.name, userData=lang.code)
        settings = config_service.get_settings()
        ui_source_language = getattr(settings, "ui_source_language", "en")
        set_combo_data(self.source_combo, ui_source_language)
        if self.source_combo.currentData() != ui_source_language:
            set_combo_data(self.source_combo, "en")
        ui_target_language = getattr(settings, "ui_target_language", "en")
        set_combo_data(self.target_combo, ui_target_language)
        if self.target_combo.currentData() != ui_target_language:
            set_combo_data(self.target_combo, "en")

    def _create_main_buttons(self):
        self.translate_btn, _ = self._create_widget_from_config('main_buttons', 'translate', QPushButton)
        self.translate_btn.setProperty("role", "translateButton")
        self.reader_mode_btn, cfg = self._create_widget_from_config('main_buttons', 'reader', QPushButton)
        self.reader_mode_btn.setProperty("role", "readerButton")
        if 'utility' in cfg:
            self.reader_mode_btn.setProperty("utility", cfg['utility'])
        if 'enabled' in cfg:
            self.reader_mode_btn.setEnabled(cfg['enabled'])

    def _create_utility_buttons(self):
        def _create_util_btn(key):
            btn, cfg = self._create_widget_from_config('utility_buttons', key, QPushButton)
            if 'icon_key' in cfg:
                btn.setIcon(_make_icon(ICONS_CONFIG['utility_icons'][cfg['icon_key']]))
            if 'utility' in cfg:
                btn.setProperty("utility", cfg['utility'])
            return btn
        self.clear_original_btn = _create_util_btn('clear')
        self.copy_original_btn = _create_util_btn('copy')
        self.clear_translated_btn = _create_util_btn('clear')
        self.copy_translated_btn = _create_util_btn('copy')

    def _create_text_widgets(self):
        self.original_text = self._create_text_edit("Recognized text will appear here...")
        self.translated_text = self._create_text_edit("Translation will appear here...")
        self.translated_label, _ = self._create_widget_from_config('label', 'translation', QLabel)

    def _create_panels(self):
        original_buttons = [self.translate_btn, self.clear_original_btn, self.copy_original_btn]
        translated_buttons = [self.reader_mode_btn, self.clear_translated_btn, self.copy_translated_btn]
        self.original_panel = PanelWidget(self.original_text, original_buttons, _apply_button_style, parent=self)
        self.translated_panel = PanelWidget(self.translated_text, translated_buttons, _apply_button_style, parent=self)

    def _setup_ui(self):
        self.info_row = self._create_info_row()
        self.language_row = self._create_language_row()
        self._create_text_widgets()
        self._create_main_buttons()
        self._create_utility_buttons()
        self._create_panels()
        self._init_language_controls()
        self.footer_widget = self._create_footer()
        self.icon_translation = _make_icon(ICONS_CONFIG["translate"]["all"])
        self.icon_check_green = _make_icon(ICONS_CONFIG["utility_icons"]["check_success"])
        layout = self.content_layout
        layout.setSpacing(6)
        layout.addWidget(self.info_row)
        layout.addLayout(self.language_row)
        if hasattr(self, "mode_combo"):
            try:
                self._apply_mode_visibility(self.mode_combo.currentText())
            except Exception:
                pass
        layout.addWidget(self.original_panel)
        layout.addWidget(self.translated_label)
        layout.addWidget(self.translated_panel)
        layout.addWidget(self.footer_widget)
        layout.setStretch(layout.indexOf(self.original_panel), 1)
        layout.setStretch(layout.indexOf(self.translated_panel), 1)
        self.hideable_elements = [self.info_row, self.original_label, self.translated_label, self.footer_widget]

    def __init__(self):
        """Initialize the overlay window.

        The overlay creates and manages all UI components, signals, settings, and business logic.
        """
        super().__init__(title="Translator")
        self._translator_settings_dialog = None
        self._translation_start_time = None
        self._translation_worker = None
        self._translation_thread = None
        self._style_worker = None
        self._style_thread = None

        # Animation state for loading spinner + dots
        self._loading_timer: Optional[QTimer] = None
        self._loading_rotation = 0
        self._loading_dots_count = 0
        self._loading_base_text = ""

        self._setup_ui()

        # Initialize provider menu
        self._setup_provider_menu()

        self._apply_translator_font_size()

        self.add_settings_button(self._open_translator_settings)

        self._connect_signals()

        # Observe settings changes to react to provider/key updates
        try:
            self._settings_observer = _OverlaySettingsObserver(self)
            config_service.add_observer(self._settings_observer)
        except Exception as e:
            logger.debug(f"Failed to add settings observer: {e}")

        # Initial API state check for button/status
        self._update_api_state_and_ui()

        logger.debug("OverlayWindow initialized")



    def _apply_translator_font_size(self, font_size: Optional[int] = None) -> None:
        """Apply the configured font size to both translator text fields."""
        try:
            resolved_font_size = font_size
            if resolved_font_size is None:
                resolved_font_size = config_service.get_setting("translator_font_size")

            if resolved_font_size is None:
                resolved_font_size = TRANSLATOR_FONT_SIZE_DEFAULT

            for text_widget in (self.original_text, self.translated_text):
                if not text_widget:
                    continue

                if hasattr(text_widget, "apply_font_point_size"):
                    text_widget.apply_font_point_size(resolved_font_size)
                    continue

                font = text_widget.font()
                if font.pointSize() == resolved_font_size:
                    continue

                font.setPointSize(resolved_font_size)
                text_widget.setFont(font)
        except Exception as e:
            logger.debug(f"Failed to apply translator font size: {e}")

    def _connect_signals(self):
        """Connect all UI signals to their slots."""
        self.auto_swap_checkbox.stateChanged.connect(self._on_auto_swap_changed)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        self.swap_btn.clicked.connect(self._on_swap_clicked)
        self.original_text.textChanged.connect(self._on_original_text_changed)
        self.translated_text.textChanged.connect(self._update_reader_button_state)
        if hasattr(self, "mode_combo"):
            self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        if hasattr(self, "edit_styles_btn") and self.edit_styles_btn:
            self.edit_styles_btn.clicked.connect(self._open_stylist_settings)
        if self.translate_btn:
            self.translate_btn.clicked.connect(self._on_translate_clicked)
        self.reader_mode_btn.clicked.connect(self._on_reader_mode_clicked)
        self.clear_original_btn.clicked.connect(self._clear_original_text)
        self.copy_original_btn.clicked.connect(self._copy_original_to_clipboard)
        self.clear_translated_btn.clicked.connect(self._clear_translated_text)
        self.copy_translated_btn.clicked.connect(self._copy_translated_to_clipboard)
        self.close_btn.clicked.connect(self.dismiss)
        self.close_btn.installEventFilter(self)
        # Install event filter on original_text to capture Ctrl+Enter for translation
        self.original_text.installEventFilter(self)

    def _classify_request_error(self, error_message: str) -> tuple[str, bool]:
        """Map backend error text to a short UI status and whether it is a known API issue."""
        err_lower = (error_message or "").lower()

        if "quota" in err_lower:
            return "Quota exceeded", True
        if "rate limit" in err_lower or "429" in err_lower:
            return "Rate limit exceeded", True
        if "timeout" in err_lower:
            return "Request timed out", True
        if "cancel" in err_lower:
            return "Cancelled", True
        if "connection" in err_lower or "network" in err_lower:
            return "Network error", True
        if "server error" in err_lower or "500" in err_lower:
            return "Server error", True
        if "503" in err_lower:
            return "Service unavailable", True

        return "Failed", False

    def _apply_request_error_status(self, error_message: str, *, show_popup_for_unknown: bool) -> None:
        """Apply a stable error status without letting the generic finish path overwrite it."""
        status_text, is_known_error = self._classify_request_error(error_message)

        if show_popup_for_unknown and not is_known_error:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Translation failed", f"Translation error: {error_message}")

        logger.error(f"Translation failed: {error_message}")

        if self._translation_start_time is not None:
            elapsed = time.time() - self._translation_start_time
            self.status_label.setText(f"{status_text} ({elapsed:.1f}s)")
        else:
            self.status_label.setText(status_text)

        try:
            _apply_status_style(self.status_label, 'error')
        except Exception:
            pass

    def _apply_successful_translation_result(self, result: str) -> None:
        """Render a successful translation/style result into the UI."""
        if not result.strip():
            self.status_label.setText("Model returned empty response")
            _apply_status_style(self.status_label, 'error')
            self.translated_text.setPlainText("")
            logger.warning("Model returned empty translation response")
            return

        self.translated_text.setPlainText(result)
        _apply_status_style(self.status_label, 'default')
        logger.info("Translation completed and inserted into translated_text")

        try:
            settings = self._cached_settings
            auto_copy = getattr(settings, "auto_copy_translated_overlay", False)
            if auto_copy:
                clipboard = QApplication.clipboard()
                clipboard.setText(result)
                logger.info("Translated text automatically copied to clipboard (translator overlay)")
                self._show_button_feedback(self.copy_translated_btn)
        except Exception as e:
            logger.debug(f"Failed to auto-copy translated text: {e}")

    def _apply_success_completion_status(self) -> None:
        """Replace the in-flight status with the standard completion message."""
        if self._translation_start_time is not None:
            elapsed = time.time() - self._translation_start_time
            if "safety" not in (self.status_label.text() or "").lower():
                self.status_label.setText(f"Completed in {elapsed:.1f}s")
            return

        if "safety" not in (self.status_label.text() or "").lower():
            self.status_label.setText("")

    def _restore_request_controls(self) -> None:
        """Stop request affordances and restore the translate/style button text."""
        settings = getattr(self, "_cached_settings", None)
        compact = getattr(settings, "compact_view", False)
        prev_text = getattr(self, "_translation_prev_text", "Translate")

        self._stop_loading_animation()
        if self.translate_btn:
            self.translate_btn.setEnabled(True)
            if not compact:
                self.translate_btn.setText(prev_text)

        if hasattr(self, "_translation_prev_text"):
            delattr(self, "_translation_prev_text")

    def _finalize_translation_request(self, *, success: bool, refresh_api_state: bool) -> None:
        """Run request cleanup after the terminal finished signal."""
        if success:
            self._apply_success_completion_status()

        self._translation_start_time = None
        self._restore_request_controls()

        if refresh_api_state:
            try:
                self._update_api_state_and_ui()
            except Exception:
                pass

    def _is_style_mode_selected(self) -> bool:
        """Return whether the current request should use Style mode."""
        return bool(hasattr(self, "mode_combo") and (self.mode_combo.currentText().strip().lower() == "style"))

    def _begin_request_ui_state(self, *, is_style: bool):
        """Initialize request state and loading UI before starting a worker."""
        self._translation_start_time = time.time()
        self.status_label.setText("Request sent")
        _apply_status_style(self.status_label, 'default')

        settings = self._cached_settings
        compact = getattr(settings, "compact_view", False)

        if self.translate_btn:
            prev_text = self.translate_btn.text()
            base_text = "Styling" if is_style else "Translating"
            self._start_loading_animation(base_text, compact)
        else:
            prev_text = "Style" if is_style else "Translate"

        self._translation_prev_text = prev_text
        return settings

    def _resolve_style_name(self, settings) -> str:
        """Resolve the current style preset name with the same fallback order as the UI."""
        style_name = ""
        try:
            style_name = self.style_combo.currentText().strip()
        except Exception:
            pass

        if style_name:
            return style_name

        try:
            styles = getattr(settings, "text_styles", []) or []
            if styles:
                first_style = styles[0]
                return (first_style.get("name") or "Improve") if isinstance(first_style, dict) else str(first_style)
        except Exception:
            pass

        return "Improve"

    def _start_style_request(self, text: str, settings) -> None:
        """Start a style worker for the current request."""
        style_name = self._resolve_style_name(settings)
        logger.debug(f"Style mode selected. Style='{style_name}'")
        self._style_worker, self._style_thread = self._setup_worker(StyleWorker, text, style_name)

    def _start_translation_request(self, text: str) -> None:
        """Start a translation worker using the current UI language selections."""
        ui_source_lang = self.source_combo.currentData()
        ui_target_lang = self.target_combo.currentData()
        logger.debug(f"Translate mode selected with UI languages: source='{ui_source_lang}', target='{ui_target_lang}'")
        self._translation_worker, self._translation_thread = self._setup_worker(
            TranslationWorker,
            text,
            ui_source_lang,
            ui_target_lang,
        )

    def _on_mode_changed(self, index: int):
        """Handle mode combo box changes (Translate vs Style)."""
        try:
            mode_text = self.mode_combo.currentText().strip().lower()
            self._apply_mode_visibility(mode_text)
        except Exception as e:
            logger.debug(f"Failed to handle mode change: {e}")



    def _open_stylist_settings(self):
        """Open the main settings dialog on the Stylist tab via UIService."""
        try:
            from ..services.ui_service import get_ui_service

            ui_service = get_ui_service()
            if ui_service is None:
                logger.warning("UIService is not available; cannot open Stylist settings")
                return

            ui_service.open_settings(tab_title="Stylist")
            logger.info("Opened settings dialog on Stylist tab")
        except Exception as e:
            logger.error(f"Failed to open stylist settings: {e}", exc_info=True)

    def _apply_mode_visibility(self, mode: str):
        """Apply visibility changes based on selected mode."""
        try:
            mode = (mode or "").strip().lower()
            is_style = mode == "style"

            # Show/hide style combo based on mode
            if hasattr(self, "style_combo") and self.style_combo:
                self.style_combo.setVisible(is_style)
            
            if hasattr(self, "edit_styles_btn") and self.edit_styles_btn:
                self.edit_styles_btn.setVisible(is_style)

            # Update translate button text and icon
            if hasattr(self, "translate_btn") and self.translate_btn:
                try:
                    compact = getattr(getattr(self, "_cached_settings", None), "compact_view", False)
                    if not compact:
                        new_text = translate_button_text(is_style)
                        self.translate_btn.setText(new_text)
                    # Only set icon if button is enabled (not in disabled state)
                    if self.translate_btn.isEnabled():
                        self.translate_btn.setIcon(self.icon_translation)
                        self.translate_btn.setIconSize(QSize(14, 14))
                    # Force a style refresh to reflect label changes instantly
                    self.translate_btn.style().unpolish(self.translate_btn)
                    self.translate_btn.style().polish(self.translate_btn)
                    self.translate_btn.update()
                except Exception:
                    pass

            logger.debug(f"Mode visibility applied: mode='{mode}', is_style={is_style}")

            # Ensure API state is correctly reflected after mode change
            self._update_api_state_and_ui()
        except Exception as e:
            logger.debug(f"Failed to apply mode visibility: {e}")

    def _update_language_controls_visibility(self):
        """Update visibility of language controls based on auto-swap setting."""
        try:
            settings = config_service.get_settings()
            auto_swap = getattr(settings, "auto_swap_en_ru", True)

            # Show language controls when auto-swap is disabled
            show_controls = not auto_swap

            if hasattr(self, "source_combo") and self.source_combo:
                self.source_combo.setVisible(show_controls)
            if hasattr(self, "target_combo") and self.target_combo:
                self.target_combo.setVisible(show_controls)
            if hasattr(self, "swap_btn") and self.swap_btn:
                self.swap_btn.setVisible(show_controls)
            if hasattr(self, "language_spacer") and self.language_spacer:
                # Adjust spacer size based on visibility
                size = 0 if show_controls else 34  # Hide spacer when controls are visible
                self.language_spacer.changeSize(size, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

            # Force layout recalculation to eliminate spacing artifacts
            self.content_layout.invalidate()

            logger.debug(f"Language controls visibility updated: auto_swap={auto_swap}, show_controls={show_controls}")
        except Exception as e:
            logger.debug(f"Failed to update language controls visibility: {e}")




    def _is_api_ready(self) -> tuple[bool, str]:
        """Check whether API calls can proceed given current provider/key settings."""
        try:
            provider = (config_service.get_setting("api_provider") or APIProvider.OPENAI.value).strip().lower()
            try:
                provider = APIProvider(provider).value
            except ValueError:
                return False, f"Unsupported API provider: {provider}"

            key = config_service.get_setting(f"{provider}_api_key")
            if not key:
                return False, f"{provider.capitalize()} API key is not configured"

            if validate_api_key_format(key, provider):
                return True, ""
            return False, f"{provider.capitalize()} API key format is invalid"
        except Exception as e:
            logger.debug(f"API readiness check failed: {e}")
            return False, "API key is not configured"

    def _apply_disabled_translate_visuals(self, reason_msg: str) -> None:
        """Apply strong disabled visuals for the Translate/Style button."""
        try:
            if not hasattr(self, "translate_btn") or not self.translate_btn:
                return

            # Determine compact mode safely
            compact = False
            try:
                compact = bool(getattr(getattr(self, "_cached_settings", None), "compact_view", False))
            except Exception:
                compact = False

            _disable_translate_button_visuals(self.translate_btn, reason_msg, compact)
        except Exception as e:
            logger.debug(f"Failed to apply disabled translate visuals: {e}")

    def _restore_enabled_translate_visuals(self) -> None:
        """Restore normal visuals for the Translate/Style button."""
        try:
            if not hasattr(self, "translate_btn") or not self.translate_btn:
                return

            # Avoid re-enabling visuals during an active request
            if getattr(self, "_translation_start_time", None) is None:
                self.translate_btn.setEnabled(True)

            # Determine compact mode safely
            compact = False
            try:
                compact = bool(getattr(getattr(self, "_cached_settings", None), "compact_view", False))
            except Exception:
                compact = False

            _enable_translate_button_visuals(self.translate_btn, compact)
        except Exception as e:
            logger.debug(f"Failed to restore enabled translate visuals: {e}")

    def _find_index_by_text(self, combo, text: str) -> int:
        """Helper to find index by visible text."""
        for i in range(combo.count()):
            if (combo.itemText(i) or "").strip().lower() == text.lower():
                return i
        return -1

    def _update_provider_badge(self) -> None:
        """Update the provider badge to reflect the current API provider."""
        try:
            if not hasattr(self, "provider_badge") or not self.provider_badge:
                return

            provider = (config_service.get_setting("api_provider") or APIProvider.OPENAI.value).strip().lower()
            try:
                provider_enum = APIProvider(provider)
            except ValueError:
                return

            # Map provider to display name and property
            provider_map = {
                APIProvider.OPENAI: "OpenAI",
                APIProvider.GOOGLE: "Google",
                APIProvider.DEEPL: "DeepL",
            }
            display_name = provider_map[provider_enum]
            prop_value = provider_enum.value

            self.provider_badge.setText(display_name)
            self.provider_badge.setProperty("provider", prop_value)
            self.provider_badge.setToolTip(f"Using {display_name}. Click to change provider.")

            # Force style refresh to apply QSS
            self.provider_badge.style().unpolish(self.provider_badge)
            self.provider_badge.style().polish(self.provider_badge)
            self.provider_badge.update()
        except Exception as e:
            logger.debug(f"Failed to update provider badge: {e}")

    def _setup_provider_menu(self):
        """Setup the dropdown menu for the provider badge."""
        try:
            if not hasattr(self, "provider_badge") or not self.provider_badge:
                return

            menu = QMenu(self.provider_badge)
            menu.setObjectName("providerMenu")
            # Enable translucent background for rounded corners in QSS
            menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            # Remove standard window frame/shadow to allow QSS control (matches ComboBox dropdowns)
            menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
            
            provider_labels = {
                APIProvider.OPENAI: "OpenAI",
                APIProvider.GOOGLE: "Google",
                APIProvider.DEEPL: "DeepL",
            }
            for provider, label in provider_labels.items():
                action = QAction(label, self)
                action.triggered.connect(lambda checked=False, value=provider.value: self._switch_provider(value))
                menu.addAction(action)

            self.provider_badge.setMenu(menu)
            logger.debug("Provider menu setup completed")

        except Exception as e:
            logger.error(f"Failed to setup provider menu: {e}")

    def _switch_provider(self, provider_key: str):
        """Switch the API provider and persist the setting."""
        try:
            logger.info(f"Switching provider to: {provider_key}")
            if config_service.set_setting("api_provider", provider_key):
                # UI update will happen automatically via _SettingsObserver -> _update_api_state_and_ui
                pass
        except Exception as e:
            logger.error(f"Failed to switch provider: {e}")

    def _update_api_state_and_ui(self) -> None:
        """Enable/disable action button and set high-priority status when API key is missing/invalid."""
        try:
            ready, msg = self._is_api_ready()

            # Strong visual treatment for the action button
            if not ready:
                self._apply_disabled_translate_visuals(msg)
            else:
                self._restore_enabled_translate_visuals()

            # Update status label with priority red message when not ready
            if hasattr(self, "status_label") and self.status_label:
                if not ready:
                    _apply_status_style(self.status_label, 'error')
                    self.status_label.setText(msg)
                else:
                    # Restore default style only if we are clearing an API key error
                    if "API key" in (self.status_label.text() or ""):
                        _apply_status_style(self.status_label, 'default')
                        self.status_label.setText("")

            # Update provider badge
            self._update_provider_badge()

            # Enforce provider capabilities (disable Style mode for DeepL)
            try:
                provider = (config_service.get_setting("api_provider") or APIProvider.OPENAI.value).strip().lower()
                if hasattr(self, "mode_combo") and self.mode_combo:
                    style_idx = self._find_index_by_text(self.mode_combo, "Style")
                    if provider == "deepl":
                        # If currently on Style, switch to Translate before removing the item
                        try:
                            if (self.mode_combo.currentText() or "").strip().lower() == "style":
                                trans_idx = self._find_index_by_text(self.mode_combo, "Translate")
                                if trans_idx != -1:
                                    self.mode_combo.setCurrentIndex(trans_idx)
                                    self._apply_mode_visibility("Translate")
                        except Exception:
                            pass
                        # Remove Style option
                        if style_idx != -1:
                            self.mode_combo.removeItem(style_idx)
                        # Ensure style combo is hidden
                        if hasattr(self, "style_combo") and self.style_combo:
                            self.style_combo.setVisible(False)
                        # Hide mode controls for DeepL provider
                        if hasattr(self, "mode_label") and self.mode_label:
                            self.mode_label.setVisible(False)
                        if hasattr(self, "mode_combo") and self.mode_combo:
                            self.mode_combo.setVisible(False)
                    else:
                        # Ensure Style option exists for LLM providers
                        if style_idx == -1:
                            try:
                                self.mode_combo.addItem("Style")
                            except Exception:
                                pass
                        # Ensure mode controls are visible for non-DeepL providers
                        if hasattr(self, "mode_label") and self.mode_label:
                            self.mode_label.setVisible(True)
                        if hasattr(self, "mode_combo") and self.mode_combo:
                            self.mode_combo.setVisible(True)
            except Exception as e:
                logger.debug(f"Provider capability enforcement failed: {e}")
        except Exception as e:
            logger.debug(f"Failed to update API state/UI: {e}")

    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape:
            logger.info("Escape key pressed, dismissing overlay")
            self.dismiss()
        else:
            super().keyPressEvent(event)

    def _open_translator_settings(self):
        """Show the translator-specific settings dialog."""
        try:
            if self._translator_settings_dialog is None:
                dialog = TranslatorSettingsDialog(self)
                dialog.destroyed.connect(lambda: setattr(self, "_translator_settings_dialog", None))
                self._translator_settings_dialog = dialog

            dialog = self._translator_settings_dialog
            if dialog.isHidden():
                dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        except Exception as e:
            logger.error(f"Failed to open translator settings dialog: {e}")

    def _update_layout(self):
        """Updates the entire UI layout based on current view settings."""
        settings = config_service.get_settings()
        compact = getattr(settings, "compact_view", False)
        autohide = getattr(settings, "overlay_side_buttons_autohide", False)

        # Cache settings for use in other methods
        self._cached_settings = settings
        self._apply_translator_font_size(getattr(settings, "translator_font_size", None))

        for element in self.hideable_elements:
            element.setVisible(not compact)

        if hasattr(self, 'language_spacer'):
            size = 34 if compact else 0
            self.language_spacer.changeSize(size, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        # Configure panel widgets instead of manual per-panel logic
        self.original_panel.configure(compact, autohide)
        self.translated_panel.configure(compact, autohide)

        # Re-apply API state after layout changes to override any button style resets
        self._update_api_state_and_ui()

        # Re-apply mode-dependent UI so the Translate button text is restored in full mode
        if hasattr(self, "mode_combo"):
            self._apply_mode_visibility(self.mode_combo.currentText())

        logger.debug(f"Layout updated: compact={compact}, autohide={autohide}")

    def eventFilter(self, obj, event):
        """Handle events for child widgets, including hover for compact buttons."""
        if not hasattr(self, "original_text"):
            return super().eventFilter(obj, event)

        # Handle Ctrl+Enter in original_text to trigger translation
        if obj == self.original_text and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                logger.debug("Ctrl+Enter pressed in original_text, triggering translation")
                self._on_translate_clicked()
                return True

        # PanelWidget handles its own hover-based autohide; no-op here

        if obj == self.close_btn:
            if event.type() == QEvent.Type.Enter:
                self.close_btn.setIcon(self.close_icon_hover)
            elif event.type() == QEvent.Type.Leave:
                self.close_btn.setIcon(self.close_icon_normal)

        return super().eventFilter(obj, event)

    def show_overlay(self, original_text: str = "", translated_text: str = "", position: tuple[int, int] | None = None, error_message: str = ""):
        """Show the overlay with specified content."""
        logger.info("Showing overlay window")
        # Ensure button/state reflect API key presence at time of showing
        self._update_api_state_and_ui()

        settings = config_service.get_settings()
        current_state = getattr(settings, "auto_swap_en_ru", True)
        self.auto_swap_checkbox.setChecked(current_state)

        self._update_layout()
        # Re-assert API state after layout restyles
        self._update_api_state_and_ui()

        # Update language controls visibility after layout is set up
        self._update_language_controls_visibility()

        self.original_text.setPlainText(original_text)
        self.translated_text.setPlainText(translated_text)

        # Update status based on error or success
        if error_message:
            status_text, _is_known_error = self._classify_request_error(error_message)
            self.status_label.setText(status_text)
            _apply_status_style(self.status_label, 'error')
        elif original_text:
            self.status_label.setText("Completed")
            _apply_status_style(self.status_label, 'default')
        else:
            self.status_label.setText("")

        # Update reader button state after setting text
        self._update_reader_button_state()

        # Set focus to original text for quick typing
        self.original_text.setFocus()
        cursor = self.original_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.original_text.setTextCursor(cursor)

        self.show()
        self.raise_()
        self.activateWindow()
        logger.debug("Overlay window shown and activated")

    def _show_button_feedback(self, button: QPushButton):
        """Show visual feedback on a button by displaying a green checkmark for 1.2 seconds."""
        try:
            prev_icon = button.icon()
            prev_text = button.text()

            try:
                button.setIcon(self.icon_check_green)
            except Exception:
                pass
            button.setText("")
            
            def _restore_button(p_icon, p_text):
                """Restore button icon and text, handling deleted button gracefully."""
                try:
                    button.setIcon(p_icon)
                    button.setText(p_text)
                except RuntimeError:
                    # Button already deleted, ignore
                    pass
            
            QTimer.singleShot(
                1200,
                lambda p_icon=prev_icon, p_text=prev_text: _restore_button(p_icon, p_text),
            )
        except Exception as e:
            logger.error(f"Failed to show button feedback: {e}")

    def _copy_text_to_clipboard(self, text_widget, button: QPushButton, text_name: str):
        """Copy text from a QTextEdit to clipboard and provide visual feedback on a button."""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(text_widget.toPlainText())
            logger.info(f"{text_name} text copied to clipboard")
            self._show_button_feedback(button)
        except Exception as e:
            logger.error(f"Failed to copy {text_name} text: {e}")

    def _copy_original_to_clipboard(self):
        """Copy original text to clipboard."""
        self._copy_text_to_clipboard(self.original_text, self.copy_original_btn, "Original")

    def _clear_text(self, text_widget, button: QPushButton, label_to_reset: Optional[QLabel] = None):
        """Clear text from a QTextEdit widget and optionally reset a label, with visual feedback on button."""
        try:
            text_widget.clear()
            if label_to_reset:
                label_to_reset.setText("Language: —")
            self._show_button_feedback(button)
        except Exception as e:
            logger.error(f"Failed to clear text: {e}")

    def _clear_original_text(self):
        """Clear original text area and reset language label."""
        self._clear_text(self.original_text, self.clear_original_btn, self.detected_lang_label)
        self.status_label.setText("")
        # Re-assert API state warning if needed
        self._update_api_state_and_ui()

    def _clear_translated_text(self):
        """Clear translated text area."""
        self._clear_text(self.translated_text, self.clear_translated_btn)
        self.status_label.setText("")
        # Re-assert API state warning if needed
        self._update_api_state_and_ui()


    def _on_original_text_changed(self):
        """Update detected language label when original text changes."""
        try:
            text = self.original_text.toPlainText().strip()
            if not text:
                self.detected_lang_label.setText("Language: —")
                return

            lang_code = detect_language(text)
            if lang_code:
                lang_name = get_language_name(lang_code)
                self.detected_lang_label.setText(f"Language: {lang_name}")
            else:
                self.detected_lang_label.setText("Language: —")
        except Exception as e:
            logger.debug(f"Failed to update detected language label: {e}")

    def _update_reader_button_state(self):
        """Update the reader mode button state based on translated text presence."""
        try:
            translated_text = self.translated_text.toPlainText().strip()
            self.reader_mode_btn.setEnabled(bool(translated_text))
        except Exception as e:
            logger.debug(f"Failed to update reader button state: {e}")

    def _on_auto_swap_changed(self, state):
        """Persist Auto-swap checkbox state to settings when changed."""
        enabled = bool(state)
        if config_service.set_setting("auto_swap_en_ru", enabled):
            logger.info(f"Auto-swap setting updated: {enabled}")
            # Update language controls visibility when auto-swap setting changes
            self._update_language_controls_visibility()

    def _on_source_changed(self, index: int):
        """User changed Source combo -> persist ui_source_language."""
        code = self.source_combo.currentData()
        if config_service.set_setting("ui_source_language", code):
            logger.info(f"UI source language updated: {code}")

    def _on_target_changed(self, index: int):
        """User changed Target combo -> persist ui_target_language."""
        data = self.target_combo.currentData()
        updates = {"ui_target_language": data}
        try:
            previous_target = getattr(config_service.get_settings(), "ui_target_language", data)
            if config_service.update_settings(updates):
                logger.info(f"UI target updated: lang={data}")
            else:
                set_combo_data(self.target_combo, previous_target)
                logger.error(f"Failed to persist target selection: {data}")
        except Exception as e:
            logger.error(f"Failed to persist target selection: {e}")

    def _perform_language_swap(self):
        """Perform the language swap logic and persist changes."""
        if not hasattr(self, "source_combo") or not hasattr(self, "target_combo"):
            return

        src_data = self.source_combo.currentData()
        tgt_data = self.target_combo.currentData()

        if src_data == "auto":
            new_source = tgt_data
            new_target = tgt_data
            set_combo_data(self.source_combo, new_source)
            logger.info(f"Swap with 'auto' source: source set to '{new_source}'")
        else:
            new_source = tgt_data
            new_target = src_data
            set_combo_data(self.source_combo, new_source)
            set_combo_data(self.target_combo, new_target)
            logger.info(f"Swapped languages: source='{new_source}', target='{new_target}'")

        # Common settings update logic
        updates = {
            "ui_source_language": new_source,
            "ui_target_language": new_target,
        }
        try:
            if not config_service.update_settings(updates):
                set_combo_data(self.source_combo, src_data)
                set_combo_data(self.target_combo, tgt_data)
                logger.error("Failed to persist swap")
        except Exception as e:
            logger.error(f"Failed to persist swap: {e}")


    def _on_swap_clicked(self):
        """Swap button behavior"""
        self._perform_language_swap()

    def _setup_worker(self, worker_class, *args):
        """Generic method to set up and start a worker in a background thread."""
        worker = worker_class(*args)
        thread = QThread()
        worker.moveToThread(thread)

        worker.finished.connect(self._on_translation_finished)
        thread.started.connect(worker.run)

        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        # Watchdog timer setup
        api_timeout = config_service.get_setting("api_timeout")
        try:
            api_timeout = int(api_timeout)
        except (TypeError, ValueError):
            api_timeout = None
        if api_timeout is None or not API_TIMEOUT_MIN <= api_timeout <= API_TIMEOUT_MAX:
            api_timeout = API_TIMEOUT_DEFAULT
        watchdog_timeout = max(api_timeout * 2, 60)  # Reduced minimum to 60 seconds
        
        watchdog = QTimer(self)
        watchdog.setSingleShot(True)
        watchdog_active = [True]  # Mutable flag for closure
        
        def _force_thread_termination():
            if not watchdog_active[0]:
                return
            try:
                if not thread.isRunning():
                    logger.debug("Watchdog triggered but thread already finished")
                    return
                
                # Disconnect self to prevent re-entry
                try:
                    watchdog.timeout.disconnect(_force_thread_termination)
                except (RuntimeError, TypeError):
                    pass
                    
                logger.error(f"Watchdog timeout: forcing thread termination after {watchdog_timeout}s")
                thread.quit()
                thread.wait(1000)
                if thread.isRunning():
                    logger.warning("Thread still running after quit, forcing termination")
                    thread.terminate()
                    thread.wait(1000)
                    if thread.isRunning():
                        logger.error("Thread still running after terminate! System instability possible.")
            except Exception as e:
                logger.error(f"Exception during watchdog thread termination: {e}")
        
        def cleanup_watchdog():
            """Stop watchdog and clean up resources."""
            if not watchdog_active[0]:
                return
            watchdog_active[0] = False
            try:
                logger.debug("Cleaning up watchdog timer")
                # Disconnect signals to prevent dangling references
                try:
                    thread.finished.disconnect(cleanup_watchdog)
                except (RuntimeError, TypeError):
                    pass
                try:
                    worker.finished.disconnect(cleanup_watchdog)
                except (RuntimeError, TypeError):
                    pass
                # Schedule deletion
                watchdog.deleteLater()
                logger.debug("Watchdog cleanup completed")
            except Exception as e:
                logger.debug(f"Watchdog cleanup error: {e}")
        
        watchdog.timeout.connect(_force_thread_termination)
        

        
        # Connect cleanup signals
        thread.finished.connect(cleanup_watchdog)
        worker.finished.connect(cleanup_watchdog)
        
        # Start watchdog immediately BEFORE thread ensures 100% coverage
        if watchdog_active[0]:
            logger.debug(f"Starting watchdog with {watchdog_timeout}s timeout")
            watchdog.start(watchdog_timeout * 1000)
            
        # Now start the thread
        thread.start()
        return worker, thread



    def _on_translate_clicked(self):
        """Translate or Style the text from the original_text field based on mode."""
        if self._translation_start_time is not None:
            self._cancel_active_request()
            return

        # Check if button is logically disabled (fake disabled state to preserve cursor events)
        if hasattr(self, "translate_btn") and self.translate_btn and self.translate_btn.property("logically_disabled"):
            ready, _msg = self._is_api_ready()
            if not ready:
                logger.debug("Translate button clicked but is logically disabled")
                return
            self._restore_enabled_translate_visuals()
            
        text = self.original_text.toPlainText().strip()
        if not text:
            logger.info("Translate/Style button clicked with empty original_text")
            return

        # Guard: API must be ready (key configured/valid)
        ready, _msg = self._is_api_ready()
        if not ready:
            self._update_api_state_and_ui()
            return

        is_style = self._is_style_mode_selected()
        settings = self._begin_request_ui_state(is_style=is_style)

        if is_style:
            self._start_style_request(text, settings)
            return

        self._start_translation_request(text)

    def _on_translation_finished(self, success: bool, result: str):
        """Handle completion of background translation."""
        try:
            if success:
                self._apply_successful_translation_result(result)
            else:
                self._apply_request_error_status(result, show_popup_for_unknown=True)
        finally:
            self._finalize_translation_request(
                success=success,
                refresh_api_state=not success,
            )

    def _cancel_active_request(self):
        """Cancel active translation/style request and restore UI state."""
        translation_worker = getattr(self, "_translation_worker", None)
        translation_thread = getattr(self, "_translation_thread", None)
        style_worker = getattr(self, "_style_worker", None)
        style_thread = getattr(self, "_style_thread", None)

        try:
            translation_running = translation_thread is not None and translation_thread.isRunning()
        except RuntimeError:  # C++ object already deleted
            translation_running = False
        try:
            style_running = style_thread is not None and style_thread.isRunning()
        except RuntimeError:
            style_running = False

        if translation_running or not style_running:
            worker = translation_worker
            thread = translation_thread
        else:
            worker = style_worker
            thread = style_thread

        if worker is not None:
            for signal, handler in (
                (worker.finished, self._on_translation_finished),
            ):
                try:
                    signal.disconnect(handler)
                except (RuntimeError, TypeError):
                    pass

            if hasattr(worker, "request_cancel"):
                try:
                    worker.request_cancel()
                except Exception as e:
                    logger.debug(f"Failed to request worker cancellation: {e}")

        if thread is not None:
            try:
                if thread.isRunning():
                    thread.quit()
            except Exception as e:
                logger.debug(f"Failed to quit worker thread: {e}")

        self._translation_start_time = None
        self.status_label.setText("Cancelled")
        try:
            _apply_status_style(self.status_label, 'error')
        except Exception:
            pass

        settings = self._cached_settings
        compact = getattr(settings, "compact_view", False)
        prev_text = getattr(self, "_translation_prev_text", "Translate")
        self._stop_loading_animation()
        if self.translate_btn:
            self.translate_btn.setEnabled(True)
            if not compact:
                self.translate_btn.setText(prev_text)
        if hasattr(self, "_translation_prev_text"):
            delattr(self, "_translation_prev_text")

    def shutdown_workers(self):
        """Cancel and wait for all live request worker threads during application shutdown."""
        pairs = (
            (getattr(self, "_translation_worker", None), getattr(self, "_translation_thread", None)),
            (getattr(self, "_style_worker", None), getattr(self, "_style_thread", None)),
        )

        threads = []
        for worker, thread in pairs:
            if worker is not None and hasattr(worker, "request_cancel"):
                try:
                    worker.request_cancel()
                except Exception as e:
                    logger.debug(f"Failed to request worker cancellation during shutdown: {e}")
            try:
                if thread is not None and thread.isRunning():
                    thread.quit()
                    threads.append(thread)
            except RuntimeError:  # C++ object already deleted
                pass

        deadline = time.monotonic() + 5.0
        while any(thread.isRunning() for thread in threads):
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                break
            for thread in threads:
                if thread.isRunning():
                    thread.wait(min(100, remaining_ms))

        for thread in threads:
            if thread.isRunning():
                logger.warning("Overlay worker thread did not stop during shutdown")

    def _start_loading_animation(self, base_text: str, compact: bool):
        """Start the loading animation with spinning icon and animated dots."""
        try:
            self._loading_base_text = base_text
            self._loading_rotation = 0
            self._loading_dots_count = 0
            self._loading_compact = compact

            # Store original icon for restoration
            if self.translate_btn:
                self._original_icon = self.translate_btn.icon()

            # Create and start timer (60ms interval for smooth animation)
            if self._loading_timer is None:
                self._loading_timer = QTimer(self)
                self._loading_timer.timeout.connect(self._update_loading_animation)
            self._loading_timer.start(60)

            # Initial update
            self._update_loading_animation()
            logger.debug("Loading animation started")
        except Exception as e:
            logger.debug(f"Failed to start loading animation: {e}")

    def _stop_loading_animation(self):
        """Stop the loading animation and restore original icon."""
        try:
            if self._loading_timer is not None:
                self._loading_timer.stop()

            # Restore original icon
            if self.translate_btn and hasattr(self, "_original_icon"):
                self.translate_btn.setIcon(self._original_icon)

            logger.debug("Loading animation stopped")
        except Exception as e:
            logger.debug(f"Failed to stop loading animation: {e}")

    def _update_loading_animation(self):
        """Update the loading animation: rotate icon and cycle dots."""
        try:
            if not self.translate_btn:
                return

            # Update rotation (15 degrees per tick for slower animation)
            self._loading_rotation = (self._loading_rotation + 15) % 360

            # Rotate the icon (only in compact mode)
            is_compact = getattr(self, "_loading_compact", False)
            if is_compact and hasattr(self, "_original_icon") and self._original_icon:
                # Get pixmap from original icon
                pixmap = self._original_icon.pixmap(QSize(16, 16))
                if not pixmap.isNull():
                    # Apply rotation transform
                    transform = QTransform()
                    transform.rotate(self._loading_rotation)
                    rotated_pixmap = pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
                    from PySide6.QtGui import QIcon
                    self.translate_btn.setIcon(QIcon(rotated_pixmap))

            # Update dots (cycle every 90 degrees / 6 ticks for slower animation)
            if self._loading_rotation % 90 == 0:
                self._loading_dots_count = (self._loading_dots_count + 1) % 4

            # Update text with animated dots (only in non-compact mode)
            if not getattr(self, "_loading_compact", False):
                # Use fixed width: dots + spaces to prevent text jumping
                dots = "." * self._loading_dots_count + " " * (3 - self._loading_dots_count)
                self.translate_btn.setText(f"  {self._loading_base_text}{dots}")

            # Update status label with animated dots
            if hasattr(self, "status_label") and self.status_label:
                dots = "." * self._loading_dots_count + " " * (3 - self._loading_dots_count)
                self.status_label.setText(f"Request sent{dots}")

        except Exception as e:
            logger.debug(f"Failed to update loading animation: {e}")

    def _copy_translated_to_clipboard(self):
        """Copy translated text to clipboard."""
        self._copy_text_to_clipboard(self.translated_text, self.copy_translated_btn, "Translated")

    def _on_reader_mode_clicked(self):
        """Handle reader mode button click."""
        try:
            translated_text = self.translated_text.toPlainText().strip()
            if not translated_text:
                logger.info("Reader mode clicked with empty translated text")
                return

            from ..services.ui_service import get_ui_service
            ui_service = get_ui_service()
            if ui_service:
                ui_service.show_reader_window(translated_text)
                logger.info("Reader mode activated with translated text")
            else:
                logger.error("UI service not available")
                self.status_label.setText("Reader mode unavailable")
        except Exception as e:
            logger.error(f"Failed to open reader mode: {e}")
            self.status_label.setText("Failed to open reader")


    def dismiss(self) -> None:
        """Dismiss the overlay window, ensuring child dialogs are closed first."""
        logger.info("Dismissing overlay window")
        if self._translator_settings_dialog:
            try:
                self._translator_settings_dialog.close()
            except Exception as e:
                logger.warning(f"Could not close translator settings dialog: {e}")
        
        super().dismiss()
        logger.debug("Overlay window dismissed")

    def is_overlay_visible(self) -> bool:
        """Check if overlay is currently visible."""
        return self.isVisible()
