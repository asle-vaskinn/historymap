#!/usr/bin/env python3
"""
Prepare water training data for ML segmentation.

This script:
1. Fetches map tiles from WMS for historical maps
2. Converts water polygon annotations to raster masks
3. Organizes into training structure for U-Net

Usage:
    python scripts/ml/prepare_water_training.py --year 1880 --tiles 50
    python scripts/ml/prepare_water_training.py --year 1937 --bbox 10.38,63.42,10.44,63.45
"""

import argparse
import json
import random
import sys
from io import BytesIO
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import numpy as np
from PIL import Image

try:
    import requests
    from shapely.geometry import shape, box, mapping
    from shapely.ops import unary_union
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import from_bounds
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install with: pip install requests shapely rasterio pillow numpy")
    sys.exit(1)


# WMS sources for historical maps
WMS_SOURCES = {
    '1880': {
        'url': 'https://wms.geonorge.no/skwms1/wms.historiskekart',
        'layers': 'amt1',
        'name': 'Amtskart 1880',
        'default_bbox': [10.35, 63.38, 10.45, 63.46],
    },
    '1904': {
        'url': 'https://wms.geonorge.no/skwms1/wms.historiskekart',
        'layers': 'amt1',
        'name': 'Amtskart 1904',
        'default_bbox': [10.35, 63.38, 10.45, 63.46],
    },
    '1937': {
        'url': 'https://kart.trondheim.kommune.no/geoserver/Raster/wms',
        'layers': 'ortofoto1937',
        'name': 'Flyfoto 1937',
        'default_bbox': [10.38, 63.42, 10.44, 63.45],
    },
    '2006': {
        'url': 'https://kart.trondheim.kommune.no/geoserver/Raster/wms',
        'layers': 'ortofoto2006',
        'name': 'Flyfoto 2006',
        'default_bbox': [10.30, 63.38, 10.50, 63.48],
    },
}

# Class IDs matching ml/config.yaml
CLASS_BACKGROUND = 0
CLASS_BUILDING = 1
CLASS_ROAD = 2
CLASS_WATER = 3
CLASS_FOREST = 4

# Tile size in pixels
TILE_SIZE = 512


def fetch_wms_tile(
    url: str,
    layers: str,
    bbox: Tuple[float, float, float, float],
    size: int = TILE_SIZE
) -> Optional[Image.Image]:
    """
    Fetch a single tile from WMS.

    Args:
        url: WMS base URL
        layers: Layer name(s)
        bbox: Bounding box (west, south, east, north)
        size: Tile size in pixels

    Returns:
        PIL Image or None if failed
    """
    params = {
        'service': 'WMS',
        'version': '1.1.1',
        'request': 'GetMap',
        'layers': layers,
        'styles': '',
        'format': 'image/png',
        'srs': 'EPSG:4326',
        'width': size,
        'height': size,
        'bbox': f'{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}',
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            return Image.open(BytesIO(response.content)).convert('RGB')
        else:
            print(f"  WMS error: {response.status_code}")
            return None
    except Exception as e:
        print(f"  WMS fetch failed: {e}")
        return None


def load_water_polygons(geojson_path: Path) -> List[Dict]:
    """Load water polygons from GeoJSON file."""
    if not geojson_path.exists():
        print(f"  Warning: Water GeoJSON not found: {geojson_path}")
        return []

    with open(geojson_path) as f:
        data = json.load(f)

    features = data.get('features', [])
    print(f"  Loaded {len(features)} water polygons")
    return features


def filter_water_for_year(
    features: List[Dict],
    year: int
) -> List[Dict]:
    """
    Filter water features to those that existed in a given year.

    Water exists if: sd <= year AND (ed is None OR ed > year)
    """
    valid = []
    for feat in features:
        props = feat.get('properties', {})
        sd = props.get('sd', 1700)  # Default: always existed
        ed = props.get('ed')  # None = still exists

        if sd <= year and (ed is None or ed > year):
            valid.append(feat)

    print(f"  {len(valid)} water features for year {year}")
    return valid


def create_water_mask(
    water_features: List[Dict],
    bbox: Tuple[float, float, float, float],
    size: int = TILE_SIZE
) -> np.ndarray:
    """
    Create water mask for a tile bounding box.

    Args:
        water_features: List of water GeoJSON features
        bbox: Tile bounding box (west, south, east, north)
        size: Tile size in pixels

    Returns:
        Numpy array with class IDs (0=background, 3=water)
    """
    # Create empty mask
    mask = np.zeros((size, size), dtype=np.uint8)

    if not water_features:
        return mask

    # Create tile bounding box polygon
    tile_box = box(bbox[0], bbox[1], bbox[2], bbox[3])

    # Collect geometries that intersect the tile
    water_geoms = []
    for feat in water_features:
        try:
            geom = shape(feat['geometry'])
            if geom.intersects(tile_box):
                # Clip to tile bounds
                clipped = geom.intersection(tile_box)
                if not clipped.is_empty:
                    water_geoms.append(clipped)
        except Exception as e:
            continue

    if not water_geoms:
        return mask

    # Create transform for rasterization
    transform = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], size, size)

    # Rasterize water polygons
    try:
        shapes = [(geom, CLASS_WATER) for geom in water_geoms]
        mask = rasterize(
            shapes,
            out_shape=(size, size),
            transform=transform,
            fill=CLASS_BACKGROUND,
            dtype=np.uint8
        )
    except Exception as e:
        print(f"    Rasterization error: {e}")

    return mask


