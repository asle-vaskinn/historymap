#!/usr/bin/env python3
"""
Vectorization script for converting raster segmentation masks to vector polygons.
Converts predicted masks to GeoJSON format with optional geo-referencing.

Usage:
    python vectorize.py --input mask.png --output features.geojson
    python vectorize.py --input mask.png --output features.geojson --bounds "10.38,63.42,10.42,63.44"
    python vectorize.py --input-dir masks/ --output-dir vectors/ --simplify 1.0
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import cv2
import numpy as np
from PIL import Image
from tqdm import tqdm
import geojson
from shapely.geometry import Polygon, MultiPolygon, mapping
from shapely.ops import unary_union
from shapely import simplify as shapely_simplify


# Class definitions
CLASS_NAMES = {
    0: 'background',
    1: 'building',
    2: 'road',
    3: 'water',
    4: 'forest'
}

CLASS_COLORS = {
    0: None,  # Background - don't vectorize
    1: '#8B4513',  # Building - brown
    2: '#696969',  # Road - gray
    3: '#4169E1',  # Water - blue
    4: '#228B22'   # Forest - green
}


def load_mask(mask_path: str) -> np.ndarray:
    """
    Load segmentation mask from PNG file.

    Args:
        mask_path: Path to mask image

    Returns:
        Numpy array with class indices (H, W)
    """
    mask_image = Image.open(mask_path)
    mask = np.array(mask_image)

    # Ensure it's 2D
    if len(mask.shape) == 3:
        mask = mask[:, :, 0]

    return mask


def extract_contours(mask: np.ndarray, class_id: int) -> List[np.ndarray]:
    """
    Extract contours for a specific class from the mask.

    Args:
        mask: Segmentation mask (H, W)
        class_id: Class ID to extract

    Returns:
        List of contours (each is an array of points)
    """
    # Create binary mask for this class
    binary_mask = (mask == class_id).astype(np.uint8) * 255

    # Find contours
    contours, hierarchy = cv2.findContours(
        binary_mask,
        cv2.RETR_EXTERNAL,  # Only external contours
        cv2.CHAIN_APPROX_SIMPLE  # Compress horizontal/vertical/diagonal segments
    )

    return contours


def contour_to_polygon(contour: np.ndarray, min_area: float = 10.0) -> Optional[Polygon]:
    """
    Convert OpenCV contour to Shapely Polygon.

    Args:
        contour: OpenCV contour array
        min_area: Minimum area threshold (polygons smaller than this are discarded)

    Returns:
        Shapely Polygon or None if invalid
    """
    # Reshape contour
    points = contour.reshape(-1, 2)

    # Need at least 3 points for a polygon
    if len(points) < 3:
        return None

    # Create polygon
    try:
        polygon = Polygon(points)

        # Check if valid and meets minimum area
        if polygon.is_valid and polygon.area >= min_area:
            # Simplify to remove unnecessary vertices
            return polygon
        else:
            return None
    except Exception:
        return None


def pixel_to_geo_coords(
    x: float,
    y: float,
    mask_shape: Tuple[int, int],
    bounds: Tuple[float, float, float, float]
) -> Tuple[float, float]:
    """
    Convert pixel coordinates to geographic coordinates.

    Args:
        x: Pixel x coordinate
        y: Pixel y coordinate
        mask_shape: (height, width) of mask
        bounds: (min_lon, min_lat, max_lon, max_lat)

    Returns:
        (lon, lat) tuple
    """
    height, width = mask_shape
    min_lon, min_lat, max_lon, max_lat = bounds

    # Calculate lon/lat
    lon = min_lon + (x / width) * (max_lon - min_lon)
    lat = max_lat - (y / height) * (max_lat - min_lat)  # Y is inverted

    return lon, lat


def transform_polygon_to_geo(
    polygon: Polygon,
    mask_shape: Tuple[int, int],
    bounds: Tuple[float, float, float, float]
) -> Polygon:
    """
    Transform polygon from pixel coordinates to geographic coordinates.

    Args:
        polygon: Shapely polygon in pixel coordinates
        mask_shape: (height, width) of mask
        bounds: (min_lon, min_lat, max_lon, max_lat)

    Returns:
        Polygon in geographic coordinates
    """
    def transform_coords(coords):
        return [pixel_to_geo_coords(x, y, mask_shape, bounds) for x, y in coords]

    # Transform exterior ring
    exterior = transform_coords(polygon.exterior.coords)

    # Transform interior rings (holes)
    interiors = [transform_coords(interior.coords) for interior in polygon.interiors]

    return Polygon(exterior, interiors)


def merge_adjacent_polygons(polygons: List[Polygon], buffer_distance: float = 0.5) -> List[Polygon]:
    """
    Merge adjacent polygons of the same class.

    Args:
        polygons: List of Shapely polygons
        buffer_distance: Buffer distance for merging (in pixels or degrees)

    Returns:
        List of merged polygons
    """
    if not polygons:
        return []

    # Use unary_union to merge overlapping/touching polygons
    merged = unary_union(polygons)

    # Convert result to list
    if isinstance(merged, Polygon):
        return [merged]
    elif isinstance(merged, MultiPolygon):
        return list(merged.geoms)
    else:
        return []


def vectorize_mask(
    mask_path: str,
    output_path: str,
    bounds: Optional[Tuple[float, float, float, float]] = None,
    simplify_tolerance: float = 1.0,
    min_area: float = 10.0,
    merge_adjacent: bool = True,
    probability_map_path: Optional[str] = None
) -> Dict:
    """
    Convert raster mask to vector GeoJSON.

    Args:
        mask_path: Path to input mask PNG
        output_path: Path to output GeoJSON
        bounds: Optional (min_lon, min_lat, max_lon, max_lat) for geo-referencing
        simplify_tolerance: Douglas-Peucker simplification tolerance
        min_area: Minimum polygon area threshold
        merge_adjacent: Whether to merge adjacent polygons of the same class
        probability_map_path: Optional path to probability map for confidence values

    Returns:
        GeoJSON FeatureCollection dict
    """
    # Load mask
    mask = load_mask(mask_path)
    mask_shape = mask.shape

    # Load probability map if provided
    probability_map = None
    if probability_map_path and os.path.exists(probability_map_path):
        # This would need to be implemented if you save probability maps
        pass

    # Initialize feature collection
    features = []

    # Process each class (skip background class 0)
    for class_id in range(1, 5):
        class_name = CLASS_NAMES.get(class_id, f'class_{class_id}')

        # Extract contours for this class
        contours = extract_contours(mask, class_id)

        if not contours:
            continue

        # Convert contours to polygons
        polygons = []
        for contour in contours:
            polygon = contour_to_polygon(contour, min_area=min_area)
            if polygon is not None:
                polygons.append(polygon)

        if not polygons:
            continue

        # Merge adjacent polygons if requested
        if merge_adjacent:
            polygons = merge_adjacent_polygons(polygons)

        # Simplify polygons
        if simplify_tolerance > 0:
            polygons = [shapely_simplify(p, tolerance=simplify_tolerance, preserve_topology=True) for p in polygons]
            polygons = [p for p in polygons if p.is_valid and p.area >= min_area]

        # Transform to geographic coordinates if bounds provided
        if bounds is not None:
            polygons = [transform_polygon_to_geo(p, mask_shape, bounds) for p in polygons]

        # Create GeoJSON features
        for i, polygon in enumerate(polygons):
            properties = {
                'class': class_name,
                'class_id': int(class_id),
                'feature_id': f'{class_name}_{i}',
                'area': float(polygon.area),
            }

            # Add confidence if available
            if probability_map is not None:
                # Calculate average confidence for this polygon
                # This would require proper implementation with the probability map
                properties['confidence'] = 0.9  # Placeholder

            # Add color for styling
            if class_id in CLASS_COLORS and CLASS_COLORS[class_id]:
                properties['color'] = CLASS_COLORS[class_id]

            feature = geojson.Feature(
                geometry=mapping(polygon),
                properties=properties
            )
            features.append(feature)

    # Create FeatureCollection
    feature_collection = geojson.FeatureCollection(features)

    # Add metadata
    feature_collection['metadata'] = {
        'source': os.path.basename(mask_path),
        'bounds': bounds,
        'class_names': CLASS_NAMES,
        'feature_count': len(features),
        'class_counts': {
            CLASS_NAMES[i]: sum(1 for f in features if f['properties']['class_id'] == i)
            for i in range(1, 5)
        }
    }

    # Save to file
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(feature_collection, f, indent=2)

    return feature_collection


def process_directory(
    input_dir: str,
    output_dir: str,
    bounds: Optional[Tuple[float, float, float, float]] = None,
    simplify_tolerance: float = 1.0,
    min_area: float = 10.0,
    merge_adjacent: bool = True
):
    """Process all mask files in a directory."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Find all mask files
    mask_files = list(input_path.glob('*.png'))

    if not mask_files:
        print(f"No PNG files found in {input_dir}")
        return

    print(f"Found {len(mask_files)} masks to vectorize")

    # Process with progress bar
    for mask_file in tqdm(mask_files, desc="Vectorizing masks"):
        output_file = output_path / f"{mask_file.stem}.geojson"

        try:
            vectorize_mask(
                mask_path=str(mask_file),
                output_path=str(output_file),
                bounds=bounds,
                simplify_tolerance=simplify_tolerance,
                min_area=min_area,
                merge_adjacent=merge_adjacent
            )
        except Exception as e:
            print(f"\nError processing {mask_file.name}: {e}")
            continue


