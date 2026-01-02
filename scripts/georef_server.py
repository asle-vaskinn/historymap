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
import re
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import os
import cgi

# Configuration
PORT = 8082
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "georeference"
INPUT_DIR = DATA_DIR / "input"
GCPS_DIR = DATA_DIR / "gcps"
OUTPUT_DIR = DATA_DIR / "output"

# Ensure directories exist
INPUT_DIR.mkdir(parents=True, exist_ok=True)
GCPS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def secure_filename(filename):
    """
    Sanitize filename to prevent directory traversal and other security issues.
    Similar to werkzeug's secure_filename.
    """
    # Remove any directory components
    filename = os.path.basename(filename)
    # Replace problematic characters
    filename = re.sub(r'[^\w\s.-]', '', filename)
    # Remove leading/trailing whitespace and dots
    filename = filename.strip().strip('.')
    # Replace multiple spaces/underscores with single one
    filename = re.sub(r'[\s_]+', '_', filename)
    return filename or 'unnamed_file'


class GeorefHandler(SimpleHTTPRequestHandler):
    """HTTP handler with API endpoints for georeferencing."""

    def __init__(self, *args, **kwargs):
        # Serve from project root
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        """Handle GET requests for API endpoints."""
        parsed = urlparse(self.path)

        if parsed.path == "/api/input-files":
            self.handle_list_input_files()
        else:
            # Fall back to default file serving
            super().do_GET()

    def do_POST(self):
        """Handle POST requests for API endpoints."""
        parsed = urlparse(self.path)

        if parsed.path == "/api/save-gcps":
            self.handle_save_gcps()
        elif parsed.path == "/api/georeference":
            self.handle_georeference()
        elif parsed.path == "/api/upload-image":
            self.handle_upload_image()
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

    def handle_upload_image(self):
        """Handle image upload from multipart form data."""
        try:
            # Parse multipart form data
            content_type = self.headers.get('Content-Type', '')
            if not content_type.startswith('multipart/form-data'):
                self.send_json_response({
                    "success": False,
                    "error": "Expected multipart/form-data"
                }, status=400)
                return

            # Parse the form data
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    'REQUEST_METHOD': 'POST',
                    'CONTENT_TYPE': content_type,
                }
            )

            # Get the uploaded file
            if 'image' not in form:
                self.send_json_response({
                    "success": False,
                    "error": "No 'image' field in form data"
                }, status=400)
                return

            file_item = form['image']
            if not file_item.file:
                self.send_json_response({
                    "success": False,
                    "error": "No file uploaded"
                }, status=400)
                return

            # Get and sanitize filename
            original_filename = file_item.filename
            if not original_filename:
                self.send_json_response({
                    "success": False,
                    "error": "No filename provided"
                }, status=400)
                return

            safe_filename = secure_filename(original_filename)

            # Check for common image extensions
            allowed_extensions = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.gif', '.bmp'}
            file_ext = Path(safe_filename).suffix.lower()
            if file_ext not in allowed_extensions:
                self.send_json_response({
                    "success": False,
                    "error": f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
                }, status=400)
                return

            # Save the file
            output_path = INPUT_DIR / safe_filename

            # Check if file already exists
            if output_path.exists():
                self.send_json_response({
                    "success": False,
                    "error": f"File '{safe_filename}' already exists"
                }, status=409)
                return

            # Write file to disk
            with open(output_path, 'wb') as f:
                f.write(file_item.file.read())

            # Return success response
            self.send_json_response({
                "success": True,
                "filename": safe_filename,
                "path": str(output_path.relative_to(BASE_DIR))
            })

        except Exception as e:
            self.send_json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    def handle_list_input_files(self):
        """List all files in the input directory."""
        try:
            # Get list of files
            files = []
            if INPUT_DIR.exists():
                for filepath in sorted(INPUT_DIR.iterdir()):
                    if filepath.is_file():
                        # Get file stats
                        stat = filepath.stat()
                        files.append({
                            "filename": filepath.name,
                            "path": str(filepath.relative_to(BASE_DIR)),
                            "size": stat.st_size,
                            "modified": stat.st_mtime
                        })

            self.send_json_response({
                "success": True,
                "files": files,
                "count": len(files)
            })

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
