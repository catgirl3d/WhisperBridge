"""
Unit tests for worker lifecycle, cancellation, and watchdog functionality.
Includes integration tests for Watchdog timer and Qt signals using pytest-qt.
Run with: python -m pytest tests/test_worker_timeout.py -v
"""

import threading
import time
import pytest
from unittest.mock import Mock

# Import dependencies
try:
    from PySide6.QtCore import QMetaObject, QTimer, QThread, Qt, Signal, Slot, QObject
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QSignalSpy
    from whisperbridge.ui_qt.workers import (
        BaseWorker, TranslationWorker, StyleWorker,
        CaptureOcrTranslateWorker, ApiTestWorker
    )
    from whisperbridge.ui_qt.overlay_window import OverlayWindow
    from whisperbridge.services.config_service import config_service
    from whisperbridge.services.translation_service import TranslationService
except ImportError:
    # Allow running non-Qt tests in minimal env
    BaseWorker = None
    OverlayWindow = None
    config_service = None
    TranslationService = None
    QSignalSpy = None
    CaptureOcrTranslateWorker = None
    ApiTestWorker = None
    QObject = None


if BaseWorker is not None:
    class ManualCompletionWorker(BaseWorker):
        """Test-only worker for setup and cleanup without translation execution."""

        def __init__(self, result="result", error_message="Some error"):
            super().__init__()
            self.result = result
            self.error_message = error_message

        def run(self):
            pass

        @Slot()
        def complete_success(self):
            self.finished.emit(True, self.result)

        @Slot()
        def complete_error(self):
            self.finished.emit(False, self.error_message)

        @Slot()
        def complete_both(self):
            self.finished.emit(False, self.error_message)
else:
    ManualCompletionWorker = None


if QObject is not None:
    class ShutdownWorker(QObject):
        """Worker that exits only after observing the real cancellation request."""

        finished = Signal()

        def __init__(self):
            super().__init__()
            self._cancel_requested = False
            self.started = threading.Event()

        def request_cancel(self):
            self._cancel_requested = True

        def run(self):
            self.started.set()
            while not self._cancel_requested:
                time.sleep(0.01)
            self.finished.emit()
else:
    ShutdownWorker = None


if BaseWorker is not None:
    class CancellableCompletionWorker(BaseWorker):
        """Test worker that remains active until cancellation is requested."""

        def __init__(self):
            super().__init__()
            self.started = threading.Event()
            self._completed = False

        def run(self):
            self.started.set()
            while not self._cancel_requested:
                time.sleep(0.005)
            if not self._completed:
                self.finished.emit(True, "cancelled")

        @Slot()
        def complete_success(self):
            self._completed = True
            self._cancel_requested = True
            self.finished.emit(True, "completed")
else:
    CancellableCompletionWorker = None


# --- Non-Qt Tests (Unit Tests) ---

class TestWorkerTimeoutLogic:
    """Test timeout calculation logic (Unit tests)."""

    def test_timeout_calculation_for_watchdog(self):
        """Test watchdog timeout calculation logic independent of Qt."""
        api_timeout = 60
        watchdog_timeout = max(api_timeout * 2, 60)
        assert watchdog_timeout == 120
        
        api_timeout = 10
        watchdog_timeout = max(api_timeout * 2, 60)
        assert watchdog_timeout == 60  # Minimum 60s enforced


# --- Qt Integration Tests ---

