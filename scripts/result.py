"""
Standardized Result type for pipeline operations.

Provides a consistent way to return success/failure from pipeline functions
with optional value, error message, and additional details.

Usage:
    from result import Result

    def process_data(path: Path) -> Result[int]:
        try:
            count = do_processing(path)
            return Result.ok(count, processed=count, path=str(path))
        except FileNotFoundError as e:
            return Result.fail(f"File not found: {path}", stage='process')
        except Exception as e:
            return Result.fail(str(e), stage='process', exception=type(e).__name__)

    # Using results
    result = process_data(some_path)
    if result.success:
        print(f"Processed {result.value} items")
    else:
        print(f"Error: {result.error}")
        print(f"Details: {result.details}")
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Generic, List, Optional, TypeVar

T = TypeVar('T')


@dataclass
class Result(Generic[T]):
    """Standard result type for pipeline operations.

    Attributes:
        success: Whether the operation succeeded
        value: The result value (if success=True)
        error: Error message (if success=False)
        details: Additional context (timing, counts, warnings, etc.)
    """
    success: bool
    value: Optional[T] = None
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, value: T = None, **details) -> 'Result[T]':
        """Create a successful result.

        Args:
            value: The result value
            **details: Additional context to include

        Returns:
            Result with success=True

        Example:
            >>> Result.ok(42, processed=42, duration=1.5)
            Result(success=True, value=42, details={'processed': 42, 'duration': 1.5})
        """
        return cls(success=True, value=value, details=details)

    @classmethod
    def fail(cls, error: str, **details) -> 'Result[T]':
        """Create a failed result.

        Args:
            error: Error message
            **details: Additional context (stage, exception type, etc.)

        Returns:
            Result with success=False

        Example:
            >>> Result.fail("File not found", stage='ingest', path='/foo/bar')
            Result(success=False, error='File not found', details={'stage': 'ingest', ...})
        """
        return cls(success=False, error=error, details=details)

    def map(self, func) -> 'Result':
        """Transform the value if successful.

        Args:
            func: Function to apply to value

        Returns:
            New Result with transformed value, or same error

        Example:
            >>> Result.ok(5).map(lambda x: x * 2)
            Result(success=True, value=10)
        """
        if self.success:
            try:
                new_value = func(self.value)
                return Result.ok(new_value, **self.details)
            except Exception as e:
                return Result.fail(str(e), original_value=self.value, **self.details)
        return self

    def and_then(self, func) -> 'Result':
        """Chain operations that return Results.

        Args:
            func: Function that takes value and returns Result

        Returns:
            Result from func, or same error

        Example:
            >>> Result.ok(5).and_then(lambda x: Result.ok(x * 2))
            Result(success=True, value=10)
        """
        if self.success:
            return func(self.value)
        return self

    def unwrap(self) -> T:
        """Get the value or raise an exception.

        Returns:
            The value if successful

        Raises:
            ValueError: If the result is a failure

        Example:
            >>> Result.ok(42).unwrap()
            42
            >>> Result.fail("error").unwrap()
            ValueError: Result failed: error
        """
        if self.success:
            return self.value
        raise ValueError(f"Result failed: {self.error}")

    def unwrap_or(self, default: T) -> T:
        """Get the value or a default.

        Args:
            default: Value to return if failed

        Returns:
            The value if successful, otherwise default

        Example:
            >>> Result.ok(42).unwrap_or(0)
            42
            >>> Result.fail("error").unwrap_or(0)
            0
        """
        if self.success:
            return self.value
        return default

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dict representation of the result
        """
        d = {
            'success': self.success,
        }
        if self.success:
            d['value'] = self.value
        else:
            d['error'] = self.error
        if self.details:
            d['details'] = self.details
        return d

    def __bool__(self) -> bool:
        """Allow using Result in boolean context."""
        return self.success

    def __repr__(self) -> str:
        if self.success:
            return f"Result.ok({self.value!r})"
        return f"Result.fail({self.error!r})"


@dataclass
class BatchResult:
    """Result for batch operations with multiple items.

    Useful for operations that process multiple files/features
    where some may succeed and others fail.

    Attributes:
        results: List of individual Results
        summary: Aggregate statistics
    """
    results: List[Result] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def add(self, result: Result) -> None:
        """Add a result to the batch."""
        self.results.append(result)

    @property
    def success(self) -> bool:
        """True if all results succeeded."""
        return all(r.success for r in self.results)

    @property
    def partial_success(self) -> bool:
        """True if at least one result succeeded."""
        return any(r.success for r in self.results)

    @property
    def succeeded(self) -> List[Result]:
        """Get all successful results."""
        return [r for r in self.results if r.success]

    @property
    def failed(self) -> List[Result]:
        """Get all failed results."""
        return [r for r in self.results if not r.success]

    def compute_summary(self) -> Dict[str, Any]:
        """Compute and store summary statistics."""
        self.summary = {
            'total': len(self.results),
            'succeeded': len(self.succeeded),
            'failed': len(self.failed),
            'success_rate': len(self.succeeded) / len(self.results) if self.results else 0,
        }
        return self.summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        if not self.summary:
            self.compute_summary()
        return {
            'success': self.success,
            'partial_success': self.partial_success,
            'summary': self.summary,
            'results': [r.to_dict() for r in self.results],
        }

    def __len__(self) -> int:
        return len(self.results)

    def __iter__(self):
        return iter(self.results)
