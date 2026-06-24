#!/usr/bin/env python3
"""
Extract road network data from NVDB (Nasjonal Vegdatabank).

This extractor fetches road segments from the Norwegian National Road Database
and saves them to the raw/ directory for subsequent processing.

API Documentation: https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/

Usage:
    from extract.extract_nvdb import NVDBExtractor

    extractor = NVDBExtractor()
    result = extractor.run()

CLI Usage:
    python scripts/extract/extract_nvdb.py
    python scripts/extract/extract_nvdb.py --kommune 5001
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlencode

# Import base class and constants
try:
    from extract.base import BaseExtractor
    from constants import GEO, DATA_DIR
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from extract.base import BaseExtractor
    from constants import GEO, DATA_DIR

# Optional: Use requests if available, fall back to urllib
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False


class NVDBExtractor(BaseExtractor):
    """Extract road network from Norwegian National Road Database (NVDB).

    NVDB provides comprehensive road network data for Norway including:
    - Road geometry (centerlines)
    - Road classification (E, R, F, K, P, S)
    - Construction/opening dates (for some roads)
    - Tunnels and bridges with dates

    Attributes:
        kommune: Municipality code (default: 5001 for Trondheim)
        bbox: Optional bounding box filter
    """

    # NVDB API V3 base URL
    BASE_URL = "https://nvdbapiles-v3.atlas.vegvesen.no"

    # Request settings
    TIMEOUT = 60
    RATE_LIMIT_DELAY = 0.2  # seconds between requests
    MAX_PER_PAGE = 1000

    # Road categories
    ROAD_CATEGORIES = {
        'E': 'Europaveg',
        'R': 'Riksveg',
        'F': 'Fylkesveg',
        'K': 'Kommunal veg',
        'P': 'Privat veg',
        'S': 'Skogsbilveg'
    }

    def __init__(
        self,
        kommune: str = "5001",  # Trondheim
        bbox: Tuple[float, float, float, float] = None,
        data_dir: Path = None
    ):
        """Initialize NVDB extractor.

        Args:
            kommune: Municipality code (default: 5001 for Trondheim)
            bbox: Optional bounding box as (west, south, east, north)
            data_dir: Base data directory
        """
        super().__init__(
            source_id='nvdb',
            feature_type='roads',
            data_dir=data_dir
        )
        self.kommune = kommune
        self.bbox = bbox or GEO.bbox
        self._session = None

    @property
    def session(self):
        """Lazy-initialize requests session."""
        if self._session is None and HAS_REQUESTS:
            self._session = requests.Session()
            self._session.headers.update({
                'Accept': 'application/vnd.vegvesen.nvdb-v3-rev2+json',
                'User-Agent': 'HistoryMap/1.0 (https://github.com/historymap)'
            })
        return self._session

    def extract(self) -> Dict[str, Any]:
        """Extract road network from NVDB.

        Returns:
            Result dictionary with success, count, files, etc.
        """
        print(f"Extracting NVDB roads for kommune {self.kommune}...")

        try:
            # Fetch road links
            road_links = self._fetch_road_links()

            if not road_links:
                return {
                    'success': False,
                    'error': 'No road links retrieved from NVDB',
                    'count': 0,
                    'files': []
                }

            # Filter to LineString/MultiLineString only
            road_features = [
                f for f in road_links
                if f['geometry']['type'] in ('LineString', 'MultiLineString')
            ]
            print(f"  Filtered to {len(road_features)} road line features")

            # Try to fetch additional date information
            date_info = self._fetch_road_dates()

            # Enrich features with date info
            enriched = 0
            for feature in road_features:
                props = feature['properties']
                ref = f"{props.get('vegkategori', '')}{props.get('vegnummer', '')}"
                if ref in date_info:
                    props['construction_year'] = date_info[ref].get('construction_year')
                    props['date_source_type'] = date_info[ref].get('source_type')
                    enriched += 1

            if enriched:
                print(f"  Enriched {enriched} features with date information")

            # Create GeoJSON
            geojson = {
                'type': 'FeatureCollection',
                'metadata': {
                    'source': 'nvdb',
                    'feature_type': 'roads',
                    'feature_count': len(road_features),
                    'kommune': self.kommune
                },
                'features': road_features
            }

            # Save to raw directory
            output_file = 'roads.geojson'
            output_path = self.raw_dir / output_file

            with open(output_path, 'w') as f:
                json.dump(geojson, f)

            # Calculate category stats
            categories = {}
            for f in road_features:
                cat = f['properties'].get('vegkategori', 'unknown')
                categories[cat] = categories.get(cat, 0) + 1

            print(f"  Saved to {output_path}")
            print(f"  Categories: {categories}")

            return {
                'success': True,
                'count': len(road_features),
                'files': [output_file],
                'message': f"Extracted {len(road_features)} road segments",
                'categories': categories,
                'enriched_with_dates': enriched
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'count': 0,
                'files': []
            }

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make a request to the NVDB API.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Parsed JSON response

        Raises:
            Exception: On network or parsing errors
        """
        url = f"{self.BASE_URL}{endpoint}"
        if params:
            url = f"{url}?{urlencode(params)}"

        if HAS_REQUESTS:
            response = self.session.get(url, timeout=self.TIMEOUT)
            response.raise_for_status()
            result = response.json()
        else:
            req = urllib.request.Request(url)
            req.add_header('Accept', 'application/vnd.vegvesen.nvdb-v3-rev2+json')
            req.add_header('User-Agent', 'HistoryMap/1.0')
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as response:
                result = json.loads(response.read().decode('utf-8'))

        time.sleep(self.RATE_LIMIT_DELAY)
        return result

    def _fetch_road_links(self) -> List[Dict]:
        """Fetch road network links (veglenker) for the municipality.

        Returns:
            List of road features with geometry
        """
        all_links = []
        start = 0

        print(f"  Fetching road network links from NVDB...")

        while True:
            params = {
                'kommune': self.kommune,
                'inkluder': 'geometri,alle',
                'srid': '4326',  # WGS84
                'antall': self.MAX_PER_PAGE,
                'start': start
            }

            try:
                data = self._make_request('/vegnett/veglenkesekvenser/segmentert', params)
            except Exception as e:
                print(f"  Error fetching road links: {e}")
                break

            objects = data.get('objekter', [])
            if not objects:
                break

            for obj in objects:
                geom = obj.get('geometri', {}).get('wkt')
                if not geom:
                    continue

                geojson_geom = self._wkt_to_geojson(geom)
                if not geojson_geom:
                    continue

                feature = {
                    'type': 'Feature',
                    'properties': {
                        '_src': 'nvdb',
                        '_src_id': f"nvdb-{obj.get('veglenkesekvensid')}-{obj.get('segmentnummer', 0)}",
                        'nvdb_id': obj.get('veglenkesekvensid'),
                        'segment_id': obj.get('segmentnummer'),
                        'vegkategori': obj.get('vegsystemreferanse', {}).get('vegsystem', {}).get('vegkategori'),
                        'vegnummer': obj.get('vegsystemreferanse', {}).get('vegsystem', {}).get('nummer'),
                        'kommune': obj.get('kommune'),
                        'medium': obj.get('medium'),  # T=tunnel, B=bridge
                        'typeVeg': obj.get('typeVeg'),
                        'lengde': obj.get('lengde'),
                        'startdato': obj.get('startdato'),
                        'sluttdato': obj.get('sluttdato'),
                    },
                    'geometry': geojson_geom
                }
                all_links.append(feature)

            print(f"    Fetched {len(all_links)} road links...")

            # Check for more pages
            metadata = data.get('metadata', {})
            returned = metadata.get('returnert', 0)
            if returned < self.MAX_PER_PAGE:
                break

            start += returned

        print(f"  Total road links: {len(all_links)}")
        return all_links

    def _fetch_road_dates(self) -> Dict[str, Dict]:
        """Fetch road objects with construction/opening dates.

        Queries tunnels (type 67) and bridges (type 60) for dates.

        Returns:
            Dict mapping road reference to date information
        """
        date_info = {}

        object_types = [
            (67, 'Åpningsår'),   # Tunnels
            (60, 'Byggeår'),     # Bridges
        ]

        for obj_type, date_field in object_types:
            try:
                params = {
                    'kommune': self.kommune,
                    'inkluder': 'egenskaper,lokasjon',
                    'antall': self.MAX_PER_PAGE
                }
                data = self._make_request(f'/vegobjekter/{obj_type}', params)

                for obj in data.get('objekter', []):
                    egenskaper = obj.get('egenskaper', [])
                    for egenskap in egenskaper:
                        if date_field.lower() in egenskap.get('navn', '').lower():
                            ref = obj.get('lokasjon', {}).get('vegsystemreferanse', [{}])[0]
                            ref_str = f"{ref.get('vegsystem', {}).get('vegkategori', '')}{ref.get('vegsystem', {}).get('nummer', '')}"
                            if ref_str:
                                date_info[ref_str] = {
                                    'construction_year': egenskap.get('verdi'),
                                    'source_type': obj_type
                                }
            except Exception as e:
                print(f"  Warning: Could not fetch object type {obj_type}: {e}")
                continue

        return date_info

    def _wkt_to_geojson(self, wkt: str) -> Optional[Dict]:
        """Convert WKT geometry to GeoJSON.

        Args:
            wkt: WKT geometry string

        Returns:
            GeoJSON geometry dict or None
        """
        if not wkt:
            return None

        wkt = wkt.strip()

        if wkt.upper().startswith('LINESTRING'):
            coords_str = wkt[wkt.index('(') + 1:wkt.rindex(')')]
            coords = []
            for point in coords_str.split(','):
                parts = point.strip().split()
                if len(parts) >= 2:
                    coords.append([float(parts[0]), float(parts[1])])
            if coords:
                return {'type': 'LineString', 'coordinates': coords}

        elif wkt.upper().startswith('MULTILINESTRING'):
            content = wkt[wkt.index('((') + 2:wkt.rindex('))')]
            lines = []
            for line_str in content.split('),('):
                line_str = line_str.replace('(', '').replace(')', '')
                coords = []
                for point in line_str.split(','):
                    parts = point.strip().split()
                    if len(parts) >= 2:
                        coords.append([float(parts[0]), float(parts[1])])
                if coords:
                    lines.append(coords)
            if lines:
                return {'type': 'MultiLineString', 'coordinates': lines}

        elif wkt.upper().startswith('POINT'):
            coords_str = wkt[wkt.index('(') + 1:wkt.rindex(')')]
            parts = coords_str.strip().split()
            if len(parts) >= 2:
                return {'type': 'Point', 'coordinates': [float(parts[0]), float(parts[1])]}

        return None


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Extract road network from NVDB (Norwegian National Road Database)'
    )
    parser.add_argument(
        '--kommune',
        type=str,
        default='5001',
        help='Municipality code (default: 5001 for Trondheim)'
    )

    args = parser.parse_args()

    extractor = NVDBExtractor(kommune=args.kommune)
    result = extractor.run()

    if result['success']:
        print(f"\nExtraction successful!")
        print(f"  Roads: {result['count']}")
        print(f"  Duration: {result['duration_seconds']:.1f}s")
        if result.get('categories'):
            print(f"  Categories: {result['categories']}")
    else:
        print(f"\nExtraction failed: {result.get('error')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
