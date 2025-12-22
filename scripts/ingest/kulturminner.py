#!/usr/bin/env python3
"""
Kulturminnesøk (Cultural Heritage) road data ingestion.

Downloads historical roads and paths from Riksantikvaren's cultural heritage database.
Uses the ArcGIS REST API from Kulturminnesøk.

API Documentation: https://data.norge.no/en/datasets/3ecd699c-29b0-4bbd-9550-1dfe1a93bd60/kulturminnesok
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
    """Kulturminnesøk heritage roads ingestor."""

    # ArcGIS REST API base URL for Kulturminnesøk
    # Note: This endpoint may need to be updated based on current availability
    BASE_URL = "https://kart.ra.no/arcgis/rest/services/Distribusjon/Kulturminner/MapServer"

    # Alternative GeoNorge WFS endpoint
    GEONORGE_WFS = "https://wfs.geonorge.no/skwms1/wfs.kulturminner"

    # Trondheim bounding box (WGS84)
    TRONDHEIM_BBOX = {
        'minLon': 10.20,
        'minLat': 63.35,
        'maxLon': 10.60,
        'maxLat': 63.50
    }

    # Keywords for transportation heritage
    TRANSPORT_KEYWORDS = [
        'vei', 'veg', 'gate', 'sti', 'ferdselsåre',
        'bro', 'bru', 'kai', 'brygge', 'samferdsel',
        'kongevei', 'postvei', 'pilegrimsled'
    ]

    TIMEOUT = 120
    RATE_LIMIT_DELAY = 0.5

    def __init__(self, **kwargs):
        super().__init__('kulturminner', **kwargs)
        if requests is None:
            raise ImportError("requests library required: pip install requests")

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'TrondheimHistoricalMap/1.0'
        })

    def _query_arcgis_layer(self, layer_id: int, where_clause: str = "1=1") -> List[Dict]:
        """Query an ArcGIS layer and return features."""
        features = []

        bbox = self.TRONDHEIM_BBOX
        geometry = f"{bbox['minLon']},{bbox['minLat']},{bbox['maxLon']},{bbox['maxLat']}"

        params = {
            'where': where_clause,
            'geometry': geometry,
            'geometryType': 'esriGeometryEnvelope',
            'inSR': '4326',
            'outSR': '4326',
            'outFields': '*',
            'returnGeometry': 'true',
            'f': 'json'
        }

        url = f"{self.BASE_URL}/{layer_id}/query"

        try:
            logger.info(f"Querying layer {layer_id}...")
            response = self.session.get(url, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()

            data = response.json()

            if 'error' in data:
                logger.warning(f"API error for layer {layer_id}: {data['error']}")
                return []

            for feature in data.get('features', []):
                # Convert ESRI geometry to GeoJSON
                geom = feature.get('geometry')
                attrs = feature.get('attributes', {})

                if geom:
                    geojson_geom = self._esri_to_geojson(geom)
                    if geojson_geom:
                        features.append({
                            'type': 'Feature',
                            'properties': attrs,
                            'geometry': geojson_geom
                        })

            time.sleep(self.RATE_LIMIT_DELAY)

        except requests.exceptions.HTTPError as e:
            logger.warning(f"HTTP error querying layer {layer_id}: {e}")
        except Exception as e:
            logger.warning(f"Error querying layer {layer_id}: {e}")

        return features

    def _try_geonorge_wfs(self) -> List[Dict]:
        """Try to fetch from GeoNorge WFS as fallback."""
        features = []

        bbox = self.TRONDHEIM_BBOX
        bbox_str = f"{bbox['minLon']},{bbox['minLat']},{bbox['maxLon']},{bbox['maxLat']}"

        # Try WFS GetFeature request
        params = {
            'service': 'WFS',
            'version': '2.0.0',
            'request': 'GetFeature',
            'typeName': 'app:Lokalitet',  # Cultural heritage localities
            'srsName': 'EPSG:4326',
            'bbox': f"{bbox_str},EPSG:4326",
            'outputFormat': 'application/json'
        }

        try:
            logger.info("Trying GeoNorge WFS endpoint...")
            response = self.session.get(self.GEONORGE_WFS, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()

            data = response.json()

            if data.get('type') == 'FeatureCollection':
                features = data.get('features', [])
                logger.info(f"Retrieved {len(features)} features from GeoNorge WFS")

        except Exception as e:
            logger.warning(f"GeoNorge WFS failed: {e}")

        return features

    def _esri_to_geojson(self, esri_geom: Dict) -> Optional[Dict]:
        """Convert ESRI geometry to GeoJSON."""
        if 'paths' in esri_geom:
            # Polyline
            paths = esri_geom['paths']
            if len(paths) == 1:
                return {'type': 'LineString', 'coordinates': paths[0]}
            else:
                return {'type': 'MultiLineString', 'coordinates': paths}

        elif 'rings' in esri_geom:
            # Polygon (we'll convert to centroid or skip for roads)
            return None

        elif 'x' in esri_geom and 'y' in esri_geom:
            # Point
            return {'type': 'Point', 'coordinates': [esri_geom['x'], esri_geom['y']]}

        return None

    def _filter_transport_features(self, features: List[Dict]) -> List[Dict]:
        """Filter features to only include transportation-related heritage."""
        filtered = []

        for feature in features:
            props = feature.get('properties', {})

            # Check various fields for transport-related keywords
            text_fields = [
                props.get('navn', ''),
                props.get('beskrivelse', ''),
                props.get('vernetype', ''),
                props.get('kategori', ''),
                props.get('art', ''),
                props.get('funksjon', ''),
                props.get('kulturminneType', ''),
                props.get('undertype', ''),
            ]

            combined_text = ' '.join(str(f).lower() for f in text_fields if f)

            # Check if any transport keyword matches
            is_transport = any(kw in combined_text for kw in self.TRANSPORT_KEYWORDS)

            if is_transport:
                filtered.append(feature)

        return filtered

    def ingest(self) -> Dict:
        """
        Perform the cultural heritage roads ingestion.

        Returns:
            Dict with ingestion results
        """
        all_features = []

        try:
            # Try ArcGIS layers first
            # Layer IDs vary - common ones are 0 (localities), 1 (single monuments)
            for layer_id in [0, 1, 2, 3]:
                features = self._query_arcgis_layer(layer_id)
                if features:
                    logger.info(f"Layer {layer_id}: {len(features)} features")
                    all_features.extend(features)

            # If no features from ArcGIS, try GeoNorge WFS
            if not all_features:
                logger.info("No features from ArcGIS, trying GeoNorge WFS...")
                all_features = self._try_geonorge_wfs()

            if not all_features:
                logger.warning("No features retrieved from any source")
                # Create empty file to indicate we tried
                geojson = {
                    'type': 'FeatureCollection',
                    'features': [],
                    'metadata': {
                        'note': 'No transport heritage features found in Trondheim area',
                        'bbox': self.TRONDHEIM_BBOX
                    }
                }
                output_file = self.raw_dir / 'kulturminner_roads.json'
                with open(output_file, 'w') as f:
                    json.dump(geojson, f)

                return {
                    'success': True,
                    'files': ['kulturminner_roads.json'],
                    'count': 0,
                    'message': 'No transport heritage features found (API may be unavailable)'
                }

            # Filter to transport-related features
            transport_features = self._filter_transport_features(all_features)

            # Further filter to LineString features (roads)
            road_features = [
                f for f in transport_features
                if f.get('geometry', {}).get('type') in ('LineString', 'MultiLineString')
            ]

            logger.info(f"Total features: {len(all_features)}")
            logger.info(f"Transport-related: {len(transport_features)}")
            logger.info(f"Road geometries: {len(road_features)}")

            # Save all transport features (including points for bridges, etc.)
            geojson = {
                'type': 'FeatureCollection',
                'features': transport_features
            }

            output_file = self.raw_dir / 'kulturminner_roads.json'
            with open(output_file, 'w') as f:
                json.dump(geojson, f)

            return {
                'success': True,
                'files': ['kulturminner_roads.json'],
                'count': len(transport_features),
                'message': f"Downloaded {len(transport_features)} transport heritage features ({len(road_features)} roads)",
                'notes': f"Filtered from {len(all_features)} total features"
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
