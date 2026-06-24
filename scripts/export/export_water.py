#!/usr/bin/env python3
"""
Export merged water data to frontend-ready format.

Transforms internal schema to compact frontend format and generates
water.geojson for the MapLibre GL JS frontend.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Import canonical source mappings from constants
try:
    from constants import (
        SOURCE_SHORT_CODES,
        WATER_MERGED,
        WATER_EXPORT,
        WATER_PMTILES,
        to_short_code,
        is_valid_source,
    )
except ImportError:
    # Fallback for running directly
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from constants import (
        SOURCE_SHORT_CODES,
        WATER_MERGED,
        WATER_EXPORT,
        WATER_PMTILES,
        to_short_code,
        is_valid_source,
    )


def get_source_code(source: str) -> str:
    """Map internal source name to compact frontend code.

    Args:
        source: Source ID (e.g., 'manual', 'osm')

    Returns:
        Short code (e.g., 'man', 'osm')
    """
    # Handle short codes that may already be in the data
    if source in ['man', 'osm', 'ml']:
        return source

    # Check canonical mapping
    if source in SOURCE_SHORT_CODES:
        return SOURCE_SHORT_CODES[source]

    # Manual source variations
    if source.lower() in ['manual', 'man']:
        return 'man'

    # OSM variations
    if 'osm' in source.lower():
        return 'osm'

    # ML sources
    if source.startswith('ml_'):
        return 'ml'

    return 'unk'


def generate_wid(src: str, src_id: str) -> str:
    """
    Generate compact water feature ID.

    Args:
        src: Source ID (e.g., 'manual', 'osm')
        src_id: Source-specific ID (e.g., 'brattora_harbor', 'way/123456')

    Returns:
        Compact ID (e.g., 'man-brattora_harbor', 'osm-123456')
    """
    short_src = get_source_code(src)

    # Clean up source ID
    # Remove common prefixes and clean separators
    clean_id = src_id.replace('way/', '').replace('relation/', '')

    return f"{short_src}-{clean_id}"


def transform_feature(feature: Dict) -> Dict:
    """Transform a water feature to frontend format."""
    props = feature.get('properties', {})
    geom = feature.get('geometry')

    # Build compact frontend properties
    frontend_props = {}

    # Source
    src = props.get('_src', '')
    frontend_props['src'] = get_source_code(src)

    # Generate compact water ID
    src_id = props.get('_src_id', '')
    if src_id:
        frontend_props['wid'] = generate_wid(src, src_id)
    else:
        # Fallback: generate ID from geometry hash or index
        frontend_props['wid'] = f"{frontend_props['src']}-unknown"

    # Required fields
    if props.get('sd'):
        frontend_props['sd'] = props['sd']
    if props.get('ed'):
        frontend_props['ed'] = props['ed']

    # Evidence
    ev = props.get('ev', 'l')
    frontend_props['ev'] = ev

    # Water type (fjord, river, lake, canal, harbor, pond, stream)
    if props.get('wtype'):
        frontend_props['wtype'] = props['wtype']

    # Name
    if props.get('name'):
        frontend_props['nm'] = props['name']
    elif props.get('nm'):
        frontend_props['nm'] = props['nm']

    return {
        'type': 'Feature',
        'properties': frontend_props,
        'geometry': geom
    }


def export_water(
    input_path: Path,
    output_path: Path
) -> bool:
    """
    Export merged water features to frontend format.

    Args:
        input_path: Path to water_merged.geojson
        output_path: Path to output water.geojson

    Returns:
        True if successful
    """
    print(f"Loading merged water features from {input_path}...")

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return False

    with open(input_path) as f:
        data = json.load(f)

    features = data.get('features', [])
    print(f"  Loaded {len(features)} water features")

    # Transform features
    print("Transforming to frontend format...")
    frontend_features = []

    for feat in features:
        transformed = transform_feature(feat)
        frontend_features.append(transformed)

    print(f"  Transformed {len(frontend_features)} features")

    # Generate output
    output = {
        'type': 'FeatureCollection',
        'features': frontend_features,
        'metadata': {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'source': str(input_path),
            'count': len(frontend_features)
        }
    }

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    # Print stats
    by_source = {}
    by_wtype = {}
    with_dates = 0
    with_end_dates = 0

    for feat in frontend_features:
        src = feat['properties'].get('src', 'unk')
        by_source[src] = by_source.get(src, 0) + 1

        wtype = feat['properties'].get('wtype', 'unknown')
        by_wtype[wtype] = by_wtype.get(wtype, 0) + 1

        if feat['properties'].get('sd'):
            with_dates += 1
        if feat['properties'].get('ed'):
            with_end_dates += 1

    print(f"\nExport complete:")
    print(f"  Total water features: {len(frontend_features)}")
    print(f"  Features with start dates: {with_dates}")
    print(f"  Features with end dates: {with_end_dates}")
    print(f"  By source: {by_source}")
    print(f"  By water type: {by_wtype}")

    return True


def generate_pmtiles(
    input_path: Path,
    output_path: Path,
    min_zoom: int = 8,
    max_zoom: int = 16
) -> bool:
    """
    Generate PMTiles from water GeoJSON using tippecanoe.

    Args:
        input_path: Path to water.geojson
        output_path: Path to output water.pmtiles

    Returns:
        True if successful
    """
    import subprocess

    print(f"\nGenerating PMTiles from {input_path}...")

    # Check if tippecanoe is available
    try:
        subprocess.run(['tippecanoe', '--version'],
                      capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Warning: tippecanoe not found. Skipping PMTiles generation.")
        print("Install with: brew install tippecanoe")
        return False

    cmd = [
        'tippecanoe',
        '--output', str(output_path),
        '--force',  # Overwrite existing
        '--layer', 'water',
        '--minimum-zoom', str(min_zoom),
        '--maximum-zoom', str(max_zoom),
        # Polygon-specific options
        '--coalesce-densest-as-needed',
        '--extend-zooms-if-still-dropping',
        # Attribute types
        '--attribute-type=sd:int',
        '--attribute-type=ed:int',
        str(input_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"tippecanoe error: {result.stderr}")
            return False

        print(f"PMTiles generated: {output_path}")
        return True

    except Exception as e:
        print(f"Error generating PMTiles: {e}")
        return False


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Export water data to frontend format')
    parser.add_argument('--input', '-i', type=Path,
                        default=WATER_MERGED,
                        help=f'Input merged water GeoJSON (default: {WATER_MERGED})')
    parser.add_argument('--output', '-o', type=Path,
                        default=WATER_EXPORT,
                        help=f'Output frontend GeoJSON (default: {WATER_EXPORT})')

    args = parser.parse_args()

    # Export to GeoJSON
    success = export_water(args.input, args.output)
    if not success:
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
