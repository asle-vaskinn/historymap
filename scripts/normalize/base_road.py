#!/usr/bin/env python3
"""
Base class for road data normalization.

Extends BaseNormalizer with road-specific features:
- LineString/MultiLineString geometry support
- Road type (rt) field
- Length calculation (len)
- NVDB reference (nvdb_id)
"""

import json
from abc import abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseNormalizer


# Road-specific normalized schema
ROAD_SCHEMA = {
    'required': ['_src', '_src_id', '_ingested'],
    'optional': [
        'sd',       # start_date - year road constructed
        'ed',       # end_date - year road removed/rerouted
        'ev',       # evidence level (h/m/l)
        'nm',       # road name
        'rt',       # road_type: motorway/primary/secondary/tertiary/residential/path/historical
        'len',      # length in meters
        'nvdb_id',  # NVDB reference if matched
        '_raw'      # original properties
    ]
}

# Valid road types
ROAD_TYPES = {
    'motorway', 'trunk', 'primary', 'secondary', 'tertiary',
    'residential', 'service', 'path', 'track', 'historical', 'unknown'
}


class BaseRoadNormalizer(BaseNormalizer):
    """Base class for road-specific data normalizers."""

    def __init__(self, source_id: str, data_dir: Optional[Path] = None):
        super().__init__(source_id, data_dir)

    def create_normalized_road_feature(
        self,
        src_id: str,
        geometry: Dict,
        sd: Optional[int] = None,
        ed: Optional[int] = None,
        ev: str = 'l',
        nm: Optional[str] = None,
        rt: Optional[str] = None,
        length: Optional[float] = None,
        nvdb_id: Optional[str] = None,
        raw_props: Optional[Dict] = None
    ) -> Dict:
        """
        Create a normalized road GeoJSON feature.

        Args:
            src_id: Source-specific ID
            geometry: GeoJSON geometry (LineString or MultiLineString)
            sd: Start date (year constructed)
            ed: End date (year removed/rerouted)
            ev: Evidence strength (h/m/l)
            nm: Road name
            rt: Road type (motorway/primary/secondary/tertiary/residential/path/historical)
            length: Road segment length in meters
            nvdb_id: NVDB reference ID if matched
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
        if nm:
            props['nm'] = nm
        if rt:
            props['rt'] = rt
        if length is not None:
            props['len'] = round(length, 1)
        if nvdb_id:
            props['nvdb_id'] = nvdb_id
        if raw_props:
            props['_raw'] = raw_props

        return {
            'type': 'Feature',
            'properties': props,
            'geometry': geometry
        }

    def validate_road_feature(self, feature: Dict) -> List[str]:
        """
        Validate a normalized road feature.

        Returns list of validation errors (empty if valid).
        """
        errors = []
        props = feature.get('properties', {})

        # Required fields
        for field in ROAD_SCHEMA['required']:
            if field not in props:
                errors.append(f"Missing required field: {field}")

        # Geometry validation
        geom = feature.get('geometry')
        if not geom:
            errors.append("Missing geometry")
        elif geom.get('type') not in ('LineString', 'MultiLineString'):
            errors.append(f"Invalid geometry type for road: {geom.get('type')} (expected LineString or MultiLineString)")

        # Evidence level
        if 'ev' in props and props['ev'] not in ('h', 'm', 'l'):
            errors.append(f"Invalid evidence level: {props['ev']}")

        # Road type
        if 'rt' in props and props['rt'] not in ROAD_TYPES:
            errors.append(f"Invalid road type: {props['rt']}")

        # Date consistency
        if 'sd' in props and 'ed' in props:
            if props['ed'] is not None and props['sd'] > props['ed']:
                errors.append(f"start_date ({props['sd']}) > end_date ({props['ed']})")

        return errors

    def calculate_length(self, geometry: Dict) -> Optional[float]:
        """
        Calculate approximate length of road in meters.

        Uses simple equirectangular approximation suitable for Trondheim latitude.
        For precise calculations, use pyproj.
        """
        import math

        def haversine_distance(lon1, lat1, lon2, lat2):
            """Calculate distance between two points in meters."""
            R = 6371000  # Earth radius in meters
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlambda = math.radians(lon2 - lon1)

            a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            return R * c

        def line_length(coords):
            """Calculate length of a line from coordinates."""
            total = 0
            for i in range(len(coords) - 1):
                lon1, lat1 = coords[i][:2]
                lon2, lat2 = coords[i+1][:2]
                total += haversine_distance(lon1, lat1, lon2, lat2)
            return total

        geom_type = geometry.get('type')
        coords = geometry.get('coordinates', [])

        if geom_type == 'LineString':
            return line_length(coords)
        elif geom_type == 'MultiLineString':
            return sum(line_length(line) for line in coords)

        return None

    @abstractmethod
    def normalize(self) -> List[Dict]:
        """
        Normalize raw data to common road schema.

        Returns:
            List of normalized GeoJSON features
        """
        pass

    def run(self) -> bool:
        """Run normalization and save output."""
        print(f"Normalizing roads from {self.source_id}...")

        try:
            features = self.normalize()

            # Validate all features
            errors = []
            valid_features = []
            for i, feat in enumerate(features):
                feat_errors = self.validate_road_feature(feat)
                if feat_errors:
                    errors.extend([f"Feature {i}: {e}" for e in feat_errors])
                else:
                    valid_features.append(feat)

            if errors:
                print(f"  Validation warnings ({len(errors)} issues in {len(features)} features):")
                for e in errors[:10]:
                    print(f"    - {e}")
                if len(errors) > 10:
                    print(f"    ... and {len(errors) - 10} more")

            # Save output (even if some features had errors, save the valid ones)
            output_path = self.normalized_dir / 'roads.geojson'
            output = {
                'type': 'FeatureCollection',
                'features': valid_features
            }
            with open(output_path, 'w') as f:
                json.dump(output, f)

            # Update manifest
            manifest = self.load_manifest()
            manifest['normalized_at'] = datetime.utcnow().isoformat() + 'Z'
            manifest['normalized_file'] = 'roads.geojson'
            manifest['normalized_count'] = len(valid_features)
            manifest['validation_errors'] = len(errors)
            self.save_manifest(manifest)

            print(f"  Success: {len(valid_features)} road features normalized")
            if errors:
                print(f"  Skipped: {len(features) - len(valid_features)} invalid features")
            print(f"  Output: {output_path}")
            return True

        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            return False
