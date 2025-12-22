#!/usr/bin/env python3
"""
Shared date parsing utilities for normalizing dates from various sources.

This module provides unified date parsing functions used across all
normalization scripts (OSM, SEFRAK, Kulturminner, etc.).

Handles various formats:
- Integer years: 1950
- String years: "1950", "c1950", "~1950", "ca 1950"
- Decade ranges: "1950s", "1950-1960"
- ISO dates: "1950-01-01"
- Century descriptions: "19th century", "1800-tallet"
- Historical periods: "middelalder", "vikingtid"
- Descriptive ranges: "early 1900s", "late 1800s"
"""

import re
from typing import Optional, Union, Tuple


def parse_year(value: Union[str, int, float, None]) -> Optional[int]:
    """
    Parse various date formats to a year integer.

    This is the main parsing function that handles all common formats
    found in Norwegian heritage data, OSM, and historical sources.

    Args:
        value: Date value in various formats (str, int, float, or None)

    Returns:
        Integer year if parseable, None otherwise

    Examples:
        >>> parse_year(1950)
        1950
        >>> parse_year("1950")
        1950
        >>> parse_year("~1950")
        1950
        >>> parse_year("ca 1950")
        1950
        >>> parse_year("1950-01-01")
        1950
        >>> parse_year("1950s")
        1950
        >>> parse_year("1950-1960")
        1950
        >>> parse_year("19th century")
        1800
        >>> parse_year("1800-tallet")
        1850
        >>> parse_year("middelalder")
        1300
        >>> parse_year("early 1900s")
        1900
    """
    if value is None:
        return None

    # Handle numeric types
    if isinstance(value, int):
        return value if is_valid_year(value) else None

    if isinstance(value, float):
        year = int(value)
        return year if is_valid_year(year) else None

    if not isinstance(value, str):
        return None

    # Clean and normalize string
    value = value.strip().lower()

    if not value:
        return None

    # Pattern 1: Pure year "1880"
    if re.match(r'^\d{4}$', value):
        year = int(value)
        return year if is_valid_year(year) else None

    # Pattern 2: Year with prefix "~1880", "ca 1880", "c1880", "circa 1880"
    match = re.match(r'^[~c]a?\s*(\d{4})$', value)
    if match:
        year = int(match.group(1))
        return year if is_valid_year(year) else None

    # Pattern 3: ISO date "1880-01-01", "1880-12"
    match = re.match(r'^(\d{4})-\d{1,2}', value)
    if match:
        year = int(match.group(1))
        return year if is_valid_year(year) else None

    # Pattern 4: Date range "1880-1890" -> use start year
    match = re.match(r'^(\d{4})\s*[-–]\s*(\d{4})$', value)
    if match:
        year = int(match.group(1))
        return year if is_valid_year(year) else None

    # Pattern 5: Decade "1880s" -> 1880
    match = re.match(r'^(\d{3})0s$', value)
    if match:
        year = int(match.group(1)) * 10
        return year if is_valid_year(year) else None

    # Pattern 6: Descriptive ranges "early 1900s", "late 1800s", "mid 1800s"
    match = re.match(r'^(early|late|mid)\s+(\d{3})0s$', value)
    if match:
        qualifier = match.group(1)
        decade_start = int(match.group(2)) * 10

        if qualifier == 'early':
            year = decade_start
        elif qualifier == 'mid':
            year = decade_start + 5
        else:  # late
            year = decade_start + 7

        return year if is_valid_year(year) else None

    # Pattern 7: English century "19th century", "18th century"
    match = re.match(r'^(\d{1,2})(?:st|nd|rd|th)\s+century', value)
    if match:
        century = int(match.group(1))
        year = (century - 1) * 100
        return year if is_valid_year(year) else None

    # Pattern 8: Norwegian century "1800-tallet" (midpoint of century)
    match = re.match(r'^(\d{2})00-tallet$', value)
    if match:
        century_start = int(match.group(1)) * 100
        year = century_start + 50  # Use midpoint
        return year if is_valid_year(year) else None

    # Pattern 9: Historical periods (Norwegian)
    period_map = {
        'middelalder': 1300,      # Medieval period
        'vikingtid': 900,         # Viking age
        'jernald': 500,           # Iron age
        'bronsealder': -1000,     # Bronze age (BCE)
        'steinalder': -3000,      # Stone age (BCE)
    }

    for period, year in period_map.items():
        if period in value:
            return year if is_valid_year(year, min_year=-5000) else None

    # Pattern 10: Try to extract any 4-digit year from the string
    match = re.search(r'\b(1[0-9]{3}|20[0-3][0-9])\b', value)
    if match:
        year = int(match.group(1))
        return year if is_valid_year(year) else None

    return None


