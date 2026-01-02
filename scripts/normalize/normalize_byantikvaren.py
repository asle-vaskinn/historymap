#!/usr/bin/env python3
"""
Byantikvaren (Trondheim City Antiquarian) data normalization.

Converts raw Byantikvaren GeoJSON to normalized building schema.
Source contains ~6,000 heritage buildings with:
- datering: exact construction year (e.g., "1924")
- bygg_revet_aar: demolition year
- tidsperiode: time period range (e.g., "1900-1924")
- antikvarisk_klassifisering: heritage class (A, B, C, R=demolished)
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from pyproj import Transformer
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False
    Transformer = None

from .base import BaseNormalizer


def transform_coordinates(geom: Dict, transformer) -> Dict:
    """
    Transform geometry coordinates from EPSG:25832 to EPSG:4326.

    Args:
        geom: GeoJSON geometry dict
        transformer: pyproj Transformer instance

    Returns:
        Geometry with transformed coordinates
    """
    geom_type = geom.get('type')
    coords = geom.get('coordinates')

    if not coords:
        return geom

    def transform_point(point):
        """Transform a single [x, y] point."""
        lon, lat = transformer.transform(point[0], point[1])
        return [lon, lat]

    def transform_ring(ring):
        """Transform a ring (list of points)."""
        return [transform_point(p) for p in ring]

    if geom_type == 'Point':
        new_coords = transform_point(coords)
    elif geom_type == 'LineString':
        new_coords = transform_ring(coords)
    elif geom_type == 'Polygon':
        new_coords = [transform_ring(ring) for ring in coords]
    elif geom_type == 'MultiPolygon':
        new_coords = [[transform_ring(ring) for ring in polygon] for polygon in coords]
    elif geom_type == 'MultiLineString':
        new_coords = [transform_ring(line) for line in coords]
    elif geom_type == 'MultiPoint':
        new_coords = transform_ring(coords)
    else:
        return geom  # Unknown type, return unchanged

    return {'type': geom_type, 'coordinates': new_coords}


def parse_datering(value: Optional[str]) -> Optional[int]:
    """
    Parse the 'datering' field which contains construction year.

    Args:
        value: String like "1924", "ca. 1850", "1920-tallet", etc.

    Returns:
        Integer year or None if unparseable
    """
    if not value:
        return None

    value = str(value).strip()

    # Direct year (most common): "1924"
    if re.match(r'^\d{4}$', value):
        year = int(value)
        if 1600 <= year <= 2025:
            return year

    # "ca. 1850" or "ca 1850"
    match = re.search(r'ca\.?\s*(\d{4})', value, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # "1920-tallet" (1920s) -> midpoint 1925
    match = re.search(r'(\d{4})-tallet', value)
    if match:
        decade = int(match.group(1))
        return decade + 5

    # Range like "1850-1860" -> use start year
    match = re.search(r'(\d{4})\s*[-–]\s*(\d{4})', value)
    if match:
        return int(match.group(1))

    return None


def parse_tidsperiode(value: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """
    Parse the 'tidsperiode' field which contains time period ranges.

    Args:
        value: String like "1900-1924", "1800-1899. 1800-tallet uspesifisert"

    Returns:
        Tuple of (start_year, end_year) or (None, None)
    """
    if not value:
        return None, None

    value = str(value).strip()

    # "1900-1924" or "1950-1974"
    match = re.search(r'(\d{4})\s*[-–]\s*(\d{4})', value)
    if match:
        return int(match.group(1)), int(match.group(2))

    # "1800-1899. 1800-tallet uspesifisert" -> extract range
    match = re.search(r'(\d{4})-(\d{4})\.', value)
    if match:
        return int(match.group(1)), int(match.group(2))

    return None, None


def map_heritage_class(klassifisering: Optional[str]) -> Tuple[str, bool]:
    """
    Map Byantikvaren heritage classification to evidence level.

    Classifications:
    - A: Highest heritage value (fredningsverdig)
    - B: High heritage value (bevaringsverdig)
    - C: Heritage value (verneverdig)
    - R - Revet: Demolished

    Returns:
        Tuple of (evidence_level, is_demolished)
    """
    if not klassifisering:
        return 'h', False  # Default to high evidence from official source

    klass = str(klassifisering).strip().upper()

    # Check for demolished - value is "R - Revet"
    if klass.startswith('R'):
        return 'h', True  # Demolished
    elif klass.startswith('A') or klass.startswith('B'):
        return 'h', False  # High evidence
    elif klass.startswith('C'):
        return 'h', False  # Still high - official classification
    else:
        return 'm', False  # Unknown classification


class Normalizer(BaseNormalizer):
    """Byantikvaren data normalizer."""

    def __init__(self, **kwargs):
        super().__init__('trondheim_kommune', **kwargs)
        self.raw_file = self.raw_dir / 'kulturminner.geojson'

    def normalize(self) -> List[Dict]:
        """
        Normalize Byantikvaren features to standard schema.

        Transforms coordinates from EPSG:25832 (UTM zone 32N) to EPSG:4326 (WGS84).

        Returns:
            List of normalized GeoJSON features
        """
        if not self.raw_file.exists():
            raise FileNotFoundError(f"Raw file not found: {self.raw_file}")

        # Create coordinate transformer (UTM zone 32N -> WGS84)
        if HAS_PYPROJ:
            transformer = Transformer.from_crs(
                "EPSG:25832", "EPSG:4326", always_xy=True
            )
        else:
            print("Warning: pyproj not installed, coordinates will not be transformed")
            transformer = None

        with open(self.raw_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        features = data.get('features', [])
        normalized = []

        stats = {
            'total': 0,
            'with_datering': 0,
            'with_tidsperiode_only': 0,
            'with_demolition': 0,
            'demolished': 0,
            'no_geometry': 0,
            'no_date': 0,
        }

        for feature in features:
            stats['total'] += 1
            props = feature.get('properties', {})
            geom = feature.get('geometry')

            # Skip features without geometry
            if not geom:
                stats['no_geometry'] += 1
                continue

            # Parse construction year
            datering = props.get('datering')
            tidsperiode = props.get('tidsperiode')

            start_date = parse_datering(datering)

            if start_date:
                stats['with_datering'] += 1
                date_type = 'x'  # Exact
            else:
                # Try tidsperiode as fallback
                period_start, period_end = parse_tidsperiode(tidsperiode)
                if period_start and period_end:
                    # Use midpoint of period
                    start_date = (period_start + period_end) // 2
                    date_type = 's'  # Estimated
                    stats['with_tidsperiode_only'] += 1
                else:
                    stats['no_date'] += 1
                    date_type = None

            # Parse demolition year
            bygg_revet = props.get('bygg_revet_aar')
            end_date = None
            if bygg_revet:
                try:
                    end_date = int(float(bygg_revet))
                    if 1600 <= end_date <= 2025:
                        stats['with_demolition'] += 1
                    else:
                        end_date = None
                except (ValueError, TypeError):
                    pass

            # Get heritage classification
            klassifisering = props.get('antikvarisk_klassifisering')
            evidence, is_demolished = map_heritage_class(klassifisering)

            if is_demolished:
                stats['demolished'] += 1

            # Build unique ID
            intern_id = props.get('intern_id')
            bygningsnummer = props.get('bygningsnummer')

            if intern_id:
                src_id = f"ba_{intern_id}"
            elif bygningsnummer:
                src_id = f"ba_bygg_{bygningsnummer}"
            else:
                src_id = f"ba_{stats['total']}"

            # Build normalized feature
            normalized_props = {
                '_src': 'tk',  # trondheim_kommune source code
                '_src_id': src_id,
                '_ingested': datetime.utcnow().strftime('%Y-%m-%d'),
                'ev': evidence,
            }

            # Add construction date if available
            if start_date:
                normalized_props['sd'] = start_date
                normalized_props['sd_t'] = date_type
                normalized_props['sd_s'] = 'tk'

            # Add demolition date if available
            if end_date:
                normalized_props['ed'] = end_date
                normalized_props['ed_t'] = 'x'
                normalized_props['ed_s'] = 'tk'
            elif is_demolished and not end_date:
                # Mark as demolished but date unknown
                normalized_props['demolished'] = True

            # Add name if available
            navn = props.get('navn') or props.get('enkeltminne_navn')
            if navn:
                normalized_props['nm'] = navn

            # Add heritage classification
            if klassifisering:
                normalized_props['heritage_class'] = klassifisering

            # Add building number for OSM matching
            if bygningsnummer:
                normalized_props['bygningsnummer'] = bygningsnummer

            # Preserve raw properties
            normalized_props['_raw'] = {
                'intern_id': intern_id,
                'lokalitetsid': props.get('lokalitetsid'),
                'antikvarisk_klassifisering': klassifisering,
                'datering': datering,
                'tidsperiode': tidsperiode,
                'bygg_revet_aar': bygg_revet,
                'arkitekt': props.get('arkitekt'),
                'hovedmateriale': props.get('hovedmateriale'),
                'type': props.get('type'),
                'lokalitet_art': props.get('lokalitet_art'),
                'kpa_info': props.get('kpa_info'),
            }

            # Transform geometry from UTM to WGS84
            if transformer:
                transformed_geom = transform_coordinates(geom, transformer)
            else:
                transformed_geom = geom

            normalized_feature = {
                'type': 'Feature',
                'properties': normalized_props,
                'geometry': transformed_geom,
            }

            normalized.append(normalized_feature)

        # Log statistics
        print(f"\nNormalization statistics:")
        print(f"  Total features: {stats['total']}")
        print(f"  With exact datering: {stats['with_datering']}")
        print(f"  With tidsperiode only: {stats['with_tidsperiode_only']}")
        print(f"  With demolition year: {stats['with_demolition']}")
        print(f"  Marked demolished: {stats['demolished']}")
        print(f"  Skipped (no geometry): {stats['no_geometry']}")
        print(f"  No date available: {stats['no_date']}")
        print(f"  Normalized: {len(normalized)}")

        return normalized


def main():
    """Run the normalizer directly."""
    normalizer = Normalizer()
    success = normalizer.run()
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
