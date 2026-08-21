"""
Tests for singleton management in api_manager module.

This module tests singleton functionality including:
- Creating singleton on first call
- Returning same instance on subsequent calls
- Single initialization
- Thread safety
- Error handling on initialization failure
"""

import threading
import time

import pytest

import whisperbridge.core.api_manager as api_manager_mod
from whisperbridge.core.api_manager import get_api_manager, init_api_manager


@pytest.fixture
def reset_singleton(mocker):
    """Fixture to reset the singleton state before and after each test."""
    # Store original state
    orig_api_manager = api_manager_mod._api_manager
    
    # Mock config_service dependency
    mocker.patch("whisperbridge.services.config_service.config_service", mocker.Mock())
    
    # Reset
    api_manager_mod._api_manager = None
    
    yield
    
    # Restore
    api_manager_mod._api_manager = orig_api_manager


class TestGetAPIManager:
    """Tests for get_api_manager function."""

    def test_get_api_manager_creates_singleton(self, reset_singleton):
        """Test that get_api_manager creates singleton on first call."""
        # Act
        manager = get_api_manager()

        # Assert
        assert isinstance(manager, api_manager_mod.APIManager)
        assert api_manager_mod._api_manager is manager

    def test_get_api_manager_returns_same_instance(self, reset_singleton):
        """Test that repeated calls return same instance."""
        # Act
        manager1 = get_api_manager()
        manager2 = get_api_manager()

        # Assert
        assert manager1 is manager2


class TestInitAPIManager:
    """Tests for init_api_manager function."""

    def test_init_api_manager_initializes_once(self, reset_singleton, mocker):
        """Test that initialization happens correctly."""
        # Note: We can't easily mock the 'initialize' method on the instance 
        # BEFORE it's created, so we check if the manager is returned initialized
        
        # Act
        manager = init_api_manager()

        # Assert
        assert manager.is_initialized() is True
        assert api_manager_mod._api_manager is manager

    def test_get_api_manager_thread_safety(self, reset_singleton, mocker):
        """Concurrent callers create exactly one shared singleton instance."""
        instances = []
        errors = []
        factory_lock = threading.Lock()
        factory_calls = 0

        def slow_factory(config):
            nonlocal factory_calls
            with factory_lock:
                factory_calls += 1
            time.sleep(0.01)
            return object()

        mocker.patch.object(api_manager_mod, "APIManager", side_effect=slow_factory)
        barrier = threading.Barrier(10)

        def get_manager():
            try:
                barrier.wait()
                manager = get_api_manager()
                instances.append(manager)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_manager) for _ in range(10)]
        for thread in threads:
            thread.start()

        for t in threads:
            t.join()

        # Assert
        assert len(errors) == 0, f"Thread safety errors: {errors}"
        assert len(instances) == 10
        assert all(inst is instances[0] for inst in instances)
        assert factory_calls == 1

    def test_init_api_manager_raises_on_failure(self, reset_singleton, mocker):
        """Test that RuntimeError is raised when initialization fails."""
        # Patch APIManager.initialize to fail
        mocker.patch("whisperbridge.core.api_manager.manager.APIManager.initialize", return_value=False)

        # Act & Assert
        with pytest.raises(RuntimeError, match="Failed to initialize API manager"):
            init_api_manager()


class TestSingletonBehavior:
    """Tests for overall singleton behavior."""

    def test_singleton_persists_across_calls(self, reset_singleton):
        """Test that singleton instance persists across multiple calls."""
        # Act
        manager1 = get_api_manager()
        manager2 = get_api_manager()
        manager3 = get_api_manager()

        # Assert
        assert manager1 is manager2
        assert manager2 is manager3
        assert manager1 is manager3
