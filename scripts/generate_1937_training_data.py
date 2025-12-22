#!/usr/bin/env python3
"""
Generate training data for 1937 aerial photo building extraction.

Uses modern OSM building footprints as pseudo-labels.
Logic: Buildings that exist today likely also existed in 1937.

Usage:
    python scripts/generate_1937_training_data.py --output data/training_1937 --tiles 50
"""

import argparse
import json
import os
import ssl
import time
import urllib.request
from pathlib import Path
from typing import List, Tuple, Dict
import math

# Optional imports - check availability
try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Warning: PIL not installed. Run: pip install Pillow")

try:
    from shapely.geometry import shape, box
    from shapely.ops import unary_union
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    print("Warning: Shapely not installed. Run: pip install shapely")


# Configuration
WMS_URL = "https://kart.trondheim.kommune.no/geoserver/Raster/wms"
WMS_LAYER = "ortofoto1937"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Tile configuration
TILE_SIZE = 512  # pixels
TILE_RESOLUTION = 0.5  # meters per pixel (approximate for 1937 photos)

# Central Trondheim area (good coverage in 1937 photos)
AREA_BOUNDS = {
    'west': 10.38,
    'south': 63.42,
    'east': 10.44,
    'north': 63.44
}

# SSL context
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


def meters_per_degree_lat():
    """Meters per degree latitude (approximately constant)."""
    return 111320


def meters_per_degree_lon(lat: float):
    """Meters per degree longitude at given latitude."""
    return 111320 * math.cos(math.radians(lat))


def generate_tile_grid(bounds: Dict, tile_size_m: float) -> List[Dict]:
    """Generate a grid of tiles covering the area."""
    tiles = []

    lat_center = (bounds['south'] + bounds['north']) / 2

    # Calculate tile size in degrees
    tile_lat = tile_size_m / meters_per_degree_lat()
    tile_lon = tile_size_m / meters_per_degree_lon(lat_center)

    # Generate grid
    lat = bounds['south']
    row = 0
    while lat < bounds['north']:
        lon = bounds['west']
        col = 0
        while lon < bounds['east']:
            tiles.append({
                'row': row,
                'col': col,
                'west': lon,
                'south': lat,
                'east': min(lon + tile_lon, bounds['east']),
                'north': min(lat + tile_lat, bounds['north'])
            })
            lon += tile_lon
            col += 1
        lat += tile_lat
        row += 1

    return tiles


def download_wms_tile(tile: Dict, output_path: Path, size: int = TILE_SIZE) -> bool:
    """Download a tile from the 1937 WMS."""
    bbox = f"{tile['west']},{tile['south']},{tile['east']},{tile['north']}"

    url = (
        f"{WMS_URL}?service=WMS&version=1.1.1&request=GetMap"
        f"&layers={WMS_LAYER}&styles=&format=image/png"
        f"&srs=EPSG:4326&bbox={bbox}&width={size}&height={size}"
    )

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as response:
            with open(output_path, 'wb') as f:
                f.write(response.read())
        return True
    except Exception as e:
        print(f"  Error downloading tile: {e}")
        return False


def fetch_osm_buildings(tile: Dict, retry: int = 3) -> List[Dict]:
    """Fetch OSM building footprints for a tile."""
    query = f"""
    [out:json][timeout:60];
    (
      way["building"]({tile['south']},{tile['west']},{tile['north']},{tile['east']});
      relation["building"]({tile['south']},{tile['west']},{tile['north']},{tile['east']});
    );
    out body;
    >;
    out skel qt;
    """

    for attempt in range(retry):
        try:
            # Rate limiting - wait between requests
            time.sleep(1.5)

            req = urllib.request.Request(
                OVERPASS_URL,
                data=query.encode('utf-8'),
                headers={'Content-Type': 'text/plain'}
            )

            with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as response:
                data = json.loads(response.read().decode('utf-8'))

            return data.get('elements', [])
        except Exception as e:
            if attempt < retry - 1:
                print(f"  Retry {attempt + 1}/{retry} after error: {e}")
                time.sleep(5)  # Wait longer before retry
            else:
                print(f"  Error fetching OSM: {e}")
                return []

    return []


def elements_to_polygons(elements: List[Dict], tile: Dict) -> List[List[Tuple[float, float]]]:
    """Convert OSM elements to polygon coordinates."""
    # Build node lookup
    nodes = {}
    for el in elements:
        if el.get('type') == 'node':
            nodes[el['id']] = (el['lon'], el['lat'])

    # Extract building polygons
    polygons = []
    for el in elements:
        if el.get('type') == 'way' and 'building' in el.get('tags', {}):
            coords = []
            for node_id in el.get('nodes', []):
                if node_id in nodes:
                    coords.append(nodes[node_id])
            if len(coords) >= 3:
                polygons.append(coords)

    return polygons


