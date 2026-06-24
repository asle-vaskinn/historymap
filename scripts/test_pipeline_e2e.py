#!/usr/bin/env python3
"""
End-to-end pipeline test.

Verifies the full pipeline by:
1. Injecting a test building into manual source
2. Running the pipeline
3. Verifying the test building appears in PMTiles output
4. Removing the test building
5. Running the pipeline again
6. Verifying the test building is gone

Usage:
    python scripts/test_pipeline_e2e.py
    python scripts/test_pipeline_e2e.py --keep  # Don't clean up after test
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Test building marker - unique name to identify in output
TEST_MARKER = "TEST_PIPELINE_E2E_MARKER"
TEST_BUILDING_ID = "test-pipeline-e2e-12345"

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
# Inject into RAW (not normalized) so the normalize step picks it up
MANUAL_SOURCE = PROJECT_ROOT / "data" / "sources" / "manual" / "raw" / "buildings.geojson"
PMTILES_OUTPUT = PROJECT_ROOT / "data" / "export" / "buildings_temporal.pmtiles"
GEOJSON_OUTPUT = PROJECT_ROOT / "data" / "export" / "buildings.geojson"

# Test building - placed in the sea outside Trondheim (won't interfere with real data)
TEST_BUILDING = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[10.35, 63.50], [10.351, 63.50], [10.351, 63.501], [10.35, 63.501], [10.35, 63.50]]]
    },
    "properties": {
        "_src": "manual",
        "_src_id": TEST_BUILDING_ID,
        "sd": 1999,
        "ev": "h",
        "nm": TEST_MARKER,
        "bt": "test"
    }
}


def load_manual_source() -> dict:
    """Load the manual source GeoJSON."""
    if not MANUAL_SOURCE.exists():
        return {"type": "FeatureCollection", "features": []}

    with open(MANUAL_SOURCE) as f:
        return json.load(f)


def save_manual_source(data: dict):
    """Save the manual source GeoJSON."""
    MANUAL_SOURCE.parent.mkdir(parents=True, exist_ok=True)
    with open(MANUAL_SOURCE, 'w') as f:
        json.dump(data, f, indent=2)


def inject_test_building():
    """Add test building to manual source."""
    print("\n[INJECT] Adding test building to manual source...")

    data = load_manual_source()

    # Remove any existing test building first
    data['features'] = [f for f in data['features']
                        if f.get('properties', {}).get('nm') != TEST_MARKER]

    # Add test building
    data['features'].append(TEST_BUILDING)
    save_manual_source(data)

    print(f"  Added: {TEST_MARKER}")
    print(f"  Manual source now has {len(data['features'])} features")


def remove_test_building():
    """Remove test building from manual source."""
    print("\n[REMOVE] Removing test building from manual source...")

    data = load_manual_source()
    original_count = len(data['features'])

    data['features'] = [f for f in data['features']
                        if f.get('properties', {}).get('nm') != TEST_MARKER]

    save_manual_source(data)

    removed = original_count - len(data['features'])
    print(f"  Removed {removed} test feature(s)")
    print(f"  Manual source now has {len(data['features'])} features")


def run_pipeline():
    """Run the rebuild pipeline."""
    print("\n[PIPELINE] Running rebuild.sh...")

    result = subprocess.run(
        ["./rebuild.sh"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"  ERROR: Pipeline failed!")
        print(result.stderr)
        return False

    print("  Pipeline completed successfully")
    return True


def check_pmtiles_for_marker() -> bool:
    """Check if test building exists in PMTiles output."""
    print("\n[VERIFY] Checking PMTiles for test building...")

    if not PMTILES_OUTPUT.exists():
        print(f"  ERROR: PMTiles not found: {PMTILES_OUTPUT}")
        return False

    try:
        import pmtiles
        from pmtiles.reader import Reader, MmapSource

        with open(PMTILES_OUTPUT, 'rb') as f:
            source = MmapSource(f)
            reader = Reader(source)

            # Get metadata
            metadata = reader.metadata()
            print(f"  PMTiles metadata: {metadata.get('name', 'unnamed')}")

            # We can't easily search PMTiles by attribute without extracting all tiles
            # Fall back to checking GeoJSON export instead
            print("  (PMTiles attribute search not implemented, checking GeoJSON export)")

    except ImportError:
        print("  pmtiles library not available, checking GeoJSON export instead")

    # Fall back to checking GeoJSON export
    return check_geojson_for_marker()


def check_geojson_for_marker() -> bool:
    """Check if test building exists in GeoJSON export."""
    if not GEOJSON_OUTPUT.exists():
        print(f"  ERROR: GeoJSON not found: {GEOJSON_OUTPUT}")
        return False

    with open(GEOJSON_OUTPUT) as f:
        data = json.load(f)

    # Search for test marker
    for feature in data.get('features', []):
        props = feature.get('properties', {})
        if props.get('nm') == TEST_MARKER:
            print(f"  FOUND: {TEST_MARKER}")
            print(f"    sd: {props.get('sd')}")
            print(f"    ev: {props.get('ev')}")
            return True

    print(f"  NOT FOUND: {TEST_MARKER}")
    return False


def run_test(keep: bool = False) -> bool:
    """Run the full end-to-end test."""
    print("=" * 60)
    print("END-TO-END PIPELINE TEST")
    print("=" * 60)

    success = True

    try:
        # Step 1: Inject test building
        inject_test_building()

        # Step 2: Run pipeline
        if not run_pipeline():
            print("\n[FAIL] Pipeline failed on first run")
            return False

        # Step 3: Verify test building exists
        print("\n" + "-" * 40)
        print("TEST 1: Building should EXIST after injection")
        print("-" * 40)

        if check_pmtiles_for_marker():
            print("\n[PASS] Test building found in output!")
        else:
            print("\n[FAIL] Test building NOT found in output!")
            success = False

        # Step 4: Remove test building
        remove_test_building()

        # Step 5: Run pipeline again
        if not run_pipeline():
            print("\n[FAIL] Pipeline failed on second run")
            return False

        # Step 6: Verify test building is gone
        print("\n" + "-" * 40)
        print("TEST 2: Building should NOT EXIST after removal")
        print("-" * 40)

        if not check_pmtiles_for_marker():
            print("\n[PASS] Test building correctly removed from output!")
        else:
            print("\n[FAIL] Test building still in output after removal!")
            success = False

    finally:
        # Cleanup (unless --keep)
        if not keep:
            print("\n[CLEANUP] Removing any remaining test data...")
            remove_test_building()

    # Summary
    print("\n" + "=" * 60)
    if success:
        print("[SUCCESS] All tests passed!")
    else:
        print("[FAILURE] Some tests failed!")
    print("=" * 60)

    return success


def main():
    parser = argparse.ArgumentParser(
        description='End-to-end pipeline test'
    )
    parser.add_argument('--keep', action='store_true',
                        help="Don't clean up test data after running")

    args = parser.parse_args()

    success = run_test(keep=args.keep)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
