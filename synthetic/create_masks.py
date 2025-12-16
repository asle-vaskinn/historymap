#!/usr/bin/env python3
"""
create_masks.py - Generate ground truth segmentation masks from vector data

This script creates pixel-perfect segmentation masks aligned with rendered map tiles.
It uses the same tile coordinates and projection as the renderer to ensure alignment.

Classes (pixel values):
    0: background
    1: building
    2: road
    3: water
    4: forest/vegetation

Usage:
    python create_masks.py --z 15 --x 17234 --y 9345 --output mask.png
    python create_masks.py --bbox 10.3,63.4,10.4,63.5 --output mask.png
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Tuple, Optional, Dict, List
from io import BytesIO

try:
    import requests
    from PIL import Image, ImageDraw
    import numpy as np
except ImportError as e:
    print(f"Error: Missing required dependency: {e}")
    print("Install with: pip install requests pillow numpy")
    sys.exit(1)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Class definitions
CLASS_BACKGROUND = 0
CLASS_BUILDING = 1
CLASS_ROAD = 2
CLASS_WATER = 3
CLASS_FOREST = 4

# Priority order for overlapping features (higher priority wins)
CLASS_PRIORITY = {
    CLASS_WATER: 4,
    CLASS_BUILDING: 3,
    CLASS_ROAD: 2,
    CLASS_FOREST: 1,
    CLASS_BACKGROUND: 0
}

# OSM layer mappings to classes
LAYER_CLASS_MAP = {
    'water': CLASS_WATER,
    'waterway': CLASS_WATER,
    'building': CLASS_BUILDING,
    'road': CLASS_ROAD,
    'highway': CLASS_ROAD,
    'landuse': CLASS_FOREST,  # Will check properties for forest/wood
    'natural': CLASS_FOREST,  # Will check for wood/tree
}


def tile_to_bbox(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
    """
    Convert tile coordinates (z, x, y) to bounding box (west, south, east, north).

    Args:
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate

    Returns:
        Tuple of (west, south, east, north) in EPSG:4326
    """
    n = 2.0 ** z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0

    import math
    north_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    south_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))
    north = math.degrees(north_rad)
    south = math.degrees(south_rad)

    return (west, south, east, north)


def bbox_to_tile(west: float, south: float, east: float, north: float,
                 zoom: int = 15) -> Tuple[int, int, int]:
    """
    Convert bounding box to tile coordinates at given zoom level.
    Returns the tile at the center of the bbox.

    Args:
        west, south, east, north: Bounding box coordinates
        zoom: Zoom level

    Returns:
        Tuple of (z, x, y)
    """
    import math

    # Calculate center point
    lon = (west + east) / 2
    lat = (north + south) / 2

    n = 2.0 ** zoom
    x = int((lon + 180.0) / 360.0 * n)

    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)

    return (zoom, x, y)


def fetch_vector_tile(z: int, x: int, y: int) -> Optional[bytes]:
    """
    Fetch vector tile data from OSM tile server.

    Args:
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate

    Returns:
        Vector tile data as bytes, or None if fetch fails
    """
    # Using OpenMapTiles CDN for vector tiles
    url = f"https://api.maptiler.com/tiles/v3/{z}/{x}/{y}.pbf"

    # Alternative: Use local PMTiles if available
    # For now, we'll use Overpass API to get raw OSM data

    # Get bounding box for this tile
    bbox = tile_to_bbox(z, x, y)
    west, south, east, north = bbox

    # Use Overpass API to get OSM data
    overpass_url = "https://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:json][timeout:25];
    (
      way["building"]({south},{west},{north},{east});
      way["highway"]({south},{west},{north},{east});
      way["waterway"]({south},{west},{north},{east});
      way["natural"~"water|wood|tree_row"]({south},{west},{north},{east});
      way["landuse"~"forest|wood"]({south},{west},{north},{east});
      relation["building"]({south},{west},{north},{east});
      relation["natural"="water"]({south},{west},{north},{east});
    );
    out geom;
    """

    try:
        logger.info(f"Fetching OSM data for tile {z}/{x}/{y} from Overpass API")
        response = requests.post(
            overpass_url,
            data={'data': overpass_query},
            timeout=30
        )
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        logger.error(f"Failed to fetch vector data: {e}")
        return None


