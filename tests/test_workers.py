"""
Minimal tests for worker classes and factory.
Run with: python -m pytest test_workers.py
"""

import pytest
from unittest.mock import Mock
from PySide6.QtCore import QObject, Signal, QThread
from typing import Protocol

from whisperbridge.ui_qt.workers import ApiTestWorker, TranslationWorker
from whisperbridge.services.config_workers import SettingsSaveWorker
from whisperbridge.ui_qt.app import QtApp

# If run directly, execute pytest with very verbose output and no coverage
if __name__ == "__main__":
    pytest.main([__file__, "-vv", "--no-cov"])

class RunnableWorker(Protocol):
    finished: Signal
    error: Signal

    def run(self): ...
    def moveToThread(self, thread: QThread): ...
    def deleteLater(self): ...


class MockWorker(RunnableWorker):
    """Mock worker for testing factory."""
    finished = Signal()
    error = Signal(str)

    def __init__(self, should_succeed=True):
        super().__init__()
        self.should_succeed = should_succeed

    def run(self):
        if self.should_succeed:
            self.finished.emit()
        else:
            self.error.emit("Mock error")

    def moveToThread(self, thread: QThread):
        pass

    def deleteLater(self):
        pass


class TestWorkers:
    """Test worker signal emissions."""

    def test_api_test_worker_success(self, qtbot, mocker):
        """Test ApiTestWorker emits finished on success."""
        mock_get_api = mocker.patch('whisperbridge.ui_qt.workers.get_api_manager')
        mock_api = Mock()
        mock_api.is_initialized.return_value = True
        mock_api.get_available_models_sync.return_value = (['gpt-4'], 'mock')
        mock_get_api.return_value = mock_api

        worker = ApiTestWorker('openai', 'sk-test')
        with qtbot.waitSignal(worker.finished) as blocker:
            worker.run()
        assert blocker.args == [True, '', ['gpt-4'], 'mock']

    def test_api_test_worker_error(self, qtbot, mocker):
        """Test ApiTestWorker emits error on failure."""
        mock_get_api = mocker.patch('whisperbridge.ui_qt.workers.get_api_manager')
        mock_api = Mock()
        mock_api.is_initialized.return_value = True
        mock_api.get_available_models_sync.return_value = ([], 'error')
        mock_get_api.return_value = mock_api

        worker = ApiTestWorker('openai', 'sk-test')
        with qtbot.waitSignal(worker.error) as blocker:
            worker.run()
        assert blocker.args == ['API error or invalid key']


    def test_settings_save_worker_success(self, qtbot, mocker):
        """Test SettingsSaveWorker emits finished on success."""
        mock_sm = mocker.patch('whisperbridge.services.config_workers.settings_manager')
        mock_sm.save_settings.return_value = True

        worker = SettingsSaveWorker(Mock())
        with qtbot.waitSignal(worker.finished) as blocker:
            worker.run()
        assert blocker.args == [True, "Settings saved successfully."]

    def test_settings_save_worker_error(self, qtbot, mocker):
        """Test SettingsSaveWorker emits error on failure."""
        mock_sm = mocker.patch('whisperbridge.services.config_workers.settings_manager')
        mock_sm.save_settings.return_value = False

        worker = SettingsSaveWorker(Mock())
        with qtbot.waitSignal(worker.error) as blocker:
            worker.run()
        assert blocker.args == ["Failed to save settings."]

