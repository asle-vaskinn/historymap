"""
Main rendering script to convert vector tiles to styled raster images.

This module provides a flexible rendering pipeline that can use multiple backends:
1. Pillow-based vector rendering (primary, offline-capable)
2. MapLibre-native Python bindings (if available, faster)
3. Static image API fallback (requires network)

The renderer supports:
- Rendering specific tiles by z/x/y coordinates
- Applying styles from MapLibre GL JSON
- Batch rendering of multiple tiles
- Reproducible output (deterministic rendering)
- Progress reporting for large batch jobs
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm

try:
    import mapbox_vector_tile
    HAS_MVT = True
except ImportError:
    HAS_MVT = False
    logging.warning("mapbox-vector-tile not installed. Vector tile decoding will be limited.")

from tile_utils import TileCoordinates, tile_to_quadkey

try:
    from pmtiles.reader import Reader as PMTilesReaderBase, MmapSource
    HAS_PMTILES = True
except ImportError:
    HAS_PMTILES = False
    logging.warning("pmtiles library not installed. Cannot read PMTiles files directly.")


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class RenderConfig:
    """Configuration for tile rendering."""
    tile_size: int = 512  # Output image size in pixels
    background_color: Tuple[int, int, int, int] = (242, 239, 233, 255)  # Light beige
    antialias: bool = True
    line_quality: int = 4  # Supersampling factor for line rendering
    compression: str = 'PNG'  # Output format
    compression_level: int = 6  # PNG compression level (0-9)


class StyleProcessor:
    """Process MapLibre GL style JSON for rendering."""

    def __init__(self, style_path: str):
        """
        Initialize style processor.

        Args:
            style_path: Path to MapLibre GL style JSON file
        """
        with open(style_path, 'r') as f:
            self.style = json.load(f)

        self.layers = self.style.get('layers', [])
        self.sources = self.style.get('sources', {})

        # Parse and index layers by source-layer
        self.layers_by_source = self._index_layers()

    def _index_layers(self) -> Dict[str, List[Dict]]:
        """Index layers by their source-layer for faster lookup."""
        indexed = {}
        for layer in self.layers:
            source_layer = layer.get('source-layer', '')
            if source_layer:
                if source_layer not in indexed:
                    indexed[source_layer] = []
                indexed[source_layer].append(layer)
        return indexed

    def get_layers_for_feature(self, source_layer: str,
                               feature_type: str) -> List[Dict]:
        """
        Get applicable style layers for a feature.

        Args:
            source_layer: Name of the source layer (e.g., 'building')
            feature_type: Feature geometry type ('Point', 'LineString', 'Polygon')

        Returns:
            List of applicable style layers
        """
        layers = self.layers_by_source.get(source_layer, [])

        # Filter by geometry type
        applicable = []
        for layer in layers:
            layer_type = layer.get('type')

            # Map layer types to geometry types
            if feature_type == 'Polygon' and layer_type in ['fill', 'fill-extrusion']:
                applicable.append(layer)
            elif feature_type == 'LineString' and layer_type == 'line':
                applicable.append(layer)
            elif feature_type == 'Point' and layer_type in ['circle', 'symbol']:
                applicable.append(layer)

        return applicable

    def get_paint_property(self, layer: Dict, property_name: str,
                          zoom: int = 14, default: Any = None) -> Any:
        """
        Get paint property value, handling zoom functions.

        Args:
            layer: Style layer dictionary
            property_name: Name of paint property
            zoom: Zoom level for evaluation
            default: Default value if property not found

        Returns:
            Resolved property value
        """
        paint = layer.get('paint', {})
        value = paint.get(property_name, default)

        # Handle zoom-based expressions (simplified)
        if isinstance(value, dict):
            if 'stops' in value:
                # Legacy stops format
                stops = value['stops']
                # Find appropriate stop
                for i, (stop_zoom, stop_value) in enumerate(stops):
                    if zoom <= stop_zoom:
                        return stop_value
                return stops[-1][1]
            # TODO: Handle full expression syntax
            return default

        return value if value is not None else default

    def parse_color(self, color_value: Any) -> Tuple[int, int, int, int]:
        """
        Parse color from various formats to RGBA tuple.

        Args:
            color_value: Color in various formats (hex, rgb, rgba, named)

        Returns:
            RGBA tuple (r, g, b, a) with values 0-255
        """
        if isinstance(color_value, str):
            # Hex color
            if color_value.startswith('#'):
                color_value = color_value.lstrip('#')
                if len(color_value) == 6:
                    r, g, b = tuple(int(color_value[i:i+2], 16) for i in (0, 2, 4))
                    return (r, g, b, 255)
                elif len(color_value) == 8:
                    r, g, b, a = tuple(int(color_value[i:i+2], 16) for i in (0, 2, 4, 6))
                    return (r, g, b, a)

            # rgb() or rgba()
            if color_value.startswith('rgb'):
                # Simple parsing (not fully robust)
                values = color_value.split('(')[1].split(')')[0].split(',')
                values = [v.strip() for v in values]
                if len(values) == 3:
                    return (int(values[0]), int(values[1]), int(values[2]), 255)
                elif len(values) == 4:
                    return (int(values[0]), int(values[1]), int(values[2]),
                           int(float(values[3]) * 255))

        # Default fallback
        return (0, 0, 0, 255)


class PillowRenderer:
    """
    Render vector tiles to raster images using Pillow.

    This is the primary rendering backend - works offline and is pure Python.
    """

    def __init__(self, config: RenderConfig, style: StyleProcessor):
        """
        Initialize Pillow renderer.

        Args:
            config: Rendering configuration
            style: Style processor
        """
        self.config = config
        self.style = style

    def render_tile(self, z: int, x: int, y: int,
                   features: Dict[str, List[Dict]]) -> Image.Image:
        """
        Render a tile to an image.

        Args:
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate
            features: Dictionary of features by layer name

        Returns:
            Rendered PIL Image
        """
        # Create image with background color
        img = Image.new('RGBA', (self.config.tile_size, self.config.tile_size),
                       self.config.background_color)

        # Create drawing context
        draw = ImageDraw.Draw(img, 'RGBA')

        # Get tile bounds for coordinate transformation
        tile_bbox = TileCoordinates.tile_to_bbox(z, x, y)

        # Render layers in order (back to front)
        for layer in self.style.layers:
            layer_id = layer.get('id')
            layer_type = layer.get('type')
            source_layer = layer.get('source-layer', '')

            # Skip if no features for this layer
            if source_layer not in features:
                continue

            # Get features for this source layer
            layer_features = features[source_layer]

            # Render based on layer type
            if layer_type == 'fill':
                self._render_fill_layer(draw, layer, layer_features, z, tile_bbox)
            elif layer_type == 'line':
                self._render_line_layer(draw, layer, layer_features, z, tile_bbox)
            elif layer_type == 'circle':
                self._render_circle_layer(draw, layer, layer_features, z, tile_bbox)

        return img

    def _render_fill_layer(self, draw: ImageDraw.Draw, layer: Dict,
                          features: List[Dict], zoom: int,
                          tile_bbox: Tuple[float, float, float, float]):
        """Render polygon fill layer."""
        fill_color = self.style.get_paint_property(layer, 'fill-color', zoom,
                                                   default='#000000')
        fill_opacity = self.style.get_paint_property(layer, 'fill-opacity', zoom,
                                                     default=1.0)

        # Parse color and apply opacity
        r, g, b, a = self.style.parse_color(fill_color)
        a = int(a * fill_opacity)
        color = (r, g, b, a)

        # Outline (optional)
        outline_color = self.style.get_paint_property(layer, 'fill-outline-color',
                                                      zoom, default=None)
        if outline_color:
            outline = self.style.parse_color(outline_color)
        else:
            outline = None

        # Render each feature
        for feature in features:
            geom_type = feature.get('geometry', {}).get('type')
            if geom_type not in ['Polygon', 'MultiPolygon']:
                continue

            coords = self._project_coordinates(feature, tile_bbox)

            if geom_type == 'Polygon':
                # coords is list of rings (first is outer, rest are holes)
                if coords:
                    outer = coords[0]
                    if len(outer) >= 3:
                        draw.polygon(outer, fill=color, outline=outline)
            elif geom_type == 'MultiPolygon':
                for polygon in coords:
                    if polygon:
                        outer = polygon[0]
                        if len(outer) >= 3:
                            draw.polygon(outer, fill=color, outline=outline)

    def _render_line_layer(self, draw: ImageDraw.Draw, layer: Dict,
                          features: List[Dict], zoom: int,
                          tile_bbox: Tuple[float, float, float, float]):
        """Render line layer."""
        line_color = self.style.get_paint_property(layer, 'line-color', zoom,
                                                   default='#000000')
        line_width = self.style.get_paint_property(layer, 'line-width', zoom,
                                                   default=1.0)
        line_opacity = self.style.get_paint_property(layer, 'line-opacity', zoom,
                                                     default=1.0)

        # Parse color and apply opacity
        r, g, b, a = self.style.parse_color(line_color)
        a = int(a * line_opacity)
        color = (r, g, b, a)

        # Scale line width for zoom
        width = max(1, int(line_width))

        # Render each feature
        for feature in features:
            geom_type = feature.get('geometry', {}).get('type')
            if geom_type not in ['LineString', 'MultiLineString']:
                continue

            coords = self._project_coordinates(feature, tile_bbox)

            if geom_type == 'LineString':
                if len(coords) >= 2:
                    draw.line(coords, fill=color, width=width)
            elif geom_type == 'MultiLineString':
                for line in coords:
                    if len(line) >= 2:
                        draw.line(line, fill=color, width=width)

    def _render_circle_layer(self, draw: ImageDraw.Draw, layer: Dict,
                            features: List[Dict], zoom: int,
                            tile_bbox: Tuple[float, float, float, float]):
        """Render circle (point) layer."""
        circle_color = self.style.get_paint_property(layer, 'circle-color', zoom,
                                                     default='#000000')
        circle_radius = self.style.get_paint_property(layer, 'circle-radius', zoom,
                                                      default=5.0)
        circle_opacity = self.style.get_paint_property(layer, 'circle-opacity', zoom,
                                                       default=1.0)

        # Parse color and apply opacity
        r, g, b, a = self.style.parse_color(circle_color)
        a = int(a * circle_opacity)
        color = (r, g, b, a)

        radius = max(1, int(circle_radius))

        # Render each feature
        for feature in features:
            geom_type = feature.get('geometry', {}).get('type')
            if geom_type != 'Point':
                continue

            coords = self._project_coordinates(feature, tile_bbox)
            if coords:
                x, y = coords[0]
                bbox = [x - radius, y - radius, x + radius, y + radius]
                draw.ellipse(bbox, fill=color)

    def _project_coordinates(self, feature: Dict,
                            tile_bbox: Tuple[float, float, float, float]) -> List:
        """
        Project feature coordinates to pixel space.

        MVT coordinates are in tile-local space (0-4096 extent), not geographic.
        We just need to scale them to pixel coordinates.

        Args:
            feature: GeoJSON-like feature with MVT coordinates
            tile_bbox: Tile bounding box (unused for MVT, kept for API compatibility)

        Returns:
            Projected coordinates suitable for PIL drawing
        """
        geometry = feature.get('geometry', {})
        geom_type = geometry.get('type')
        coords = geometry.get('coordinates', [])

        # MVT extent is typically 4096
        mvt_extent = 4096

        def scale_point(x: float, y: float) -> Tuple[int, int]:
            """Scale MVT point to pixel coordinates."""
            px = int((x / mvt_extent) * self.config.tile_size)
            py = int((y / mvt_extent) * self.config.tile_size)
            return (px, py)

        def scale_coords(coords_list, depth=0):
            """Recursively scale coordinates."""
            if not coords_list:
                return []

            # Check if this is a coordinate pair (leaf node)
            if isinstance(coords_list[0], (int, float)):
                return scale_point(coords_list[0], coords_list[1])

            # Otherwise, recurse
            return [scale_coords(c, depth + 1) for c in coords_list]

        return scale_coords(coords)


class TileRenderer:
    """
    Main tile rendering class that manages backends and batch operations.
    """

    def __init__(self, style_path: str, config: Optional[RenderConfig] = None):
        """
        Initialize tile renderer.

        Args:
            style_path: Path to MapLibre GL style JSON
            config: Rendering configuration (uses defaults if not provided)
        """
        self.config = config or RenderConfig()
        self.style = StyleProcessor(style_path)
        self.renderer = PillowRenderer(self.config, self.style)

        logger.info(f"Initialized renderer with style: {style_path}")
        logger.info(f"Output size: {self.config.tile_size}x{self.config.tile_size}")

    def render_tile(self, z: int, x: int, y: int,
                   pmtiles_path: Optional[str] = None,
                   features: Optional[Dict[str, List[Dict]]] = None) -> Image.Image:
        """
        Render a single tile.

        Args:
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate
            pmtiles_path: Path to PMTiles file (optional)
            features: Pre-loaded features (optional, overrides pmtiles_path)

        Returns:
            Rendered PIL Image
        """
        # Load features if not provided
        if features is None:
            if pmtiles_path:
                features = self._load_features_from_pmtiles(pmtiles_path, z, x, y)
            else:
                # Render empty tile with just background
                features = {}

        # Render using Pillow backend
        img = self.renderer.render_tile(z, x, y, features)

        logger.debug(f"Rendered tile z={z}, x={x}, y={y}")
        return img

    def _load_features_from_pmtiles(self, pmtiles_path: str,
                                   z: int, x: int, y: int) -> Dict[str, List[Dict]]:
        """
        Load features from PMTiles file.

        Args:
            pmtiles_path: Path to PMTiles file
            z, x, y: Tile coordinates

        Returns:
            Dictionary of features by layer name
        """
        if not HAS_PMTILES:
            logger.error("pmtiles library not available")
            return {}

        if not HAS_MVT:
            logger.error("mapbox-vector-tile library not available")
            return {}

        try:
            with open(pmtiles_path, 'rb') as f:
                source = MmapSource(f)
                reader = PMTilesReaderBase(source)

                import gzip

                # Get tile data
                tile_data = reader.get(z, x, y)

                if tile_data is None:
                    logger.warning(f"No tile data for z={z}, x={x}, y={y}")
                    return {}

                # Decompress if gzipped
                if tile_data[:2] == b'\x1f\x8b':  # gzip magic bytes
                    tile_data = gzip.decompress(tile_data)

                # Decode vector tile
                decoded = mapbox_vector_tile.decode(tile_data)

                # Convert to GeoJSON-like format
                features = {}
                for layer_name, layer_data in decoded.items():
                    features[layer_name] = layer_data.get('features', [])

                return features

        except Exception as e:
            logger.error(f"Error loading tile from PMTiles: {e}")
            return {}

    def render_batch(self, tiles: List[Tuple[int, int, int]],
                    output_dir: str,
                    pmtiles_path: Optional[str] = None,
                    num_workers: int = 4,
                    naming_pattern: str = "{z}_{x}_{y}.png") -> List[str]:
        """
        Render multiple tiles in batch.

        Args:
            tiles: List of (z, x, y) tuples
            output_dir: Directory to save rendered tiles
            pmtiles_path: Path to PMTiles file (optional)
            num_workers: Number of parallel workers
            naming_pattern: Output filename pattern

        Returns:
            List of output file paths
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        output_files = []

        logger.info(f"Rendering {len(tiles)} tiles to {output_dir}")

        # Progress bar
        with tqdm(total=len(tiles), desc="Rendering tiles") as pbar:
            # Parallel rendering
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                # Submit all tasks
                futures = {}
                for z, x, y in tiles:
                    filename = naming_pattern.format(z=z, x=x, y=y)
                    output_file = output_path / filename

                    future = executor.submit(
                        self._render_and_save,
                        z, x, y, output_file, pmtiles_path
                    )
                    futures[future] = (z, x, y, output_file)

                # Collect results
                for future in as_completed(futures):
                    z, x, y, output_file = futures[future]
                    try:
                        result = future.result()
                        if result:
                            output_files.append(str(output_file))
                    except Exception as e:
                        logger.error(f"Error rendering tile z={z}, x={x}, y={y}: {e}")
                    finally:
                        pbar.update(1)

        logger.info(f"Successfully rendered {len(output_files)}/{len(tiles)} tiles")
        return output_files

    def _render_and_save(self, z: int, x: int, y: int,
                        output_file: Path,
                        pmtiles_path: Optional[str]) -> bool:
        """
        Helper method to render and save a single tile.

        Returns:
            True if successful, False otherwise
        """
        try:
            img = self.render_tile(z, x, y, pmtiles_path=pmtiles_path)
            img.save(
                output_file,
                format=self.config.compression,
                compress_level=self.config.compression_level
            )
            return True
        except Exception as e:
            logger.error(f"Error rendering/saving tile: {e}")
            return False


