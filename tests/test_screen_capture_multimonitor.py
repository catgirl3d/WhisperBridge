"""Unit tests for Qt-based multi-monitor screen capture."""

from __future__ import annotations

import pytest
from unittest.mock import Mock
from PIL import Image
from PySide6.QtCore import QRect

from whisperbridge.services.screen_capture_service import Rectangle, ScreenCaptureService


@pytest.fixture
def capture_service():
    """Create a ScreenCaptureService instance for testing."""
    return ScreenCaptureService()


class _FakePixmap:
    """Minimal fake pixmap for capture composition tests."""

    def __init__(self, is_null: bool = False, width: int = 0, height: int = 0):
        self._is_null = is_null
        self._width = width
        self._height = height

    def isNull(self) -> bool:
        return self._is_null

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height


class _FakeScreen:
    """Minimal fake screen with geometry and grabWindow tracking."""

    def __init__(
        self,
        geom: QRect,
        pixmap: _FakePixmap | None = None,
        dpr: float = 1.0,
    ):
        self._geom = geom
        self._pixmap = pixmap or _FakePixmap(False)
        self._dpr = dpr
        self.grab_calls = []

    def geometry(self) -> QRect:
        return self._geom

    def grabWindow(self, win_id, x, y, width, height):
        self.grab_calls.append((win_id, x, y, width, height))
        return self._pixmap

    def devicePixelRatio(self) -> float:
        return self._dpr


class _FakeQImage:
    """Minimal fake QImage for painter flow and bytes conversion."""

    Format_ARGB32 = object()

    def __init__(self, size, fmt):
        self._w = size.width()
        self._h = size.height()
        self._bytes = b"\x00\x00\x00\x00" * (self._w * self._h)

    def fill(self, *_args, **_kwargs):
        return None

    def width(self) -> int:
        return self._w

    def height(self) -> int:
        return self._h

    def sizeInBytes(self) -> int:
        return len(self._bytes)

    class _Ptr:
        def __init__(self, payload: bytes):
            self._payload = payload

        def setsize(self, _size: int):
            return None

        def __bytes__(self):
            return self._payload

    def bits(self):
        return self._Ptr(self._bytes)


class _FakeQImageMemoryViewBits(_FakeQImage):
    """QImage fake where bits() behaves like memoryview (no setsize)."""

    def bits(self):
        return memoryview(self._bytes)


class _FakePainter:
    """Minimal fake QPainter that records draw calls."""

    def __init__(self, _image):
        self.draw_calls = []

    def drawPixmap(self, *args):
        # Support both signatures used by QPainter:
        # - drawPixmap(x, y, pixmap)
        # - drawPixmap(x, y, w, h, pixmap)
        self.draw_calls.append(args)

    def end(self):
        return None


class _FakeGuiApp:
    """Minimal fake QGuiApplication with configurable screens."""

    def __init__(self, screens):
        self._screens = screens

    def screens(self):
        return self._screens


def test_qt_capture_composes_from_multiple_screens(capture_service, mocker):
    """Capture should compose image parts from all intersecting screens."""
    left = _FakeScreen(QRect(-1920, 0, 1920, 1080))
    right = _FakeScreen(QRect(0, 0, 1920, 1080))

    mocker.patch("whisperbridge.services.screen_capture_service.QT_AVAILABLE", True)
    mocker.patch.object(
        ScreenCaptureService,
        "_get_qt_gui_app",
        return_value=_FakeGuiApp([left, right]),
    )
    mocker.patch("whisperbridge.services.screen_capture_service.QImage", _FakeQImage)
    mocker.patch("whisperbridge.services.screen_capture_service.QPainter", _FakePainter)

    region = Rectangle(x=-100, y=10, width=200, height=50)
    result = capture_service.capture_area(region)

    assert result.success is True
    assert isinstance(result.image, Image.Image)
    assert result.image.size == (200, 50)

    # Left screen captures [-100..0], right captures [0..100]
    assert len(left.grab_calls) == 1
    assert len(right.grab_calls) == 1
    assert left.grab_calls[0][1:] == (1820, 10, 100, 50)
    assert right.grab_calls[0][1:] == (0, 10, 100, 50)


