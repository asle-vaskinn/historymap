#!/usr/bin/env python3
"""
Bootstrap water training data from OSM water polygons.

This script automatically generates training data by:
1. Loading existing OSM water polygons
2. Fetching map tiles from WMS for each historical year
3. Rasterizing OSM water onto tiles as class 3 masks

This provides a baseline training dataset. For areas where historical
water differs from current OSM (filled harbors, changed shorelines),
manual annotation or correction is still needed.

Usage:
    python scripts/ml/bootstrap_water_training.py --year 1937 --tiles 100
    python scripts/ml/bootstrap_water_training.py --year 1880 --tiles 50 --focus-water
"""

import argparse
import json
import random
import sys
from io import BytesIO
from pathlib import Path
from typing import List, Tuple, Optional, Dict

import numpy as np
from PIL import Image

try:
    import requests
    from shapely.geometry import shape, box
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    print("Warning: shapely not installed. pip install shapely")

try:
    from rasterio.features import rasterize
    from rasterio.transform import from_bounds
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    print("Warning: rasterio not installed. pip install rasterio")


# WMS sources for historical maps
WMS_SOURCES = {
    '1880': {
        'url': 'https://wms.geonorge.no/skwms1/wms.historiskekart',
        'layers': 'amt1',
        'name': 'Amtskart 1880',
        'bbox': [10.30, 63.38, 10.50, 63.48],
    },
    '1904': {
        'url': 'https://wms.geonorge.no/skwms1/wms.historiskekart',
        'layers': 'amt1',
        'name': 'Amtskart 1904',
        'bbox': [10.30, 63.38, 10.50, 63.48],
    },
    '1937': {
        'url': 'https://kart.trondheim.kommune.no/geoserver/Raster/wms',
        'layers': 'ortofoto1937',
        'name': 'Flyfoto 1937',
        'bbox': [10.38, 63.42, 10.44, 63.45],
    },
    '2006': {
        'url': 'https://kart.trondheim.kommune.no/geoserver/Raster/wms',
        'layers': 'ortofoto2006',
        'name': 'Flyfoto 2006',
        'bbox': [10.30, 63.38, 10.50, 63.48],
    },
}

# Class IDs
CLASS_BACKGROUND = 0
CLASS_WATER = 3

# Tile size
TILE_SIZE = 512
TILE_DEG = 0.003  # ~150m at 63°N


def load_osm_water(data_dir: Path) -> List[Dict]:
    """Load OSM water polygons."""
    water_path = data_dir / 'sources' / 'osm' / 'water.geojson'

    if not water_path.exists():
        print(f"Error: OSM water not found at {water_path}")
        print("Run: python scripts/ingest/fetch_osm_water.py first")
        return []

    with open(water_path) as f:
        data = json.load(f)

    features = data.get('features', [])
    print(f"Loaded {len(features)} OSM water features")
    return features


def build_water_index(features: List[Dict]) -> Tuple[List, List, Optional[STRtree]]:
    """Build spatial index for water polygons."""
    if not HAS_SHAPELY:
        return [], features, None

    geometries = []
    indexed_features = []

    for feat in features:
        try:
            geom = shape(feat['geometry'])
            if geom.is_valid and not geom.is_empty:
                geometries.append(geom)
                indexed_features.append(feat)
        except Exception:
            continue

    if not geometries:
        return [], [], None

    index = STRtree(geometries)
    return geometries, indexed_features, index


