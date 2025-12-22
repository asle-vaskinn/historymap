#!/usr/bin/env python3
"""
Building verification pipeline.

Verifies if known buildings (from OSM/SEFRAK) exist in historical maps
using ML extraction. Updates building records with verification evidence.

Workflow:
1. Ensure map is georeferenced (GCPs or existing)
2. Run ML inference to extract buildings
3. Vectorize to GeoJSON polygons
4. Match extracted buildings to known buildings
5. Update verification evidence

Usage:
    python verify_buildings.py \
        --map data/kartverket/raw/1880.png \
        --gcps data/kartverket/gcps/1880.gcp.json \
        --buildings data/buildings_temporal.geojson \
        --output data/buildings_verified.geojson

    # Multiple maps at once
    python verify_buildings.py \
        --map-dir data/kartverket/georeferenced/ \
        --buildings data/buildings_temporal.geojson \
        --output data/buildings_verified.geojson
"""

import argparse
import json
import logging
import math
import os
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class MapInfo:
    """Information about a historical map source."""
    map_id: str
    map_date: int
    file_path: Path
    gcp_path: Optional[Path] = None
    bounds: Optional[Tuple[float, float, float, float]] = None


@dataclass
class Detection:
    """A single ML detection match."""
    map_date: int
    map_id: str
    ml_confidence: float
    overlap_score: float
    combined_score: float
    centroid_distance: float
    quality: str  # 'high', 'medium', 'low'


@dataclass
class VerificationRecord:
    """Verification record for a building."""
    building_id: str
    maps_checked: List[int] = field(default_factory=list)
    detections: List[Detection] = field(default_factory=list)
    verified: bool = False
    verified_date: Optional[int] = None
    earliest_detection: Optional[int] = None


@dataclass
class VerificationReport:
    """Summary report of verification run."""
    total_buildings: int
    buildings_checked: int
    buildings_verified: int
    buildings_not_found: int
    detections_by_quality: Dict[str, int]
    maps_processed: List[str]
    processing_time_seconds: float


def load_geojson(path: Path) -> Dict:
    """Load a GeoJSON file."""
    with open(path, 'r') as f:
        return json.load(f)


def save_geojson(data: Dict, path: Path):
    """Save a GeoJSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def get_polygon_centroid(coords: List) -> Tuple[float, float]:
    """Calculate centroid of a polygon."""
    if not coords or not coords[0]:
        return (0, 0)
    ring = coords[0]
    n = len(ring)
    if n == 0:
        return (0, 0)
    cx = sum(p[0] for p in ring) / n
    cy = sum(p[1] for p in ring) / n
    return (cx, cy)


def get_bbox(coords: List) -> Tuple[float, float, float, float]:
    """Get bounding box of a polygon."""
    if not coords or not coords[0]:
        return (0, 0, 0, 0)
    ring = coords[0]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def bboxes_overlap(bbox1: Tuple, bbox2: Tuple, buffer: float = 0.0001) -> bool:
    """Check if two bounding boxes overlap with a buffer."""
    return not (
        bbox1[2] + buffer < bbox2[0] - buffer or
        bbox1[0] - buffer > bbox2[2] + buffer or
        bbox1[3] + buffer < bbox2[1] - buffer or
        bbox1[1] - buffer > bbox2[3] + buffer
    )


def point_in_polygon(point: Tuple[float, float], coords: List) -> bool:
    """Check if a point is inside a polygon using ray casting."""
    if not coords or not coords[0]:
        return False
    ring = coords[0]
    x, y = point
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def calculate_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calculate distance between two points (in degrees, ~111km per degree)."""
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)


def calculate_combined_confidence(
    ml_confidence: float,
    overlap_score: float,
    area_ratio: float,
    centroid_distance: float
) -> float:
    """
    Calculate combined confidence score for a building verification.

    Args:
        ml_confidence: ML model confidence (0-1)
        overlap_score: Geometric overlap score (0-1)
        area_ratio: Ratio of areas (smaller/larger, 0-1)
        centroid_distance: Distance between centroids in degrees

    Returns:
        Combined confidence score (0-1)
    """
    # Normalize centroid distance (20m ~ 0.0002 degrees at this latitude)
    centroid_score = max(0, 1 - (centroid_distance / 0.0002))

    # Weighted combination
    combined = (
        0.4 * ml_confidence +
        0.3 * overlap_score +
        0.2 * min(area_ratio, 1.0) +
        0.1 * centroid_score
    )

    return min(1.0, max(0.0, combined))


