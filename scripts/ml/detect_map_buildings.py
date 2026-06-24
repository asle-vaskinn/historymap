#!/usr/bin/env python3
"""
Detect buildings on historical maps using image processing.

This uses traditional CV techniques rather than ML since:
1. Historical maps have different visual styles than training data
2. Buildings on old maps are often marked with distinct colors/patterns

The approach:
1. Detect building-like shapes on 1904 map using color/edge detection
2. Match detected shapes to OSM buildings using geometric similarity
3. Buildings that match = confirmed historical buildings
4. Buildings only in 1904 = potentially demolished

Usage:
    python scripts/ml/detect_map_buildings.py --input data/training_matched_1904/images --output data/detected_1904
"""

import argparse
import json
from pathlib import Path
from typing import List, Tuple, Dict, Optional

import numpy as np
from PIL import Image

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from shapely.geometry import shape, box, Polygon, mapping
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


def detect_buildings_color(image: np.ndarray) -> np.ndarray:
    """
    Detect building-like regions using color segmentation.

    On the Amtskart 1904, buildings are typically shown as red/brown shapes.
    """
    # Convert to HSV for better color detection
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

    # Buildings on Amtskart are typically red/brown
    # Red in HSV: H=0-10 or H=170-180, S=50-255, V=50-255

    # Lower red range
    lower_red1 = np.array([0, 30, 50])
    upper_red1 = np.array([10, 255, 200])
    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)

    # Upper red range
    lower_red2 = np.array([160, 30, 50])
    upper_red2 = np.array([180, 255, 200])
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)

    # Orange/brown range (some buildings)
    lower_orange = np.array([10, 30, 50])
    upper_orange = np.array([25, 255, 200])
    mask3 = cv2.inRange(hsv, lower_orange, upper_orange)

    # Combine masks
    mask = mask1 | mask2 | mask3

    # Clean up with morphology
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    return mask


