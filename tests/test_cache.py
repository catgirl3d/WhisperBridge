"""
Tests for ModelCache class in api_manager.cache module.

This module tests caching functionality including:
- Basic set/get operations
- TTL expiration
- Disk persistence
- Thread safety
- Model list validation
- Cache clearing operations
- Old file cleanup
"""

import json
import threading
import time
from pathlib import Path

import pytest
from freezegun import freeze_time

from whisperbridge.core.api_manager.cache import ModelCache


class TestCacheSetAndGet:
    """Tests for basic cache set and get operations."""

    def test_cache_set_and_get(self, tmp_path):
        """Test that cache can store and retrieve models correctly."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=1209600)
        models = ["gpt-4", "gpt-3.5"]

        # Act
        cache.set("openai", models)
        result = cache.get("openai")

        # Assert
        assert result is not None
        retrieved_models, timestamp = result
        assert retrieved_models == models
        assert isinstance(timestamp, float)


class TestCacheTTLExpiration:
    """Tests for TTL expiration functionality."""

    def test_cache_ttl_expiration(self, tmp_path):
        """Test that cache returns None after TTL expires."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=1)
        models = ["gpt-4", "gpt-3.5"]

        # Act - freeze time after TTL expires
        with freeze_time("2024-01-01 00:00:00") as frozen_time:
            cache.set("openai", models)
            
            # Check it's there
            assert cache.get("openai") is not None
            
            # Move time forward by 2 seconds
            frozen_time.tick(2)
            
            result = cache.get("openai")

        # Assert
        assert result is None


class TestCacheDiskPersistence:
    """Tests for disk persistence functionality."""

    def test_cache_disk_persistence(self, tmp_path):
        """Test that cache can be saved to and loaded from disk."""
        # Arrange
        cache1 = ModelCache(tmp_path, ttl_seconds=1209600)
        models = ["gpt-4", "gpt-3.5"]
        cache1.set("openai", models)
        cache1.save_to_disk()

        # Act - create new cache instance and load from disk
        cache2 = ModelCache(tmp_path, ttl_seconds=1209600)
        cache2.load_from_disk()
        result = cache2.get("openai")

        # Assert
        assert result is not None
        retrieved_models, _ = result
        assert retrieved_models == models


