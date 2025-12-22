#!/usr/bin/env python3
"""
Normalize building data with era-based evidence requirements.

Rules:
- Modern buildings (in OSM) exist today, so:
  - Post-1950: Show unless strong evidence they didn't exist
  - 1900-1950: Need medium evidence to show
  - Pre-1900: Need strong evidence to show

- Evidence strength:
  - Strong (h): SEFRAK, Matrikkelen, OSM date tag, ML detection
  - Medium (m): Building type inference, statistical
  - Low (l): No evidence / assumed

- Demolished buildings: Need strong evidence (ML detection)
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

def parse_date(value: Any) -> Optional[int]:
    """Parse a date value to an integer year."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        if re.match(r'^\d{4}$', value):
            return int(value)
        match = re.match(r'^(\d{4})', value)
        if match:
            return int(match.group(1))
        match = re.match(r'^(\d{4})\s*[-–]\s*(\d{4})$', value)
        if match:
            return int(match.group(1))
    return None

def determine_evidence_strength(source: str, has_date: bool) -> str:
    """
    Determine evidence strength.
    Returns: 'h' (high/strong), 'm' (medium), 'l' (low/weak)
    """
    if source in ('sefrak', 'matrikkelen'):
        return 'h'  # Registry data is strong
    if source == 'osm' and has_date:
        return 'h'  # OSM with explicit date is strong
    if source == 'ml_1880_matched':
        return 'h'  # ML detection is strong evidence of existence
    if source == 'osm':
        return 'l'  # OSM without date - building exists but date unknown
    if source in ('ml_1880_not_detected', 'osm_assumed', 'est'):
        return 'l'  # No evidence
    return 'l'

def source_code(source: str) -> str:
    """Convert source name to short code."""
    mapping = {
        'sefrak': 'sef',
        'osm': 'osm',
        'osm_assumed': 'osm',
        'ml_1880_matched': 'ml',
        'ml_1880_not_detected': 'osm',
        'matrikkelen': 'mat',
    }
    return mapping.get(source, 'unk')

def normalize_building(feature: Dict) -> Dict:
    """Normalize a single building feature."""
    props = feature.get('properties', {})
    new_props = {}

    # Building ID
    if 'osm_id' in props:
        new_props['bid'] = props['osm_id']

    # Get source and date info
    source = props.get('source', 'osm_assumed')
    start_date = parse_date(props.get('start_date'))
    has_explicit_date = start_date is not None and source in ('sefrak', 'osm', 'matrikkelen')

    # Evidence strength
    ev = determine_evidence_strength(source, has_explicit_date)
    new_props['ev'] = ev
    new_props['src'] = source_code(source)

    # Start date handling based on evidence
    if ev == 'h':
        # Strong evidence - use the date
        if start_date:
            new_props['sd'] = start_date
        elif source == 'ml_1880_matched':
            new_props['sd'] = 1880  # ML detected = existed by 1880
    # For medium/low evidence, don't set sd - will use era-based defaults in frontend

    # Handle SEFRAK periods
    if 'sefrak_period' in props:
        period = props['sefrak_period']
        match = re.match(r'^(\d{4})\s*[-–]\s*(\d{4})$', period)
        if match:
            new_props['sd'] = int(match.group(1))
            new_props['ev'] = 'h'
            new_props['src'] = 'sef'

    # ML confidence for matched buildings
    if source == 'ml_1880_matched':
        conf = props.get('ml_confidence', 0.8)
        new_props['mlc'] = round(float(conf), 2)

    # Building metadata
    if 'building' in props:
        new_props['bt'] = props['building']
    if 'name' in props and props['name']:
        new_props['nm'] = props['name']

    return {
        'type': 'Feature',
        'properties': new_props,
        'geometry': feature['geometry']
    }

def normalize_demolished(feature: Dict) -> Dict:
    """Normalize a demolished building feature."""
    props = feature.get('properties', {})
    new_props = {}

    existed_in = props.get('existed_in', 1880)

    new_props['sd'] = existed_in
    new_props['ev'] = 'h'  # ML detection is strong evidence
    new_props['src'] = 'ml'
    new_props['dem'] = 1  # Flag as demolished
    new_props['mlc'] = props.get('confidence', 0.7)

    return {
        'type': 'Feature',
        'properties': new_props,
        'geometry': feature['geometry']
    }

def process_file(input_path: Path, output_path: Path, is_demolished: bool = False):
    """Process a GeoJSON file."""
    print(f"Processing {input_path.name}...")

    with open(input_path, 'r') as f:
        data = json.load(f)

    features = []
    for feat in data.get('features', []):
        try:
            if is_demolished:
                normalized = normalize_demolished(feat)
            else:
                normalized = normalize_building(feat)
            features.append(normalized)
        except Exception as e:
            print(f"  Warning: {e}")
            continue

    output_data = {
        'type': 'FeatureCollection',
        'features': features
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f)

    # Stats
    ev_counts = {'h': 0, 'm': 0, 'l': 0}
    src_counts = {}
    has_sd = 0

    for feat in features:
        p = feat['properties']
        ev = p.get('ev', 'l')
        ev_counts[ev] = ev_counts.get(ev, 0) + 1
        src = p.get('src', 'unk')
        src_counts[src] = src_counts.get(src, 0) + 1
        if 'sd' in p:
            has_sd += 1

    print(f"  Total: {len(features)}")
    print(f"  Evidence: {ev_counts}")
    print(f"  Sources: {src_counts}")
    print(f"  With start date: {has_sd}")
    print(f"  Output: {output_path}")

def main():
    data_dir = Path(__file__).parent.parent / 'data'

    # Process main buildings
    process_file(
        data_dir / 'buildings_dated.geojson',
        data_dir / 'buildings_v2.geojson',
        is_demolished=False
    )

    # Process demolished buildings
    process_file(
        data_dir / 'buildings_demolished_since_1880.geojson',
        data_dir / 'buildings_demolished_v2.geojson',
        is_demolished=True
    )

    print("\nDone!")

if __name__ == '__main__':
    main()
