"""
Overlay UI Builder module for creating overlay window components.

Configuration Guidelines:
- All widget styles should be centralized in CONFIG dictionaries
- Use consistent naming: {WIDGET_TYPE}_CONFIG
- Include size, style, and any widget-specific properties
- Add objectName for widgets that need styling/testing
- Follow DRY principle - avoid hardcoded values

Key Principles:
1. Centralized Configuration: All styles in CONFIG dictionaries at class level
2. Explicit Mapping: Use explicit button-to-style mappings, not dynamic key generation
3. Unified Factory: Single _create_widget_from_config method for all widgets
4. ObjectName Usage: Set objectName for all testable/stylable widgets
5. Separation of Concerns: Python handles logic, QSS handles appearance
"""

from pathlib import Path
from typing import List, Optional

import qtawesome as qta
from loguru import logger
from PySide6.QtCore import (
    QEvent,
    QSize,
    Qt,
)
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
    QVBoxLayout,
    QListView,
)

from ..services.config_service import config_service
from ..utils.language_utils import get_supported_languages

# Base path for assets
_ASSETS_BASE = Path(__file__).parent.parent / "assets"


class TranslatorSettingsDialog(QDialog):
    """Dialog for translator-specific settings."""

    # Configuration for translator settings dialog
    TRANSLATOR_DIALOG_CONFIG = {
        'dialog': {
            'title': "Translator Settings",
            'object_name': "TranslatorSettingsDialog",
            'minimum_width': 320
        },
        'compact_view_checkbox': {
            'text': "Compact view",
            'tooltip': "Hides labels and buttons for a more compact translator window",
            'object_name': "compact_view_checkbox"
        },
        'autohide_buttons_checkbox': {
            'text': "Hide right-side buttons (show on hover)",
            'tooltip': "If enabled, the narrow buttons on the right appear only on hover",
            'object_name': "autohide_buttons_checkbox"
        },
        'close_button': {
            'text': "Close",
            'size': (None, 26),
            'object_name': "translatorCloseButton"
        }
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create builder instance for unified widget creation
        self.builder = OverlayUIBuilder()

        # Apply dialog configuration
        dialog_config = self.TRANSLATOR_DIALOG_CONFIG['dialog']
        self.setWindowTitle(dialog_config['title'])
        self.setObjectName(dialog_config['object_name'])
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMinimumWidth(dialog_config['minimum_width'])

        layout = QVBoxLayout(self)
        settings = config_service.get_settings()

        # Compact view checkbox
        self.compact_view_checkbox, _ = self.builder._create_widget_from_config('translator', 'compact_view_checkbox', QCheckBox)
        self.compact_view_checkbox.setChecked(getattr(settings, "compact_view", False))
        self.compact_view_checkbox.stateChanged.connect(self._on_compact_view_changed)
        layout.addWidget(self.compact_view_checkbox)

        # Side buttons auto-hide checkbox
        self.autohide_buttons_checkbox, _ = self.builder._create_widget_from_config('translator', 'autohide_buttons_checkbox', QCheckBox)
        self.autohide_buttons_checkbox.setChecked(getattr(settings, "overlay_side_buttons_autohide", False))
        self.autohide_buttons_checkbox.stateChanged.connect(self._on_autohide_buttons_changed)
        layout.addWidget(self.autohide_buttons_checkbox)

        # Close button
        close_button, _ = self.builder._create_widget_from_config('translator', 'close_button', QPushButton)
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

    def _on_compact_view_changed(self, state):
        """Persist compact view setting."""
        try:
            enabled = bool(state)
            config_service.set_setting("compact_view", enabled)
            logger.info(f"Compact view setting updated: {enabled}")
            parent = self.parent()
            if parent and hasattr(parent, "_update_layout"):
                getattr(parent, "_update_layout")()
        except Exception as e:
            logger.error(f"Failed to save compact view setting: {e}")

    def _on_autohide_buttons_changed(self, state):
        """Persist side-buttons auto-hide setting and apply policy immediately."""
        try:
            enabled = bool(state)
            config_service.set_setting("overlay_side_buttons_autohide", enabled)
            logger.info(f"Side buttons auto-hide updated: {enabled}")
            parent = self.parent()
            if parent and hasattr(parent, "_update_layout"):
                getattr(parent, "_update_layout")()
        except Exception as e:
            logger.error(f"Failed to save side buttons auto-hide setting: {e}")


class PanelWidget(QFrame):
    """Reusable panel with a text area and an optional side or bottom button area."""
    
    # Configuration for layout spacing and dimensions
    LAYOUT_CONFIG = {
        'main_vertical_spacing': 4,
        'main_vertical_margins': (0, 0, 0, 0),
        'top_horizontal_margins': (0, 0, 0, 0),
        'side_panel_expanded_width': 28,
        'side_panel_collapsed_width': 1,
        'side_panel_spacing': 3,
        'side_panel_margins': (0, 0, 0, 0),
        'btn_row_margins': (0, 0, 0, 0)
    }

    def __init__(self, text_edit: QTextEdit, buttons: List[QPushButton], apply_button_style_cb, parent=None):
        super().__init__(parent)
        self.text_edit = text_edit
        self.buttons = buttons
        self._apply_btn_style = apply_button_style_cb
        self.side_panel: Optional[QFrame] = None
        self.btn_row: Optional[QHBoxLayout] = None
        self._autohide = False

        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.installEventFilter(self)

        # Main structure: top (text + optional side panel), bottom (optional btn row)
        self._main_v = QVBoxLayout(self)
        self._main_v.setContentsMargins(*self.LAYOUT_CONFIG['main_vertical_margins'])
        self._main_v.setSpacing(self.LAYOUT_CONFIG['main_vertical_spacing'])

        self._top_h = QHBoxLayout()
        self._top_h.setContentsMargins(*self.LAYOUT_CONFIG['top_horizontal_margins'])
        self._top_h.addWidget(self.text_edit, 1)
        self._main_v.addLayout(self._top_h, 1)

    def _ensure_side_panel(self):
        if self.side_panel is None:
            panel = QFrame()
            panel.setFrameStyle(QFrame.Shape.NoFrame)
            panel.setFixedWidth(self.LAYOUT_CONFIG['side_panel_expanded_width'])
            v = QVBoxLayout(panel)
            v.setSpacing(self.LAYOUT_CONFIG['side_panel_spacing'])
            v.setContentsMargins(*self.LAYOUT_CONFIG['side_panel_margins'])
            v.addStretch()
            v.addStretch()
            panel.setMouseTracking(True)
            panel.installEventFilter(self)
            # Insert buttons above the bottom stretch
            for btn in self.buttons:
                v.insertWidget(v.count() - 1, btn, alignment=Qt.AlignmentFlag.AlignHCenter)
            self._top_h.addWidget(panel)
            self.side_panel = panel

    def _remove_side_panel(self):
        if self.side_panel is not None:
            layout = self.side_panel.layout()
            if layout:
                for btn in self.buttons:
                    layout.removeWidget(btn)
            self._top_h.removeWidget(self.side_panel)
            self.side_panel.deleteLater()
            self.side_panel = None

    def _ensure_btn_row(self):
        if self.btn_row is None:
            row = QHBoxLayout()
            row.setContentsMargins(*self.LAYOUT_CONFIG['btn_row_margins'])
            row.addStretch(1)
            for btn in self.buttons:
                row.addWidget(btn)
            self._main_v.addLayout(row)
            self.btn_row = row

    def _remove_btn_row(self):
        if self.btn_row is not None:
            for btn in self.buttons:
                self.btn_row.removeWidget(btn)
            self._main_v.removeItem(self.btn_row)
            self.btn_row = None

    def configure(self, compact: bool, autohide: bool):
        """Switch between compact (side panel) and full (bottom row) modes."""
        self._autohide = autohide
        if compact:
            self._remove_btn_row()
            self._ensure_side_panel()
            if self.side_panel:
                width = self.LAYOUT_CONFIG['side_panel_expanded_width'] if not autohide else self.LAYOUT_CONFIG['side_panel_collapsed_width']
                self.side_panel.setFixedWidth(width)
            for b in self.buttons:
                b.setVisible(not autohide)
                self._apply_btn_style(b, True)
        else:
            self._remove_side_panel()
            self._ensure_btn_row()
            for b in self.buttons:
                b.setVisible(True)
                self._apply_btn_style(b, False)

    def eventFilter(self, obj, event):
        # Hover-based autohide for compact mode
        try:
            autohide = getattr(self, '_autohide', False)
            side_panel = getattr(self, 'side_panel', None)
            if autohide and side_panel and obj in (self, side_panel):
                if event.type() == QEvent.Type.Enter:
                    side_panel.setFixedWidth(self.LAYOUT_CONFIG['side_panel_expanded_width'])
                    for b in self.buttons:
                        b.setVisible(True)
                elif event.type() == QEvent.Type.Leave:
                    if not side_panel.underMouse() and not self.underMouse():
                        side_panel.setFixedWidth(self.LAYOUT_CONFIG['side_panel_collapsed_width'])
                        for b in self.buttons:
                            b.setVisible(False)
        except Exception as e:
            logger.debug(f"PanelWidget eventFilter error: {e}")
        return False


class OverlayUIBuilder:
    """Builder class for creating overlay window UI components."""

    # Configuration for layout spacing and dimensions
    LAYOUT_CONFIG = {
        'info_row_margins': (0, 3, 0, 0),
        'info_row_spacer_width': 10,
        'info_row_spacer_height': 10,
        'footer_margins': (0, 0, 0, 0)
    }

    # Configuration for icons (centralized)
    ICONS_CONFIG = {
        'utility_icons': {
            'eraser': {'icon': 'fa5s.eraser', 'color': 'black'},
            'copy': {'icon': 'fa5.copy', 'color': 'black'},
            'check_success': {'icon': 'fa5s.check', 'color': 'green'},
        },
        'window_controls': {
            'settings': {'icon': 'fa5s.cog', 'color': 'black'},
            'close': {'icon': 'fa5s.times', 'color': 'black'},
            'close_hover': {'icon': 'fa5s.times', 'color': 'white'},
            'collapse': {'icon': 'fa5s.compress-alt', 'color': 'black'},
        },
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

    # Configuration for language widgets
    LANGUAGE_WIDGET_CONFIG = {
        'source_combo': {
            'size': (125, 28),
            'icon_size': (28, 28),
            'object_name': 'sourceLanguageCombo'
        },
        'target_combo': {
            'size': (125, 28),
            'icon_size': (28, 28),
            'object_name': 'targetLanguageCombo'
        },
        'swap_button': {
            'size': (35, 28),
            'icon_size': (20, 24)
        }
    }

    # Configuration for footer widgets
    FOOTER_WIDGET_CONFIG = {
        'status_label': {
            'object_name': "statusLabel"
        },
        'provider_badge': {
            'object_name': "providerBadge",
            'text': ""  # Will be set dynamically
        },
        'close_button': {
            'size': (86, 28),
            'icon_size': (16, 16),
            'object_name': "closeButton",
            'text': "Close",
            'icons': {
                'normal': ICONS_CONFIG['window_controls']['close'],
                'hover': ICONS_CONFIG['window_controls']['close_hover']
            }
        }
    }

    # Configuration for top-bar widgets
    OVERLAY_TOP_CONTROLS_CONFIG = {
        'title_label': {
            'object_name': 'overlayTitleLabel',
            'text': ''  # set by caller as needed
        },
        'settings_button': {
            'object_name': 'settingsBtnTop',
            'size': (22, 22),
            'icon': ICONS_CONFIG['window_controls']['settings'],
            'icon_size': (18, 16),
            'tooltip': 'Settings'
        },
        'close_button': {
            'object_name': 'closeBtnTop',
            'size': (22, 22),
            'icon': ICONS_CONFIG['window_controls']['close'],
            'icon_size': (20, 16),
            'tooltip': 'Close'
        },
        'collapse_button': {
            'object_name': 'collapseBtnTop',
            'size': (22, 22),
            'icon': ICONS_CONFIG['window_controls']['collapse'],
            'icon_size': (20, 16),
            'tooltip': 'Collapse'
        }
    }


    # Configuration for button styles (appearance moved to QSS; sizes/icons/text remain)
    BUTTON_STYLES = {
        'translate_compact': {
            'text': '',
            'size': (24, 24),
            'icon_size': (12, 12),
            'icon_spec': ICONS_CONFIG['translate']['all']
        },
        'translate_full': {
            'size': (120, 28),
            'icon_size': (14, 14),
            'icon_spec': ICONS_CONFIG['translate']['all']
        },
        'reader_compact': {
            'text': '',
            'size': (24, 24),
            'icon_size': (17, 17),
            'icon_spec': ICONS_CONFIG['reader']['compact']
        },
        'reader_full': {
            'text': '',
            'size': (40, 28),
            'icon_size': (19, 19),
            'tooltip': 'Open text in reader mode for comfortable reading',
            'icon_spec': ICONS_CONFIG['reader']['full']
        },
        'default_compact': {
            'text': '',
            'size': (24, 24),
            'icon_size': (15, 15)
        },
        'default_full': {
            'text': '',
            'size': (40, 28),
            'icon_size': (16, 16)
        }
    }

    # Configuration for info row widgets
    INFO_WIDGET_CONFIG = {
        'mode_combo': {
            'size': (95, 28),
            'object_name': 'modeCombo'
        },
        'style_combo': {
            'size': (95, 28),
            'object_name': 'styleCombo'
        },
        'detected_lang_label': {
            'width': 120
        },
        'mode_label': {
            'text': 'Mode:'
        },
        'auto_swap_checkbox': {
            'text': 'Auto-translate EN ↔ RU',
            'tooltip': 'If enabled, English will be translated to Russian, and Russian to English'
        }
    }

    # Configuration for text edit widgets
    TEXT_EDIT_CONFIG = {
        'object_name': 'textEdit'
    }

    # Configuration for label widgets
    LABEL_CONFIG = {
        'bold': {
            'object_name': 'boldLabel'
        },
        'original': {
            'text': 'Original:',
            'object_name': 'boldLabel'
        },
        'translation': {
            'text': 'Translation:',
            'object_name': 'boldLabel'
        }
    }

    def __init__(self):
        # Expose icons for external use (config-driven)
        self.icon_translation = self._make_icon_from_spec(self.ICONS_CONFIG['translate']['all'])
        self.icon_check_green = self._make_icon_from_spec(self.ICONS_CONFIG['utility_icons']['check_success'])

    def _load_icon(self, icon_name: str) -> QIcon:
        """Load icon from assets."""
        return QIcon(QPixmap(str(_ASSETS_BASE / "icons" / icon_name)))

    def _make_qta_icon(self, spec: dict) -> QIcon:
        """Create a qtawesome icon from spec {'icon': str, 'color': str}."""
        if not spec:
            return QIcon()
        try:
            return qta.icon(spec['icon'], color=spec.get('color'))
        except Exception:
            return QIcon()

    def _make_icon_from_spec(self, spec: dict) -> QIcon:
        """Create QIcon from spec. Supports {'icon','color'} for qtawesome or {'asset'} for PNG."""
        if not spec:
            return QIcon()
        if 'asset' in spec:
            return self._load_icon(spec['asset'])
        return self._make_qta_icon(spec)

    def _refresh_widget_style(self, widget):
        """Refresh widget style after property changes."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _apply_custom_dropdown_style(self, combo: QComboBox):
        """Apply custom styling to the dropdown view of a QComboBox."""
        view = QListView()
        combo.setView(view)
        view.window().setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        view.window().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def _create_text_edit(self, placeholder):
        """Create a QTextEdit widget."""
        text_edit = QTextEdit()
        text_edit.setReadOnly(False)
        text_edit.setAcceptRichText(False)
        text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        text_edit.setPlaceholderText(placeholder)
        text_edit.setObjectName(self.TEXT_EDIT_CONFIG['object_name'])
        return text_edit

    def _create_button(self, parent=None, text=None, icon=None, size=None, icon_size=None, tooltip=None):
        """Generic button factory. Creates buttons without explicit parent (ownership managed by layout)."""
        btn = QPushButton(parent)
        if text:
            btn.setText(text)
        if icon:
            btn.setIcon(icon)
            if icon_size:
                btn.setIconSize(QSize(*icon_size))
        if size:
            btn.setFixedSize(*size)
        if tooltip:
            btn.setToolTip(tooltip)
        return btn

    def apply_button_style(self, button: QPushButton, compact: bool):
        """Apply styling to a button based on compact mode using configuration dictionary.
        Visual appearance is controlled via QSS.
        """
        mode = 'compact' if compact else 'full'

        # Explicit mapping of buttons to their style configurations
        button_configs = {
            self.translate_btn: {
                'compact': self.BUTTON_STYLES['translate_compact'],
                'full': self.BUTTON_STYLES['translate_full']
            },
            self.reader_mode_btn: {
                'compact': self.BUTTON_STYLES['reader_compact'],
                'full': self.BUTTON_STYLES['reader_full']
            }
        }

        # Get the specific config for the button and mode
        config = button_configs.get(button, {}).get(mode)

        if not config:
            # Fallback to default styles for other buttons (clear, copy, etc.)
            config = self.BUTTON_STYLES[f'default_{mode}']

        config = config.copy()  # Work with a copy to avoid modifying the original

        # Apply size, text, tooltip, and icon from config
        if 'text' in config and config['text'] is not None:
            button.setText(config['text'])
        if 'tooltip' in config and config['tooltip']:
            button.setToolTip(config['tooltip'])
        button.setFixedSize(*config['size'])
        button.setIconSize(QSize(*config['icon_size']))
        if 'icon_spec' in config:
            button.setIcon(self._make_icon_from_spec(config['icon_spec']))

        # Set dynamic properties for QSS to pick up (mode / utility)
        try:
            button.setProperty("mode", mode)
            # utility property should already be set by creators for small action buttons;
            # ensure property exists for consistency
            if button.property("utility") is None:
                button.setProperty("utility", False)

            # Force style refresh so QSS reacts to the new properties
            self._refresh_widget_style(button)
        except Exception:
            # Avoid breaking UI flow on styling errors
            pass

    def _create_widget_from_config(self, widget_type: str, config_key: str, widget_class, **kwargs):
        """Generic widget factory using configuration dictionaries."""
        config_maps = {
            'info': self.INFO_WIDGET_CONFIG,
            'language': self.LANGUAGE_WIDGET_CONFIG,
            'footer': self.FOOTER_WIDGET_CONFIG,
            'label': self.LABEL_CONFIG,
            'top': self.OVERLAY_TOP_CONTROLS_CONFIG,
            'translator': TranslatorSettingsDialog.TRANSLATOR_DIALOG_CONFIG
        }

        config = config_maps[widget_type][config_key]
        widget = widget_class(**kwargs)

        # Apply common configuration properties
        if hasattr(widget, 'setFixedSize') and 'size' in config and config['size'] is not None:
            width, height = config['size']
            if width is not None and height is not None:
                widget.setFixedSize(width, height)
            elif width is not None:
                widget.setFixedWidth(width)
            elif height is not None:
                widget.setFixedHeight(height)
        if hasattr(widget, 'setObjectName') and 'object_name' in config:
            widget.setObjectName(config['object_name'])
        if hasattr(widget, 'setFixedWidth') and 'width' in config:
            widget.setFixedWidth(config['width'])
        if hasattr(widget, 'setIconSize') and 'icon_size' in config:
            widget.setIconSize(QSize(*config['icon_size']))
        if hasattr(widget, 'setText') and 'text' in config:
            widget.setText(config['text'])
        if hasattr(widget, 'setToolTip') and 'tooltip' in config:
            widget.setToolTip(config['tooltip'])

        return widget, config

    def _create_mode_combo(self) -> QComboBox:
        """Create mode selector combo box using config."""
        combo, _ = self._create_widget_from_config('info', 'mode_combo', QComboBox)
        combo.addItem("Translate")
        combo.addItem("Style")

        # Apply rounded corners to dropdown list
        self._apply_custom_dropdown_style(combo)

        return combo

    def _create_style_combo(self) -> QComboBox:
        """Create style presets combo box using config."""
        combo, _ = self._create_widget_from_config('info', 'style_combo', QComboBox)
        self._populate_styles(combo)
        combo.setVisible(False)  # Hidden by default; shown only in Style mode

        # Apply rounded corners to dropdown list
        self._apply_custom_dropdown_style(combo)

        return combo

    def _create_detected_lang_label(self) -> QLabel:
        """Create detected language label using config."""
        label, _ = self._create_widget_from_config('info', 'detected_lang_label', QLabel, text="Language: —")
        return label

    def _create_info_row(self):
        """Create the top info row with mode selector, style presets, language detection and auto-translate."""
        container = QFrame()
        container.setFrameStyle(QFrame.Shape.NoFrame)

        info_row = QHBoxLayout(container)
        info_row.setContentsMargins(*self.LAYOUT_CONFIG['info_row_margins'])

        # Left: Mode selector + Style presets (when Style mode is active)
        self.mode_label, _ = self._create_widget_from_config('info', 'mode_label', QLabel)
        info_row.addWidget(self.mode_label)

        self.mode_combo = self._create_mode_combo()
        info_row.addWidget(self.mode_combo)

        self.style_combo = self._create_style_combo()
        info_row.addWidget(self.style_combo)

        # Middle: stretch to push detection + auto-swap to the right
        spacer_width = self.LAYOUT_CONFIG['info_row_spacer_width']
        spacer_height = self.LAYOUT_CONFIG['info_row_spacer_height']
        info_row.addItem(QSpacerItem(spacer_width, spacer_height, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        # Right: Detected language label + Auto-translate toggle
        self.detected_lang_label = self._create_detected_lang_label()
        info_row.addWidget(self.detected_lang_label)

        self.auto_swap_checkbox, _ = self._create_widget_from_config('info', 'auto_swap_checkbox', QCheckBox)
        info_row.addWidget(self.auto_swap_checkbox)

        # Return the container widget so it can be managed uniformly (hideable_elements)
        return container


    def _create_swap_button(self) -> QPushButton:
        """Create language swap button using config."""
        swap_btn, _ = self._create_widget_from_config('language', 'swap_button', QPushButton)
        swap_btn.setIcon(self._make_icon_from_spec(self.ICONS_CONFIG['swap']))
        return swap_btn

    def _create_language_row(self):
        """Create the language selection row."""
        language_row = QHBoxLayout()
        self.original_label, _ = self._create_widget_from_config('label', 'original', QLabel)
        language_row.addWidget(self.original_label, alignment=Qt.AlignmentFlag.AlignBottom)
        language_row.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        # We create comboboxes directly from their unique configurations
        self.source_combo, _ = self._create_widget_from_config('language', 'source_combo', QComboBox)
        self.source_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.source_combo.setMaxVisibleItems(12)

        # Apply rounded corners to dropdown list
        self._apply_custom_dropdown_style(self.source_combo)

        self.target_combo, _ = self._create_widget_from_config('language', 'target_combo', QComboBox)
        self.target_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.target_combo.setMaxVisibleItems(12)

        # Apply rounded corners to dropdown list
        self._apply_custom_dropdown_style(self.target_combo)
        
        self.swap_btn = self._create_swap_button()

        language_row.addWidget(self.source_combo)
        language_row.addWidget(self.swap_btn)
        language_row.addWidget(self.target_combo)

        # Spacer for compact mode button panel
        self.language_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        language_row.addItem(self.language_spacer)

        return language_row

    def _populate_styles(self, combo: QComboBox):
        """Populate style presets from settings into the given combo box."""
        try:
            combo.clear()
            settings = config_service.get_settings()
            styles = getattr(settings, "text_styles", []) or []
            if not styles:
                combo.addItem("Improve")  # fallback display
                return
            for s in styles:
                name = (s.get("name") or "").strip() if isinstance(s, dict) else str(s)
                if name:
                    combo.addItem(name)
        except Exception as e:
            logger.warning(f"Failed to populate styles: {e}")

    def _create_status_label(self) -> QLabel:
        """Create standardized status label using config."""
        status_label, _ = self._create_widget_from_config('footer', 'status_label', QLabel, text="")
        return status_label

    def _create_provider_badge(self) -> QToolButton:
        """Create provider badge button using config."""
        # Use QToolButton for interactive badge with menu
        provider_badge, _ = self._create_widget_from_config('footer', 'provider_badge', QToolButton, text="")
        provider_badge.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        # Ensure it behaves like a label with a menu
        provider_badge.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        return provider_badge

    def _create_close_button(self) -> QPushButton:
        """Create standardized close button using config."""
        config = self.FOOTER_WIDGET_CONFIG['close_button']
        close_btn, _ = self._create_widget_from_config('footer', 'close_button', QPushButton, text=config['text'])

        # Prepare and expose hover/normal icons for external use (OverlayWindow hover handling)
        icons = config.get('icons', {})
        self.close_icon_normal = self._make_icon_from_spec(icons.get('normal'))
        self.close_icon_hover = self._make_icon_from_spec(icons.get('hover'))

        try:
            close_btn.setIcon(self.close_icon_normal)
        except Exception:
            pass
        return close_btn

    def _create_footer(self):
        """Create the footer row with provider badge, status label and close button."""
        footer_widget = QFrame()
        footer_widget.setFrameStyle(QFrame.Shape.NoFrame)
        footer_row = QHBoxLayout(footer_widget)
        footer_row.setContentsMargins(*self.LAYOUT_CONFIG['footer_margins'])

        self.provider_badge = self._create_provider_badge()
        footer_row.addWidget(self.provider_badge)

        self.status_label = self._create_status_label()
        footer_row.addWidget(self.status_label)
        footer_row.addStretch()

        close_btn = self._create_close_button()
        footer_row.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        return footer_widget, close_btn

    def init_language_controls(self):
        """Populate and configure language selection combos."""
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
        self.set_combo_data(self.source_combo, ui_source_language)
        if self.source_combo.currentData() != ui_source_language:
            self.set_combo_data(self.source_combo, "en")

        ui_target_language = getattr(settings, "ui_target_language", "en")
        self.set_combo_data(self.target_combo, ui_target_language)
        if self.target_combo.currentData() != ui_target_language:
            self.set_combo_data(self.target_combo, "en")

    def set_combo_data(self, combo, data_value):
        """Set combo to the index matching the data value, with signal blocking."""
        combo.blockSignals(True)
        try:
            for i in range(combo.count()):
                if combo.itemData(i) == data_value:
                    combo.setCurrentIndex(i)
                    break
        finally:
            combo.blockSignals(False)

    def apply_disabled_translate_visuals(self, button: QPushButton, reason_msg: str, compact: bool) -> None:
        """Apply strong disabled visuals for the Translate/Style button.
        Visuals are controlled by QSS; here we set state, properties and the lock icon.
        """
        if not button:
            return

        try:
            # Set logical disabled property (not actual disabled state to preserve cursor events)
            button.setProperty("logically_disabled", True)
            button.setCursor(Qt.CursorShape.ForbiddenCursor)
            button.setToolTip(reason_msg or self.DEFAULT_DISABLED_TOOLTIP)

            # Set mode property so QSS selects the appropriate disabled appearance
            mode = 'compact' if compact else 'full'
            button.setProperty("mode", mode)

            # Set lock icon as visual indicator for disabled translate (from config spec)
            icon_spec = self.ICONS_CONFIG['translate_disabled'].get(mode)
            if icon_spec:
                button.setIcon(self._make_icon_from_spec(icon_spec))

            # Force style refresh
            self._refresh_widget_style(button)
        except Exception as e:
            logger.debug(f"Failed to apply disabled translate visuals: {e}")

    def get_translate_button_text(self, is_style: bool = False) -> str:
        """Get text for translate button with leading spaces for alignment."""
        return "  Style" if is_style else "  Translate"

    def restore_enabled_translate_visuals(self, button: QPushButton, compact: bool) -> None:
        """Restore normal visuals for the Translate/Style button."""
        if not button:
            return
    
        try:
            # Remove logical disabled property (re-enable cursor events)
            button.setProperty("logically_disabled", False)
            button.setCursor(Qt.CursorShape.ArrowCursor)
            button.setToolTip("")
    
            # Ensure compact property is updated and re-apply sizes/icons
            self.apply_button_style(button, compact)
    
            # Only restore translation icon for translate button, not for reader button
            if button == self.translate_btn:
                button.setIcon(self._make_icon_from_spec(self.ICONS_CONFIG['translate']['all']))
    
            # Refresh style
            self._refresh_widget_style(button)
        except Exception as e:
            logger.debug(f"Failed to restore enabled translate visuals: {e}")

    def apply_status_style(self, status_label: QLabel, style_type: str) -> None:
        """Apply centralized styling to status label based on type using dynamic properties."""
        if not status_label:
            return

        try:
            # Set a dynamic property to control styling via QSS
            status_label.setProperty("status", style_type)
            # Force a style refresh to apply the new property-based style
            self._refresh_widget_style(status_label)
        except Exception as e:
            logger.debug(f"Failed to apply status style: {e}")

    def create_top_label(self, text: str = "") -> QLabel:
        """Create a top-bar title label using config."""
        lbl, cfg = self._create_widget_from_config('top', 'title_label', QLabel, text=text)
        return lbl

    def create_top_button(self, key: str) -> QPushButton:
        """Create a top-bar button using config."""
        btn, cfg = self._create_widget_from_config('top', key, QPushButton)
        if 'icon' in cfg:
            btn.setIcon(self._make_icon_from_spec(cfg['icon']))
        if 'icon_size' in cfg:
            btn.setIconSize(QSize(*cfg['icon_size']))
        # Preserve legacy QSS: do not set extra properties that could change styling
        self._refresh_widget_style(btn)
        return btn

    def _create_main_buttons(self):
        """Create main action buttons (translate and reader mode)."""
        self.translate_btn = self._create_button(text="  Translate")
        self.translate_btn.setObjectName("translateButton")

        self.reader_mode_btn = self._create_button(text="")
        # Use a stable object name for QSS selectors
        self.reader_mode_btn.setObjectName("readerButton")
        # Mark as utility=false by default; compact/full visual will be applied later
        self.reader_mode_btn.setProperty("utility", False)
        self.reader_mode_btn.setEnabled(False)  # Disable by default if no translated text

    def _create_utility_buttons(self):
        """Create utility buttons (clear and copy)."""
        self.clear_original_btn = self._create_button(
            text="",
            icon=self._make_icon_from_spec(self.ICONS_CONFIG['utility_icons']['eraser']),
            tooltip="Clear text"
        )
        self.copy_original_btn = self._create_button(
            text="",
            icon=self._make_icon_from_spec(self.ICONS_CONFIG['utility_icons']['copy']),
            tooltip="Copy text"
        )
        self.clear_translated_btn = self._create_button(
            text="",
            icon=self._make_icon_from_spec(self.ICONS_CONFIG['utility_icons']['eraser']),
            tooltip="Clear text"
        )
        self.copy_translated_btn = self._create_button(
            text="",
            icon=self._make_icon_from_spec(self.ICONS_CONFIG['utility_icons']['copy']),
            tooltip="Copy text"
        )

        # Mark utility buttons so QSS can style them as compact/utility actions
        for btn in (self.clear_original_btn, self.copy_original_btn, self.clear_translated_btn, self.copy_translated_btn):
            btn.setProperty("utility", True)

    def _create_text_widgets(self):
        """Create text edit widgets and labels."""
        self.original_text = self._create_text_edit("Recognized text will appear here...")
        self.translated_text = self._create_text_edit("Translation will appear here...")

        self.translated_label, _ = self._create_widget_from_config('label', 'translation', QLabel)

    def _create_panels(self, owner):
        """Create panel widgets for organizing buttons and text areas."""
        self.original_buttons = [self.translate_btn, self.clear_original_btn, self.copy_original_btn]
        self.translated_buttons = [self.reader_mode_btn, self.clear_translated_btn, self.copy_translated_btn]

        self.original_panel = PanelWidget(self.original_text, self.original_buttons, self.apply_button_style, parent=owner)
        self.translated_panel = PanelWidget(self.translated_text, self.translated_buttons, self.apply_button_style, parent=owner)

    def build_ui(self, owner):
        """Build and return all UI components for the overlay window.

        The builder creates all widgets and returns them in a dict.
        Ownership is transferred to the overlay window, which manages signals, layout, and lifecycle.
        """
        # Create main UI widgets
        info_row = self._create_info_row()
        language_row = self._create_language_row()

        self._create_text_widgets()
        self._create_main_buttons()
        self._create_utility_buttons()
        self._create_panels(owner)

        # Initialize language controls after creating combos
        self.init_language_controls()

        footer_widget, close_btn = self._create_footer()

        # Return all created components
        return {
            'info_row': info_row,
            'language_row': language_row,
            'original_panel': self.original_panel,
            'translated_label': self.translated_label,
            'translated_panel': self.translated_panel,
            'footer_widget': footer_widget,
            'close_btn': close_btn,
            'hideable_elements': [info_row, self.original_label, self.translated_label, footer_widget]
        }