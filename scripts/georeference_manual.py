#!/usr/bin/env python3
"""
Manual georeferencing helper for historical maps.

Given approximate corner coordinates, creates a world file and GeoTIFF
for the historical map image and its extracted features.

Usage:
    python georeference_manual.py --input map.jpg --output map_georef.tif \
        --bounds 10.37,63.42,10.44,63.44
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    print("Warning: rasterio not available, will create world file only")


def create_world_file(image_path: Path, bounds: tuple, output_path: Path = None):
    """
    Create a world file (.pgw/.jgw) for georeferencing.

    World file format (6 lines):
    1. pixel size in x-direction (usually positive)
    2. rotation about y-axis (usually 0)
    3. rotation about x-axis (usually 0)
    4. pixel size in y-direction (usually negative)
    5. x-coordinate of upper-left pixel center
    6. y-coordinate of upper-left pixel center

    Args:
        image_path: Path to the image
        bounds: (west, south, east, north) in degrees
        output_path: Output path for world file (default: same as image with world extension)
    """
    # Get image dimensions
    img = Image.open(image_path)
    width, height = img.size

    west, south, east, north = bounds

    # Calculate pixel size
    pixel_width = (east - west) / width
    pixel_height = (south - north) / height  # Negative because y increases downward

    # Upper-left corner (center of first pixel)
    x_origin = west + pixel_width / 2
    y_origin = north + pixel_height / 2

    # Determine world file extension
    suffix = image_path.suffix.lower()
    world_ext = {
        '.png': '.pgw',
        '.jpg': '.jgw',
        '.jpeg': '.jgw',
        '.tif': '.tfw',
        '.tiff': '.tfw',
    }.get(suffix, '.wld')

    if output_path is None:
        output_path = image_path.with_suffix(world_ext)

    # Write world file
    with open(output_path, 'w') as f:
        f.write(f"{pixel_width:.10f}\n")  # A: pixel size X
        f.write("0.0\n")                   # D: rotation Y
        f.write("0.0\n")                   # B: rotation X
        f.write(f"{pixel_height:.10f}\n") # E: pixel size Y (negative)
        f.write(f"{x_origin:.10f}\n")     # C: X origin
        f.write(f"{y_origin:.10f}\n")     # F: Y origin

    print(f"Created world file: {output_path}")
    print(f"  Image size: {width}x{height}")
    print(f"  Bounds: W={west:.6f}, S={south:.6f}, E={east:.6f}, N={north:.6f}")
    print(f"  Pixel size: {pixel_width:.8f} x {abs(pixel_height):.8f} degrees")

    return output_path


def create_geotiff(image_path: Path, bounds: tuple, output_path: Path):
    """
    Create a GeoTIFF from an image with georeferencing.

    Args:
        image_path: Path to input image
        bounds: (west, south, east, north) in degrees
        output_path: Output GeoTIFF path
    """
    if not HAS_RASTERIO:
        print("Error: rasterio required for GeoTIFF creation")
        return None

    # Load image
    img = Image.open(image_path)
    if img.mode == 'RGBA':
        # Convert to RGB, handling transparency
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    img_array = np.array(img)

    # Get dimensions
    height, width = img_array.shape[:2]

    # Create transform
    west, south, east, north = bounds
    transform = from_bounds(west, south, east, north, width, height)

    # Write GeoTIFF
    with rasterio.open(
        output_path,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=3,
        dtype=img_array.dtype,
        crs=CRS.from_epsg(4326),
        transform=transform,
    ) as dst:
        # Write RGB bands
        for i in range(3):
            dst.write(img_array[:, :, i], i + 1)

    print(f"Created GeoTIFF: {output_path}")
    return output_path


def create_geojson_from_mask(mask_path: Path, bounds: tuple, output_path: Path,
                              class_names: dict = None):
    """
    Convert a segmentation mask to GeoJSON polygons.

    Args:
        mask_path: Path to mask image (grayscale, values 0-4)
        bounds: (west, south, east, north) in degrees
        output_path: Output GeoJSON path
        class_names: Dict mapping class IDs to names
    """
    if class_names is None:
        class_names = {
            0: 'background',
            1: 'building',
            2: 'road',
            3: 'water',
            4: 'forest'
        }

    try:
        from rasterio import features as rio_features
        from shapely.geometry import shape, mapping
        from shapely.ops import unary_union
    except ImportError:
        print("Error: rasterio and shapely required for vectorization")
        return None

    # Load mask
    mask = np.array(Image.open(mask_path))
    height, width = mask.shape

    west, south, east, north = bounds
    transform = from_bounds(west, south, east, north, width, height)

    # Extract features for each class (except background)
    all_features = []

    for class_id in [1, 2, 3, 4]:  # Skip background
        class_mask = (mask == class_id).astype(np.uint8)

        if class_mask.sum() == 0:
            continue

        # Extract shapes
        shapes = list(rio_features.shapes(class_mask, transform=transform))

        # Filter to only keep the class pixels (value=1)
        for geom, value in shapes:
            if value == 1:
                # Simplify geometry to reduce file size
                poly = shape(geom)
                if poly.is_valid and poly.area > 1e-10:
                    # Simplify (tolerance in degrees, ~1m at this latitude)
                    simplified = poly.simplify(0.00001, preserve_topology=True)

                    feature = {
                        "type": "Feature",
                        "properties": {
                            "class": class_names.get(class_id, f"class_{class_id}"),
                            "class_id": class_id,
                            "start_date": 1904,
                            "source": "ml_extracted"
                        },
                        "geometry": mapping(simplified)
                    }
                    all_features.append(feature)

    # Create GeoJSON
    geojson = {
        "type": "FeatureCollection",
        "features": all_features
    }

    with open(output_path, 'w') as f:
        json.dump(geojson, f)

    print(f"Created GeoJSON: {output_path}")
    print(f"  Total features: {len(all_features)}")

    # Count by class
    class_counts = {}
    for f in all_features:
        cls = f['properties']['class']
        class_counts[cls] = class_counts.get(cls, 0) + 1

    for cls, count in sorted(class_counts.items()):
        print(f"    {cls}: {count}")

    return output_path


def main():
    parser = argparse.ArgumentParser(description='Georeference historical map')
    parser.add_argument('--input', '-i', required=True, help='Input image')
    parser.add_argument('--mask', '-m', help='Segmentation mask to vectorize')
    parser.add_argument('--output', '-o', help='Output path (default: input_georef.tif)')
    parser.add_argument('--bounds', '-b', required=True,
                       help='Bounds as west,south,east,north in degrees')
    parser.add_argument('--geojson', '-g', help='Output GeoJSON path for mask')
    parser.add_argument('--world-only', action='store_true',
                       help='Only create world file, not GeoTIFF')
    args = parser.parse_args()

    input_path = Path(args.input)

    # Parse bounds
    try:
        bounds = tuple(map(float, args.bounds.split(',')))
        if len(bounds) != 4:
            raise ValueError("Need exactly 4 values")
    except ValueError as e:
        print(f"Error parsing bounds: {e}")
        print("Expected format: west,south,east,north (e.g., 10.37,63.42,10.44,63.44)")
        sys.exit(1)

    # Create world file
    create_world_file(input_path, bounds)

    # Create GeoTIFF if requested
    if not args.world_only and HAS_RASTERIO:
        output_path = Path(args.output) if args.output else input_path.with_suffix('.tif')
        if output_path.suffix.lower() != '.tif':
            output_path = output_path.with_suffix('.tif')
        create_geotiff(input_path, bounds, output_path)

    # Vectorize mask if provided
    if args.mask:
        mask_path = Path(args.mask)
        geojson_path = Path(args.geojson) if args.geojson else mask_path.with_suffix('.geojson')
        create_geojson_from_mask(mask_path, bounds, geojson_path)


if __name__ == '__main__':
    main()