def main():
    """Command-line interface for tile rendering."""
    parser = argparse.ArgumentParser(
        description='Render vector tiles to styled raster images',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Render single tile
  python render_tiles.py --style style.json --tile 10 524 340 --output tile.png

  # Render batch of tiles
  python render_tiles.py --style style.json --batch tiles.txt --output-dir output/

  # Render from PMTiles
  python render_tiles.py --style style.json --pmtiles data.pmtiles --tile 10 524 340

Tile coordinate format (for batch file):
  z x y
  10 524 340
  10 524 341
  ...
        """
    )

    parser.add_argument('--style', required=True,
                       help='Path to MapLibre GL style JSON')
    parser.add_argument('--pmtiles',
                       help='Path to PMTiles file')
    parser.add_argument('--tile', nargs=3, type=int, metavar=('Z', 'X', 'Y'),
                       help='Single tile to render (z x y)')
    parser.add_argument('--batch',
                       help='File containing list of tiles to render')
    parser.add_argument('--output', '-o',
                       help='Output file for single tile')
    parser.add_argument('--output-dir', '-d',
                       help='Output directory for batch rendering')
    parser.add_argument('--size', type=int, default=512,
                       help='Output image size in pixels (default: 512)')
    parser.add_argument('--workers', type=int, default=4,
                       help='Number of parallel workers for batch (default: 4)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose logging')

    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate arguments
    if args.tile and args.batch:
        parser.error("Cannot specify both --tile and --batch")

    if not args.tile and not args.batch:
        parser.error("Must specify either --tile or --batch")

    if args.tile and not args.output:
        parser.error("--output required when using --tile")

    if args.batch and not args.output_dir:
        parser.error("--output-dir required when using --batch")

    # Create renderer
    config = RenderConfig(tile_size=args.size)
    renderer = TileRenderer(args.style, config)

    # Render
    if args.tile:
        # Single tile
        z, x, y = args.tile
        logger.info(f"Rendering tile z={z}, x={x}, y={y}")

        img = renderer.render_tile(z, x, y, pmtiles_path=args.pmtiles)
        img.save(args.output)

        logger.info(f"Saved to {args.output}")

    elif args.batch:
        # Batch rendering
        # Read tile list
        tiles = []
        with open(args.batch, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split()
                    if len(parts) >= 3:
                        z, x, y = int(parts[0]), int(parts[1]), int(parts[2])
                        tiles.append((z, x, y))

        logger.info(f"Loaded {len(tiles)} tiles from {args.batch}")

        output_files = renderer.render_batch(
            tiles,
            args.output_dir,
            pmtiles_path=args.pmtiles,
            num_workers=args.workers
        )

        logger.info(f"Batch rendering complete: {len(output_files)} tiles saved")


if __name__ == '__main__':
    main()