@pytest.mark.skipif(BaseWorker is None, reason="Requires Qt and project dependencies")
class TestQtIntegration:
    """Integration tests requiring Qt event loop."""

    @pytest.fixture
    def mock_config_service(self, monkeypatch):
        """Mock config_service with controllable timeout."""
        timeout_value = [60]  # Mutable for test control
        
        def get_setting(key):
            if key == "api_timeout":
                return timeout_value[0]
            # Mock other settings needed for workers
            if key == "ui_source_language": return "en"
            if key == "ui_target_language": return "ru"
            return None
        
        monkeypatch.setattr(
            'whisperbridge.services.config_service.config_service.get_setting',
            get_setting
        )
        return timeout_value

    @pytest.fixture(autouse=True)
    def mock_qmessagebox(self, mocker):
        """Mock QMessageBox to prevent blocking dialogs and crashes in tests."""
        mock_warn = mocker.patch('PySide6.QtWidgets.QMessageBox.warning')
        yield mock_warn

    @pytest.fixture
    def overlay(self, qtbot, mock_config_service):
        """Create OverlayWindow instance."""
        window = OverlayWindow()
        window._update_layout()
        qtbot.addWidget(window)
        yield window
        # Cleanup any remaining threads/workers in case of test failure
        for thread in window.findChildren(QThread):
            if thread.isRunning():
                thread.quit()
                thread.wait(500)

    def test_overlay_applies_translator_font_size_from_settings(self, qtbot, mocker):
        """Overlay should apply the configured font size to both translator text fields."""
        mock_settings = Mock(
            compact_view=False,
            overlay_side_buttons_autohide=False,
            translator_font_size=18,
            auto_swap_en_ru=True,
            text_styles=[],
        )

        def get_setting(key):
            if key == "translator_font_size":
                return 18
            if key == "api_provider":
                return "openai"
            if key == "openai_api_key":
                return ""
            return None

        mocker.patch('whisperbridge.ui_qt.overlay_window.config_service.get_setting', side_effect=get_setting)
        mocker.patch('whisperbridge.ui_qt.overlay_window.config_service.get_settings', return_value=mock_settings)

        window = OverlayWindow()
        qtbot.addWidget(window)
        window._update_layout()

        assert window.original_text.font().pointSize() == 18
        assert window.translated_text.font().pointSize() == 18
        assert window.original_text.document().defaultFont().pointSize() == 18
        assert window.translated_text.document().defaultFont().pointSize() == 18

    def test_overlay_observer_applies_live_translator_font_size_change(self, qtbot, mocker):
        """Overlay should update both text fields when translator_font_size changes."""
        mock_settings = Mock(
            compact_view=False,
            overlay_side_buttons_autohide=False,
            translator_font_size=14,
            auto_swap_en_ru=True,
            stylist_cache_enabled=False,
            translation_cache_enabled=False,
            auto_copy_translated_overlay=False,
            text_styles=[],
        )

        def get_setting(key):
            if key == "translator_font_size":
                return 14
            if key == "api_provider":
                return "openai"
            if key == "openai_api_key":
                return ""
            return None

        mocker.patch('whisperbridge.ui_qt.overlay_window.config_service.get_setting', side_effect=get_setting)
        mocker.patch('whisperbridge.ui_qt.overlay_window.config_service.get_settings', return_value=mock_settings)

        window = OverlayWindow()
        qtbot.addWidget(window)
        window._update_layout()

        assert window.original_text.font().pointSize() == 14
        assert window.translated_text.font().pointSize() == 14

        window._settings_observer.on_settings_changed("translator_font_size", 14, 19)

        assert window.original_text.font().pointSize() == 19
        assert window.translated_text.font().pointSize() == 19

    def test_overlay_dialog_spinbox_applies_font_size_live(self, qtbot, mocker):
        """Translator settings dialog should update overlay text fields immediately."""
        mock_settings = Mock(
            compact_view=False,
            overlay_side_buttons_autohide=False,
            translator_font_size=14,
            auto_swap_en_ru=True,
            overlay_window_geometry=None,
            stylist_cache_enabled=False,
            translation_cache_enabled=False,
            auto_copy_translated_overlay=False,
            text_styles=[],
        )

        current_font_size = {"value": 14}
        window = None

        def get_setting(key):
            if key == "translator_font_size":
                return current_font_size["value"]
            if key == "api_provider":
                return "openai"
            if key == "openai_api_key":
                return ""
            return None

        def set_setting(key, value):
            if key == "translator_font_size":
                old_value = current_font_size["value"]
                current_font_size["value"] = value
                mock_settings.translator_font_size = value
                if window is not None:
                    window._settings_observer.on_settings_changed(key, old_value, value)
            return True

        mocker.patch('whisperbridge.ui_qt.overlay_window.config_service.get_setting', side_effect=get_setting)
        mocker.patch('whisperbridge.ui_qt.overlay_window.config_service.get_settings', return_value=mock_settings)
        mocker.patch('whisperbridge.ui_qt.overlay_ui_builder.config_service.get_settings', return_value=mock_settings)
        mocker.patch('whisperbridge.ui_qt.overlay_ui_builder.config_service.set_setting', side_effect=set_setting)

        window = OverlayWindow()
        qtbot.addWidget(window)
        window._open_translator_settings()
        qtbot.wait(10)

        dialog = window._translator_settings_dialog
        dialog.translator_font_size_spinbox.setValue(20)
        qtbot.wait(10)

        assert window.original_text.font().pointSize() == 20
        assert window.translated_text.font().pointSize() == 20
        assert window.original_text.document().defaultFont().pointSize() == 20
        assert window.translated_text.document().defaultFont().pointSize() == 20

    # --- Worker Thread Lifecycle Tests ---

    def test_worker_thread_lifecycle(self, qtbot, overlay):
        """Verify a manually completed worker thread starts and stops."""
        worker, thread = overlay._setup_worker(ManualCompletionWorker)
        
        # Verify thread is running
        assert thread.isRunning()
        
        # Cleanup
        with qtbot.waitSignal(thread.finished, timeout=1000):
            assert QMetaObject.invokeMethod(worker, "complete_success", Qt.QueuedConnection)
        # Verify thread stopped
        assert not thread.isRunning()

    def test_shutdown_workers_cancels_current_style_worker_after_translation_completion(self, qtbot, overlay):
        """Shutdown must cancel the live style worker, not a completed translation worker."""
        translation_worker, translation_thread = overlay._setup_worker(CancellableCompletionWorker)
        overlay._translation_worker = translation_worker
        overlay._translation_thread = translation_thread
        assert translation_worker.started.wait(1.0)

        with qtbot.waitSignal(translation_thread.finished, timeout=1000):
            translation_worker.complete_success()

        # The stale completed pair stays in the fields but is inert: shutdown
        # must cancel the new live style pair instead of the finished one.
        style_worker, style_thread = overlay._setup_worker(CancellableCompletionWorker)
        overlay._style_worker = style_worker
        overlay._style_thread = style_thread
        assert style_worker.started.wait(1.0)

        overlay.shutdown_workers()

        # Cancelling the stale worker too is harmless; what matters is that
        # the live style pair received cancellation and both threads stopped.
        assert style_worker._cancel_requested is True
        assert style_thread.isFinished()

    def test_shutdown_workers_waits_after_request_cancel(self, qtbot, overlay):
        """Shutdown waits for a thread even when request cancellation already cleared the marker."""
        worker, thread = overlay._setup_worker(CancellableCompletionWorker)
        overlay._translation_worker = worker
        overlay._translation_thread = thread
        assert worker.started.wait(1.0)
        overlay._translation_start_time = time.monotonic()

        overlay._cancel_active_request()
        assert overlay._translation_start_time is None
        overlay.shutdown_workers()

        assert thread.isFinished()

    def test_shutdown_workers_cancels_both_live_pairs(self, qtbot, overlay):
        """If translation and style pairs are both live, both workers get cancelled."""
        translation_worker, translation_thread = overlay._setup_worker(CancellableCompletionWorker)
        style_worker, style_thread = overlay._setup_worker(CancellableCompletionWorker)
        overlay._translation_worker = translation_worker
        overlay._translation_thread = translation_thread
        overlay._style_worker = style_worker
        overlay._style_thread = style_thread
        assert translation_worker.started.wait(1.0)
        assert style_worker.started.wait(1.0)

        overlay.shutdown_workers()

        assert translation_worker._cancel_requested is True
        assert style_worker._cancel_requested is True
        assert translation_thread.isFinished()
        assert style_thread.isFinished()

    def test_qt_app_shutdown_cancels_and_joins_worker(self, qapp, mocker):
        """Shutdown cancels a real worker and waits for its QThread to finish."""
        from whisperbridge.ui_qt.app import QtApp

        mocker.patch("whisperbridge.ui_qt.app.get_api_manager", return_value=Mock())
        app = QtApp()
        worker = ShutdownWorker()
        thread, _ = app.create_and_run_worker(worker, lambda: None)

        assert worker.started.wait(1.0)
        started_at = time.monotonic()
        app.shutdown()
        elapsed = time.monotonic() - started_at

        assert elapsed < 5.5
        assert worker._cancel_requested is True
        assert thread.isFinished()

    def test_qt_app_shutdown_is_idempotent_without_workers(self, qapp, mocker):
        """Shutdown remains safe when called repeatedly without workers."""
        from whisperbridge.ui_qt.app import QtApp

        mocker.patch("whisperbridge.ui_qt.app.get_api_manager", return_value=Mock())
        app = QtApp()

        app.shutdown()
        app.shutdown()

        assert app.shutdown_requested is True

    def test_watchdog_cleanup_on_success(self, qtbot, overlay):
        """Verify watchdog cleanup after a manual successful completion."""
        timers_before = len(overlay.findChildren(QTimer))
        worker, thread = overlay._setup_worker(ManualCompletionWorker, "Translated text")
        
        with qtbot.waitSignal(thread.finished, timeout=1000):
            assert QMetaObject.invokeMethod(worker, "complete_success", Qt.QueuedConnection)
        
        qtbot.waitUntil(lambda: len(overlay.findChildren(QTimer)) == timers_before, timeout=1000)

    def test_watchdog_cleanup_on_error(self, qtbot, overlay):
        """Verify watchdog cleanup after a manual worker error."""
        timers_before = len(overlay.findChildren(QTimer))
        worker, thread = overlay._setup_worker(ManualCompletionWorker, "result", "Some error")
        
        with qtbot.waitSignal(thread.finished, timeout=1000):
            assert QMetaObject.invokeMethod(worker, "complete_error", Qt.QueuedConnection)

        qtbot.waitUntil(lambda: len(overlay.findChildren(QTimer)) == timers_before, timeout=1000)

    def test_second_click_cancels_active_request(self, qtbot, overlay, mocker):
        """Second click should cancel the active request and restore button state."""
        mocker.patch.object(overlay, "_is_api_ready", return_value=(True, ""))

        started = threading.Event()
        release = threading.Event()

        def blocking_translate(*_args, **_kwargs):
            started.set()
            release.wait(5)
            return Mock(success=True, translated_text="late")

        mock_service = Mock()
        mock_service.translate_text = Mock(side_effect=blocking_translate)
        mocker.patch(
            'whisperbridge.services.translation_service.get_translation_service',
            return_value=mock_service,
        )

        overlay.original_text.setPlainText("hello")
        overlay._on_translate_clicked()
        assert started.wait(1.0)

        assert overlay._translation_start_time is not None
        assert overlay.translate_btn.isEnabled() is True

        overlay._on_translate_clicked()
        release.set()
        qtbot.wait(50)

        assert overlay._translation_start_time is None
        assert overlay.translate_btn.isEnabled() is True
        assert "cancel" in overlay.status_label.text().lower()

        try:
            translation_thread = getattr(overlay, "_translation_thread", None)
            if translation_thread is not None and translation_thread.isRunning():
                translation_thread.quit()
                translation_thread.wait(2000)
        except RuntimeError:
            pass

    def test_translate_click_starts_translation_worker_with_selected_languages(self, overlay, mocker):
        """Translate mode should pass the current source and target languages to TranslationWorker."""
        mocker.patch.object(overlay, "_is_api_ready", return_value=(True, ""))
        mock_start_loading = mocker.patch.object(overlay, "_start_loading_animation")
        mock_setup_worker = mocker.patch.object(overlay, "_setup_worker", return_value=(Mock(), Mock()))

        overlay._cached_settings = Mock(compact_view=False, text_styles=[])
        overlay.original_text.setPlainText("hello")
        overlay.ui_builder.set_combo_data(overlay.source_combo, "en")
        overlay.ui_builder.set_combo_data(overlay.target_combo, "ru")

        overlay._on_translate_clicked()

        assert overlay._translation_start_time is not None
        assert overlay._translation_prev_text == "  Translate"
        assert overlay.status_label.text() == "Request sent"
        mock_start_loading.assert_called_once_with("Translating", False)
        mock_setup_worker.assert_called_once_with(TranslationWorker, "hello", "en", "ru")

    def test_translate_click_starts_style_worker_with_selected_style(self, overlay, mocker):
        """Style mode should pass the currently selected style name to StyleWorker."""
        mocker.patch.object(overlay, "_is_api_ready", return_value=(True, ""))
        mock_start_loading = mocker.patch.object(overlay, "_start_loading_animation")
        mock_setup_worker = mocker.patch.object(overlay, "_setup_worker", return_value=(Mock(), Mock()))

        overlay._cached_settings = Mock(compact_view=False, text_styles=[])
        overlay.original_text.setPlainText("hello")
        overlay.style_combo.clear()
        overlay.style_combo.addItem("Formal")
        overlay.style_combo.setCurrentIndex(0)
        style_index = overlay._find_index_by_text(overlay.mode_combo, "Style")
        overlay.mode_combo.setCurrentIndex(style_index)

        overlay._on_translate_clicked()

        assert overlay._translation_start_time is not None
        assert overlay._translation_prev_text == "  Style"
        mock_start_loading.assert_called_once_with("Styling", False)
        mock_setup_worker.assert_called_once_with(StyleWorker, "hello", "Formal")

    def test_translate_click_uses_first_configured_style_when_combo_is_empty(self, overlay, mocker):
        """Style mode should fall back to the first configured style when the combo has no current text."""
        mocker.patch.object(overlay, "_is_api_ready", return_value=(True, ""))
        mocker.patch.object(overlay, "_start_loading_animation")
        mock_setup_worker = mocker.patch.object(overlay, "_setup_worker", return_value=(Mock(), Mock()))

        overlay._cached_settings = Mock(compact_view=False, text_styles=[{"name": "Improve tone"}])
        overlay.original_text.setPlainText("hello")
        overlay.style_combo.clear()
        style_index = overlay._find_index_by_text(overlay.mode_combo, "Style")
        overlay.mode_combo.setCurrentIndex(style_index)

        overlay._on_translate_clicked()

        mock_setup_worker.assert_called_once_with(StyleWorker, "hello", "Improve tone")

    @pytest.mark.parametrize("api_timeout,expected_watchdog", [
        (10, 60),   # api_timeout=10 -> watchdog=max(20,60)=60
        (30, 60),   # api_timeout=30 -> watchdog=max(60,60)=60
        (60, 120),  # api_timeout=60 -> watchdog=max(120,60)=120
        (100, 60),  # invalid api_timeout falls back to the 30-second default
    ])
    def test_watchdog_timeout_calculation_only(self, qtbot, overlay, mock_config_service, mocker, api_timeout, expected_watchdog):
        """Test watchdog timeout calculation without actual termination.
        
        This test verifies timeout calculation logic.
        Actual termination testing is difficult in unit tests due to Qt's deleteLater.
        """
        mock_config_service[0] = api_timeout
        
        # Patch QTimer.start to capture the timeout value
        mock_start = mocker.patch('whisperbridge.ui_qt.overlay_window.QTimer.start')
        worker, thread = overlay._setup_worker(ManualCompletionWorker)
        
        # Verify QTimer.start was called with expected timeout (in ms)
        assert mock_start.called
        actual_timeout_ms = mock_start.call_args[0][0]
        expected_timeout_ms = expected_watchdog * 1000
        assert actual_timeout_ms == expected_timeout_ms, \
            f"api_timeout={api_timeout}, expected watchdog={expected_watchdog}s, got {actual_timeout_ms/1000}s"
        
        # Cleanup
        with qtbot.waitSignal(thread.finished, timeout=1000):
            assert QMetaObject.invokeMethod(worker, "complete_success", Qt.QueuedConnection)

    # --- Signal Emission Order Tests ---

    def test_signal_disconnection_after_cleanup(self, qtbot, overlay):
        """Verify signal-driven cleanup happens correctly."""
        # Count timers before
        timers_before = len(overlay.findChildren(QTimer))
        worker, thread = overlay._setup_worker(ManualCompletionWorker)
        
        # Trigger cleanup
        with qtbot.waitSignal(thread.finished, timeout=1000):
            assert QMetaObject.invokeMethod(worker, "complete_success", Qt.QueuedConnection)
        
        qtbot.waitUntil(lambda: len(overlay.findChildren(QTimer)) == timers_before, timeout=1000)
        
        # Thread may be deleted by now, so just verify test completed without crash
        # The fact we got here means cleanup worked

    def test_known_error_status_from_finished_signal(self, overlay, mock_qmessagebox):
        """Known API errors should keep their status from the sole finished signal."""
        overlay._is_api_ready = Mock(return_value=(True, ""))
        overlay._translation_start_time = time.time() - 0.1
        error_message = "quota exceeded: billing limit reached"

        overlay._on_translation_finished(False, error_message)

        assert "quota exceeded" in overlay.status_label.text().lower()
        mock_qmessagebox.assert_not_called()

    def test_finished_without_error_signal_sets_known_error_status(self, overlay, mock_qmessagebox):
        """Finished(False, ...) should still show a known status even if error signal was not delivered."""
        overlay._is_api_ready = Mock(return_value=(True, ""))
        overlay._translation_start_time = time.time() - 0.1

        overlay._on_translation_finished(False, "quota exceeded: billing limit reached")

        assert "quota exceeded" in overlay.status_label.text().lower()
        mock_qmessagebox.assert_not_called()

    def test_unknown_error_popup_is_shown_once_from_finished_signal(self, overlay, mock_qmessagebox):
        """Unknown errors should surface one popup from the sole finished signal."""
        overlay._is_api_ready = Mock(return_value=(True, ""))
        overlay._translation_start_time = time.time() - 0.1
        error_message = "unexpected translator explosion"

        overlay._on_translation_finished(False, error_message)

        assert "failed" in overlay.status_label.text().lower()
        mock_qmessagebox.assert_called_once_with(
            overlay,
            "Translation failed",
            f"Translation error: {error_message}",
        )

    def test_successful_finished_updates_translation_and_completion_status(self, overlay, mock_qmessagebox):
        """Successful completion should populate translated text and show completion timing."""
        overlay._translation_start_time = time.time() - 0.1
        overlay._translation_prev_text = "Translate"

        overlay._on_translation_finished(True, "Hola")

        assert overlay.translated_text.toPlainText() == "Hola"
        assert overlay.status_label.text().startswith("Completed in ")
        assert overlay._translation_start_time is None
        mock_qmessagebox.assert_not_called()

    # --- Race Condition Scenarios ---

    def test_concurrent_cleanup_calls(self, qtbot, overlay):
        """Verify one terminal failure signal performs cleanup safely."""
        worker, thread = overlay._setup_worker(ManualCompletionWorker, "result", "Fail")
        finished_spy = QSignalSpy(worker.finished)
        
        with qtbot.waitSignal(thread.finished, timeout=1000):
            assert QMetaObject.invokeMethod(worker, "complete_both", Qt.QueuedConnection)
        
        assert finished_spy.count() == 1
        assert finished_spy.at(0) == [False, "Fail"]
        with pytest.raises(AttributeError):
            worker.error
        try:
            assert not thread.isRunning()
        except RuntimeError:
            pass

    def test_cleanup_before_thread_start(self, qtbot, overlay):
        """Verify cleanup works when signals fire immediately after setup."""
        timers_before = len(overlay.findChildren(QTimer))
        worker, thread = overlay._setup_worker(ManualCompletionWorker, "result", "Immediate Fail")
        
        # Emit error immediately (before thread really starts)
        with qtbot.waitSignal(thread.finished, timeout=1000):
            assert QMetaObject.invokeMethod(worker, "complete_error", Qt.QueuedConnection)
        
        qtbot.waitUntil(lambda: len(overlay.findChildren(QTimer)) == timers_before, timeout=1000)

    def test_late_signal_after_cleanup_no_crash(self, qtbot, overlay):
        """Verify late lifecycle signals after cleanup do not crash."""
        worker, thread = overlay._setup_worker(ManualCompletionWorker)
        
        # Trigger cleanup
        with qtbot.waitSignal(thread.finished, timeout=1000):
            assert QMetaObject.invokeMethod(worker, "complete_success", Qt.QueuedConnection)
        
        qtbot.wait(200)
        
        # Try to emit signals again (simulates race condition)
        # This should raise RuntimeError because worker is deleted, but that's expected
        # The important thing is that the application doesn't crash
        try:
            worker.finished.emit(True, "late_result")
        except RuntimeError as e:
            # Expected - worker was deleted
            assert "Signal source has been deleted" in str(e)
        else:
            # If no error, worker wasn't deleted (unexpected but not a crash)
            pass
        
        # Try with thread signal
        try:
            thread.finished.emit()
        except RuntimeError as e:
            # Expected - thread was deleted
            assert "Signal source has been deleted" in str(e)
        
        # No crash = success

    def test_watchdog_vs_completion_race(self, qtbot, overlay, mock_config_service):
        """Test race condition between watchdog timeout and normal completion."""
        mock_config_service[0] = 0.5
        
        # Create a worker that might complete right as watchdog fires
        worker, thread = overlay._setup_worker(ManualCompletionWorker)
        
        # Simulate completion happening
        with qtbot.waitSignal(thread.finished, timeout=1000):
            assert QMetaObject.invokeMethod(worker, "complete_success", Qt.QueuedConnection)
        
        # Verify thread stopped cleanly
        assert not thread.isRunning()
        
        # No crash = success

    # --- Memory Leak Tests ---

    def test_no_worker_leak(self, qtbot, overlay):
        """Verify each manually completed worker is destroyed after cleanup."""
        workers_and_threads = []
        destroyed_spies = []

        for i in range(10):
            worker, thread = overlay._setup_worker(ManualCompletionWorker)
            workers_and_threads.append((worker, thread))
            destroyed_spy = QSignalSpy(worker.destroyed)
            destroyed_spies.append(destroyed_spy)
            with qtbot.waitSignal(thread.finished, timeout=1000):
                assert QMetaObject.invokeMethod(worker, "complete_success", Qt.QueuedConnection)
            qtbot.waitUntil(lambda: destroyed_spy.count() == 1, timeout=1000)

        assert all(spy.count() == 1 for spy in destroyed_spies)

    def test_no_thread_leak(self, qtbot, overlay):
        """Verify each created thread is naturally destroyed after completion."""
        threads_and_spies = []

        for i in range(10):
            worker, thread = overlay._setup_worker(ManualCompletionWorker)
            destroyed_spy = QSignalSpy(thread.destroyed)
            threads_and_spies.append((thread, destroyed_spy))
            with qtbot.waitSignal(thread.finished, timeout=1000):
                assert QMetaObject.invokeMethod(worker, "complete_success", Qt.QueuedConnection)
            qtbot.waitUntil(lambda: destroyed_spy.count() == 1, timeout=1000)

        assert all(spy.count() == 1 for _, spy in threads_and_spies)

    # --- Stress Tests ---

    def test_rapid_fire_requests(self, qtbot, overlay):
        """Test that five rapid manual completions emit results and clean up."""
        workers_and_threads = []
        finished_spies = []

        for i in range(5):
            worker, thread = overlay._setup_worker(ManualCompletionWorker, f"result{i}")
            workers_and_threads.append((worker, thread))
            finished_spies.append(QSignalSpy(worker.finished))
            thread_spy = QSignalSpy(thread.finished)
            workers_and_threads[-1] = (worker, thread, thread_spy)

        qtbot.waitUntil(lambda: all(thread.isRunning() for _, thread, _ in workers_and_threads), timeout=1000)
        qtbot.wait(50)
        for worker, thread, thread_spy in workers_and_threads:
            with qtbot.waitSignal(thread.finished, timeout=1000):
                assert QMetaObject.invokeMethod(worker, "complete_success", Qt.QueuedConnection)
            assert thread_spy.count() == 1

        assert [
            (spy.at(0)[0], spy.at(0)[1]) for spy in finished_spies
        ] == [(True, f"result{i}") for i in range(5)]
        assert [spy.count() for spy in finished_spies] == [1] * 5

    def test_many_workers_sequential(self, qtbot, overlay):
        """Test that many sequential lifecycle operations stay clean."""
        initial_timers = len(overlay.findChildren(QTimer))
        workers_and_threads = []
        
        # Run 20 sequential operations
        for i in range(20):
            worker, thread = overlay._setup_worker(ManualCompletionWorker, f"result{i}")
            workers_and_threads.append((worker, thread))
            with qtbot.waitSignal(thread.finished, timeout=1000):
                assert QMetaObject.invokeMethod(worker, "complete_success", Qt.QueuedConnection)

        qtbot.waitUntil(lambda: len(overlay.findChildren(QTimer)) == initial_timers, timeout=1000)

    def test_multiple_workers_concurrent(self, qtbot, overlay):
        """Test that three concurrent manual workers finish cleanly."""
        workers_and_threads = []
        finished_spies = []

        for i in range(3):
            worker, thread = overlay._setup_worker(ManualCompletionWorker, f"result{i}")
            workers_and_threads.append((worker, thread))
            finished_spies.append(QSignalSpy(worker.finished))
            workers_and_threads[-1] = (worker, thread, QSignalSpy(thread.finished))

        qtbot.waitUntil(lambda: all(thread.isRunning() for _, thread, _ in workers_and_threads), timeout=1000)
        qtbot.wait(50)
        for worker, thread, thread_spy in workers_and_threads:
            with qtbot.waitSignal(thread.finished, timeout=1000):
                assert QMetaObject.invokeMethod(worker, "complete_success", Qt.QueuedConnection)
            assert thread_spy.count() == 1

        assert [
            (spy.at(0)[0], spy.at(0)[1]) for spy in finished_spies
        ] == [(True, f"result{i}") for i in range(3)]
        assert [spy.count() for spy in finished_spies] == [1] * 3

    # --- Additional Coverage Tests ---

    def test_translation_worker_empty_response(self, qtbot, mock_config_service, mocker):
        """Test TranslationWorker handles empty API response."""
        mock_service = Mock()
        mock_service.translate_text = Mock(return_value=Mock(success=True, translated_text=None))

        mocker.patch('whisperbridge.services.translation_service.get_translation_service', return_value=mock_service)
        worker = TranslationWorker("Hello", "en", "es")
        finished_spy = QSignalSpy(worker.finished)
        worker.run()
        assert finished_spy.count() == 1
        assert finished_spy.at(0)[0] is True
        assert finished_spy.at(0)[1] == ""

    def test_translation_worker_service_error(self, qtbot, mock_config_service, mocker):
        """Test TranslationWorker handles service errors."""
        mock_service = Mock()
        mock_service.translate_text = Mock(side_effect=Exception("Service unavailable"))

        mocker.patch('whisperbridge.services.translation_service.get_translation_service', return_value=mock_service)
        worker = TranslationWorker("Hello", "en", "es")
        finished_spy = QSignalSpy(worker.finished)
        worker.run()
        assert finished_spy.count() == 1
        assert finished_spy.at(0)[0] is False
        with pytest.raises(AttributeError):
            worker.error

    def test_style_worker_empty_response(self, qtbot, mock_config_service, mocker):
        """Test StyleWorker handles empty API response."""
        mock_service = Mock()
        mock_service.style_text = Mock(return_value=Mock(success=True, translated_text=None))

        mocker.patch('whisperbridge.services.translation_service.get_translation_service', return_value=mock_service)
        worker = StyleWorker("Raw", "Formal")
        finished_spy = QSignalSpy(worker.finished)
        worker.run()
        assert finished_spy.count() == 1
        assert finished_spy.at(0)[0] is True
        assert finished_spy.at(0)[1] == ""

    def test_style_worker_service_error(self, qtbot, mock_config_service, mocker):
        """Test StyleWorker handles service errors."""
        mock_service = Mock()
        mock_service.style_text = Mock(side_effect=Exception("Service unavailable"))

        mocker.patch('whisperbridge.services.translation_service.get_translation_service', return_value=mock_service)
        worker = StyleWorker("Raw", "Formal")
        finished_spy = QSignalSpy(worker.finished)
        worker.run()
        assert finished_spy.count() == 1
        assert finished_spy.at(0)[0] is False
        with pytest.raises(AttributeError):
            worker.error


