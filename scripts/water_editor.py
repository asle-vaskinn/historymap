#!/usr/bin/env python3
"""
Flask backend for water feature editor.

Endpoints:
    GET  /                       - Serve water_editor.html
    GET  /api/water              - Return all water features as GeoJSON
    POST /api/water              - Save water features (receives GeoJSON)
    GET  /api/maps               - Return list of available historical map images
    GET  /api/water/osm-only     - Preview OSM water features before import
    POST /api/water/import-osm   - Import water features from OSM Overpass API

Run with: python scripts/water_editor.py
"""

import json
import os
import ssl
import urllib.request
from pathlib import Path
from typing import Dict, Any, List

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
WATER_PATH = DATA_DIR / 'sources' / 'manual' / 'water.geojson'
KARTVERKET_DIR = DATA_DIR / 'kartverket'
SCRIPTS_DIR = PROJECT_ROOT / 'scripts'

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all origins

# SSL context for macOS compatibility
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# Trondheim bounding box
TRONDHEIM_BBOX = {
    'south': 63.35,
    'west': 10.20,
    'north': 63.50,
    'east': 10.60
}

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def load_water_features() -> Dict[str, Any]:
    """Load water features from GeoJSON file or create empty FeatureCollection."""
    if not WATER_PATH.exists():
        # Create directory if it doesn't exist
        WATER_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Create empty FeatureCollection
        empty_collection = {
            "type": "FeatureCollection",
            "features": []
        }

        with open(WATER_PATH, 'w') as f:
            json.dump(empty_collection, f, indent=2)

        return empty_collection

    with open(WATER_PATH, 'r') as f:
        return json.load(f)


def save_water_features(feature_collection: Dict[str, Any]) -> None:
    """Save water features to GeoJSON file with pretty-printing."""
    # Ensure directory exists
    WATER_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(WATER_PATH, 'w') as f:
        json.dump(feature_collection, f, indent=2, ensure_ascii=False)


def determine_water_type(tags: Dict[str, str]) -> str:
    """
    Determine water type from OSM tags.

    Args:
        tags: OSM element tags

    Returns:
        Water type: 'lake', 'river', 'harbor', 'canal', or 'fjord'
    """
    # Check for harbor
    if tags.get('harbour'):
        return 'harbor'

    # Check natural=water with subtypes
    if tags.get('natural') == 'water':
        water_type = tags.get('water', '')
        if water_type == 'lake':
            return 'lake'
        elif water_type == 'river':
            return 'river'
        elif water_type == 'reservoir':
            return 'lake'

    # Check waterway types
    waterway = tags.get('waterway', '')
    if waterway == 'river':
        return 'river'
    elif waterway == 'canal':
        return 'canal'
    elif waterway in ['stream', 'brook']:
        return 'river'

    # Check landuse
    if tags.get('landuse') == 'reservoir':
        return 'lake'

    # Default to fjord for coastal water features
    return 'fjord'


def osm_to_geojson_geometry(element: Dict, node_map: Dict) -> Dict[str, Any]:
    """
    Convert OSM element to GeoJSON geometry.

    Args:
        element: OSM element (way or relation)
        node_map: Map of node IDs to coordinates

    Returns:
        GeoJSON geometry dict or None if conversion fails
    """
    elem_type = element.get('type')

    if elem_type == 'way':
        # Simple way - create Polygon
        nodes = element.get('nodes', [])
        if len(nodes) < 4:  # Need at least 4 nodes for a closed polygon
            return None

        coords = []
        for node_id in nodes:
            if node_id in node_map:
                lon, lat = node_map[node_id]
                coords.append([lon, lat])
            else:
                return None  # Missing node

        # Check if closed (first == last)
        if coords[0] != coords[-1]:
            coords.append(coords[0])  # Close the polygon

        return {
            "type": "Polygon",
            "coordinates": [coords]
        }

    elif elem_type == 'relation':
        # Multipolygon relation
        members = element.get('members', [])
        outer_ways = [m for m in members if m.get('role') == 'outer']

        if not outer_ways:
            return None

        polygons = []
        for member in outer_ways:
            if member.get('type') == 'way' and 'nodes' in member:
                nodes = member['nodes']
                if len(nodes) < 4:
                    continue

                coords = []
                for node_id in nodes:
                    if node_id in node_map:
                        lon, lat = node_map[node_id]
                        coords.append([lon, lat])
                    else:
                        break

                if len(coords) >= 4:
                    # Ensure closed
                    if coords[0] != coords[-1]:
                        coords.append(coords[0])
                    polygons.append([coords])

        if not polygons:
            return None

        if len(polygons) == 1:
            return {
                "type": "Polygon",
                "coordinates": polygons[0]
            }
        else:
            return {
                "type": "MultiPolygon",
                "coordinates": polygons
            }

    return None


