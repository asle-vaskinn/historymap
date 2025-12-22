#!/usr/bin/env python3
"""
OSM building data normalization.

Converts raw Overpass API output to normalized GeoJSON schema.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseNormalizer


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


class Normalizer(BaseNormalizer):
    """OSM building data normalizer."""

    def __init__(self, **kwargs):
        super().__init__('osm', **kwargs)

    def normalize(self) -> List[Dict]:
        """Normalize OSM buildings to common schema."""

        raw_file = self.raw_dir / 'osm_buildings.json'
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

        # Process ways (buildings)
        features = []
        for el in elements:
            if el.get('type') != 'way':
                continue

            tags = el.get('tags', {})
            if 'building' not in tags:
                continue

            # Build geometry from node refs
            node_refs = el.get('nodes', [])
            coords = []
            for ref in node_refs:
                if ref in nodes:
                    coords.append(list(nodes[ref]))

            if len(coords) < 4:  # Need at least 3 points + closing
                continue

            # Ensure polygon is closed
            if coords[0] != coords[-1]:
                coords.append(coords[0])

            geometry = {
                'type': 'Polygon',
                'coordinates': [coords]
            }

            # Extract date if available
            start_date = None
            has_explicit_date = False

            for date_key in ['start_date', 'building:start_date', 'construction_date']:
                if date_key in tags:
                    start_date = parse_date(tags[date_key])
                    if start_date:
                        has_explicit_date = True
                        break

            # Determine evidence level
            # High if explicit date, Low otherwise
            ev = 'h' if has_explicit_date else 'l'

            # Create normalized feature
            feature = self.create_normalized_feature(
                src_id=f"way/{el['id']}",
                geometry=geometry,
                sd=start_date,
                ev=ev,
                bt=tags.get('building'),
                nm=tags.get('name'),
                raw_props={
                    'osm_id': el['id'],
                    'tags': tags
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
