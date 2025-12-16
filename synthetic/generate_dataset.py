#!/usr/bin/env python3
"""
generate_dataset.py - Main pipeline for generating synthetic historical map training data

This script orchestrates the complete dataset generation process:
1. Selects random tiles from available area
2. Renders styled images using historical map styles
3. Applies aging effects
4. Generates aligned segmentation masks
5. Saves image/mask pairs with metadata

Usage:
    python generate_dataset.py --count 1000 --output ../data/synthetic
    python generate_dataset.py --count 100 --bbox 10.3,63.4,10.5,63.5 --zoom 15
    python generate_dataset.py --count 500 --styles military_1880 cadastral_1900
"""

import argparse
import json
import logging
import sys
import time
import random
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, asdict
import hashlib

try:
    from PIL import Image
    import numpy as np
    from tqdm import tqdm
except ImportError as e:
    print(f"Error: Missing required dependency: {e}")
    print("Install with: pip install pillow numpy tqdm")
    sys.exit(1)

# Import local modules
try:
    from tile_utils import TileCoordinates
    from age_effects import age_map, ERA_PRESETS
    from create_masks import create_mask
    import requests
except ImportError as e:
    print(f"Error: Missing local module or dependency: {e}")
    print("Ensure tile_utils.py, age_effects.py, and create_masks.py are in the same directory")
    print("Install requests with: pip install requests")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class SampleMetadata:
    """Metadata for a single training sample."""
    image_file: str
    mask_file: str
    tile_z: int
    tile_x: int
    tile_y: int
    style: str
    aging_intensity: float
    aging_seed: int
    bbox: List[float]  # [west, south, east, north]
    class_counts: Dict[int, int]
    timestamp: str


