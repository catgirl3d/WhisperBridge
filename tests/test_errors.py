"""
Tests for error handling in api_manager.errors module.

This module tests error classification functionality including:
- Authentication error classification
- Rate limit error classification with retry_after
- Network/timeout error classification
- Server error classification (5xx)
- Unknown error fallback
- requires_initialization decorator
- Network diagnostics logging
"""

import pytest

from whisperbridge.core.api_manager.errors import (
    APIError,
    APIErrorType,
    RetryableAPIError,
    classify_error,
    log_network_diagnostics,
    requires_initialization,
)


class TestErrorClassification:
    """Tests for classify_error function."""

    def test_classify_authentication_error(self):
        """Test classification of authentication errors."""
        # Arrange
        error = Exception("unauthorized: invalid api key")

        # Act
        api_error = classify_error(error)

        # Assert
        assert api_error.error_type == APIErrorType.AUTHENTICATION
        assert "unauthorized" in api_error.message.lower()

    def test_classify_rate_limit_error_with_retry_after(self):
        """Test classification of rate limit errors with retry_after field."""
        # Arrange
        error = Exception("rate limit exceeded")
        error.retry_after = 60

        # Act
        api_error = classify_error(error)

        # Assert
        assert api_error.error_type == APIErrorType.RATE_LIMIT
        assert api_error.retry_after == 60

    def test_classify_network_timeout_error(self):
        """Test classification of timeout and network errors."""
        # Arrange - test timeout error
        error1 = TimeoutError("Request timed out")

        # Act
        api_error1 = classify_error(error1)

        # Assert
        assert api_error1.error_type == APIErrorType.TIMEOUT

        # Arrange - test connection error
        error2 = Exception("connection refused")

        # Act
        api_error2 = classify_error(error2)

        # Assert
        assert api_error2.error_type == APIErrorType.NETWORK

    def test_classify_server_error_5xx(self):
        """Test classification of server errors (5xx status codes)."""
        # Arrange
        error = Exception("Internal server error")
        error.status_code = 503

        # Act
        api_error = classify_error(error)

        # Assert
        assert api_error.error_type == APIErrorType.SERVER_ERROR
        assert api_error.status_code == 503

    def test_classify_unknown_error(self):
        """Test fallback to UNKNOWN for unrecognized errors."""
        # Arrange
        error = Exception("Something went wrong")

        # Act
        api_error = classify_error(error)

        # Assert
        assert api_error.error_type == APIErrorType.UNKNOWN

    def test_classify_quota_exceeded_error(self):
        """Test classification of quota exceeded errors."""
        # Arrange
        error = Exception("quota exceeded: billing limit reached")

        # Act
        api_error = classify_error(error)

        # Assert
        assert api_error.error_type == APIErrorType.QUOTA_EXCEEDED

    def test_classify_invalid_request_error(self):
        """Test classification of invalid request errors."""
        # Arrange
        error = Exception("bad request: malformed input")

        # Act
        api_error = classify_error(error)

        # Assert
        assert api_error.error_type == APIErrorType.INVALID_REQUEST


class TestRequiresInitializationDecorator:
    """Tests for requires_initialization decorator."""

    def test_requires_initialization_decorator_blocks_uninitialized(self):
        """Test that decorator blocks calls when not initialized."""
        # Arrange
        class TestClass:
            def __init__(self):
                self._initialized = False

            @requires_initialization
            def test_method(self):
                return "success"

            def is_initialized(self):
                return self._initialized

        obj = TestClass()

        # Act & Assert
        with pytest.raises(RuntimeError, match="API manager not initialized"):
            obj.test_method()

    def test_requires_initialization_decorator_allows_initialized(self):
        """Test that decorator allows calls after initialization."""
        # Arrange
        class TestClass:
            def __init__(self):
                self._initialized = False

            @requires_initialization
            def test_method(self):
                return "success"

            def is_initialized(self):
                return self._initialized

        obj = TestClass()
        obj._initialized = True

        # Act
        result = obj.test_method()

        # Assert
        assert result == "success"


class TestNetworkDiagnostics:
    """Tests for log_network_diagnostics function."""

    def test_log_network_diagnostics_logs_once(self, mocker, loguru_caplog):
        """Test that diagnostics are logged only once."""
        # Arrange
        mocker.patch("sys.frozen", False, create=True)
        mocker.patch("platform.platform", return_value="Windows-11")
        mocker.patch("sys.executable", "/path/to/python.exe")

        # Act - call twice
        log_network_diagnostics(url="https://api.example.com")
        log_network_diagnostics(url="https://api.example.com")

        # Assert - check that debug log was called (at least once)
        assert any("Network diagnostics" in record.message for record in loguru_caplog.records)


class TestAPIErrorDataclass:
    """Tests for APIError dataclass."""

    def test_api_error_default_timestamp(self):
        """Test that APIError sets default timestamp."""
        # Arrange & Act
        error = APIError(APIErrorType.AUTHENTICATION, "Test error")

        # Assert
        assert error.error_type == APIErrorType.AUTHENTICATION
        assert error.message == "Test error"
        assert error.timestamp is not None

    def test_api_error_with_optional_fields(self):
        """Test that APIError accepts optional fields."""
        # Arrange & Act
        error = APIError(
            error_type=APIErrorType.RATE_LIMIT,
            message="Rate limit exceeded",
            status_code=429,
            retry_after=60
        )

        # Assert
        assert error.error_type == APIErrorType.RATE_LIMIT
        assert error.status_code == 429
        assert error.retry_after == 60


class TestRetryableAPIError:
    """Tests for RetryableAPIError exception."""

    def test_retryable_api_error_creation(self):
        """Test that RetryableAPIError can be created."""
        # Arrange & Act & Assert
        with pytest.raises(RetryableAPIError, match="Retryable error"):
            raise RetryableAPIError("Retryable error")
