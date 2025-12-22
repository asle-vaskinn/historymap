#!/usr/bin/env python3
"""
Test script for PMTiles export functionality.

Creates a minimal test GeoJSON file and converts it to PMTiles
to verify the export pipeline works correctly.
"""

import json
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from export.export_pmtiles import export_pmtiles, check_tippecanoe


def create_test_geojson(path: Path) -> None:
    """
    Create a minimal test GeoJSON file with temporal attributes.

    Args:
        path: Path to write test GeoJSON
    """
    # Create a simple building polygon in Trondheim
    # Coordinates roughly at city center (63.43, 10.39)
    test_data = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'properties': {
                    'bid': 'test-1',
                    'src': 'osm',
                    'sd': 1880,
                    'ed': None,
                    'ev': 'h',
                    'bt': 'residential',
                    'nm': 'Test Building 1'
                },
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [10.39, 63.43],
                        [10.391, 63.43],
                        [10.391, 63.431],
                        [10.39, 63.431],
                        [10.39, 63.43]
                    ]]
                }
            },
            {
                'type': 'Feature',
                'properties': {
                    'bid': 'test-2',
                    'src': 'sef',
                    'sd': 1920,
                    'ed': 1980,
                    'ev': 'm',
                    'bt': 'commercial'
                },
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [10.392, 63.43],
                        [10.393, 63.43],
                        [10.393, 63.431],
                        [10.392, 63.431],
                        [10.392, 63.43]
                    ]]
                }
            },
            {
                'type': 'Feature',
                'properties': {
                    'bid': 'ml-3',
                    'src': 'ml',
                    'ml_src': 'kv1880',
                    'sd': 1860,
                    'ed': None,
                    'ev': 'l',
                    'mlc': 0.85
                },
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [10.394, 63.43],
                        [10.395, 63.43],
                        [10.395, 63.431],
                        [10.394, 63.431],
                        [10.394, 63.43]
                    ]]
                }
            }
        ]
    }

    with open(path, 'w') as f:
        json.dump(test_data, f)


def test_pmtiles_export() -> bool:
    """
    Test PMTiles export with minimal test data.

    Returns:
        True if successful
    """
    print("Testing PMTiles export...")
    print("="*60)

    # Check if tippecanoe is available
    if not check_tippecanoe():
        print("\nERROR: tippecanoe not found")
        print("\nInstallation instructions:")
        print("  macOS:  brew install tippecanoe")
        print("  Linux:  Build from https://github.com/felt/tippecanoe")
        return False

    print("\n✓ tippecanoe is available")

    # Create temporary files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        test_geojson = tmpdir / 'test_buildings.geojson'
        test_pmtiles = tmpdir / 'test_buildings.pmtiles'

        # Create test GeoJSON
        print("\nCreating test GeoJSON...")
        create_test_geojson(test_geojson)
        print(f"  Created: {test_geojson}")

        with open(test_geojson) as f:
            data = json.load(f)
        print(f"  Features: {len(data['features'])}")

        # Export to PMTiles
        print("\nExporting to PMTiles...")
        success = export_pmtiles(
            input_path=test_geojson,
            output_path=test_pmtiles,
            min_zoom=10,
            max_zoom=16,
            layer_name='buildings',
            name='Test Buildings',
            description='Test building data for PMTiles export',
            attribution='Test data',
            force=True,
            verbose=True
        )

        if not success:
            print("\n✗ PMTiles export failed")
            return False

        # Check output
        if not test_pmtiles.exists():
            print("\n✗ Output file was not created")
            return False

        print("\n✓ PMTiles file created successfully")

        # Check metadata file
        metadata_path = test_pmtiles.with_suffix('.meta.json')
        if not metadata_path.exists():
            print("✗ Metadata file was not created")
            return False

        print("✓ Metadata file created")

        with open(metadata_path) as f:
            metadata = json.load(f)

        print("\nMetadata:")
        print(f"  Format: {metadata.get('format')}")
        print(f"  Features: {metadata.get('feature_count')}")
        print(f"  Size: {metadata.get('size_mb')} MB")
        print(f"  Zoom levels: {metadata.get('zoom_levels', {}).get('min')}-{metadata.get('zoom_levels', {}).get('max')}")
        print(f"  Layer: {metadata.get('layer_name')}")

        # Verify key metadata
        assert metadata.get('format') == 'pmtiles', "Format mismatch"
        assert metadata.get('feature_count') == 3, "Feature count mismatch"
        assert metadata.get('layer_name') == 'buildings', "Layer name mismatch"
        assert metadata.get('zoom_levels', {}).get('min') == 10, "Min zoom mismatch"
        assert metadata.get('zoom_levels', {}).get('max') == 16, "Max zoom mismatch"

        print("\n✓ Metadata validation passed")

    print("\n" + "="*60)
    print("✓ All tests passed!")
    print("="*60)

    return True


def main():
    """CLI entry point."""
    print("\nPMTiles Export Test")
    print("="*60)
    print("\nThis test creates a minimal GeoJSON file and converts it")
    print("to PMTiles to verify the export pipeline works correctly.")
    print("="*60)

    try:
        success = test_pmtiles_export()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