def lon_to_pixel(lon: float, bbox: Tuple[float, float, float, float],
                 width: int) -> int:
    """Convert longitude to pixel X coordinate."""
    west, south, east, north = bbox
    return int((lon - west) / (east - west) * width)


def lat_to_pixel(lat: float, bbox: Tuple[float, float, float, float],
                 height: int) -> int:
    """Convert latitude to pixel Y coordinate."""
    west, south, east, north = bbox
    # Note: Y coordinates are inverted (north at top)
    return int((north - lat) / (north - south) * height)


def classify_feature(element: Dict) -> int:
    """
    Determine the class of an OSM element based on its tags.

    Args:
        element: OSM element dictionary

    Returns:
        Class ID (0-4)
    """
    tags = element.get('tags', {})

    # Water features
    if 'waterway' in tags or tags.get('natural') == 'water':
        return CLASS_WATER

    # Buildings
    if 'building' in tags:
        return CLASS_BUILDING

    # Roads/highways
    if 'highway' in tags:
        return CLASS_ROAD

    # Forest/vegetation
    if tags.get('natural') in ['wood', 'tree_row'] or \
       tags.get('landuse') in ['forest', 'wood']:
        return CLASS_FOREST

    return CLASS_BACKGROUND


def draw_feature(draw: ImageDraw.Draw, element: Dict, bbox: Tuple[float, float, float, float],
                 width: int, height: int, class_id: int):
    """
    Draw a single OSM feature onto the mask.

    Args:
        draw: PIL ImageDraw object
        element: OSM element dictionary
        bbox: Bounding box (west, south, east, north)
        width: Image width in pixels
        height: Image height in pixels
        class_id: Class ID to draw (1-4)
    """
    if element['type'] == 'way':
        if 'geometry' not in element:
            return

        # Convert coordinates to pixels
        coords = []
        for node in element['geometry']:
            x = lon_to_pixel(node['lon'], bbox, width)
            y = lat_to_pixel(node['lat'], bbox, height)
            coords.append((x, y))

        if len(coords) < 2:
            return

        # Check if it's a closed polygon (building or area)
        is_closed = (coords[0] == coords[-1]) or \
                   (len(coords) >= 3 and element.get('tags', {}).get('building'))

        if is_closed and len(coords) >= 3:
            # Draw filled polygon
            draw.polygon(coords, fill=class_id)
        else:
            # Draw line (for roads, waterways)
            # Use wider lines for better visibility
            line_width = 3 if class_id == CLASS_ROAD else 5
            draw.line(coords, fill=class_id, width=line_width)

    elif element['type'] == 'relation':
        # Handle multipolygons (e.g., complex buildings, water bodies)
        for member in element.get('members', []):
            if 'geometry' in member:
                coords = []
                for node in member['geometry']:
                    x = lon_to_pixel(node['lon'], bbox, width)
                    y = lat_to_pixel(node['lat'], bbox, height)
                    coords.append((x, y))

                if len(coords) >= 3:
                    draw.polygon(coords, fill=class_id)


