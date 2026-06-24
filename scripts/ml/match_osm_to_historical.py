#!/usr/bin/env python3
"""
Match OSM buildings to historical map for ML training.

This implements the geometric similarity approach:
1. Load OSM building footprints (full polygons, not points)
2. Fetch historical map tiles from WMS
3. Use OSM footprints as training labels (buildings that still exist)
4. Train model on these high-quality matches
5. Model can then detect ALL buildings on historical map
6. Buildings detected but not in OSM = demolished buildings

Usage:
    python scripts/ml/match_osm_to_historical.py --year 1904 --tiles 100
    python scripts/ml/match_osm_to_historical.py --year 1880 --tiles 50 --min-age 100
"""

import argparse
import json
import random
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

try:
    import requests
    from shapely.geometry import box, mapping, shape
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


# WMS sources for historical maps
WMS_SOURCES = {
    '1880': {
        'url': 'https://wms.geonorge.no/skwms1/wms.historiskekart',
        'layers': 'amt1',
        'name': 'Amtskart ~1880',
        'bbox': [10.35, 63.40, 10.45, 63.46],
    },
    '1904': {
        'url': 'https://wms.geonorge.no/skwms1/wms.historiskekart',
        'layers': 'amt1',
        'name': 'Amtskart ~1904',
        'bbox': [10.35, 63.40, 10.45, 63.46],
    },
    '1937': {
        'url': 'https://kart.trondheim.kommune.no/geoserver/Raster/wms',
        'layers': 'ortofoto1937',
        'name': 'Flyfoto 1937',
        'bbox': [10.38, 63.42, 10.44, 63.45],
    },
}

# Class IDs
CLASS_BACKGROUND = 0
CLASS_BUILDING = 1

# Tile parameters
TILE_SIZE = 512
TILE_DEG = 0.002  # ~100m at 63°N


def load_osm_buildings(data_dir: Path, min_age: int = 0) -> Tuple[List[Dict], Optional[STRtree]]:
    """
    Load OSM buildings with full polygon footprints.

    Args:
        data_dir: Path to data directory
        min_age: Minimum building age to include (filters by construction year)

    Returns:
        Tuple of (features list, spatial index)
    """
    # Try normalized first, then raw
    osm_paths = [
        data_dir / 'sources' / 'osm' / 'normalized' / 'buildings.geojson',
        data_dir / 'sources' / 'osm' / 'raw' / 'buildings.geojson',
        data_dir / 'export' / 'buildings.geojson',
    ]

    osm_data = None
    for path in osm_paths:
        if path.exists():
            print(f"Loading OSM from {path}...")
            with open(path) as f:
                osm_data = json.load(f)
            break

    if osm_data is None:
        print("Error: OSM buildings not found")
        return [], None

    features = osm_data.get('features', [])
    print(f"Loaded {len(features)} OSM features")

    # Filter by age if requested
    if min_age > 0:
        current_year = datetime.now().year
        max_construction_year = current_year - min_age

        filtered = []
        for f in features:
            props = f.get('properties', {})
            # Check construction year
            sd = props.get('sd') or props.get('start_date') or props.get('building:year')
            if sd is not None:
                try:
                    year = int(sd)
                    if year <= max_construction_year:
                        filtered.append(f)
                except (ValueError, TypeError):
                    # Include buildings without valid dates
                    filtered.append(f)
            else:
                # Include buildings without dates (might be old)
                filtered.append(f)

        print(f"Filtered to {len(filtered)} buildings >= {min_age} years old")
        features = filtered

    # Build spatial index with valid polygons only
    geometries = []
    valid_features = []

    for f in features:
        try:
            geom = shape(f['geometry'])
            # Only include Polygons and MultiPolygons with actual area
            if geom.geom_type in ('Polygon', 'MultiPolygon') and geom.area > 0:
                geometries.append(geom)
                valid_features.append(f)
        except Exception:
            continue

    print(f"Built spatial index with {len(geometries)} valid polygon geometries")

    if geometries:
        tree = STRtree(geometries)
        return valid_features, tree

    return valid_features, None


