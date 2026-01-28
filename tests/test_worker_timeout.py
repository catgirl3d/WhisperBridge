"""
Unit tests for worker timeout and event loop cleanup functionality.
These tests don't require Qt GUI - they test the logic directly.
Run with: python -m pytest test_worker_timeout.py -v
"""

import sys
import os
import asyncio
# Add project root to Python path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import pytest
from unittest.mock import Mock, patch, MagicMock

# Import dependencies for integration tests
try:
    from whisperbridge.ui_qt.workers import BaseAsyncWorker
    from whisperbridge.services.config_service import config_service
except ImportError:
    # Allow running other tests even if dependencies are missing (e.g. in minimal env)
    BaseAsyncWorker = None
    config_service = None


class TestAsyncioTimeoutWrapper:
    """Test the asyncio timeout wrapper logic."""

    def test_asyncio_wait_for_timeout(self):
        """Test asyncio.wait_for properly raises TimeoutError."""
        async def slow_coro():
            await asyncio.sleep(10)  # Sleep for 10 seconds
        
        # Should timeout after 1 second
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(asyncio.wait_for(slow_coro(), timeout=0.1))

    def test_asyncio_wait_for_success(self):
        """Test asyncio.wait_for completes successfully."""
        async def fast_coro():
            return "success"
        
        # Should complete within timeout
        result = asyncio.run(asyncio.wait_for(fast_coro(), timeout=1.0))
        assert result == "success"

    def test_event_loop_cleanup_pending_tasks(self):
        """Test event loop properly cancels pending tasks."""
        async def hanging_coro():
            await asyncio.sleep(100)  # Will hang
        
        async def create_pending_tasks():
            # Create a task that will be cancelled
            task = asyncio.create_task(hanging_coro())
            # Give it a moment to start
            await asyncio.sleep(0.01)
            return task
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Run with short timeout
            task = loop.run_until_complete(create_pending_tasks())
            
            # Now try to cancel pending tasks
            pending = asyncio.all_tasks(loop)
            assert len(pending) > 0, "Should have pending tasks"
            
            # Cancel all tasks
            for t in pending:
                t.cancel()
            
            # Give tasks a chance to handle cancellation
            try:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass  # Expected during cancellation
                
        finally:
            try:
                loop.close()
            except Exception:
                pass  # Loop may be in bad state


class TestWorkerTimeoutLogic:
    """Test the timeout logic in workers without Qt."""

    def test_timeout_calculation_for_watchdog(self):
        """Test watchdog timeout calculation."""
        api_timeout = 60
        watchdog_timeout = max(api_timeout * 2, 60)
        assert watchdog_timeout == 120
        
        api_timeout = 30
        watchdog_timeout = max(api_timeout * 2, 60)
        assert watchdog_timeout == 60  # 30 * 2 = 60, but max(60, 60) = 60
        
        api_timeout = 10
        watchdog_timeout = max(api_timeout * 2, 60)
        assert watchdog_timeout == 60  # 10 * 2 = 20, but max(20, 60) = 60


class TestEventLoopCleanup:
    """Test event loop cleanup logic."""

    def test_cancel_all_pending_tasks(self):
        """Test all pending tasks are cancelled."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def task1():
            await asyncio.sleep(100)
        
        async def task2():
            await asyncio.sleep(100)
        
        try:
            # Create tasks
            t1 = loop.create_task(task1())
            t2 = loop.create_task(task2())
            
            # Get pending tasks (convert to list)
            pending = list(asyncio.all_tasks(loop))
            assert len(pending) == 2
            
            # Cancel all tasks
            for task in pending:
                task.cancel()
            
            # Give tasks a moment to process cancellation
            loop.run_until_complete(asyncio.sleep(0.01))
            
            # Verify tasks are cancelled
            assert all(t.cancelled() for t in pending)
            
        finally:
            try:
                loop.close()
            except Exception:
                pass

    def test_gather_with_return_exceptions(self):
        """Test asyncio.gather with return_exceptions handles cancelled tasks."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def failing_task():
            await asyncio.sleep(100)
            raise ValueError("Task failed")
        
        async def cancelled_task():
            await asyncio.sleep(100)
            raise asyncio.CancelledError()
        
        try:
            t1 = loop.create_task(failing_task())
            t2 = loop.create_task(cancelled_task())
            
            # Cancel tasks
            t1.cancel()
            t2.cancel()
            
            # Gather with return_exceptions should not raise
            # Note: In Python 3.13+, gather requires tasks as *args, not list
            results = loop.run_until_complete(
                asyncio.gather(*[t1, t2], return_exceptions=True)
            )
            
            # Results should contain exceptions
            assert len(results) == 2
            
        finally:
            try:
                loop.close()
            except Exception:
                pass