def create_mask(polygons: List[List[Tuple[float, float]]],
                tile: Dict,
                size: int = TILE_SIZE) -> 'Image':
    """Create a class index mask from building polygons.

    Mask values:
        0 = background
        1 = building
    """
    if not HAS_PIL:
        raise ImportError("PIL required for mask creation")

    # Create black image (class 0 = background)
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)

    # Convert geo coords to pixel coords
    def geo_to_pixel(lon, lat):
        x = int((lon - tile['west']) / (tile['east'] - tile['west']) * size)
        y = int((tile['north'] - lat) / (tile['north'] - tile['south']) * size)
        return (x, y)

    # Draw each polygon (class 1 = building)
    for poly_coords in polygons:
        pixel_coords = [geo_to_pixel(lon, lat) for lon, lat in poly_coords]
        if len(pixel_coords) >= 3:
            draw.polygon(pixel_coords, fill=1)

    return mask


def process_tile(tile: Dict, output_dir: Path, idx: int) -> bool:
    """Process a single tile: download image and create mask."""
    tile_name = f"tile_{idx:04d}"
    image_path = output_dir / "images" / f"{tile_name}.png"
    mask_path = output_dir / "masks" / f"{tile_name}.png"

    # Download aerial image
    print(f"  [{idx}] Downloading 1937 tile...")
    if not download_wms_tile(tile, image_path):
        return False

    # Check if image has content (not blank)
    if HAS_PIL:
        img = Image.open(image_path)
        if img.getextrema() == ((0, 0), (0, 0), (0, 0)):  # All black
            print(f"  [{idx}] Skipping blank tile")
            os.remove(image_path)
            return False

    # Fetch OSM buildings
    print(f"  [{idx}] Fetching OSM buildings...")
    elements = fetch_osm_buildings(tile)

    # Convert to polygons
    polygons = elements_to_polygons(elements, tile)

    if len(polygons) == 0:
        print(f"  [{idx}] No buildings in tile, skipping")
        os.remove(image_path)
        return False

    # Create mask
    print(f"  [{idx}] Creating mask ({len(polygons)} buildings)...")
    mask = create_mask(polygons, tile)
    mask.save(mask_path)

    # Save tile metadata
    meta = {
        'tile_name': tile_name,
        'bounds': tile,
        'num_buildings': len(polygons)
    }
    meta_path = output_dir / "metadata" / f"{tile_name}.json"
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"  [{idx}] Done: {len(polygons)} buildings")
    return True


def main():
    parser = argparse.ArgumentParser(description='Generate 1937 training data')
    parser.add_argument('--output', type=str, default='data/training_1937',
                        help='Output directory')
    parser.add_argument('--tiles', type=int, default=50,
                        help='Maximum number of tiles to generate')
    parser.add_argument('--tile-size', type=int, default=TILE_SIZE,
                        help='Tile size in pixels')
    args = parser.parse_args()

    if not HAS_PIL:
        print("Error: PIL (Pillow) is required. Install with: pip install Pillow")
        return

    output_dir = Path(args.output)

    # Create output directories
    (output_dir / "images").mkdir(parents=True, exist_ok=True)
    (output_dir / "masks").mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata").mkdir(parents=True, exist_ok=True)

    print(f"Generating training data for 1937 aerial photos")
    print(f"Output: {output_dir}")
    print(f"Area: {AREA_BOUNDS}")
    print()

    # Generate tile grid
    # Tile size in meters (512px at ~0.5m/px = 256m)
    tile_size_m = args.tile_size * TILE_RESOLUTION
    tiles = generate_tile_grid(AREA_BOUNDS, tile_size_m)

    print(f"Generated {len(tiles)} tiles in grid")
    print(f"Processing up to {args.tiles} tiles...")
    print()

    # Process tiles
    successful = 0
    for i, tile in enumerate(tiles):
        if successful >= args.tiles:
            break

        if process_tile(tile, output_dir, i):
            successful += 1

    print()
    print(f"Done! Generated {successful} training tile pairs")
    print(f"  Images: {output_dir}/images/")
    print(f"  Masks:  {output_dir}/masks/")
    print()
    print("Next steps:")
    print("  1. Review generated masks for quality")
    print("  2. Train model: python ml/train.py --config ml/config_1937.yaml")


if __name__ == '__main__':
    main()
