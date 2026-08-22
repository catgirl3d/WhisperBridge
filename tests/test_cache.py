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
import os
import threading
import time

import pytest
from freezegun import freeze_time

from whisperbridge.core.api_manager.cache import ModelCache


class TestCacheSetAndGet:
    """Tests for basic cache set and get operations."""

    def test_cache_set_and_get(self, tmp_path):
        """Test that cache can store and retrieve models correctly."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=1209600)
        models = ["gpt-5.4-mini", "gpt-5.6-luna"]

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
        models = ["gpt-5.4-mini", "gpt-5.6-luna"]

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
        models = ["gpt-5.4-mini", "gpt-5.6-luna"]
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

    def test_concurrent_persistence_writes_keep_a_complete_snapshot(self, tmp_path):
        """Concurrent persistence writes must not overwrite newer cache entries."""
        cache = ModelCache(tmp_path, ttl_seconds=1209600)
        num_threads = 10

        threads = [
            threading.Thread(
                target=cache.cache_models_and_persist,
                args=(f"provider_{i}", [f"model_{i}"]),
            )
            for i in range(num_threads)
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        with (tmp_path / "models_cache.json").open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert set(data) == {f"provider_{i}" for i in range(num_threads)}


class TestValidateModelList:
    """Tests for model list validation."""

    def test_validate_model_list_valid(self):
        """Test that valid model lists pass validation."""
        # Arrange & Act & Assert
        assert ModelCache.validate_model_list(["gpt-5.4-mini", "gpt-5.6-luna"]) is True
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
        cache.set("openai", ["gpt-5.4-mini"])
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
        cache.set("openai", ["gpt-5.4-mini"])
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
    """Tests for expired cache entry cleanup."""

    def test_cleanup_old_files_removes_expired_entries(self, tmp_path):
        """Expired entries are removed based on their stored timestamp."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=60)
        cache_file = tmp_path / "models_cache.json"
        cache_file.write_text('{"openai": {"models": ["gpt-5.4-mini"], "timestamp": 1234567890.0}}', encoding='utf-8')
        cache.load_from_disk()

        # Act
        cache.cleanup_old_files()

        # Assert
        assert not cache_file.exists()

    def test_cleanup_old_files_handles_unlink_error(self, tmp_path, mocker):
        """Test that cleanup tolerates an inaccessible expired cache file."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=60)
        cache_file = tmp_path / "models_cache.json"
        cache_file.write_text(
            '{"openai": {"models": ["gpt-5.4-mini"], "timestamp": 1234567890.0}}',
            encoding="utf-8",
        )
        cache.load_from_disk()
        mock_unlink = mocker.patch.object(
            type(cache_file), "unlink", side_effect=PermissionError("file is in use")
        )

        # Act
        cache.cleanup_old_files()

        # Assert
        mock_unlink.assert_called_once()
        assert cache_file.exists()

    def test_cleanup_ignores_file_mtime_for_fresh_entries(self, tmp_path):
        """A fresh entry remains valid even when the file itself is old."""
        cache1 = ModelCache(tmp_path, ttl_seconds=60)
        cache1.cache_models_and_persist("openai", ["gpt-5.4-mini"])
        cache_file = tmp_path / "models_cache.json"
        old_timestamp = time.time() - 120
        os.utime(cache_file, (old_timestamp, old_timestamp))

        cache2 = ModelCache(tmp_path, ttl_seconds=60)
        cache2.initialize_safely()

        assert cache2.get("openai") is not None


class TestCacheIsCached:
    """Tests for is_cached method."""

    def test_is_cached_true(self, tmp_path):
        """Test that is_cached returns True for cached provider."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=1209600)
        cache.set("openai", ["gpt-5.4-mini"])

        # Act & Assert
        assert cache.is_cached("openai") is True

    def test_is_cached_false(self, tmp_path):
        """Test that is_cached returns False for non-cached provider."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=1209600)

        # Act & Assert
        assert cache.is_cached("openai") is False

    def test_is_cached_false_after_ttl_expires(self, tmp_path):
        """Test that is_cached returns False for an expired provider entry."""
        cache = ModelCache(tmp_path, ttl_seconds=1)

        with freeze_time("2024-01-01 00:00:00") as frozen_time:
            cache.set("openai", ["gpt-5.4-mini"])
            frozen_time.tick(2)

            assert cache.is_cached("openai") is False


class TestCacheModelsAndPersist:
    """Tests for cache_models_and_persist method."""

    def test_cache_models_and_persist(self, tmp_path):
        """Test that cache_models_and_persist saves to both memory and disk."""
        # Arrange
        cache = ModelCache(tmp_path, ttl_seconds=1209600)
        models = ["gpt-5.4-mini", "gpt-5.6-luna"]

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
        cache1.set("openai", ["gpt-5.4-mini"])
        cache1.save_to_disk()

        # Act
        cache2 = ModelCache(tmp_path, ttl_seconds=1209600)
        cache2.initialize_safely()

        # Assert
        result = cache2.get("openai")
        assert result is not None
        models, _ = result
        assert models == ["gpt-5.4-mini"]

    def test_initialize_safely_handles_missing_cache(self, tmp_path):
        """Test that initialize_safely handles missing cache file gracefully."""
        # Arrange & Act - no cache file exists
        cache = ModelCache(tmp_path, ttl_seconds=1209600)
        cache.initialize_safely()

        # Assert - should not raise an error
        assert cache.get("openai") is None
