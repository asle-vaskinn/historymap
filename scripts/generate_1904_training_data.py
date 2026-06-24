#!/usr/bin/env python3
"""
Generate training data for Kartverket 1904 map building detection.

This script:
1. Fetches map tiles from Kartverket WMS historical map service
2. Uses SEFRAK buildings (sd <= 1904) as pseudo-labels
3. Rasterizes building footprints onto tiles as class 1 masks

Usage:
    python scripts/generate_1904_training_data.py --tiles 100
    python scripts/generate_1904_training_data.py --tiles 50 --focus-buildings
    python scripts/generate_1904_training_data.py --dry-run
"""

import argparse
import json
import random
import sys
from io import BytesIO
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from datetime import datetime

import numpy as np
from PIL import Image

try:
    import requests
    from shapely.geometry import shape, box, mapping
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    print("Error: shapely not installed. pip install shapely")
    sys.exit(1)

try:
    from rasterio.features import rasterize
    from rasterio.transform import from_bounds
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    print("Error: rasterio not installed. pip install rasterio")
    sys.exit(1)


# WMS source for 1904 historical map
WMS_CONFIG = {
    'url': 'https://wms.geonorge.no/skwms1/wms.historiskekart',
    'layers': 'amt1',  # Amtskart layer
    'name': 'Amtskart ~1900',
    # Downtown Trondheim focus area
    'bbox': [10.35, 63.40, 10.45, 63.46],
}

# Class IDs (matching existing ML pipeline)
CLASS_BACKGROUND = 0
CLASS_BUILDING = 1

# Tile parameters
TILE_SIZE = 512
TILE_DEG = 0.002  # ~100m at 63°N - smaller for downtown detail


def load_sefrak_buildings(data_dir: Path, max_year: int = 1904) -> Tuple[List[Dict], object]:
    """
    Load SEFRAK buildings constructed by max_year.

    Returns:
        Tuple of (features list, spatial index)
    """
    sefrak_path = data_dir / 'sources' / 'sefrak' / 'normalized' / 'buildings.geojson'

    if not sefrak_path.exists():
        print(f"Warning: SEFRAK not found at {sefrak_path}")
        # Try alternative path
        sefrak_path = data_dir / 'sources' / 'sefrak' / 'raw' / 'buildings.geojson'
        if not sefrak_path.exists():
            print("Error: SEFRAK data not found")
            return [], None

    print(f"Loading SEFRAK from {sefrak_path}...")
    with open(sefrak_path) as f:
        data = json.load(f)

    features = data.get('features', [])
    print(f"Loaded {len(features)} total SEFRAK features")

    # Filter by construction year
    filtered = []
    for f in features:
        props = f.get('properties', {})
        sd = props.get('sd') or props.get('byggeaar') or props.get('construction_year')
        if sd is not None:
            try:
                year = int(sd)
                if year <= max_year:
                    filtered.append(f)
            except (ValueError, TypeError):
                pass

    print(f"Filtered to {len(filtered)} buildings with sd <= {max_year}")

    if not filtered:
        print("Warning: No SEFRAK buildings found for the specified year range")
        return [], None

    # Build spatial index
    geometries = []
    for f in filtered:
        try:
            geom = shape(f['geometry'])
            geometries.append(geom)
        except Exception as e:
            continue

    if geometries:
        tree = STRtree(geometries)
        print(f"Built spatial index with {len(geometries)} geometries")
        return filtered, tree

    return filtered, None


def fetch_wms_tile(west: float, south: float, east: float, north: float) -> Optional[Image.Image]:
    """Fetch a single tile from WMS service."""
    params = {
        'SERVICE': 'WMS',
        'VERSION': '1.3.0',
        'REQUEST': 'GetMap',
        'LAYERS': WMS_CONFIG['layers'],
        'CRS': 'EPSG:4326',
        'BBOX': f'{south},{west},{north},{east}',  # WMS 1.3.0 uses lat,lon order for EPSG:4326
        'WIDTH': TILE_SIZE,
        'HEIGHT': TILE_SIZE,
        'FORMAT': 'image/png',
        'STYLES': '',
    }

    try:
        response = requests.get(WMS_CONFIG['url'], params=params, timeout=30)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type:
                return Image.open(BytesIO(response.content)).convert('RGB')
            else:
                # Might be an error response
                print(f"  WMS returned non-image: {content_type[:50]}")
                return None
        else:
            print(f"  WMS error: {response.status_code}")
            return None
    except Exception as e:
        print(f"  WMS fetch error: {e}")
        return None


