#!/usr/bin/env python3
"""
Export buildings to GeoJSON for frontend visualization.
"""

import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

def export_buildings(db_path: Path, output_path: Path, min_confidence: float = 0.0):
    """
    Export buildings from database to GeoJSON.

    Args:
        db_path: Path to SQLite database
        output_path: Output GeoJSON path
        min_confidence: Minimum confidence to include (0.0 = all)
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Query buildings with geometry
    query = """
        SELECT
            building_id,
            geometry_json,
            building_type,
            name,
            est_start_year,
            est_end_year,
            est_confidence,
            est_method,
            centroid_lon,
            centroid_lat
        FROM buildings
        WHERE geometry_json IS NOT NULL
          AND est_start_year IS NOT NULL
    """

    if min_confidence > 0:
        query += f" AND est_confidence >= {min_confidence}"

    rows = conn.execute(query).fetchall()

    features = []
    for row in rows:
        try:
            geom = json.loads(row['geometry_json'])
        except:
            continue

        # Determine source from building_id prefix and map to frontend abbreviations
        raw_source = row['building_id'].split(':')[0] if ':' in row['building_id'] else 'unknown'
        source_map = {
            'sefrak': 'sef',      # SEFRAK cultural heritage
            'osm': 'osm',         # OpenStreetMap
            'matrikkelen': 'mat', # Matrikkelen
            'tk': 'tk',           # Trondheim Kommune
            'ml': 'ml',           # ML Detection
            'man': 'man',         # Manual/researcher verified
        }
        source = source_map.get(raw_source, raw_source)

        # Map confidence to evidence level for frontend
        conf = row['est_confidence'] or 0
        if conf >= 0.5:
            evidence = 'h'  # high
        elif conf >= 0.3:
            evidence = 'm'  # medium
        else:
            evidence = 'l'  # low

        feature = {
            'type': 'Feature',
            'geometry': geom,
            'properties': {
                'id': row['building_id'],
                'sd': row['est_start_year'],  # start_date
                'ed': row['est_end_year'],    # end_date
                'cf': round(conf, 2),          # confidence
                'ev': evidence,                # evidence level
                'src': source,                 # source
                'bt': row['building_type'],   # building_type
                'nm': row['name']             # name
            }
        }
        features.append(feature)

    # Calculate statistics by era
    era_stats = {}
    for f in features:
        year = f['properties']['sd']
        if year < 1800:
            era = 'pre-1800'
        elif year < 1900:
            era = '1800-1899'
        elif year < 1950:
            era = '1900-1949'
        elif year < 2000:
            era = '1950-1999'
        else:
            era = '2000+'
        era_stats[era] = era_stats.get(era, 0) + 1

    # Build GeoJSON
    geojson = {
        'type': 'FeatureCollection',
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'total_buildings': len(features),
            'min_confidence': min_confidence,
            'era_distribution': era_stats,
            'source': 'historymap estimation pipeline'
        },
        'features': features
    }

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(geojson, f)

    print(f"Exported {len(features):,} buildings to {output_path}")
    print(f"Era distribution: {era_stats}")

    conn.close()
    return len(features)


def main():
    db_path = Path(__file__).parent.parent.parent / "data" / "db" / "buildings.db"
    output_dir = Path(__file__).parent.parent.parent / "frontend" / "data"

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    # Export all buildings
    output_path = output_dir / "buildings_temporal.geojson"
    export_buildings(db_path, output_path)

    # Export high-confidence buildings
    output_high = output_dir / "buildings_high_confidence.geojson"
    export_buildings(db_path, output_high, min_confidence=0.5)

    print("\nDone!")


if __name__ == "__main__":
    main()