class TestCacheThreadSafety:
    """Tests for thread-safe operations."""

    def test_cache_thread_safety(self, tmp_path):
        """Test that cache handles concurrent operations safely."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=1209600)
        num_threads = 10
        errors = []

        def write_provider(provider_id):
            try:
                cache.set(f"provider_{provider_id}", [f"model_{provider_id}"])
            except Exception as e:
                errors.append(e)

        def read_provider(provider_id):
            try:
                cache.get(f"provider_{provider_id}")
            except Exception as e:
                errors.append(e)

        # Act - create concurrent threads
        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=write_provider, args=(i,))
            threads.append(t)
            t.start()

        for i in range(num_threads):
            t = threading.Thread(target=read_provider, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Assert
        assert len(errors) == 0, f"Thread safety errors: {errors}"

        # Verify all data was written correctly
        for i in range(num_threads):
            result = cache.get(f"provider_{i}")
            assert result is not None
            models, _ = result
            assert models == [f"model_{i}"]


class TestValidateModelList:
    """Tests for model list validation."""

    def test_validate_model_list_valid(self):
        """Test that valid model lists pass validation."""
        # Arrange & Act & Assert
        assert ModelCache.validate_model_list(["gpt-4", "gpt-3.5"]) is True
        assert ModelCache.validate_model_list(["model"]) is True
        assert ModelCache.validate_model_list(["  model  ", "another-model"]) is True

    def test_validate_model_list_invalid(self):
        """Test that invalid model lists fail validation."""
        # Arrange & Act & Assert
        assert ModelCache.validate_model_list([]) is False
        assert ModelCache.validate_model_list(None) is False
        assert ModelCache.validate_model_list(["", "  "]) is False
        assert ModelCache.validate_model_list([123, None]) is False
        assert ModelCache.validate_model_list(["valid", ""]) is False


class TestCacheClearOperations:
    """Tests for cache clearing operations."""

    def test_cache_clear_all(self, tmp_path):
        """Test that cache can clear all entries."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=1209600)
        cache.set("openai", ["gpt-4"])
        cache.set("google", ["gemini-2.5-flash"])
        cache.set("deepl", ["deepl-translate"])

        # Act
        cache.clear()

        # Assert
        assert cache.get("openai") is None
        assert cache.get("google") is None
        assert cache.get("deepl") is None

    def test_cache_clear_single_provider(self, tmp_path):
        """Test that cache can clear a single provider."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=1209600)
        cache.set("openai", ["gpt-4"])
        cache.set("google", ["gemini-2.5-flash"])

        # Act
        cache.clear("openai")

        # Assert
        assert cache.get("openai") is None
        result = cache.get("google")
        assert result is not None
        models, _ = result
        assert models == ["gemini-2.5-flash"]


class TestCacheCleanupOldFiles:
    """Tests for old file cleanup functionality."""

    def test_cleanup_old_files(self, tmp_path, mocker):
        """Test that old cache files are removed when they exceed TTL."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=60)
        cache_file = tmp_path / "models_cache.json"
        
        # Create a cache file
        cache_file.write_text('{"openai": {"models": ["gpt-4"], "timestamp": 1234567890.0}}', encoding='utf-8')
        
        # Mock stat() for the specific cache file to make it appear old
        mock_stat = mocker.Mock()
        mock_stat.st_mtime = time.time() - 120  # 2 minutes ago (older than TTL of 60)
        
        # Patch Path.stat to return old stat for our cache file
        original_stat = Path.stat
        def patched_stat(self, *args, **kwargs):
            if self == cache_file:
                return mock_stat
            return original_stat(self, *args, **kwargs)
        mocker.patch.object(Path, 'stat', patched_stat)
        
        # Mock unlink to verify it's called
        mock_unlink = mocker.patch.object(type(cache_file), 'unlink')

        # Act
        cache.cleanup_old_files()

        # Assert
        # unlink() should have been called on the cache file
        mock_unlink.assert_called_once()


class TestCacheIsCached:
    """Tests for is_cached method."""

    def test_is_cached_true(self, tmp_path):
        """Test that is_cached returns True for cached provider."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=1209600)
        cache.set("openai", ["gpt-4"])

        # Act & Assert
        assert cache.is_cached("openai") is True

    def test_is_cached_false(self, tmp_path):
        """Test that is_cached returns False for non-cached provider."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=1209600)

        # Act & Assert
        assert cache.is_cached("openai") is False


class TestCacheModelsAndPersist:
    """Tests for cache_models_and_persist method."""

    def test_cache_models_and_persist(self, tmp_path):
        """Test that cache_models_and_persist saves to both memory and disk."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=1209600)
        models = ["gpt-4", "gpt-3.5"]

        # Act
        cache.cache_models_and_persist("openai", models)

        # Assert - check in-memory cache
        result = cache.get("openai")
        assert result is not None
        retrieved_models, _ = result
        assert retrieved_models == models

        # Assert - check disk persistence
        cache_file = tmp_path / "models_cache.json"
        assert cache_file.exists()
        with cache_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        assert "openai" in data
        assert data["openai"]["models"] == models


class TestCacheInitializeSafely:
    """Tests for initialize_safely method."""

    def test_initialize_safely_loads_cache(self, tmp_path):
        """Test that initialize_safely loads cache from disk."""
        # Arrange
        cache1 = ModelCache(tmp_path, ttl_seconds=1209600)
        cache1.set("openai", ["gpt-4"])
        cache1.save_to_disk()

        # Act
        cache2 = ModelCache(tmp_path, ttl_seconds=1209600)
        cache2.initialize_safely()

        # Assert
        result = cache2.get("openai")
        assert result is not None
        models, _ = result
        assert models == ["gpt-4"]

    def test_initialize_safely_handles_missing_cache(self, tmp_path):
        """Test that initialize_safely handles missing cache file gracefully."""
        # Arrange & Act - no cache file exists
        cache = ModelCache(tmp_path, ttl_seconds=1209600)
        cache.initialize_safely()

        # Assert - should not raise an error
        assert cache.get("openai") is None
