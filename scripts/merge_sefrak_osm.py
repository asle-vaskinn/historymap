#!/usr/bin/env python3
"""
Merge SEFRAK historic building points with OSM building polygons.

This creates a GeoJSON with:
- OSM building polygons
- start_date from SEFRAK (construction decade)
- source: 'sefrak' or 'osm' for provenance

Buildings not matched to SEFRAK are assumed modern (post-1950).
"""

import json
import subprocess
from pathlib import Path

# Use osmium to extract buildings from PBF if available
# Otherwise, we'll need to use the PMTiles directly in the frontend


def load_sefrak(path: Path) -> list:
    """Load SEFRAK GeoJSON."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['features']


def extract_osm_buildings_via_overpass():
    """
    Download OSM buildings for Trondheim via Overpass API.
    Returns GeoJSON features.
    """
    import requests

    # Trondheim bounding box
    bbox = "63.38,10.30,63.46,10.50"  # south,west,north,east

    query = f"""
    [out:json][timeout:120];
    (
      way["building"]({bbox});
      relation["building"]({bbox});
    );
    out body;
    >;
    out skel qt;
    """

    url = "https://overpass-api.de/api/interpreter"
    print("Fetching OSM buildings from Overpass API...")

    response = requests.post(url, data={'data': query}, timeout=180)
    response.raise_for_status()
    data = response.json()

    # Convert Overpass JSON to GeoJSON
    print(f"Received {len(data.get('elements', []))} elements")

    # Build node lookup
    nodes = {}
    ways = []
    relations = []

    for elem in data.get('elements', []):
        if elem['type'] == 'node':
            nodes[elem['id']] = (elem['lon'], elem['lat'])
        elif elem['type'] == 'way':
            ways.append(elem)
        elif elem['type'] == 'relation':
            relations.append(elem)

    # Convert ways to GeoJSON features
    features = []
    for way in ways:
        coords = []
        for node_id in way.get('nodes', []):
            if node_id in nodes:
                coords.append(nodes[node_id])

        if len(coords) >= 4:  # Valid polygon
            # Ensure ring is closed
            if coords[0] != coords[-1]:
                coords.append(coords[0])

            tags = way.get('tags', {})
            props = {
                'osm_id': way['id'],
                'building': tags.get('building', 'yes'),
                'name': tags.get('name', ''),
                'start_date': tags.get('start_date', ''),
                'source': 'osm',
            }

            features.append({
                'type': 'Feature',
                'properties': props,
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [coords]
                }
            })

    print(f"Converted {len(features)} building polygons")
    return features


def match_sefrak_to_osm(sefrak_features: list, osm_features: list, max_distance: float = 50.0):
    """
    Match SEFRAK points to OSM polygons by proximity.

    Args:
        sefrak_features: SEFRAK point features (EPSG:25832)
        osm_features: OSM polygon features (EPSG:4326)
        max_distance: Maximum match distance in meters

    Returns:
        Updated OSM features with SEFRAK dates
    """
    from math import sqrt
    from pyproj import Transformer

    # Create transformer from UTM32N to WGS84
    transformer = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)

    # Convert SEFRAK points to WGS84
    sefrak_points = []
    for f in sefrak_features:
        coords = f['geometry']['coordinates']
        lon, lat = transformer.transform(coords[0], coords[1])
        sefrak_points.append({
            'lon': lon,
            'lat': lat,
            'start_date': f['properties'].get('start_date'),
            'end_date': f['properties'].get('end_date'),
            'period': f['properties'].get('period_description'),
            'name': f['properties'].get('name', ''),
            'status': f['properties'].get('sefrak_status'),
        })

    print(f"Matching {len(sefrak_points)} SEFRAK points to {len(osm_features)} OSM buildings...")

    # Calculate centroid of each OSM building
    matched = 0
    for osm_f in osm_features:
        coords = osm_f['geometry']['coordinates'][0]
        cx = sum(c[0] for c in coords) / len(coords)
        cy = sum(c[1] for c in coords) / len(coords)

        # Find nearest SEFRAK point
        best_dist = float('inf')
        best_sefrak = None

        for sefrak in sefrak_points:
            # Simple distance in degrees (rough)
            dx = (sefrak['lon'] - cx) * 111000 * 0.5  # ~55km per degree at 63N
            dy = (sefrak['lat'] - cy) * 111000
            dist = sqrt(dx*dx + dy*dy)

            if dist < best_dist:
                best_dist = dist
                best_sefrak = sefrak

        # Match if within threshold
        if best_sefrak and best_dist < max_distance:
            if best_sefrak['start_date']:
                osm_f['properties']['start_date'] = best_sefrak['start_date']
                osm_f['properties']['end_date'] = best_sefrak.get('end_date', 2025)
                osm_f['properties']['source'] = 'sefrak'
                osm_f['properties']['sefrak_period'] = best_sefrak['period']
                matched += 1

    print(f"Matched {matched} buildings to SEFRAK data")

    # Buildings not matched assumed modern
    for osm_f in osm_features:
        if 'source' not in osm_f['properties'] or osm_f['properties']['source'] == 'osm':
            if not osm_f['properties'].get('start_date'):
                osm_f['properties']['start_date'] = 1950
                osm_f['properties']['end_date'] = 2025
                osm_f['properties']['source'] = 'osm_assumed'

    return osm_features


def create_temporal_geojson(features: list) -> dict:
    """Create GeoJSON FeatureCollection with temporal attributes."""
    return {
        'type': 'FeatureCollection',
        'name': 'Trondheim Buildings with Temporal Data',
        'features': features
    }


def main():
    data_dir = Path(__file__).parent.parent / 'data'
    sefrak_path = data_dir / 'sefrak' / 'sefrak_trondheim.geojson'
    output_path = data_dir / 'buildings_temporal.geojson'

    # Load SEFRAK
    print(f"Loading SEFRAK from {sefrak_path}")
    sefrak = load_sefrak(sefrak_path)
    print(f"Loaded {len(sefrak)} SEFRAK buildings")

    # Get OSM buildings
    osm_features = extract_osm_buildings_via_overpass()

    if not osm_features:
        print("No OSM buildings retrieved!")
        return

    # Match and merge
    merged = match_sefrak_to_osm(sefrak, osm_features)

    # Create output
    geojson = create_temporal_geojson(merged)

    # Save
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False)

    print(f"\nSaved to: {output_path}")
    print(f"File size: {output_path.stat().st_size / 1024 / 1024:.1f} MB")

    # Statistics
    sources = {}
    for f in merged:
        src = f['properties'].get('source', 'unknown')
        sources[src] = sources.get(src, 0) + 1

    print("\nBuildings by source:")
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"  {src}: {count}")


if __name__ == '__main__':
    main()
