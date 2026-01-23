"""
Data transfer object for overlay UI components.

This module provides a typed container for all UI components created by OverlayUIBuilder,
eliminating the need for direct attribute access to the builder instance.
"""

from dataclasses import dataclass
from typing import List, TYPE_CHECKING

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpacerItem,
    QTextEdit,
    QToolButton,
)

# Forward reference for PanelWidget (defined in overlay_ui_builder.py)
if TYPE_CHECKING:
    from .overlay_ui_builder import PanelWidget


@dataclass
class OverlayUIComponents:
    """
    Container for all UI components created by OverlayUIBuilder.
    
    Provides a clean interface between builder and window,
    eliminating direct attribute access to builder instance.
    This follows the Data Transfer Object pattern for better
    separation of concerns and improved testability.
    
    Total: 35 fields organized into logical groups.
    """
    
    # === Layout containers (3 fields) ===
    info_row: QFrame
    language_row: QHBoxLayout
    footer_widget: QFrame
    
    # === Info row widgets (6 fields) ===
    mode_label: QLabel
    mode_combo: QComboBox
    style_combo: QComboBox
    edit_styles_btn: QPushButton
    detected_lang_label: QLabel
    auto_swap_checkbox: QCheckBox
    
    # === Language row widgets (5 fields) ===
    source_combo: QComboBox
    target_combo: QComboBox
    swap_btn: QPushButton
    original_label: QLabel
    language_spacer: QSpacerItem
    
    # === Text panels (5 fields) ===
    original_text: QTextEdit
    translated_text: QTextEdit
    translated_label: QLabel
    original_panel: "PanelWidget"
    translated_panel: "PanelWidget"
    
    # === Action buttons (8 fields) ===
    translate_btn: QPushButton
    reader_mode_btn: QPushButton
    clear_original_btn: QPushButton
    copy_original_btn: QPushButton
    clear_translated_btn: QPushButton
    copy_translated_btn: QPushButton
    original_buttons: List[QPushButton]
    translated_buttons: List[QPushButton]
    
    # === Footer widgets (3 fields) ===
    status_label: QLabel
    provider_badge: QToolButton
    close_btn: QPushButton
    
    # === Icons (4 fields) ===
    icon_translation: QIcon
    icon_check_green: QIcon
    close_icon_normal: QIcon
    close_icon_hover: QIcon
    
    # === Hideable elements for compact mode (1 field) ===
    hideable_elements: List[QFrame]
