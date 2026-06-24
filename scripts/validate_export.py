#!/usr/bin/env python3
"""
Export Validation Script

Validates that exported GeoJSON files meet the frontend contract:
- Required fields are present
- Field values are valid (evidence levels, date ranges, etc.)
- Source codes are consistent

Run after export stage to catch issues before deployment.

Usage:
    python scripts/validate_export.py
    python scripts/validate_export.py --verbose
    python scripts/validate_export.py --strict  # Fail on warnings
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any

# Import constants
try:
    from constants import (
        EXPORT_DIR,
        BUILDINGS_EXPORT,
        ROADS_EXPORT,
        WATER_EXPORT,
        REQUIRED_EXPORT_FIELDS,
        VALID_EVIDENCE_LEVELS,
        VALID_WATER_TYPES,
        MIN_VALID_YEAR,
        MAX_VALID_YEAR,
        SOURCE_SHORT_CODES,
    )
except ImportError:
    # Fallback for running directly
    sys.path.insert(0, str(Path(__file__).parent))
    from constants import (
        EXPORT_DIR,
        BUILDINGS_EXPORT,
        ROADS_EXPORT,
        WATER_EXPORT,
        REQUIRED_EXPORT_FIELDS,
        VALID_EVIDENCE_LEVELS,
        VALID_WATER_TYPES,
        MIN_VALID_YEAR,
        MAX_VALID_YEAR,
        SOURCE_SHORT_CODES,
    )


class ValidationResult:
    """Holds validation results for a single file."""

    def __init__(self, filename: str):
        self.filename = filename
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.feature_count = 0
        self.sources_found: Set[str] = set()
        self.date_sources_found: Set[str] = set()

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, msg: str):
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def add_info(self, msg: str):
        self.info.append(msg)


def validate_buildings(path: Path, verbose: bool = False) -> ValidationResult:
    """Validate buildings export file."""
    result = ValidationResult("buildings.geojson")

    if not path.exists():
        result.add_error(f"File not found: {path}")
        return result

    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result.add_error(f"Invalid JSON: {e}")
        return result

    features = data.get('features', [])
    result.feature_count = len(features)

    if result.feature_count == 0:
        result.add_error("No features in file")
        return result

    required_fields = set(REQUIRED_EXPORT_FIELDS['buildings'])
    # Valid source codes include regular sources plus 'inh' for inherited dates
    valid_sources = set(SOURCE_SHORT_CODES.values()) | {'inh'}
    missing_fields_count: Dict[str, int] = {}
    invalid_evidence_count = 0
    invalid_year_count = 0
    sample_size = min(len(features), 1000)  # Check first 1000 features

    for i, feature in enumerate(features[:sample_size]):
        props = feature.get('properties', {})

        # Check required fields
        for field in required_fields:
            if field not in props or props[field] is None:
                missing_fields_count[field] = missing_fields_count.get(field, 0) + 1

        # Track sources
        if 'src' in props:
            result.sources_found.add(props['src'])
        if 'sd_src' in props:
            result.date_sources_found.add(props['sd_src'])

        # Validate evidence level
        ev = props.get('ev')
        if ev and ev not in VALID_EVIDENCE_LEVELS:
            invalid_evidence_count += 1

        # Validate year range
        sd = props.get('sd')
        if sd and (sd < MIN_VALID_YEAR or sd > MAX_VALID_YEAR):
            invalid_year_count += 1

        ed = props.get('ed')
        if ed and (ed < MIN_VALID_YEAR or ed > MAX_VALID_YEAR):
            invalid_year_count += 1

    # Report missing fields
    for field, count in missing_fields_count.items():
        pct = (count / sample_size) * 100
        if pct > 10:
            result.add_error(f"Field '{field}' missing in {count}/{sample_size} features ({pct:.1f}%)")
        elif pct > 0:
            result.add_warning(f"Field '{field}' missing in {count}/{sample_size} features ({pct:.1f}%)")

    # Report invalid values
    if invalid_evidence_count > 0:
        result.add_error(f"Invalid evidence levels in {invalid_evidence_count} features")

    if invalid_year_count > 0:
        result.add_warning(f"Years outside valid range in {invalid_year_count} features")

    # Check source consistency
    unknown_sources = result.sources_found - valid_sources
    if unknown_sources:
        result.add_warning(f"Unknown source codes found: {unknown_sources}")

    unknown_date_sources = result.date_sources_found - valid_sources
    if unknown_date_sources:
        result.add_warning(f"Unknown date source codes found: {unknown_date_sources}")

    # Info
    result.add_info(f"Total features: {result.feature_count}")
    result.add_info(f"Sources: {sorted(result.sources_found)}")
    result.add_info(f"Date sources: {sorted(result.date_sources_found)}")

    return result


def validate_roads(path: Path, verbose: bool = False) -> ValidationResult:
    """Validate roads export file."""
    result = ValidationResult("roads_temporal.geojson")

    if not path.exists():
        result.add_warning(f"File not found: {path}")
        return result

    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result.add_error(f"Invalid JSON: {e}")
        return result

    features = data.get('features', [])
    result.feature_count = len(features)

    if result.feature_count == 0:
        result.add_warning("No road features in file")
        return result

    required_fields = set(REQUIRED_EXPORT_FIELDS['roads'])
    missing_fields_count: Dict[str, int] = {}
    sample_size = min(len(features), 500)

    for feature in features[:sample_size]:
        props = feature.get('properties', {})

        for field in required_fields:
            if field not in props or props[field] is None:
                missing_fields_count[field] = missing_fields_count.get(field, 0) + 1

        if 'src' in props:
            result.sources_found.add(props['src'])

    # Report missing fields
    for field, count in missing_fields_count.items():
        pct = (count / sample_size) * 100
        if pct > 10:
            result.add_error(f"Field '{field}' missing in {count}/{sample_size} features ({pct:.1f}%)")
        elif pct > 0:
            result.add_warning(f"Field '{field}' missing in {count}/{sample_size} features ({pct:.1f}%)")

    result.add_info(f"Total features: {result.feature_count}")
    result.add_info(f"Sources: {sorted(result.sources_found)}")

    return result


def validate_water(path: Path, verbose: bool = False) -> ValidationResult:
    """Validate water export file."""
    result = ValidationResult("water.geojson")

    if not path.exists():
        result.add_warning(f"File not found: {path} (water export may not be implemented)")
        return result

    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result.add_error(f"Invalid JSON: {e}")
        return result

    features = data.get('features', [])
    result.feature_count = len(features)

    if result.feature_count == 0:
        result.add_warning("No water features in file")
        return result

    invalid_wtypes = set()

    for feature in features:
        props = feature.get('properties', {})

        wtype = props.get('wtype')
        if wtype and wtype not in VALID_WATER_TYPES:
            invalid_wtypes.add(wtype)

        if 'src' in props:
            result.sources_found.add(props['src'])

    if invalid_wtypes:
        result.add_warning(f"Unknown water types: {invalid_wtypes}")

    result.add_info(f"Total features: {result.feature_count}")
    result.add_info(f"Sources: {sorted(result.sources_found)}")

    return result


def print_result(result: ValidationResult, verbose: bool = False):
    """Print validation result."""
    status = "PASS" if result.passed else "FAIL"
    status_color = "\033[92m" if result.passed else "\033[91m"
    reset = "\033[0m"

    print(f"\n{status_color}[{status}]{reset} {result.filename}")

    for error in result.errors:
        print(f"  \033[91m✗ ERROR: {error}\033[0m")

    for warning in result.warnings:
        print(f"  \033[93m⚠ WARNING: {warning}\033[0m")

    if verbose:
        for info in result.info:
            print(f"  ℹ {info}")


def main():
    parser = argparse.ArgumentParser(description="Validate export files")
    parser.add_argument('--verbose', '-v', action='store_true', help="Show detailed info")
    parser.add_argument('--strict', action='store_true', help="Treat warnings as errors")
    parser.add_argument('--export-dir', type=Path, default=EXPORT_DIR, help="Export directory")
    args = parser.parse_args()

    print("=" * 60)
    print("EXPORT VALIDATION")
    print("=" * 60)
    print(f"Export directory: {args.export_dir}")

    results = []

    # Validate buildings
    buildings_path = args.export_dir / "buildings.geojson"
    result = validate_buildings(buildings_path, args.verbose)
    results.append(result)
    print_result(result, args.verbose)

    # Validate roads
    roads_path = args.export_dir / "roads_temporal.geojson"
    result = validate_roads(roads_path, args.verbose)
    results.append(result)
    print_result(result, args.verbose)

    # Validate water (optional)
    water_path = args.export_dir / "water.geojson"
    result = validate_water(water_path, args.verbose)
    results.append(result)
    print_result(result, args.verbose)

    # Summary
    print("\n" + "=" * 60)
    errors = sum(len(r.errors) for r in results)
    warnings = sum(len(r.warnings) for r in results)

    if errors > 0:
        print(f"\033[91mVALIDATION FAILED: {errors} errors, {warnings} warnings\033[0m")
        sys.exit(1)
    elif args.strict and warnings > 0:
        print(f"\033[93mVALIDATION FAILED (strict mode): {warnings} warnings\033[0m")
        sys.exit(1)
    else:
        print(f"\033[92mVALIDATION PASSED: {warnings} warnings\033[0m")
        sys.exit(0)


if __name__ == "__main__":
    main()
