#!/usr/bin/env python3
"""
Extract building/property data from Trondheim kommune WMS.

Uses GetFeatureInfo requests across a grid to extract property data
including etableringsDato (establishment dates) from the Eiendomsinformasjon layer.
"""

import json
import time
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# Trondheim bounding box in EPSG:4326 (WGS84)
TRONDHEIM_BBOX = {
    'min_lon': 10.20,  # West - focus on central Trondheim
    'max_lon': 10.50,  # East
    'min_lat': 63.40,  # South
    'max_lat': 63.46,  # North
}

# WMS endpoint
WMS_URL = "https://kart5.nois.no/trondheim/api/wms"

# Layers to query
LAYERS = {
    'eiendom': {
        'name': 'Eiendomsinformasjon',
        'theme': 'Eiendomsinformasjon',
    },
    'bygg': {
        'name': 'Bygg',
        'theme': 'Bygg',
    },
}

# Output directory
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "trondheim_wms"


def get_feature_info(lon: float, lat: float, layer: str, theme: str,
                     width: int = 256, height: int = 256) -> dict:
    """
    Make a GetFeatureInfo request at a specific coordinate.

    Returns parsed JSON response or None on error.
    """
    # Create a small bbox around the point
    delta = 0.002  # ~200m at this latitude
    bbox = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"

    params = {
        'SERVICE': 'WMS',
        'VERSION': '1.1.1',
        'REQUEST': 'GetFeatureInfo',
        'LAYERS': layer,
        'QUERY_LAYERS': layer,
        'INFO_FORMAT': 'application/json',
        'SRS': 'EPSG:4326',
        'BBOX': bbox,
        'WIDTH': width,
        'HEIGHT': height,
        'X': width // 2,
        'Y': height // 2,
        'FEATURE_COUNT': 50,  # Get multiple features per request
        f'theme1': theme,
    }

    try:
        response = requests.get(WMS_URL, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"  Request error at ({lon:.4f}, {lat:.4f}): {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"  JSON error at ({lon:.4f}, {lat:.4f}): {e}")
        return None


def extract_features(data: dict, source_layer: str) -> list:
    """Extract features from WMS GetFeatureInfo response."""
    features = []

    if not data:
        return features

    # Response format varies - handle different structures
    if isinstance(data, list):
        layers = data
    elif isinstance(data, dict):
        layers = data.get('layers', [data])
    else:
        return features

    for layer in layers:
        if isinstance(layer, dict):
            rows = layer.get('rows', [])
            layer_name = layer.get('layerName', source_layer)

            for row in rows:
                if isinstance(row, dict):
                    feature = {
                        'layer': layer_name,
                        'properties': row,
                    }
                    features.append(feature)

    return features


def parse_eiendom_features(features: list) -> list:
    """Parse property features and extract relevant fields."""
    parsed = []

    for f in features:
        props = f.get('properties', {})

        # Extract key fields
        parsed_feature = {
            'type': 'Feature',
            'properties': {
                'source': 'trondheim_wms',
                'layer': f.get('layer', 'unknown'),
            },
            'geometry': None,  # Will be set from coordinates if available
        }

        # Map property fields
        field_mapping = {
            # Property identification
            'GNR': 'gnr',
            'BNR': 'bnr',
            'FNR': 'fnr',
            'SNR': 'snr',
            'MATRIKKELNUMMER': 'matrikkelnummer',

            # Dates - the key data we want
            'etableringsDato': 'etablerings_dato',
            'OPPDATERINGSDATO': 'oppdaterings_dato',

            # Location
            'NORD': 'nord',
            'OST': 'ost',
            'ADRESSE': 'adresse',

            # Status flags
            'harKulturminne': 'har_kulturminne',
            'harGrunnforurensing': 'har_grunnforurensing',
            'tinglyst': 'tinglyst',
            'seksjonert': 'seksjonert',

            # Area
            'AREAL': 'areal',
            'oppgittAreal': 'oppgitt_areal',

            # Building info (from Bygg layer)
            'BYGGNR': 'byggnr',
            'BYGGTYP_NBR': 'byggtype',
            'BYGGSTAT': 'byggstatus',
            'DATAFANGSTDATO': 'datafangst_dato',
        }

        for src_key, dst_key in field_mapping.items():
            if src_key in props:
                value = props[src_key]
                # Clean up values
                if value not in [None, '', 'null']:
                    parsed_feature['properties'][dst_key] = value

        # Try to extract year from etableringsDato (format: "M/D/YYYY HH:MM:SS AM")
        etabl_dato = parsed_feature['properties'].get('etablerings_dato')
        if etabl_dato:
            try:
                # Parse date format like "5/7/1889 12:00:00 AM"
                date_part = str(etabl_dato).split()[0]  # Get "5/7/1889"
                parts = date_part.split('/')
                if len(parts) == 3:
                    year = int(parts[2])
                    if 1600 <= year <= 2025:
                        parsed_feature['properties']['start_date'] = year
            except (ValueError, TypeError, IndexError):
                pass

        # Create point geometry if coordinates available
        nord = props.get('NORD')
        ost = props.get('OST')
        if nord and ost:
            try:
                # Convert from UTM to approximate WGS84
                # Note: For accuracy, use pyproj, but this is a rough approximation
                parsed_feature['geometry'] = {
                    'type': 'Point',
                    'coordinates': [float(ost), float(nord)]  # Store UTM coords for now
                }
                parsed_feature['properties']['coord_system'] = 'EPSG:25832'
            except (ValueError, TypeError):
                pass

        # Only add if we have some useful data
        if len(parsed_feature['properties']) > 2:
            parsed.append(parsed_feature)

    return parsed


def generate_grid(bbox: dict, step: float) -> list:
    """Generate a grid of points within the bounding box."""
    points = []
    lon = bbox['min_lon']
    while lon <= bbox['max_lon']:
        lat = bbox['min_lat']
        while lat <= bbox['max_lat']:
            points.append((lon, lat))
            lat += step
        lon += step
    return points


def extract_layer(layer_key: str, bbox: dict, grid_step: float,
                  max_workers: int = 4, delay: float = 0.1) -> list:
    """Extract all features from a layer using grid sampling."""
    layer_info = LAYERS[layer_key]
    layer_name = layer_info['name']
    theme = layer_info['theme']

    print(f"\nExtracting layer: {layer_name}")

    # Generate grid
    grid_points = generate_grid(bbox, grid_step)
    print(f"  Grid points: {len(grid_points)}")

    all_features = []
    seen_ids = set()  # For deduplication

    # Process grid points
    completed = 0
    for lon, lat in grid_points:
        data = get_feature_info(lon, lat, layer_name, theme)
        features = extract_features(data, layer_name)
        parsed = parse_eiendom_features(features)

        for f in parsed:
            # Create unique ID for deduplication
            props = f['properties']
            if 'matrikkelnummer' in props:
                uid = props['matrikkelnummer']
            elif 'byggnr' in props:
                uid = f"bygg_{props['byggnr']}"
            elif 'gnr' in props and 'bnr' in props:
                uid = f"{props.get('gnr', '')}-{props.get('bnr', '')}-{props.get('fnr', '0')}"
            else:
                uid = str(hash(json.dumps(props, sort_keys=True)))

            if uid not in seen_ids:
                seen_ids.add(uid)
                f['properties']['uid'] = uid
                all_features.append(f)

        completed += 1
        if completed % 50 == 0:
            print(f"  Progress: {completed}/{len(grid_points)} points, {len(all_features)} unique features")

        time.sleep(delay)  # Be nice to the server

    print(f"  Total unique features: {len(all_features)}")
    return all_features


def create_geojson(features: list, name: str) -> dict:
    """Create a GeoJSON FeatureCollection."""
    return {
        'type': 'FeatureCollection',
        'name': name,
        'features': features
    }


def analyze_features(features: list):
    """Print analysis of extracted features."""
    print(f"\n{'='*60}")
    print(f"Analysis of {len(features)} features")
    print('='*60)

    # Count by layer
    layers = {}
    for f in features:
        layer = f['properties'].get('layer', 'unknown')
        layers[layer] = layers.get(layer, 0) + 1

    print("\nBy layer:")
    for layer, count in sorted(layers.items(), key=lambda x: -x[1]):
        print(f"  {layer}: {count}")

    # Count features with dates
    with_dates = [f for f in features if 'start_date' in f['properties']]
    print(f"\nFeatures with establishment date: {len(with_dates)}")

    if with_dates:
        # Distribution by decade
        decades = {}
        for f in with_dates:
            year = f['properties']['start_date']
            decade = (year // 10) * 10
            decades[decade] = decades.get(decade, 0) + 1

        print("\nBy decade (establishment date):")
        for decade in sorted(decades.keys()):
            count = decades[decade]
            bar = '#' * min(count // 5, 40)
            print(f"  {decade}s: {count:4d} {bar}")

    # Cultural heritage
    kulturminne = [f for f in features if f['properties'].get('har_kulturminne')]
    print(f"\nCultural heritage buildings: {len(kulturminne)}")


def main():
    parser = argparse.ArgumentParser(description='Extract building data from Trondheim WMS')
    parser.add_argument('--grid-step', type=float, default=0.003,
                        help='Grid step size in degrees (default: 0.003 = ~300m)')
    parser.add_argument('--delay', type=float, default=0.1,
                        help='Delay between requests in seconds (default: 0.1)')
    parser.add_argument('--layer', choices=['eiendom', 'bygg', 'all'], default='all',
                        help='Layer to extract (default: all)')
    parser.add_argument('--test', action='store_true',
                        help='Test mode - smaller area')
    parser.add_argument('--output', type=str, default=None,
                        help='Output file path')
    args = parser.parse_args()

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Use smaller bbox for testing
    if args.test:
        bbox = {
            'min_lon': 10.38,
            'max_lon': 10.42,
            'min_lat': 63.42,
            'max_lat': 63.44,
        }
        print("TEST MODE - using smaller area")
    else:
        bbox = TRONDHEIM_BBOX

    print(f"Bounding box: {bbox}")
    print(f"Grid step: {args.grid_step} degrees")

    all_features = []

    # Extract layers
    if args.layer in ['eiendom', 'all']:
        features = extract_layer('eiendom', bbox, args.grid_step, delay=args.delay)
        all_features.extend(features)

    if args.layer in ['bygg', 'all']:
        features = extract_layer('bygg', bbox, args.grid_step, delay=args.delay)
        all_features.extend(features)

    # Analyze
    analyze_features(all_features)

    # Save to GeoJSON
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = OUTPUT_DIR / f"trondheim_{args.layer}.geojson"

    geojson = create_geojson(all_features, f"Trondheim WMS Extract - {args.layer}")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {output_path}")
    print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")


if __name__ == '__main__':
    main()
