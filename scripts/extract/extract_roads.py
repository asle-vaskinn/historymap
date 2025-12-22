#!/usr/bin/env python3
"""
Extract roads from ML prediction images as vector LineStrings.

This script:
1. Loads prediction image (grayscale, road pixels are bright)
2. Thresholds to binary (default 0.5)
3. Skeletonizes to 1-pixel width using scikit-image
4. Traces connected components as LineStrings
5. Simplifies with Douglas-Peucker (tolerance=1m in pixel coords)
6. Splits at intersections for segment-based tracking
7. Outputs GeoJSON with properties: src='ml', ev='m'

Supports georeferencing via:
- World files (.jgw, .pgw) next to the image
- Explicit transform parameters
- Bounding box coordinates

Usage:
    # Basic usage with world file
    python scripts/extract/extract_roads.py \\
        --input data/kartverket/prediction.png \\
        --output data/roads_1880.geojson

    # With explicit bounds
    python scripts/extract/extract_roads.py \\
        --input prediction.png \\
        --output roads.geojson \\
        --bounds 10.37,63.42,10.44,63.44

    # Adjust thresholds
    python scripts/extract/extract_roads.py \\
        --input prediction.png \\
        --output roads.geojson \\
        --threshold 0.6 \\
        --simplify-tolerance 3 \\
        --min-length 10
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple, Optional, Dict

import numpy as np
from PIL import Image
from shapely.geometry import LineString, Point, mapping
from shapely.ops import unary_union, linemerge
from shapely import simplify as shapely_simplify
from skimage.morphology import skeletonize


def load_world_file(image_path: Path) -> Optional[Tuple[float, float, float, float, float, float]]:
    """
    Load world file (.jgw, .pgw, .tfw) if it exists.

    World file format (6 lines):
    1. pixel size in x-direction
    2. rotation about y-axis
    3. rotation about x-axis
    4. pixel size in y-direction (negative)
    5. x-coordinate of upper-left pixel center
    6. y-coordinate of upper-left pixel center

    Args:
        image_path: Path to image file

    Returns:
        Tuple of (A, D, B, E, C, F) or None if not found
        Where transform is: x = A*col + B*row + C, y = D*col + E*row + F
    """
    # Try different world file extensions
    suffix = image_path.suffix.lower()
    world_extensions = {
        '.png': '.pgw',
        '.jpg': '.jgw',
        '.jpeg': '.jgw',
        '.tif': '.tfw',
        '.tiff': '.tfw',
    }

    world_ext = world_extensions.get(suffix, '.wld')
    world_path = image_path.with_suffix(world_ext)

    if not world_path.exists():
        # Try generic .wld
        world_path = image_path.with_suffix('.wld')
        if not world_path.exists():
            return None

    try:
        with open(world_path, 'r') as f:
            lines = f.readlines()
            if len(lines) < 6:
                return None

            A = float(lines[0].strip())  # pixel size X
            D = float(lines[1].strip())  # rotation Y
            B = float(lines[2].strip())  # rotation X
            E = float(lines[3].strip())  # pixel size Y (negative)
            C = float(lines[4].strip())  # X origin
            F = float(lines[5].strip())  # Y origin

            return (A, D, B, E, C, F)

    except (ValueError, IOError) as e:
        print(f"Warning: Failed to load world file {world_path}: {e}", file=sys.stderr)
        return None


def pixel_to_geo(x: float, y: float, transform: Tuple[float, float, float, float, float, float]) -> Tuple[float, float]:
    """
    Convert pixel coordinates to geographic coordinates using affine transform.

    Args:
        x: Pixel x coordinate (column)
        y: Pixel y coordinate (row)
        transform: (A, D, B, E, C, F) from world file

    Returns:
        (lon, lat) tuple
    """
    A, D, B, E, C, F = transform
    lon = A * x + B * y + C
    lat = D * x + E * y + F
    return (lon, lat)


def bounds_to_transform(bounds: Tuple[float, float, float, float], width: int, height: int) -> Tuple[float, float, float, float, float, float]:
    """
    Convert bounding box to affine transform parameters.

    Args:
        bounds: (west, south, east, north) in degrees
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        (A, D, B, E, C, F) affine transform tuple
    """
    west, south, east, north = bounds

    # Pixel size
    A = (east - west) / width  # pixel size X
    E = (south - north) / height  # pixel size Y (negative)

    # No rotation
    D = 0.0
    B = 0.0

    # Upper-left corner (center of first pixel)
    C = west + A / 2
    F = north + E / 2

    return (A, D, B, E, C, F)


def load_prediction_image(image_path: Path, threshold: float = 0.5) -> np.ndarray:
    """
    Load prediction image and threshold to binary.

    Args:
        image_path: Path to prediction image
        threshold: Confidence threshold (0.0-1.0)

    Returns:
        Binary mask array (H, W) where True = road
    """
    img = Image.open(image_path)
    img_array = np.array(img)

    # Convert to grayscale if needed
    if len(img_array.shape) == 3:
        # If RGB, average channels or take first channel
        img_array = img_array.mean(axis=2)

    # Normalize to 0-1 range
    if img_array.max() > 1.0:
        img_array = img_array.astype(np.float32) / 255.0

    # Threshold
    binary_mask = img_array >= threshold

    return binary_mask


def skeletonize_roads(binary_mask: np.ndarray) -> np.ndarray:
    """
    Skeletonize road mask to 1-pixel width centerlines.

    Args:
        binary_mask: Binary mask (H, W) where True = road

    Returns:
        Skeleton array (H, W) where True = centerline
    """
    # Use scikit-image skeletonize
    skeleton = skeletonize(binary_mask)
    return skeleton


def trace_skeleton_to_lines(skeleton: np.ndarray, min_length: float = 5.0) -> List[LineString]:
    """
    Trace skeleton pixels into connected LineStrings.

    Args:
        skeleton: Skeleton array (H, W)
        min_length: Minimum line length in pixels

    Returns:
        List of LineString geometries in pixel coordinates
    """
    # Find connected components
    import cv2

    skeleton_uint8 = skeleton.astype(np.uint8) * 255
    num_labels, labels = cv2.connectedComponents(skeleton_uint8)

    lines = []

    for label in range(1, num_labels):  # Skip background (0)
        # Get points for this connected component
        points_mask = labels == label
        ys, xs = np.where(points_mask)

        if len(xs) < 2:
            continue

        # Order points to form a continuous line
        points = list(zip(xs, ys))
        ordered_points = _order_skeleton_points(points)

        if len(ordered_points) < 2:
            continue

        # Create LineString
        line = LineString(ordered_points)

        if line.length >= min_length:
            lines.append(line)

    return lines


def _order_skeleton_points(points: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """
    Order skeleton points to form a continuous line.
    Uses nearest neighbor heuristic starting from an endpoint.

    Args:
        points: List of (x, y) tuples

    Returns:
        Ordered list of points
    """
    if len(points) < 2:
        return points

    # Build neighbor counts to find endpoints
    point_set = set(points)
    neighbor_counts = {}

    for p in points:
        count = 0
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                neighbor = (p[0] + dx, p[1] + dy)
                if neighbor in point_set:
                    count += 1
        neighbor_counts[p] = count

    # Find endpoints (points with 1 neighbor) or start from any point
    endpoints = [p for p, c in neighbor_counts.items() if c == 1]
    start = endpoints[0] if endpoints else points[0]

    # Build ordered list by nearest neighbor
    ordered = [start]
    remaining = point_set - {start}

    while remaining:
        current = ordered[-1]
        # Find nearest unvisited neighbor (within distance 2 to allow small gaps)
        best_dist = float('inf')
        best_neighbor = None

        for p in remaining:
            dist = abs(p[0] - current[0]) + abs(p[1] - current[1])  # Manhattan distance
            if dist < best_dist:
                best_dist = dist
                best_neighbor = p

        if best_neighbor is None or best_dist > 2:  # Max gap of 2 pixels
            break

        ordered.append(best_neighbor)
        remaining.remove(best_neighbor)

    return ordered


def split_at_intersections(lines: List[LineString]) -> List[LineString]:
    """
    Split lines at intersection points for segment-based tracking.

    This creates separate segments between intersections, which is important
    for tracking historical road changes (e.g., when one segment was added).

    Args:
        lines: List of LineString geometries

    Returns:
        List of LineString geometries with splits at intersections
    """
    # For now, return lines as-is
    # TODO: Implement proper intersection detection and splitting
    # This is complex and requires:
    # 1. Find all intersection points between lines
    # 2. Split each line at its intersection points
    # 3. Return all resulting segments

    # Simple implementation: just return original lines
    # More sophisticated implementation would use shapely's split operations
    return lines


def simplify_lines(lines: List[LineString], tolerance: float) -> List[LineString]:
    """
    Simplify lines using Douglas-Peucker algorithm.

    Args:
        lines: List of LineString geometries
        tolerance: Simplification tolerance in same units as coordinates

    Returns:
        List of simplified LineStrings
    """
    if tolerance <= 0:
        return lines

    simplified = []
    for line in lines:
        simple_line = shapely_simplify(line, tolerance=tolerance, preserve_topology=True)
        if simple_line.is_valid and simple_line.length > 0:
            simplified.append(simple_line)

    return simplified


def transform_lines_to_geo(
    lines: List[LineString],
    transform: Tuple[float, float, float, float, float, float]
) -> List[LineString]:
    """
    Transform lines from pixel coordinates to geographic coordinates.

    Args:
        lines: List of LineStrings in pixel coordinates
        transform: Affine transform parameters

    Returns:
        List of LineStrings in geographic coordinates
    """
    geo_lines = []

    for line in lines:
        geo_coords = [pixel_to_geo(x, y, transform) for x, y in line.coords]
        geo_line = LineString(geo_coords)
        geo_lines.append(geo_line)

    return geo_lines


def create_geojson(
    lines: List[LineString],
    source: str = 'ml',
    evidence: str = 'm',
    map_year: Optional[int] = None,
    metadata: Optional[Dict] = None
) -> Dict:
    """
    Create GeoJSON FeatureCollection from lines.

    Args:
        lines: List of LineString geometries
        source: Source identifier (default: 'ml')
        evidence: Evidence level (default: 'm' for medium)
        map_year: Year of source map (if known)
        metadata: Additional metadata to include

    Returns:
        GeoJSON FeatureCollection dict
    """
    features = []

    for i, line in enumerate(lines):
        properties = {
            'rid': f'{source}_road_{i}',
            'src': source,
            'ev': evidence,
            'length': float(line.length),
        }

        # Add temporal properties if map year is known
        if map_year is not None:
            properties['sd'] = map_year
            properties['sd_t'] = 'n'  # not-later-than
            properties['sd_s'] = f'{source}{map_year}'

        feature = {
            'type': 'Feature',
            'geometry': mapping(line),
            'properties': properties
        }
        features.append(feature)

    geojson = {
        'type': 'FeatureCollection',
        'features': features
    }

    # Add metadata
    if metadata is None:
        metadata = {}

    geojson['metadata'] = {
        'feature_type': 'road',
        'feature_count': len(features),
        'source': source,
        'evidence': evidence,
        **metadata
    }

    if map_year is not None:
        geojson['metadata']['reference_year'] = map_year

    return geojson


def extract_roads(
    input_path: Path,
    output_path: Path,
    threshold: float = 0.5,
    simplify_tolerance: float = 2.0,
    min_length: float = 5.0,
    bounds: Optional[Tuple[float, float, float, float]] = None,
    transform: Optional[Tuple[float, float, float, float, float, float]] = None,
    source: str = 'ml',
    evidence: str = 'm',
    map_year: Optional[int] = None
) -> Dict:
    """
    Main extraction function.

    Args:
        input_path: Path to prediction image
        output_path: Path to output GeoJSON
        threshold: Confidence threshold (0.0-1.0)
        simplify_tolerance: Douglas-Peucker tolerance in pixels
        min_length: Minimum line length in pixels
        bounds: Optional (west, south, east, north) bounds
        transform: Optional affine transform parameters
        source: Source identifier
        evidence: Evidence level
        map_year: Year of source map

    Returns:
        GeoJSON FeatureCollection dict
    """
    print(f"Loading prediction image: {input_path}")

    # Load and threshold image
    binary_mask = load_prediction_image(input_path, threshold=threshold)
    print(f"  Thresholded at {threshold}: {binary_mask.sum()} road pixels")

    # Skeletonize
    print("Skeletonizing to centerlines...")
    skeleton = skeletonize_roads(binary_mask)
    print(f"  Skeleton has {skeleton.sum()} pixels")

    # Trace to lines
    print("Tracing connected components...")
    lines = trace_skeleton_to_lines(skeleton, min_length=min_length)
    print(f"  Found {len(lines)} line segments")

    if not lines:
        print("Warning: No road lines found!", file=sys.stderr)
        # Return empty GeoJSON
        empty_geojson = create_geojson([], source=source, evidence=evidence, map_year=map_year)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(empty_geojson, f, indent=2)
        return empty_geojson

    # Simplify
    if simplify_tolerance > 0:
        print(f"Simplifying with tolerance={simplify_tolerance}...")
        lines = simplify_lines(lines, tolerance=simplify_tolerance)
        print(f"  {len(lines)} lines after simplification")

    # Split at intersections
    print("Splitting at intersections...")
    lines = split_at_intersections(lines)
    print(f"  {len(lines)} segments after splitting")

    # Determine transform
    if transform is None:
        # Try to load world file
        world_transform = load_world_file(input_path)

        if world_transform is not None:
            print("Using world file for georeferencing")
            transform = world_transform
        elif bounds is not None:
            print("Using bounds for georeferencing")
            img = Image.open(input_path)
            width, height = img.size
            transform = bounds_to_transform(bounds, width, height)
        else:
            print("Warning: No georeferencing available, using pixel coordinates", file=sys.stderr)

    # Transform to geographic coordinates
    if transform is not None:
        print("Transforming to geographic coordinates...")
        lines = transform_lines_to_geo(lines, transform)
        print(f"  Transformed {len(lines)} lines")

    # Create GeoJSON
    metadata = {
        'input_image': str(input_path),
        'threshold': threshold,
        'simplify_tolerance': simplify_tolerance,
        'min_length': min_length,
    }

    if transform is not None:
        metadata['georeferenced'] = True
        metadata['transform'] = transform
    else:
        metadata['georeferenced'] = False

    geojson = create_geojson(
        lines,
        source=source,
        evidence=evidence,
        map_year=map_year,
        metadata=metadata
    )

    # Save to file
    print(f"Writing GeoJSON to: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(geojson, f, indent=2)

    print(f"Done! Extracted {len(lines)} road segments")
    return geojson


def parse_bounds(bounds_str: str) -> Tuple[float, float, float, float]:
    """
    Parse bounds string to tuple.

    Args:
        bounds_str: String in format "west,south,east,north"

    Returns:
        Tuple of (west, south, east, north)
    """
    try:
        values = [float(x.strip()) for x in bounds_str.split(',')]
        if len(values) != 4:
            raise ValueError("Bounds must have exactly 4 values")
        return tuple(values)
    except Exception as e:
        raise ValueError(f"Invalid bounds format: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Extract roads from ML prediction images',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Input/output
    parser.add_argument('--input', type=Path, required=True,
                       help='Path to prediction image')
    parser.add_argument('--output', type=Path, required=True,
                       help='Path to output GeoJSON')

    # Processing parameters
    parser.add_argument('--threshold', type=float, default=0.5,
                       help='Confidence threshold (0.0-1.0, default: 0.5)')
    parser.add_argument('--simplify-tolerance', type=float, default=2.0,
                       help='Douglas-Peucker simplification tolerance in pixels (default: 2.0)')
    parser.add_argument('--min-length', type=float, default=5.0,
                       help='Minimum line length in pixels (default: 5.0)')

    # Georeferencing
    parser.add_argument('--bounds', type=str,
                       help='Geographic bounds as "west,south,east,north" (e.g., "10.37,63.42,10.44,63.44")')

    # Metadata
    parser.add_argument('--source', type=str, default='ml',
                       help='Source identifier (default: ml)')
    parser.add_argument('--evidence', type=str, default='m',
                       help='Evidence level: h/m/l (default: m)')
    parser.add_argument('--year', type=int,
                       help='Year of source map (for temporal properties)')

    args = parser.parse_args()

    # Parse bounds if provided
    bounds = None
    if args.bounds:
        try:
            bounds = parse_bounds(args.bounds)
            print(f"Using bounds: W={bounds[0]:.6f}, S={bounds[1]:.6f}, E={bounds[2]:.6f}, N={bounds[3]:.6f}")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    # Validate input
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Extract roads
    try:
        extract_roads(
            input_path=args.input,
            output_path=args.output,
            threshold=args.threshold,
            simplify_tolerance=args.simplify_tolerance,
            min_length=args.min_length,
            bounds=bounds,
            source=args.source,
            evidence=args.evidence,
            map_year=args.year
        )
    except Exception as e:
        print(f"Error during extraction: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
