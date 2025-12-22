#!/usr/bin/env python3
"""
Complete building extraction workflow from historical maps.

Pipeline:
1. Load historical map image
2. Georeference using GCPs (or validate existing georeferencing)
3. Tile into ML-compatible chunks
4. Run segmentation model
5. Vectorize building polygons
6. Add to evidence database

Usage:
    python scripts/extract_buildings.py --map trondheim_1936.jpg --year 1936
    python scripts/extract_buildings.py --map-dir data/georeference/input/ --all
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

import numpy as np
from PIL import Image

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'ml'))

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
MODELS_DIR = PROJECT_ROOT / 'models' / 'checkpoints'
INPUT_DIR = DATA_DIR / 'georeference' / 'input'
GCPS_DIR = DATA_DIR / 'georeference' / 'gcps'
OUTPUT_DIR = DATA_DIR / 'georeference' / 'output'
EXTRACTED_DIR = DATA_DIR / 'extracted'


def find_gcps(map_name: str) -> Optional[Path]:
    """Find GCP file for a map."""
    # Try different naming patterns
    patterns = [
        GCPS_DIR / f"{map_name}.gcp.json",
        GCPS_DIR / f"{map_name}.json",
        DATA_DIR / 'kartverket' / 'gcps' / f"{map_name}.json",
    ]

    for pattern in patterns:
        if pattern.exists():
            return pattern

    return None


def load_gcps(gcp_path: Path) -> Dict:
    """Load GCPs from JSON file."""
    with open(gcp_path) as f:
        return json.load(f)


def calculate_transform_from_gcps(gcps: List[Dict], img_width: int, img_height: int) -> Tuple[float, float, float, float]:
    """
    Calculate approximate bounds from GCPs.

    Returns (west, south, east, north) bounds.
    """
    if len(gcps) < 3:
        raise ValueError("Need at least 3 GCPs for transformation")

    # Extract pixel and geo coordinates
    pixels = [(g['pixel_x'], g['pixel_y']) for g in gcps]
    geos = [(g['geo_x'], g['geo_y']) for g in gcps]

    # Simple affine estimation (least squares would be better)
    # For now, use min/max of GCPs to estimate bounds
    geo_xs = [g[0] for g in geos]
    geo_ys = [g[1] for g in geos]

    pix_xs = [p[0] for p in pixels]
    pix_ys = [p[1] for p in pixels]

    # Calculate pixel to geo ratio
    x_scale = (max(geo_xs) - min(geo_xs)) / (max(pix_xs) - min(pix_xs))
    y_scale = (max(geo_ys) - min(geo_ys)) / (max(pix_ys) - min(pix_ys))

    # Estimate full image bounds
    # Assume GCPs are somewhat distributed across the image
    avg_pix_x = sum(pix_xs) / len(pix_xs)
    avg_pix_y = sum(pix_ys) / len(pix_ys)
    avg_geo_x = sum(geo_xs) / len(geo_xs)
    avg_geo_y = sum(geo_ys) / len(geo_ys)

    west = avg_geo_x - (avg_pix_x * x_scale)
    east = avg_geo_x + ((img_width - avg_pix_x) * x_scale)
    north = avg_geo_y + (avg_pix_y * abs(y_scale))
    south = avg_geo_y - ((img_height - avg_pix_y) * abs(y_scale))

    return (west, south, east, north)


def tile_image(image_path: Path, tile_size: int = 512, overlap: int = 64) -> List[Dict]:
    """
    Tile an image into overlapping chunks for ML inference.

    Returns list of tile info dicts with image data and position.
    """
    img = Image.open(image_path)
    width, height = img.size

    tiles = []
    stride = tile_size - overlap

    tile_id = 0
    for y in range(0, height, stride):
        for x in range(0, width, stride):
            # Calculate tile bounds
            x1 = x
            y1 = y
            x2 = min(x + tile_size, width)
            y2 = min(y + tile_size, height)

            # Extract tile
            tile = img.crop((x1, y1, x2, y2))

            # Pad if needed
            if tile.size != (tile_size, tile_size):
                padded = Image.new(img.mode, (tile_size, tile_size), color=255)
                padded.paste(tile, (0, 0))
                tile = padded

            tiles.append({
                'id': tile_id,
                'image': tile,
                'x': x1,
                'y': y1,
                'width': x2 - x1,
                'height': y2 - y1
            })
            tile_id += 1

    return tiles


def run_inference(tiles: List[Dict], model_path: Path, device: str = 'auto') -> List[Dict]:
    """
    Run ML model inference on tiles.

    Returns tiles with prediction masks added.
    """
    import torch
    from predict import load_model, get_device

    if device == 'auto':
        device = get_device()
    else:
        device = torch.device(device)

    print(f"  Loading model from {model_path}...")
    model = load_model(str(model_path), device)
    model.eval()

    print(f"  Running inference on {len(tiles)} tiles...")

    for tile in tiles:
        # Prepare input
        img_array = np.array(tile['image'])

        # Normalize and convert to tensor
        if len(img_array.shape) == 2:
            img_array = np.stack([img_array] * 3, axis=-1)
        elif img_array.shape[2] == 4:
            img_array = img_array[:, :, :3]

        img_tensor = torch.from_numpy(img_array).permute(2, 0, 1).float() / 255.0
        img_tensor = img_tensor.unsqueeze(0).to(device)

        # Run inference
        with torch.no_grad():
            output = model(img_tensor)
            pred = torch.argmax(output, dim=1).squeeze().cpu().numpy()

        tile['mask'] = pred.astype(np.uint8)

    return tiles


def merge_masks(tiles: List[Dict], img_width: int, img_height: int) -> np.ndarray:
    """
    Merge tile masks back into full image mask.
    """
    full_mask = np.zeros((img_height, img_width), dtype=np.uint8)

    for tile in tiles:
        x, y = tile['x'], tile['y']
        w, h = tile['width'], tile['height']

        mask = tile['mask'][:h, :w]
        full_mask[y:y+h, x:x+w] = mask

    return full_mask


def vectorize_buildings(mask: np.ndarray, bounds: Tuple[float, float, float, float]) -> List[Dict]:
    """
    Convert building mask to GeoJSON polygons.

    Args:
        mask: Segmentation mask with class indices
        bounds: (west, south, east, north) geographic bounds

    Returns:
        List of GeoJSON feature dicts
    """
    import cv2
    from shapely.geometry import Polygon, mapping
    from shapely.ops import unary_union

    west, south, east, north = bounds
    height, width = mask.shape

    # Pixel to geo conversion
    x_scale = (east - west) / width
    y_scale = (south - north) / height  # Negative because y increases downward

    def pixel_to_geo(px, py):
        return (west + px * x_scale, north + py * y_scale)

    # Extract building class (1)
    building_mask = (mask == 1).astype(np.uint8) * 255

    # Find contours
    contours, _ = cv2.findContours(building_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    features = []
    for i, contour in enumerate(contours):
        if len(contour) < 4:
            continue

        # Skip very small contours
        area = cv2.contourArea(contour)
        if area < 100:  # pixels
            continue

        # Convert to geo coordinates
        coords = []
        for point in contour.squeeze():
            if len(point.shape) == 0:
                continue
            geo_x, geo_y = pixel_to_geo(point[0], point[1])
            coords.append((geo_x, geo_y))

        if len(coords) < 4:
            continue

        # Close the polygon
        coords.append(coords[0])

        try:
            poly = Polygon(coords)
            if poly.is_valid and poly.area > 0:
                # Simplify slightly
                poly = poly.simplify(0.00001)

                features.append({
                    'type': 'Feature',
                    'properties': {
                        'class': 'building',
                        'confidence': 0.75,
                        'extraction_method': 'ml_segmentation'
                    },
                    'geometry': mapping(poly)
                })
        except Exception as e:
            continue

    return features


def save_geojson(features: List[Dict], output_path: Path, map_year: int, source_name: str):
    """Save features to GeoJSON file."""
    geojson_data = {
        'type': 'FeatureCollection',
        'metadata': {
            'source': source_name,
            'reference_year': map_year,
            'extracted_at': datetime.now().isoformat(),
            'building_count': len(features)
        },
        'features': features
    }

    # Add temporal properties to each feature
    for feat in geojson_data['features']:
        feat['properties']['source'] = f"ml_{source_name}"
        feat['properties']['max_year'] = map_year

    with open(output_path, 'w') as f:
        json.dump(geojson_data, f, indent=2)

    return output_path


def import_to_database(geojson_path: Path, source_id: str, reference_year: int):
    """Import extracted buildings to evidence database."""
    from db.schema import init_db
    from db.buildings import upsert_building
    from db.evidence import Evidence, add_evidence

    conn = init_db()

    with open(geojson_path) as f:
        data = json.load(f)

    count = 0
    for i, feat in enumerate(data.get('features', [])):
        props = feat.get('properties', {})
        geom = feat.get('geometry')

        building_id = f"{source_id}:{reference_year}_{i}"

        upsert_building(
            conn,
            building_id=building_id,
            geometry=geom,
            geometry_source=source_id,
            building_type='building'
        )

        confidence = props.get('confidence', 0.75)

        evidence = Evidence(
            building_id=building_id,
            source_id=source_id,
            evidence_type='presence',
            max_year=reference_year,
            confidence=confidence,
            confidence_reason='ml_extraction',
            source_local_id=f"{reference_year}_{i}",
            method='ml_detection'
        )
        add_evidence(conn, evidence)
        count += 1

    conn.commit()
    conn.close()

    return count


def extract_from_map(map_path: Path, year: int, model_path: Path = None) -> Dict:
    """
    Full extraction pipeline for a single map.

    Returns extraction statistics.
    """
    map_name = map_path.stem
    source_id = f"map_{year}"

    print(f"\n{'='*60}")
    print(f"Extracting buildings from: {map_name}")
    print(f"Reference year: {year}")
    print(f"{'='*60}")

    # Default model path
    if model_path is None:
        model_path = MODELS_DIR / 'best_model.pth'

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    # Find GCPs
    print("\n1. Loading GCPs...")
    gcp_path = find_gcps(map_name)
    if not gcp_path:
        raise FileNotFoundError(f"No GCPs found for {map_name}. Create GCPs first using georef_editor.html")

    gcp_data = load_gcps(gcp_path)
    gcps = gcp_data.get('gcps', [])
    print(f"   Found {len(gcps)} GCPs")

    if len(gcps) < 4:
        raise ValueError(f"Need at least 4 GCPs, found {len(gcps)}")

    # Load image
    print("\n2. Loading image...")
    img = Image.open(map_path)
    width, height = img.size
    print(f"   Image size: {width} x {height}")

    # Calculate bounds from GCPs
    print("\n3. Calculating geographic bounds...")
    bounds = calculate_transform_from_gcps(gcps, width, height)
    print(f"   Bounds: W={bounds[0]:.4f}, S={bounds[1]:.4f}, E={bounds[2]:.4f}, N={bounds[3]:.4f}")

    # Tile image
    print("\n4. Tiling image...")
    tiles = tile_image(map_path, tile_size=512, overlap=64)
    print(f"   Created {len(tiles)} tiles")

    # Run inference
    print("\n5. Running ML inference...")
    tiles = run_inference(tiles, model_path)

    # Merge masks
    print("\n6. Merging masks...")
    full_mask = merge_masks(tiles, width, height)

    # Save mask for debugging
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    mask_path = EXTRACTED_DIR / f"{map_name}_mask.png"
    Image.fromarray(full_mask * 50).save(mask_path)  # Multiply for visibility
    print(f"   Saved mask to {mask_path}")

    # Vectorize
    print("\n7. Vectorizing buildings...")
    features = vectorize_buildings(full_mask, bounds)
    print(f"   Extracted {len(features)} building polygons")

    # Save GeoJSON
    geojson_path = EXTRACTED_DIR / f"buildings_{year}.geojson"
    save_geojson(features, geojson_path, year, map_name)
    print(f"   Saved to {geojson_path}")

    # Import to database
    print("\n8. Importing to database...")
    db_count = import_to_database(geojson_path, source_id, year)
    print(f"   Added {db_count} buildings to database")

    return {
        'map': map_name,
        'year': year,
        'tiles': len(tiles),
        'buildings': len(features),
        'geojson': str(geojson_path),
        'mask': str(mask_path)
    }


def main():
    parser = argparse.ArgumentParser(description='Extract buildings from historical maps')
    parser.add_argument('--map', type=Path, help='Path to map image')
    parser.add_argument('--year', type=int, help='Reference year for the map')
    parser.add_argument('--model', type=Path, default=None, help='Path to model checkpoint')
    parser.add_argument('--all', action='store_true', help='Process all maps in input directory')

    args = parser.parse_args()

    if args.all:
        # Find all maps with GCPs
        print("Finding maps with GCPs...")
        maps_to_process = []

        for gcp_file in GCPS_DIR.glob('*.gcp.json'):
            map_name = gcp_file.stem.replace('.gcp', '')
            map_path = INPUT_DIR / f"{map_name}.jpg"

            if not map_path.exists():
                map_path = INPUT_DIR / f"{map_name}.png"

            if map_path.exists():
                # Extract year from name
                import re
                year_match = re.search(r'(\d{4})', map_name)
                if year_match:
                    year = int(year_match.group(1))
                    maps_to_process.append((map_path, year))

        if not maps_to_process:
            print("No maps with GCPs found!")
            return

        print(f"Found {len(maps_to_process)} maps to process")

        results = []
        for map_path, year in maps_to_process:
            try:
                result = extract_from_map(map_path, year, args.model)
                results.append(result)
            except Exception as e:
                print(f"Error processing {map_path}: {e}")

        print("\n" + "="*60)
        print("EXTRACTION COMPLETE")
        print("="*60)
        for r in results:
            print(f"  {r['map']}: {r['buildings']} buildings extracted")

    elif args.map and args.year:
        result = extract_from_map(args.map, args.year, args.model)
        print("\n" + "="*60)
        print(f"Extraction complete: {result['buildings']} buildings")
        print(f"GeoJSON: {result['geojson']}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
