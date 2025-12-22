#!/usr/bin/env python3
"""
Normalizer for manually entered water feature data.

Water features track temporal changes to waterbodies including filled harbors,
dammed lakes, and river course changes.

Input: data/sources/manual/water.geojson
Output: data/sources/manual/normalized/water.geojson
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .base import BaseNormalizer


# Valid water types
WATER_TYPES = {'river', 'fjord', 'lake', 'canal', 'harbor'}

# Valid evidence levels
EVIDENCE_LEVELS = {'h', 'm', 'l'}

# Valid year range
MIN_YEAR = 1700
MAX_YEAR = 2030


class WaterNormalizer(BaseNormalizer):
    """Normalizer for manual water feature entries."""

    def __init__(self, data_dir: Optional[Path] = None, input_file: Optional[str] = None,
                 output_file: Optional[str] = None):
        super().__init__('manual', data_dir)
        self.input_file = input_file or 'water.geojson'
        self.output_file = output_file or 'water.geojson'
        self.stats = {
            'total': 0,
            'valid': 0,
            'skipped': 0,
            'errors': {
                'no_geometry': 0,
                'missing_sd': 0,
                'invalid_sd': 0,
                'invalid_ed': 0,
                'missing_wtype': 0,
                'invalid_wtype': 0,
                'invalid_ev': 0,
            }
        }

    def validate_year(self, year: any, allow_none: bool = False) -> Optional[int]:
        """
        Validate a year value.

        Args:
            year: Year value to validate
            allow_none: Whether None is allowed

        Returns:
            Validated year as int, or None if allow_none=True
        """
        if year is None:
            return None if allow_none else False

        if isinstance(year, str):
            try:
                year = int(year.strip())
            except (ValueError, AttributeError):
                return False

        if not isinstance(year, int):
            return False

        if year < MIN_YEAR or year > MAX_YEAR:
            return False

        return year

    def normalize_feature(self, feat: Dict) -> Optional[Dict]:
        """
        Normalize a single water feature.

        Args:
            feat: Raw GeoJSON feature

        Returns:
            Normalized feature or None if invalid
        """
        props = feat.get('properties', {})
        geometry = feat.get('geometry')

        # Validate geometry
        if not geometry:
            self.stats['errors']['no_geometry'] += 1
            print(f"  Warning: Skipping feature without geometry: {props.get('id', 'unknown')}")
            return None

        # Validate sd (required)
        sd_raw = props.get('sd')
        if sd_raw is None:
            self.stats['errors']['missing_sd'] += 1
            print(f"  Warning: Skipping feature without sd: {props.get('id', 'unknown')}")
            return None

        sd = self.validate_year(sd_raw, allow_none=False)
        if sd is False:
            self.stats['errors']['invalid_sd'] += 1
            print(f"  Warning: Skipping feature with invalid sd '{sd_raw}': {props.get('id', 'unknown')}")
            return None

        # Validate ed (optional, but must be valid if present)
        ed_raw = props.get('ed')
        ed = None
        if ed_raw is not None:
            ed = self.validate_year(ed_raw, allow_none=True)
            if ed is False:
                self.stats['errors']['invalid_ed'] += 1
                print(f"  Warning: Skipping feature with invalid ed '{ed_raw}': {props.get('id', 'unknown')}")
                return None
            # Ensure ed > sd if both present
            if ed is not None and ed <= sd:
                self.stats['errors']['invalid_ed'] += 1
                print(f"  Warning: Skipping feature where ed ({ed}) <= sd ({sd}): {props.get('id', 'unknown')}")
                return None

        # Validate wtype (required)
        wtype = props.get('wtype')
        if not wtype:
            self.stats['errors']['missing_wtype'] += 1
            print(f"  Warning: Skipping feature without wtype: {props.get('id', 'unknown')}")
            return None

        wtype = wtype.lower().strip()
        if wtype not in WATER_TYPES:
            self.stats['errors']['invalid_wtype'] += 1
            print(f"  Warning: Skipping feature with invalid wtype '{wtype}': {props.get('id', 'unknown')}")
            print(f"           Valid types: {', '.join(sorted(WATER_TYPES))}")
            return None

        # Validate ev (optional, default 'm')
        ev = props.get('ev', 'm')
        if isinstance(ev, str):
            ev = ev.lower().strip()
        if ev not in EVIDENCE_LEVELS:
            self.stats['errors']['invalid_ev'] += 1
            print(f"  Warning: Invalid evidence level '{ev}', using 'm': {props.get('id', 'unknown')}")
            ev = 'm'

        # Generate ID if missing
        src_id = props.get('id')
        if not src_id:
            src_id = f"water_{self.stats['valid']:04d}"

        # Ensure src='man'
        src = props.get('src', 'man')

        # Extract other fields
        name = props.get('name')
        notes = props.get('notes')

        # Build raw_props with additional fields
        raw_props = {}
        if name:
            raw_props['name'] = name
        if notes:
            raw_props['notes'] = notes

        # Preserve provenance fields if present
        for field in ['added_by', 'added_at', 'verified', 'verified_by', 'verified_at',
                      'modified_by', 'modified_at', 'ev_src', 'ev_url', 'ev_note']:
            if field in props:
                raw_props[field] = props[field]

        # Create normalized feature
        normalized = {
            'type': 'Feature',
            'geometry': geometry,
            'properties': {
                '_src': src,
                '_src_id': src_id,
                'sd': sd,
                'ev': ev,
                'wtype': wtype,
            }
        }

        # Add optional fields
        if ed is not None:
            normalized['properties']['ed'] = ed
        if name:
            normalized['properties']['name'] = name
        if raw_props:
            normalized['properties']['_raw'] = raw_props

        return normalized

    def normalize(self) -> List[Dict]:
        """
        Normalize water features to common schema.

        Returns:
            List of normalized GeoJSON features
        """
        # Determine input path
        raw_path = self.raw_dir / self.input_file
        if not raw_path.exists():
            print(f"  No raw data found at {raw_path}")
            return []

        print(f"  Reading from: {raw_path}")

        # Load raw data
        with open(raw_path) as f:
            raw_data = json.load(f)

        features = []
        raw_features = raw_data.get('features', [])
        self.stats['total'] = len(raw_features)

        # Process each feature
        for feat in raw_features:
            normalized = self.normalize_feature(feat)
            if normalized:
                features.append(normalized)
                self.stats['valid'] += 1
            else:
                self.stats['skipped'] += 1

        return features

    def run(self) -> bool:
        """Run normalization and save output."""
        print(f"Normalizing water features from {self.source_id}...")

        try:
            features = self.normalize()

            # Save output
            output_path = self.normalized_dir / self.output_file
            output = {
                'type': 'FeatureCollection',
                'features': features
            }
            with open(output_path, 'w') as f:
                json.dump(output, f, indent=2)

            # Print statistics
            print(f"\n  Statistics:")
            print(f"    Total features:     {self.stats['total']}")
            print(f"    Valid features:     {self.stats['valid']}")
            print(f"    Skipped features:   {self.stats['skipped']}")

            if self.stats['skipped'] > 0:
                print(f"\n  Errors by type:")
                for error_type, count in sorted(self.stats['errors'].items()):
                    if count > 0:
                        print(f"    {error_type:20s}: {count}")

            print(f"\n  Success: {len(features)} features normalized")
            print(f"  Output: {output_path}")

            # Update manifest (if it exists)
            try:
                manifest = self.load_manifest()
                manifest['water_normalized_count'] = len(features)
                self.save_manifest(manifest)
            except Exception as e:
                print(f"  Warning: Could not update manifest: {e}")

            return True

        except FileNotFoundError as e:
            print(f"  Error: {e}")
            return False
        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Normalize manual water feature entries',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: read from data/sources/manual/water.geojson
  python scripts/normalize/normalize_water.py

  # Custom input/output
  python scripts/normalize/normalize_water.py \\
    --input custom_water.geojson \\
    --output custom_output.geojson

  # Custom data directory
  python scripts/normalize/normalize_water.py --data-dir /path/to/data
        """
    )
    parser.add_argument('--data-dir', '-d', type=Path,
                        default=Path(__file__).parent.parent.parent / 'data',
                        help='Data directory (default: ../../data)')
    parser.add_argument('--input', '-i', type=str,
                        default='water.geojson',
                        help='Input filename in data/sources/manual/ (default: water.geojson)')
    parser.add_argument('--output', '-o', type=str,
                        default='water.geojson',
                        help='Output filename in data/sources/manual/normalized/ (default: water.geojson)')
    args = parser.parse_args()

    normalizer = WaterNormalizer(
        data_dir=args.data_dir,
        input_file=args.input,
        output_file=args.output
    )
    success = normalizer.run()
    exit(0 if success else 1)


if __name__ == '__main__':
    main()