def create_mask(z: int, x: int, y: int, size: int = 512) -> Optional[np.ndarray]:
    """
    Create segmentation mask for a tile.

    Args:
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate
        size: Output image size (default 512x512)

    Returns:
        Numpy array of shape (size, size) with class IDs, or None on failure
    """
    # Fetch vector data
    data = fetch_vector_tile(z, x, y)
    if data is None:
        return None

    # Parse JSON response from Overpass
    try:
        osm_data = json.loads(data)
        elements = osm_data.get('elements', [])
        logger.info(f"Found {len(elements)} OSM elements")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OSM data: {e}")
        return None

    # Get bounding box for coordinate conversion
    bbox = tile_to_bbox(z, x, y)

    # Create layers for each class (to handle priority)
    layers = {
        CLASS_WATER: Image.new('L', (size, size), 0),
        CLASS_BUILDING: Image.new('L', (size, size), 0),
        CLASS_ROAD: Image.new('L', (size, size), 0),
        CLASS_FOREST: Image.new('L', (size, size), 0),
    }

    # Draw features on appropriate layers
    for element in elements:
        class_id = classify_feature(element)
        if class_id == CLASS_BACKGROUND:
            continue

        draw = ImageDraw.Draw(layers[class_id])
        draw_feature(draw, element, bbox, size, size, 1)  # Draw as 1, we'll multiply later

    # Combine layers with priority (higher priority overwrites lower)
    final_mask = np.zeros((size, size), dtype=np.uint8)

    # Sort classes by priority (lowest first)
    sorted_classes = sorted(CLASS_PRIORITY.keys(), key=lambda k: CLASS_PRIORITY[k])

    for class_id in sorted_classes:
        if class_id == CLASS_BACKGROUND:
            continue
        layer_array = np.array(layers[class_id])
        # Where layer has pixels, set to class_id
        final_mask[layer_array > 0] = class_id

    logger.info(f"Mask created with {len(np.unique(final_mask))} unique classes")
    logger.info(f"Class distribution: {[(i, np.sum(final_mask == i)) for i in range(5)]}")

    return final_mask


def save_mask(mask: np.ndarray, output_path: str):
    """
    Save mask as single-channel PNG.

    Args:
        mask: Numpy array with class IDs
        output_path: Output file path
    """
    # Ensure it's uint8
    mask = mask.astype(np.uint8)

    # Save as grayscale PNG
    img = Image.fromarray(mask, mode='L')
    img.save(output_path)
    logger.info(f"Mask saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate ground truth segmentation masks from vector data'
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--tile',
        type=str,
        help='Tile coordinates as z/x/y (e.g., 15/17234/9345)'
    )
    input_group.add_argument(
        '--zxy',
        nargs=3,
        type=int,
        metavar=('Z', 'X', 'Y'),
        help='Tile coordinates as separate arguments'
    )
    input_group.add_argument(
        '--bbox',
        type=str,
        help='Bounding box as west,south,east,north'
    )

    # Output options
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Output mask file path (.png)'
    )
    parser.add_argument(
        '--size',
        type=int,
        default=512,
        help='Output image size (default: 512x512)'
    )
    parser.add_argument(
        '--zoom',
        type=int,
        default=15,
        help='Zoom level when using --bbox (default: 15)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Parse input coordinates
    if args.tile:
        parts = args.tile.split('/')
        if len(parts) != 3:
            logger.error("Tile format must be z/x/y")
            sys.exit(1)
        z, x, y = map(int, parts)
    elif args.zxy:
        z, x, y = args.zxy
    elif args.bbox:
        parts = args.bbox.split(',')
        if len(parts) != 4:
            logger.error("Bbox format must be west,south,east,north")
            sys.exit(1)
        west, south, east, north = map(float, parts)
        z, x, y = bbox_to_tile(west, south, east, north, args.zoom)
        logger.info(f"Converted bbox to tile {z}/{x}/{y}")
    else:
        logger.error("No input coordinates specified")
        sys.exit(1)

    # Validate tile coordinates
    max_tile = 2 ** z
    if not (0 <= x < max_tile and 0 <= y < max_tile):
        logger.error(f"Invalid tile coordinates for zoom {z}: {x}/{y}")
        sys.exit(1)

    # Create output directory if needed
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate mask
    logger.info(f"Generating mask for tile {z}/{x}/{y}")
    mask = create_mask(z, x, y, args.size)

    if mask is None:
        logger.error("Failed to create mask")
        sys.exit(1)

    # Save mask
    save_mask(mask, str(output_path))

    # Print statistics
    print(f"\nMask Statistics:")
    print(f"  Size: {mask.shape}")
    print(f"  Classes present: {sorted(np.unique(mask))}")
    print(f"  Pixel counts:")
    for class_id in range(5):
        count = np.sum(mask == class_id)
        pct = count / mask.size * 100
        class_names = ['background', 'building', 'road', 'water', 'forest']
        print(f"    {class_names[class_id]}: {count} ({pct:.2f}%)")


if __name__ == '__main__':
    main()