def generate_tile_grid(
    bbox: Tuple[float, float, float, float],
    tile_count: int,
    water_features: List[Dict] = None,
    prioritize_water: bool = True
) -> List[Tuple[float, float, float, float]]:
    """
    Generate tile bounding boxes within the overall bbox.

    Args:
        bbox: Overall bounding box
        tile_count: Number of tiles to generate
        water_features: If provided, prioritize tiles with water
        prioritize_water: Whether to focus on water areas

    Returns:
        List of tile bounding boxes
    """
    west, south, east, north = bbox
    width = east - west
    height = north - south

    # Approximate tile size in degrees (for 512px at these latitudes)
    # At 63°N, 1 degree longitude ≈ 50km, so 0.002° ≈ 100m ≈ reasonable tile
    tile_size_deg = 0.002

    tiles = []

    if prioritize_water and water_features:
        # Generate tiles centered on water features
        water_geoms = [shape(f['geometry']) for f in water_features
                      if f.get('geometry')]
        if water_geoms:
            water_union = unary_union(water_geoms)
            water_bounds = water_union.bounds

            # Generate more tiles near water
            for _ in range(tile_count * 2):  # Generate extra, will filter
                # Random point near water
                cx = random.uniform(water_bounds[0] - 0.01, water_bounds[2] + 0.01)
                cy = random.uniform(water_bounds[1] - 0.01, water_bounds[3] + 0.01)

                # Create tile bbox
                tile_bbox = (
                    cx - tile_size_deg / 2,
                    cy - tile_size_deg / 2,
                    cx + tile_size_deg / 2,
                    cy + tile_size_deg / 2
                )

                # Check if within overall bbox
                if (tile_bbox[0] >= west and tile_bbox[2] <= east and
                    tile_bbox[1] >= south and tile_bbox[3] <= north):
                    tiles.append(tile_bbox)

                if len(tiles) >= tile_count:
                    break

    # Fill remaining with random tiles
    while len(tiles) < tile_count:
        cx = random.uniform(west + tile_size_deg/2, east - tile_size_deg/2)
        cy = random.uniform(south + tile_size_deg/2, north - tile_size_deg/2)

        tile_bbox = (
            cx - tile_size_deg / 2,
            cy - tile_size_deg / 2,
            cx + tile_size_deg / 2,
            cy + tile_size_deg / 2
        )
        tiles.append(tile_bbox)

    return tiles[:tile_count]


