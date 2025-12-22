#!/usr/bin/env python3
"""
Import normalized GeoJSON sources into the evidence database.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.schema import init_db, get_stats
from db.buildings import upsert_building
from db.evidence import Evidence, add_evidence


def import_sefrak(conn, data_dir: Path) -> int:
    """Import SEFRAK buildings with exact dates."""
    sefrak_file = data_dir / "sources" / "sefrak" / "normalized" / "buildings.geojson"

    if not sefrak_file.exists():
        print(f"  SEFRAK file not found: {sefrak_file}")
        return 0

    with open(sefrak_file) as f:
        data = json.load(f)

    count = 0
    for feat in data.get('features', []):
        props = feat.get('properties', {})
        geom = feat.get('geometry')

        src_id = props.get('_src_id')
        if not src_id:
            continue

        building_id = f"sefrak:{src_id}"

        # Upsert building
        upsert_building(
            conn,
            building_id=building_id,
            geometry=geom,
            geometry_source='sefrak',
            building_type=props.get('bt'),
            name=props.get('nm')
        )

        # Add evidence
        start_date = props.get('sd')
        end_date = props.get('ed')

        if start_date:
            evidence = Evidence(
                building_id=building_id,
                source_id='sefrak',
                evidence_type='exact',
                exact_year=start_date,
                end_year=end_date,
                confidence=0.95,  # SEFRAK is authoritative
                confidence_reason='official_registry',
                source_local_id=src_id,
                method='registry',
                raw_properties=props.get('_raw')
            )
            add_evidence(conn, evidence)
            count += 1

    conn.commit()
    return count


def import_osm(conn, data_dir: Path) -> int:
    """Import OSM buildings."""
    osm_file = data_dir / "sources" / "osm" / "normalized" / "buildings.geojson"

    if not osm_file.exists():
        print(f"  OSM file not found: {osm_file}")
        return 0

    with open(osm_file) as f:
        data = json.load(f)

    count = 0
    for feat in data.get('features', []):
        props = feat.get('properties', {})
        geom = feat.get('geometry')

        src_id = props.get('_src_id')
        if not src_id:
            continue

        building_id = f"osm:{src_id}"

        # Upsert building
        upsert_building(
            conn,
            building_id=building_id,
            geometry=geom,
            geometry_source='osm',
            building_type=props.get('bt'),
            name=props.get('nm')
        )

        # Add evidence
        start_date = props.get('sd')
        end_date = props.get('ed')

        # OSM: presence evidence (building exists now)
        evidence_type = 'presence'
        confidence = 0.6
        confidence_reason = 'osm_presence'

        if start_date:
            # Has explicit date - higher confidence
            evidence_type = 'exact'
            confidence = 0.85
            confidence_reason = 'osm_explicit_date'

        evidence = Evidence(
            building_id=building_id,
            source_id='osm',
            evidence_type=evidence_type,
            exact_year=start_date if evidence_type == 'exact' else None,
            max_year=2025 if evidence_type == 'presence' else None,
            end_year=end_date,
            confidence=confidence,
            confidence_reason=confidence_reason,
            source_local_id=src_id,
            method='tag' if start_date else 'presence',
            raw_properties=props.get('_raw')
        )
        add_evidence(conn, evidence)
        count += 1

    conn.commit()
    return count


def import_ml_source(conn, data_dir: Path, source_id: str, reference_year: int) -> int:
    """Import ML-detected buildings from a historical map."""

    # Try multiple possible paths
    possible_paths = [
        data_dir / "kartverket" / f"buildings_{reference_year}.geojson",
        data_dir / "kartverket" / str(reference_year) / "extracted" / f"buildings_{reference_year}.geojson",
        data_dir / "sources" / "ml_detected" / source_id.replace('map_', 'kartverket_') / "normalized" / "buildings.geojson",
        data_dir / "sources" / "ml_detected" / source_id / "normalized" / "buildings.geojson",
    ]

    ml_file = None
    for path in possible_paths:
        if path.exists():
            ml_file = path
            break

    if not ml_file:
        print(f"  ML source not found for {source_id}")
        return 0

    with open(ml_file) as f:
        data = json.load(f)

    count = 0
    for i, feat in enumerate(data.get('features', [])):
        props = feat.get('properties', {})
        geom = feat.get('geometry')

        # Generate ID from source - use index if no ID provided
        src_id = props.get('_src_id') or props.get('id') or f"{reference_year}_{i}"
        building_id = f"{source_id}:{src_id}"

        # Upsert building
        upsert_building(
            conn,
            building_id=building_id,
            geometry=geom,
            geometry_source=source_id,
            building_type=props.get('bt') or props.get('class'),
            name=None
        )

        # Add evidence - presence on this map means building existed BY this year
        ml_confidence = props.get('confidence', 0.75)

        evidence = Evidence(
            building_id=building_id,
            source_id=source_id,
            evidence_type='presence',
            max_year=reference_year,  # Building existed BY this year
            confidence=ml_confidence,
            confidence_reason='ml_detection',
            source_local_id=src_id,
            method='ml_detection',
            raw_properties=props
        )
        add_evidence(conn, evidence)
        count += 1

    conn.commit()
    return count


def main():
    """Import all available sources."""
    print("Initializing database...")
    conn = init_db()

    data_dir = Path(__file__).parent.parent.parent / "data"

    print("\nImporting sources:")

    # Import SEFRAK
    print("  Importing SEFRAK...")
    sefrak_count = import_sefrak(conn, data_dir)
    print(f"    → {sefrak_count} buildings with dates")

    # Import OSM
    print("  Importing OSM...")
    osm_count = import_osm(conn, data_dir)
    print(f"    → {osm_count} buildings")

    # Import ML sources
    ml_sources = [
        ('map_1880', 1880),
        ('map_1868', 1868),
        ('map_1909', 1909),
        ('map_1936', 1936),
    ]

    for source_id, year in ml_sources:
        print(f"  Importing {source_id}...")
        ml_count = import_ml_source(conn, data_dir, source_id, year)
        print(f"    → {ml_count} buildings")

    # Show stats
    print("\nDatabase statistics:")
    stats = get_stats(conn)
    print(f"  Buildings: {stats['buildings']}")
    print(f"  Evidence records: {stats['evidence']}")
    print(f"  By source:")
    for source, cnt in stats['evidence_by_source'].items():
        print(f"    - {source}: {cnt}")

    conn.close()
    print("\nImport complete!")


if __name__ == "__main__":
    main()