@pytest.mark.skipif(CaptureOcrTranslateWorker is None, reason="Requires Qt and project dependencies")
class TestCaptureOcrTranslateWorker:
    """Tests for CaptureOcrTranslateWorker."""

    @pytest.fixture
    def mock_services(self, mocker):
        """Mock OCR, translation, and notification service boundaries."""
        ocr_service = Mock()
        ocr_service.process_image.return_value = Mock(
            text="original", success=True, error_message=None
        )
        translation_service = Mock(spec=TranslationService, is_available=True)
        translation_service.translate_text.return_value = Mock(
            success=True, translated_text="translated"
        )
        notification_service = Mock()
        mocker.patch(
            'whisperbridge.ui_qt.workers.get_ocr_service', return_value=ocr_service
        )
        mocker.patch(
            'whisperbridge.ui_qt.workers.get_translation_service',
            return_value=translation_service,
        )
        mocker.patch(
            'whisperbridge.ui_qt.workers.get_notification_service',
            return_value=notification_service,
        )
        mocker.patch(
            'whisperbridge.ui_qt.workers.config_service.get_settings',
            return_value=Mock(ui_source_language="auto", ui_target_language="uk"),
        )

        yield ocr_service, translation_service, notification_service

    def test_capture_ocr_worker_with_image(self, mock_services):
        """Test worker processes pre-captured image."""
        ocr_service, translation_service, _ = mock_services
        image = Mock()

        worker = CaptureOcrTranslateWorker(image=image)
        worker.run()

        ocr_service.process_image.assert_called_once()
        request = ocr_service.process_image.call_args.args[0]
        assert request.image is image
        translation_service.translate_text.assert_called_once_with(
            "original", ui_source_lang="auto", ui_target_lang="uk"
        )

    def test_capture_ocr_worker_success_signals(self, qtbot, mock_services):
        """Test worker emits finished payload for successful OCR path."""
        _, _, notification_service = mock_services

        worker = CaptureOcrTranslateWorker(image=Mock())
        finished_spy = QSignalSpy(worker.finished)
        progress_spy = QSignalSpy(worker.progress)
        worker.run()

        assert progress_spy.count() >= 1
        assert finished_spy.count() == 1
        assert finished_spy.at(0)[2] == "ocr"
        notification_service.info.assert_called_once_with(
            "OCR completed. Translating...", title="WhisperBridge"
        )

    def test_capture_ocr_worker_preserves_ocr_failure_contract(self, mock_services):
        """OCR failures emit the original text/translation/error tuple."""
        ocr_service, _, _ = mock_services
        ocr_service.process_image.return_value = Mock(
            text="", success=False, error_message="vision failed"
        )

        worker = CaptureOcrTranslateWorker(image=Mock())
        finished_spy = QSignalSpy(worker.finished)
        worker.run()

        assert finished_spy.count() == 1
        assert finished_spy.at(0) == ["", "", "ocr", "vision failed"]

    def test_capture_ocr_worker_reports_unavailable_translation(self, mock_services):
        """A missing translation service preserves the OCR result and error."""
        ocr_service, translation_service, _ = mock_services
        translation_service.is_available = False

        worker = CaptureOcrTranslateWorker(image=Mock())
        finished_spy = QSignalSpy(worker.finished)
        worker.run()

        assert finished_spy.at(0) == ["original", "", "ocr", "Translation service not configured"]
        translation_service.translate_text.assert_not_called()

    def test_capture_ocr_worker_cancel(self, mock_services, mocker):
        """Test worker respects cancel request."""
        ocr_service, _, _ = mock_services
        worker = CaptureOcrTranslateWorker(image=Mock())
        worker.request_cancel()

        finished_spy = QSignalSpy(worker.finished)
        worker.run()

        ocr_service.process_image.assert_not_called()
        assert finished_spy.count() == 1
        assert finished_spy.at(0) == ["", "", "", ""]

    def test_capture_ocr_worker_requires_image(self):
        """Worker constructor must reject missing image input."""
        with pytest.raises(ValueError, match="image is required"):
            CaptureOcrTranslateWorker(image=None)

    def test_processing_error_preserves_overlay_error_payload(self, mock_services):
        """Processing failures inside OCR keep the existing overlay error payload."""
        ocr_service, _, _ = mock_services
        ocr_service.process_image.side_effect = Exception("processing exploded")

        worker = CaptureOcrTranslateWorker(image=Mock())
        finished_spy = QSignalSpy(worker.finished)

        worker.run()

        assert finished_spy.at(0) == [
            "Processing error",
            "",
            "ocr",
            "processing exploded",
        ]
        with pytest.raises(AttributeError):
            worker.error

    def test_external_ocr_crash_emits_infrastructure_error_payload(self, mock_services, mocker):
        """A failure acquiring the OCR service uses the notification-only payload."""
        get_ocr_service_mock = mocker.patch(
            "whisperbridge.ui_qt.workers.get_ocr_service",
            side_effect=Exception("ocr service unavailable"),
        )
        worker = CaptureOcrTranslateWorker(image=Mock())
        finished_spy = QSignalSpy(worker.finished)

        worker.run()

        get_ocr_service_mock.assert_called_once_with()
        assert finished_spy.at(0) == ["", "", "", "ocr service unavailable"]

    def test_capture_service_is_not_called_when_image_provided(self, mock_services, mocker):
        """Worker must process the exact pre-captured image passed by caller."""
        ocr_service, _, _ = mock_services

        pre_captured_image = Mock()
        worker = CaptureOcrTranslateWorker(image=pre_captured_image)
        worker.run()

        request = ocr_service.process_image.call_args.args[0]
        assert request.image is pre_captured_image

    def test_worker_cancellation_during_processing(self, qtbot, mock_services):
        """Test worker respects cancellation request during processing."""
        worker = CaptureOcrTranslateWorker(image=Mock())
        progress_spy = QSignalSpy(worker.progress)
        finished_spy = QSignalSpy(worker.finished)
        
        # Request cancellation before run
        worker.request_cancel()
        
        worker.run()
        
        # Worker should return early without emitting progress
        assert progress_spy.count() == 0
        assert finished_spy.count() == 1
        assert finished_spy.at(0) == ["", "", "", ""]


