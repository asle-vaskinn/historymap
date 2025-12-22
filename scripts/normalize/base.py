#!/usr/bin/env python3
"""
Base class for data normalization.
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# Common normalized schema
NORMALIZED_SCHEMA = {
    'required': ['_src', '_src_id', '_ingested'],
    'optional': ['sd', 'ed', 'ev', 'bt', 'nm', '_raw']
}


class BaseNormalizer(ABC):
    """Base class for source-specific data normalizers."""

    def __init__(self, source_id: str, data_dir: Optional[Path] = None):
        self.source_id = source_id
        self.data_dir = data_dir or Path(__file__).parent.parent.parent / 'data'
        self.source_dir = self.data_dir / 'sources' / source_id
        self.raw_dir = self.source_dir / 'raw'
        self.normalized_dir = self.source_dir / 'normalized'
        self.manifest_path = self.source_dir / 'manifest.json'

        # Ensure directories exist
        self.normalized_dir.mkdir(parents=True, exist_ok=True)

    def load_manifest(self) -> Dict:
        """Load the source manifest."""
        if self.manifest_path.exists():
            with open(self.manifest_path) as f:
                return json.load(f)
        return {}

    def save_manifest(self, manifest: Dict) -> None:
        """Save the source manifest."""
        with open(self.manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

    def create_normalized_feature(
        self,
        src_id: str,
        geometry: Dict,
        sd: Optional[int] = None,
        ed: Optional[int] = None,
        ev: str = 'l',
        bt: Optional[str] = None,
        nm: Optional[str] = None,
        raw_props: Optional[Dict] = None
    ) -> Dict:
        """
        Create a normalized GeoJSON feature.

        Args:
            src_id: Source-specific ID
            geometry: GeoJSON geometry
            sd: Start date (year built)
            ed: End date (year demolished)
            ev: Evidence strength (h/m/l)
            bt: Building type
            nm: Building name
            raw_props: Original properties to preserve

        Returns:
            Normalized GeoJSON feature
        """
        props = {
            '_src': self.source_id,
            '_src_id': src_id,
            '_ingested': datetime.utcnow().strftime('%Y-%m-%d'),
        }

        if sd is not None:
            props['sd'] = sd
        if ed is not None:
            props['ed'] = ed
        if ev:
            props['ev'] = ev
        if bt:
            props['bt'] = bt
        if nm:
            props['nm'] = nm
        if raw_props:
            props['_raw'] = raw_props

        return {
            'type': 'Feature',
            'properties': props,
            'geometry': geometry
        }

    def validate_feature(self, feature: Dict) -> List[str]:
        """
        Validate a normalized feature.

        Returns list of validation errors (empty if valid).
        """
        errors = []
        props = feature.get('properties', {})

        for field in NORMALIZED_SCHEMA['required']:
            if field not in props:
                errors.append(f"Missing required field: {field}")

        if 'geometry' not in feature or not feature['geometry']:
            errors.append("Missing geometry")

        if 'ev' in props and props['ev'] not in ('h', 'm', 'l'):
            errors.append(f"Invalid evidence level: {props['ev']}")

        return errors

    @abstractmethod
    def normalize(self) -> List[Dict]:
        """
        Normalize raw data to common schema.

        Returns:
            List of normalized GeoJSON features
        """
        pass

    def run(self) -> bool:
        """Run normalization and save output."""
        print(f"Normalizing {self.source_id}...")

        try:
            features = self.normalize()

            # Validate all features
            errors = []
            for i, feat in enumerate(features):
                feat_errors = self.validate_feature(feat)
                if feat_errors:
                    errors.extend([f"Feature {i}: {e}" for e in feat_errors])

            if errors:
                print(f"  Validation errors:")
                for e in errors[:10]:  # Show first 10
                    print(f"    - {e}")
                if len(errors) > 10:
                    print(f"    ... and {len(errors) - 10} more")
                return False

            # Save output
            output_path = self.normalized_dir / 'buildings.geojson'
            output = {
                'type': 'FeatureCollection',
                'features': features
            }
            with open(output_path, 'w') as f:
                json.dump(output, f)

            # Update manifest
            manifest = self.load_manifest()
            manifest['normalized_at'] = datetime.utcnow().isoformat() + 'Z'
            manifest['normalized_file'] = 'buildings.geojson'
            manifest['normalized_count'] = len(features)
            self.save_manifest(manifest)

            print(f"  Success: {len(features)} features normalized")
            print(f"  Output: {output_path}")
            return True

        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            return False