def get_quality_level(score: float) -> str:
    """Determine quality level from combined score."""
    if score >= 0.7:
        return 'high'
    elif score >= 0.5:
        return 'medium'
    else:
        return 'low'


class BuildingVerifier:
    """
    End-to-end building verification pipeline.

    Takes known buildings and historical maps, runs ML extraction,
    and matches extracted buildings to verify existence.
    """

    def __init__(
        self,
        buildings_path: Path,
        output_path: Path,
        model_path: Path,
        work_dir: Optional[Path] = None,
        confidence_threshold: float = 0.5
    ):
        """
        Initialize verifier.

        Args:
            buildings_path: Path to buildings GeoJSON (OSM/SEFRAK merged)
            output_path: Path to output verified buildings GeoJSON
            model_path: Path to ML model checkpoint
            work_dir: Working directory for intermediate files
            confidence_threshold: Minimum combined score to count as verified
        """
        self.buildings_path = Path(buildings_path)
        self.output_path = Path(output_path)
        self.model_path = Path(model_path)
        self.confidence_threshold = confidence_threshold

        # Working directory for intermediate files
        if work_dir:
            self.work_dir = Path(work_dir)
            self.work_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._temp_dir = tempfile.TemporaryDirectory()
            self.work_dir = Path(self._temp_dir.name)

        # Load buildings
        logger.info(f"Loading buildings from {buildings_path}")
        self.buildings_data = load_geojson(self.buildings_path)
        self.buildings = self.buildings_data['features']
        logger.info(f"Loaded {len(self.buildings)} buildings")

        # Initialize verification records
        self.verification_records: Dict[str, VerificationRecord] = {}
        self._init_verification_records()

        # Track processed maps
        self.maps_processed: List[str] = []

    def _init_verification_records(self):
        """Initialize verification records for all buildings."""
        for feat in self.buildings:
            props = feat.get('properties', {})
            bid = props.get('bid') or props.get('id') or str(id(feat))
            self.verification_records[str(bid)] = VerificationRecord(
                building_id=str(bid)
            )

    def _get_building_id(self, feature: Dict) -> str:
        """Get a unique ID for a building feature."""
        props = feature.get('properties', {})
        return str(props.get('bid') or props.get('id') or id(feature))

    def process_map(self, map_info: MapInfo) -> Dict:
        """
        Process a single historical map.

        Steps:
        1. Ensure georeferenced
        2. Run ML inference
        3. Vectorize buildings
        4. Match to known buildings
        5. Record evidence

        Args:
            map_info: Information about the map to process

        Returns:
            Processing statistics
        """
        logger.info(f"Processing map: {map_info.map_id} ({map_info.map_date})")

        # Step 1: Ensure georeferenced
        georef_path, bounds = self._ensure_georeferenced(map_info)
        if bounds is None:
            logger.error(f"Could not determine bounds for {map_info.map_id}")
            return {'error': 'No bounds'}

        # Step 2: Run ML inference
        mask_path = self._run_inference(georef_path, map_info.map_id)

        # Step 3: Vectorize
        extracted_buildings = self._vectorize(mask_path, bounds, map_info.map_id)
        logger.info(f"Extracted {len(extracted_buildings)} buildings from ML")

        # Step 4: Match buildings
        matches = self._match_buildings(extracted_buildings, map_info)

        # Step 5: Record evidence
        for match in matches:
            self._record_evidence(match, map_info)

        self.maps_processed.append(map_info.map_id)

        return {
            'map_id': map_info.map_id,
            'map_date': map_info.map_date,
            'extracted_count': len(extracted_buildings),
            'match_count': len(matches),
            'high_quality_matches': sum(1 for m in matches if m['quality'] == 'high'),
            'medium_quality_matches': sum(1 for m in matches if m['quality'] == 'medium'),
            'low_quality_matches': sum(1 for m in matches if m['quality'] == 'low'),
        }

    def _ensure_georeferenced(self, map_info: MapInfo) -> Tuple[Path, Optional[Tuple]]:
        """
        Ensure map is georeferenced.

        Returns:
            Tuple of (georeferenced_path, bounds)
        """
        try:
            # Import the georeferencing module
            sys.path.insert(0, str(Path(__file__).parent))
            from georeference_map import check_georeferencing, ensure_georeferenced

            output_path = self.work_dir / f"{map_info.map_id}_georef.tif"

            result_path, info = ensure_georeferenced(
                input_path=map_info.file_path,
                gcp_path=map_info.gcp_path,
                output_path=output_path
            )

            return result_path, info.bounds

        except Exception as e:
            logger.error(f"Georeferencing failed: {e}")
            # Fall back to provided bounds if available
            if map_info.bounds:
                return map_info.file_path, map_info.bounds
            return map_info.file_path, None

    def _run_inference(self, image_path: Path, map_id: str) -> Path:
        """
        Run ML inference to generate segmentation mask.

        Args:
            image_path: Path to georeferenced image
            map_id: Map identifier for output naming

        Returns:
            Path to generated mask
        """
        mask_path = self.work_dir / f"{map_id}_mask.png"

        # Import and run prediction
        sys.path.insert(0, str(Path(__file__).parent.parent / 'ml'))

        try:
            from predict import load_model, process_single_image, get_device

            device = get_device()
            model = load_model(str(self.model_path), device)

            process_single_image(
                model=model,
                image_path=str(image_path),
                output_path=str(mask_path),
                device=device,
                save_probabilities=True
            )

            logger.info(f"Generated mask: {mask_path}")
            return mask_path

        except Exception as e:
            logger.error(f"ML inference failed: {e}")
            raise

    def _vectorize(
        self,
        mask_path: Path,
        bounds: Tuple[float, float, float, float],
        map_id: str
    ) -> List[Dict]:
        """
        Vectorize mask to building polygons.

        Args:
            mask_path: Path to segmentation mask
            bounds: Geographic bounds (west, south, east, north)
            map_id: Map identifier

        Returns:
            List of building feature dicts
        """
        output_path = self.work_dir / f"{map_id}_buildings.geojson"

        # Import and run vectorization
        sys.path.insert(0, str(Path(__file__).parent.parent / 'ml'))

        try:
            from vectorize import vectorize_buildings

            # Format bounds as expected by vectorize (min_lon, min_lat, max_lon, max_lat)
            result = vectorize_buildings(
                mask_path=str(mask_path),
                output_path=str(output_path),
                bounds=bounds,
                simplify_tolerance=1.0,
                min_area=10.0,
                merge_adjacent=True
            )

            return result.get('features', [])

        except Exception as e:
            logger.error(f"Vectorization failed: {e}")
            return []

    def _match_buildings(
        self,
        extracted: List[Dict],
        map_info: MapInfo
    ) -> List[Dict]:
        """
        Match extracted buildings to known buildings.

        Args:
            extracted: List of ML-extracted building features
            map_info: Map information for context

        Returns:
            List of match records
        """
        matches = []

        if not extracted:
            return matches

        # Pre-compute bboxes for extracted buildings
        extracted_info = []
        for feat in extracted:
            if feat['geometry']['type'] != 'Polygon':
                continue
            coords = feat['geometry']['coordinates']
            bbox = get_bbox(coords)
            centroid = get_polygon_centroid(coords)
            props = feat.get('properties', {})
            ml_conf = props.get('confidence', props.get('mlc', 0.7))
            extracted_info.append({
                'feature': feat,
                'bbox': bbox,
                'centroid': centroid,
                'coords': coords,
                'ml_confidence': ml_conf
            })

        # Match each known building against extracted
        for known_feat in self.buildings:
            if known_feat['geometry']['type'] != 'Polygon':
                continue

            known_coords = known_feat['geometry']['coordinates']
            known_bbox = get_bbox(known_coords)
            known_centroid = get_polygon_centroid(known_coords)
            building_id = self._get_building_id(known_feat)

            best_match = None
            best_score = 0

            for ext_info in extracted_info:
                # Quick bbox filter
                if not bboxes_overlap(known_bbox, ext_info['bbox'], buffer=0.0002):
                    continue

                # Calculate overlap score
                ml_in_known = point_in_polygon(ext_info['centroid'], known_coords)
                known_in_ml = point_in_polygon(known_centroid, ext_info['coords'])

                if ml_in_known or known_in_ml:
                    overlap_score = 0.8
                else:
                    # Check distance
                    dist = calculate_distance(known_centroid, ext_info['centroid'])
                    if dist < 0.0002:  # ~20m
                        overlap_score = 0.6
                    else:
                        overlap_score = 0

                if overlap_score == 0:
                    continue

                # Calculate area ratio (simple approximation)
                # This would need proper polygon area calculation
                area_ratio = 0.8  # Placeholder

                centroid_dist = calculate_distance(known_centroid, ext_info['centroid'])

                combined = calculate_combined_confidence(
                    ml_confidence=ext_info['ml_confidence'],
                    overlap_score=overlap_score,
                    area_ratio=area_ratio,
                    centroid_distance=centroid_dist
                )

                if combined > best_score:
                    best_score = combined
                    best_match = {
                        'building_id': building_id,
                        'ml_confidence': ext_info['ml_confidence'],
                        'overlap_score': overlap_score,
                        'combined_score': combined,
                        'centroid_distance': centroid_dist,
                        'quality': get_quality_level(combined)
                    }

            if best_match and best_match['combined_score'] >= 0.3:  # Low threshold for recording
                matches.append(best_match)

        return matches

    def _record_evidence(self, match: Dict, map_info: MapInfo):
        """Record verification evidence for a building."""
        building_id = match['building_id']

        if building_id not in self.verification_records:
            self.verification_records[building_id] = VerificationRecord(
                building_id=building_id
            )

        record = self.verification_records[building_id]

        # Add map to checked list
        if map_info.map_date not in record.maps_checked:
            record.maps_checked.append(map_info.map_date)

        # Add detection
        detection = Detection(
            map_date=map_info.map_date,
            map_id=map_info.map_id,
            ml_confidence=match['ml_confidence'],
            overlap_score=match['overlap_score'],
            combined_score=match['combined_score'],
            centroid_distance=match['centroid_distance'],
            quality=match['quality']
        )
        record.detections.append(detection)

        # Update verification status
        if match['combined_score'] >= self.confidence_threshold:
            record.verified = True
            if record.verified_date is None or map_info.map_date < record.verified_date:
                record.verified_date = map_info.map_date

        # Track earliest detection
        if record.earliest_detection is None or map_info.map_date < record.earliest_detection:
            record.earliest_detection = map_info.map_date

    def finalize(self) -> VerificationReport:
        """
        Finalize verification and generate output.

        Updates buildings_data with verification evidence and saves to output.

        Returns:
            VerificationReport with summary statistics
        """
        logger.info("Finalizing verification...")

        # Update building features with verification evidence
        verified_count = 0
        not_found_count = 0
        quality_counts = {'high': 0, 'medium': 0, 'low': 0}

        for feat in self.buildings:
            building_id = self._get_building_id(feat)
            props = feat.setdefault('properties', {})

            if building_id in self.verification_records:
                record = self.verification_records[building_id]

                # Create verification metadata
                verification = {
                    'maps_checked': sorted(record.maps_checked),
                    'detections': [
                        {
                            'map_date': d.map_date,
                            'map_id': d.map_id,
                            'combined_score': round(d.combined_score, 3),
                            'quality': d.quality
                        }
                        for d in record.detections
                    ],
                    'verified': record.verified,
                    'verified_date': record.verified_date
                }

                props['_verification'] = verification

                # Update temporal fields based on verification
                if record.verified and record.verified_date:
                    current_sd = props.get('sd')

                    # Update start date if verification pushes it earlier
                    if current_sd is None or record.verified_date < current_sd:
                        props['sd'] = record.verified_date
                        props['sd_t'] = 'n'  # not-later-than
                        props['sd_s'] = f"ml{record.verified_date % 100:02d}"

                    # Update evidence level
                    best_detection = max(record.detections, key=lambda d: d.combined_score)
                    props['sd_c'] = round(best_detection.combined_score, 2)

                    if best_detection.quality == 'high':
                        props['ev'] = 'h'
                    elif best_detection.quality == 'medium':
                        props['ev'] = 'm'

                    verified_count += 1
                    quality_counts[best_detection.quality] += 1
                else:
                    not_found_count += 1
            else:
                not_found_count += 1

        # Save output
        self.buildings_data['features'] = self.buildings
        self.buildings_data['metadata'] = {
            'verification_date': datetime.now().isoformat(),
            'maps_processed': self.maps_processed,
            'confidence_threshold': self.confidence_threshold
        }

        save_geojson(self.buildings_data, self.output_path)
        logger.info(f"Saved verified buildings to {self.output_path}")

        # Generate report
        report = VerificationReport(
            total_buildings=len(self.buildings),
            buildings_checked=len([r for r in self.verification_records.values() if r.maps_checked]),
            buildings_verified=verified_count,
            buildings_not_found=not_found_count,
            detections_by_quality=quality_counts,
            maps_processed=self.maps_processed,
            processing_time_seconds=0  # Would need timing code
        )

        # Save report
        report_path = self.output_path.with_suffix('.report.json')
        with open(report_path, 'w') as f:
            json.dump(asdict(report), f, indent=2)
        logger.info(f"Saved verification report to {report_path}")

        return report