@pytest.mark.skipif(ApiTestWorker is None, reason="Requires Qt and project dependencies")
class TestApiTestWorker:
    """Tests for ApiTestWorker."""
    
    def test_api_test_worker_error(self, qtbot, mocker):
        """Test API test worker handles errors."""
        # Patch where the function is imported and used, not where it's defined
        mock_get_api = mocker.patch('whisperbridge.ui_qt.workers.get_api_manager')
        mock_api = Mock()
        mock_api.is_initialized.return_value = True
        mock_api.get_available_models_sync.return_value = ([], 'error')
        mock_get_api.return_value = mock_api
        
        worker = ApiTestWorker("openai", "invalid-key")
        finished_spy = QSignalSpy(worker.finished)
        
        worker.run()
        
        assert finished_spy.count() == 1
        assert finished_spy.at(0) == [False, "API error or invalid key", [], ""]
        with pytest.raises(AttributeError):
            worker.error
    
    def test_api_test_worker_no_models(self, qtbot, mocker):
        """Test API test worker handles no models available."""
        # Patch where the function is imported and used, not where it's defined
        mock_get_api = mocker.patch('whisperbridge.ui_qt.workers.get_api_manager')
        mock_api = Mock()
        mock_api.is_initialized.return_value = True
        mock_api.get_available_models_sync.return_value = ([], 'api')
        mock_get_api.return_value = mock_api
        
        worker = ApiTestWorker("openai", "valid-key")
        finished_spy = QSignalSpy(worker.finished)
        
        worker.run()
        
        assert finished_spy.count() == 1
        assert finished_spy.at(0) == [False, "No models available for this API key", [], ""]
    
    def test_api_test_worker_unconfigured(self, qtbot, mocker):
        """Test API test worker handles unconfigured provider."""
        # Patch where the function is imported and used, not where it's defined
        mock_get_api = mocker.patch('whisperbridge.ui_qt.workers.get_api_manager')
        mock_api = Mock()
        mock_api.is_initialized.return_value = False
        mock_api.get_available_models_sync.return_value = ([], 'unconfigured')
        mock_get_api.return_value = mock_api
        
        worker = ApiTestWorker("openai", "valid-key")
        finished_spy = QSignalSpy(worker.finished)
        
        worker.run()
        
        assert finished_spy.count() == 1
        assert finished_spy.at(0) == [False, "API error or invalid key", [], ""]
        

