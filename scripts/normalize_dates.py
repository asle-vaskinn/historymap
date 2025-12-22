#!/usr/bin/env python3
"""
Normalize all date fields in GeoJSON to integers.
Also implements the unified schema with proper date types.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

def parse_date(value: Any) -> Optional[int]:
    """Parse a date value to an integer year."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        # Handle various string formats
        value = value.strip()
        # Pure year: "1880"
        if re.match(r'^\d{4}$', value):
            return int(value)
        # Date: "1880-01-01"
        match = re.match(r'^(\d{4})', value)
        if match:
            return int(match.group(1))
        # Range: "1880-1890" -> use start
        match = re.match(r'^(\d{4})\s*[-–]\s*(\d{4})$', value)
        if match:
            return int(match.group(1))
        # Decade: "1880s" -> 1880
        match = re.match(r'^(\d{3})0s$', value)
        if match:
            return int(match.group(1)) * 10
        # Century: "19th century" -> 1800
        match = re.match(r'^(\d{1,2})(?:st|nd|rd|th)\s+century', value, re.I)
        if match:
            return (int(match.group(1)) - 1) * 100
    return None

def determine_date_type(source: str) -> str:
    """Determine date type code from source."""
    if source in ('sefrak', 'osm', 'matrikkelen'):
        return 'x'  # exact
    elif source.startswith('ml_'):
        if 'matched' in source:
            return 'n'  # not-later-than (strong evidence)
        elif 'not_detected' in source:
            # NOT DETECTED is WEAK evidence - don't use it to hide buildings!
            # The ML only detected ~260 of thousands of 1880 buildings
            return 'u'  # unknown - should show at all times
    return 'u'  # unknown

def source_code(source: str) -> str:
    """Convert source name to short code."""
    mapping = {
        'sefrak': 'sef',
        'osm': 'osm',
        'osm_assumed': 'est',
        'ml_1880_matched': 'ml80',
        'ml_1880_not_detected': 'ml80',
        'matrikkelen': 'mat',
        'derived': 'der'
    }
    return mapping.get(source, source[:3])

def normalize_feature(feature: Dict, is_demolished: bool = False) -> Dict:
    """Normalize a single feature's date properties."""
    props = feature.get('properties', {})
    new_props = {}

    # Copy non-date properties
    for key, value in props.items():
        if key not in ('start_date', 'end_date', 'source', 'confidence',
                       'ml_confidence', 'sefrak_period', 'start_date_min',
                       'existed_in', 'status'):
            new_props[key] = value

    # Building ID
    if 'osm_id' in props:
        new_props['bid'] = f"osm_{props['osm_id']}"
    elif 'bid' in props:
        new_props['bid'] = props['bid']

    # Handle demolished buildings specially
    if is_demolished or props.get('status') == 'demolished':
        existed_in = props.get('existed_in', 1880)
        new_props['sd'] = existed_in
        new_props['sd_t'] = 'n'  # not-later-than
        new_props['sd_s'] = 'ml80'
        new_props['sd_c'] = props.get('confidence', 0.7)
        new_props['ed'] = 2000  # Unknown, but sometime before present
        new_props['ed_t'] = 's'  # estimated
        new_props['ed_s'] = 'ml80'
        new_props['btype'] = 'demolished'
        return {
            'type': 'Feature',
            'properties': new_props,
            'geometry': feature['geometry']
        }

    # Start date handling
    start_date = parse_date(props.get('start_date'))
    source = props.get('source', 'est')
    date_type = determine_date_type(source)

    if date_type == 'u':
        # Unknown date - building should show at all times
        # Don't set sd at all, or use very old date
        # Frontend will treat missing sd as "always visible"
        new_props['sd_t'] = 'u'
        new_props['sd_s'] = source_code(source)
    elif start_date is not None:
        new_props['sd'] = start_date
        new_props['sd_t'] = date_type
        new_props['sd_s'] = source_code(source)

        # Add confidence if not exact
        if new_props['sd_t'] not in ('x', 'u'):
            conf = props.get('ml_confidence') or props.get('confidence') or 0.5
            new_props['sd_c'] = round(float(conf), 2)

    # Handle SEFRAK periods like "1830-1840"
    if 'sefrak_period' in props:
        period = props['sefrak_period']
        match = re.match(r'^(\d{4})\s*[-–]\s*(\d{4})$', period)
        if match:
            new_props['sd'] = int(match.group(1))
            new_props['sd_max'] = int(match.group(2))
            new_props['sd_t'] = 'x'
            new_props['sd_s'] = 'sef'

    # End date handling
    end_date = parse_date(props.get('end_date'))
    if end_date is not None and end_date != 2025:
        new_props['ed'] = end_date
        new_props['ed_t'] = 's'  # Usually estimated for demolished
        new_props['ed_s'] = source_code(source)

    # Building type
    if 'building' in props:
        new_props['btype'] = props['building']
    if 'name' in props and props['name']:
        new_props['name'] = props['name']

    return {
        'type': 'Feature',
        'properties': new_props,
        'geometry': feature['geometry']
    }

def normalize_geojson(input_path: Path, output_path: Path, is_demolished: bool = False):
    """Normalize all features in a GeoJSON file."""
    print(f"Processing {input_path}...")

    with open(input_path, 'r') as f:
        data = json.load(f)

    normalized_features = []
    for feature in data.get('features', []):
        try:
            normalized = normalize_feature(feature, is_demolished=is_demolished)
            normalized_features.append(normalized)
        except Exception as e:
            print(f"  Warning: Failed to normalize feature: {e}")
            continue

    output_data = {
        'type': 'FeatureCollection',
        'name': data.get('name', 'Normalized Buildings'),
        'features': normalized_features
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f)

    print(f"  Normalized {len(normalized_features)} features")
    print(f"  Output: {output_path}")

    # Print stats
    date_types = {}
    sources = {}
    for feat in normalized_features:
        props = feat.get('properties', {})
        dt = props.get('sd_t', 'none')
        src = props.get('sd_s', 'none')
        date_types[dt] = date_types.get(dt, 0) + 1
        sources[src] = sources.get(src, 0) + 1

    print(f"\n  Date types: {date_types}")
    print(f"  Sources: {sources}")

def main():
    data_dir = Path(__file__).parent.parent / 'data'

    # Normalize dated buildings
    normalize_geojson(
        data_dir / 'buildings_dated.geojson',
        data_dir / 'buildings_unified.geojson',
        is_demolished=False
    )

    # Normalize demolished buildings
    normalize_geojson(
        data_dir / 'buildings_demolished_since_1880.geojson',
        data_dir / 'buildings_demolished_unified.geojson',
        is_demolished=True
    )

    print("\nDone! Use buildings_unified.geojson for the frontend.")

if __name__ == '__main__':
    main()