def prepare_training_data(
    year: str,
    output_dir: Path,
    tile_count: int = 50,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    water_geojson: Optional[Path] = None
) -> bool:
    """
    Prepare training data for a specific map year.

    Args:
        year: Map year (e.g., '1880', '1937')
        output_dir: Output directory for training data
        tile_count: Number of tiles to generate
        bbox: Custom bounding box (default from WMS_SOURCES)
        water_geojson: Path to water polygons GeoJSON

    Returns:
        True if successful
    """
    if year not in WMS_SOURCES:
        print(f"Error: Unknown year '{year}'. Available: {list(WMS_SOURCES.keys())}")
        return False

    wms_config = WMS_SOURCES[year]
    if bbox is None:
        bbox = tuple(wms_config['default_bbox'])

    print(f"\nPreparing training data for {wms_config['name']}...")
    print(f"  Bbox: {bbox}")
    print(f"  Tiles: {tile_count}")

    # Create output directories
    year_dir = output_dir / year
    images_dir = year_dir / 'images'
    masks_dir = year_dir / 'masks'
    metadata_dir = year_dir / 'metadata'

    for d in [images_dir, masks_dir, metadata_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Load water polygons
    if water_geojson is None:
        # Try default locations
        script_dir = Path(__file__).parent.parent.parent
        water_geojson = script_dir / 'data' / 'sources' / 'manual' / 'water.geojson'
        if not water_geojson.exists():
            water_geojson = script_dir / 'data' / 'sources' / 'osm' / 'water.geojson'

    water_features = load_water_polygons(water_geojson)
    water_for_year = filter_water_for_year(water_features, int(year))

    # Generate tile grid
    print(f"\nGenerating {tile_count} tiles...")
    tiles = generate_tile_grid(bbox, tile_count, water_for_year)

    # Fetch tiles and create masks
    successful = 0
    water_tiles = 0

    for i, tile_bbox in enumerate(tiles):
        tile_id = f"{year}_{i:04d}"

        # Fetch WMS tile
        image = fetch_wms_tile(
            wms_config['url'],
            wms_config['layers'],
            tile_bbox
        )

        if image is None:
            print(f"  [{i+1}/{tile_count}] Failed to fetch tile")
            continue

        # Create water mask
        mask = create_water_mask(water_for_year, tile_bbox)
        has_water = np.any(mask == CLASS_WATER)

        # Save image
        image_path = images_dir / f"{tile_id}.png"
        image.save(image_path)

        # Save mask
        mask_path = masks_dir / f"{tile_id}.png"
        Image.fromarray(mask).save(mask_path)

        # Save metadata
        metadata = {
            'tile_id': tile_id,
            'year': year,
            'bbox': tile_bbox,
            'wms_url': wms_config['url'],
            'wms_layers': wms_config['layers'],
            'has_water': has_water,
            'water_pixels': int(np.sum(mask == CLASS_WATER)),
        }

        metadata_path = metadata_dir / f"{tile_id}.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        successful += 1
        if has_water:
            water_tiles += 1

        status = "water" if has_water else "no water"
        print(f"  [{i+1}/{tile_count}] {tile_id} - {status}")

    # Write summary
    summary = {
        'year': year,
        'wms_source': wms_config['name'],
        'bbox': bbox,
        'total_tiles': successful,
        'tiles_with_water': water_tiles,
        'tile_size': TILE_SIZE,
        'classes': {
            'background': CLASS_BACKGROUND,
            'building': CLASS_BUILDING,
            'road': CLASS_ROAD,
            'water': CLASS_WATER,
            'forest': CLASS_FOREST,
        }
    }

    summary_path = year_dir / 'summary.json'
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*50}")
    print(f"Training data prepared for {year}")
    print(f"  Total tiles: {successful}")
    print(f"  Tiles with water: {water_tiles}")
    print(f"  Output: {year_dir}")
    print(f"{'='*50}")

    return successful > 0


def main():
    parser = argparse.ArgumentParser(
        description='Prepare water training data for ML segmentation'
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
        default=50,
        help='Number of tiles to generate (default: 50)'
    )
    parser.add_argument(
        '--bbox', '-b',
        type=str,
        default=None,
        help='Bounding box: west,south,east,north (default: from config)'
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=None,
        help='Output directory (default: data/training_water)'
    )
    parser.add_argument(
        '--water', '-w',
        type=Path,
        default=None,
        help='Path to water polygons GeoJSON'
    )

    args = parser.parse_args()

    # Parse bbox if provided
    bbox = None
    if args.bbox:
        try:
            parts = [float(x) for x in args.bbox.split(',')]
            if len(parts) != 4:
                raise ValueError("Need 4 values")
            bbox = tuple(parts)
        except Exception as e:
            print(f"Error parsing bbox: {e}")
            sys.exit(1)

    # Set output directory
    if args.output is None:
        script_dir = Path(__file__).parent.parent.parent
        output_dir = script_dir / 'data' / 'training_water'
    else:
        output_dir = args.output

    # Prepare training data
    success = prepare_training_data(
        year=args.year,
        output_dir=output_dir,
        tile_count=args.tiles,
        bbox=bbox,
        water_geojson=args.water
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
