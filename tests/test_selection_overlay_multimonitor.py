"""Tests for multi-monitor geometry behavior in selection overlay."""

from PySide6.QtCore import QPoint, QRect

from whisperbridge.ui_qt.selection_overlay import SelectionOverlayQt


class _FakeScreen:
    """Simple fake screen object exposing only needed geometry API."""

    def __init__(self, virtual_rect: QRect):
        self._virtual_rect = virtual_rect

    def virtualGeometry(self) -> QRect:
        return self._virtual_rect


def test_selection_overlay_uses_virtual_desktop_geometry(qapp, mocker):
    """Selection overlay should span whole virtual desktop across monitors."""
    virtual_rect = QRect(-1920, 0, 3840, 1080)
    fake_screen = _FakeScreen(virtual_rect)

    mocker.patch(
        "whisperbridge.ui_qt.selection_overlay.QGuiApplication.primaryScreen",
        return_value=fake_screen,
    )

    overlay = SelectionOverlayQt()

    assert overlay.virtual_geometry == virtual_rect
    assert overlay.geometry() == virtual_rect


def test_selection_size_label_prefers_outside_above_selection(qapp):
    """Label anchor should be placed above selection (outside highlighted area)."""
    overlay = SelectionOverlayQt()
    overlay.setGeometry(QRect(0, 0, 500, 300))
    rect = QRect(100, 120, 300, 100)

    # Simulate text size from painter boundingRect
    text_rect = QRect(0, 0, 80, 20)

    label_rect = overlay._select_size_label_rect(rect, text_rect)

    assert label_rect is not None
    assert label_rect.x() == rect.left()
    assert label_rect.y() == rect.top() - text_rect.height() - overlay.SIZE_TEXT_MARGIN


def test_selection_size_label_hidden_when_no_space_above(qapp):
    """When above area is unavailable, selector should fall back below selection."""
    overlay = SelectionOverlayQt()
    overlay.setGeometry(QRect(0, 0, 300, 200))
    rect = QRect(40, 5, 120, 60)
    text_rect = QRect(0, 0, 80, 20)

    label_rect = overlay._select_size_label_rect(rect, text_rect)

    assert label_rect is not None
    assert label_rect.y() == rect.bottom() + overlay.SIZE_TEXT_MARGIN + 1


def test_selection_size_label_falls_back_to_top_right(qapp):
    """When top-left is out of bounds, label should move to top-right."""
    overlay = SelectionOverlayQt()

    # Force narrow overlay bounds to invalidate top-left but keep top-right valid
    overlay.setGeometry(QRect(0, 0, 120, 100))
    selection = QRect(-20, 40, 100, 30)
    text_rect = QRect(0, 0, 50, 14)

    label_rect = overlay._select_size_label_rect(selection, text_rect)

    assert label_rect is not None
    assert label_rect.x() == selection.right() - text_rect.width() + 1
    assert label_rect.y() == selection.top() - text_rect.height() - overlay.SIZE_TEXT_MARGIN


def test_selection_size_label_falls_back_to_bottom_left(qapp):
    """When top candidates are invalid, label should use bottom-left if available."""
    overlay = SelectionOverlayQt()
    overlay.setGeometry(QRect(0, 0, 200, 100))

    # Near top border -> top positions invalid, bottom-left valid
    selection = QRect(20, 4, 80, 40)
    text_rect = QRect(0, 0, 60, 18)

    label_rect = overlay._select_size_label_rect(selection, text_rect)

    assert label_rect is not None
    assert label_rect.x() == selection.left()
    assert label_rect.y() == selection.bottom() + overlay.SIZE_TEXT_MARGIN + 1


def test_selection_size_label_hidden_when_no_external_space(qapp):
    """Label should be hidden if none of four external positions fit."""
    overlay = SelectionOverlayQt()
    overlay.setGeometry(QRect(0, 0, 80, 40))
    selection = QRect(10, 5, 30, 20)
    text_rect = QRect(0, 0, 90, 30)

    label_rect = overlay._select_size_label_rect(selection, text_rect)

    assert label_rect is None


def test_selection_size_label_falls_back_to_bottom_right(qapp):
    """When left-side candidates are invalid, selector should use bottom-right."""
    overlay = SelectionOverlayQt()
    overlay.setGeometry(QRect(0, 0, 120, 80))

    # top-left/top-right are out (negative y), bottom-left is out (negative x),
    # bottom-right remains valid.
    selection = QRect(-10, 2, 110, 20)
    text_rect = QRect(0, 0, 30, 10)

    label_rect = overlay._select_size_label_rect(selection, text_rect)

    assert label_rect is not None
    assert label_rect.x() == selection.right() - text_rect.width() + 1
    assert label_rect.y() == selection.bottom() + overlay.SIZE_TEXT_MARGIN + 1


def test_selection_overlay_start_uses_frozen_rect_geometry(qapp):
    """Freeze-frame start should align overlay geometry with frozen capture bounds."""
    overlay = SelectionOverlayQt()

    class _FrozenRect:
        x = -1920
        y = 0
        width = 3840
        height = 1080

    overlay.start(frozen_image=None, frozen_rect=_FrozenRect())

    assert overlay.virtual_geometry == QRect(-1920, 0, 3840, 1080)
    assert overlay.geometry() == QRect(-1920, 0, 3840, 1080)


def test_selection_overlay_dismiss_clears_transient_state(qapp):
    """Dismiss should clear selection state and frozen pixmap buffer."""
    overlay = SelectionOverlayQt()
    overlay.selection_start = QPoint(10, 20)
    overlay.selection_end = QPoint(50, 80)
    overlay.is_selecting = True
    overlay._frozen_background_pixmap = object()

    overlay.dismiss()

    assert overlay.selection_start is None
    assert overlay.selection_end is None
    assert overlay.is_selecting is False
    assert overlay._frozen_background_pixmap is None


def test_qimage_rgba8888_format_fallback_to_enum_container(mocker):
    """Format resolver should support enum-container style PySide API."""

    class _FakeQImage:
        Format_RGBA8888 = None

        class Format:
            Format_RGBA8888 = 777

    mocker.patch("whisperbridge.ui_qt.selection_overlay.QImage", _FakeQImage)

    assert SelectionOverlayQt._get_qimage_rgba8888_format() == 777
