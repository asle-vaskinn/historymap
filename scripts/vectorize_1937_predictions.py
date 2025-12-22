#!/usr/bin/env python3
"""
Vectorize 1937 aerial photo predictions to GeoJSON.

Uses tile metadata for geo-referencing.

Usage:
    python scripts/vectorize_1937_predictions.py
"""

import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from shapely.geometry import Polygon, mapping
from shapely.ops import unary_union

# Paths
PREDICTIONS_DIR = Path("data/sources/ml_detected/ortofoto1937/predictions")
METADATA_DIR = Path("data/training_1937/metadata")
OUTPUT_PATH = Path("data/sources/ml_detected/ortofoto1937/buildings.geojson")


def load_mask(mask_path: Path) -> np.ndarray:
    """Load segmentation mask."""
    mask_image = Image.open(mask_path)
    mask = np.array(mask_image)
    if len(mask.shape) == 3:
        mask = mask[:, :, 0]
    return mask


def extract_contours(mask: np.ndarray, class_id: int = 1) -> list:
    """Extract contours for building class."""
    binary_mask = (mask == class_id).astype(np.uint8) * 255
    contours, _ = cv2.findContours(
        binary_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )
    return contours


def contour_to_polygon(contour: np.ndarray, min_area: float = 10.0):
    """Convert OpenCV contour to Shapely polygon."""
    if len(contour) < 3:
        return None

    points = contour.squeeze()
    if len(points.shape) != 2 or points.shape[0] < 3:
        return None

    polygon = Polygon(points)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
        # buffer(0) might return MultiPolygon - get largest
        if hasattr(polygon, 'geoms'):
            polygon = max(polygon.geoms, key=lambda p: p.area, default=None)
            if polygon is None:
                return None

    if polygon.is_empty or polygon.area < min_area:
        return None

    return polygon


def pixel_to_geo(x: float, y: float, mask_shape: tuple, bounds: dict) -> tuple:
    """Convert pixel coordinates to geographic coordinates."""
    height, width = mask_shape

    # Normalize to 0-1
    norm_x = x / width
    norm_y = y / height

    # Convert to geo (note: y is inverted)
    lon = bounds['west'] + norm_x * (bounds['east'] - bounds['west'])
    lat = bounds['north'] - norm_y * (bounds['north'] - bounds['south'])

    return (lon, lat)


def transform_polygon(polygon: Polygon, mask_shape: tuple, bounds: dict) -> Polygon:
    """Transform polygon from pixel to geo coordinates."""
    geo_coords = [
        pixel_to_geo(x, y, mask_shape, bounds)
        for x, y in polygon.exterior.coords
    ]
    return Polygon(geo_coords)


def vectorize_tile(pred_path: Path, meta_path: Path, min_area_m2: float = 20.0) -> list:
    """Vectorize a single tile prediction."""
    # Load mask
    mask = load_mask(pred_path)
    mask_shape = mask.shape

    # Load metadata
    with open(meta_path) as f:
        meta = json.load(f)
    bounds = meta['bounds']

    # Calculate approximate pixel size in meters
    # At 63.43° latitude, 1° lon ≈ 49km, 1° lat ≈ 111km
    lat_center = (bounds['north'] + bounds['south']) / 2
    import math
    meters_per_deg_lon = 111320 * math.cos(math.radians(lat_center))
    meters_per_deg_lat = 111320

    tile_width_m = (bounds['east'] - bounds['west']) * meters_per_deg_lon
    tile_height_m = (bounds['north'] - bounds['south']) * meters_per_deg_lat

    pixel_size_m = (tile_width_m / mask_shape[1] + tile_height_m / mask_shape[0]) / 2
    min_area_px = min_area_m2 / (pixel_size_m ** 2)

    # Extract building contours
    contours = extract_contours(mask, class_id=1)

    features = []
    for contour in contours:
        polygon = contour_to_polygon(contour, min_area=min_area_px)
        if polygon is None:
            continue

        # Transform to geo coordinates
        geo_polygon = transform_polygon(polygon, mask_shape, bounds)

        # Simplify (tolerance in degrees, ~1m at this latitude)
        simplify_tol = 1.0 / meters_per_deg_lon
        geo_polygon = geo_polygon.simplify(simplify_tol)

        if geo_polygon.is_empty:
            continue

        features.append({
            "type": "Feature",
            "geometry": mapping(geo_polygon),
            "properties": {
                "src": "ml",
                "sd": 1937,
                "ed": None,
                "ev": "l",  # low confidence (pseudo-labels)
                "mlc": 0.5,  # placeholder confidence
                "tile": meta['tile_name']
            }
        })

    return features


def main():
    # Ensure output directory exists
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Find all predictions
    pred_files = sorted(PREDICTIONS_DIR.glob("tile_*.png"))

    if not pred_files:
        print(f"No predictions found in {PREDICTIONS_DIR}")
        return

    print(f"Vectorizing {len(pred_files)} prediction tiles...")

    all_features = []
    for pred_path in pred_files:
        # Find corresponding metadata (strip _mask suffix)
        tile_name = pred_path.stem.replace("_mask", "")
        meta_path = METADATA_DIR / f"{tile_name}.json"

        if not meta_path.exists():
            print(f"  Warning: No metadata for {tile_name}, skipping")
            continue

        features = vectorize_tile(pred_path, meta_path)
        all_features.extend(features)
        print(f"  {tile_name}: {len(features)} buildings")

    # Create GeoJSON
    geojson = {
        "type": "FeatureCollection",
        "features": all_features,
        "metadata": {
            "source": "ML detection from 1937 aerial photos",
            "model": "U-Net ResNet18",
            "training_data": "OSM pseudo-labels",
            "count": len(all_features)
        }
    }

    # Save
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(geojson, f)

    print(f"\nSaved {len(all_features)} buildings to {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
