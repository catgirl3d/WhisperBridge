"""Tests for multi-monitor coordinate conversion logic in screen utils."""

from PySide6.QtCore import QPoint, QRect

from whisperbridge.utils.screen_utils import ScreenUtils


class _FakeScreen:
    """Minimal fake QScreen replacement for DPR/geometry tests."""

    def __init__(self, geometry: QRect, dpr: float):
        self._geometry = geometry
        self._dpr = dpr

    def geometry(self) -> QRect:
        return self._geometry

    def devicePixelRatio(self) -> float:
        return self._dpr


class _FakeRect:
    """Minimal QRect-like object for deterministic conversion testing."""

    def __init__(self, x: int, y: int, width: int, height: int):
        self._x = x
        self._y = y
        self._w = width
        self._h = height

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y

    def width(self) -> int:
        return self._w

    def height(self) -> int:
        return self._h

    def center(self) -> QPoint:
        return QPoint(self._x + self._w // 2, self._y + self._h // 2)


def test_convert_rect_to_pixels_multimonitor_keeps_virtual_offset(mocker):
    """Conversion should scale local coordinates without scaling virtual monitor offset."""
    rect = _FakeRect(100, 100, 200, 80)
    # Secondary monitor starts at x=80 in virtual desktop and has DPR=1.5
    fake_screen = _FakeScreen(QRect(80, 0, 1920, 1080), dpr=1.5)

    pixel_x, pixel_y, pixel_width, pixel_height = ScreenUtils.convert_rect_to_pixels(rect, screen=fake_screen)

    assert pixel_x == 110  # 80 + int((100-80)*1.5)
    assert pixel_y == 150  # 0 + int((100-0)*1.5)
    assert pixel_width == 300
    assert pixel_height == 120


def test_convert_rect_to_pixels_uses_screen_resolution_helper(mocker):
    """When screen is not passed explicitly, helper should resolve and be used."""
    rect = _FakeRect(-1900, 120, 100, 40)
    fake_screen = _FakeScreen(QRect(-1920, 0, 1920, 1080), dpr=1.25)

    helper = mocker.patch.object(ScreenUtils, "_get_screen_for_rect", return_value=fake_screen)

    result = ScreenUtils.convert_rect_to_pixels(rect)

    helper.assert_called_once_with(rect)
    assert result == (-1895, 150, 125, 50)


def test_convert_rect_to_pixels_fallback_without_screen(mocker):
    """If screen cannot be resolved, conversion should keep logical coordinates."""
    rect = _FakeRect(-50, 20, 120, 60)
    mocker.patch.object(ScreenUtils, "_get_screen_for_rect", return_value=None)

    assert ScreenUtils.convert_rect_to_pixels(rect) == (-50, 20, 120, 60)

