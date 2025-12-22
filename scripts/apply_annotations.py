#!/usr/bin/env python3
"""
Apply human annotations to improve ML training data.

Takes annotation JSON (from source viewer export) and updates training masks
to correct the ML predictions.

Usage:
    python scripts/apply_annotations.py --annotations data/annotations/annotations_1937.json

This script:
1. Loads the annotation file
2. For each annotated building, finds the corresponding training tile(s)
3. Updates the mask to add/remove the building polygon
4. Saves updated masks for retraining
"""

import argparse
import json
import ssl
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from shapely.geometry import Polygon

# Paths
TRAINING_DIR = Path("data/training_1937")
PREDICTIONS_DIR = Path("data/sources/ml_detected/ortofoto1937/predictions")
METADATA_DIR = Path("data/training_1937/metadata")
CORRECTED_DIR = Path("data/training_1937_corrected")

# Area bounds
AREA_BOUNDS = {
    'west': 10.38,
    'south': 63.42,
    'east': 10.44,
    'north': 63.44
}

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


def fetch_building_geometry(osm_id: int, max_retries: int = 3) -> list:
    """Fetch building geometry from OSM with retry logic."""
    query = f"""
    [out:json][timeout:120];
    way({osm_id});
    out body;
    >;
    out skel qt;
    """

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                OVERPASS_URL,
                data=query.encode('utf-8'),
                headers={'Content-Type': 'text/plain'}
            )

            with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as response:
                data = json.loads(response.read().decode('utf-8'))

            # Build node lookup
            nodes = {}
            for el in data.get('elements', []):
                if el.get('type') == 'node':
                    nodes[el['id']] = (el['lon'], el['lat'])

            # Extract building coords
            for el in data.get('elements', []):
                if el.get('type') == 'way':
                    coords = []
                    for node_id in el.get('nodes', []):
                        if node_id in nodes:
                            coords.append(nodes[node_id])
                    return coords

            return []

        except Exception as e:
            wait_time = 2 ** attempt * 5  # 5, 10, 20 seconds
            print(f"    Attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                print(f"    Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                print(f"    All retries failed for building {osm_id}")
                return []

    return []


def find_tiles_for_building(coords: list, tiles_meta: list) -> list:
    """Find which tiles contain this building."""
    if not coords:
        return []

    # Calculate building centroid
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    centroid = (sum(lons) / len(lons), sum(lats) / len(lats))

    matching_tiles = []
    for tile in tiles_meta:
        bounds = tile['bounds']
        if (bounds['west'] <= centroid[0] <= bounds['east'] and
            bounds['south'] <= centroid[1] <= bounds['north']):
            matching_tiles.append(tile)

    return matching_tiles


def geo_to_pixel(lon: float, lat: float, bounds: dict, mask_shape: tuple) -> tuple:
    """Convert geographic coordinates to pixel coordinates."""
    height, width = mask_shape
    x = int((lon - bounds['west']) / (bounds['east'] - bounds['west']) * width)
    y = int((bounds['north'] - lat) / (bounds['north'] - bounds['south']) * height)
    return (x, y)


def update_mask(mask: np.ndarray, coords: list, bounds: dict, existed: bool) -> np.ndarray:
    """Update mask to add or remove a building polygon."""
    if not coords:
        return mask

    mask_shape = mask.shape

    # Convert coords to pixels
    pixel_coords = []
    for lon, lat in coords:
        px, py = geo_to_pixel(lon, lat, bounds, mask_shape)
        px = max(0, min(px, mask_shape[1] - 1))
        py = max(0, min(py, mask_shape[0] - 1))
        pixel_coords.append((px, py))

    if len(pixel_coords) < 3:
        return mask

    pts = np.array(pixel_coords, dtype=np.int32)

    if existed:
        # Add building (fill with 1)
        cv2.fillPoly(mask, [pts], 1)
    else:
        # Remove building (fill with 0)
        cv2.fillPoly(mask, [pts], 0)

    return mask


def load_tiles_metadata() -> list:
    """Load metadata for all training tiles."""
    tiles = []
    for meta_path in sorted(METADATA_DIR.glob("tile_*.json")):
        with open(meta_path) as f:
            meta = json.load(f)
            meta['meta_path'] = meta_path
            tiles.append(meta)
    return tiles


def main():
    parser = argparse.ArgumentParser(description='Apply annotations to training data')
    parser.add_argument('--annotations', type=str, required=True,
                        help='Path to annotations JSON file')
    parser.add_argument('--output', type=str, default=str(CORRECTED_DIR),
                        help='Output directory for corrected masks')
    args = parser.parse_args()

    # Load annotations
    with open(args.annotations) as f:
        data = json.load(f)

    annotations = data.get('annotations', [])
    print(f"Loaded {len(annotations)} annotations")

    if not annotations:
        print("No annotations to apply")
        return

    # Create output directory
    output_dir = Path(args.output)
    (output_dir / "images").mkdir(parents=True, exist_ok=True)
    (output_dir / "masks").mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata").mkdir(parents=True, exist_ok=True)

    # Load tile metadata
    tiles_meta = load_tiles_metadata()
    print(f"Found {len(tiles_meta)} training tiles")

    # Track which tiles need updating
    tiles_to_update = {}  # tile_name -> list of (coords, existed)

    # Fetch geometries and map to tiles
    print("\nFetching building geometries...")
    for i, ann in enumerate(annotations):
        osm_id = ann['osm_id']
        existed = ann['existed']

        print(f"  [{i+1}/{len(annotations)}] Building {osm_id}: {'existed' if existed else 'did not exist'}")

        # Rate limit - be polite to Overpass API
        time.sleep(2.0)

        coords = fetch_building_geometry(osm_id)
        if not coords:
            print(f"    Warning: Could not fetch geometry for {osm_id}")
            continue

        # Find tiles
        matching_tiles = find_tiles_for_building(coords, tiles_meta)
        if not matching_tiles:
            print(f"    Warning: Building {osm_id} not in any training tile")
            continue

        for tile in matching_tiles:
            tile_name = tile['tile_name']
            if tile_name not in tiles_to_update:
                tiles_to_update[tile_name] = []
            tiles_to_update[tile_name].append((coords, existed))
            print(f"    Found in tile {tile_name}")

    print(f"\nUpdating {len(tiles_to_update)} tiles...")

    # Update each tile
    for tile_name, updates in tiles_to_update.items():
        # Load original mask
        original_mask_path = TRAINING_DIR / "masks" / f"{tile_name}.png"
        if not original_mask_path.exists():
            print(f"  Warning: Original mask not found for {tile_name}")
            continue

        mask = np.array(Image.open(original_mask_path))
        if len(mask.shape) == 3:
            mask = mask[:, :, 0]

        # Load metadata for bounds
        meta_path = METADATA_DIR / f"{tile_name}.json"
        with open(meta_path) as f:
            meta = json.load(f)
        bounds = meta['bounds']

        # Apply each update
        for coords, existed in updates:
            mask = update_mask(mask, coords, bounds, existed)

        # Save corrected mask
        corrected_mask = Image.fromarray(mask.astype(np.uint8))
        corrected_mask.save(output_dir / "masks" / f"{tile_name}.png")

        # Copy original image
        original_img_path = TRAINING_DIR / "images" / f"{tile_name}.png"
        if original_img_path.exists():
            import shutil
            shutil.copy(original_img_path, output_dir / "images" / f"{tile_name}.png")

        # Copy metadata
        shutil.copy(meta_path, output_dir / "metadata" / f"{tile_name}.json")

        print(f"  Updated {tile_name} with {len(updates)} corrections")

    print(f"\nDone! Corrected training data saved to {output_dir}")
    print("\nTo retrain with corrected data:")
    print(f"  1. Update ml/config_1937.yaml: data_dir: ../{output_dir}")
    print("  2. Run: python ml/train.py --config ml/config_1937.yaml")


if __name__ == '__main__':
    main()