def rasterize_buildings(
    features: List[Dict],
    tree: object,
    west: float, south: float, east: float, north: float,
    width: int = TILE_SIZE, height: int = TILE_SIZE
) -> Tuple[np.ndarray, int]:
    """
    Rasterize SEFRAK buildings onto a tile.

    Returns:
        Tuple of (mask array, building count)
    """
    tile_box = box(west, south, east, north)

    # Query spatial index for buildings in this tile
    if tree is not None:
        candidate_indices = tree.query(tile_box)
    else:
        candidate_indices = range(len(features))

    # Collect intersecting building geometries
    shapes_to_rasterize = []
    for idx in candidate_indices:
        try:
            f = features[idx]
            geom = shape(f['geometry'])
            if geom.intersects(tile_box):
                # Clip to tile bounds
                clipped = geom.intersection(tile_box)
                if not clipped.is_empty:
                    shapes_to_rasterize.append((clipped, CLASS_BUILDING))
        except Exception:
            continue

    # Create mask
    mask = np.zeros((height, width), dtype=np.uint8)

    if shapes_to_rasterize:
        transform = from_bounds(west, south, east, north, width, height)
        mask = rasterize(
            shapes_to_rasterize,
            out_shape=(height, width),
            transform=transform,
            fill=CLASS_BACKGROUND,
            dtype=np.uint8
        )

    return mask, len(shapes_to_rasterize)


def generate_tile_grid(
    bbox: List[float],
    features: List[Dict],
    tree: object,
    n_tiles: int,
    focus_buildings: bool = True
) -> List[Tuple[float, float, float, float]]:
    """
    Generate tile bounds within bbox.

    If focus_buildings is True, preferentially generate tiles where SEFRAK buildings exist.
    """
    west, south, east, north = bbox
    tiles = []

    # Calculate grid dimensions
    x_tiles = int((east - west) / TILE_DEG)
    y_tiles = int((north - south) / TILE_DEG)

    print(f"Grid size: {x_tiles} x {y_tiles} = {x_tiles * y_tiles} possible tiles")

    # Generate all possible tile centers
    all_tiles = []
    for xi in range(x_tiles):
        for yi in range(y_tiles):
            tile_west = west + xi * TILE_DEG
            tile_south = south + yi * TILE_DEG
            tile_east = tile_west + TILE_DEG
            tile_north = tile_south + TILE_DEG

            # Check if tile has buildings
            tile_box = box(tile_west, tile_south, tile_east, tile_north)
            has_buildings = False
            building_count = 0

            if tree is not None:
                candidate_indices = tree.query(tile_box)
                for idx in candidate_indices:
                    try:
                        geom = shape(features[idx]['geometry'])
                        if geom.intersects(tile_box):
                            has_buildings = True
                            building_count += 1
                    except:
                        pass

            all_tiles.append({
                'bounds': (tile_west, tile_south, tile_east, tile_north),
                'has_buildings': has_buildings,
                'building_count': building_count
            })

    # Split into tiles with and without buildings
    with_buildings = [t for t in all_tiles if t['has_buildings']]
    without_buildings = [t for t in all_tiles if not t['has_buildings']]

    print(f"Tiles with buildings: {len(with_buildings)}")
    print(f"Tiles without buildings: {len(without_buildings)}")

    if focus_buildings and with_buildings:
        # 80% from building tiles, 20% from background
        n_building_tiles = min(int(n_tiles * 0.8), len(with_buildings))
        n_background_tiles = min(n_tiles - n_building_tiles, len(without_buildings))

        # Sort by building count (descending) and take top tiles
        with_buildings.sort(key=lambda t: t['building_count'], reverse=True)
        selected_building = with_buildings[:n_building_tiles]

        # Random background tiles
        random.shuffle(without_buildings)
        selected_background = without_buildings[:n_background_tiles]

        selected = selected_building + selected_background
    else:
        # Random selection
        random.shuffle(all_tiles)
        selected = all_tiles[:n_tiles]

    return [t['bounds'] for t in selected]


