#!/usr/bin/env python3
"""
Flask API server for manual building edits.

Endpoints:
    GET  /api/manual - Returns manual edits as GeoJSON FeatureCollection
    POST /api/manual - Saves a new building edit
    POST /api/rebuild - Triggers merge pipeline + PMTiles regeneration

Run with: python scripts/api/server.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from flask import Flask, request, jsonify
from flask_cors import CORS

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
EDITS_PATH = DATA_DIR / 'sources' / 'manual' / 'raw' / 'edits.json'

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all origins


def load_edits() -> Dict[str, Any]:
    """Load edits from JSON file or create empty FeatureCollection."""
    if not EDITS_PATH.exists():
        # Create directory if it doesn't exist
        EDITS_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Create empty FeatureCollection
        empty_collection = {
            "type": "FeatureCollection",
            "features": []
        }

        with open(EDITS_PATH, 'w') as f:
            json.dump(empty_collection, f, indent=2)

        return empty_collection

    with open(EDITS_PATH, 'r') as f:
        return json.load(f)


def save_edits(feature_collection: Dict[str, Any]) -> None:
    """Save edits to JSON file."""
    with open(EDITS_PATH, 'w') as f:
        json.dump(feature_collection, f, indent=2)


@app.route('/api/manual', methods=['GET'])
def get_manual_edits():
    """
    Get all manual edits.

    Returns:
        GeoJSON FeatureCollection with all manual edits
    """
    try:
        edits = load_edits()
        return jsonify(edits), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/manual', methods=['POST'])
def add_manual_edit():
    """
    Add a new manual building edit.

    Expected JSON body:
        {
            "osm_id": "way/12345",
            "geometry": {...},  # GeoJSON geometry
            "sd": 1850,         # Start date
            "ed": null,         # End date (null if still standing)
            "note": "Reason for edit"
        }

    Returns:
        The created feature
    """
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['osm_id', 'geometry', 'sd']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Load existing edits
        edits = load_edits()

        # Create new feature
        feature = {
            "type": "Feature",
            "geometry": data['geometry'],
            "properties": {
                "osm_id": data['osm_id'],
                "sd": data['sd'],
                "ed": data.get('ed'),
                "src": "manual",
                "ev": "h",  # High evidence for manual edits
                "note": data.get('note', ''),
                "edited_at": datetime.utcnow().isoformat() + 'Z'
            }
        }

        # Check if an edit for this OSM ID already exists
        existing_index = None
        for i, f in enumerate(edits['features']):
            if f['properties'].get('osm_id') == data['osm_id']:
                existing_index = i
                break

        if existing_index is not None:
            # Update existing edit
            edits['features'][existing_index] = feature
        else:
            # Add new edit
            edits['features'].append(feature)

        # Save to file
        save_edits(edits)

        return jsonify(feature), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rebuild', methods=['POST'])
def rebuild_pipeline():
    """
    Trigger merge pipeline and PMTiles regeneration.

    Runs the following steps:
        1. Normalize manual source
        2. Merge all sources
        3. Export to GeoJSON and PMTiles

    Returns:
        Status of the rebuild process
    """
    try:
        # Path to pipeline script
        pipeline_script = PROJECT_ROOT / 'scripts' / 'pipeline.py'

        if not pipeline_script.exists():
            return jsonify({"error": "Pipeline script not found"}), 500

        # Run pipeline stages: normalize manual, merge, export
        print("Starting rebuild process...")
        print(f"Pipeline script: {pipeline_script}")

        # Run as subprocess to avoid blocking
        # Using PYTHONPATH to ensure imports work
        env = os.environ.copy()
        env['PYTHONPATH'] = str(PROJECT_ROOT / 'scripts')

        result = subprocess.run(
            [
                sys.executable,
                str(pipeline_script),
                '--stage', 'normalize',
                '--sources', 'manual'
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            print(f"Normalize failed: {result.stderr}")
            return jsonify({
                "error": "Normalization failed",
                "stderr": result.stderr,
                "stdout": result.stdout
            }), 500

        # Run merge
        result = subprocess.run(
            [
                sys.executable,
                str(pipeline_script),
                '--stage', 'merge'
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            print(f"Merge failed: {result.stderr}")
            return jsonify({
                "error": "Merge failed",
                "stderr": result.stderr,
                "stdout": result.stdout
            }), 500

        # Run export (includes PMTiles)
        result = subprocess.run(
            [
                sys.executable,
                str(pipeline_script),
                '--stage', 'export'
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=180
        )

        if result.returncode != 0:
            print(f"Export failed: {result.stderr}")
            return jsonify({
                "error": "Export failed",
                "stderr": result.stderr,
                "stdout": result.stdout
            }), 500

        print("Rebuild completed successfully")

        return jsonify({
            "status": "success",
            "message": "Pipeline rebuilt successfully"
        }), 200

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Pipeline execution timed out"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({
        "status": "healthy",
        "edits_path": str(EDITS_PATH),
        "edits_exist": EDITS_PATH.exists()
    }), 200


if __name__ == '__main__':
    print(f"Starting Flask API server...")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Edits path: {EDITS_PATH}")
    print(f"Edits file exists: {EDITS_PATH.exists()}")

    # Ensure edits file exists
    load_edits()

    app.run(port=5001, debug=True, host='127.0.0.1')
