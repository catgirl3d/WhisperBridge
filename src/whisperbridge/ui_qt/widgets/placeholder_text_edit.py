from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import QTextEdit


class PlaceholderTextEdit(QTextEdit):
    """QTextEdit with explicit, font-synced placeholder rendering.

    Qt paints `placeholderText` through a separate internal path from normal document
    text. This widget keeps both paths aligned by owning placeholder painting and by
    synchronizing the document default font whenever the widget font changes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._placeholder_text = ""
        self._is_preediting = False

    def placeholderText(self) -> str:
        """Return the logical placeholder text stored by this widget."""
        return self._placeholder_text

    def setPlaceholderText(self, placeholder_text: str) -> None:
        """Store placeholder text and disable Qt's implicit placeholder paint path."""
        self._placeholder_text = placeholder_text or ""
        super().setPlaceholderText("")
        self.viewport().update()

    def apply_font_point_size(self, point_size: int) -> None:
        """Apply a point size to the widget font and sync document rendering."""
        updated_font = QFont(self.font())
        if updated_font.pointSize() == point_size:
            return

        updated_font.setPointSize(point_size)
        self.setFont(updated_font)

    def setFont(self, font) -> None:
        """Keep document text and placeholder rendering aligned with widget font."""
        super().setFont(font)
        self._sync_font_rendering()

    def _sync_font_rendering(self) -> None:
        """Sync the QTextDocument and viewport repaint with the current widget font."""
        self.document().setDefaultFont(self.font())
        self.viewport().update()
        self.update()

    def _should_draw_placeholder(self) -> bool:
        """Return whether the placeholder should be drawn in the viewport."""
        return bool(self._placeholder_text) and self.document().isEmpty() and not self._is_preediting

    def _placeholder_text_rect(self):
        """Return the viewport text rect used for placeholder drawing."""
        margin = int(self.document().documentMargin())
        return self.viewport().rect().adjusted(margin, margin, -margin, -margin)

    def _draw_placeholder(self, painter) -> None:
        """Draw the placeholder using the current widget font and placeholder color."""
        painter.setPen(self.palette().placeholderText().color())
        painter.setFont(self.font())
        painter.drawText(
            self._placeholder_text_rect(),
            Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            self._placeholder_text,
        )

    def paintEvent(self, event) -> None:
        """Paint placeholder text using the widget's current font."""
        super().paintEvent(event)

        if not self._should_draw_placeholder():
            return

        with QPainter(self.viewport()) as painter:
            self._draw_placeholder(painter)

    def inputMethodEvent(self, event) -> None:
        """Mirror QTextEdit behavior by hiding placeholder during IME preedit."""
        self._is_preediting = bool(event.preeditString())
        try:
            super().inputMethodEvent(event)
        finally:
            self.viewport().update()
