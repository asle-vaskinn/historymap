#!/usr/bin/env python3
"""
Georeferencing server - handles GCP saving and georeferencing from the web UI.

Usage:
    python scripts/georef_server.py

Then open: http://localhost:8082/georef_editor.html
"""

import json
import subprocess
import sys
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import os

# Configuration
PORT = 8082
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "georeference"
INPUT_DIR = DATA_DIR / "input"
GCPS_DIR = DATA_DIR / "gcps"
OUTPUT_DIR = DATA_DIR / "output"

# Ensure directories exist
GCPS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class GeorefHandler(SimpleHTTPRequestHandler):
    """HTTP handler with API endpoints for georeferencing."""

    def __init__(self, *args, **kwargs):
        # Serve from project root
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_POST(self):
        """Handle POST requests for API endpoints."""
        parsed = urlparse(self.path)

        if parsed.path == "/api/save-gcps":
            self.handle_save_gcps()
        elif parsed.path == "/api/georeference":
            self.handle_georeference()
        else:
            self.send_error(404, "Not found")

    def handle_save_gcps(self):
        """Save GCP file to disk."""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            map_id = data.get('map_id', 'unknown')
            filename = f"{map_id}.gcp.json"
            filepath = GCPS_DIR / filename

            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)

            self.send_json_response({
                "success": True,
                "message": f"Saved to {filepath.relative_to(BASE_DIR)}",
                "path": str(filepath.relative_to(BASE_DIR))
            })
        except Exception as e:
            self.send_json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    def handle_georeference(self):
        """Run georeferencing script."""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            map_id = data.get('map_id')
            input_file = data.get('input_file')

            if not map_id or not input_file:
                self.send_json_response({
                    "success": False,
                    "error": "Missing map_id or input_file"
                }, status=400)
                return

            # Build paths
            input_path = INPUT_DIR / input_file
            gcps_path = GCPS_DIR / f"{map_id}.gcp.json"
            output_path = OUTPUT_DIR / f"{map_id}.tif"

            # Check files exist
            if not input_path.exists():
                self.send_json_response({
                    "success": False,
                    "error": f"Input file not found: {input_path}"
                }, status=400)
                return

            if not gcps_path.exists():
                self.send_json_response({
                    "success": False,
                    "error": f"GCPs file not found: {gcps_path}. Save GCPs first."
                }, status=400)
                return

            # Run georeferencing
            script_path = BASE_DIR / "scripts" / "georeference_map.py"
            cmd = [
                sys.executable,
                str(script_path),
                "--input", str(input_path),
                "--gcps", str(gcps_path),
                "--output", str(output_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(BASE_DIR)
            )

            if result.returncode == 0:
                self.send_json_response({
                    "success": True,
                    "message": f"Georeferenced successfully!",
                    "output": str(output_path.relative_to(BASE_DIR)),
                    "stdout": result.stdout,
                    "stderr": result.stderr
                })
            else:
                self.send_json_response({
                    "success": False,
                    "error": "Georeferencing failed",
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }, status=500)

        except Exception as e:
            self.send_json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    def send_json_response(self, data, status=200):
        """Send JSON response."""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def end_headers(self):
        """Add CORS headers to all responses."""
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()


def main():
    os.chdir(BASE_DIR)

    print(f"Georeferencing Server")
    print(f"=" * 40)
    print(f"Base directory: {BASE_DIR}")
    print(f"Input folder:   {INPUT_DIR.relative_to(BASE_DIR)}")
    print(f"GCPs folder:    {GCPS_DIR.relative_to(BASE_DIR)}")
    print(f"Output folder:  {OUTPUT_DIR.relative_to(BASE_DIR)}")
    print(f"=" * 40)
    print(f"\nOpen: http://localhost:{PORT}/scripts/georef_editor.html\n")

    server = HTTPServer(('', PORT), GeorefHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
