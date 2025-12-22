#!/usr/bin/env python3
"""
Kulturminnesøk heritage road data normalization.

Converts raw cultural heritage data to normalized road GeoJSON schema.
Heritage roads typically have high evidence (official registry) but may
have less precise dates.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from .base_road import BaseRoadNormalizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Normalizer(BaseRoadNormalizer):
    """Kulturminnesøk heritage road data normalizer."""

    def __init__(self, **kwargs):
        super().__init__('kulturminner', **kwargs)

    def _parse_date(self, date_str: Optional[str]) -> Optional[int]:
        """
        Parse date from heritage record.

        Handles formats like:
        - "1850"
        - "ca 1850"
        - "1800-tallet" (19th century)
        - "middelalder" (medieval)
        - "1850-1900"
        """
        if not date_str:
            return None

        date_str = str(date_str).lower().strip()

        # Direct year match
        match = re.search(r'\b(\d{4})\b', date_str)
        if match:
            return int(match.group(1))

        # Century patterns
        century_map = {
            '1700-tallet': 1750,
            '1800-tallet': 1850,
            '1900-tallet': 1950,
            '18. århundre': 1750,
            '19. århundre': 1850,
        }
        for pattern, year in century_map.items():
            if pattern in date_str:
                return year

        # Historical period patterns
        if 'middelalder' in date_str:
            return 1300
        if 'vikingtid' in date_str:
            return 900
        if 'jernald' in date_str:
            return 500
        if 'bronsealder' in date_str:
            return -1000

        return None

    def _extract_date_from_properties(self, props: Dict) -> Optional[int]:
        """Extract date from various property fields."""
        # Try different date fields
        date_fields = [
            'datering', 'dateringsperiode', 'byggeår', 'anleggsår',
            'førstegangsregistrering', 'opprinnelig_funksjon_tid',
            'tidligste_dato', 'eldste_datering'
        ]

        for field in date_fields:
            value = props.get(field)
            if value:
                date = self._parse_date(value)
                if date:
                    return date

        # Try description field
        beskrivelse = props.get('beskrivelse', '')
        if beskrivelse:
            # Look for date patterns in description
            match = re.search(r'\b(1[0-9]{3})\b', str(beskrivelse))
            if match:
                return int(match.group(1))

        return None

    def _extract_road_name(self, props: Dict) -> Optional[str]:
        """Extract road name from properties."""
        name_fields = ['navn', 'name', 'kulturminneNavn', 'lokalitetsNavn']

        for field in name_fields:
            value = props.get(field)
            if value and str(value).strip():
                return str(value).strip()

        return None

    def _map_heritage_type(self, props: Dict) -> str:
        """Map heritage type to road type."""
        type_text = ' '.join([
            str(props.get('vernetype', '')),
            str(props.get('kategori', '')),
            str(props.get('art', '')),
            str(props.get('funksjon', '')),
        ]).lower()

        if 'kongevei' in type_text or 'riksvei' in type_text:
            return 'primary'
        if 'postvei' in type_text:
            return 'secondary'
        if 'pilegrimsled' in type_text or 'ferdselsåre' in type_text:
            return 'path'
        if 'sti' in type_text:
            return 'track'

        return 'historical'

    def normalize(self) -> List[Dict]:
        """Normalize cultural heritage roads to common schema."""
        raw_file = self.raw_dir / 'kulturminner_roads.json'

        if not raw_file.exists():
            logger.error(f"Raw file not found: {raw_file}")
            return []

        with open(raw_file) as f:
            raw_data = json.load(f)

        features = []
        raw_features = raw_data.get('features', [])

        logger.info(f"Normalizing {len(raw_features)} cultural heritage features...")

        for idx, raw_feat in enumerate(raw_features):
            props = raw_feat.get('properties', {})
            geom = raw_feat.get('geometry')

            if not geom:
                continue

            # Only process line geometries for roads
            if geom['type'] not in ('LineString', 'MultiLineString'):
                continue

            # Generate source ID
            heritage_id = props.get('kulturminneId') or props.get('id') or props.get('lokalitetId')
            if heritage_id:
                src_id = f"kult_{heritage_id}"
            else:
                src_id = f"kult_road_{idx}"

            # Extract date
            start_date = self._extract_date_from_properties(props)

            # Extract name
            road_name = self._extract_road_name(props)

            # Map road type
            road_type = self._map_heritage_type(props)

            # Evidence is HIGH for heritage registry (official government data)
            evidence = 'h'

            # Calculate length
            length = self.calculate_length(geom)

            # Create normalized feature
            feature = self.create_normalized_road_feature(
                src_id=src_id,
                geometry=geom,
                sd=start_date,
                ed=None,  # Heritage roads typically still exist or are preserved
                ev=evidence,
                nm=road_name,
                rt=road_type,
                length=length,
                raw_props={
                    'heritage_id': heritage_id,
                    'vernetype': props.get('vernetype'),
                    'kategori': props.get('kategori'),
                    'beskrivelse': props.get('beskrivelse', '')[:500],  # Truncate
                    'kommune': props.get('kommune'),
                    'fredningsstatus': props.get('fredningsstatus'),
                }
            )

            features.append(feature)

        logger.info(f"Normalized {len(features)} heritage road features")

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
