#!/usr/bin/env python3
"""
Cut georeferenced maps into ML-ready tiles.

This script processes georeferenced GeoTIFF files and cuts them into
smaller tiles suitable for machine learning training. Each tile maintains
geographic coordinate information.

Features:
- Configurable tile size (256x256, 512x512, etc.)
- Configurable overlap between tiles
- Skip empty or mostly empty tiles
- Save tile bounds to JSON for reference
- Support for various input formats

Usage:
    # Basic tiling
    python tile_maps.py input.tif --tile-size 256

    # With overlap
    python tile_maps.py input.tif --tile-size 512 --overlap 64

    # Skip empty tiles
    python tile_maps.py input.tif --skip-empty --empty-threshold 0.95

    # Batch process directory
    python tile_maps.py --input-dir ../data/kartverket/georeferenced --tile-size 256
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from tqdm import tqdm

try:
    from osgeo import gdal, osr
except ImportError:
    print("ERROR: GDAL is required. Install with: pip install gdal")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Enable GDAL exceptions
gdal.UseExceptions()


class MapTiler:
    """Cut georeferenced maps into tiles."""

    def __init__(
        self,
        tile_size: int = 256,
        overlap: int = 0,
        skip_empty: bool = True,
        empty_threshold: float = 0.95,
        output_format: str = 'PNG'
    ):
        """
        Initialize map tiler.

        Args:
            tile_size: Size of square tiles in pixels
            overlap: Overlap between tiles in pixels
            skip_empty: If True, skip tiles that are mostly empty
            empty_threshold: Fraction of empty pixels to consider tile empty
            output_format: Output image format (PNG, JPEG, TIFF)
        """
        self.tile_size = tile_size
        self.overlap = overlap
        self.skip_empty = skip_empty
        self.empty_threshold = empty_threshold
        self.output_format = output_format.upper()

    def tile_map(
        self,
        input_path: Path,
        output_dir: Path,
        prefix: Optional[str] = None
    ) -> Dict:
        """
        Tile a georeferenced map.

        Args:
            input_path: Path to input GeoTIFF
            output_dir: Directory to save tiles
            prefix: Optional prefix for tile filenames

        Returns:
            Dictionary with tiling statistics and metadata
        """
        # Open dataset
        try:
            ds = gdal.Open(str(input_path), gdal.GA_ReadOnly)
            if ds is None:
                raise RuntimeError(f"Could not open {input_path}")
        except Exception as e:
            logger.error(f"Failed to open {input_path}: {e}")
            return {'error': str(e)}

        # Get image properties
        width = ds.RasterXSize
        height = ds.RasterYSize
        bands = ds.RasterCount

        logger.info(f"Input: {width}x{height}, {bands} bands")

        # Get geotransform
        geotransform = ds.GetGeoTransform()
        projection = ds.GetProjection()

        if geotransform is None or geotransform == (0, 1, 0, 0, 0, 1):
            logger.warning("No geotransform found. Tiles will not have geo-coordinates.")
            has_geo = False
        else:
            has_geo = True
            logger.info(f"Geotransform: {geotransform}")

        # Create output directory
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine prefix
        if prefix is None:
            prefix = input_path.stem

        # Calculate tile grid
        step = self.tile_size - self.overlap
        cols = int(np.ceil((width - self.overlap) / step))
        rows = int(np.ceil((height - self.overlap) / step))

        logger.info(f"Creating {cols}x{rows} = {cols*rows} tiles (overlap: {self.overlap}px)")

        # Tile the image
        tiles_created = 0
        tiles_skipped = 0
        tile_metadata = []

        with tqdm(total=rows*cols, desc="Tiling") as pbar:
            for row in range(rows):
                for col in range(cols):
                    # Calculate tile boundaries
                    x_off = col * step
                    y_off = row * step
                    x_size = min(self.tile_size, width - x_off)
                    y_size = min(self.tile_size, height - y_off)

                    # Skip if tile is too small
                    if x_size < self.tile_size // 2 or y_size < self.tile_size // 2:
                        tiles_skipped += 1
                        pbar.update(1)
                        continue

                    # Read tile data
                    try:
                        tile_data = ds.ReadAsArray(x_off, y_off, x_size, y_size)

                        if tile_data is None:
                            logger.warning(f"Could not read tile at ({col}, {row})")
                            tiles_skipped += 1
                            pbar.update(1)
                            continue

                        # Handle single band vs multi-band
                        if bands == 1:
                            tile_data = tile_data.reshape(y_size, x_size)
                        else:
                            # Transpose from (bands, height, width) to (height, width, bands)
                            tile_data = np.transpose(tile_data, (1, 2, 0))

                        # Check if tile is empty
                        if self.skip_empty and self._is_empty(tile_data):
                            tiles_skipped += 1
                            pbar.update(1)
                            continue

                        # Pad tile if needed
                        if x_size < self.tile_size or y_size < self.tile_size:
                            tile_data = self._pad_tile(tile_data, self.tile_size, bands)

                        # Generate tile name: prefix_z_row_col.ext
                        # z is placeholder for zoom level (0 for now)
                        tile_name = f"{prefix}_0_{row}_{col}"
                        tile_path = output_dir / f"{tile_name}.{self.output_format.lower()}"

                        # Save tile image
                        self._save_tile(tile_data, tile_path)

                        # Calculate tile bounds in geo-coordinates
                        if has_geo:
                            bounds = self._calculate_bounds(
                                geotransform,
                                x_off, y_off,
                                x_size, y_size
                            )
                        else:
                            bounds = None

                        # Save metadata
                        tile_meta = {
                            'filename': tile_name + f".{self.output_format.lower()}",
                            'row': row,
                            'col': col,
                            'pixel_x': x_off,
                            'pixel_y': y_off,
                            'pixel_width': x_size,
                            'pixel_height': y_size,
                            'bounds': bounds,
                            'crs': projection if projection else None,
                        }
                        tile_metadata.append(tile_meta)

                        tiles_created += 1

                    except Exception as e:
                        logger.warning(f"Error processing tile ({col}, {row}): {e}")
                        tiles_skipped += 1

                    pbar.update(1)

        # Save tile index
        index_path = output_dir / f"{prefix}_tiles.json"
        index_data = {
            'source_file': str(input_path),
            'tile_size': self.tile_size,
            'overlap': self.overlap,
            'tiles_created': tiles_created,
            'tiles_skipped': tiles_skipped,
            'grid_cols': cols,
            'grid_rows': rows,
            'projection': projection if projection else None,
            'geotransform': list(geotransform) if geotransform else None,
            'tiles': tile_metadata,
        }

        with open(index_path, 'w') as f:
            json.dump(index_data, f, indent=2)

        logger.info(f"Created {tiles_created} tiles, skipped {tiles_skipped}")
        logger.info(f"Tile index saved to: {index_path}")

        # Close dataset
        ds = None

        return index_data

    def _is_empty(self, tile_data: np.ndarray) -> bool:
        """
        Check if tile is mostly empty.

        A tile is considered empty if most pixels are:
        - Zero/black
        - White (255)
        - Transparent (alpha channel = 0)
        - NoData value

        Args:
            tile_data: Tile data array

        Returns:
            True if tile is mostly empty
        """
        # Check for common empty values
        if len(tile_data.shape) == 2:
            # Single band
            empty_pixels = (tile_data == 0) | (tile_data == 255)
        else:
            # Multi-band: check if all bands are empty
            empty_pixels = np.all(tile_data == 0, axis=2) | np.all(tile_data == 255, axis=2)

            # Check alpha channel if present (4th band)
            if tile_data.shape[2] == 4:
                empty_pixels |= (tile_data[:, :, 3] == 0)

        empty_fraction = np.mean(empty_pixels)
        return empty_fraction > self.empty_threshold

    def _pad_tile(self, tile_data: np.ndarray, target_size: int, bands: int) -> np.ndarray:
        """
        Pad tile to target size.

        Args:
            tile_data: Tile data array
            target_size: Target size (square)
            bands: Number of bands

        Returns:
            Padded tile data
        """
        if len(tile_data.shape) == 2:
            # Single band
            padded = np.zeros((target_size, target_size), dtype=tile_data.dtype)
            h, w = tile_data.shape
            padded[:h, :w] = tile_data
        else:
            # Multi-band
            padded = np.zeros((target_size, target_size, bands), dtype=tile_data.dtype)
            h, w = tile_data.shape[:2]
            padded[:h, :w, :] = tile_data

        return padded

    def _save_tile(self, tile_data: np.ndarray, output_path: Path):
        """Save tile as image."""
        try:
            # Convert to uint8 if needed
            if tile_data.dtype != np.uint8:
                # Normalize to 0-255 range
                if tile_data.max() > 255:
                    tile_data = (tile_data / tile_data.max() * 255).astype(np.uint8)
                else:
                    tile_data = tile_data.astype(np.uint8)

            # Create PIL image
            if len(tile_data.shape) == 2:
                # Single band (grayscale)
                img = Image.fromarray(tile_data, mode='L')
            else:
                # Multi-band
                if tile_data.shape[2] == 1:
                    img = Image.fromarray(tile_data[:, :, 0], mode='L')
                elif tile_data.shape[2] == 3:
                    img = Image.fromarray(tile_data, mode='RGB')
                elif tile_data.shape[2] == 4:
                    img = Image.fromarray(tile_data, mode='RGBA')
                else:
                    # More than 4 bands: save first 3 as RGB
                    img = Image.fromarray(tile_data[:, :, :3], mode='RGB')

            # Save image
            if self.output_format == 'JPEG':
                # Convert RGBA to RGB for JPEG
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                img.save(output_path, 'JPEG', quality=95)
            else:
                img.save(output_path, self.output_format)

        except Exception as e:
            logger.error(f"Failed to save tile {output_path}: {e}")
            raise

    def _calculate_bounds(
        self,
        geotransform: Tuple,
        x_off: int,
        y_off: int,
        x_size: int,
        y_size: int
    ) -> Dict:
        """
        Calculate geographic bounds of tile.

        Args:
            geotransform: GDAL geotransform tuple
            x_off: X offset in pixels
            y_off: Y offset in pixels
            x_size: Width in pixels
            y_size: Height in pixels

        Returns:
            Dictionary with bounds (west, south, east, north)
        """
        # Geotransform: [origin_x, pixel_width, rotation_x, origin_y, rotation_y, pixel_height]
        origin_x, pixel_width, rot_x, origin_y, rot_y, pixel_height = geotransform

        # Calculate corners
        # Top-left
        min_x = origin_x + x_off * pixel_width + y_off * rot_x
        max_y = origin_y + x_off * rot_y + y_off * pixel_height

        # Bottom-right
        max_x = origin_x + (x_off + x_size) * pixel_width + (y_off + y_size) * rot_x
        min_y = origin_y + (x_off + x_size) * rot_y + (y_off + y_size) * pixel_height

        return {
            'west': min_x,
            'south': min_y,
            'east': max_x,
            'north': max_y,
        }

    def batch_tile_directory(
        self,
        input_dir: Path,
        output_dir: Path,
        pattern: str = '*.tif'
    ) -> List[Dict]:
        """
        Tile all maps in a directory.

        Args:
            input_dir: Directory containing georeferenced maps
            output_dir: Directory to save tiles
            pattern: File pattern to match

        Returns:
            List of tiling results
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)

        # Find all matching files
        input_files = sorted(input_dir.glob(pattern))

        if not input_files:
            logger.warning(f"No files matching {pattern} in {input_dir}")
            return []

        logger.info(f"Found {len(input_files)} files to process")

        results = []

        for input_file in input_files:
            logger.info(f"Processing: {input_file.name}")

            # Create subdirectory for this map
            map_output_dir = output_dir / input_file.stem

            try:
                result = self.tile_map(
                    input_path=input_file,
                    output_dir=map_output_dir,
                    prefix=input_file.stem
                )
                results.append(result)

            except Exception as e:
                logger.error(f"Failed to tile {input_file}: {e}")
                results.append({
                    'source_file': str(input_file),
                    'error': str(e)
                })

        logger.info(f"Batch tiling complete: {len(results)} maps processed")
        return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Cut georeferenced maps into tiles',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Tile a single map
  python tile_maps.py map.tif --tile-size 256 --output ../data/kartverket/tiles/

  # Tile with overlap
  python tile_maps.py map.tif --tile-size 512 --overlap 64

  # Batch process directory
  python tile_maps.py --input-dir ../data/kartverket/georeferenced/ \\
                      --output-dir ../data/kartverket/tiles/ \\
                      --tile-size 256

  # Include empty tiles
  python tile_maps.py map.tif --no-skip-empty
        """
    )

    parser.add_argument(
        'input',
        nargs='?',
        type=str,
        help='Input georeferenced GeoTIFF'
    )
    parser.add_argument(
        '--input-dir',
        type=str,
        help='Process all TIFFs in this directory'
    )
    parser.add_argument(
        '--output',
        '--output-dir',
        type=str,
        help='Output directory for tiles'
    )
    parser.add_argument(
        '--tile-size',
        type=int,
        default=256,
        choices=[128, 256, 512, 1024],
        help='Tile size in pixels (default: 256)'
    )
    parser.add_argument(
        '--overlap',
        type=int,
        default=0,
        help='Overlap between tiles in pixels (default: 0)'
    )
    parser.add_argument(
        '--no-skip-empty',
        action='store_true',
        help='Do not skip empty tiles'
    )
    parser.add_argument(
        '--empty-threshold',
        type=float,
        default=0.95,
        help='Fraction of empty pixels to skip tile (default: 0.95)'
    )
    parser.add_argument(
        '--format',
        type=str,
        default='PNG',
        choices=['PNG', 'JPEG', 'TIFF'],
        help='Output image format (default: PNG)'
    )
    parser.add_argument(
        '--pattern',
        type=str,
        default='*.tif',
        help='File pattern for batch processing (default: *.tif)'
    )
    parser.add_argument(
        '--prefix',
        type=str,
        help='Prefix for tile filenames (default: input filename)'
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.input and not args.input_dir:
        parser.error("either input file or --input-dir is required")

    if not args.output:
        parser.error("--output or --output-dir is required")

    # Create tiler
    tiler = MapTiler(
        tile_size=args.tile_size,
        overlap=args.overlap,
        skip_empty=not args.no_skip_empty,
        empty_threshold=args.empty_threshold,
        output_format=args.format
    )

    # Process files
    try:
        if args.input_dir:
            # Batch mode
            results = tiler.batch_tile_directory(
                input_dir=Path(args.input_dir),
                output_dir=Path(args.output),
                pattern=args.pattern
            )

            # Count successes and failures
            successes = sum(1 for r in results if 'error' not in r)
            failures = len(results) - successes

            logger.info(f"Batch complete: {successes} successful, {failures} failed")

        else:
            # Single file mode
            output_dir = Path(args.output)

            result = tiler.tile_map(
                input_path=Path(args.input),
                output_dir=output_dir,
                prefix=args.prefix
            )

            if 'error' in result:
                logger.error("Tiling failed")
                sys.exit(1)
            else:
                logger.info("Tiling completed successfully")

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Tiling failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