def test_qt_capture_uses_qt_bounds_when_platform_bounds_differ(capture_service, mocker):
    """Capture remains correct when platform bounds and Qt bounds are desynchronized.

    Regression: selected-area clamping must not depend on platform monitor bounds,
    otherwise mixed-DPI / multi-monitor setups can clip valid Qt logical regions
    to zero and fail capture.
    """

    # Qt sees the right monitor in logical space.
    right = _FakeScreen(QRect(1920, 0, 1920, 1080), pixmap=_FakePixmap(False))

    # Simulate stale/mismatched platform bounds source that would incorrectly
    # zero-out this region if used for clamping.
    mocker.patch(
        "whisperbridge.services.screen_capture_service.ScreenUtils.clamp_rectangle_to_screen",
        return_value=Rectangle(0, 0, 0, 0),
    )

    mocker.patch("whisperbridge.services.screen_capture_service.QT_AVAILABLE", True)
    mocker.patch.object(
        ScreenCaptureService,
        "_get_qt_gui_app",
        return_value=_FakeGuiApp([right]),
    )
    mocker.patch("whisperbridge.services.screen_capture_service.QImage", _FakeQImage)
    mocker.patch("whisperbridge.services.screen_capture_service.QPainter", _FakePainter)

    # Region fully inside Qt logical geometry of the right screen.
    region = Rectangle(x=2000, y=20, width=120, height=40)
    result = capture_service.capture_area(region)

    assert result.success is True
    assert isinstance(result.image, Image.Image)
    assert result.image.size == (120, 40)
    assert len(right.grab_calls) == 1
    assert right.grab_calls[0][1:] == (80, 20, 120, 40)


def test_qt_capture_mixed_dpi_uses_logical_destination_sizes(capture_service, mocker):
    """Capture should draw each screen fragment into explicit logical target sizes.

    This protects composition correctness when high-DPI screens return larger
    physical pixmaps for the same logical intersection region.
    """

    # Left monitor (DPR=1.0), right monitor (DPR=2.0)
    left = _FakeScreen(
        QRect(0, 0, 1920, 1080),
        pixmap=_FakePixmap(False, width=100, height=40),
        dpr=1.0,
    )
    right = _FakeScreen(
        QRect(1920, 0, 1920, 1080),
        pixmap=_FakePixmap(False, width=200, height=80),
        dpr=2.0,
    )

    painter_instances: list[_FakePainter] = []

    def _painter_factory(image):
        painter = _FakePainter(image)
        painter_instances.append(painter)
        return painter

    mocker.patch("whisperbridge.services.screen_capture_service.QT_AVAILABLE", True)
    mocker.patch(
        "whisperbridge.services.screen_capture_service.ScreenUtils.clamp_rectangle_to_screen",
        side_effect=lambda r: r,
    )
    mocker.patch.object(
        ScreenCaptureService,
        "_get_qt_gui_app",
        return_value=_FakeGuiApp([left, right]),
    )
    mocker.patch("whisperbridge.services.screen_capture_service.QImage", _FakeQImage)
    mocker.patch("whisperbridge.services.screen_capture_service.QPainter", side_effect=_painter_factory)

    # Target spans both monitors by 100 logical px each side.
    region = Rectangle(x=1820, y=10, width=200, height=40)
    result = capture_service.capture_area(region)

    assert result.success is True
    assert len(painter_instances) == 1
    draw_calls = painter_instances[0].draw_calls
    assert len(draw_calls) == 2

    # New logic must use explicit destination width/height (logical), regardless
    # of underlying pixmap physical size.
    # Signature: drawPixmap(dst_x, dst_y, dst_w, dst_h, pixmap)
    assert draw_calls[0][0:4] == (0, 0, 100, 40)
    assert draw_calls[1][0:4] == (100, 0, 100, 40)


def test_qt_capture_returns_none_when_no_screen_intersection(capture_service, mocker):
    """Capture should fail explicitly when target doesn't intersect any screen."""
    screen = _FakeScreen(QRect(0, 0, 1920, 1080), pixmap=_FakePixmap(is_null=False))

    mocker.patch("whisperbridge.services.screen_capture_service.QT_AVAILABLE", True)
    mocker.patch.object(
        ScreenCaptureService,
        "_get_qt_gui_app",
        return_value=_FakeGuiApp([screen]),
    )
    mocker.patch("whisperbridge.services.screen_capture_service.QImage", _FakeQImage)
    mocker.patch("whisperbridge.services.screen_capture_service.QPainter", _FakePainter)

    region = Rectangle(x=-3000, y=10, width=200, height=50)
    result = capture_service.capture_area(region)

    assert result.success is False


