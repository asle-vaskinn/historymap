#!/usr/bin/env python3
"""
OpenStreetMap building data ingestion.

Downloads building footprints from Overpass API for Trondheim area.
"""

import json
import ssl
import urllib.request
from pathlib import Path
from typing import Dict

from .base import BaseIngestor

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


class Ingestor(BaseIngestor):
    """OSM building data ingestor."""

    def __init__(self, **kwargs):
        super().__init__('osm', **kwargs)

    def ingest(self) -> Dict:
        """Download OSM buildings for Trondheim."""

        # Overpass query for buildings in Trondheim
        query = f"""
        [out:json][timeout:180];
        (
          way["building"]({TRONDHEIM_BBOX['south']},{TRONDHEIM_BBOX['west']},{TRONDHEIM_BBOX['north']},{TRONDHEIM_BBOX['east']});
          relation["building"]({TRONDHEIM_BBOX['south']},{TRONDHEIM_BBOX['west']},{TRONDHEIM_BBOX['north']},{TRONDHEIM_BBOX['east']});
        );
        out body;
        >;
        out skel qt;
        """

        print(f"  Querying Overpass API...")
        print(f"  Bounding box: {TRONDHEIM_BBOX}")

        try:
            # Make request
            req = urllib.request.Request(
                OVERPASS_URL,
                data=query.encode('utf-8'),
                headers={'Content-Type': 'text/plain'}
            )

            with urllib.request.urlopen(req, timeout=300, context=SSL_CONTEXT) as response:
                data = json.loads(response.read().decode('utf-8'))

            # Save raw data
            output_file = self.raw_dir / 'osm_buildings.json'
            with open(output_file, 'w') as f:
                json.dump(data, f)

            # Count elements
            elements = data.get('elements', [])
            ways = [e for e in elements if e.get('type') == 'way']

            return {
                'success': True,
                'files': ['osm_buildings.json'],
                'count': len(ways),
                'message': f"Downloaded {len(ways)} building ways"
            }

        except urllib.error.URLError as e:
            return {
                'success': False,
                'message': f"Network error: {e}"
            }
        except Exception as e:
            return {
                'success': False,
                'message': f"Error: {e}"
            }


def main():
    """CLI entry point."""
    ingestor = Ingestor()
    success = ingestor.run()
    exit(0 if success else 1)


if __name__ == '__main__':
    main()