def detect_buildings_edges(image: np.ndarray) -> np.ndarray:
    """
    Detect building-like regions using edge detection.

    Buildings typically have clear rectangular edges.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    # Detect edges
    edges = cv2.Canny(gray, 50, 150)

    # Dilate to connect nearby edges
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(edges, kernel, iterations=2)

    # Find contours and fill
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    mask = np.zeros_like(gray)
    for contour in contours:
        area = cv2.contourArea(contour)
        if 100 < area < 50000:  # Filter by area (reasonable building size in pixels)
            # Check if roughly rectangular
            rect = cv2.minAreaRect(contour)
            box_area = rect[1][0] * rect[1][1]
            if box_area > 0:
                rectangularity = area / box_area
                if rectangularity > 0.5:  # At least 50% rectangular
                    cv2.drawContours(mask, [contour], -1, 255, -1)

    return mask


def extract_building_polygons(
    mask: np.ndarray,
    tile_bounds: Tuple[float, float, float, float],
    min_area_px: int = 50,
    simplify_tolerance: float = 2.0
) -> List[Dict]:
    """
    Extract building polygons from detection mask.

    Args:
        mask: Binary mask (255 = building)
        tile_bounds: (west, south, east, north) geographic bounds
        min_area_px: Minimum building area in pixels
        simplify_tolerance: Tolerance for polygon simplification

    Returns:
        List of GeoJSON feature dicts
    """
    if not HAS_SHAPELY:
        return []

    west, south, east, north = tile_bounds
    height, width = mask.shape

    # Coordinate transform
    px_to_lon = (east - west) / width
    px_to_lat = (north - south) / height

    # Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    features = []
    for contour in contours:
        if cv2.contourArea(contour) < min_area_px:
            continue

        # Simplify contour
        epsilon = simplify_tolerance
        approx = cv2.approxPolyDP(contour, epsilon, True)

        if len(approx) < 3:
            continue

        # Convert pixel coords to geographic
        coords = []
        for point in approx:
            px, py = point[0]
            lon = west + px * px_to_lon
            lat = north - py * px_to_lat  # Flip Y axis
            coords.append((lon, lat))

        # Close the polygon
        coords.append(coords[0])

        try:
            polygon = Polygon(coords)
            if polygon.is_valid and polygon.area > 0:
                features.append({
                    'type': 'Feature',
                    'geometry': mapping(polygon),
                    'properties': {
                        'source': 'cv_detection',
                        'area_m2': polygon.area * 111000 * 111000 * np.cos(np.radians(south)),  # Rough m² estimate
                    }
                })
        except Exception:
            continue

    return features


def process_tile(
    image_path: Path,
    tile_bounds: Tuple[float, float, float, float],
    method: str = 'color'
) -> Tuple[np.ndarray, List[Dict]]:
    """
    Process a single tile to detect buildings.

    Args:
        image_path: Path to tile image
        tile_bounds: Geographic bounds
        method: Detection method ('color', 'edge', 'combined')

    Returns:
        Tuple of (detection mask, list of feature dicts)
    """
    image = np.array(Image.open(image_path).convert('RGB'))

    if method == 'color':
        mask = detect_buildings_color(image)
    elif method == 'edge':
        mask = detect_buildings_edges(image)
    else:  # combined
        color_mask = detect_buildings_color(image)
        edge_mask = detect_buildings_edges(image)
        # Use intersection of both methods for higher precision
        mask = color_mask & edge_mask

    features = extract_building_polygons(mask, tile_bounds)

    return mask, features


def main():
    parser = argparse.ArgumentParser(description='Detect buildings on historical maps')
    parser.add_argument('--input', '-i', type=Path, required=True,
                        help='Input directory with tile images')
    parser.add_argument('--output', '-o', type=Path, required=True,
                        help='Output directory')
    parser.add_argument('--metadata', '-m', type=Path, default=None,
                        help='Path to metadata.json with tile bounds (optional)')
    parser.add_argument('--method', choices=['color', 'edge', 'combined'],
                        default='color', help='Detection method')
    parser.add_argument('--save-masks', action='store_true',
                        help='Save detection masks')

    args = parser.parse_args()

    if not HAS_CV2:
        print("Error: OpenCV required. pip install opencv-python")
        return 1

    if not HAS_SHAPELY:
        print("Error: Shapely required. pip install shapely")
        return 1

    args.output.mkdir(parents=True, exist_ok=True)

    # Load metadata for tile bounds
    tile_metadata = {}
    if args.metadata:
        with open(args.metadata) as f:
            data = json.load(f)
            for tile in data.get('tiles', []):
                tile_id = tile['id']
                b = tile['bounds']
                tile_metadata[tile_id] = (b['west'], b['south'], b['east'], b['north'])
    else:
        # Try to find metadata in parent directory
        meta_path = args.input.parent / 'metadata.json'
        if meta_path.exists():
            with open(meta_path) as f:
                data = json.load(f)
                for tile in data.get('tiles', []):
                    tile_id = tile['id']
                    b = tile['bounds']
                    tile_metadata[tile_id] = (b['west'], b['south'], b['east'], b['north'])

    # Process tiles
    image_files = sorted(args.input.glob('*.png'))
    print(f"Processing {len(image_files)} tiles with method: {args.method}")

    all_features = []

    for img_path in image_files:
        tile_id = img_path.stem.replace('_mask', '')

        # Get tile bounds
        if tile_id in tile_metadata:
            bounds = tile_metadata[tile_id]
        else:
            # Default bounds (approximate for Trondheim downtown)
            print(f"  Warning: No bounds for {tile_id}, using default")
            bounds = (10.38, 63.42, 10.42, 63.46)

        mask, features = process_tile(img_path, bounds, args.method)

        print(f"  {tile_id}: {len(features)} buildings detected")

        # Add tile ID to features
        for f in features:
            f['properties']['tile_id'] = tile_id

        all_features.extend(features)

        if args.save_masks:
            mask_path = args.output / f"{tile_id}_detected.png"
            Image.fromarray(mask).save(mask_path)

    # Save GeoJSON
    geojson = {
        'type': 'FeatureCollection',
        'features': all_features
    }

    output_path = args.output / 'detected_buildings.geojson'
    with open(output_path, 'w') as f:
        json.dump(geojson, f, indent=2)

    print(f"\n{'='*60}")
    print(f"DETECTION COMPLETE")
    print(f"{'='*60}")
    print(f"Total buildings detected: {len(all_features)}")
    print(f"Output: {output_path}")

    return 0


if __name__ == '__main__':
    exit(main())
