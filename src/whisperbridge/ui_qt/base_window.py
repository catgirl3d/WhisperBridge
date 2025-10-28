from PySide6.QtCore import QEvent

class BaseWindow:
    """
    Mixin class that provides a unified way to hide windows.
    """
    def dismiss(self):
        """
        Generic method to hide or dismiss the window.
        Override this in subclasses.
        """
        self.hide()

    def closeEvent(self, event):
        """
        Standardized handler for the close event.
        Calls dismiss() to apply the unified logic.
        """
        self.dismiss()
        event.ignore()  # Ignore the event so as not to close the application