def parse_date_range(value: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Parse a date range string into (start_year, end_year).

    Args:
        value: Date range string

    Returns:
        Tuple of (start_year, end_year). Either can be None if not parseable.

    Examples:
        >>> parse_date_range("1950-1960")
        (1950, 1960)
        >>> parse_date_range("1950s")
        (1950, 1959)
        >>> parse_date_range("early 1900s")
        (1900, 1920)
        >>> parse_date_range("19th century")
        (1800, 1899)
        >>> parse_date_range("1800-tallet")
        (1800, 1899)
    """
    if not value or not isinstance(value, str):
        return (None, None)

    value = value.strip().lower()

    # Explicit range "1950-1960"
    match = re.match(r'^(\d{4})\s*[-–]\s*(\d{4})$', value)
    if match:
        start = int(match.group(1))
        end = int(match.group(2))
        return (
            start if is_valid_year(start) else None,
            end if is_valid_year(end) else None
        )

    # Decade "1950s"
    match = re.match(r'^(\d{3})0s$', value)
    if match:
        start = int(match.group(1)) * 10
        end = start + 9
        return (
            start if is_valid_year(start) else None,
            end if is_valid_year(end) else None
        )

    # Descriptive ranges "early 1900s", "late 1800s", "mid 1800s"
    match = re.match(r'^(early|late|mid)\s+(\d{3})0s$', value)
    if match:
        qualifier = match.group(1)
        decade_start = int(match.group(2)) * 10

        if qualifier == 'early':
            start, end = decade_start, decade_start + 20
        elif qualifier == 'mid':
            start, end = decade_start + 3, decade_start + 7
        else:  # late
            start, end = decade_start + 7, decade_start + 9

        return (
            start if is_valid_year(start) else None,
            end if is_valid_year(end) else None
        )

    # English century "19th century"
    match = re.match(r'^(\d{1,2})(?:st|nd|rd|th)\s+century', value)
    if match:
        century = int(match.group(1))
        start = (century - 1) * 100
        end = start + 99
        return (
            start if is_valid_year(start) else None,
            end if is_valid_year(end) else None
        )

    # Norwegian century "1800-tallet"
    match = re.match(r'^(\d{2})00-tallet$', value)
    if match:
        start = int(match.group(1)) * 100
        end = start + 99
        return (
            start if is_valid_year(start) else None,
            end if is_valid_year(end) else None
        )

    # Try single year parse - return as both start and end
    year = parse_year(value)
    if year is not None:
        return (year, year)

    return (None, None)


def estimate_year_from_range(start: Optional[int], end: Optional[int]) -> Optional[int]:
    """
    Estimate a single year from a date range.

    Uses the midpoint if both are provided, otherwise returns whichever exists.
    This is useful for SEFRAK data which often provides construction period ranges.

    Args:
        start: Start year of range (or None)
        end: End year of range (or None)

    Returns:
        Estimated single year, or None if both are None

    Examples:
        >>> estimate_year_from_range(1840, 1850)
        1845
        >>> estimate_year_from_range(1840, None)
        1840
        >>> estimate_year_from_range(None, 1850)
        1850
        >>> estimate_year_from_range(None, None) is None
        True
    """
    if start is not None and end is not None:
        # Both provided - use midpoint
        return (start + end) // 2
    elif start is not None:
        # Only start provided
        return start
    elif end is not None:
        # Only end provided
        return end
    else:
        # Neither provided
        return None


def is_valid_year(year: int, min_year: int = 1700, max_year: int = 2030) -> bool:
    """
    Check if year is within valid range for historical buildings.

    Default range is 1700-2030, covering the historical map period.
    Can be overridden for archaeological/prehistoric data.

    Args:
        year: Year to validate
        min_year: Minimum valid year (default: 1700)
        max_year: Maximum valid year (default: 2030)

    Returns:
        True if year is in valid range, False otherwise

    Examples:
        >>> is_valid_year(1880)
        True
        >>> is_valid_year(1650)
        False
        >>> is_valid_year(1650, min_year=1600)
        True
        >>> is_valid_year(2050)
        False
    """
    return min_year <= year <= max_year


def normalize_year_to_int(value: Union[str, int, float, None]) -> Optional[int]:
    """
    Alias for parse_year() for backwards compatibility.

    Some older scripts may import this function name.

    Args:
        value: Date value to parse

    Returns:
        Integer year or None
    """
    return parse_year(value)


# Example usage and tests
if __name__ == '__main__':
    import doctest

    print("Running date_utils doctests...")
    results = doctest.testmod()

    if results.failed == 0:
        print(f"All {results.attempted} tests passed!")
    else:
        print(f"{results.failed} of {results.attempted} tests failed")

    # Additional manual tests
    print("\nManual test examples:")

    test_cases = [
        "1880",
        "~1880",
        "ca 1850",
        "1880-01-01",
        "1880-1890",
        "1880s",
        "early 1900s",
        "late 1800s",
        "19th century",
        "1800-tallet",
        "middelalder",
        "vikingtid",
        None,
        1950,
        1950.0,
    ]

    for test in test_cases:
        result = parse_year(test)
        print(f"  {test!r:20s} -> {result}")

    print("\nRange parsing examples:")

    range_cases = [
        "1950-1960",
        "1950s",
        "early 1900s",
        "19th century",
        "1800-tallet",
    ]

    for test in range_cases:
        start, end = parse_date_range(test)
        estimated = estimate_year_from_range(start, end)
        print(f"  {test:20s} -> ({start}, {end}) -> {estimated}")
