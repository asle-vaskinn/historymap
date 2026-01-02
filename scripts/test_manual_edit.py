#!/usr/bin/env python3
"""
Test script for manual building edit workflow.

Tests the complete flow:
1. Select a test building
2. Create a manual edit via API
3. Run normalization and merge
4. Verify the edit appears in merged output
5. Generate a subset PMTiles with the edited building
6. Clean up the test edit

Run with: python scripts/test_manual_edit.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import requests

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
EDITS_PATH = DATA_DIR / 'sources' / 'manual' / 'raw' / 'edits.json'
MERGED_PATH = DATA_DIR / 'merged' / 'buildings_merged.geojson'
EXPORT_PATH = DATA_DIR / 'export' / 'buildings.geojson'

# Test configuration
API_URL = 'http://localhost:5001'
TEST_OSM_ID = 'way/test_building_12345'  # Unique test ID
TEST_SD = 1888  # Test construction year
TEST_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [10.4, 63.43],
        [10.401, 63.43],
        [10.401, 63.431],
        [10.4, 63.431],
        [10.4, 63.43]
    ]]
}


def print_step(step_num, message):
    """Print a formatted step message."""
    print(f"\n{'='*60}")
    print(f"STEP {step_num}: {message}")
    print('='*60)


def backup_edits():
    """Backup current edits file."""
    if EDITS_PATH.exists():
        backup_path = EDITS_PATH.with_suffix('.json.backup')
        shutil.copy(EDITS_PATH, backup_path)
        print(f"  Backed up edits to {backup_path}")
        return backup_path
    return None


def restore_edits(backup_path):
    """Restore edits from backup."""
    if backup_path and backup_path.exists():
        shutil.copy(backup_path, EDITS_PATH)
        backup_path.unlink()
        print(f"  Restored edits from {backup_path}")


def check_api_health():
    """Check if the API server is running."""
    try:
        response = requests.get(f'{API_URL}/api/health', timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def get_current_edits():
    """Get current manual edits from API."""
    response = requests.get(f'{API_URL}/api/manual')
    response.raise_for_status()
    return response.json()


def add_test_edit():
    """Add a test manual edit via API."""
    payload = {
        'osm_id': TEST_OSM_ID,
        'geometry': TEST_GEOMETRY,
        'sd': TEST_SD,
        'ed': None,
        'note': 'TEST EDIT - should be removed after test'
    }

    response = requests.post(
        f'{API_URL}/api/manual',
        json=payload,
        headers={'Content-Type': 'application/json'}
    )
    response.raise_for_status()
    return response.json()


def remove_test_edit():
    """Remove the test edit from edits.json directly."""
    if not EDITS_PATH.exists():
        return False

    with open(EDITS_PATH, 'r') as f:
        edits = json.load(f)

    original_count = len(edits['features'])
    edits['features'] = [
        f for f in edits['features']
        if f['properties'].get('osm_id') != TEST_OSM_ID
    ]
    new_count = len(edits['features'])

    with open(EDITS_PATH, 'w') as f:
        json.dump(edits, f, indent=2)

    removed = original_count - new_count
    print(f"  Removed {removed} test edit(s)")
    return removed > 0


def run_normalize():
    """Run normalization for manual source."""
    print("  Running normalize for manual source...")
    env = os.environ.copy()
    env['PYTHONPATH'] = str(PROJECT_ROOT / 'scripts')

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / 'scripts' / 'pipeline.py'),
         '--stage', 'normalize', '--sources', 'manual'],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"  ERROR: {result.stderr}")
        return False

    print(f"  {result.stdout.strip().split(chr(10))[-1]}")
    return True


def run_merge():
    """Run merge pipeline."""
    print("  Running merge...")
    env = os.environ.copy()
    env['PYTHONPATH'] = str(PROJECT_ROOT / 'scripts')
    env['PYTHONUNBUFFERED'] = '1'

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / 'scripts' / 'pipeline.py'),
         '--stage', 'merge'],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"  ERROR: {result.stderr}")
        return False

    # Show last few lines
    lines = result.stdout.strip().split('\n')
    for line in lines[-5:]:
        print(f"  {line}")
    return True


def verify_edit_in_merge(osm_id, expected_sd):
    """Verify the edit appears in merged output with correct date."""
    if not MERGED_PATH.exists():
        print(f"  ERROR: Merged file not found: {MERGED_PATH}")
        return False

    with open(MERGED_PATH, 'r') as f:
        merged = json.load(f)

    # Find the building by _src_id (the OSM reference in merged data)
    for feature in merged['features']:
        props = feature.get('properties', {})
        feature_src_id = props.get('_src_id')

        if feature_src_id == osm_id:
            actual_sd = props.get('sd')
            sd_src = props.get('sd_src', 'unknown')
            print(f"  Found building: _src_id={osm_id}")
            print(f"    sd={actual_sd}, expected={expected_sd}")
            print(f"    ev={props.get('ev')}")
            print(f"    _src={props.get('_src')}, sd_src={sd_src}")

            if actual_sd == expected_sd:
                print(f"  SUCCESS: Date matches!")
                if sd_src == 'manual':
                    print(f"  SUCCESS: sd_src is 'manual' as expected!")
                return True
            else:
                print(f"  MISMATCH: Expected sd={expected_sd}, got sd={actual_sd}")
                return False

    print(f"  Building not found in merged output: {osm_id}")
    return False


def generate_test_pmtiles():
    """Generate a small PMTiles file with just the test area."""
    print("  Running export (full pipeline)...")
    env = os.environ.copy()
    env['PYTHONPATH'] = str(PROJECT_ROOT / 'scripts')
    env['PYTHONUNBUFFERED'] = '1'

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / 'scripts' / 'pipeline.py'),
         '--stage', 'export'],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"  ERROR: {result.stderr}")
        return False

    # Show PMTiles output info
    lines = result.stdout.strip().split('\n')
    for line in lines:
        if 'PMTiles' in line or 'Output:' in line or 'Size:' in line:
            print(f"  {line}")

    return True


def use_real_building():
    """Use a real existing building for testing instead of synthetic."""
    # Find a real building from the merged data to use as test subject
    if not MERGED_PATH.exists():
        print("  No merged file yet, will use synthetic test building")
        return None, None, None

    with open(MERGED_PATH, 'r') as f:
        merged = json.load(f)

    # Find a building with coordinates (preferably one without manual edits)
    for feature in merged['features'][:500]:  # Check first 500
        props = feature.get('properties', {})
        osm_id = props.get('_src_id')  # OSM buildings have _src_id like "way/123"

        if osm_id and osm_id.startswith('way/') and feature.get('geometry'):
            # Don't pick buildings that already have manual edits
            if props.get('sd_src') == 'manual':
                continue

            # Pick a building with an inherited date (low evidence) to make test visible
            if props.get('ev') == 'l' and props.get('sd_inherited'):
                original_sd = props.get('sd')
                print(f"  Selected test building: {osm_id}")
                print(f"    Current sd: {original_sd} (inherited)")
                print(f"    Source: {props.get('_src')}")
                return osm_id, feature['geometry'], original_sd

    # Fallback: just pick any building with _src_id
    for feature in merged['features'][:100]:
        props = feature.get('properties', {})
        osm_id = props.get('_src_id')
        if osm_id and osm_id.startswith('way/') and feature.get('geometry'):
            original_sd = props.get('sd')
            print(f"  Selected test building (fallback): {osm_id}")
            print(f"    Current sd: {original_sd}")
            return osm_id, feature['geometry'], original_sd

    return None, None, None


def main():
    """Run the complete test workflow."""
    print("\n" + "="*60)
    print("MANUAL EDIT WORKFLOW TEST")
    print("="*60)
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Project root: {PROJECT_ROOT}")

    # Step 1: Check API server
    print_step(1, "Check API server")
    if not check_api_health():
        print("  ERROR: API server not running!")
        print("  Start it with: python scripts/api/server.py")
        return False
    print("  API server is healthy")

    # Get current edits count
    current_edits = get_current_edits()
    print(f"  Current edits count: {len(current_edits['features'])}")

    # Step 2: Select a real building to test
    print_step(2, "Select test building")
    real_osm_id, real_geometry, original_sd = use_real_building()

    if real_osm_id:
        test_osm_id = real_osm_id
        test_geometry = real_geometry
        print(f"  Using real building: {test_osm_id}")
    else:
        test_osm_id = TEST_OSM_ID
        test_geometry = TEST_GEOMETRY
        original_sd = None
        print(f"  Using synthetic building: {test_osm_id}")

    # Step 3: Backup current edits
    print_step(3, "Backup current edits")
    backup_path = backup_edits()

    try:
        # Step 4: Add test edit via API
        print_step(4, "Add test edit via API")

        payload = {
            'osm_id': test_osm_id,
            'geometry': test_geometry,
            'sd': TEST_SD,
            'ed': None,
            'note': 'TEST EDIT - should be removed after test'
        }

        response = requests.post(
            f'{API_URL}/api/manual',
            json=payload,
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code != 201:
            print(f"  ERROR: API returned {response.status_code}")
            print(f"  Response: {response.text}")
            return False

        result = response.json()
        print(f"  Created edit:")
        print(f"    osm_id: {result['properties']['osm_id']}")
        print(f"    sd: {result['properties']['sd']}")
        print(f"    ev: {result['properties']['ev']}")

        # Step 5: Run normalize
        print_step(5, "Normalize manual source")
        if not run_normalize():
            print("  ERROR: Normalization failed")
            return False

        # Step 6: Run merge
        print_step(6, "Run merge pipeline")
        if not run_merge():
            print("  ERROR: Merge failed")
            return False

        # Step 7: Verify edit in merged output
        print_step(7, "Verify edit in merged output")

        # First check normalized output
        normalized_path = DATA_DIR / 'sources' / 'manual' / 'normalized' / 'buildings.geojson'
        if normalized_path.exists():
            with open(normalized_path, 'r') as f:
                normalized = json.load(f)
            found = any(
                f['properties'].get('osm_id') == test_osm_id
                for f in normalized['features']
            )
            if found:
                print(f"  Test building found in normalized manual source")
            else:
                print(f"  Test building NOT found in normalized manual source")

        # Then check merged output
        if real_osm_id:
            # For real buildings, check by _osm_id in merged data
            verified = verify_edit_in_merge(test_osm_id, TEST_SD)
        else:
            # For synthetic buildings, we can only verify they're in normalized
            verified = found if 'found' in dir() else False
            if verified:
                print(f"  (Synthetic buildings won't appear in OSM-centric merge)")
                print(f"  Verified in normalized output only")

        # Step 8: Generate PMTiles (optional - takes time)
        print_step(8, "Generate PMTiles (export)")
        if not generate_test_pmtiles():
            print("  WARNING: PMTiles generation failed")
        else:
            print("  PMTiles generated successfully")

        # Step 9: Cleanup
        print_step(9, "Cleanup - remove test edit")

        # Remove the test edit from edits.json
        with open(EDITS_PATH, 'r') as f:
            edits = json.load(f)

        original_count = len(edits['features'])
        edits['features'] = [
            f for f in edits['features']
            if f['properties'].get('osm_id') != test_osm_id
        ]

        with open(EDITS_PATH, 'w') as f:
            json.dump(edits, f, indent=2)

        removed_count = original_count - len(edits['features'])
        print(f"  Removed {removed_count} test edit(s)")

        # Re-run normalize to clean up
        print("  Re-normalizing to clean up...")
        run_normalize()

        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"  Test building: {test_osm_id}")
        print(f"  Test year: {TEST_SD}")
        print(f"  Edit verified in merge: {'YES' if verified else 'NO'}")
        print(f"  Cleanup completed: YES")

        return verified

    finally:
        # Always try to restore backup if something went wrong
        if backup_path and backup_path.exists():
            print("\n  (Backup file preserved at: {backup_path})")


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
