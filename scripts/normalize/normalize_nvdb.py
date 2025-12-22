#!/usr/bin/env python3
"""
NVDB road data normalizer.

Transforms raw NVDB road data to the normalized road schema.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from .base_road import BaseRoadNormalizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# NVDB road category to normalized road type mapping
NVDB_CATEGORY_MAP = {
    'E': 'motorway',      # Europaveg
    'R': 'primary',       # Riksveg
    'F': 'secondary',     # Fylkesveg
    'K': 'tertiary',      # Kommunal veg
    'P': 'residential',   # Privat veg
    'S': 'track',         # Skogsveg
}

# NVDB typeVeg mapping
NVDB_TYPE_MAP = {
    'kanalisertVeg': 'motorway',
    'enkelBilveg': 'secondary',
    'rampe': 'service',
    'rundkjøring': 'service',
    'gangOgSykkelveg': 'path',
    'sykkelveg': 'path',
    'gangveg': 'path',
    'gågate': 'path',
    'fortau': 'path',
}


class Normalizer(BaseRoadNormalizer):
    """NVDB road data normalizer."""

    def __init__(self, **kwargs):
        super().__init__('nvdb', **kwargs)

    def _parse_date(self, date_str: Optional[str]) -> Optional[int]:
        """
        Parse NVDB date string to year.

        Handles formats like:
        - "2015-01-01"
        - "2015"
        - "01.01.2015"
        """
        if not date_str:
            return None

        date_str = str(date_str).strip()

        # Try YYYY-MM-DD
        match = re.match(r'^(\d{4})-\d{2}-\d{2}', date_str)
        if match:
            return int(match.group(1))

        # Try DD.MM.YYYY
        match = re.match(r'^\d{2}\.\d{2}\.(\d{4})', date_str)
        if match:
            return int(match.group(1))

        # Try just YYYY
        match = re.match(r'^(\d{4})$', date_str)
        if match:
            return int(match.group(1))

        # Try numeric value
        try:
            year = int(float(date_str))
            if 1800 <= year <= 2100:
                return year
        except (ValueError, TypeError):
            pass

        return None

    def _map_road_type(self, props: Dict) -> str:
        """Map NVDB properties to normalized road type."""
        # First try typeVeg
        type_veg = props.get('typeVeg', '')
        if type_veg in NVDB_TYPE_MAP:
            return NVDB_TYPE_MAP[type_veg]

        # Then try vegkategori
        vegkategori = props.get('vegkategori', '')
        if vegkategori in NVDB_CATEGORY_MAP:
            return NVDB_CATEGORY_MAP[vegkategori]

        return 'unknown'

    def _generate_road_name(self, props: Dict) -> Optional[str]:
        """Generate road name from NVDB properties."""
        vegkategori = props.get('vegkategori', '')
        vegnummer = props.get('vegnummer')

        if vegkategori and vegnummer:
            # E.g., "E6", "Rv706", "Fv704"
            prefix_map = {
                'E': 'E',
                'R': 'Rv',
                'F': 'Fv',
                'K': 'Kv',
                'P': '',
                'S': ''
            }
            prefix = prefix_map.get(vegkategori, '')
            if prefix:
                return f"{prefix}{vegnummer}"

        return None

    def normalize(self) -> List[Dict]:
        """Normalize NVDB road data to common schema."""
        raw_file = self.raw_dir / 'nvdb_roads.json'

        if not raw_file.exists():
            logger.error(f"Raw file not found: {raw_file}")
            return []

        with open(raw_file) as f:
            raw_data = json.load(f)

        features = []
        raw_features = raw_data.get('features', [])

        logger.info(f"Normalizing {len(raw_features)} NVDB road features...")

        for raw_feat in raw_features:
            props = raw_feat.get('properties', {})
            geom = raw_feat.get('geometry')

            if not geom or geom['type'] not in ('LineString', 'MultiLineString'):
                continue

            # Generate source ID
            nvdb_id = props.get('nvdb_id')
            segment_id = props.get('segment_id', 0)
            src_id = f"nvdb_{nvdb_id}_{segment_id}"

            # Extract/derive dates
            # NVDB may have startdato (when segment was added to database)
            # and construction_year from enriched tunnel/bridge data
            start_date = self._parse_date(props.get('construction_year'))

            # If no explicit construction year, try startdato
            # but be careful - startdato may just be when it was registered
            if not start_date:
                startdato = self._parse_date(props.get('startdato'))
                # Only use if it looks like a plausible construction date
                if startdato and startdato < 2000:
                    start_date = startdato

            # End date (road removed/rerouted)
            end_date = self._parse_date(props.get('sluttdato'))

            # Road type
            road_type = self._map_road_type(props)

            # Road name
            road_name = self._generate_road_name(props)

            # Calculate length
            length = props.get('lengde')
            if length is None:
                length = self.calculate_length(geom)

            # Evidence is HIGH for NVDB (official government database)
            evidence = 'h'

            # Create normalized feature
            feature = self.create_normalized_road_feature(
                src_id=src_id,
                geometry=geom,
                sd=start_date,
                ed=end_date,
                ev=evidence,
                nm=road_name,
                rt=road_type,
                length=length,
                nvdb_id=str(nvdb_id) if nvdb_id else None,
                raw_props={
                    'vegkategori': props.get('vegkategori'),
                    'vegnummer': props.get('vegnummer'),
                    'typeVeg': props.get('typeVeg'),
                    'medium': props.get('medium'),
                    'kommune': props.get('kommune'),
                }
            )

            features.append(feature)

        logger.info(f"Normalized {len(features)} road features")

        # Log statistics
        with_dates = sum(1 for f in features if f['properties'].get('sd'))
        by_type = {}
        for f in features:
            rt = f['properties'].get('rt', 'unknown')
            by_type[rt] = by_type.get(rt, 0) + 1

        logger.info(f"  Roads with dates: {with_dates}")
        logger.info(f"  By type: {by_type}")

        return features


# Allow running directly
if __name__ == '__main__':
    normalizer = Normalizer()
    normalizer.run()
