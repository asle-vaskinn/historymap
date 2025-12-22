#!/usr/bin/env python3
"""
OSM road data normalization.

Converts raw Overpass API output to normalized road GeoJSON schema.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_road import BaseRoadNormalizer


def parse_date(value: Any) -> Optional[int]:
    """Parse various date formats to year integer."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        # Match "1880", "~1880", "1880s", "1880-1890", etc.
        match = re.match(r'^~?(\d{4})', value)
        if match:
            return int(match.group(1))
    return None


# OSM highway type to normalized road type mapping
OSM_HIGHWAY_MAP = {
    'motorway': 'motorway',
    'motorway_link': 'motorway',
    'trunk': 'trunk',
    'trunk_link': 'trunk',
    'primary': 'primary',
    'primary_link': 'primary',
    'secondary': 'secondary',
    'secondary_link': 'secondary',
    'tertiary': 'tertiary',
    'tertiary_link': 'tertiary',
    'residential': 'residential',
    'unclassified': 'residential',
    'living_street': 'residential',
    'service': 'service',
    'pedestrian': 'path',
    'footway': 'path',
    'cycleway': 'path',
    'path': 'path',
    'track': 'track',
}


class Normalizer(BaseRoadNormalizer):
    """OSM road data normalizer."""

    def __init__(self, **kwargs):
        super().__init__('osm_roads', **kwargs)

    def normalize(self) -> List[Dict]:
        """Normalize OSM roads to common schema."""

        raw_file = self.raw_dir / 'osm_roads.json'
        if not raw_file.exists():
            raise FileNotFoundError(f"Raw file not found: {raw_file}")

        with open(raw_file) as f:
            data = json.load(f)

        elements = data.get('elements', [])

        # Build node lookup for geometry construction
        nodes = {}
        for el in elements:
            if el.get('type') == 'node':
                nodes[el['id']] = (el['lon'], el['lat'])

        # Process ways (roads)
        features = []
        for el in elements:
            if el.get('type') != 'way':
                continue

            tags = el.get('tags', {})
            if 'highway' not in tags:
                continue

            # Build geometry from node refs (LineString for roads)
            node_refs = el.get('nodes', [])
            coords = []
            for ref in node_refs:
                if ref in nodes:
                    coords.append(list(nodes[ref]))

            if len(coords) < 2:  # Need at least 2 points for a line
                continue

            geometry = {
                'type': 'LineString',
                'coordinates': coords
            }

            # Extract date if available
            # OSM roads may have start_date, construction_date, or nvdb:date
            start_date = None
            has_explicit_date = False

            for date_key in ['start_date', 'construction_date', 'nvdb:date', 'opening_date']:
                if date_key in tags:
                    start_date = parse_date(tags[date_key])
                    if start_date:
                        has_explicit_date = True
                        break

            # Map highway type to normalized road type
            highway = tags.get('highway', '')
            road_type = OSM_HIGHWAY_MAP.get(highway, 'unknown')

            # Determine evidence level
            # High if explicit date from NVDB, Medium if other explicit date, Low otherwise
            if has_explicit_date:
                if 'nvdb:date' in tags:
                    ev = 'h'  # NVDB is authoritative
                else:
                    ev = 'm'  # Other OSM dates are less certain
            else:
                ev = 'l'

            # Road name
            road_name = tags.get('name')
            if not road_name:
                # Try ref (e.g., "E6", "Fv704")
                road_name = tags.get('ref')

            # Create normalized feature
            feature = self.create_normalized_road_feature(
                src_id=f"way/{el['id']}",
                geometry=geometry,
                sd=start_date,
                ev=ev,
                nm=road_name,
                rt=road_type,
                length=self.calculate_length(geometry),
                raw_props={
                    'osm_id': el['id'],
                    'highway': highway,
                    'tags': {k: v for k, v in tags.items() if k in [
                        'name', 'ref', 'highway', 'surface', 'lanes',
                        'maxspeed', 'oneway', 'bridge', 'tunnel'
                    ]}
                }
            )

            features.append(feature)

        return features


def main():
    """CLI entry point."""
    normalizer = Normalizer()
    success = normalizer.run()
    exit(0 if success else 1)


if __name__ == '__main__':
    main()
