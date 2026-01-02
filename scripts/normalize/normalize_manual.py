#!/usr/bin/env python3
"""
Normalizer for manually entered building data.

Reads from two sources:
1. buildings.geojson - static manual entries (historical buildings, etc.)
2. edits.json - UI-based edits from the web interface

Manual entries have full provenance tracking:
- added_by, added_at: Who added and when
- verified, verified_by, verified_at: Verification status
- modified_by, modified_at: Modification tracking

These are preserved in _raw for audit trails.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

try:
    from base import BaseNormalizer
except ImportError:
    from normalize.base import BaseNormalizer


class Normalizer(BaseNormalizer):
    """Normalizer for manual building entries."""

    def __init__(self, data_dir: Optional[Path] = None):
        super().__init__('manual', data_dir)

    def normalize(self) -> List[Dict]:
        """
        Normalize manual building entries.

        Reads from two sources:
        1. buildings.geojson - static manual entries (historical buildings, etc.)
        2. edits.json - UI-based edits from the web interface

        Returns:
            List of normalized GeoJSON features
        """
        features = []

        # Source 1: Static manual entries
        raw_path = self.raw_dir / 'buildings.geojson'
        if raw_path.exists():
            with open(raw_path) as f:
                raw_data = json.load(f)
            static_count = 0
            for feat in raw_data.get('features', []):
                normalized = self._normalize_static_feature(feat, len(features))
                if normalized:
                    features.append(normalized)
                    static_count += 1
            print(f"  Loaded {static_count} features from buildings.geojson")

        # Source 2: UI-based edits
        edits_path = self.raw_dir / 'edits.json'
        if edits_path.exists():
            with open(edits_path) as f:
                edits_data = json.load(f)
            edits_count = 0
            for feat in edits_data.get('features', []):
                normalized = self._normalize_edit(feat)
                if normalized:
                    features.append(normalized)
                    edits_count += 1
            print(f"  Loaded {edits_count} features from edits.json")

        return features

    def _normalize_edit(self, feat: Dict) -> Optional[Dict]:
        """Normalize an edit from edits.json (UI-based edits)."""
        props = feat.get('properties', {})
        geometry = feat.get('geometry')

        if not geometry:
            return None

        osm_id = props.get('osm_id', '')
        src_id = osm_id if osm_id else f"edit_{props.get('edited_at', 'unknown')}"

        # Create normalized feature with OSM reference
        normalized = self.create_normalized_feature(
            src_id=src_id,
            geometry=geometry,
            sd=props.get('sd'),
            ed=props.get('ed'),
            ev=props.get('ev', 'h'),  # Manual edits default to high evidence
            bt=None,
            nm=None,
            raw_props={
                'osm_id': osm_id,
                'note': props.get('note'),
                'edited_at': props.get('edited_at'),
            }
        )

        # Add osm_ref for merge matching (this is what the merge uses)
        normalized['properties']['osm_ref'] = osm_id
        # Also keep osm_id for reference
        normalized['properties']['osm_id'] = osm_id

        return normalized

    def _normalize_static_feature(self, feat: Dict, index: int) -> Optional[Dict]:
        """Normalize a feature from buildings.geojson (static manual entries)."""
        props = feat.get('properties', {})
        geometry = feat.get('geometry')

        if not geometry:
            print(f"  Skipping feature without geometry: {props.get('id')}")
            return None

        # Extract normalized fields
        src_id = props.get('id', f"man_{index:04d}")
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

        return normalized


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
