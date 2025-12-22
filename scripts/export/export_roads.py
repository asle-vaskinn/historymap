#!/usr/bin/env python3
"""
Export merged road data to frontend-ready format.

Transforms internal schema to compact frontend format and generates
roads_temporal.geojson for the MapLibre GL JS frontend.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# Source code mappings for frontend
SOURCE_CODES = {
    'nvdb': 'nvdb',
    'osm_roads': 'osm',
    'kulturminner': 'kult',
    'ml_detected': 'ml',
}


def get_source_code(source: str) -> str:
    """Map internal source name to compact frontend code."""
    for key, code in SOURCE_CODES.items():
        if key in source.lower():
            return code
    return 'unk'


def transform_feature(feature: Dict) -> Dict:
    """Transform a road feature to frontend format."""
    props = feature.get('properties', {})
    geom = feature.get('geometry')

    # Build compact frontend properties
    frontend_props = {}

    # Required fields
    if props.get('sd'):
        frontend_props['sd'] = props['sd']
    if props.get('ed'):
        frontend_props['ed'] = props['ed']

    # Evidence
    ev = props.get('ev', 'l')
    frontend_props['ev'] = ev

    # Road type
    if props.get('rt'):
        frontend_props['rt'] = props['rt']

    # Name
    if props.get('nm'):
        frontend_props['nm'] = props['nm']

    # Length (km, rounded)
    if props.get('len'):
        frontend_props['len'] = round(props['len'] / 1000, 2)

    # Source
    src = props.get('_src', '')
    frontend_props['src'] = get_source_code(src)

    # ML-specific fields
    if props.get('mlc'):
        frontend_props['mlc'] = round(props['mlc'], 2)
    if props.get('ml_src'):
        frontend_props['ml_src'] = props['ml_src']

    # NVDB ID for linking
    if props.get('nvdb_id'):
        frontend_props['nvdb_id'] = props['nvdb_id']

    # Generate compact road ID
    src_id = props.get('_src_id', '')
    if src_id:
        # Shorten the ID for frontend
        if '_' in src_id:
            parts = src_id.split('_')
            rid = '_'.join(parts[-2:]) if len(parts) > 2 else parts[-1]
        else:
            rid = src_id[-10:]  # Last 10 chars
        frontend_props['rid'] = rid

    return {
        'type': 'Feature',
        'properties': frontend_props,
        'geometry': geom
    }


def export_roads(
    input_path: Path,
    output_path: Path,
    min_confidence: float = 0.5
) -> bool:
    """
    Export merged roads to frontend format.

    Args:
        input_path: Path to roads_merged.geojson
        output_path: Path to output roads_temporal.geojson
        min_confidence: Minimum ML confidence to include

    Returns:
        True if successful
    """
    print(f"Loading merged roads from {input_path}...")

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return False

    with open(input_path) as f:
        data = json.load(f)

    features = data.get('features', [])
    print(f"  Loaded {len(features)} road features")

    # Transform features
    print("Transforming to frontend format...")
    frontend_features = []

    for feat in features:
        props = feat.get('properties', {})

        # Filter low-confidence ML detections
        if props.get('mlc') and props['mlc'] < min_confidence:
            continue

        transformed = transform_feature(feat)
        frontend_features.append(transformed)

    print(f"  Transformed {len(frontend_features)} features")

    # Generate output
    output = {
        'type': 'FeatureCollection',
        'features': frontend_features,
        'metadata': {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'source': str(input_path),
            'count': len(frontend_features)
        }
    }

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(output, f)

    # Print stats
    by_source = {}
    with_dates = 0
    for feat in frontend_features:
        src = feat['properties'].get('src', 'unk')
        by_source[src] = by_source.get(src, 0) + 1
        if feat['properties'].get('sd'):
            with_dates += 1

    print(f"\nExport complete:")
    print(f"  Total roads: {len(frontend_features)}")
    print(f"  Roads with dates: {with_dates}")
    print(f"  By source: {by_source}")

    return True


def generate_pmtiles(
    input_path: Path,
    output_path: Path,
    min_zoom: int = 10,
    max_zoom: int = 16
) -> bool:
    """
    Generate PMTiles from road GeoJSON using tippecanoe.

    Args:
        input_path: Path to roads_temporal.geojson
        output_path: Path to output roads.pmtiles

    Returns:
        True if successful
    """
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
        '--layer', 'roads',
        '--minimum-zoom', str(min_zoom),
        '--maximum-zoom', str(max_zoom),
        # Line-specific options
        '--simplify-only-low-zooms',
        '--coalesce-densest-as-needed',
        # Attribute types
        '--attribute-type=sd:int',
        '--attribute-type=ed:int',
        '--attribute-type=len:float',
        '--attribute-type=mlc:float',
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

    parser = argparse.ArgumentParser(description='Export road data to frontend format')
    parser.add_argument('--input', '-i', type=Path,
                        default=Path(__file__).parent.parent.parent / 'data' / 'merged' / 'roads_merged.geojson',
                        help='Input merged roads GeoJSON')
    parser.add_argument('--output', '-o', type=Path,
                        default=Path(__file__).parent.parent.parent / 'frontend' / 'data' / 'roads_temporal.geojson',
                        help='Output frontend GeoJSON')
    parser.add_argument('--pmtiles', '-p', type=Path, default=None,
                        help='Output PMTiles path (optional)')
    parser.add_argument('--min-confidence', type=float, default=0.5,
                        help='Minimum ML confidence to include')
    parser.add_argument('--min-zoom', type=int, default=10,
                        help='Minimum zoom for PMTiles')
    parser.add_argument('--max-zoom', type=int, default=16,
                        help='Maximum zoom for PMTiles')

    args = parser.parse_args()

    # Export to GeoJSON
    success = export_roads(args.input, args.output, args.min_confidence)
    if not success:
        sys.exit(1)

    # Generate PMTiles if requested
    if args.pmtiles:
        if not generate_pmtiles(args.output, args.pmtiles, args.min_zoom, args.max_zoom):
            print("Warning: PMTiles generation failed")

    sys.exit(0)


if __name__ == '__main__':
    main()
