from typing import Optional

from PySide6.QtWidgets import QLineEdit
from PySide6.QtCore import Qt, Signal
from loguru import logger

from ...utils.keyboard_utils import KeyboardUtils

class HotkeyEdit(QLineEdit):
    """
    A custom QLineEdit for recording global hotkeys.
    It captures physical key presses and formats them as a string.
    """
    hotkeyChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Click and press keys...")
        self._set_style()

    def _set_style(self):
        self.setStyleSheet("""
            HotkeyEdit {
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 4px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
            HotkeyEdit:focus {
                border: 1px solid #0078d4;
            }
        """)

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        logger.debug(f"HotkeyEdit: keyPressEvent key={key}, modifiers={modifiers}")
        
        # Ignore individual modifier presses as final keys
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            self._update_display(modifiers)
            return

        # ESC to clear
        if key == Qt.Key_Escape:
            logger.debug("HotkeyEdit: ESC pressed, clearing hotkey")
            self.clear_hotkey()
            return

        # Backspace/Delete to clear
        if key in (Qt.Key_Backspace, Qt.Key_Delete):
            logger.debug("HotkeyEdit: Backspace/Delete pressed, clearing hotkey")
            self.clear_hotkey()
            return

        # Build combination string
        parts = []
        
        if modifiers & Qt.ControlModifier:
            parts.append("ctrl")
        if modifiers & Qt.AltModifier:
            parts.append("alt")
        if modifiers & Qt.ShiftModifier:
            parts.append("shift")
        if modifiers & Qt.MetaModifier:
            parts.append("win")

        # Get key name
        # Priority: Native VK (physical key) -> Qt Key Map
        key_text = None
        native_vk = event.nativeVirtualKey()
        if native_vk:
            key_text = KeyboardUtils.get_name_from_vk(native_vk)
            if key_text:
                logger.debug(f"HotkeyEdit: Mapped native VK {native_vk} to '{key_text}'")
        
        if not key_text:
            key_text = self._qt_key_to_str(key)
            
        if key_text:
            parts.append(key_text)
            
        hotkey_str = "+".join(parts)
        logger.debug(f"HotkeyEdit: Recording new hotkey: '{hotkey_str}'")
        self._recording = False  # Actual key pressed, finalize
        self.setText(hotkey_str)
        self.hotkeyChanged.emit(hotkey_str)
        
        # Clear focus to stop recording
        self.clearFocus()

    def _update_display(self, modifiers):
        parts = []
        if modifiers & Qt.ControlModifier:
            parts.append("ctrl")
        if modifiers & Qt.AltModifier:
            parts.append("alt")
        if modifiers & Qt.ShiftModifier:
            parts.append("shift")
        if modifiers & Qt.MetaModifier:
            parts.append("win")
            
        display_text = "+".join(parts) + "+..." if parts else ""
        logger.debug(f"HotkeyEdit: Updating display with modifiers: '{display_text}'")
        self.setText(display_text)

    def clear_hotkey(self):
        self.setText("")
        self.hotkeyChanged.emit("")
        self.clearFocus()

    def focusInEvent(self, event):
        """Pause global hotkeys and show recording state."""
        super().focusInEvent(event)
        logger.debug("HotkeyEdit: Focus gained, pausing global hotkeys")
        
        self._temp_original_hotkey = self.text()
        self.setText("<Press keys...>")
        self._recording = True
        
        try:
            from ..app import get_qt_app
            app = get_qt_app()
            # Use hasattr() to safely check if hotkey_service exists and is not None
            if app and app.services and hasattr(app.services, 'hotkey_service') and app.services.hotkey_service:
                app.services.hotkey_service.set_paused(True)
        except Exception as e:
            logger.debug(f"HotkeyEdit: Failed to pause hotkeys: {e}")

    def focusOutEvent(self, event):
        """Resume global hotkeys and restore if cancelled."""
        super().focusOutEvent(event)
        logger.debug("HotkeyEdit: Focus lost, resuming global hotkeys")
        
        # If we lost focus without pressing any non-modifier keys
        if getattr(self, '_recording', False):
            self.setText(getattr(self, '_temp_original_hotkey', ""))
            self._recording = False
            
        try:
            from ..app import get_qt_app
            app = get_qt_app()
            # Use hasattr() to safely check if hotkey_service exists and is not None
            if app and app.services and hasattr(app.services, 'hotkey_service') and app.services.hotkey_service:
                app.services.hotkey_service.set_paused(False)
        except Exception as e:
            logger.debug(f"HotkeyEdit: Failed to resume hotkeys: {e}")

    def _qt_key_to_str(self, key) -> Optional[str]:
        # Map Qt keys to our internal string format (which WIN_VK_MAP understands)
        if Qt.Key_A <= key <= Qt.Key_Z:
            return chr(key).lower()
        if Qt.Key_0 <= key <= Qt.Key_9:
            return chr(key)
        if Qt.Key_F1 <= key <= Qt.Key_F12:
            return f"f{key - Qt.Key_F1 + 1}"
        
        # Special keys
        map_special = {
            Qt.Key_Space: "space",
            Qt.Key_Return: "enter",
            Qt.Key_Enter: "enter",
            Qt.Key_Tab: "tab",
            Qt.Key_Up: "up",
            Qt.Key_Down: "down",
            Qt.Key_Left: "left",
            Qt.Key_Right: "right",
            Qt.Key_Home: "home",
            Qt.Key_End: "end",
            Qt.Key_PageUp: "pageup",
            Qt.Key_PageDown: "pagedown",
            Qt.Key_Insert: "insert",
        }
        return map_special.get(key)