def fetch_wms_tile(url: str, layers: str, bbox: Tuple[float, float, float, float]) -> Optional[Image.Image]:
    """Fetch a single tile from WMS."""
    params = {
        'service': 'WMS',
        'version': '1.1.1',
        'request': 'GetMap',
        'layers': layers,
        'styles': '',
        'format': 'image/png',
        'srs': 'EPSG:4326',
        'width': TILE_SIZE,
        'height': TILE_SIZE,
        'bbox': f'{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}',
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200 and 'image' in response.headers.get('content-type', ''):
            return Image.open(BytesIO(response.content)).convert('RGB')
    except Exception as e:
        pass

    return None


def create_water_mask(
    tile_bbox: Tuple[float, float, float, float],
    water_geometries: List,
    water_index: Optional[STRtree]
) -> np.ndarray:
    """Create water mask for a tile using OSM water polygons."""
    mask = np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.uint8)

    if not HAS_RASTERIO or not HAS_SHAPELY:
        return mask

    if not water_geometries:
        return mask

    # Create tile box
    tile_box = box(tile_bbox[0], tile_bbox[1], tile_bbox[2], tile_bbox[3])

    # Find intersecting water geometries
    if water_index:
        candidate_indices = water_index.query(tile_box)
        candidates = [water_geometries[i] for i in candidate_indices]
    else:
        candidates = water_geometries

    # Collect clipped geometries
    water_shapes = []
    for geom in candidates:
        try:
            if geom.intersects(tile_box):
                clipped = geom.intersection(tile_box)
                if not clipped.is_empty:
                    water_shapes.append((clipped, CLASS_WATER))
        except Exception:
            continue

    if not water_shapes:
        return mask

    # Rasterize
    transform = from_bounds(tile_bbox[0], tile_bbox[1], tile_bbox[2], tile_bbox[3], TILE_SIZE, TILE_SIZE)

    try:
        mask = rasterize(
            water_shapes,
            out_shape=(TILE_SIZE, TILE_SIZE),
            transform=transform,
            fill=CLASS_BACKGROUND,
            dtype=np.uint8
        )
    except Exception:
        pass

    return mask


def generate_tile_positions(
    map_bbox: List[float],
    tile_count: int,
    water_geometries: List,
    water_index: Optional[STRtree],
    focus_water: bool = True,
    water_ratio: float = 0.7
) -> List[Tuple[float, float, float, float]]:
    """Generate tile positions, optionally focusing on water areas."""
    west, south, east, north = map_bbox
    tiles = []

    if focus_water and water_geometries and HAS_SHAPELY:
        # Calculate water bounds
        water_union = unary_union(water_geometries)
        water_bounds = water_union.bounds

        # Generate tiles near water
        water_tiles_needed = int(tile_count * water_ratio)

        for _ in range(water_tiles_needed * 3):  # Generate extra, will filter
            if len(tiles) >= water_tiles_needed:
                break

            # Random point near water
            cx = random.uniform(
                max(west, water_bounds[0] - 0.02),
                min(east, water_bounds[2] + 0.02)
            )
            cy = random.uniform(
                max(south, water_bounds[1] - 0.02),
                min(north, water_bounds[3] + 0.02)
            )

            tile_bbox = (
                cx - TILE_DEG / 2,
                cy - TILE_DEG / 2,
                cx + TILE_DEG / 2,
                cy + TILE_DEG / 2
            )

            # Check if within map bounds
            if (tile_bbox[0] >= west and tile_bbox[2] <= east and
                tile_bbox[1] >= south and tile_bbox[3] <= north):

                # Check if tile contains water
                tile_box = box(*tile_bbox)
                has_water = False
                if water_index:
                    candidates = water_index.query(tile_box)
                    for idx in candidates:
                        if water_geometries[idx].intersects(tile_box):
                            has_water = True
                            break

                if has_water:
                    tiles.append(tile_bbox)

    # Fill remaining with random tiles (including non-water for negative examples)
    attempts = 0
    while len(tiles) < tile_count and attempts < tile_count * 5:
        attempts += 1

        cx = random.uniform(west + TILE_DEG/2, east - TILE_DEG/2)
        cy = random.uniform(south + TILE_DEG/2, north - TILE_DEG/2)

        tile_bbox = (
            cx - TILE_DEG / 2,
            cy - TILE_DEG / 2,
            cx + TILE_DEG / 2,
            cy + TILE_DEG / 2
        )

        # Avoid duplicates
        is_duplicate = False
        for existing in tiles:
            if abs(existing[0] - tile_bbox[0]) < TILE_DEG / 2:
                if abs(existing[1] - tile_bbox[1]) < TILE_DEG / 2:
                    is_duplicate = True
                    break

        if not is_duplicate:
            tiles.append(tile_bbox)

    return tiles[:tile_count]


