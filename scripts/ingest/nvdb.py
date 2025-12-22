#!/usr/bin/env python3
"""
NVDB (Nasjonal Vegdatabank) road data ingestor.

Downloads road network data from the Norwegian National Road Database
for the Trondheim municipality area.

API Documentation: https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    requests = None

from .base import BaseIngestor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Ingestor(BaseIngestor):
    """NVDB road data ingestor for Trondheim area."""

    # NVDB API V3 base URL
    BASE_URL = "https://nvdbapiles-v3.atlas.vegvesen.no"

    # Trondheim municipality code
    TRONDHEIM_KOMMUNE = "5001"

    # Trondheim bounding box (WGS84)
    TRONDHEIM_BBOX = {
        'minLat': 63.35,
        'maxLat': 63.50,
        'minLon': 10.20,
        'maxLon': 10.60
    }

    # Road categories to include
    ROAD_CATEGORIES = ['E', 'R', 'F', 'K', 'P', 'S']  # Europa, Riks, Fylkes, Kommune, Privat, Skogs

    # Request settings
    TIMEOUT = 60
    RATE_LIMIT_DELAY = 0.2  # seconds between requests
    MAX_PER_PAGE = 1000

    def __init__(self, **kwargs):
        super().__init__('nvdb', **kwargs)
        if requests is None:
            raise ImportError("requests library required: pip install requests")

        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.vegvesen.nvdb-v3-rev2+json',
            'User-Agent': 'TrondheimHistoricalMap/1.0'
        })

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make a request to the NVDB API."""
        url = f"{self.BASE_URL}{endpoint}"
        if params:
            url = f"{url}?{urlencode(params)}"

        logger.debug(f"Requesting: {url}")

        response = self.session.get(url, timeout=self.TIMEOUT)
        response.raise_for_status()

        time.sleep(self.RATE_LIMIT_DELAY)
        return response.json()

    def _fetch_road_links(self) -> List[Dict]:
        """
        Fetch road network links (veglenker) for Trondheim.

        Returns list of road link features with geometry.
        """
        all_links = []
        start = 0

        logger.info("Fetching road network links from NVDB...")

        while True:
            params = {
                'kommune': self.TRONDHEIM_KOMMUNE,
                'inkluder': 'geometri,alle',
                'srid': '4326',  # WGS84
                'antall': self.MAX_PER_PAGE,
                'start': start
            }

            try:
                data = self._make_request('/vegnett/veglenkesekvenser/segmentert', params)
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error fetching road links: {e}")
                break
            except Exception as e:
                logger.error(f"Error fetching road links: {e}")
                break

            objects = data.get('objekter', [])
            if not objects:
                break

            for obj in objects:
                # Extract geometry and properties
                geom = obj.get('geometri', {}).get('wkt')
                if not geom:
                    continue

                # Convert WKT to GeoJSON (simplified)
                geojson_geom = self._wkt_to_geojson(geom)
                if not geojson_geom:
                    continue

                feature = {
                    'type': 'Feature',
                    'properties': {
                        'nvdb_id': obj.get('veglenkesekvensid'),
                        'segment_id': obj.get('segmentnummer'),
                        'start_posisjon': obj.get('startposisjon'),
                        'slutt_posisjon': obj.get('sluttposisjon'),
                        'vegkategori': obj.get('vegsystemreferanse', {}).get('vegsystem', {}).get('vegkategori'),
                        'vegnummer': obj.get('vegsystemreferanse', {}).get('vegsystem', {}).get('nummer'),
                        'kommune': obj.get('kommune'),
                        'medium': obj.get('medium'),  # T=tunnel, B=bridge, etc.
                        'typeVeg': obj.get('typeVeg'),
                        'adskilte_lop': obj.get('adskilte_løp'),
                        'lengde': obj.get('lengde'),
                        # Date-related fields if present
                        'startdato': obj.get('startdato'),
                        'sluttdato': obj.get('sluttdato'),
                        'metadata': obj.get('metadata', {})
                    },
                    'geometry': geojson_geom
                }
                all_links.append(feature)

            logger.info(f"  Fetched {len(all_links)} road links so far...")

            # Check for more pages
            metadata = data.get('metadata', {})
            returned = metadata.get('returnert', 0)
            if returned < self.MAX_PER_PAGE:
                break

            start += returned

        logger.info(f"Total road links fetched: {len(all_links)}")
        return all_links

    def _fetch_road_objects_with_dates(self) -> Dict[str, Dict]:
        """
        Fetch road objects that have construction/opening dates.

        Object types to query:
        - 532: Veg (road)
        - 581: Åpningsdato for vegstrekning
        - 67: Tunnelløp (tunnel with opening year)
        - 60: Bru (bridge with construction year)

        Returns dict mapping road reference to date information.
        """
        date_info = {}

        # Try to fetch road opening dates (object type 581 if it exists)
        # The actual object types vary - let's try the main road network dates
        object_types_to_try = [
            # (type_id, date_field_name)
            (67, 'Åpningsår'),   # Tunnels
            (60, 'Byggeår'),     # Bridges
        ]

        for obj_type, date_field in object_types_to_try:
            logger.info(f"Fetching object type {obj_type} ({date_field})...")

            try:
                params = {
                    'kommune': self.TRONDHEIM_KOMMUNE,
                    'inkluder': 'egenskaper,lokasjon',
                    'antall': self.MAX_PER_PAGE
                }
                data = self._make_request(f'/vegobjekter/{obj_type}', params)

                for obj in data.get('objekter', []):
                    # Extract date from properties
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
                logger.warning(f"Could not fetch object type {obj_type}: {e}")
                continue

        logger.info(f"Found {len(date_info)} road segments with date info")
        return date_info

    def _wkt_to_geojson(self, wkt: str) -> Optional[Dict]:
        """Convert WKT geometry to GeoJSON."""
        if not wkt:
            return None

        wkt = wkt.strip()

        # Handle LINESTRING
        if wkt.upper().startswith('LINESTRING'):
            coords_str = wkt[wkt.index('(') + 1:wkt.rindex(')')]
            coords = []
            for point in coords_str.split(','):
                parts = point.strip().split()
                if len(parts) >= 2:
                    coords.append([float(parts[0]), float(parts[1])])
            if coords:
                return {'type': 'LineString', 'coordinates': coords}

        # Handle MULTILINESTRING
        elif wkt.upper().startswith('MULTILINESTRING'):
            # Extract content between outer parentheses
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

        # Handle POINT (convert to single-point LineString for roads)
        elif wkt.upper().startswith('POINT'):
            coords_str = wkt[wkt.index('(') + 1:wkt.rindex(')')]
            parts = coords_str.strip().split()
            if len(parts) >= 2:
                coord = [float(parts[0]), float(parts[1])]
                # Return as point (will be filtered out later for roads)
                return {'type': 'Point', 'coordinates': coord}

        return None

    def ingest(self) -> Dict:
        """
        Perform the NVDB road data ingestion.

        Returns:
            Dict with ingestion results
        """
        try:
            # Fetch road network
            road_links = self._fetch_road_links()

            if not road_links:
                return {
                    'success': False,
                    'message': 'No road links retrieved from NVDB'
                }

            # Filter to LineString/MultiLineString only (roads, not points)
            road_features = [
                f for f in road_links
                if f['geometry']['type'] in ('LineString', 'MultiLineString')
            ]

            logger.info(f"Filtered to {len(road_features)} road line features")

            # Try to fetch additional date information
            date_info = self._fetch_road_objects_with_dates()

            # Enrich road features with date info if available
            enriched = 0
            for feature in road_features:
                props = feature['properties']
                ref = f"{props.get('vegkategori', '')}{props.get('vegnummer', '')}"
                if ref in date_info:
                    props['construction_year'] = date_info[ref].get('construction_year')
                    props['date_source_type'] = date_info[ref].get('source_type')
                    enriched += 1

            logger.info(f"Enriched {enriched} features with date information")

            # Create GeoJSON FeatureCollection
            geojson = {
                'type': 'FeatureCollection',
                'features': road_features
            }

            # Save to file
            output_file = self.raw_dir / 'nvdb_roads.json'
            with open(output_file, 'w') as f:
                json.dump(geojson, f)

            # Calculate stats
            categories = {}
            for f in road_features:
                cat = f['properties'].get('vegkategori', 'unknown')
                categories[cat] = categories.get(cat, 0) + 1

            return {
                'success': True,
                'files': ['nvdb_roads.json'],
                'count': len(road_features),
                'message': f"Downloaded {len(road_features)} road segments",
                'notes': f"Categories: {categories}, with dates: {enriched}"
            }

        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': str(e)
            }


# Allow running directly
if __name__ == '__main__':
    ingestor = Ingestor()
    ingestor.run()
