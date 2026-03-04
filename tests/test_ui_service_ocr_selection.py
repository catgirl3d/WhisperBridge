"""UIService OCR selection pipeline tests."""

from unittest.mock import Mock

from whisperbridge.services.ui_service import UIService


class _FakeRect:
    """Minimal QRect-like object for selection callback tests."""

    def __init__(self, x: int, y: int, w: int, h: int):
        self._x = x
        self._y = y
        self._w = w
        self._h = h

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y

    def width(self) -> int:
        return self._w

    def height(self) -> int:
        return self._h


def _build_ui_service(mocker) -> UIService:
    """Create UIService instance with heavy UI initialization disabled."""
    mocker.patch.object(UIService, "_initialize_ui_components", return_value=None)
    ui = UIService(app=Mock())
    ui.logger = Mock()
    return ui


def test_on_selection_completed_uses_logical_rect_without_pixel_conversion(mocker):
    """Selection pipeline must keep logical coordinates and skip pixel conversion helper."""
    ui = _build_ui_service(mocker)

    convert_mock = mocker.patch(
        "whisperbridge.utils.screen_utils.ScreenUtils.convert_rect_to_pixels"
    )

    fake_image = Mock()
    capture_result = Mock(success=True, image=fake_image)
    capture_mock = mocker.patch.object(ui, "_capture_region_image", return_value=capture_result)
    start_worker_mock = mocker.patch.object(ui, "_start_ocr_worker")

    rect = _FakeRect(-120, 50, 300, 80)
    ui._on_selection_completed(rect)

    convert_mock.assert_not_called()

    captured_region = capture_mock.call_args.args[0]
    assert captured_region.x == -120
    assert captured_region.y == 50
    assert captured_region.width == 300
    assert captured_region.height == 80

    start_worker_mock.assert_called_once_with(image=fake_image)


def test_on_selection_completed_handles_capture_failure_without_starting_worker(mocker):
    """UI flow must stop and notify user when main-thread capture fails."""
    ui = _build_ui_service(mocker)

    capture_result = Mock(success=False, image=None)
    mocker.patch.object(ui, "_capture_region_image", return_value=capture_result)
    start_worker_mock = mocker.patch.object(ui, "_start_ocr_worker")
    notify_mock = mocker.patch("whisperbridge.services.ui_service.get_notification_service")
    notifier = Mock()
    notify_mock.return_value = notifier

    rect = _FakeRect(10, 20, 120, 50)
    ui._on_selection_completed(rect)

    start_worker_mock.assert_not_called()
    notifier.error.assert_called_once_with("Screen capture failed", "WhisperBridge")


def test_start_ocr_worker_requires_image(mocker):
    """Worker startup contract should reject missing image explicitly."""
    ui = _build_ui_service(mocker)

    settings = Mock(ocr_enabled=True)
    config_service_mock = mocker.patch("whisperbridge.services.config_service.config_service")
    config_service_mock.get_settings.return_value = settings

    notify_mock = mocker.patch("whisperbridge.services.ui_service.get_notification_service")
    notifier = Mock()
    notify_mock.return_value = notifier

    create_worker_mock = mocker.patch.object(ui.app, "create_and_run_worker")

    ui._start_ocr_worker(image=None)

    create_worker_mock.assert_not_called()
    notifier.error.assert_called_once_with("No OCR image provided.", "WhisperBridge")


def test_activate_ocr_starts_selection_with_frozen_frame_when_capture_succeeds(mocker):
    """OCR activation should pass freeze-frame image/rect into selection overlay start()."""
    ui = _build_ui_service(mocker)
    ui.selection_overlay = Mock()
    ui.overlay_windows["ocr"] = Mock()

    mocker.patch("whisperbridge.services.ui_service.BUILD_OCR_ENABLED", True)

    settings = Mock(ocr_enabled=True)
    config_service_mock = mocker.patch("whisperbridge.services.config_service.config_service")
    config_service_mock.get_settings.return_value = settings

    frozen_image = Mock()
    frozen_rect = Mock(x=-1920, y=0, width=3840, height=1080)
    frozen_result = Mock(success=True, image=frozen_image, rectangle=frozen_rect)
    mocker.patch.object(ui, "_capture_virtual_desktop_image", return_value=frozen_result)

    ui.activate_ocr()

    ui.selection_overlay.start.assert_called_once_with(
        frozen_image=frozen_image,
        frozen_rect=frozen_rect,
    )


def test_on_selection_completed_uses_frozen_crop_before_live_capture(mocker):
    """Selection completion should prefer frozen-frame crop and skip live recapture."""
    ui = _build_ui_service(mocker)

    frozen_image = Mock()
    frozen_rect = Mock()
    ui._frozen_capture_image = frozen_image
    ui._frozen_capture_rect = frozen_rect

    live_capture_mock = mocker.patch.object(ui, "_capture_region_image")
    fake_image = Mock()
    start_worker_mock = mocker.patch.object(ui, "_start_ocr_worker")

    capture_service = Mock()
    capture_service.crop_captured_image.return_value = Mock(
        success=True,
        image=fake_image,
        error_message="",
    )
    mocker.patch("whisperbridge.services.ui_service.get_capture_service", return_value=capture_service)

    rect = _FakeRect(10, 20, 120, 50)
    ui._on_selection_completed(rect)

    live_capture_mock.assert_not_called()
    capture_service.crop_captured_image.assert_called_once()
    start_worker_mock.assert_called_once_with(image=fake_image)
    assert ui._frozen_capture_image is None
    assert ui._frozen_capture_rect is None