def parse_map_info(
    map_path: str,
    gcp_path: Optional[str] = None,
    map_id: Optional[str] = None,
    map_date: Optional[int] = None
) -> MapInfo:
    """
    Parse map information from file paths.

    Attempts to extract map_id and map_date from filenames or GCP file.
    """
    map_path = Path(map_path)

    # Try to get info from GCP file
    if gcp_path:
        gcp_path = Path(gcp_path)
        if gcp_path.exists():
            with open(gcp_path) as f:
                gcp_data = json.load(f)
                if map_id is None:
                    map_id = gcp_data.get('map_id')
                if map_date is None:
                    map_date = gcp_data.get('map_date')

    # Fall back to extracting from filename
    if map_id is None:
        map_id = map_path.stem

    if map_date is None:
        # Try to find a year in the filename
        import re
        year_match = re.search(r'(18\d{2}|19\d{2}|20\d{2})', map_path.stem)
        if year_match:
            map_date = int(year_match.group(1))
        else:
            map_date = 1900  # Default

    return MapInfo(
        map_id=map_id,
        map_date=map_date,
        file_path=map_path,
        gcp_path=Path(gcp_path) if gcp_path else None
    )


def main():
    parser = argparse.ArgumentParser(
        description='Verify building existence in historical maps using ML extraction'
    )

    # Input options
    parser.add_argument('--map', '-m', help='Path to historical map image')
    parser.add_argument('--map-dir', help='Directory of georeferenced maps to process')
    parser.add_argument('--gcps', '-g', help='Path to GCP JSON file')
    parser.add_argument('--map-id', help='Map identifier (default: from filename)')
    parser.add_argument('--map-date', type=int, help='Map year (default: from filename/GCP)')

    # Required inputs
    parser.add_argument('--buildings', '-b', required=True,
                       help='Path to buildings GeoJSON (OSM/SEFRAK merged)')
    parser.add_argument('--model', default='models/checkpoints/best_model.pth',
                       help='Path to ML model checkpoint')

    # Output options
    parser.add_argument('--output', '-o', required=True,
                       help='Path to output verified buildings GeoJSON')
    parser.add_argument('--work-dir', '-w',
                       help='Working directory for intermediate files')

    # Processing options
    parser.add_argument('--confidence-threshold', type=float, default=0.5,
                       help='Minimum combined score to count as verified (default: 0.5)')

    args = parser.parse_args()

    # Validate inputs
    if not args.map and not args.map_dir:
        parser.error("Either --map or --map-dir is required")

    if not Path(args.buildings).exists():
        logger.error(f"Buildings file not found: {args.buildings}")
        sys.exit(1)

    if not Path(args.model).exists():
        logger.error(f"Model checkpoint not found: {args.model}")
        sys.exit(1)

    # Initialize verifier
    verifier = BuildingVerifier(
        buildings_path=Path(args.buildings),
        output_path=Path(args.output),
        model_path=Path(args.model),
        work_dir=Path(args.work_dir) if args.work_dir else None,
        confidence_threshold=args.confidence_threshold
    )

    # Process single map
    if args.map:
        map_info = parse_map_info(
            map_path=args.map,
            gcp_path=args.gcps,
            map_id=args.map_id,
            map_date=args.map_date
        )

        stats = verifier.process_map(map_info)
        logger.info(f"Processed {map_info.map_id}: "
                   f"{stats['extracted_count']} extracted, {stats['match_count']} matched")

    # Process directory of maps
    elif args.map_dir:
        map_dir = Path(args.map_dir)
        map_files = list(map_dir.glob('*.tif')) + list(map_dir.glob('*.png'))

        for map_file in map_files:
            # Look for corresponding GCP file
            gcp_file = map_dir.parent / 'gcps' / f"{map_file.stem}.gcp.json"
            if not gcp_file.exists():
                gcp_file = None

            map_info = parse_map_info(
                map_path=str(map_file),
                gcp_path=str(gcp_file) if gcp_file else None
            )

            try:
                stats = verifier.process_map(map_info)
                logger.info(f"Processed {map_info.map_id}: "
                           f"{stats['extracted_count']} extracted, {stats['match_count']} matched")
            except Exception as e:
                logger.error(f"Error processing {map_file.name}: {e}")

    # Finalize and generate report
    report = verifier.finalize()

    # Print summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"Total buildings: {report.total_buildings}")
    print(f"Buildings checked: {report.buildings_checked}")
    print(f"Buildings verified: {report.buildings_verified}")
    print(f"Buildings not found: {report.buildings_not_found}")
    print(f"\nDetections by quality:")
    for quality, count in report.detections_by_quality.items():
        print(f"  {quality}: {count}")
    print(f"\nMaps processed: {', '.join(report.maps_processed)}")
    print(f"\nOutput: {args.output}")


if __name__ == '__main__':
    main()