def fetch_wms_tile(url: str, layers: str, west: float, south: float,
                   east: float, north: float) -> Optional[Image.Image]:
    """Fetch a single tile from WMS service."""

    # Use WMS 1.3.0 with proper CRS handling
    params = {
        'SERVICE': 'WMS',
        'VERSION': '1.3.0',
        'REQUEST': 'GetMap',
        'LAYERS': layers,
        'CRS': 'EPSG:4326',
        'BBOX': f'{south},{west},{north},{east}',  # WMS 1.3.0 lat,lon order
        'WIDTH': TILE_SIZE,
        'HEIGHT': TILE_SIZE,
        'FORMAT': 'image/png',
        'STYLES': '',
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type:
                return Image.open(BytesIO(response.content)).convert('RGB')
    except Exception as e:
        print(f"  WMS error: {e}")

    return None


def rasterize_buildings(
    features: List[Dict],
    tree: Optional[STRtree],
    west: float, south: float, east: float, north: float,
    width: int = TILE_SIZE, height: int = TILE_SIZE
) -> Tuple[np.ndarray, int, float]:
    """
    Rasterize OSM buildings onto a tile.

    Returns:
        Tuple of (mask array, building count, building pixel ratio)
    """
    tile_box = box(west, south, east, north)

    # Query spatial index
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
                clipped = geom.intersection(tile_box)
                if not clipped.is_empty and clipped.area > 0:
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

    # Calculate building pixel ratio
    building_pixels = np.sum(mask == CLASS_BUILDING)
    total_pixels = width * height
    ratio = building_pixels / total_pixels

    return mask, len(shapes_to_rasterize), ratio


def generate_building_focused_tiles(
    bbox: List[float],
    features: List[Dict],
    tree: Optional[STRtree],
    n_tiles: int,
    min_building_ratio: float = 0.01  # At least 1% buildings
) -> List[Tuple[float, float, float, float]]:
    """
    Generate tiles centered on building clusters.

    This ensures we get tiles with good building coverage for training.
    """
    west, south, east, north = bbox

    # Calculate grid dimensions
    x_tiles = int((east - west) / TILE_DEG)
    y_tiles = int((north - south) / TILE_DEG)

    print(f"Grid size: {x_tiles} x {y_tiles} = {x_tiles * y_tiles} possible tiles")

    # Score all tiles by building coverage
    scored_tiles = []

    for xi in range(x_tiles):
        for yi in range(y_tiles):
            tile_west = west + xi * TILE_DEG
            tile_south = south + yi * TILE_DEG
            tile_east = tile_west + TILE_DEG
            tile_north = tile_south + TILE_DEG

            tile_box = box(tile_west, tile_south, tile_east, tile_north)

            # Quick check: count buildings in tile
            building_count = 0
            total_area = 0

            if tree is not None:
                candidate_indices = tree.query(tile_box)
                for idx in candidate_indices:
                    try:
                        geom = shape(features[idx]['geometry'])
                        if geom.intersects(tile_box):
                            clipped = geom.intersection(tile_box)
                            if not clipped.is_empty:
                                building_count += 1
                                total_area += clipped.area
                    except:
                        pass

            if building_count > 0:
                scored_tiles.append({
                    'bounds': (tile_west, tile_south, tile_east, tile_north),
                    'building_count': building_count,
                    'building_area': total_area,
                    'score': building_count * (1 + total_area * 10000)  # Favor tiles with more/larger buildings
                })

    # Sort by score (descending) and select top tiles
    scored_tiles.sort(key=lambda t: t['score'], reverse=True)

    print(f"Found {len(scored_tiles)} tiles with buildings")

    # Take best tiles, but also include some diversity
    selected = []

    # Top 70% from highest-scoring
    n_best = int(n_tiles * 0.7)
    for tile in scored_tiles[:n_best]:
        selected.append(tile['bounds'])

    # Remaining 30% randomly from tiles with buildings
    remaining = scored_tiles[n_best:]
    random.shuffle(remaining)
    for tile in remaining[:n_tiles - len(selected)]:
        selected.append(tile['bounds'])

    # If we still need more, add random tiles (background examples)
    if len(selected) < n_tiles:
        n_background = n_tiles - len(selected)
        print(f"Adding {n_background} background tiles for negative examples")

        for _ in range(n_background * 3):
            if len(selected) >= n_tiles:
                break

            tile_west = random.uniform(west, east - TILE_DEG)
            tile_south = random.uniform(south, north - TILE_DEG)
            bounds = (tile_west, tile_south, tile_west + TILE_DEG, tile_south + TILE_DEG)

            # Check not already selected
            is_dup = any(
                abs(b[0] - bounds[0]) < TILE_DEG/2 and abs(b[1] - bounds[1]) < TILE_DEG/2
                for b in selected
            )
            if not is_dup:
                selected.append(bounds)

    return selected[:n_tiles]


def main():
    parser = argparse.ArgumentParser(description='Match OSM buildings to historical map for training')
    parser.add_argument('--year', '-y', type=str, default='1904',
                        choices=list(WMS_SOURCES.keys()),
                        help='Historical map year')
    parser.add_argument('--tiles', '-n', type=int, default=100,
                        help='Number of tiles to generate')
    parser.add_argument('--min-age', type=int, default=0,
                        help='Minimum building age in years (to filter likely old buildings)')
    parser.add_argument('--output', '-o', type=Path,
                        default=None,
                        help='Output directory (default: data/training_matched_{year})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without downloading')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed for reproducibility')

    args = parser.parse_args()
    random.seed(args.seed)

    wms_config = WMS_SOURCES[args.year]

    print("=" * 60)
    print(f"OSM-MATCHED TRAINING DATA GENERATOR")
    print("=" * 60)
    print(f"Historical map: {wms_config['name']}")
    print(f"Tiles: {args.tiles}")
    if args.min_age > 0:
        print(f"Min building age: {args.min_age} years")
    print()

    # Setup paths
    data_dir = Path('data')
    output_dir = args.output or Path(f'data/training_matched_{args.year}')
    images_dir = output_dir / 'images'
    masks_dir = output_dir / 'masks'

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(exist_ok=True)
        masks_dir.mkdir(exist_ok=True)

    # Load OSM buildings (full polygons)
    print("Loading OSM buildings with full polygon footprints...")
    features, tree = load_osm_buildings(data_dir, min_age=args.min_age)

    if not features:
        print("Error: No OSM buildings found")
        return 1

    # Generate building-focused tiles
    print("\nGenerating building-focused tiles...")
    tile_bounds = generate_building_focused_tiles(
        wms_config['bbox'],
        features,
        tree,
        args.tiles
    )

    print(f"Selected {len(tile_bounds)} tiles")

    if args.dry_run:
        print("\nDRY RUN - would generate:")
        for i, (w, s, e, n) in enumerate(tile_bounds[:5]):
            print(f"  Tile {i}: ({w:.4f}, {s:.4f}) to ({e:.4f}, {n:.4f})")
        if len(tile_bounds) > 5:
            print(f"  ... and {len(tile_bounds) - 5} more")
        return 0

    # Generate tiles
    print("\nFetching tiles and generating masks...")

    metadata = {
        'generated_at': datetime.now().isoformat(),
        'approach': 'osm_polygon_matching',
        'description': 'Training data using OSM building footprints as labels',
        'wms_source': wms_config,
        'min_building_age': args.min_age,
        'tile_size': TILE_SIZE,
        'tile_deg': TILE_DEG,
        'tiles': [],
        'stats': {
            'total_tiles': 0,
            'tiles_with_buildings': 0,
            'total_buildings': 0,
            'avg_building_ratio': 0,
        }
    }

    success_count = 0
    building_tile_count = 0
    total_buildings = 0
    total_ratio = 0

    for i, (west, south, east, north) in enumerate(tile_bounds):
        tile_id = f"tile_{i:04d}"
        print(f"\n[{i+1}/{len(tile_bounds)}] {tile_id}")

        # Fetch WMS tile
        image = fetch_wms_tile(
            wms_config['url'], wms_config['layers'],
            west, south, east, north
        )

        if image is None:
            print(f"  FAILED to fetch tile")
            continue

        # Rasterize OSM buildings
        mask, building_count, building_ratio = rasterize_buildings(
            features, tree, west, south, east, north
        )

        print(f"  Buildings: {building_count}, Coverage: {building_ratio*100:.2f}%")

        # Save
        image_path = images_dir / f"{tile_id}.png"
        mask_path = masks_dir / f"{tile_id}.png"

        image.save(image_path)
        Image.fromarray(mask).save(mask_path)

        # Update stats
        metadata['tiles'].append({
            'id': tile_id,
            'bounds': {'west': west, 'south': south, 'east': east, 'north': north},
            'building_count': building_count,
            'building_ratio': building_ratio,
        })

        success_count += 1
        if building_count > 0:
            building_tile_count += 1
        total_buildings += building_count
        total_ratio += building_ratio

    # Finalize stats
    metadata['stats'] = {
        'total_tiles': success_count,
        'tiles_with_buildings': building_tile_count,
        'total_buildings': total_buildings,
        'avg_building_ratio': total_ratio / max(1, success_count),
    }

    # Save metadata
    metadata_path = output_dir / 'metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print("\n" + "=" * 60)
    print("GENERATION COMPLETE")
    print("=" * 60)
    print(f"Successfully generated: {success_count}/{len(tile_bounds)} tiles")
    print(f"Tiles with buildings: {building_tile_count}")
    print(f"Total buildings: {total_buildings}")
    print(f"Avg building coverage: {total_ratio/max(1,success_count)*100:.2f}%")
    print(f"Output: {output_dir}")
    print()
    print("KEY ADVANTAGE: Using OSM polygon footprints provides:")
    print("  - Full building shapes (not just centroid points)")
    print("  - Higher pixel coverage for training")
    print("  - Better segmentation boundaries")
    print()
    print("NEXT STEPS:")
    print("  1. Update ml/config_1904.yaml to use this data")
    print("  2. Retrain with: cd ml && python train.py --config config_1904.yaml")
    print("  3. After training, model will detect ALL buildings on 1904 map")
    print("  4. Buildings detected but not in OSM = demolished buildings")

    return 0


if __name__ == '__main__':
    sys.exit(main())
