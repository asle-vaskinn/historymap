#!/usr/bin/env python3
"""
Fetch water polygons from OSM via Overpass API for Trondheim area.

This creates a baseline of current water features that can be compared
with historical maps to identify filled areas.

Output schema matches water temporal data:
- wtype: river, fjord, lake, canal, harbor
- sd: start date (set to 2024 for current OSM)
- ed: end date (null for existing water)
- ev: evidence level (h for OSM)
- name: feature name if available
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional
import urllib.request
import urllib.parse

# Trondheim bounding box
BBOX = {
    'south': 63.40,
    'west': 10.30,
    'north': 63.46,
    'east': 10.50
}

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Overpass query for water features - simplified
OVERPASS_QUERY = """
[out:json][timeout:120];
(
  // Natural water bodies (ways only, skip relations for speed)
  way["natural"="water"]({south},{west},{north},{east});

  // Major waterways only
  way["waterway"="river"]({south},{west},{north},{east});
);
out body;
>;
out skel qt;
"""


def fetch_overpass(query: str) -> Dict:
    """Fetch data from Overpass API."""
    # Format query with bbox
    formatted_query = query.format(**BBOX)

    data = urllib.parse.urlencode({'data': formatted_query}).encode('utf-8')

    print(f"Fetching from Overpass API...")
    req = urllib.request.Request(OVERPASS_URL, data=data)
    req.add_header('User-Agent', 'HistoryMap/1.0')

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching from Overpass: {e}")
        sys.exit(1)


def determine_water_type(tags: Dict) -> str:
    """Determine water type from OSM tags."""
    natural = tags.get('natural', '')
    waterway = tags.get('waterway', '')
    water = tags.get('water', '')
    landuse = tags.get('landuse', '')

    # Check waterway first
    if waterway == 'river':
        return 'river'
    if waterway == 'stream':
        return 'river'
    if waterway == 'canal':
        return 'canal'

    # Check water type
    if water == 'lake' or water == 'pond':
        return 'lake'
    if water == 'river':
        return 'river'
    if water == 'canal':
        return 'canal'
    if water == 'harbour' or water == 'basin':
        return 'harbor'

    # Check natural
    if natural == 'coastline':
        return 'fjord'
    if natural == 'water':
        # Default water to fjord for coastal areas
        return 'fjord'

    # Check landuse
    if landuse == 'harbour':
        return 'harbor'

    return 'fjord'  # Default


def build_geometry(element: Dict, nodes: Dict) -> Optional[Dict]:
    """Build GeoJSON geometry from OSM element."""
    elem_type = element.get('type')

    if elem_type == 'node':
        return {
            'type': 'Point',
            'coordinates': [element['lon'], element['lat']]
        }

    elif elem_type == 'way':
        node_ids = element.get('nodes', [])
        coords = []
        for nid in node_ids:
            if nid in nodes:
                node = nodes[nid]
                coords.append([node['lon'], node['lat']])

        if len(coords) < 2:
            return None

        # Check if closed polygon
        if coords[0] == coords[-1] and len(coords) >= 4:
            return {
                'type': 'Polygon',
                'coordinates': [coords]
            }
        else:
            return {
                'type': 'LineString',
                'coordinates': coords
            }

    return None


def convert_to_geojson(osm_data: Dict) -> Dict:
    """Convert Overpass response to GeoJSON."""
    elements = osm_data.get('elements', [])

    # Build node lookup
    nodes = {}
    for elem in elements:
        if elem.get('type') == 'node':
            nodes[elem['id']] = elem

    features = []

    for elem in elements:
        if elem.get('type') not in ['way', 'relation']:
            continue

        tags = elem.get('tags', {})

        # Skip if no relevant tags
        if not any(k in tags for k in ['natural', 'waterway', 'water', 'landuse', 'harbour']):
            continue

        geom = build_geometry(elem, nodes)
        if not geom:
            continue

        wtype = determine_water_type(tags)
        name = tags.get('name', '')

        feature = {
            'type': 'Feature',
            'geometry': geom,
            'properties': {
                'osm_id': elem['id'],
                'osm_type': elem['type'],
                'wtype': wtype,
                'name': name,
                'sd': 2024,  # Current as of 2024
                'ed': None,  # Still exists
                'ev': 'h',   # High evidence (OSM)
                'src': 'osm',
                '_raw': tags
            }
        }

        features.append(feature)

    return {
        'type': 'FeatureCollection',
        'features': features
    }


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Fetch water polygons from OSM for Trondheim'
    )
    parser.add_argument('--output', '-o', type=Path,
                        default=Path('data/sources/osm/water.geojson'),
                        help='Output file path')

    args = parser.parse_args()

    # Fetch from Overpass
    print(f"Fetching water features for Trondheim...")
    print(f"  Bbox: {BBOX['south']},{BBOX['west']} to {BBOX['north']},{BBOX['east']}")

    osm_data = fetch_overpass(OVERPASS_QUERY)

    elements = osm_data.get('elements', [])
    print(f"  Received {len(elements)} elements")

    # Convert to GeoJSON
    geojson = convert_to_geojson(osm_data)

    print(f"  Converted to {len(geojson['features'])} features")

    # Count by type
    by_type = {}
    for feat in geojson['features']:
        wtype = feat['properties']['wtype']
        by_type[wtype] = by_type.get(wtype, 0) + 1

    print(f"\n  By type:")
    for wtype, count in sorted(by_type.items()):
        print(f"    {wtype}: {count}")

    # Create output directory
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    with open(args.output, 'w') as f:
        json.dump(geojson, f, indent=2)

    print(f"\nOutput written to: {args.output}")


if __name__ == '__main__':
    main()
