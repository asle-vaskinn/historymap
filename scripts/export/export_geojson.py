#!/usr/bin/env python3
"""
Export merged building data to frontend-ready GeoJSON format.

Transforms merged building data from data/merged/buildings_merged.geojson
to a compact, frontend-optimized format in data/export/buildings.geojson.

Transformations:
1. Compact source codes: sefrak→sef, osm→osm, ml_*→ml
2. Generate compact building IDs from _src and _src_id
3. Keep only frontend-required fields
4. Strip development metadata (_raw, _merge_info, _ingested)
5. Add src_all array if multiple sources contributed
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# Source code mappings: full name → short code
SOURCE_CODES = {
    'sefrak': 'sef',
    'trondheim_kommune': 'tk',
    'osm': 'osm',
    'matrikkelen': 'mat',
    'ml_kartverket_1880': 'ml',
    'ml_kartverket_1904': 'ml',
    'ml_aerial_1947': 'ml',
    'ml_aerial_1964': 'ml',
}

# ML source codes: full name → map identifier
ML_SOURCE_CODES = {
    'ml_kartverket_1880': 'kv1880',
    'ml_kartverket_1904': 'kv1904',
    'ml_aerial_1947': 'air1947',
    'ml_aerial_1964': 'air1964',
}


def generate_bid(src: str, src_id: str) -> str:
    """
    Generate compact building ID.

    Args:
        src: Source ID (e.g., 'sefrak', 'osm')
        src_id: Source-specific ID (e.g., 'SEFRAK-12345', 'way/123456')

    Returns:
        Compact ID (e.g., 'sef-12345', 'osm-123456')
    """
    short_src = SOURCE_CODES.get(src, src)

    # Clean up source ID
    # Remove common prefixes and clean separators
    clean_id = src_id.replace('SEFRAK-', '').replace('way/', '').replace('relation/', '')

    return f"{short_src}-{clean_id}"


def transform_feature(feature: Dict) -> Dict:
    """
    Transform a merged feature to frontend format.

    Args:
        feature: Merged GeoJSON feature

    Returns:
        Frontend-ready GeoJSON feature
    """
    props = feature.get('properties', {})

    # Get source information
    src = props.get('_src', 'unknown')
    src_id = props.get('_src_id', 'unknown')
    src_all = props.get('src_all', [src])

    # Generate compact building ID
    bid = generate_bid(src, src_id)

    # Build frontend properties
    frontend_props = {
        'bid': bid,
        'src': SOURCE_CODES.get(src, src),
    }

    # Add src_all if multiple sources contributed
    if len(src_all) > 1:
        frontend_props['src_all'] = [SOURCE_CODES.get(s, s) for s in src_all]

    # Copy core temporal fields
    if 'sd' in props:
        frontend_props['sd'] = props['sd']
    if 'ed' in props:
        frontend_props['ed'] = props['ed']
    if 'ev' in props:
        frontend_props['ev'] = props['ev']

    # Copy ML-specific fields
    if src.startswith('ml_'):
        frontend_props['ml_src'] = ML_SOURCE_CODES.get(src, src)
        if 'mlc' in props:
            frontend_props['mlc'] = props['mlc']

    # Copy building metadata
    if 'bt' in props:
        frontend_props['bt'] = props['bt']
    if 'nm' in props:
        frontend_props['nm'] = props['nm']

    # Copy replacement information
    if 'rep_by' in props:
        # Transform rep_by ID to frontend format
        rep_src = props.get('_merge_info', {}).get('sources', {})
        # Try to find the replacing building's source
        # For now, keep as-is but we could enhance this
        frontend_props['rep_by'] = props['rep_by']
    if 'rep_ev' in props:
        frontend_props['rep_ev'] = props['rep_ev']

    return {
        'type': 'Feature',
        'properties': frontend_props,
        'geometry': feature.get('geometry')
    }


def export_geojson(
    input_path: Path,
    output_path: Path,
    stats: bool = True
) -> bool:
    """
    Export merged GeoJSON to frontend format.

    Args:
        input_path: Path to merged buildings GeoJSON
        output_path: Path to write frontend GeoJSON
        stats: Print statistics

    Returns:
        True if successful
    """
    print(f"Loading merged data from {input_path}...")

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return False

    with open(input_path) as f:
        data = json.load(f)

    features = data.get('features', [])
    print(f"  Loaded {len(features)} features")

    # Transform features
    print("\nTransforming to frontend format...")
    frontend_features = []

    for feat in features:
        try:
            transformed = transform_feature(feat)
            frontend_features.append(transformed)
        except Exception as e:
            print(f"  Warning: Failed to transform feature: {e}")
            continue

    print(f"  Transformed {len(frontend_features)} features")

    # Calculate statistics
    if stats:
        print("\n" + "="*60)
        print("EXPORT STATISTICS")
        print("="*60)

        # Count by source
        by_source = {}
        for feat in frontend_features:
            src = feat['properties'].get('src', 'unknown')
            by_source[src] = by_source.get(src, 0) + 1

        print(f"\nTotal features: {len(frontend_features)}")
        print("\nBy source:")
        for src in sorted(by_source.keys()):
            count = by_source[src]
            pct = (count / len(frontend_features) * 100) if frontend_features else 0
            print(f"  {src:10s}: {count:6d} ({pct:5.1f}%)")

        # Count with dates
        with_sd = sum(1 for f in frontend_features if 'sd' in f['properties'])
        with_ed = sum(1 for f in frontend_features if 'ed' in f['properties'])

        print(f"\nTemporal data:")
        print(f"  With start date: {with_sd:6d} ({with_sd/len(frontend_features)*100:5.1f}%)")
        print(f"  With end date:   {with_ed:6d} ({with_ed/len(frontend_features)*100:5.1f}%)")

        # Count by evidence level
        by_evidence = {}
        for feat in frontend_features:
            ev = feat['properties'].get('ev', 'unknown')
            by_evidence[ev] = by_evidence.get(ev, 0) + 1

        print(f"\nBy evidence level:")
        for ev in ['h', 'm', 'l']:
            count = by_evidence.get(ev, 0)
            pct = (count / len(frontend_features) * 100) if frontend_features else 0
            print(f"  {ev} (high/med/low): {count:6d} ({pct:5.1f}%)")

        # Count ML detections
        ml_count = sum(1 for f in frontend_features if 'ml_src' in f['properties'])
        if ml_count > 0:
            print(f"\nML-detected buildings: {ml_count}")

            by_ml_src = {}
            for feat in frontend_features:
                ml_src = feat['properties'].get('ml_src')
                if ml_src:
                    by_ml_src[ml_src] = by_ml_src.get(ml_src, 0) + 1

            print("  By map source:")
            for ml_src in sorted(by_ml_src.keys()):
                count = by_ml_src[ml_src]
                print(f"    {ml_src:10s}: {count:6d}")

        # Count multi-source buildings
        multi_source = sum(1 for f in frontend_features if 'src_all' in f['properties'])
        if multi_source > 0:
            print(f"\nMulti-source buildings: {multi_source}")

        # Count replacements
        replaced = sum(1 for f in frontend_features if 'rep_by' in f['properties'])
        if replaced > 0:
            print(f"Replaced buildings: {replaced}")

        # Date range
        dates = [f['properties']['sd'] for f in frontend_features if 'sd' in f['properties']]
        if dates:
            print(f"\nDate range: {min(dates)} - {max(dates)}")

        print("="*60)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        'type': 'FeatureCollection',
        'features': frontend_features
    }

    print(f"\nWriting output to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(output, f)

    # Calculate file size
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  File size: {size_mb:.2f} MB")

    # Write export metadata
    metadata = {
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'source_file': str(input_path),
        'feature_count': len(frontend_features),
        'size_mb': round(size_mb, 2),
        'statistics': {
            'by_source': by_source if stats else {},
            'with_dates': {
                'start_date': with_sd if stats else 0,
                'end_date': with_ed if stats else 0
            },
            'ml_detected': ml_count if stats else 0,
            'multi_source': multi_source if stats else 0,
            'replaced': replaced if stats else 0,
            'date_range': {
                'min': min(dates) if dates else None,
                'max': max(dates) if dates else None
            } if stats and dates else None
        }
    }

    metadata_path = output_path.with_suffix('.meta.json')
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"  Metadata: {metadata_path}")
    print("\nExport complete!")

    return True


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Export merged building data to frontend-ready GeoJSON'
    )
    parser.add_argument(
        '--input', '-i',
        type=Path,
        default=Path(__file__).parent.parent.parent / 'data' / 'merged' / 'buildings_merged.geojson',
        help='Path to merged buildings GeoJSON (default: data/merged/buildings_merged.geojson)'
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=Path(__file__).parent.parent.parent / 'data' / 'export' / 'buildings.geojson',
        help='Path to write frontend GeoJSON (default: data/export/buildings.geojson)'
    )
    parser.add_argument(
        '--no-stats',
        action='store_true',
        help='Disable statistics output'
    )

    args = parser.parse_args()

    success = export_geojson(
        input_path=args.input,
        output_path=args.output,
        stats=not args.no_stats
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
