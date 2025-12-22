#!/usr/bin/env python3
"""
Verify modern OSM buildings against 1937 aerial photo predictions.

For each modern building, check if it appears in the 1937 ML predictions.

Output colors:
- Green (verified_there): Building clearly visible in 1937
- Yellow (unsure): Unclear or partial match
- Red (verified_not_there): Building NOT in 1937 (built after 1937)

Usage:
    python scripts/verify_1937_buildings.py
"""

import json
import math
import ssl
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from shapely.geometry import shape, box, mapping
from shapely.ops import unary_union

# Paths
PREDICTIONS_DIR = Path("data/sources/ml_detected/ortofoto1937/predictions")
METADATA_DIR = Path("data/training_1937/metadata")
OUTPUT_PATH = Path("data/sources/ml_detected/ortofoto1937/verified_buildings.geojson")

# Area bounds (same as training data)
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


def fetch_osm_buildings(bounds: dict, retries: int = 3) -> list:
    """Fetch all OSM buildings in the area."""
    query = f"""
    [out:json][timeout:180];
    (
      way["building"]({bounds['south']},{bounds['west']},{bounds['north']},{bounds['east']});
      relation["building"]({bounds['south']},{bounds['west']},{bounds['north']},{bounds['east']});
    );
    out body;
    >;
    out skel qt;
    """

    print("Fetching OSM buildings...")

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                OVERPASS_URL,
                data=query.encode('utf-8'),
                headers={'Content-Type': 'text/plain'}
            )
            with urllib.request.urlopen(req, timeout=180, context=SSL_CONTEXT) as response:
                data = json.loads(response.read().decode('utf-8'))
                break
        except Exception as e:
            print(f"  Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(10)
            else:
                raise

    # Build node lookup
    nodes = {}
    for el in data.get('elements', []):
        if el.get('type') == 'node':
            nodes[el['id']] = (el['lon'], el['lat'])

    # Extract building polygons
    buildings = []
    for el in data.get('elements', []):
        if el.get('type') == 'way' and 'building' in el.get('tags', {}):
            coords = []
            for node_id in el.get('nodes', []):
                if node_id in nodes:
                    coords.append(nodes[node_id])
            if len(coords) >= 3:
                buildings.append({
                    'id': el['id'],
                    'coords': coords,
                    'tags': el.get('tags', {})
                })

    print(f"  Found {len(buildings)} OSM buildings")
    return buildings


def load_prediction_tiles() -> list:
    """Load all prediction masks with their bounds."""
    tiles = []

    for pred_path in sorted(PREDICTIONS_DIR.glob("tile_*_mask.png")):
        tile_name = pred_path.stem.replace("_mask", "")
        meta_path = METADATA_DIR / f"{tile_name}.json"

        if not meta_path.exists():
            continue

        with open(meta_path) as f:
            meta = json.load(f)

        # Load mask
        mask = np.array(Image.open(pred_path))
        if len(mask.shape) == 3:
            mask = mask[:, :, 0]

        tiles.append({
            'name': tile_name,
            'bounds': meta['bounds'],
            'mask': mask
        })

    print(f"Loaded {len(tiles)} prediction tiles")
    return tiles


def point_in_bounds(lon: float, lat: float, bounds: dict) -> bool:
    """Check if point is within bounds."""
    return (bounds['west'] <= lon <= bounds['east'] and
            bounds['south'] <= lat <= bounds['north'])


def geo_to_pixel(lon: float, lat: float, bounds: dict, mask_shape: tuple) -> tuple:
    """Convert geographic coordinates to pixel coordinates."""
    height, width = mask_shape
    x = int((lon - bounds['west']) / (bounds['east'] - bounds['west']) * width)
    y = int((bounds['north'] - lat) / (bounds['north'] - bounds['south']) * height)
    return (x, y)


def check_building_in_tile(building_coords: list, tile: dict) -> float:
    """
    Check how much of a building overlaps with predicted buildings in a tile.

    Returns overlap ratio (0.0 to 1.0)
    """
    bounds = tile['bounds']
    mask = tile['mask']
    mask_shape = mask.shape

    # Convert building coords to pixel coords
    pixel_coords = []
    for lon, lat in building_coords:
        if point_in_bounds(lon, lat, bounds):
            px, py = geo_to_pixel(lon, lat, bounds, mask_shape)
            px = max(0, min(px, mask_shape[1] - 1))
            py = max(0, min(py, mask_shape[0] - 1))
            pixel_coords.append((px, py))

    if len(pixel_coords) < 3:
        return -1.0  # Building not in this tile

    # Create building mask
    building_mask = np.zeros(mask_shape, dtype=np.uint8)
    pts = np.array(pixel_coords, dtype=np.int32)
    cv2.fillPoly(building_mask, [pts], 1)

    # Calculate overlap with prediction
    building_pixels = np.sum(building_mask == 1)
    if building_pixels == 0:
        return -1.0

    overlap_pixels = np.sum((building_mask == 1) & (mask == 1))
    overlap_ratio = overlap_pixels / building_pixels

    return overlap_ratio


def verify_building(building: dict, tiles: list) -> dict:
    """
    Verify a single building against all prediction tiles.

    Returns:
        - existed: bool - ML prediction of whether building existed in 1937
        - confidence: float 0-1 - how confident the prediction is
        - coverage: float 0-1 - how much of building is covered by prediction tiles
    """
    coords = building['coords']

    # Find centroid
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    centroid_lon = sum(lons) / len(lons)
    centroid_lat = sum(lats) / len(lats)

    # Check if building is within our coverage area
    if not point_in_bounds(centroid_lon, centroid_lat, AREA_BOUNDS):
        return {
            'existed': None,
            'confidence': 0.0,
            'coverage': 0.0,
            'reason': 'Outside prediction coverage'
        }

    # Check each tile
    max_overlap = -1.0
    checked_tiles = 0

    for tile in tiles:
        overlap = check_building_in_tile(coords, tile)
        if overlap >= 0:
            checked_tiles += 1
            max_overlap = max(max_overlap, overlap)

    if checked_tiles == 0:
        return {
            'existed': None,
            'confidence': 0.0,
            'coverage': 0.0,
            'reason': 'No prediction tile covers this building'
        }

    # Binary classification with confidence
    # Overlap > 0.5 means "existed", confidence based on how clear the signal is
    if max_overlap >= 0.5:
        # Existed - confidence scales from 0.5 (at threshold) to 1.0 (at 100% overlap)
        confidence = 0.5 + (max_overlap - 0.5)
        return {
            'existed': True,
            'confidence': round(confidence, 2),
            'coverage': 1.0,
            'overlap': round(max_overlap, 2),
            'reason': f'{max_overlap*100:.0f}% overlap'
        }
    else:
        # Did not exist - confidence scales from 0.5 (at threshold) to 1.0 (at 0% overlap)
        confidence = 0.5 + (0.5 - max_overlap)
        return {
            'existed': False,
            'confidence': round(confidence, 2),
            'coverage': 1.0,
            'overlap': round(max_overlap, 2),
            'reason': f'{max_overlap*100:.0f}% overlap'
        }


def main():
    # Ensure output directory exists
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Fetch OSM buildings
    buildings = fetch_osm_buildings(AREA_BOUNDS)

    # Load prediction tiles
    tiles = load_prediction_tiles()

    if not tiles:
        print("Error: No prediction tiles found")
        return

    # Verify each building
    print(f"\nVerifying {len(buildings)} buildings against 1937 predictions...")

    features = []
    stats = {
        'existed_high_conf': 0,    # existed=True, conf >= 0.7
        'existed_low_conf': 0,     # existed=True, conf < 0.7
        'not_existed_high_conf': 0, # existed=False, conf >= 0.7
        'not_existed_low_conf': 0,  # existed=False, conf < 0.7
        'no_coverage': 0
    }

    for i, building in enumerate(buildings):
        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{len(buildings)} buildings...")

        result = verify_building(building, tiles)

        # Skip buildings outside coverage
        if result['existed'] is None:
            stats['no_coverage'] += 1
            continue

        # Update stats
        if result['existed']:
            if result['confidence'] >= 0.7:
                stats['existed_high_conf'] += 1
            else:
                stats['existed_low_conf'] += 1
        else:
            if result['confidence'] >= 0.7:
                stats['not_existed_high_conf'] += 1
            else:
                stats['not_existed_low_conf'] += 1

        # Create GeoJSON feature
        from shapely.geometry import Polygon
        try:
            poly = Polygon(building['coords'])
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue
        except:
            continue

        feature = {
            "type": "Feature",
            "geometry": mapping(poly),
            "properties": {
                "osm_id": building['id'],
                "name": building['tags'].get('name', ''),
                # Binary classification + confidence
                "existed": result['existed'],
                "confidence": result['confidence'],
                "overlap": result.get('overlap', 0),
                "reason": result['reason']
            }
        }
        features.append(feature)

    # Create GeoJSON
    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "source": "OSM buildings verified against 1937 aerial predictions",
            "bounds": AREA_BOUNDS,
            "stats": stats,
            "confidence_threshold": 0.7,  # UI can adjust this
            "schema": {
                "existed": "bool - ML prediction: did building exist in 1937?",
                "confidence": "float 0-1 - how confident is the prediction",
                "overlap": "float 0-1 - overlap ratio with ML prediction mask"
            }
        }
    }

    # Save
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(geojson, f)

    print(f"\nVerification complete!")
    print(f"  Existed (high confidence):     {stats['existed_high_conf']}")
    print(f"  Existed (low confidence):      {stats['existed_low_conf']}")
    print(f"  Not existed (high confidence): {stats['not_existed_high_conf']}")
    print(f"  Not existed (low confidence):  {stats['not_existed_low_conf']}")
    print(f"  No coverage:                   {stats['no_coverage']}")
    print(f"\nSaved to {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
