#!/usr/bin/env python3
"""
Export sources manifest for frontend.

Reads all ML source manifests and generates a combined JSON file
that the frontend can use to discover available historical map sources.
"""

import json
import argparse
from pathlib import Path
from typing import Dict, Any, List


def discover_ml_sources(sources_dir: Path) -> Dict[str, Dict[str, Any]]:
    """
    Discover all ML detection sources.

    Returns:
        Dict mapping source_key (e.g., 'kv1880') to source config
    """
    ml_dir = sources_dir / 'ml_detected'
    if not ml_dir.exists():
        print(f"ML sources directory not found: {ml_dir}")
        return {}

    sources = {}

    for manifest_path in ml_dir.rglob('manifest.json'):
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to read {manifest_path}: {e}")
            continue

        source_id = manifest.get('source_id', '')
        if not source_id.startswith('ml_'):
            continue

        # Create frontend key from source_id
        # ml_kartverket_1880 -> kv1880
        # ml_kartverket_1904 -> kv1904
        # ml_aerial_1947 -> air1947
        key = create_frontend_key(source_id)

        # Get source directory relative to manifest
        source_dir = manifest_path.parent

        source_config = {
            'name': manifest.get('short_name', manifest.get('source_name', 'Unknown')),
            'year': manifest.get('coverage', {}).get('temporal', {}).get('reference_year'),
            'bounds': manifest.get('coverage', {}).get('spatial', {}).get('bounds'),
            # Relative to sources_dir (e.g., ml_detected/kartverket_1880)
            'source_dir': str(source_dir.relative_to(sources_dir)),
        }

        # Add raster info if present
        rasters = manifest.get('source_rasters', {})
        if rasters:
            source_config['raster_type'] = rasters.get('type', 'image')
            source_config['attribution'] = rasters.get('attribution', '')

            if rasters.get('type') == 'tiles':
                source_config['tile_url'] = rasters.get('tile_url')
                source_config['minzoom'] = rasters.get('minzoom', 10)
                source_config['maxzoom'] = rasters.get('maxzoom', 16)
            elif rasters.get('type') in ('image', 'mosaic'):
                # Convert relative paths to paths from data directory
                images = []
                for img in rasters.get('images', []):
                    images.append({
                        'url': f"{source_config['source_dir']}/{img['path']}",
                        'bounds': img['bounds']
                    })
                source_config['images'] = images

        # Add feature files info
        normalized_dir = source_dir / 'normalized'
        feature_files = {}

        buildings_file = normalized_dir / 'buildings.geojson'
        if buildings_file.exists():
            feature_files['buildings'] = f"{source_config['source_dir']}/normalized/buildings.geojson"

        roads_file = normalized_dir / 'roads.geojson'
        if roads_file.exists():
            feature_files['roads'] = f"{source_config['source_dir']}/normalized/roads.geojson"

        source_config['features'] = feature_files

        sources[key] = source_config

    return sources


def create_frontend_key(source_id: str) -> str:
    """
    Convert source_id to frontend key.

    Examples:
        ml_kartverket_1880 -> kv1880
        ml_kartverket_1904 -> kv1904
        ml_aerial_1947 -> air1947
    """
    # Remove ml_ prefix
    name = source_id.replace('ml_', '')

    # Handle known patterns
    if name.startswith('kartverket_'):
        year = name.replace('kartverket_', '')
        return f'kv{year}'
    elif name.startswith('aerial_'):
        year = name.replace('aerial_', '')
        return f'air{year}'
    else:
        # Generic: just remove underscores
        return name.replace('_', '')


def export_manifest(sources: Dict[str, Dict], output_path: Path,
                   base_url: str = '../data/sources') -> bool:
    """
    Export sources manifest for frontend.

    Args:
        sources: Dict of source configs
        output_path: Where to write the manifest
        base_url: Base URL prefix for paths (relative to frontend)

    Returns:
        True if successful
    """
    # Transform paths to use base_url
    manifest = {
        'version': '1.0',
        'generated_at': None,  # Will be set below
        'base_url': base_url,
        'sources': {}
    }

    from datetime import datetime, timezone
    manifest['generated_at'] = datetime.now(timezone.utc).isoformat()

    for key, config in sources.items():
        source_entry = {
            'name': config['name'],
            'year': config['year'],
            'bounds': config['bounds'],
        }

        # Raster config
        if config.get('raster_type'):
            raster = {
                'type': config['raster_type'],
                'attribution': config.get('attribution', '')
            }

            if config['raster_type'] == 'tiles':
                # Convert source_dir path to URL
                tile_url = config.get('tile_url', '')
                if tile_url:
                    raster['url'] = f"{base_url}/{config['source_dir']}/{tile_url}"
                raster['minzoom'] = config.get('minzoom', 10)
                raster['maxzoom'] = config.get('maxzoom', 16)
                raster['bounds'] = config.get('bounds')
            else:
                # image or mosaic
                images = []
                for img in config.get('images', []):
                    images.append({
                        'url': f"{base_url}/{img['url']}",
                        'bounds': img['bounds']
                    })
                raster['images'] = images

            source_entry['raster'] = raster

        # Feature files
        features = config.get('features', {})
        if features:
            source_entry['features'] = {
                feat_type: f"{base_url}/{path}"
                for feat_type, path in features.items()
            }

        manifest['sources'][key] = source_entry

    # Sort sources by year
    manifest['sources'] = dict(
        sorted(manifest['sources'].items(),
               key=lambda x: x[1].get('year', 9999))
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"Exported {len(sources)} sources to {output_path}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Export sources manifest for frontend',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python export_sources_manifest.py                    # Default output
  python export_sources_manifest.py -o custom.json     # Custom output path
  python export_sources_manifest.py --base-url ./data  # Custom base URL
"""
    )

    parser.add_argument('-d', '--data-dir', type=Path,
                        default=Path(__file__).parent.parent.parent / 'data',
                        help='Base data directory')
    parser.add_argument('-o', '--output', type=Path,
                        default=None,
                        help='Output path (default: frontend/data/sources_manifest.json)')
    parser.add_argument('--base-url', type=str,
                        default='../data/sources',
                        help='Base URL prefix for paths relative to frontend')

    args = parser.parse_args()

    # Default output to frontend/data/
    if args.output is None:
        frontend_data = args.data_dir.parent / 'frontend' / 'data'
        args.output = frontend_data / 'sources_manifest.json'

    sources_dir = args.data_dir / 'sources'

    print(f"Discovering ML sources in {sources_dir}...")
    sources = discover_ml_sources(sources_dir)

    if not sources:
        print("No ML sources found!")
        return 1

    print(f"Found {len(sources)} ML sources: {list(sources.keys())}")

    if not export_manifest(sources, args.output, args.base_url):
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
