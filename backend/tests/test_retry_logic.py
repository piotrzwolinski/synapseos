"""Tests for _execute_with_retry connection resilience.

Validates that the retry wrapper:
1. Catches the correct exception types (neo4j → redis after migration)
2. Calls reconnect() on transient failures
3. Raises on persistent failures after max retries
4. Passes through non-connection errors immediately
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# =============================================================================
# Test the retry logic in isolation (no real DB)
# =============================================================================

class TestExecuteWithRetry:
    """Test _execute_with_retry behavior with simulated failures."""

    def _make_db_with_retry(self):
        """Create a minimal object with _execute_with_retry logic.

        This extracts the retry logic so it can be tested independently
        of the actual Neo4j/FalkorDB connection.
        """
        class RetryMixin:
            def __init__(self):
                self.reconnect_calls = 0

            def reconnect(self):
                self.reconnect_calls += 1

            def _execute_with_retry(self, query_func, max_retries=2):
                last_error = None
                for attempt in range(max_retries + 1):
                    try:
                        return query_func()
                    except (ConnectionError, TimeoutError) as e:
                        # These simulate redis.exceptions in FalkorDB
                        last_error = e
                        if attempt < max_retries:
                            self.reconnect()
                        else:
                            raise
                    except Exception as e:
                        error_msg = str(e).lower()
                        if "connection" in error_msg or "timeout" in error_msg or "defunct" in error_msg:
                            last_error = e
                            if attempt < max_retries:
                                self.reconnect()
                            else:
                                raise
                        else:
                            raise
                raise last_error

        return RetryMixin()

    def test_success_on_first_try(self):
        db = self._make_db_with_retry()
        result = db._execute_with_retry(lambda: 42)
        assert result == 42
        assert db.reconnect_calls == 0

    def test_retry_on_connection_error(self):
        """Simulates redis.exceptions.ConnectionError."""
        db = self._make_db_with_retry()
        attempts = [0]

        def flaky():
            attempts[0] += 1
            if attempts[0] == 1:
                raise ConnectionError("Connection refused")
            return "success"

        result = db._execute_with_retry(flaky)
        assert result == "success"
        assert db.reconnect_calls == 1

    def test_retry_on_timeout_error(self):
        """Simulates redis.exceptions.TimeoutError."""
        db = self._make_db_with_retry()
        attempts = [0]

        def flaky():
            attempts[0] += 1
            if attempts[0] == 1:
                raise TimeoutError("Operation timed out")
            return "success"

        result = db._execute_with_retry(flaky)
        assert result == "success"
        assert db.reconnect_calls == 1

    def test_raises_after_max_retries(self):
        db = self._make_db_with_retry()

        def always_fails():
            raise ConnectionError("Permanent failure")

        with pytest.raises(ConnectionError, match="Permanent failure"):
            db._execute_with_retry(always_fails, max_retries=2)
        assert db.reconnect_calls == 2

    def test_non_connection_error_raises_immediately(self):
        """ValueError, KeyError, etc. should NOT trigger retry."""
        db = self._make_db_with_retry()

        def bad_logic():
            raise ValueError("Bad parameter")

        with pytest.raises(ValueError, match="Bad parameter"):
            db._execute_with_retry(bad_logic)
        assert db.reconnect_calls == 0

    def test_connection_string_match_in_generic_exception(self):
        """Generic Exception with 'connection' in message should trigger retry."""
        db = self._make_db_with_retry()
        attempts = [0]

        def flaky():
            attempts[0] += 1
            if attempts[0] == 1:
                raise Exception("connection pool exhausted")
            return "recovered"

        result = db._execute_with_retry(flaky)
        assert result == "recovered"
        assert db.reconnect_calls == 1

    def test_defunct_string_match(self):
        """Neo4j-style 'defunct' connection error should trigger retry."""
        db = self._make_db_with_retry()
        attempts = [0]

        def flaky():
            attempts[0] += 1
            if attempts[0] == 1:
                raise Exception("Server at bolt://... is no longer available (defunct)")
            return "recovered"

        result = db._execute_with_retry(flaky)
        assert result == "recovered"

    def test_retry_returns_result_from_successful_attempt(self):
        """After retry, the return value from the successful call is propagated."""
        db = self._make_db_with_retry()
        attempts = [0]

        def flaky():
            attempts[0] += 1
            if attempts[0] <= 2:
                raise ConnectionError("Try again")
            return {"data": [1, 2, 3]}

        result = db._execute_with_retry(flaky, max_retries=3)
        assert result == {"data": [1, 2, 3]}
        assert db.reconnect_calls == 2

    def test_zero_retries_raises_on_first_failure(self):
        db = self._make_db_with_retry()

        def fails():
            raise ConnectionError("No retries")

        with pytest.raises(ConnectionError):
            db._execute_with_retry(fails, max_retries=0)
        assert db.reconnect_calls == 0


# =============================================================================
# Test that current database.py retry catches redis/connection exceptions
# =============================================================================

class TestCurrentRetryIntegration:
    """Verify _execute_with_retry in database.py catches Redis connection exceptions.

    After FalkorDB migration, the retry logic catches ConnectionError and
    TimeoutError (from redis.exceptions) instead of neo4j exceptions.
    """

    def test_current_retry_catches_redis_connection_error(self):
        """Retry logic catches redis.exceptions.ConnectionError."""
        from redis.exceptions import ConnectionError as RedisConnectionError
        from database import GraphConnection
        db = GraphConnection()
        db.graph = MagicMock()  # Prevent real connection

        attempts = [0]

        def flaky():
            attempts[0] += 1
            if attempts[0] == 1:
                raise RedisConnectionError("Connection refused")
            return "ok"

        db.reconnect = MagicMock()
        result = db._execute_with_retry(flaky)
        assert result == "ok"
        db.reconnect.assert_called_once()

    def test_current_retry_catches_redis_timeout_error(self):
        """Retry logic catches redis.exceptions.TimeoutError."""
        from redis.exceptions import TimeoutError as RedisTimeoutError
        from database import GraphConnection
        db = GraphConnection()
        db.graph = MagicMock()

        attempts = [0]

        def flaky():
            attempts[0] += 1
            if attempts[0] == 1:
                raise RedisTimeoutError("Operation timed out")
            return "ok"

        db.reconnect = MagicMock()
        result = db._execute_with_retry(flaky)
        assert result == "ok"
