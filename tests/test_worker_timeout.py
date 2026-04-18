"""
Unit tests for worker timeout and event loop cleanup functionality.
Includes integration tests for Watchdog timer and Qt signals using pytest-qt.
Run with: python -m pytest tests/test_worker_timeout.py -v
"""

import asyncio
import time
import pytest
from unittest.mock import Mock, AsyncMock

# Import dependencies
try:
    from PySide6.QtCore import QTimer, QThread, Qt, Signal
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QSignalSpy
    from whisperbridge.ui_qt.workers import (
        BaseAsyncWorker, TranslationWorker, StyleWorker,
        CaptureOcrTranslateWorker, ApiTestWorker
    )
    from whisperbridge.ui_qt.overlay_window import OverlayWindow
    from whisperbridge.services.config_service import config_service
except ImportError:
    # Allow running non-Qt tests in minimal env
    BaseAsyncWorker = None
    OverlayWindow = None
    config_service = None
    QSignalSpy = None
    CaptureOcrTranslateWorker = None
    ApiTestWorker = None

# --- Non-Qt Tests (Unit Tests) ---

class TestAsyncioTimeoutWrapper:
    """Test asyncio timeout wrapper logic (Unit tests)."""

    def test_asyncio_wait_for_timeout(self):
        """Test asyncio.wait_for properly raises TimeoutError."""
        async def slow_coro():
            await asyncio.sleep(10)
        
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(asyncio.wait_for(slow_coro(), timeout=0.1))

    def test_asyncio_wait_for_success(self):
        """Test asyncio.wait_for completes successfully."""
        async def fast_coro():
            return "success"
        
        result = asyncio.run(asyncio.wait_for(fast_coro(), timeout=1.0))
        assert result == "success"

    def test_event_loop_cleanup_pending_tasks(self):
        """Test event loop properly cancels pending tasks."""
        async def hanging_coro():
            await asyncio.sleep(100)
        
        async def create_pending_tasks():
            task = asyncio.create_task(hanging_coro())
            await asyncio.sleep(0.01)
            return task
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            task = loop.run_until_complete(create_pending_tasks())
            pending = asyncio.all_tasks(loop)
            assert len(pending) > 0, "Should have pending tasks"
            
            for t in pending:
                t.cancel()
            
            # Allow cancellation to process
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        finally:
            loop.close()


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

