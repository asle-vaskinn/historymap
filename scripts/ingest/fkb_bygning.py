#!/usr/bin/env python3
"""
FKB-Bygning (Kartverket) building data ingestion.

Downloads official building footprints from Kartverket.
This is the authoritative source for current building geometry in Norway.

NOTE: FKB-Bygning requires Norge digitalt partnership for download access.
See: https://www.kartverket.no/geodataarbeid/sfkb/distribusjon

Alternative access methods:
1. Manual download from Geonorge (requires GeoID login)
2. Use N50 Bygning (less detailed but public)
3. Contact Kartverket for API access

Data source: https://kartkatalog.geonorge.no/metadata/fkb-bygning/8b4304ea-4fb0-479c-a24d-fa225e2c6e97
"""

import json
import urllib.request
import urllib.parse
import ssl
from pathlib import Path
from typing import Dict, List, Optional
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from ingest.base import BaseIngestor


# Trondheim bounding box (EPSG:4326)
TRONDHEIM_BBOX = {
    'south': 63.35,
    'west': 10.20,
    'north': 63.50,
    'east': 10.60
}

# WFS endpoint for FKB-Bygning
WFS_URL = "https://wfs.geonorge.no/skwms1/wfs.fkb-bygning"

# Feature type for buildings
FEATURE_TYPE = "app:Bygning"


class Ingestor(BaseIngestor):
    """FKB-Bygning official building data ingestor."""

    def __init__(self, **kwargs):
        super().__init__('fkb_bygning', **kwargs)

    def build_wfs_url(self, start_index: int = 0, count: int = 1000) -> str:
        """Build WFS GetFeature request URL."""
        # BBOX in WFS format: minx,miny,maxx,maxy
        bbox = f"{TRONDHEIM_BBOX['west']},{TRONDHEIM_BBOX['south']},{TRONDHEIM_BBOX['east']},{TRONDHEIM_BBOX['north']}"

        params = {
            'service': 'WFS',
            'version': '2.0.0',
            'request': 'GetFeature',
            'typeName': FEATURE_TYPE,
            'outputFormat': 'application/json',
            'srsName': 'EPSG:4326',
            'bbox': f"{bbox},EPSG:4326",
            'startIndex': str(start_index),
            'count': str(count)
        }

        return f"{WFS_URL}?{urllib.parse.urlencode(params)}"

    def fetch_page(self, start_index: int, count: int) -> Optional[Dict]:
        """Fetch a single page of features."""
        url = self.build_wfs_url(start_index, count)

        # Create SSL context that doesn't verify certificates
        # (Kartverket's SSL chain sometimes has issues on macOS)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        try:
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'HistoryMap/1.0 (https://github.com/historymap)',
                    'Accept': 'application/json'
                }
            )

            with urllib.request.urlopen(req, timeout=120, context=ssl_context) as response:
                return json.loads(response.read().decode('utf-8'))

        except urllib.error.URLError as e:
            print(f"  Error fetching page at index {start_index}: {e}")
            return None

    def check_manual_file(self) -> Optional[Path]:
        """Check if FKB data was manually placed."""
        manual_paths = [
            self.raw_dir / 'fkb_bygning.geojson',
            self.raw_dir / 'Basisdata_5001_Trondheim_25832_FKB-Bygning_FGDB.gdb',
            self.raw_dir / 'FKB-Bygning.gml',
        ]
        for path in manual_paths:
            if path.exists():
                return path
        return None

    def ingest(self) -> Dict:
        """Download FKB-Bygning data for Trondheim."""

        # Check for manually placed file first
        manual_file = self.check_manual_file()
        if manual_file:
            print(f"  Found manually placed file: {manual_file}")
            if manual_file.suffix == '.geojson':
                # Already in correct format
                return {
                    'success': True,
                    'files': [manual_file.name],
                    'count': -1,  # Unknown until normalized
                    'message': f"Using manually placed file: {manual_file.name}"
                }
            else:
                print(f"  Note: File format {manual_file.suffix} may need conversion")
                return {
                    'success': True,
                    'files': [manual_file.name],
                    'count': -1,
                    'message': f"Using manually placed file (may need conversion): {manual_file.name}"
                }

        print(f"  Attempting to fetch FKB-Bygning from Kartverket WFS...")
        print(f"  Bounding box: {TRONDHEIM_BBOX}")
        print(f"  WFS endpoint: {WFS_URL}")
        print(f"")
        print(f"  NOTE: FKB-Bygning typically requires Norge digitalt partnership.")
        print(f"  If this fails, download manually from Geonorge with GeoID login.")
        print(f"")

        all_features = []
        page_size = 1000
        start_index = 0
        total_fetched = 0

        while True:
            print(f"  Fetching features {start_index} - {start_index + page_size}...")

            data = self.fetch_page(start_index, page_size)

            if data is None:
                if total_fetched == 0:
                    return {
                        'success': False,
                        'message': "Failed to fetch any data from WFS"
                    }
                break

            features = data.get('features', [])
            if not features:
                break

            all_features.extend(features)
            total_fetched += len(features)
            print(f"    Got {len(features)} features (total: {total_fetched})")

            # Check if we got a full page (might be more)
            if len(features) < page_size:
                break

            start_index += page_size

            # Safety limit
            if total_fetched > 50000:
                print("  Warning: Hit safety limit of 50000 features")
                break

        if not all_features:
            return {
                'success': False,
                'message': "No features found in bounding box"
            }

        # Create GeoJSON FeatureCollection
        output = {
            'type': 'FeatureCollection',
            'name': 'FKB-Bygning Trondheim',
            'crs': {
                'type': 'name',
                'properties': {'name': 'urn:ogc:def:crs:EPSG::4326'}
            },
            'features': all_features
        }

        # Save raw data
        output_file = self.raw_dir / 'fkb_bygning.geojson'
        with open(output_file, 'w') as f:
            json.dump(output, f)

        return {
            'success': True,
            'files': ['fkb_bygning.geojson'],
            'count': len(all_features),
            'message': f"Downloaded {len(all_features)} buildings from FKB-Bygning"
        }


def main():
    """CLI entry point."""
    ingestor = Ingestor()
    success = ingestor.run()
    exit(0 if success else 1)


if __name__ == '__main__':
    main()
