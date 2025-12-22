#!/usr/bin/env python3
"""
Normalizer for manually entered building data.

Manual entries have full provenance tracking:
- added_by, added_at: Who added and when
- verified, verified_by, verified_at: Verification status
- modified_by, modified_at: Modification tracking

These are preserved in _raw for audit trails.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from base import BaseNormalizer


class Normalizer(BaseNormalizer):
    """Normalizer for manual building entries."""

    def __init__(self, data_dir: Optional[Path] = None):
        super().__init__('manual', data_dir)

    def normalize(self) -> List[Dict]:
        """
        Normalize manual building entries.

        Returns:
            List of normalized GeoJSON features
        """
        raw_path = self.raw_dir / 'buildings.geojson'

        if not raw_path.exists():
            print(f"  No raw data found at {raw_path}")
            return []

        with open(raw_path) as f:
            raw_data = json.load(f)

        features = []
        for feat in raw_data.get('features', []):
            props = feat.get('properties', {})
            geometry = feat.get('geometry')

            if not geometry:
                print(f"  Skipping feature without geometry: {props.get('id')}")
                continue

            # Extract normalized fields
            src_id = props.get('id', f"man_{len(features):04d}")
            sd = props.get('sd')
            ed = props.get('ed')
            ev = props.get('ev', 'm')  # Default to medium evidence
            nm = props.get('nm')

            # Map use to building type (bt)
            use_to_bt = {
                'residential': 'residential',
                'commercial': 'commercial',
                'industrial': 'industrial',
                'public': 'public',
                'religious': 'religious',
                'military': 'military',
                'agricultural': 'agricultural',
                'transport': 'transport',
                'utility': 'utility',
            }
            bt = use_to_bt.get(props.get('use'))

            # Preserve full provenance in _raw
            raw_props = {
                'addr': props.get('addr'),
                'use': props.get('use'),
                'notes': props.get('notes'),
                'tags': props.get('tags'),
                # Evidence details
                'ev_src': props.get('ev_src'),
                'ev_url': props.get('ev_url'),
                'ev_note': props.get('ev_note'),
                # Provenance
                'added_by': props.get('added_by'),
                'added_at': props.get('added_at'),
                'verified': props.get('verified'),
                'verified_by': props.get('verified_by'),
                'verified_at': props.get('verified_at'),
                'modified_by': props.get('modified_by'),
                'modified_at': props.get('modified_at'),
            }

            # Remove None values from raw_props
            raw_props = {k: v for k, v in raw_props.items() if v is not None}

            # Create normalized feature
            normalized = self.create_normalized_feature(
                src_id=src_id,
                geometry=geometry,
                sd=sd,
                ed=ed,
                ev=ev,
                bt=bt,
                nm=nm,
                raw_props=raw_props if raw_props else None
            )

            features.append(normalized)

        return features


def main():
    """Run the manual normalizer."""
    import argparse

    parser = argparse.ArgumentParser(description='Normalize manual building entries')
    parser.add_argument('--data-dir', '-d', type=Path,
                        default=Path(__file__).parent.parent.parent / 'data',
                        help='Data directory')
    args = parser.parse_args()

    normalizer = Normalizer(data_dir=args.data_dir)
    success = normalizer.run()
    exit(0 if success else 1)


if __name__ == '__main__':
    main()