def main():
    parser = argparse.ArgumentParser(description='Generate 1904 map training data')
    parser.add_argument('--tiles', '-n', type=int, default=100,
                        help='Number of tiles to generate')
    parser.add_argument('--max-year', type=int, default=1904,
                        help='Maximum construction year for SEFRAK filter')
    parser.add_argument('--output', '-o', type=Path,
                        default=Path('data/training_1904'),
                        help='Output directory')
    parser.add_argument('--focus-buildings', action='store_true', default=True,
                        help='Preferentially select tiles with buildings')
    parser.add_argument('--no-focus', action='store_true',
                        help='Random tile selection instead of building focus')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without downloading')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed for reproducibility')

    args = parser.parse_args()
    random.seed(args.seed)

    print("=" * 60)
    print("1904 MAP TRAINING DATA GENERATOR")
    print("=" * 60)
    print(f"Output: {args.output}")
    print(f"Tiles: {args.tiles}")
    print(f"Max year: {args.max_year}")
    print(f"WMS: {WMS_CONFIG['name']}")
    print()

    # Setup paths
    data_dir = Path('data')
    output_dir = args.output
    images_dir = output_dir / 'images'
    masks_dir = output_dir / 'masks'

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(exist_ok=True)
        masks_dir.mkdir(exist_ok=True)

    # Load SEFRAK buildings
    print("Loading SEFRAK buildings...")
    features, tree = load_sefrak_buildings(data_dir, max_year=args.max_year)

    if not features:
        print("No SEFRAK buildings found. Trying OSM as fallback...")
        # Try OSM buildings as fallback
        osm_path = data_dir / 'sources' / 'osm' / 'normalized' / 'buildings.geojson'
        if osm_path.exists():
            with open(osm_path) as f:
                osm_data = json.load(f)
            features = osm_data.get('features', [])
            # Filter OSM by year if they have dates
            filtered = []
            for f in features:
                sd = f.get('properties', {}).get('sd')
                if sd is None or (isinstance(sd, (int, float)) and sd <= args.max_year):
                    filtered.append(f)
            features = filtered
            print(f"Using {len(features)} OSM buildings as fallback")

            # Rebuild spatial index
            geometries = [shape(f['geometry']) for f in features if f.get('geometry')]
            tree = STRtree(geometries) if geometries else None

    # Generate tile grid
    print("\nGenerating tile grid...")
    focus = args.focus_buildings and not args.no_focus
    tile_bounds = generate_tile_grid(
        WMS_CONFIG['bbox'],
        features,
        tree,
        args.tiles,
        focus_buildings=focus
    )

    print(f"\nSelected {len(tile_bounds)} tiles")

    if args.dry_run:
        print("\nDRY RUN - would generate:")
        for i, (w, s, e, n) in enumerate(tile_bounds[:5]):
            print(f"  Tile {i}: ({w:.4f}, {s:.4f}) to ({e:.4f}, {n:.4f})")
        if len(tile_bounds) > 5:
            print(f"  ... and {len(tile_bounds) - 5} more")
        return

    # Generate tiles
    print("\nFetching tiles and generating masks...")
    metadata = {
        'generated_at': datetime.now().isoformat(),
        'wms_source': WMS_CONFIG,
        'max_year': args.max_year,
        'tile_size': TILE_SIZE,
        'tile_deg': TILE_DEG,
        'tiles': []
    }

    success_count = 0
    building_total = 0

    for i, (west, south, east, north) in enumerate(tile_bounds):
        tile_id = f"tile_{i:04d}"
        print(f"\n[{i+1}/{len(tile_bounds)}] {tile_id}")
        print(f"  Bounds: ({west:.4f}, {south:.4f}) to ({east:.4f}, {north:.4f})")

        # Fetch WMS tile
        print(f"  Fetching from WMS...")
        image = fetch_wms_tile(west, south, east, north)

        if image is None:
            print(f"  FAILED to fetch tile")
            continue

        # Rasterize buildings
        print(f"  Rasterizing buildings...")
        mask, building_count = rasterize_buildings(
            features, tree, west, south, east, north
        )

        print(f"  Buildings in tile: {building_count}")
        building_total += building_count

        # Save image and mask
        image_path = images_dir / f"{tile_id}.png"
        mask_path = masks_dir / f"{tile_id}.png"

        image.save(image_path)
        Image.fromarray(mask).save(mask_path)

        # Record metadata
        metadata['tiles'].append({
            'id': tile_id,
            'bounds': {'west': west, 'south': south, 'east': east, 'north': north},
            'building_count': building_count,
            'image': str(image_path.name),
            'mask': str(mask_path.name)
        })

        success_count += 1

    # Save metadata
    metadata['success_count'] = success_count
    metadata['total_buildings'] = building_total

    metadata_path = output_dir / 'metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print("\n" + "=" * 60)
    print("GENERATION COMPLETE")
    print("=" * 60)
    print(f"Successfully generated: {success_count}/{len(tile_bounds)} tiles")
    print(f"Total buildings rasterized: {building_total}")
    print(f"Output directory: {output_dir}")
    print(f"  Images: {images_dir}")
    print(f"  Masks: {masks_dir}")
    print(f"  Metadata: {metadata_path}")


if __name__ == '__main__':
    main()
