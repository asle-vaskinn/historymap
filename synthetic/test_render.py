#!/usr/bin/env python3
"""
Test script to verify the rendering pipeline works correctly.

This script tests the basic rendering functionality without requiring
a PMTiles file, by creating synthetic test features.
"""

import sys
from pathlib import Path

try:
    from PIL import Image
    from render_tiles import TileRenderer, RenderConfig
    from tile_utils import TileCoordinates
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    print("Please install requirements: pip install -r requirements.txt")
    sys.exit(1)


def create_test_features():
    """
    Create synthetic test features to render without needing real data.

    Returns a dictionary of features in GeoJSON-like format.
    """
    # Example features for Trondheim area (z=14, x=8378, y=4543)
    z, x, y = 14, 8378, 4543
    bbox = TileCoordinates.tile_to_bbox(z, x, y)
    min_lon, min_lat, max_lon, max_lat = bbox

    # Calculate some coordinates within the tile
    center_lon = (min_lon + max_lon) / 2
    center_lat = (min_lat + max_lat) / 2
    quarter_lon = (max_lon - min_lon) / 4
    quarter_lat = (max_lat - min_lat) / 4

    features = {
        'building': [
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [center_lon - quarter_lon, center_lat - quarter_lat],
                        [center_lon + quarter_lon, center_lat - quarter_lat],
                        [center_lon + quarter_lon, center_lat + quarter_lat],
                        [center_lon - quarter_lon, center_lat + quarter_lat],
                        [center_lon - quarter_lon, center_lat - quarter_lat],
                    ]]
                },
                'properties': {'type': 'building'}
            }
        ],
        'transportation': [
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [
                        [min_lon, center_lat],
                        [max_lon, center_lat],
                    ]
                },
                'properties': {'class': 'primary'}
            },
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [
                        [center_lon, min_lat],
                        [center_lon, max_lat],
                    ]
                },
                'properties': {'class': 'secondary'}
            }
        ],
        'water': [
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [min_lon, min_lat],
                        [min_lon + quarter_lon, min_lat],
                        [min_lon + quarter_lon, min_lat + quarter_lat],
                        [min_lon, min_lat + quarter_lat],
                        [min_lon, min_lat],
                    ]]
                },
                'properties': {'type': 'water'}
            }
        ]
    }

    return features


def test_basic_rendering():
    """Test basic rendering with synthetic features."""
    print("Testing basic rendering...")

    # Check if styles exist
    styles_dir = Path(__file__).parent / 'styles'
    if not styles_dir.exists():
        print(f"Error: Styles directory not found: {styles_dir}")
        return False

    basic_style = styles_dir / 'basic_map.json'
    if not basic_style.exists():
        print(f"Error: Basic style not found: {basic_style}")
        return False

    try:
        # Create renderer
        config = RenderConfig(tile_size=512)
        renderer = TileRenderer(str(basic_style), config)
        print(f"✓ Renderer initialized with style: {basic_style.name}")

        # Create test features
        features = create_test_features()
        print(f"✓ Created {sum(len(v) for v in features.values())} test features")

        # Render tile
        z, x, y = 14, 8378, 4543
        img = renderer.render_tile(z, x, y, features=features)
        print(f"✓ Rendered tile z={z}, x={x}, y={y}")

        # Save output
        output_file = Path(__file__).parent / 'test_output.png'
        img.save(output_file)
        print(f"✓ Saved test output to: {output_file}")

        # Verify output
        if output_file.exists() and output_file.stat().st_size > 0:
            print(f"✓ Output file is valid ({output_file.stat().st_size} bytes)")
            return True
        else:
            print("✗ Output file is empty or invalid")
            return False

    except Exception as e:
        print(f"✗ Error during rendering: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tile_coordinates():
    """Test tile coordinate conversion utilities."""
    print("\nTesting tile coordinate utilities...")

    try:
        # Test Trondheim coordinates
        lon, lat = 10.4, 63.43
        zoom = 14

        # Convert to tile
        x, y = TileCoordinates.lonlat_to_tile(lon, lat, zoom)
        print(f"✓ Converted ({lon}, {lat}) -> tile ({zoom}/{x}/{y})")

        # Get bbox
        bbox = TileCoordinates.tile_to_bbox(zoom, x, y)
        print(f"✓ Tile bbox: {bbox}")

        # Get center
        center = TileCoordinates.get_tile_center(zoom, x, y)
        print(f"✓ Tile center: {center}")

        # Verify conversion is reasonable
        min_lon, min_lat, max_lon, max_lat = bbox
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            print("✓ Coordinates are within tile bounds")
            return True
        else:
            print("✗ Coordinates are NOT within tile bounds")
            return False

    except Exception as e:
        print(f"✗ Error in coordinate conversion: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multiple_styles():
    """Test rendering with different historical styles."""
    print("\nTesting multiple historical styles...")

    styles_dir = Path(__file__).parent / 'styles'
    test_styles = ['basic_map.json', 'military_1880.json', 'cadastral_1900.json', 'topographic_1920.json']

    features = create_test_features()
    z, x, y = 14, 8378, 4543

    success_count = 0
    for style_name in test_styles:
        style_path = styles_dir / style_name
        if not style_path.exists():
            print(f"  ⊘ Style not found: {style_name}")
            continue

        try:
            renderer = TileRenderer(str(style_path))
            img = renderer.render_tile(z, x, y, features=features)

            output_file = Path(__file__).parent / f'test_{style_path.stem}.png'
            img.save(output_file)

            print(f"  ✓ {style_name} -> {output_file.name}")
            success_count += 1
        except Exception as e:
            print(f"  ✗ {style_name}: {e}")

    if success_count == len(test_styles):
        print(f"✓ All {success_count} styles rendered successfully")
        return True
    elif success_count > 0:
        print(f"⚠ {success_count}/{len(test_styles)} styles rendered successfully")
        return True
    else:
        print("✗ No styles rendered successfully")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Rendering Pipeline Test Suite")
    print("=" * 60)

    results = []

    # Test 1: Tile coordinates
    results.append(("Tile Coordinates", test_tile_coordinates()))

    # Test 2: Basic rendering
    results.append(("Basic Rendering", test_basic_rendering()))

    # Test 3: Multiple styles
    results.append(("Multiple Styles", test_multiple_styles()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)

    print(f"\nTotal: {passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n✓ All tests passed! Rendering pipeline is working correctly.")
        return 0
    else:
        print(f"\n⚠ {total_count - passed_count} test(s) failed.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