def parse_bounds(bounds_str: str) -> Tuple[float, float, float, float]:
    """
    Parse bounds string to tuple.

    Args:
        bounds_str: String in format "min_lon,min_lat,max_lon,max_lat"

    Returns:
        Tuple of (min_lon, min_lat, max_lon, max_lat)
    """
    try:
        values = [float(x.strip()) for x in bounds_str.split(',')]
        if len(values) != 4:
            raise ValueError("Bounds must have exactly 4 values")
        return tuple(values)
    except Exception as e:
        raise ValueError(f"Invalid bounds format: {e}")


def main():
    parser = argparse.ArgumentParser(description='Vectorize segmentation masks to GeoJSON')

    # Input/output arguments
    parser.add_argument('--input', help='Path to input mask PNG')
    parser.add_argument('--output', help='Path to output GeoJSON')
    parser.add_argument('--input-dir', help='Path to input directory')
    parser.add_argument('--output-dir', help='Path to output directory')

    # Geo-referencing
    parser.add_argument('--bounds', type=str,
                       help='Geographic bounds as "min_lon,min_lat,max_lon,max_lat" (e.g., "10.38,63.42,10.42,63.44")')

    # Processing arguments
    parser.add_argument('--simplify', type=float, default=1.0,
                       help='Polygon simplification tolerance (Douglas-Peucker). Higher = simpler. 0 = no simplification. (default: 1.0)')
    parser.add_argument('--min-area', type=float, default=10.0,
                       help='Minimum polygon area threshold. Smaller polygons are discarded. (default: 10.0)')
    parser.add_argument('--no-merge', action='store_true',
                       help='Disable merging of adjacent polygons')
    parser.add_argument('--probability-map', help='Path to probability map for confidence values (optional)')

    args = parser.parse_args()

    # Validate arguments
    if args.input and args.input_dir:
        print("Error: Cannot specify both --input and --input-dir")
        sys.exit(1)

    if not args.input and not args.input_dir:
        print("Error: Must specify either --input or --input-dir")
        sys.exit(1)

    if args.input and not args.output:
        print("Error: --output is required when using --input")
        sys.exit(1)

    if args.input_dir and not args.output_dir:
        print("Error: --output-dir is required when using --input-dir")
        sys.exit(1)

    # Parse bounds if provided
    bounds = None
    if args.bounds:
        try:
            bounds = parse_bounds(args.bounds)
            print(f"Using bounds: {bounds}")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    # Process
    if args.input:
        print(f"Vectorizing mask: {args.input}")
        result = vectorize_mask(
            mask_path=args.input,
            output_path=args.output,
            bounds=bounds,
            simplify_tolerance=args.simplify,
            min_area=args.min_area,
            merge_adjacent=not args.no_merge,
            probability_map_path=args.probability_map
        )
        print(f"Saved GeoJSON to {args.output}")
        print(f"Created {result['metadata']['feature_count']} features:")
        for class_name, count in result['metadata']['class_counts'].items():
            if count > 0:
                print(f"  {class_name}: {count}")
    else:
        process_directory(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            bounds=bounds,
            simplify_tolerance=args.simplify,
            min_area=args.min_area,
            merge_adjacent=not args.no_merge
        )
        print(f"Saved GeoJSON files to {args.output_dir}")


if __name__ == '__main__':
    main()