class DatasetGenerator:
    """Main dataset generation pipeline."""

    def __init__(
        self,
        output_dir: str,
        styles_dir: str = None,
        available_styles: List[str] = None,
        tile_size: int = 512,
        seed: Optional[int] = None
    ):
        """
        Initialize dataset generator.

        Args:
            output_dir: Base output directory for dataset
            styles_dir: Directory containing style JSON files
            available_styles: List of style names to use (without .json extension)
            tile_size: Output image/mask size in pixels
            seed: Random seed for reproducibility
        """
        self.output_dir = Path(output_dir)
        self.tile_size = tile_size
        self.seed = seed

        # Set random seeds
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        # Setup directories
        self.images_dir = self.output_dir / 'images'
        self.masks_dir = self.output_dir / 'masks'
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.masks_dir.mkdir(parents=True, exist_ok=True)

        # Load available styles
        if styles_dir is None:
            styles_dir = Path(__file__).parent / 'styles'
        self.styles_dir = Path(styles_dir)

        if available_styles is None:
            # Auto-detect available styles
            self.available_styles = self._discover_styles()
        else:
            self.available_styles = available_styles

        if not self.available_styles:
            raise ValueError(f"No styles found in {self.styles_dir}")

        logger.info(f"Initialized generator with {len(self.available_styles)} styles: {self.available_styles}")
        logger.info(f"Output directory: {self.output_dir}")

    def _discover_styles(self) -> List[str]:
        """Discover available style files."""
        if not self.styles_dir.exists():
            logger.warning(f"Styles directory not found: {self.styles_dir}")
            return []

        styles = []
        for style_file in self.styles_dir.glob('*.json'):
            style_name = style_file.stem
            styles.append(style_name)

        return sorted(styles)

    def generate_dataset(
        self,
        count: int,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        zoom: int = 15,
        aging_intensity_range: Tuple[float, float] = (0.4, 0.8),
        skip_existing: bool = True
    ) -> List[SampleMetadata]:
        """
        Generate dataset with N image/mask pairs.

        Args:
            count: Number of samples to generate
            bbox: Bounding box (west, south, east, north) to sample tiles from.
                  If None, uses Trondheim area default.
            zoom: Zoom level for tiles
            aging_intensity_range: Min and max intensity for aging effects
            skip_existing: Skip samples if output files already exist

        Returns:
            List of sample metadata
        """
        # Default to Trondheim area if no bbox specified
        if bbox is None:
            # Trondheim approximate bounds
            bbox = (10.2, 63.35, 10.6, 63.48)

        logger.info(f"Generating {count} samples")
        logger.info(f"Bounding box: {bbox}")
        logger.info(f"Zoom level: {zoom}")

        # Generate tile list
        tiles = self._generate_tile_list(bbox, zoom, count)

        metadata_list = []
        successful = 0
        failed = 0

        # Progress bar
        with tqdm(total=count, desc="Generating dataset") as pbar:
            for i in range(count):
                try:
                    # Select random tile
                    tile_z, tile_x, tile_y = tiles[i % len(tiles)]

                    # Generate unique sample ID
                    sample_id = self._generate_sample_id(tile_z, tile_x, tile_y, i)

                    # Check if already exists
                    image_file = self.images_dir / f"{sample_id}.png"
                    mask_file = self.masks_dir / f"{sample_id}.png"

                    if skip_existing and image_file.exists() and mask_file.exists():
                        logger.debug(f"Skipping existing sample: {sample_id}")
                        pbar.update(1)
                        successful += 1
                        continue

                    # Select random style
                    style = random.choice(self.available_styles)

                    # Select random aging intensity
                    aging_intensity = random.uniform(*aging_intensity_range)
                    aging_seed = self.seed + i if self.seed is not None else None

                    # Generate sample
                    metadata = self._generate_sample(
                        tile_z, tile_x, tile_y,
                        style,
                        aging_intensity,
                        aging_seed,
                        sample_id
                    )

                    if metadata:
                        metadata_list.append(metadata)
                        successful += 1
                    else:
                        failed += 1

                except Exception as e:
                    logger.error(f"Error generating sample {i}: {e}")
                    failed += 1

                finally:
                    pbar.update(1)

        logger.info(f"Dataset generation complete: {successful} successful, {failed} failed")

        # Save metadata
        self._save_metadata(metadata_list)

        return metadata_list

    def _generate_tile_list(
        self,
        bbox: Tuple[float, float, float, float],
        zoom: int,
        count: int
    ) -> List[Tuple[int, int, int]]:
        """
        Generate list of tiles within bounding box.

        Args:
            bbox: Bounding box (west, south, east, north)
            zoom: Zoom level
            count: Number of tiles needed

        Returns:
            List of (z, x, y) tuples
        """
        west, south, east, north = bbox

        # Convert corners to tile coordinates
        x1, y1 = TileCoordinates.lonlat_to_tile(west, north, zoom)
        x2, y2 = TileCoordinates.lonlat_to_tile(east, south, zoom)

        # Ensure correct ordering (Y is inverted in tile coordinates)
        x_min, x_max = min(x1, x2), max(x1, x2)
        y_min, y_max = min(y1, y2), max(y1, y2)

        # Generate all tiles in range
        all_tiles = []
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                all_tiles.append((zoom, x, y))

        logger.info(f"Found {len(all_tiles)} tiles in bounding box at zoom {zoom}")

        # If we have fewer tiles than needed, we'll cycle through them
        if len(all_tiles) == 0:
            raise ValueError("No tiles found in bounding box")

        # Shuffle for randomness
        random.shuffle(all_tiles)

        # Extend list if needed (with repeats)
        while len(all_tiles) < count:
            all_tiles.extend(all_tiles[:min(count - len(all_tiles), len(all_tiles))])
            random.shuffle(all_tiles)

        return all_tiles[:count]

    def _generate_sample_id(self, z: int, x: int, y: int, index: int) -> str:
        """Generate unique sample identifier."""
        # Create hash of tile coordinates and index
        hash_input = f"{z}_{x}_{y}_{index}_{time.time()}"
        hash_short = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        return f"tile_{z}_{x}_{y}_{hash_short}"

    def _generate_sample(
        self,
        tile_z: int,
        tile_x: int,
        tile_y: int,
        style: str,
        aging_intensity: float,
        aging_seed: Optional[int],
        sample_id: str
    ) -> Optional[SampleMetadata]:
        """
        Generate a single training sample (image + mask).

        Args:
            tile_z, tile_x, tile_y: Tile coordinates
            style: Style name
            aging_intensity: Aging effect intensity
            aging_seed: Random seed for aging
            sample_id: Unique sample identifier

        Returns:
            SampleMetadata or None on failure
        """
        try:
            # Step 1: Render styled image
            logger.debug(f"Rendering tile {tile_z}/{tile_x}/{tile_y} with style {style}")
            rendered_image = self._render_tile(tile_z, tile_x, tile_y, style)

            if rendered_image is None:
                logger.warning(f"Failed to render tile {tile_z}/{tile_x}/{tile_y}")
                return None

            # Step 2: Apply aging effects
            logger.debug(f"Applying aging effects (intensity={aging_intensity:.2f})")

            # Extract era from style name (e.g., "military_1880" -> "1880")
            era = self._extract_era_from_style(style)
            aged_image = age_map(
                rendered_image,
                intensity=aging_intensity,
                style=era,
                seed=aging_seed
            )

            # Step 3: Generate mask
            logger.debug(f"Generating mask for tile {tile_z}/{tile_x}/{tile_y}")
            mask = create_mask(tile_z, tile_x, tile_y, self.tile_size)

            if mask is None:
                logger.warning(f"Failed to create mask for tile {tile_z}/{tile_x}/{tile_y}")
                return None

            # Step 4: Save files
            image_file = self.images_dir / f"{sample_id}.png"
            mask_file = self.masks_dir / f"{sample_id}.png"

            aged_image.save(str(image_file))
            mask_img = Image.fromarray(mask, mode='L')
            mask_img.save(str(mask_file))

            # Step 5: Calculate class distribution
            class_counts = {}
            for class_id in range(5):
                count = int(np.sum(mask == class_id))
                class_counts[class_id] = count

            # Step 6: Create metadata
            bbox = TileCoordinates.tile_to_bbox(tile_z, tile_x, tile_y)
            metadata = SampleMetadata(
                image_file=str(image_file.relative_to(self.output_dir)),
                mask_file=str(mask_file.relative_to(self.output_dir)),
                tile_z=tile_z,
                tile_x=tile_x,
                tile_y=tile_y,
                style=style,
                aging_intensity=aging_intensity,
                aging_seed=aging_seed if aging_seed is not None else -1,
                bbox=list(bbox),
                class_counts=class_counts,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )

            logger.debug(f"Successfully generated sample {sample_id}")
            return metadata

        except Exception as e:
            logger.error(f"Error generating sample {sample_id}: {e}")
            return None

    def _render_tile(
        self,
        tile_z: int,
        tile_x: int,
        tile_y: int,
        style: str
    ) -> Optional[Image.Image]:
        """
        Render a tile using OSM data and style.

        This is a simplified renderer using the Overpass API.
        For production, use render_tiles.py with PMTiles.
        """
        # Get style path
        style_path = self.styles_dir / f"{style}.json"
        if not style_path.exists():
            logger.error(f"Style file not found: {style_path}")
            return None

        # Fetch OSM data
        bbox = TileCoordinates.tile_to_bbox(tile_z, tile_x, tile_y)
        west, south, east, north = bbox

        # Simple Overpass query
        overpass_query = f"""
        [out:json][timeout:25];
        (
          way["building"]({south},{west},{north},{east});
          way["highway"]({south},{west},{north},{east});
          way["waterway"]({south},{west},{north},{east});
          way["natural"~"water|wood|tree_row"]({south},{west},{north},{east});
          way["landuse"~"forest|wood|grass"]({south},{west},{north},{east});
          relation["building"]({south},{west},{north},{east});
          relation["natural"="water"]({south},{west},{north},{east});
        );
        out geom;
        """

        try:
            response = requests.post(
                "https://overpass-api.de/api/interpreter",
                data={'data': overpass_query},
                timeout=30
            )
            response.raise_for_status()
            osm_data = response.json()
        except Exception as e:
            logger.error(f"Failed to fetch OSM data: {e}")
            return None

        # Render using simple PIL drawing
        from PIL import ImageDraw

        # Load style and get background color
        with open(style_path, 'r') as f:
            style_json = json.load(f)

        # Get background color from style
        bg_color = self._get_background_color(style_json)
        img = Image.new('RGB', (self.tile_size, self.tile_size), bg_color)
        draw = ImageDraw.Draw(img)

        # Sort elements by layer
        elements = osm_data.get('elements', [])
        sorted_elements = self._sort_elements_by_layer(elements)

        # Draw elements
        for element in sorted_elements:
            self._draw_element(draw, element, bbox, style_json)

        return img

    def _get_background_color(self, style_json: Dict) -> Tuple[int, int, int]:
        """Extract background color from style JSON."""
        layers = style_json.get('layers', [])
        for layer in layers:
            if layer.get('id') == 'background':
                paint = layer.get('paint', {})
                color = paint.get('background-color', '#f8f4f0')
                return self._parse_color(color)
        return (248, 244, 240)

    def _parse_color(self, color_str: str) -> Tuple[int, int, int]:
        """Parse hex color to RGB tuple."""
        if color_str.startswith('#'):
            hex_color = color_str.lstrip('#')
            if len(hex_color) == 6:
                return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return (200, 200, 200)

    def _sort_elements_by_layer(self, elements):
        """Sort OSM elements by rendering priority."""
        priority = {
            'landuse': 1,
            'natural': 2,
            'waterway': 3,
            'highway': 4,
            'building': 5,
        }

        def get_priority(elem):
            tags = elem.get('tags', {})
            for key in priority:
                if key in tags:
                    return priority[key]
            return 0

        return sorted(elements, key=get_priority)

    def _draw_element(self, draw, element, bbox, style_json):
        """Draw a single OSM element."""
        tags = element.get('tags', {})

        # Determine colors based on feature type
        if 'building' in tags:
            fill_color = (180, 170, 160)
            outline_color = (140, 130, 120)
        elif 'highway' in tags:
            fill_color = (200, 190, 180)
            outline_color = None
        elif 'waterway' in tags or tags.get('natural') == 'water':
            fill_color = (180, 200, 220)
            outline_color = (150, 170, 190)
        elif tags.get('natural') in ['wood', 'tree_row'] or tags.get('landuse') in ['forest', 'wood']:
            fill_color = (200, 210, 190)
            outline_color = None
        elif tags.get('landuse') == 'grass':
            fill_color = (210, 220, 200)
            outline_color = None
        else:
            return

        # Draw geometry
        if element['type'] == 'way' and 'geometry' in element:
            coords = self._convert_coords(element['geometry'], bbox, self.tile_size)
            if len(coords) < 2:
                return

            is_closed = (coords[0] == coords[-1]) or 'building' in tags

            if is_closed and len(coords) >= 3:
                draw.polygon(coords, fill=fill_color, outline=outline_color)
            else:
                width = 3 if 'highway' in tags else 2
                draw.line(coords, fill=fill_color, width=width)

    def _convert_coords(self, geometry, bbox, size):
        """Convert geographic coordinates to pixel coordinates."""
        west, south, east, north = bbox
        coords = []
        for node in geometry:
            lon = node['lon']
            lat = node['lat']
            x = int((lon - west) / (east - west) * size)
            y = int((north - lat) / (north - south) * size)
            coords.append((x, y))
        return coords

    def _extract_era_from_style(self, style_name: str) -> str:
        """Extract era from style name (e.g., 'military_1880' -> '1880')."""
        # Try to extract year
        parts = style_name.split('_')
        for part in parts:
            if part.isdigit() and len(part) == 4:
                return part

        # Default mappings
        if 'military' in style_name.lower():
            return '1880'
        elif 'cadastral' in style_name.lower():
            return '1900'
        elif 'topographic' in style_name.lower():
            return '1920'

        # Default
        return '1900'

    def _save_metadata(self, metadata_list: List[SampleMetadata]):
        """Save dataset metadata to JSON file."""
        metadata_file = self.output_dir / 'metadata.json'

        # Convert to dictionaries
        metadata_dicts = [asdict(m) for m in metadata_list]

        # Add dataset-level metadata
        dataset_metadata = {
            'dataset_info': {
                'num_samples': len(metadata_list),
                'tile_size': self.tile_size,
                'styles': self.available_styles,
                'generation_date': time.strftime("%Y-%m-%d %H:%M:%S"),
                'seed': self.seed,
            },
            'samples': metadata_dicts
        }

        with open(metadata_file, 'w') as f:
            json.dump(dataset_metadata, f, indent=2)

        logger.info(f"Saved metadata to {metadata_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate synthetic historical map training dataset',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 1000 samples in Trondheim area
  python generate_dataset.py --count 1000 --output ../data/synthetic

  # Generate 100 samples in custom area
  python generate_dataset.py --count 100 --bbox 10.3,63.4,10.5,63.5 --zoom 15

  # Use specific styles only
  python generate_dataset.py --count 500 --styles military_1880 cadastral_1900

  # Reproducible generation with seed
  python generate_dataset.py --count 1000 --seed 42
        """
    )

    parser.add_argument(
        '--count',
        type=int,
        required=True,
        help='Number of samples to generate'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='../data/synthetic',
        help='Output directory (default: ../data/synthetic)'
    )
    parser.add_argument(
        '--bbox',
        type=str,
        help='Bounding box as west,south,east,north (default: Trondheim area)'
    )
    parser.add_argument(
        '--zoom',
        type=int,
        default=15,
        help='Zoom level (default: 15)'
    )
    parser.add_argument(
        '--styles',
        nargs='+',
        help='Specific styles to use (default: all available)'
    )
    parser.add_argument(
        '--styles-dir',
        type=str,
        help='Directory containing style files (default: ./styles)'
    )
    parser.add_argument(
        '--tile-size',
        type=int,
        default=512,
        help='Output image/mask size in pixels (default: 512)'
    )
    parser.add_argument(
        '--aging-min',
        type=float,
        default=0.4,
        help='Minimum aging intensity (default: 0.4)'
    )
    parser.add_argument(
        '--aging-max',
        type=float,
        default=0.8,
        help='Maximum aging intensity (default: 0.8)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        help='Random seed for reproducibility'
    )
    parser.add_argument(
        '--no-skip-existing',
        action='store_true',
        help='Regenerate even if files already exist'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose logging'
    )

    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Parse bounding box if provided
    bbox = None
    if args.bbox:
        parts = args.bbox.split(',')
        if len(parts) != 4:
            parser.error("Bbox format must be west,south,east,north")
        bbox = tuple(map(float, parts))

    # Initialize generator
    try:
        generator = DatasetGenerator(
            output_dir=args.output,
            styles_dir=args.styles_dir,
            available_styles=args.styles,
            tile_size=args.tile_size,
            seed=args.seed
        )
    except Exception as e:
        logger.error(f"Failed to initialize generator: {e}")
        sys.exit(1)

    # Generate dataset
    start_time = time.time()

    metadata_list = generator.generate_dataset(
        count=args.count,
        bbox=bbox,
        zoom=args.zoom,
        aging_intensity_range=(args.aging_min, args.aging_max),
        skip_existing=not args.no_skip_existing
    )

    elapsed_time = time.time() - start_time

    # Print summary
    print("\n" + "=" * 70)
    print("Dataset Generation Complete")
    print("=" * 70)
    print(f"Samples generated: {len(metadata_list)}")
    print(f"Time elapsed: {elapsed_time:.2f} seconds")
    print(f"Average time per sample: {elapsed_time / max(1, len(metadata_list)):.2f} seconds")
    print(f"Output directory: {Path(args.output).absolute()}")
    print(f"  - Images: {generator.images_dir}")
    print(f"  - Masks: {generator.masks_dir}")
    print(f"  - Metadata: {generator.output_dir / 'metadata.json'}")
    print("=" * 70)


if __name__ == '__main__':
    main()
