#!/usr/bin/env python3
"""
SEFRAK cultural heritage registry data normalization.

Converts raw SEFRAK GeoJSON to normalized schema.
SEFRAK contains pre-1900 buildings with construction dates from the
Norwegian cultural heritage registry (Riksantikvaren).
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from .base import BaseNormalizer


def parse_year(value) -> Optional[int]:
    """Parse year from various formats."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def determine_demolition_date(start: Optional[int], end: Optional[int], status: str) -> Optional[int]:
    """
    Determine if building was demolished based on status and dates.

    SEFRAK status codes:
    - "0": Removed/demolished
    - "1": Exists (verified)
    - "2": Assumed to exist (not verified recently)

    Args:
        start: Construction start date
        end: Construction end date (typically 10-year range)
        status: SEFRAK status code

    Returns:
        Demolition year if known, None if building still exists
    """
    # Status 0 means demolished, but we don't know exactly when
    # We can only mark it as demolished without a specific year
    # For now, return None since we don't have the actual demolition date
    # Status 1 and 2 mean the building exists (verified or assumed)
    return None


def map_building_type(bygningstype: Optional[str], function_name: Optional[str]) -> Optional[str]:
    """
    Map SEFRAK building type codes to simplified categories.

    Common SEFRAK codes:
    - 111: Enebolig (detached house)
    - 171: Våningshus (residential building)
    - 182: Uthus (outbuilding)
    - 249: Ruin/rest
    - etc.
    """
    if function_name:
        fn_lower = function_name.lower()

        # Residential
        if any(x in fn_lower for x in ['bolig', 'hus', 'bu', 'våningshus']):
            return 'residential'

        # Agricultural
        if any(x in fn_lower for x in ['fjøs', 'løe', 'stall', 'låve', 'naust']):
            return 'agricultural'

        # Commercial/industrial
        if any(x in fn_lower for x in ['fabrikk', 'verksted', 'butikk', 'handel']):
            return 'commercial'

        # Religious
        if any(x in fn_lower for x in ['kirke', 'kapell', 'bedehus']):
            return 'religious'

        # Ruin/remains
        if any(x in fn_lower for x in ['ruin', 'rest', 'tomt']):
            return 'ruin'

    # Fallback to bygningstype code if available
    if bygningstype:
        code = bygningstype.strip()
        if code in ['111', '112', '113', '171']:
            return 'residential'
        if code in ['151', '152', '153', '161', '162']:
            return 'agricultural'
        if code == '249':
            return 'ruin'

    return None


class Normalizer(BaseNormalizer):
    """SEFRAK cultural heritage registry normalizer."""

    def __init__(self, **kwargs):
        super().__init__('sefrak', **kwargs)

    def reproject_coordinates(self, coords: List[float]) -> List[float]:
        """
        Reproject coordinates from EPSG:25832 (UTM 32N) to EPSG:4326 (WGS84).

        SEFRAK data uses UTM Zone 32N. We need to convert to lat/lon for web maps.
        """
        try:
            from pyproj import Transformer

            # Create transformer from UTM 32N to WGS84
            transformer = Transformer.from_crs(
                "EPSG:25832",  # UTM Zone 32N
                "EPSG:4326",   # WGS84 (lat/lon)
                always_xy=True
            )

            # Transform (x, y) -> (lon, lat)
            lon, lat = transformer.transform(coords[0], coords[1])
            return [lon, lat]

        except ImportError:
            # If pyproj not available, warn and return original
            # (This will produce incorrect coordinates but allows testing)
            print("Warning: pyproj not installed. Coordinates will be incorrect.")
            print("Install with: pip install pyproj")
            return coords

    def normalize(self) -> List[Dict]:
        """Normalize SEFRAK buildings to common schema."""

        # Look for raw data in multiple possible locations
        raw_file = None
        possible_paths = [
            self.raw_dir / 'sefrak_trondheim.geojson',
            self.data_dir / 'sefrak' / 'sefrak_trondheim.geojson',
        ]

        for path in possible_paths:
            if path.exists():
                raw_file = path
                break

        if not raw_file:
            raise FileNotFoundError(
                f"No SEFRAK raw data found. Tried:\n" +
                "\n".join(f"  - {p}" for p in possible_paths)
            )

        print(f"  Reading from: {raw_file}")

        with open(raw_file) as f:
            data = json.load(f)

        features = []
        skipped = {'no_geometry': 0, 'no_date': 0, 'no_id': 0}

        for feat in data.get('features', []):
            props = feat.get('properties', {})
            geom = feat.get('geometry')

            # Skip features without required data
            if not geom or not geom.get('coordinates'):
                skipped['no_geometry'] += 1
                continue

            sefrak_id = props.get('sefrak_id')
            if not sefrak_id:
                skipped['no_id'] += 1
                continue

            # Parse dates
            start = parse_year(props.get('start_date'))
            end = parse_year(props.get('end_date'))

            # SEFRAK has construction period ranges (e.g., 1840-1850)
            # Use the midpoint as the construction year for simplicity
            if start and end and end > start:
                construction_year = (start + end) // 2
            elif start:
                construction_year = start
            else:
                # No date information - skip this feature
                skipped['no_date'] += 1
                continue

            # Determine if demolished
            status = str(props.get('sefrak_status', '1'))
            demolition_year = determine_demolition_date(start, end, status)

            # Reproject geometry from UTM to WGS84
            if geom['type'] == 'Point':
                coords = self.reproject_coordinates(geom['coordinates'])
                normalized_geom = {
                    'type': 'Point',
                    'coordinates': coords
                }
            else:
                # Handle other geometry types if present
                print(f"  Warning: Unsupported geometry type {geom['type']} for {sefrak_id}")
                skipped['no_geometry'] += 1
                continue

            # Map building type
            bt = map_building_type(
                props.get('bygningstype'),
                props.get('original_function_name') or props.get('current_function_name')
            )

            # Extract name
            name = props.get('name')

            # Create normalized feature
            # SEFRAK is HIGH evidence - it's an official cultural heritage registry
            feature = self.create_normalized_feature(
                src_id=sefrak_id,
                geometry=normalized_geom,
                sd=construction_year,
                ed=demolition_year,
                ev='h',  # High evidence - official heritage registry
                bt=bt,
                nm=name,
                raw_props={
                    'bygningsnummer': props.get('bygningsnummer'),
                    'sefrak_id': sefrak_id,
                    'sefrak_status': status,
                    'time_code': props.get('time_code'),
                    'period_description': props.get('period_description'),
                    'original_function_name': props.get('original_function_name'),
                    'current_function_name': props.get('current_function_name'),
                    'bygningstype': props.get('bygningstype'),
                }
            )

            features.append(feature)

        # Report skipped features
        if any(skipped.values()):
            print(f"  Skipped: {sum(skipped.values())} features")
            for reason, count in skipped.items():
                if count > 0:
                    print(f"    - {reason}: {count}")

        return features


def main():
    """CLI entry point."""
    normalizer = Normalizer()
    success = normalizer.run()
    exit(0 if success else 1)


if __name__ == '__main__':
    main()