def test_qt_capture_handles_memoryview_bits_without_setsize(capture_service, mocker):
    """Capture should work when QImage.bits() returns memoryview (no setsize)."""
    screen = _FakeScreen(QRect(0, 0, 1920, 1080), pixmap=_FakePixmap(is_null=False))

    mocker.patch("whisperbridge.services.screen_capture_service.QT_AVAILABLE", True)
    mocker.patch.object(
        ScreenCaptureService,
        "_get_qt_gui_app",
        return_value=_FakeGuiApp([screen]),
    )
    mocker.patch("whisperbridge.services.screen_capture_service.QImage", _FakeQImageMemoryViewBits)
    mocker.patch("whisperbridge.services.screen_capture_service.QPainter", _FakePainter)

    region = Rectangle(x=10, y=10, width=120, height=30)
    result = capture_service.capture_area(region)

    assert result.success is True
    assert isinstance(result.image, Image.Image)
    assert result.image.size == (120, 30)


def test_qt_capture_returns_none_without_qt_runtime(capture_service, mocker):
    """Capture should fail explicitly when Qt capture runtime is unavailable."""
    mocker.patch("whisperbridge.services.screen_capture_service.QT_AVAILABLE", False)
    region = Rectangle(x=0, y=0, width=100, height=40)

    result = capture_service.capture_area(region)

    assert result.success is False


def test_qt_capture_fails_when_qt_gui_app_is_unavailable(capture_service, mocker):
    """Capture should fail predictably when QGuiApplication instance is unavailable.

    Also verifies clamping falls back to platform bounds in this branch.
    """
    mocker.patch("whisperbridge.services.screen_capture_service.QT_AVAILABLE", True)
    clamp_fallback = mocker.patch(
        "whisperbridge.services.screen_capture_service.ScreenUtils.clamp_rectangle_to_screen",
        side_effect=lambda r: r,
    )
    mocker.patch.object(ScreenCaptureService, "_get_qt_gui_app", return_value=None)

    region = Rectangle(x=10, y=10, width=120, height=30)
    result = capture_service.capture_area(region)

    clamp_fallback.assert_called_once_with(region)
    assert result.success is False
    assert result.error_message == "Failed to capture area"


def test_capture_virtual_desktop_uses_qt_virtual_bounds(capture_service, mocker):
    """Virtual desktop capture should use Qt-derived virtual bounds when available."""
    virtual_bounds = Rectangle(-1920, 0, 3840, 1080)
    mocker.patch.object(capture_service, "_get_qt_virtual_bounds", return_value=virtual_bounds)

    capture_area_mock = mocker.patch.object(capture_service, "capture_area")
    capture_area_mock.return_value = Mock(success=True, image=Mock(), rectangle=virtual_bounds)

    result = capture_service.capture_virtual_desktop()

    capture_area_mock.assert_called_once_with(virtual_bounds, None)
    assert result.success is True


def test_crop_captured_image_returns_clipped_region(capture_service):
    """Cropping pre-captured image should clip selection to frozen image bounds."""
    source_image = Image.new("RGB", (300, 200), color="white")
    source_rect = Rectangle(x=100, y=50, width=300, height=200)
    target_rect = Rectangle(x=50, y=40, width=100, height=100)

    result = capture_service.crop_captured_image(
        captured_image=source_image,
        captured_rectangle=source_rect,
        target_rectangle=target_rect,
    )

    assert result.success is True
    assert result.rectangle == Rectangle(x=100, y=50, width=50, height=90)
    assert result.image is not None
    assert result.image.size == (50, 90)


def test_crop_captured_image_scales_logical_to_pixel_coords(capture_service):
    """Cropping should map logical coordinates to pixel coordinates on HiDPI buffers."""
    # Image is 2x bigger than logical rectangle on both axes.
    source_image = Image.new("RGB", (600, 400), color="white")
    source_rect = Rectangle(x=100, y=50, width=300, height=200)
    target_rect = Rectangle(x=150, y=80, width=50, height=20)

    result = capture_service.crop_captured_image(
        captured_image=source_image,
        captured_rectangle=source_rect,
        target_rectangle=target_rect,
    )

    assert result.success is True
    assert result.rectangle == target_rect
    assert result.image is not None
    assert result.image.size == (100, 40)


def test_crop_captured_image_preserves_minimum_pixel_area_with_floor_ceil_mapping(capture_service):
    """Cropping should keep at least 1px area for tiny logical regions after mapping."""
    source_image = Image.new("RGB", (1, 1), color="white")
    source_rect = Rectangle(x=0, y=0, width=10, height=10)
    target_rect = Rectangle(x=0, y=0, width=1, height=1)

    result = capture_service.crop_captured_image(
        captured_image=source_image,
        captured_rectangle=source_rect,
        target_rectangle=target_rect,
    )

    assert result.success is True
    assert result.image is not None
    assert result.image.size == (1, 1)