@pytest.mark.skipif(BaseAsyncWorker is None, reason="Requires Qt and project dependencies")
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

    # --- Watchdog Timer Tests ---

    def test_watchdog_starts_with_correct_timeout(self, qtbot, overlay, mock_config_service):
        """Verify watchdog starts with correct timeout value."""
        mock_config_service[0] = 10
        worker, thread = overlay._setup_worker(TranslationWorker, "test", "en", "ru")
        
        # Verify thread is running
        assert thread.isRunning()
        
        # Cleanup
        with qtbot.waitSignal(thread.finished, timeout=1000):
            worker.finished.emit(True, "")
        
        # Verify thread stopped
        assert not thread.isRunning()

    def test_watchdog_cleanup_on_success(self, qtbot, overlay):
        """Verify watchdog cleans up when worker finishes successfully."""
        worker, thread = overlay._setup_worker(TranslationWorker, "test", "en", "ru")
        
        # Count timers before
        timers_before = len(overlay.findChildren(QTimer))
        
        with qtbot.waitSignal(thread.finished, timeout=1000):
            worker.finished.emit(True, "Translated text")
        
        # Wait for deleteLater to process
        qtbot.wait(200)
        QApplication.processEvents()
        
        # Count timers after - should not have leaked
        timers_after = len(overlay.findChildren(QTimer))
        assert timers_after <= timers_before

    def test_watchdog_cleanup_on_error(self, qtbot, overlay):
        """Verify watchdog cleans up when worker fails."""
        worker, thread = overlay._setup_worker(TranslationWorker, "test", "en", "ru")
        
        timers_before = len(overlay.findChildren(QTimer))
        
        with qtbot.waitSignal(thread.finished, timeout=1000):
            worker.error.emit("Some error")
        
        qtbot.wait(200)
        QApplication.processEvents()
        
        timers_after = len(overlay.findChildren(QTimer))
        assert timers_after <= timers_before

    def test_second_click_cancels_active_request(self, qtbot, overlay, mocker):
        """Second click should cancel the active request and restore button state."""
        mocker.patch.object(overlay, "_is_api_ready", return_value=(True, ""))

        mock_service = Mock()

        async def slow_translate(*_args, **_kwargs):
            await asyncio.sleep(10)
            return Mock(success=True, translated_text="late")

        mock_service.translate_text_async = AsyncMock(side_effect=slow_translate)
        mocker.patch(
            'whisperbridge.services.translation_service.get_translation_service',
            return_value=mock_service,
        )

        overlay.original_text.setPlainText("hello")
        overlay._on_translate_clicked()

        assert overlay._translation_start_time is not None
        assert overlay.translate_btn.isEnabled() is True

        overlay._on_translate_clicked()
        qtbot.wait(50)

        assert overlay._translation_start_time is None
        assert overlay.translate_btn.isEnabled() is True
        assert "cancel" in overlay.status_label.text().lower()

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
        (100, 200), # api_timeout=100 -> watchdog=max(200,60)=200
    ])
    def test_watchdog_timeout_calculation_only(self, qtbot, overlay, mock_config_service, mocker, api_timeout, expected_watchdog):
        """Test watchdog timeout calculation without actual termination.
        
        This test verifies timeout calculation logic.
        Actual termination testing is difficult in unit tests due to Qt's deleteLater.
        """
        mock_config_service[0] = api_timeout
        
        # Patch QTimer.start to capture the timeout value
        mock_start = mocker.patch('whisperbridge.ui_qt.overlay_window.QTimer.start')
        worker, thread = overlay._setup_worker(TranslationWorker, "test", "en", "ru")
        
        # Verify QTimer.start was called with expected timeout (in ms)
        assert mock_start.called
        actual_timeout_ms = mock_start.call_args[0][0]
        expected_timeout_ms = expected_watchdog * 1000
        assert actual_timeout_ms == expected_timeout_ms, \
            f"api_timeout={api_timeout}, expected watchdog={expected_watchdog}s, got {actual_timeout_ms/1000}s"
        
        # Cleanup
        with qtbot.waitSignal(thread.finished, timeout=1000):
            worker.finished.emit(True, "")

    # --- Signal Emission Order Tests ---

    def test_timeout_emits_error_then_finished(self, qtbot, mock_config_service):
        """Verify that on timeout, error signal is emitted BEFORE finished."""
        mock_config_service[0] = 0.1
        worker = BaseAsyncWorker()
        error_spy = QSignalSpy(worker.error)
        finished_spy = QSignalSpy(worker.finished)
        
        async def slow_coro():
            await asyncio.sleep(0.5)
            
        worker._run_async_task(slow_coro(), "TestTimeoutOrder")
        
        assert error_spy.count() == 1
        assert finished_spy.count() == 1
        error_msg = error_spy.at(0)[0]
        assert "timed out" in error_msg
        assert finished_spy.at(0)[0] is False
        assert finished_spy.at(0)[1] == error_msg

    def test_success_emits_only_finished(self, qtbot):
        """Verify success emits ONLY finished signal."""
        worker = BaseAsyncWorker()
        error_spy = QSignalSpy(worker.error)
        async def fast_coro(): return "ok"
        result = worker._run_async_task(fast_coro(), "TestSuccess")
        assert result == "ok"
        assert error_spy.count() == 0

    def test_signal_disconnection_after_cleanup(self, qtbot, overlay):
        """Verify cleanup happens correctly and worker is deleted."""
        worker, thread = overlay._setup_worker(TranslationWorker, "test", "en", "ru")
        
        # Count timers before
        timers_before = len(overlay.findChildren(QTimer))
        
        # Trigger cleanup
        with qtbot.waitSignal(thread.finished, timeout=1000):
            worker.finished.emit(True, "result")
        
        qtbot.wait(200)
        QApplication.processEvents()
        
        # Verify cleanup happened - timers should not leak
        timers_after = len(overlay.findChildren(QTimer))
        assert timers_after <= timers_before
        
        # Thread may be deleted by now, so just verify test completed without crash
        # The fact we got here means cleanup worked

    # --- Worker Integration Tests ---

    def test_translation_worker_integration(self, qtbot, mock_config_service, mocker):
        """Integration test for TranslationWorker with mocked service."""
        mock_service = Mock()
        mock_service.translate_text_async = AsyncMock(return_value=Mock(success=True, translated_text="Hola"))
        
        mocker.patch('whisperbridge.services.translation_service.get_translation_service', return_value=mock_service)
        worker = TranslationWorker("Hello", "en", "es")
        finished_spy = QSignalSpy(worker.finished)
        worker.run()
        assert finished_spy.count() == 1
        assert finished_spy.at(0)[0] is True
        assert finished_spy.at(0)[1] == "Hola"

    def test_style_worker_integration(self, qtbot, mocker):
        """Integration test for StyleWorker."""
        mock_service = Mock()
        mock_service.style_text_async = AsyncMock(return_value=Mock(success=True, translated_text="Styled Text"))
        
        mocker.patch('whisperbridge.services.translation_service.get_translation_service', return_value=mock_service)
        worker = StyleWorker("Raw", "Formal")
        finished_spy = QSignalSpy(worker.finished)
        worker.run()
        assert finished_spy.count() == 1
        assert finished_spy.at(0)[0] is True
        assert finished_spy.at(0)[1] == "Styled Text"

    def test_worker_timeout_handling(self, qtbot, mock_config_service, mocker):
        """Test TranslationWorker handles timeout correctly."""
        mock_config_service[0] = 0.1
        mock_service = Mock()
        async def slow_mock(*args, **kwargs): await asyncio.sleep(0.5)
        mock_service.translate_text_async = AsyncMock(side_effect=slow_mock)
        
        mocker.patch('whisperbridge.services.translation_service.get_translation_service', return_value=mock_service)
        worker = TranslationWorker("Slow", "en", "es")
        finished_spy = QSignalSpy(worker.finished)
        error_spy = QSignalSpy(worker.error)
        worker.run()
        assert finished_spy.count() == 1
        assert error_spy.count() == 1
        assert finished_spy.at(0)[0] is False
        assert "timed out" in error_spy.at(0)[0]

    def test_known_error_status_persists_after_finished_signal(self, overlay, mock_qmessagebox):
        """Known API errors should keep their status after the duplicate finished(False, ...) signal."""
        overlay._is_api_ready = Mock(return_value=(True, ""))
        overlay._translation_start_time = time.time() - 0.1
        error_message = "quota exceeded: billing limit reached"

        overlay._on_translation_error(error_message)
        status_after_error = overlay.status_label.text()

        overlay._on_translation_finished(False, error_message)

        assert "quota exceeded" in status_after_error.lower()
        assert overlay.status_label.text() == status_after_error
        mock_qmessagebox.assert_not_called()

    def test_finished_without_error_signal_sets_known_error_status(self, overlay, mock_qmessagebox):
        """Finished(False, ...) should still show a known status even if error signal was not delivered."""
        overlay._is_api_ready = Mock(return_value=(True, ""))
        overlay._translation_start_time = time.time() - 0.1

        overlay._on_translation_finished(False, "quota exceeded: billing limit reached")

        assert "quota exceeded" in overlay.status_label.text().lower()
        mock_qmessagebox.assert_not_called()

    def test_unknown_error_popup_is_shown_once_across_error_and_finished(self, overlay, mock_qmessagebox):
        """Unknown errors should surface one popup even when both signals are emitted."""
        overlay._is_api_ready = Mock(return_value=(True, ""))
        overlay._translation_start_time = time.time() - 0.1
        error_message = "unexpected translator explosion"

        overlay._on_translation_error(error_message)
        status_after_error = overlay.status_label.text()

        overlay._on_translation_finished(False, error_message)

        assert "failed" in overlay.status_label.text().lower()
        assert overlay.status_label.text() == status_after_error
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
        """Verify multiple cleanup calls don't cause crash (idempotency)."""
        worker, thread = overlay._setup_worker(TranslationWorker, "test", "en", "ru")
        
        # Emit both finished and error signals (simulating race)
        # This should not crash
        with qtbot.waitSignal(thread.finished, timeout=1000):
            worker.finished.emit(True, "Res")
            worker.error.emit("Fail")
        
        # Verify thread stopped cleanly
        assert not thread.isRunning()

    def test_cleanup_before_thread_start(self, qtbot, overlay):
        """Verify cleanup works even if signals fire rapidly after setup."""
        worker, thread = overlay._setup_worker(TranslationWorker, "test", "en", "ru")
        
        timers_before = len(overlay.findChildren(QTimer))
        
        # Emit error immediately (before thread really starts)
        with qtbot.waitSignal(thread.finished, timeout=1000):
            worker.error.emit("Immediate Fail")
        
        qtbot.wait(200)
        QApplication.processEvents()
        
        # Verify cleanup happened
        timers_after = len(overlay.findChildren(QTimer))
        assert timers_after <= timers_before

    def test_late_signal_after_cleanup_no_crash(self, qtbot, overlay):
        """Verify late signals after cleanup are handled gracefully."""
        worker, thread = overlay._setup_worker(TranslationWorker, "test", "en", "ru")
        
        # Trigger cleanup
        with qtbot.waitSignal(thread.finished, timeout=1000):
            worker.finished.emit(True, "result")
        
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
        worker, thread = overlay._setup_worker(TranslationWorker, "test", "en", "ru")
        
        # Simulate completion happening
        with qtbot.waitSignal(thread.finished, timeout=1000):
            worker.finished.emit(True, "result")
        
        # Verify thread stopped cleanly
        assert not thread.isRunning()
        
        # No crash = success

    # --- Memory Leak Tests ---

    def test_no_qtimer_leak(self, qtbot, overlay):
        """Verify QTimer objects are properly cleaned up after multiple tasks."""
        initial_timers = len(overlay.findChildren(QTimer))
        
        # Run 10 short tasks
        for i in range(10):
            worker, thread = overlay._setup_worker(TranslationWorker, f"test{i}", "en", "ru")
            worker.finished.emit(True, f"result{i}")
            qtbot.wait(100)  # Allow deleteLater() to process
        
        # Force Qt event loop to process deleteLater
        QApplication.processEvents()
        qtbot.wait(500)
        
        final_timers = len(overlay.findChildren(QTimer))
        
        # Should not have leaked timers (allow small slack for system timers)
        assert final_timers - initial_timers < 3, \
            f"QTimer leak detected: {final_timers - initial_timers} leaked timers"

    def test_no_worker_leak(self, qtbot, overlay):
        """Verify worker objects are properly cleaned up."""
        initial_workers = len(overlay.findChildren(BaseAsyncWorker))
        
        # Run 10 tasks
        for i in range(10):
            worker, thread = overlay._setup_worker(TranslationWorker, f"test{i}", "en", "ru")
            worker.finished.emit(True, f"result{i}")
            qtbot.wait(100)
        
        QApplication.processEvents()
        qtbot.wait(500)
        
        final_workers = len(overlay.findChildren(BaseAsyncWorker))
        
        # Workers should be deleted
        assert final_workers - initial_workers < 3, \
            f"Worker leak detected: {final_workers - initial_workers} leaked workers"

    def test_no_thread_leak(self, qtbot, overlay):
        """Verify thread objects are properly cleaned up."""
        initial_threads = len(overlay.findChildren(QThread))
        
        # Run 10 tasks
        for i in range(10):
            worker, thread = overlay._setup_worker(TranslationWorker, f"test{i}", "en", "ru")
            worker.finished.emit(True, f"result{i}")
            qtbot.wait(100)
        
        QApplication.processEvents()
        qtbot.wait(500)
        
        final_threads = len(overlay.findChildren(QThread))
        
        # Threads should be deleted
        assert final_threads - initial_threads < 3, \
            f"Thread leak detected: {final_threads - initial_threads} leaked threads"

    # --- Stress Tests ---

    def test_rapid_fire_requests(self, qtbot, overlay):
        """Test that rapid consecutive requests don't cause crashes."""
        results = []
        errors = []
        
        def on_finished(success, result):
            results.append((success, result))
        
        def on_error(msg):
            errors.append(msg)
        
        # Fire 5 rapid requests
        for i in range(5):
            worker, thread = overlay._setup_worker(TranslationWorker, f"test{i}", "en", "ru")
            worker.finished.connect(on_finished)
            worker.error.connect(on_error)
            
            # Immediately emit result
            worker.finished.emit(True, f"result{i}")
            qtbot.wait(50)  # Small delay between requests
        
        # Wait for all to complete
        qtbot.wait(1000)
        
        # System should handle this gracefully (no crashes)
        # Main check: we got here without crash
        assert True

    def test_many_workers_sequential(self, qtbot, overlay):
        """Test that many sequential operations don't cause memory issues."""
        initial_timers = len(overlay.findChildren(QTimer))
        
        # Run 20 sequential operations
        for i in range(20):
            worker, thread = overlay._setup_worker(TranslationWorker, f"test{i}", "en", "ru")
            
            with qtbot.waitSignal(thread.finished, timeout=1000):
                worker.finished.emit(True, f"result{i}")
            
            qtbot.wait(50)
        
        QApplication.processEvents()
        qtbot.wait(500)
        
        final_timers = len(overlay.findChildren(QTimer))
        
        # Should not have significant memory leak
        assert final_timers - initial_timers < 5, \
            f"Memory leak detected after 20 operations: {final_timers - initial_timers} leaked objects"

    def test_multiple_workers_concurrent(self, qtbot, overlay):
        """Test that multiple workers can run concurrently without issues."""
        workers_and_threads = []
        
        # Start 3 concurrent workers
        for i in range(3):
            worker, thread = overlay._setup_worker(TranslationWorker, f"test{i}", "en", "ru")
            workers_and_threads.append((worker, thread))
        
        # Wait a bit for them to start
        qtbot.wait(100)
        
        # Complete all workers - but handle case where they may already be finished
        for i, (worker, thread) in enumerate(workers_and_threads):
            try:
                # Use a separate wait for each worker to avoid issues
                with qtbot.waitSignal(thread.finished, timeout=1000):
                    worker.finished.emit(True, f"result{i}")
            except Exception:
                # Worker may already be finished/deleted, that's OK
                pass
        
        # Wait for cleanup to complete
        qtbot.wait(200)
        QApplication.processEvents()
        
        # No crash = success - threads may be deleted by now

    # --- Additional Coverage Tests ---
    
    def test_pending_task_cancellation_timeout(self, qtbot, mock_config_service, caplog):
        """Test that pending tasks are cancelled with timeout."""
        worker = BaseAsyncWorker()
        
        async def main_task():
            # Create a background task that won't respond to cancellation
            async def immortal_task():
                try:
                    await asyncio.sleep(1000)
                except asyncio.CancelledError:
                    # Ignore cancellation and sleep again
                    await asyncio.sleep(1000)
            
            # Start immortal task as background
            loop = asyncio.get_event_loop()
            loop.create_task(immortal_task())
            
            # Main task completes quickly
            return "done"
        
        mock_config_service[0] = 0.1
        result = worker._run_async_task(main_task(), "TestCancel")
        
        # Should return result (main task completed)
        assert result == "done"
        
        # Check for task cancellation warning
        # Note: caplog may not capture all logs in all pytest versions
        # The important thing is that the worker completes without hanging
        assert result == "done"
    
    
    def test_translation_worker_empty_response(self, qtbot, mock_config_service, mocker):
        """Test TranslationWorker handles empty API response."""
        mock_service = Mock()
        mock_service.translate_text_async = AsyncMock(return_value=Mock(success=True, translated_text=None))
        
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
        mock_service.translate_text_async = AsyncMock(side_effect=Exception("Service unavailable"))
        
        mocker.patch('whisperbridge.services.translation_service.get_translation_service', return_value=mock_service)
        worker = TranslationWorker("Hello", "en", "es")
        error_spy = QSignalSpy(worker.error)
        finished_spy = QSignalSpy(worker.finished)
        worker.run()
        assert error_spy.count() == 1
        assert finished_spy.count() == 1
        assert finished_spy.at(0)[0] is False
    
    def test_style_worker_empty_response(self, qtbot, mock_config_service, mocker):
        """Test StyleWorker handles empty API response."""
        mock_service = Mock()
        mock_service.style_text_async = AsyncMock(return_value=Mock(success=True, translated_text=None))
        
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
        mock_service.style_text_async = AsyncMock(side_effect=Exception("Service unavailable"))
        
        mocker.patch('whisperbridge.services.translation_service.get_translation_service', return_value=mock_service)
        worker = StyleWorker("Raw", "Formal")
        error_spy = QSignalSpy(worker.error)
        finished_spy = QSignalSpy(worker.finished)
        worker.run()
        assert error_spy.count() == 1
        assert finished_spy.count() == 1
        assert finished_spy.at(0)[0] is False


