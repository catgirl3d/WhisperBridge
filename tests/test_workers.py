"""
Minimal tests for worker classes and factory.
Run with: python -m pytest test_workers.py
"""

import sys
import os
# Add the project root to the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import Mock, patch
from PySide6.QtCore import QObject, Signal, QThread

from src.whisperbridge.ui_qt.workers import ApiTestWorker, TranslationWorker
from src.whisperbridge.services.config_workers import SettingsSaveWorker
from src.whisperbridge.ui_qt.app import QtApp
from typing import Protocol
from PySide6.QtCore import Signal, QObject, QThread

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

    def test_api_test_worker_success(self, qtbot):
        """Test ApiTestWorker emits finished on success."""
        with patch('src.whisperbridge.ui_qt.workers.get_api_manager') as mock_get_api:
            mock_api = Mock()
            mock_api.is_initialized.return_value = True
            mock_api.get_available_models_sync.return_value = (['gpt-4'], 'mock')
            mock_get_api.return_value = mock_api

            worker = ApiTestWorker('openai', 'sk-test')
            with qtbot.waitSignal(worker.finished) as blocker:
                worker.run()
            assert blocker.args == [True, '', ['gpt-4'], 'mock']

    def test_api_test_worker_error(self, qtbot):
        """Test ApiTestWorker emits error on failure."""
        with patch('src.whisperbridge.ui_qt.workers.get_api_manager') as mock_get_api:
            mock_api = Mock()
            mock_api.is_initialized.return_value = True
            mock_api.get_available_models_sync.return_value = ([], 'error')
            mock_get_api.return_value = mock_api

            worker = ApiTestWorker('openai', 'sk-test')
            with qtbot.waitSignal(worker.error) as blocker:
                worker.run()
            assert blocker.args == ['API error or invalid key']


    def test_settings_save_worker_success(self, qtbot):
        """Test SettingsSaveWorker emits finished on success."""
        with patch('src.whisperbridge.services.config_workers.settings_manager') as mock_sm:
            mock_sm.save_settings.return_value = True

            worker = SettingsSaveWorker(Mock())
            with qtbot.waitSignal(worker.finished) as blocker:
                worker.run()
            assert blocker.args == [True, "Settings saved successfully."]

    def test_settings_save_worker_error(self, qtbot):
        """Test SettingsSaveWorker emits error on failure."""
        with patch('src.whisperbridge.services.config_workers.settings_manager') as mock_sm:
            mock_sm.save_settings.return_value = False

            worker = SettingsSaveWorker(Mock())
            with qtbot.waitSignal(worker.error) as blocker:
                worker.run()
            assert blocker.args == ["Failed to save settings."]

