"""
Tests for scripts/result.py

Tests the Result and BatchResult classes for error handling.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from result import Result, BatchResult


class TestResult:
    """Tests for Result class."""

    def test_ok_basic(self):
        """Create a successful result."""
        r = Result.ok(42)
        assert r.success is True
        assert r.value == 42
        assert r.error is None

    def test_ok_with_details(self):
        """Successful result with details."""
        r = Result.ok(42, processed=42, path='/foo')
        assert r.details['processed'] == 42
        assert r.details['path'] == '/foo'

    def test_fail_basic(self):
        """Create a failed result."""
        r = Result.fail("Something went wrong")
        assert r.success is False
        assert r.error == "Something went wrong"
        assert r.value is None

    def test_fail_with_details(self):
        """Failed result with details."""
        r = Result.fail("Error", stage='merge', code=500)
        assert r.details['stage'] == 'merge'
        assert r.details['code'] == 500

    def test_bool_success(self):
        """Result is truthy when successful."""
        assert bool(Result.ok(1)) is True
        assert bool(Result.fail("e")) is False

    def test_unwrap_success(self):
        """Unwrap returns value on success."""
        assert Result.ok(42).unwrap() == 42

    def test_unwrap_failure(self):
        """Unwrap raises on failure."""
        with pytest.raises(ValueError, match="Result failed"):
            Result.fail("error").unwrap()

    def test_unwrap_or(self):
        """Unwrap_or returns default on failure."""
        assert Result.ok(42).unwrap_or(0) == 42
        assert Result.fail("e").unwrap_or(0) == 0

    def test_map_success(self):
        """Map transforms successful result."""
        r = Result.ok(5).map(lambda x: x * 2)
        assert r.success is True
        assert r.value == 10

    def test_map_failure(self):
        """Map preserves failure."""
        r = Result.fail("error").map(lambda x: x * 2)
        assert r.success is False
        assert r.error == "error"

    def test_and_then_success(self):
        """Chain operations with and_then."""
        def double(x):
            return Result.ok(x * 2)

        r = Result.ok(5).and_then(double)
        assert r.value == 10

    def test_and_then_failure(self):
        """and_then preserves first failure."""
        def always_fail(x):
            return Result.fail("fail")

        r = Result.fail("first").and_then(always_fail)
        assert r.error == "first"

    def test_to_dict(self):
        """Convert result to dictionary."""
        r = Result.ok(42, processed=42)
        d = r.to_dict()
        assert d['success'] is True
        assert d['value'] == 42
        assert d['details']['processed'] == 42

    def test_repr(self):
        """String representation."""
        assert repr(Result.ok(42)) == "Result.ok(42)"
        assert repr(Result.fail("e")) == "Result.fail('e')"


class TestBatchResult:
    """Tests for BatchResult class."""

    def test_empty_batch(self):
        """Empty batch has no results."""
        batch = BatchResult()
        assert len(batch) == 0
        assert batch.success is True  # Vacuously true

    def test_add_results(self):
        """Add results to batch."""
        batch = BatchResult()
        batch.add(Result.ok(1))
        batch.add(Result.ok(2))
        assert len(batch) == 2

    def test_success_all(self):
        """Batch success when all succeed."""
        batch = BatchResult()
        batch.add(Result.ok(1))
        batch.add(Result.ok(2))
        assert batch.success is True

    def test_success_partial(self):
        """Batch fails when any fails."""
        batch = BatchResult()
        batch.add(Result.ok(1))
        batch.add(Result.fail("error"))
        assert batch.success is False
        assert batch.partial_success is True

    def test_succeeded_failed_lists(self):
        """Get succeeded and failed results."""
        batch = BatchResult()
        batch.add(Result.ok(1))
        batch.add(Result.fail("e"))
        batch.add(Result.ok(2))

        assert len(batch.succeeded) == 2
        assert len(batch.failed) == 1

    def test_compute_summary(self):
        """Compute summary statistics."""
        batch = BatchResult()
        batch.add(Result.ok(1))
        batch.add(Result.ok(2))
        batch.add(Result.fail("e"))

        summary = batch.compute_summary()
        assert summary['total'] == 3
        assert summary['succeeded'] == 2
        assert summary['failed'] == 1
        assert abs(summary['success_rate'] - 0.666) < 0.01

    def test_iter(self):
        """Iterate over results."""
        batch = BatchResult()
        batch.add(Result.ok(1))
        batch.add(Result.ok(2))

        values = [r.value for r in batch]
        assert values == [1, 2]
