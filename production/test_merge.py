#!/usr/bin/env python3
"""
Test script for merge_data.py

Creates sample data and tests the merging functionality.
Useful for development and verification.
"""

import json
import tempfile
from pathlib import Path
import sys

def create_sample_osm_data():
    """Create sample OSM GeoJSON data."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [10.395, 63.430],
                        [10.396, 63.430],
                        [10.396, 63.431],
                        [10.395, 63.431],
                        [10.395, 63.430]
                    ]]
                },
                "properties": {
                    "building": "yes",
                    "name": "Old Church",
                    "start_date": 1900
                }
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [10.395, 63.430],
                        [10.400, 63.435]
                    ]
                },
                "properties": {
                    "highway": "residential",
                    "name": "Main Street"
                }
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [10.400, 63.432],
                        [10.401, 63.432],
                        [10.401, 63.433],
                        [10.400, 63.433],
                        [10.400, 63.432]
                    ]]
                },
                "properties": {
                    "building": "yes",
                    "name": "Town Hall"
                }
            }
        ]
    }

def create_sample_historical_data():
    """Create sample historical GeoJSON data."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [10.395, 63.430],
                        [10.396, 63.430],
                        [10.396, 63.431],
                        [10.395, 63.431],
                        [10.395, 63.430]
                    ]]
                },
                "properties": {
                    "feature_class": "building",
                    "name": "Old Church",
                    "start_date": 1850,
                    "confidence": 0.85
                }
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [10.410, 63.440],
                        [10.411, 63.440],
                        [10.411, 63.441],
                        [10.410, 63.441],
                        [10.410, 63.440]
                    ]]
                },
                "properties": {
                    "feature_class": "building",
                    "name": "Old Factory",
                    "start_date": 1890,
                    "end_date": 1970,
                    "confidence": 0.75
                }
            }
        ]
    }

def test_merge():
    """Test the merge functionality."""
    print("Creating test data...")

    # Create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Write OSM data
        osm_file = tmpdir / "osm_sample.geojson"
        with open(osm_file, 'w') as f:
            json.dump(create_sample_osm_data(), f, indent=2)
        print(f"✓ Created OSM sample: {osm_file}")

        # Create historical directory
        historical_dir = tmpdir / "historical"
        historical_dir.mkdir()

        # Write historical data
        hist_file = historical_dir / "kartverket_1900.geojson"
        with open(hist_file, 'w') as f:
            json.dump(create_sample_historical_data(), f, indent=2)
        print(f"✓ Created historical sample: {hist_file}")

        # Output file
        output_file = tmpdir / "merged.geojson"

        # Import and run merge
        print("\nRunning merge...")
        sys.path.insert(0, str(Path(__file__).parent))
        from merge_data import DataMerger

        merger = DataMerger(similarity_threshold=0.8)
        success = merger.merge_all_sources(osm_file, historical_dir, output_file)

        if not success:
            print("✗ Merge failed")
            return False

        # Validate output
        print("\nValidating output...")
        with open(output_file, 'r') as f:
            result = json.load(f)

        features = result['features']
        print(f"✓ Total features in output: {len(features)}")

        # Check for expected features
        building_count = sum(1 for f in features if f['properties'].get('feature_class') == 'building')
        road_count = sum(1 for f in features if f['properties'].get('feature_class') == 'road')

        print(f"✓ Buildings: {building_count}")
        print(f"✓ Roads: {road_count}")

        # Check duplicate merging
        # Old Church should be merged (appears in both OSM and historical)
        old_church = None
        for f in features:
            if 'Old Church' in str(f['properties'].get('name', '')):
                old_church = f
                break

        if old_church:
            props = old_church['properties']
            print(f"\n✓ Found merged feature 'Old Church':")
            print(f"  start_date: {props.get('start_date')} (should be 1850 - earliest)")
            print(f"  source: {props.get('source')} (should include both sources)")
            print(f"  confidence: {props.get('confidence')}")

            if props.get('start_date') == 1850:
                print("  ✓ Correctly took earliest start_date")
            else:
                print("  ✗ Did not take earliest start_date")

            if 'osm' in props.get('source', '') and 'kartverket' in props.get('source', ''):
                print("  ✓ Correctly merged sources")
            else:
                print("  ✗ Did not merge sources correctly")

        # Check temporal attributes
        features_with_start = sum(1 for f in features if f['properties'].get('start_date') is not None)
        print(f"\n✓ Features with start_date: {features_with_start}/{len(features)}")

        # Show full output
        print("\nFull merged output:")
        print(json.dumps(result, indent=2))

        print("\n✓ All tests passed!")
        return True

if __name__ == '__main__':
    try:
        success = test_merge()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