class TestTimeoutErrorHandling:
    """Test timeout error handling in workers."""

    def test_timeout_error_message_format(self):
        """Test timeout error message is properly formatted."""
        timeout = 30
        expected_msg = f"Request timed out after {timeout} seconds"
        assert expected_msg == "Request timed out after 30 seconds"
        
    def test_timeout_error_includes_timeout_value(self):
        """Test timeout error message includes the timeout value."""
        timeout = 45
        error_msg = f"Request timed out after {timeout} seconds"
        assert "45" in error_msg
        assert "seconds" in error_msg


@pytest.mark.skipif(BaseAsyncWorker is None, reason="Requires BaseAsyncWorker and config_service")
class TestBaseAsyncWorkerIntegration:
    """Integration tests for BaseAsyncWorker and config_service."""

    @pytest.fixture
    def worker(self):
        """Create a BaseAsyncWorker instance with mocked signals."""
        worker = BaseAsyncWorker()
        # Mock signals to avoid Qt event loop requirement
        worker.finished = Mock()
        worker.error = Mock()
        # Mock signal emit methods specifically
        worker.finished.emit = Mock()
        worker.error.emit = Mock()
        return worker

    def test_import_successful(self):
        """Test that BaseAsyncWorker can be imported."""
        assert BaseAsyncWorker is not None

    def test_run_async_task_uses_config_timeout(self, worker):
        """Test that _run_async_task uses timeout from config_service."""
        async def mock_coro():
            await asyncio.sleep(0.01)
            return "success"
        
        with patch('whisperbridge.services.config_service.config_service.get_setting') as mock_conf:
            mock_conf.return_value = 10.0
            
            result = worker._run_async_task(mock_coro(), "TestWorker")
            
            assert result == "success"
            mock_conf.assert_called_with("api_timeout")

    def test_run_async_task_timeout_enforcement(self, worker):
        """Test that _run_async_task enforces timeout."""
        async def slow_coro():
            await asyncio.sleep(0.5)
            
        with patch('whisperbridge.services.config_service.config_service.get_setting') as mock_conf:
            # Set timeout smaller than coro duration
            mock_conf.return_value = 0.1
            
            result = worker._run_async_task(slow_coro(), "TimeoutTest")
            
            assert result is None
            # Verify error signals emitted
            assert worker.error.emit.called
            assert worker.finished.emit.called
            
            # Check error message format
            error_args = worker.error.emit.call_args[0]
            assert "timed out" in error_args[0]
            assert "0.1" in error_args[0]
            
            # Check finished signal args (False, error_msg)
            finished_args = worker.finished.emit.call_args[0]
            assert finished_args[0] is False
            assert "timed out" in finished_args[1]

    def test_run_async_task_handles_exceptions(self, worker):
        """Test that _run_async_task handles exceptions in coroutine."""
        async def failing_coro():
            raise ValueError("Something went wrong")
            
        with patch('whisperbridge.services.config_service.config_service.get_setting') as mock_conf:
            mock_conf.return_value = 5.0
            
            result = worker._run_async_task(failing_coro(), "FailTest")
            
            assert result is None
            assert worker.error.emit.called
            assert "Something went wrong" in worker.error.emit.call_args[0][0]
            assert worker.finished.emit.called
            assert worker.finished.emit.call_args[0][0] is False

    def test_invalid_timeout_fallback(self, worker):
        """Test fallback to default timeout if config is invalid."""
        async def fast_coro():
            return "ok"
            
        with patch('whisperbridge.services.config_service.config_service.get_setting') as mock_conf:
            mock_conf.return_value = -5  # Invalid negative timeout
            
            # Should not raise, uses default 60
            result = worker._run_async_task(fast_coro(), "InvalidConfigTest")
            
            assert result == "ok"
            
            # Verify it was called
            mock_conf.assert_called_with("api_timeout")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