@pytest.mark.skipif(BaseWorker is None, reason="Requires Qt and project dependencies")
class TestErrorRecovery:
    """Tests for worker error recovery scenarios."""
    
    @pytest.fixture(autouse=True)
    def mock_qmessagebox(self, mocker):
        """Mock QMessageBox to prevent blocking dialogs and crashes in tests."""
        mock_warn = mocker.patch('PySide6.QtWidgets.QMessageBox.warning')
        yield mock_warn
    
    @pytest.fixture
    def mock_config_service(self, monkeypatch):
        """Mock config_service with controllable timeout."""
        timeout_value = [60]
        
        def get_setting(key):
            if key == "api_timeout":
                return timeout_value[0]
            if key == "ui_source_language": return "en"
            if key == "ui_target_language": return "ru"
            return None
        
        monkeypatch.setattr(
            'whisperbridge.services.config_service.config_service.get_setting',
            get_setting
        )
        return timeout_value
    
    @pytest.fixture
    def overlay(self, qtbot, mock_config_service):
        """Create OverlayWindow instance."""
        window = OverlayWindow()
        window._update_layout()
        qtbot.addWidget(window)
        yield window
        # Cleanup any remaining threads/workers
        for thread in window.findChildren(QThread):
            if thread.isRunning():
                thread.quit()
                thread.wait(500)
    
    def test_worker_recovery_after_exception(self, qtbot, overlay):
        """Test that a new worker can be created after previous one raised exception."""
        # First worker raises exception
        worker1, thread1 = overlay._setup_worker(ManualCompletionWorker, "result", "Some error")
        with qtbot.waitSignal(thread1.finished, timeout=1000):
            assert QMetaObject.invokeMethod(worker1, "complete_error", Qt.QueuedConnection)
        
        # First thread may be deleted by Qt's deleteLater, so handle gracefully
        try:
            # Verify first thread stopped
            assert not thread1.isRunning()
        except RuntimeError:
            # Thread was deleted - that's OK, means cleanup worked
            pass
        
        # Second worker should work normally
        worker2, thread2 = overlay._setup_worker(ManualCompletionWorker)
        assert thread2.isRunning()
        
        # Complete second worker
        with qtbot.waitSignal(thread2.finished, timeout=1000):
            assert QMetaObject.invokeMethod(worker2, "complete_success", Qt.QueuedConnection)
        
        # Second thread may also be deleted, handle gracefully
        try:
            # Verify second thread stopped cleanly
            assert not thread2.isRunning()
        except RuntimeError:
            # Thread was deleted - that's OK, means cleanup worked
            pass
    
    def test_multiple_consecutive_worker_failures(self, qtbot, overlay):
        """Test that multiple consecutive worker failures don't break the system."""
        # Run 5 workers that all fail
        for i in range(5):
            worker, thread = overlay._setup_worker(
                ManualCompletionWorker, "result", f"Error {i}"
            )
            with qtbot.waitSignal(thread.finished, timeout=1000):
                assert QMetaObject.invokeMethod(worker, "complete_error", Qt.QueuedConnection)
            
            # Thread may be deleted by Qt's deleteLater, so handle gracefully
            try:
                # Verify thread stopped after error
                assert not thread.isRunning()
            except RuntimeError:
                # Thread was deleted - that's OK, means cleanup worked
                pass
        
        # Now run a successful worker
        worker_success, thread_success = overlay._setup_worker(ManualCompletionWorker)
        assert thread_success.isRunning()
        
        # Complete successfully
        with qtbot.waitSignal(thread_success.finished, timeout=1000):
            assert QMetaObject.invokeMethod(worker_success, "complete_success", Qt.QueuedConnection)
        
        # Thread may be deleted, handle gracefully
        try:
            # Verify it stopped cleanly
            assert not thread_success.isRunning()
        except RuntimeError:
            # Thread was deleted - that's OK, means cleanup worked
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
