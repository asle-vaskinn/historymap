#!/usr/bin/env python3
"""
Export GeoJSON building data to PMTiles format for web viewing.

This script converts the frontend-ready GeoJSON from export_geojson.py to
PMTiles format using tippecanoe. PMTiles is a cloud-optimized format that
allows efficient serving of vector tiles without a tile server.

Requirements:
    - tippecanoe: https://github.com/felt/tippecanoe
      Install on macOS: brew install tippecanoe
      Install on Linux: Build from source or use package manager

The generated PMTiles file can be served:
    - Directly from object storage (S3, R2, etc.)
    - Via HTTP with range request support
    - Through GitHub Pages or any static host
    - With MapLibre GL JS PMTiles plugin

Optimizations for building data:
    - Zoom levels 10-16 (city to building detail)
    - Full detail at max zoom for accurate building footprints
    - Attribute types preserved (sd, ed as integers)
    - Simplified geometries at lower zooms
    - Drop rate to manage tile sizes

Temporal attributes preserved:
    - sd: start_date (year building appeared)
    - ed: end_date (year building demolished)
    - ev: evidence level (h/m/l)
    - src: data source (sef/osm/ml/tk/mat)
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def check_tippecanoe() -> bool:
    """
    Check if tippecanoe is installed and accessible.

    Returns:
        True if tippecanoe is available
    """
    try:
        result = subprocess.run(
            ['tippecanoe', '--version'],
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def export_pmtiles(
    input_path: Path,
    output_path: Path,
    min_zoom: int = 10,
    max_zoom: int = 16,
    layer_name: str = 'buildings',
    name: Optional[str] = None,
    description: Optional[str] = None,
    attribution: Optional[str] = None,
    force: bool = False,
    verbose: bool = True
) -> bool:
    """
    Export GeoJSON to PMTiles using tippecanoe.

    Args:
        input_path: Path to input GeoJSON file
        output_path: Path to output PMTiles file
        min_zoom: Minimum zoom level (default: 10 for city-level)
        max_zoom: Maximum zoom level (default: 16 for building detail)
        layer_name: Layer name in tiles (default: 'buildings')
        name: Tileset name for metadata
        description: Tileset description for metadata
        attribution: Attribution text for metadata
        force: Overwrite existing output file
        verbose: Print progress information

    Returns:
        True if successful
    """
    # Validate inputs
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return False

    if output_path.exists() and not force:
        print(f"Error: Output file exists: {output_path}")
        print("Use --force to overwrite")
        return False

    # Check tippecanoe
    if not check_tippecanoe():
        print("Error: tippecanoe not found")
        print("\nInstallation instructions:")
        print("  macOS:  brew install tippecanoe")
        print("  Linux:  Build from https://github.com/felt/tippecanoe")
        print("  Docker: docker run -v $(pwd):/data felt/tippecanoe [args]")
        return False

    # Load input to get feature count
    if verbose:
        print(f"Loading GeoJSON from {input_path}...")

    with open(input_path) as f:
        data = json.load(f)

    feature_count = len(data.get('features', []))
    if verbose:
        print(f"  Features: {feature_count}")

    # Prepare output directory
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build tippecanoe command
    cmd = [
        'tippecanoe',
        '--output', str(output_path),
        '--force' if force else '--allow-existing',
        '--layer', layer_name,
        '--minimum-zoom', str(min_zoom),
        '--maximum-zoom', str(max_zoom),

        # Preserve full detail at maximum zoom for accurate building footprints
        '--full-detail', str(max_zoom),
        '--no-simplification-of-shared-nodes',

        # Drop features as needed to manage tile size
        '--drop-densest-as-needed',
        '--extend-zooms-if-still-dropping',

        # Attribute handling
        '--attribute-type=sd:int',  # start_date as integer
        '--attribute-type=ed:int',  # end_date as integer
        '--attribute-type=mlc:float',  # ML confidence as float
        '--accumulate-attribute=src:comma',  # Combine sources

        # Feature limits (reasonable for building data)
        '--maximum-tile-features', '200000',
        '--maximum-tile-bytes', '500000',

        # Buffer for edge features
        '--buffer', '5',

        # Progress indicator
        '--quiet' if not verbose else '--progress-interval=2',

        # Input file
        str(input_path)
    ]

    # Add optional metadata
    if name:
        cmd.extend(['--name', name])
    if description:
        cmd.extend(['--description', description])
    if attribution:
        cmd.extend(['--attribution', attribution])

    # Run tippecanoe
    if verbose:
        print(f"\nGenerating PMTiles...")
        print(f"  Min zoom: {min_zoom}")
        print(f"  Max zoom: {max_zoom}")
        print(f"  Layer: {layer_name}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=not verbose,
            text=True,
            check=False
        )

        if result.returncode != 0:
            print(f"Error: tippecanoe failed with code {result.returncode}")
            if result.stderr:
                print(f"STDERR: {result.stderr}")
            return False

    except Exception as e:
        print(f"Error running tippecanoe: {e}")
        return False

    # Success - calculate file size and write metadata
    if not output_path.exists():
        print("Error: Output file was not created")
        return False

    size_mb = output_path.stat().st_size / (1024 * 1024)

    if verbose:
        print(f"\nPMTiles generation complete!")
        print(f"  Output: {output_path}")
        print(f"  Size: {size_mb:.2f} MB")

    # Write export metadata
    metadata = {
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'source_file': str(input_path),
        'format': 'pmtiles',
        'feature_count': feature_count,
        'size_mb': round(size_mb, 2),
        'zoom_levels': {
            'min': min_zoom,
            'max': max_zoom
        },
        'layer_name': layer_name,
        'tippecanoe_options': {
            'full_detail': max_zoom,
            'drop_densest_as_needed': True,
            'max_tile_features': 200000,
            'max_tile_bytes': 500000
        }
    }

    if name:
        metadata['name'] = name
    if description:
        metadata['description'] = description
    if attribution:
        metadata['attribution'] = attribution

    metadata_path = output_path.with_suffix('.meta.json')
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    if verbose:
        print(f"  Metadata: {metadata_path}")

    return True


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Export GeoJSON building data to PMTiles format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (uses default paths)
  python export_pmtiles.py

  # Custom input/output
  python export_pmtiles.py -i data/export/buildings.geojson -o tiles/buildings.pmtiles

  # Adjust zoom levels for different use cases
  python export_pmtiles.py --min-zoom 8 --max-zoom 18  # Wider range
  python export_pmtiles.py --min-zoom 12 --max-zoom 14  # Narrower range

  # With metadata
  python export_pmtiles.py \\
    --name "Trondheim Historical Buildings" \\
    --description "Building footprints 1700-present" \\
    --attribution "© Kartverket, OpenStreetMap contributors"

Frontend usage:
  1. Host PMTiles on static server with range request support
  2. Add PMTiles protocol to MapLibre:
     import { Protocol } from 'pmtiles';
     let protocol = new Protocol();
     maplibregl.addProtocol('pmtiles', protocol.tile);
  3. Add source:
     map.addSource('buildings', {
       type: 'vector',
       url: 'pmtiles://https://example.com/buildings.pmtiles'
     });
  4. Filter by year using expressions:
     ['all',
       ['<=', ['get', 'sd'], year],
       ['any',
         ['>=', ['get', 'ed'], year],
         ['!', ['has', 'ed']]
       ]
     ]
"""
    )

    parser.add_argument(
        '--input', '-i',
        type=Path,
        default=Path(__file__).parent.parent.parent / 'data' / 'export' / 'buildings.geojson',
        help='Path to input GeoJSON file (default: data/export/buildings.geojson)'
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=Path(__file__).parent.parent.parent / 'data' / 'export' / 'buildings.pmtiles',
        help='Path to output PMTiles file (default: data/export/buildings.pmtiles)'
    )
    parser.add_argument(
        '--min-zoom',
        type=int,
        default=10,
        help='Minimum zoom level (default: 10, city-level)'
    )
    parser.add_argument(
        '--max-zoom',
        type=int,
        default=16,
        help='Maximum zoom level (default: 16, building detail)'
    )
    parser.add_argument(
        '--layer',
        type=str,
        default='buildings',
        help='Layer name in tiles (default: buildings)'
    )
    parser.add_argument(
        '--name',
        type=str,
        help='Tileset name for metadata'
    )
    parser.add_argument(
        '--description',
        type=str,
        help='Tileset description for metadata'
    )
    parser.add_argument(
        '--attribution',
        type=str,
        help='Attribution text for metadata'
    )
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Overwrite existing output file'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress progress output'
    )

    args = parser.parse_args()

    success = export_pmtiles(
        input_path=args.input,
        output_path=args.output,
        min_zoom=args.min_zoom,
        max_zoom=args.max_zoom,
        layer_name=args.layer,
        name=args.name,
        description=args.description,
        attribution=args.attribution,
        force=args.force,
        verbose=not args.quiet
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
