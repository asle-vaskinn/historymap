#!/usr/bin/env python3
"""
Byantikvaren (Trondheim City Antiquarian) cultural heritage data ingestion.

Downloads building heritage data from Trondheim kommune's WFS service.
Contains ~6,000 buildings with construction years (datering), demolition years,
and heritage classification (A, B, C categories).

WFS Endpoint: https://kart.trondheim.kommune.no/geoserver/byantikvaren/ows
Layer: byantikvaren:v_new_webvisning_kulturminner
"""

import json
import logging
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
    """Byantikvaren heritage buildings ingestor."""

    # WFS endpoint for Trondheim kommune GeoServer
    WFS_URL = "https://kart.trondheim.kommune.no/geoserver/byantikvaren/ows"

    # Layer containing heritage buildings with construction years
    LAYER_NAME = "byantikvaren:v_new_webvisning_kulturminner"

    # Trondheim bounding box (WGS84) - slightly expanded for edge cases
    TRONDHEIM_BBOX = {
        'minLon': 10.10,
        'minLat': 63.30,
        'maxLon': 10.70,
        'maxLat': 63.55
    }

    TIMEOUT = 300  # 5 minutes for ~30MB download

    def __init__(self, **kwargs):
        super().__init__('trondheim_kommune', **kwargs)
        if requests is None:
            raise ImportError("requests library required: pip install requests")

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'TrondheimHistoricalMap/1.0'
        })

    def _fetch_all_features(self) -> List[Dict]:
        """
        Fetch all features from WFS in a single request.

        Note: Data is in EPSG:25832 (UTM zone 32N). Pagination is not supported
        by this endpoint (no primary key), so we fetch all ~6000 features at once.

        Returns:
            List of all GeoJSON features
        """
        params = {
            'service': 'WFS',
            'version': '2.0.0',
            'request': 'GetFeature',
            'typeName': self.LAYER_NAME,
            'outputFormat': 'application/json',
        }

        url = f"{self.WFS_URL}?{urlencode(params)}"
        logger.info(f"Fetching all features from {self.LAYER_NAME}...")

        try:
            response = self.session.get(url, timeout=self.TIMEOUT)
            response.raise_for_status()
            data = response.json()
            features = data.get('features', [])
            logger.info(f"  Fetched {len(features)} features")
            return features
        except requests.RequestException as e:
            logger.error(f"WFS request failed: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse WFS response: {e}")
            raise

    def ingest(self) -> Dict:
        """
        Perform the ingestion from Byantikvaren WFS.

        Returns:
            Dict with success status, files created, and record count
        """
        try:
            logger.info(f"Starting Byantikvaren ingestion from {self.WFS_URL}")

            # Fetch all features
            features = self._fetch_all_features()

            if not features:
                return {
                    'success': False,
                    'message': 'No features returned from WFS',
                    'count': 0,
                    'files': []
                }

            # Create GeoJSON FeatureCollection
            geojson = {
                'type': 'FeatureCollection',
                'name': 'Byantikvaren Kulturminner',
                'crs': {
                    'type': 'name',
                    'properties': {'name': 'urn:ogc:def:crs:EPSG::4326'}
                },
                'features': features
            }

            # Save to raw directory
            output_file = self.raw_dir / 'kulturminner.geojson'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(geojson, f, ensure_ascii=False, indent=2)

            # Analyze the data
            with_datering = sum(1 for f in features if f.get('properties', {}).get('datering'))
            with_demolition = sum(1 for f in features if f.get('properties', {}).get('bygg_revet_aar'))
            demolished = sum(1 for f in features
                           if f.get('properties', {}).get('antikvarisk_klassifisering') == 'R')

            logger.info(f"Data analysis:")
            logger.info(f"  Total features: {len(features)}")
            logger.info(f"  With exact datering: {with_datering}")
            logger.info(f"  With demolition year: {with_demolition}")
            logger.info(f"  Marked as demolished (R): {demolished}")

            return {
                'success': True,
                'message': f'Ingested {len(features)} heritage buildings from Byantikvaren',
                'count': len(features),
                'files': ['kulturminner.geojson'],
                'notes': f'With datering: {with_datering}, demolished: {demolished}'
            }

        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            return {
                'success': False,
                'message': str(e),
                'count': 0,
                'files': []
            }


def main():
    """Run the ingestor directly."""
    ingestor = Ingestor()
    success = ingestor.run()
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
