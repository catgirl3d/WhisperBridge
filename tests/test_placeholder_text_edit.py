from PySide6.QtGui import QFont

from whisperbridge.ui_qt.widgets.placeholder_text_edit import PlaceholderTextEdit


class FakePainter:
    def __init__(self):
        self.pen = None
        self.font = None
        self.draw_calls = []

    def setPen(self, pen):
        self.pen = pen

    def setFont(self, font):
        self.font = font

    def drawText(self, rect, flags, text):
        self.draw_calls.append((rect, flags, text))


def test_placeholder_text_edit_keeps_logical_placeholder_text(qapp):
    """Custom placeholder text edit should store and return placeholder text."""
    widget = PlaceholderTextEdit()
    widget.setPlaceholderText("Translation will appear here...")

    assert widget.placeholderText() == "Translation will appear here..."


def test_placeholder_text_edit_draws_placeholder_with_widget_font(qapp):
    """Placeholder drawing should use the current widget font and stored placeholder."""
    widget = PlaceholderTextEdit()
    widget.resize(320, 120)
    widget.setPlaceholderText("Translation will appear here...")

    updated_font = QFont(widget.font())
    updated_font.setPointSize(22)
    widget.setFont(updated_font)

    fake_painter = FakePainter()
    widget._draw_placeholder(fake_painter)

    assert widget.font().pointSize() == 22
    assert widget.document().defaultFont().pointSize() == 22
    assert fake_painter.font.pointSize() == 22
    assert len(fake_painter.draw_calls) == 1
    _, flags, text = fake_painter.draw_calls[0]
    assert flags
    assert text == "Translation will appear here..."


def test_placeholder_text_edit_only_draws_placeholder_when_document_is_empty(qapp):
    """Placeholder should disappear once the widget contains text."""
    widget = PlaceholderTextEdit()
    widget.setPlaceholderText("Translation will appear here...")

    assert widget._should_draw_placeholder()

    widget.setPlainText("ready")

    assert not widget._should_draw_placeholder()


def test_placeholder_text_edit_hides_placeholder_during_preedit(qapp):
    """Placeholder should be suppressed while an IME preedit session is active."""
    widget = PlaceholderTextEdit()
    widget.setPlaceholderText("Translation will appear here...")
    widget._is_preediting = True

    assert not widget._should_draw_placeholder()


def test_placeholder_text_edit_apply_font_point_size_updates_document_font(qapp):
    """The helper should keep widget and document font sizes aligned."""
    widget = PlaceholderTextEdit()

    widget.apply_font_point_size(19)

    assert widget.font().pointSize() == 19
    assert widget.document().defaultFont().pointSize() == 19