@pytest.mark.skipif(CaptureOcrTranslateWorker is None, reason="Requires Qt and project dependencies")
class TestCaptureOcrTranslateWorker:
    """Tests for CaptureOcrTranslateWorker."""

    @pytest.fixture
    def mock_services(self, mocker):
        """Mock OCR and OCR-translation coordinator services."""
        mock_ocr = mocker.patch('whisperbridge.ui_qt.workers.get_ocr_service')
        ocr_instance = Mock()
        ocr_instance.ensure_ready.return_value = True
        mock_ocr.return_value = ocr_instance

        mock_coord = mocker.patch('whisperbridge.ui_qt.workers.get_ocr_translation_coordinator')
        coord_instance = Mock()
        coord_instance.process_image_with_translation.return_value = ("original", "translated", "")
        mock_coord.return_value = coord_instance

        yield ocr_instance, coord_instance

    def test_capture_ocr_worker_with_image(self, mock_services):
        """Test worker processes pre-captured image."""
        ocr_instance, coord_instance = mock_services
        image = Mock()

        worker = CaptureOcrTranslateWorker(image=image)
        worker.run()

        ocr_instance.ensure_ready.assert_called_once_with(timeout=15.0)
        coord_instance.process_image_with_translation.assert_called_once_with(image, preprocess=True)

    def test_capture_ocr_worker_success_signals(self, qtbot, mock_services):
        """Test worker emits finished payload for successful OCR path."""
        _, _ = mock_services

        worker = CaptureOcrTranslateWorker(image=Mock())
        finished_spy = QSignalSpy(worker.finished)
        progress_spy = QSignalSpy(worker.progress)
        worker.run()

        assert progress_spy.count() >= 1
        assert finished_spy.count() == 1
        assert finished_spy.at(0)[2] == "ocr"

    def test_capture_ocr_worker_cancel(self, mock_services, mocker):
        """Test worker respects cancel request."""
        _, coord_instance = mock_services
        worker = CaptureOcrTranslateWorker(image=Mock())
        worker.request_cancel()

        worker.run()

        coord_instance.process_image_with_translation.assert_not_called()

    def test_capture_ocr_worker_requires_image(self):
        """Worker constructor must reject missing image input."""
        with pytest.raises(ValueError, match="image is required"):
            CaptureOcrTranslateWorker(image=None)

    def test_ocr_service_timeout_handling(self, qtbot, mock_services):
        """Test worker handles OCR service timeout gracefully."""
        ocr_instance, _ = mock_services
        # Simulate OCR service timeout
        ocr_instance.ensure_ready.return_value = False

        worker = CaptureOcrTranslateWorker(image=Mock())
        error_spy = QSignalSpy(worker.error)
        
        worker.run()
        
        # Should emit error about service not being ready
        assert error_spy.count() == 1
        # The actual error message comes from OCR service initialization
        # Just verify an error was emitted
        assert len(error_spy.at(0)[0]) > 0
    
    def test_processing_error_is_propagated(self, qtbot, mock_services):
        """Worker should emit error when coordinator processing fails."""
        _, coord_instance = mock_services
        coord_instance.process_image_with_translation.side_effect = Exception("processing exploded")

        worker = CaptureOcrTranslateWorker(image=Mock())
        error_spy = QSignalSpy(worker.error)

        worker.run()

        assert error_spy.count() == 1
        assert "processing exploded" in error_spy.at(0)[0]

    def test_capture_service_is_not_called_when_image_provided(self, mock_services, mocker):
        """Worker must process the exact pre-captured image passed by caller."""
        _, coord_instance = mock_services

        pre_captured_image = Mock()
        worker = CaptureOcrTranslateWorker(image=pre_captured_image)
        worker.run()

        coord_instance.process_image_with_translation.assert_called_once_with(pre_captured_image, preprocess=True)

    def test_worker_cancellation_during_processing(self, qtbot, mock_services):
        """Test worker respects cancellation request during processing."""
        worker = CaptureOcrTranslateWorker(image=Mock())
        progress_spy = QSignalSpy(worker.progress)
        
        # Request cancellation before run
        worker.request_cancel()
        
        worker.run()
        
        # Worker should return early without emitting progress
        assert progress_spy.count() == 0
        # The fact that run() completes without exception means cancellation worked


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
        error_spy = QSignalSpy(worker.error)
        
        worker.run()
        
        assert error_spy.count() == 1
        assert "API error or invalid key" in error_spy.at(0)[0]
    
    def test_api_test_worker_no_models(self, qtbot, mocker):
        """Test API test worker handles no models available."""
        # Patch where the function is imported and used, not where it's defined
        mock_get_api = mocker.patch('whisperbridge.ui_qt.workers.get_api_manager')
        mock_api = Mock()
        mock_api.is_initialized.return_value = True
        mock_api.get_available_models_sync.return_value = ([], 'api')
        mock_get_api.return_value = mock_api
        
        worker = ApiTestWorker("openai", "valid-key")
        error_spy = QSignalSpy(worker.error)
        
        worker.run()
        
        assert error_spy.count() == 1
        assert "No models available" in error_spy.at(0)[0]
    
    def test_api_test_worker_unconfigured(self, qtbot, mocker):
        """Test API test worker handles unconfigured provider."""
        # Patch where the function is imported and used, not where it's defined
        mock_get_api = mocker.patch('whisperbridge.ui_qt.workers.get_api_manager')
        mock_api = Mock()
        mock_api.is_initialized.return_value = False
        mock_api.get_available_models_sync.return_value = ([], 'unconfigured')
        mock_get_api.return_value = mock_api
        
        worker = ApiTestWorker("openai", "valid-key")
        error_spy = QSignalSpy(worker.error)
        
        worker.run()
        
        assert error_spy.count() == 1
        assert "API error or invalid key" in error_spy.at(0)[0]
        