def query_osm_water() -> List[Dict[str, Any]]:
    """
    Query Overpass API for water features in Trondheim.

    Returns:
        List of GeoJSON features
    """
    bbox = TRONDHEIM_BBOX

    # Overpass query for water features
    query = f"""
    [out:json][timeout:180];
    (
      way["natural"="water"]({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']});
      relation["natural"="water"]({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']});
      way["waterway"~"river|stream|canal"]({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']});
      way["landuse"="reservoir"]({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']});
      way["harbour"]({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']});
      relation["harbour"]({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']});
    );
    out body;
    >;
    out skel qt;
    """

    print(f"  Querying Overpass API for water features...")
    print(f"  Bounding box: {bbox}")

    try:
        # Make request
        req = urllib.request.Request(
            OVERPASS_URL,
            data=query.encode('utf-8'),
            headers={'Content-Type': 'text/plain'}
        )

        with urllib.request.urlopen(req, timeout=300, context=SSL_CONTEXT) as response:
            data = json.loads(response.read().decode('utf-8'))

        elements = data.get('elements', [])

        # Build node map (id -> [lon, lat])
        node_map = {}
        for elem in elements:
            if elem.get('type') == 'node':
                node_id = elem.get('id')
                lat = elem.get('lat')
                lon = elem.get('lon')
                if node_id and lat is not None and lon is not None:
                    node_map[node_id] = [lon, lat]

        # Process ways and relations into features
        features = []
        for elem in elements:
            elem_type = elem.get('type')
            if elem_type not in ['way', 'relation']:
                continue

            tags = elem.get('tags', {})
            if not tags:
                continue

            # Skip if it's a member of a relation (to avoid duplicates)
            # We'll process it through the relation instead

            geometry = osm_to_geojson_geometry(elem, node_map)
            if not geometry:
                continue

            # Determine water type
            wtype = determine_water_type(tags)

            # Create feature
            feature = {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "osm_id": elem.get('id'),
                    "name": tags.get('name', ''),
                    "wtype": wtype,
                    "sd": 1700,
                    "ed": None,
                    "src": "osm",
                    "ev": "h",
                    "_raw": tags
                }
            }

            features.append(feature)

        print(f"  Converted {len(features)} OSM water features to GeoJSON")
        return features

    except urllib.error.URLError as e:
        print(f"  Network error: {e}")
        raise Exception(f"Failed to query Overpass API: {e}")
    except Exception as e:
        print(f"  Error: {e}")
        raise


def scan_historical_maps() -> List[Dict[str, Any]]:
    """
    Scan kartverket directory for available historical map images.

    Returns:
        List of map metadata dictionaries with:
        - id: unique identifier
        - name: display name
        - path: relative path from project root
        - type: file extension
        - bounds: georeferencing bounds if available
    """
    maps = []

    if not KARTVERKET_DIR.exists():
        return maps

    # Image extensions to search for
    image_extensions = {'.png', '.jpg', '.jpeg', '.tif', '.tiff'}

    # Walk through kartverket directory
    for file_path in KARTVERKET_DIR.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in image_extensions:
            # Skip tiles directory and intermediate files
            if 'tiles' in file_path.parts or 'masks' in file_path.parts:
                continue

            relative_path = file_path.relative_to(PROJECT_ROOT)

            # Create a readable ID from the path
            map_id = str(relative_path).replace('/', '_').replace('.', '_')

            # Create a display name from the filename
            name = file_path.stem.replace('_', ' ').title()

            # Check for georeferencing info
            bounds = None
            gcp_file = file_path.parent / f"{file_path.stem}.gcp.json"
            if gcp_file.exists():
                try:
                    with open(gcp_file, 'r') as f:
                        gcp_data = json.load(f)
                        # Extract bounds if available
                        if 'bounds' in gcp_data:
                            bounds = gcp_data['bounds']
                except Exception:
                    pass  # Ignore errors reading GCP file

            maps.append({
                'id': map_id,
                'name': name,
                'path': str(relative_path),
                'type': file_path.suffix.lower(),
                'bounds': bounds
            })

    # Sort by path for consistent ordering
    maps.sort(key=lambda x: x['path'])

    return maps


@app.route('/')
def serve_editor():
    """Serve the water editor HTML interface."""
    html_path = SCRIPTS_DIR / 'water_editor.html'

    if not html_path.exists():
        return jsonify({
            "error": "water_editor.html not found",
            "expected_path": str(html_path)
        }), 404

    return send_file(html_path)


@app.route('/api/water', methods=['GET'])
def get_water_features():
    """
    Get all water features.

    Returns:
        GeoJSON FeatureCollection with all water features
    """
    try:
        features = load_water_features()
        return jsonify(features), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/water', methods=['POST'])