def bootstrap_training_data(
    year: str,
    output_dir: Path,
    data_dir: Path,
    tile_count: int = 100,
    focus_water: bool = True
) -> bool:
    """
    Bootstrap training data from OSM water.

    Args:
        year: Map year (1880, 1937, etc.)
        output_dir: Output directory for training data
        data_dir: Data directory (contains sources/osm/water.geojson)
        tile_count: Number of tiles to generate
        focus_water: Whether to focus tiles on water areas

    Returns:
        True if successful
    """
    if year not in WMS_SOURCES:
        print(f"Error: Unknown year '{year}'. Available: {list(WMS_SOURCES.keys())}")
        return False

    if not HAS_SHAPELY or not HAS_RASTERIO:
        print("Error: shapely and rasterio are required")
        print("Install with: pip install shapely rasterio")
        return False

    wms_config = WMS_SOURCES[year]

    print(f"\n{'='*60}")
    print(f"Bootstrapping water training data for {wms_config['name']}")
    print(f"{'='*60}")

    # Load OSM water
    water_features = load_osm_water(data_dir)
    if not water_features:
        return False

    # Build spatial index
    print("Building spatial index...")
    water_geoms, indexed_features, water_index = build_water_index(water_features)
    print(f"  Indexed {len(water_geoms)} valid water geometries")

    # Create output directories
    year_dir = output_dir / year
    images_dir = year_dir / 'images'
    masks_dir = year_dir / 'masks'

    for d in [images_dir, masks_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Generate tile positions
    print(f"\nGenerating {tile_count} tile positions...")
    tiles = generate_tile_positions(
        wms_config['bbox'],
        tile_count,
        water_geoms,
        water_index,
        focus_water=focus_water
    )
    print(f"  Generated {len(tiles)} tile positions")

    # Fetch tiles and create masks
    print(f"\nFetching tiles from WMS and creating masks...")

    successful = 0
    with_water = 0
    failed = 0

    for i, tile_bbox in enumerate(tiles):
        tile_id = f"{year}_{i:04d}"

        # Fetch WMS tile
        image = fetch_wms_tile(wms_config['url'], wms_config['layers'], tile_bbox)

        if image is None:
            failed += 1
            continue

        # Create water mask from OSM
        mask = create_water_mask(tile_bbox, water_geoms, water_index)
        has_water = np.any(mask == CLASS_WATER)

        # Save image
        image.save(images_dir / f"{tile_id}.png")

        # Save mask
        Image.fromarray(mask).save(masks_dir / f"{tile_id}.png")

        successful += 1
        if has_water:
            with_water += 1

        # Progress
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(tiles)}] {successful} ok, {with_water} with water, {failed} failed")

    # Write metadata
    metadata = {
        'year': year,
        'wms_source': wms_config['name'],
        'wms_url': wms_config['url'],
        'total_tiles': successful,
        'tiles_with_water': with_water,
        'tiles_without_water': successful - with_water,
        'failed_tiles': failed,
        'tile_size': TILE_SIZE,
        'tile_degrees': TILE_DEG,
        'focus_water': focus_water,
        'source': 'osm_bootstrap',
        'note': 'Masks generated from current OSM water. Historical differences need manual correction.'
    }

    with open(year_dir / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"BOOTSTRAP COMPLETE: {year}")
    print(f"{'='*60}")
    print(f"  Total tiles: {successful}")
    print(f"  With water: {with_water} ({100*with_water/max(1,successful):.1f}%)")
    print(f"  Without water: {successful - with_water} ({100*(successful-with_water)/max(1,successful):.1f}%)")
    print(f"  Failed: {failed}")
    print(f"  Output: {year_dir}")
    print(f"{'='*60}")
    print()
    print("NOTE: These masks are based on CURRENT OSM water.")
    print("For historical maps, areas that have been filled (harbors, etc.)")
    print("will have INCORRECT masks. Use source_viewer to correct them.")

    return successful > 0


def main():
    parser = argparse.ArgumentParser(
        description='Bootstrap water training data from OSM'
    )
    parser.add_argument(
        '--year', '-y',
        required=True,
        choices=list(WMS_SOURCES.keys()),
        help=f'Map year: {list(WMS_SOURCES.keys())}'
    )
    parser.add_argument(
        '--tiles', '-n',
        type=int,
        default=100,
        help='Number of tiles to generate (default: 100)'
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=None,
        help='Output directory (default: data/training_water)'
    )
    parser.add_argument(
        '--focus-water',
        action='store_true',
        default=True,
        help='Focus tiles on water areas (default: True)'
    )
    parser.add_argument(
        '--no-focus-water',
        action='store_true',
        help='Distribute tiles randomly instead of focusing on water'
    )

    args = parser.parse_args()

    # Determine paths
    script_dir = Path(__file__).parent.parent.parent
    data_dir = script_dir / 'data'

    if args.output:
        output_dir = args.output
    else:
        output_dir = data_dir / 'training_water'

    focus_water = not args.no_focus_water

    success = bootstrap_training_data(
        year=args.year,
        output_dir=output_dir,
        data_dir=data_dir,
        tile_count=args.tiles,
        focus_water=focus_water
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