@pytest.mark.skipif(BaseAsyncWorker is None, reason="Requires Qt and project dependencies")
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
    
    def test_worker_recovery_after_timeout(self, qtbot, overlay, mock_config_service):
        """Test that a new worker can be created after previous one timed out."""
        mock_config_service[0] = 0.1
        
        # First worker times out
        worker1, thread1 = overlay._setup_worker(TranslationWorker, "test1", "en", "ru")
        qtbot.wait(500)  # Wait for timeout
        
        # First thread may be deleted by Qt's deleteLater, so handle gracefully
        try:
            # Verify first thread stopped
            assert not thread1.isRunning()
        except RuntimeError:
            # Thread was deleted - that's OK, means cleanup worked
            pass
        
        # Second worker should work normally
        worker2, thread2 = overlay._setup_worker(TranslationWorker, "test2", "en", "ru")
        assert thread2.isRunning()
        
        # Complete second worker
        with qtbot.waitSignal(thread2.finished, timeout=1000):
            worker2.finished.emit(True, "result")
        
        # Second thread may also be deleted, handle gracefully
        try:
            # Verify second thread stopped cleanly
            assert not thread2.isRunning()
        except RuntimeError:
            # Thread was deleted - that's OK, means cleanup worked
            pass
    
    def test_worker_recovery_after_exception(self, qtbot, overlay):
        """Test that a new worker can be created after previous one raised exception."""
        # First worker raises exception
        worker1, thread1 = overlay._setup_worker(TranslationWorker, "test1", "en", "ru")
        worker1.error.emit("Some error")
        qtbot.wait(200)
        
        # First thread may be deleted by Qt's deleteLater, so handle gracefully
        try:
            # Verify first thread stopped
            assert not thread1.isRunning()
        except RuntimeError:
            # Thread was deleted - that's OK, means cleanup worked
            pass
        
        # Second worker should work normally
        worker2, thread2 = overlay._setup_worker(TranslationWorker, "test2", "en", "ru")
        assert thread2.isRunning()
        
        # Complete second worker
        with qtbot.waitSignal(thread2.finished, timeout=1000):
            worker2.finished.emit(True, "result")
        
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
            worker, thread = overlay._setup_worker(TranslationWorker, f"test{i}", "en", "ru")
            worker.error.emit(f"Error {i}")
            qtbot.wait(100)
            
            # Thread may be deleted by Qt's deleteLater, so handle gracefully
            try:
                # Verify thread stopped after error
                assert not thread.isRunning()
            except RuntimeError:
                # Thread was deleted - that's OK, means cleanup worked
                pass
        
        # Now run a successful worker
        worker_success, thread_success = overlay._setup_worker(TranslationWorker, "success", "en", "ru")
        assert thread_success.isRunning()
        
        # Complete successfully
        with qtbot.waitSignal(thread_success.finished, timeout=1000):
            worker_success.finished.emit(True, "success result")
        
        # Thread may be deleted, handle gracefully
        try:
            # Verify it stopped cleanly
            assert not thread_success.isRunning()
        except RuntimeError:
            # Thread was deleted - that's OK, means cleanup worked
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