def save_water():
    """
    Save water features.

    Expected JSON body:
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [...]},
                    "properties": {
                        "id": "water_001",
                        "name": "Brattøra Harbor",
                        "wtype": "harbor",
                        "sd": 1700,
                        "ed": 1960,
                        "ev": "h",
                        "notes": "Filled for railway yard",
                        "src": "man"
                    }
                }
            ]
        }

    Returns:
        Confirmation of save
    """
    try:
        data = request.get_json()

        # Validate it's a FeatureCollection
        if not isinstance(data, dict) or data.get('type') != 'FeatureCollection':
            return jsonify({
                "error": "Invalid GeoJSON: must be a FeatureCollection"
            }), 400

        if 'features' not in data or not isinstance(data['features'], list):
            return jsonify({
                "error": "Invalid GeoJSON: missing or invalid 'features' array"
            }), 400

        # Validate each feature
        for i, feature in enumerate(data['features']):
            if not isinstance(feature, dict) or feature.get('type') != 'Feature':
                return jsonify({
                    "error": f"Feature {i} is invalid: must be a Feature"
                }), 400

            if 'geometry' not in feature or 'properties' not in feature:
                return jsonify({
                    "error": f"Feature {i} is missing geometry or properties"
                }), 400

            # Ensure src is set to 'man' for manual features
            if 'properties' in feature and isinstance(feature['properties'], dict):
                feature['properties']['src'] = 'man'

        # Save to file
        save_water_features(data)

        return jsonify({
            "status": "success",
            "message": f"Saved {len(data['features'])} water features",
            "path": str(WATER_PATH.relative_to(PROJECT_ROOT))
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/maps', methods=['GET'])
def get_available_maps():
    """
    Get list of available historical map images.

    Returns:
        JSON array of map metadata objects
    """
    try:
        maps = scan_historical_maps()
        return jsonify({
            "maps": maps,
            "count": len(maps)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({
        "status": "healthy",
        "water_path": str(WATER_PATH),
        "water_exists": WATER_PATH.exists(),
        "kartverket_dir": str(KARTVERKET_DIR),
        "kartverket_exists": KARTVERKET_DIR.exists()
    }), 200


@app.route('/api/water/osm-only', methods=['GET'])
def get_osm_water():
    """
    Get OSM water features (preview before import).

    Returns:
        GeoJSON FeatureCollection with OSM water features
    """
    try:
        features = query_osm_water()
        return jsonify({
            "type": "FeatureCollection",
            "features": features
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/water/import-osm', methods=['POST'])
def import_osm_water():
    """
    Import water features from Overpass API.

    Query parameters:
        merge: 'true' to merge with existing features (default), 'false' to replace all

    Returns:
        GeoJSON FeatureCollection with merged/replaced features
    """
    try:
        # Get merge parameter (default to true)
        merge = request.args.get('merge', 'true').lower() == 'true'

        # Query OSM for water features
        osm_features = query_osm_water()

        if merge:
            # Load existing manual features
            existing = load_water_features()
            manual_features = [
                f for f in existing.get('features', [])
                if f.get('properties', {}).get('src') == 'man'
            ]

            # Combine manual + OSM features
            all_features = manual_features + osm_features

            result = {
                "type": "FeatureCollection",
                "features": all_features
            }

            message = f"Imported {len(osm_features)} OSM features, merged with {len(manual_features)} manual features"
        else:
            # Replace all with OSM features only
            result = {
                "type": "FeatureCollection",
                "features": osm_features
            }

            message = f"Replaced all features with {len(osm_features)} OSM features"

        # Save to file
        save_water_features(result)

        return jsonify({
            "status": "success",
            "message": message,
            "osm_count": len(osm_features),
            "total_count": len(result['features']),
            "path": str(WATER_PATH.relative_to(PROJECT_ROOT))
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print(f"Water Feature Editor Backend")
    print(f"=" * 50)
    print(f"Project root:    {PROJECT_ROOT}")
    print(f"Water features:  {WATER_PATH}")
    print(f"Kartverket dir:  {KARTVERKET_DIR}")
    print(f"=" * 50)
    print(f"\nEndpoints:")
    print(f"  GET  /                       - Serve water_editor.html")
    print(f"  GET  /api/water              - Get water features")
    print(f"  POST /api/water              - Save water features")
    print(f"  GET  /api/maps               - Get available maps")
    print(f"  GET  /api/water/osm-only     - Preview OSM water features")
    print(f"  POST /api/water/import-osm   - Import OSM water features")
    print(f"  GET  /api/health             - Health check")
    print(f"=" * 50)
    print(f"\nOpen: http://localhost:5002/")
    print(f"\nWater features exist: {WATER_PATH.exists()}")

    # Ensure water features file exists
    load_water_features()

    # Scan for available maps
    maps = scan_historical_maps()
    print(f"Found {len(maps)} historical maps")

    print(f"\nStarting server on port 5002...")
    app.run(port=5002, debug=True, host='127.0.0.1')
