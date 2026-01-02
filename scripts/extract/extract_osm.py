#!/usr/bin/env python3
"""
Extract features from OpenStreetMap via Overpass API.

This extractor fetches buildings, roads, or water features from OSM
and saves them to the raw/ directory for subsequent processing.

Usage:
    from extract.extract_osm import OSMExtractor

    # Extract buildings
    extractor = OSMExtractor(feature_type='buildings')
    result = extractor.run()

    # Extract water
    extractor = OSMExtractor(feature_type='water')
    result = extractor.run()

CLI Usage:
    python scripts/extract/extract_osm.py --feature-type buildings
    python scripts/extract/extract_osm.py --feature-type water --bbox 10.3,63.4,10.5,63.46
"""

import json
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# Import base class and constants
try:
    from extract.base import BaseExtractor
    from constants import GEO, DATA_DIR
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from extract.base import BaseExtractor
    from constants import GEO, DATA_DIR


OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Overpass queries by feature type
OVERPASS_QUERIES = {
    'buildings': """
[out:json][timeout:300];
(
  way["building"]({south},{west},{north},{east});
  relation["building"]({south},{west},{north},{east});
);
out body;
>;
out skel qt;
""",
    'roads': """
[out:json][timeout:300];
(
  way["highway"]["highway"!~"footway|path|steps|cycleway|pedestrian|track"]({south},{west},{north},{east});
);
out body;
>;
out skel qt;
""",
    'water': """
[out:json][timeout:120];
(
  way["natural"="water"]({south},{west},{north},{east});
  way["waterway"="river"]({south},{west},{north},{east});
  relation["natural"="water"]({south},{west},{north},{east});
);
out body;
>;
out skel qt;
"""
}


