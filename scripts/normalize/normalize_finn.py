#!/usr/bin/env python3
"""
Normalizer for Finn.no matched building data.

Takes geocoded/matched Finn data and creates normalized building records
that can be merged with other sources.

The key insight: Finn provides construction years that we match to OSM geometry.
This creates date evidence for existing buildings.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from base import BaseNormalizer


class Normalizer(BaseNormalizer):
    """Normalizer for Finn.no building data."""

    def __init__(self, data_dir: Optional[Path] = None):
        super().__init__('finn', data_dir)
        self.geocoded_path = self.source_dir / 'geocoded' / 'matches.json'

    def normalize(self) -> List[Dict]:
        """
        Normalize Finn matched data.

        Since Finn provides dates for buildings that exist in OSM,
        we create enrichment records that reference the OSM building ID.
        """
        if not self.geocoded_path.exists():
            print(f"  No geocoded data found at {self.geocoded_path}")
            print(f"  Run finn_geocode.py first")
            return []

        with open(self.geocoded_path) as f:
            data = json.load(f)

        matches = data.get('matches', [])
        features = []

        for match in matches:
            finn = match.get('finn', {})
            osm_id = match.get('osm_id')
            year = match.get('year_built')

            if not osm_id or not year:
                continue

            # Create a normalized record
            # We use the OSM ID as reference so the merge can link them
            src_id = f"finn_{finn.get('finn_code', '')}"

            # Evidence is medium - property listings are generally reliable
            # but could have errors
            ev = 'm'

            # Preserve raw data
            raw_props = {
                'finn_code': finn.get('finn_code'),
                'address': finn.get('address'),
                'title': finn.get('title'),
                'price': finn.get('price'),
                'size_m2': finn.get('size_m2'),
                'property_type': finn.get('property_type'),
                'link': finn.get('link'),
                'osm_match': osm_id,
                'scraped_at': finn.get('scraped_at')
            }

            # Remove None values
            raw_props = {k: v for k, v in raw_props.items() if v is not None}

            # Create feature - we'll use the geocoded coordinates as point geometry
            # The merge process will use osm_match to link to the actual polygon
            coords = match.get('geocoded_coords', [0, 0])

            feature = {
                'type': 'Feature',
                'properties': {
                    '_src': 'finn',
                    '_src_id': src_id,
                    '_ingested': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                    'sd': year,  # Start date from Finn
                    'ev': ev,
                    'nm': finn.get('address', '').split(',')[0],  # Street address as name
                    'osm_ref': osm_id,  # Reference to OSM building for merging
                    '_raw': raw_props
                },
                'geometry': {
                    'type': 'Point',
                    'coordinates': coords
                }
            }

            features.append(feature)

        return features


def main():
    """Run the Finn normalizer."""
    import argparse

    parser = argparse.ArgumentParser(description='Normalize Finn building data')
    parser.add_argument('--data-dir', '-d', type=Path,
                        default=Path(__file__).parent.parent.parent / 'data',
                        help='Data directory')
    args = parser.parse_args()

    normalizer = Normalizer(data_dir=args.data_dir)
    success = normalizer.run()
    exit(0 if success else 1)


if __name__ == '__main__':
    main()