class OSMExtractor(BaseExtractor):
    """Extract features from OpenStreetMap via Overpass API.

    Attributes:
        bbox: Bounding box (west, south, east, north)
        timeout: Request timeout in seconds
    """

    def __init__(
        self,
        feature_type: str = 'buildings',
        bbox: Tuple[float, float, float, float] = None,
        timeout: int = 300,
        data_dir: Path = None
    ):
        """Initialize OSM extractor.

        Args:
            feature_type: Type of features to extract ('buildings', 'roads', 'water')
            bbox: Bounding box as (west, south, east, north), defaults to GEO.bbox
            timeout: Request timeout in seconds
            data_dir: Base data directory
        """
        super().__init__(
            source_id='osm',
            feature_type=feature_type,
            data_dir=data_dir
        )
        self.bbox = bbox or GEO.bbox
        self.timeout = timeout

    def extract(self) -> Dict[str, Any]:
        """Extract features from OSM.

        Returns:
            Result dictionary with success, count, files, etc.
        """
        # Get query for feature type
        if self.feature_type not in OVERPASS_QUERIES:
            return {
                'success': False,
                'error': f"Unknown feature type: {self.feature_type}. "
                         f"Valid types: {list(OVERPASS_QUERIES.keys())}",
                'count': 0,
                'files': []
            }

        query_template = OVERPASS_QUERIES[self.feature_type]

        # Format bbox
        west, south, east, north = self.bbox
        bbox_params = {
            'south': south,
            'west': west,
            'north': north,
            'east': east
        }
        query = query_template.format(**bbox_params)

        print(f"Extracting OSM {self.feature_type}...")
        print(f"  Bbox: {self.bbox}")

        # Fetch from Overpass
        try:
            osm_data = self._fetch_overpass(query)
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'count': 0,
                'files': []
            }

        # Convert to GeoJSON
        try:
            geojson = self._convert_to_geojson(osm_data)
        except Exception as e:
            return {
                'success': False,
                'error': f"Failed to convert to GeoJSON: {e}",
                'count': 0,
                'files': []
            }

        # Save to raw directory
        output_file = f"{self.feature_type}.geojson"
        output_path = self.raw_dir / output_file

        with open(output_path, 'w') as f:
            json.dump(geojson, f)

        feature_count = len(geojson.get('features', []))
        print(f"  Extracted {feature_count} features")
        print(f"  Saved to {output_path}")

        return {
            'success': True,
            'count': feature_count,
            'files': [output_file],
            'message': f"Extracted {feature_count} {self.feature_type} from OSM"
        }

    def _fetch_overpass(self, query: str) -> Dict:
        """Fetch data from Overpass API.

        Args:
            query: Overpass QL query string

        Returns:
            Parsed JSON response

        Raises:
            Exception: On network or parsing errors
        """
        data = urllib.parse.urlencode({'data': query}).encode('utf-8')

        req = urllib.request.Request(OVERPASS_URL, data=data)
        req.add_header('User-Agent', 'HistoryMap/1.0 (https://github.com/historymap)')

        print(f"  Fetching from Overpass API (timeout={self.timeout}s)...")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raise Exception(f"HTTP error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise Exception(f"URL error: {e.reason}")
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse JSON response: {e}")

    def _convert_to_geojson(self, osm_data: Dict) -> Dict:
        """Convert Overpass response to GeoJSON.

        Args:
            osm_data: Raw Overpass API response

        Returns:
            GeoJSON FeatureCollection
        """
        elements = osm_data.get('elements', [])

        # Build node lookup for way geometry construction
        nodes = {}
        for elem in elements:
            if elem.get('type') == 'node':
                nodes[elem['id']] = (elem['lon'], elem['lat'])

        # Convert ways and relations to features
        features = []

        for elem in elements:
            elem_type = elem.get('type')

            if elem_type == 'way':
                geom = self._build_way_geometry(elem, nodes)
                if geom:
                    feature = self._create_feature(elem, geom)
                    features.append(feature)

            elif elem_type == 'relation':
                # For now, skip relations (complex multipolygon handling)
                # TODO: Add multipolygon support
                pass

        return {
            'type': 'FeatureCollection',
            'metadata': {
                'source': 'osm',
                'feature_type': self.feature_type,
                'feature_count': len(features),
                'bbox': list(self.bbox),
                'extracted_at': None  # Will be set by run()
            },
            'features': features
        }

    def _build_way_geometry(self, way: Dict, nodes: Dict) -> Optional[Dict]:
        """Build GeoJSON geometry from OSM way.

        Args:
            way: OSM way element
            nodes: Node ID to (lon, lat) mapping

        Returns:
            GeoJSON geometry or None if invalid
        """
        node_ids = way.get('nodes', [])
        coords = []

        for node_id in node_ids:
            if node_id in nodes:
                coords.append(list(nodes[node_id]))

        if len(coords) < 2:
            return None

        # Determine geometry type
        is_closed = len(coords) >= 4 and coords[0] == coords[-1]

        if is_closed and self.feature_type in ('buildings', 'water'):
            return {
                'type': 'Polygon',
                'coordinates': [coords]
            }
        else:
            return {
                'type': 'LineString',
                'coordinates': coords
            }

    def _create_feature(self, elem: Dict, geometry: Dict) -> Dict:
        """Create GeoJSON feature from OSM element.

        Args:
            elem: OSM element
            geometry: GeoJSON geometry

        Returns:
            GeoJSON Feature
        """
        tags = elem.get('tags', {})

        # Build properties
        props = {
            '_src': 'osm',
            '_src_id': f"{elem['type']}/{elem['id']}",
        }

        # Copy relevant tags
        if 'name' in tags:
            props['nm'] = tags['name']

        # Feature-type specific properties
        if self.feature_type == 'buildings':
            if 'building:year' in tags:
                try:
                    props['sd'] = int(tags['building:year'])
                    props['ev'] = 'h'  # High evidence from explicit tag
                except ValueError:
                    pass
            if 'building' in tags:
                props['bt'] = tags['building']

        elif self.feature_type == 'roads':
            if 'highway' in tags:
                props['rt'] = tags['highway']  # road type

        elif self.feature_type == 'water':
            props['wtype'] = self._determine_water_type(tags)

        return {
            'type': 'Feature',
            'geometry': geometry,
            'properties': props
        }

    def _determine_water_type(self, tags: Dict) -> str:
        """Determine water type from OSM tags."""
        natural = tags.get('natural', '')
        waterway = tags.get('waterway', '')
        water = tags.get('water', '')

        if waterway == 'river':
            return 'river'
        if waterway == 'canal':
            return 'canal'
        if water == 'lake':
            return 'lake'
        if water == 'river':
            return 'river'
        if water == 'harbour' or water == 'basin':
            return 'harbor'
        if natural == 'coastline':
            return 'fjord'

        return 'fjord'  # Default for coastal water


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Extract features from OpenStreetMap via Overpass API'
    )
    parser.add_argument(
        '--feature-type',
        choices=['buildings', 'roads', 'water'],
        default='buildings',
        help='Type of features to extract'
    )
    parser.add_argument(
        '--bbox',
        type=str,
        default=None,
        help='Bounding box as "west,south,east,north" (defaults to Trondheim)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=300,
        help='Request timeout in seconds'
    )

    args = parser.parse_args()

    # Parse bbox if provided
    bbox = None
    if args.bbox:
        try:
            bbox = tuple(float(x) for x in args.bbox.split(','))
            if len(bbox) != 4:
                raise ValueError("Bbox must have 4 values")
        except ValueError as e:
            print(f"Error parsing bbox: {e}")
            sys.exit(1)

    # Run extraction
    extractor = OSMExtractor(
        feature_type=args.feature_type,
        bbox=bbox,
        timeout=args.timeout
    )

    result = extractor.run()

    if result['success']:
        print(f"\nExtraction successful!")
        print(f"  Features: {result['count']}")
        print(f"  Duration: {result['duration_seconds']:.1f}s")
    else:
        print(f"\nExtraction failed: {result.get('error')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
