#!/usr/bin/env python3
"""
Calculate date estimates for all buildings with evidence.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.schema import init_db, get_stats
from db.evidence import update_all_estimates, get_estimate


def main():
    print("Calculating date estimates...")
    conn = init_db()

    # Calculate all estimates
    count = update_all_estimates(conn)
    print(f"\nCalculated estimates for {count} buildings")

    # Get statistics
    stats = conn.execute("""
        SELECT
            method,
            COUNT(*) as count,
            AVG(confidence) as avg_confidence,
            MIN(start_year) as min_year,
            MAX(start_year) as max_year
        FROM estimates
        GROUP BY method
        ORDER BY count DESC
    """).fetchall()

    print("\nEstimate methods:")
    for row in stats:
        print(f"  {row['method']}: {row['count']} buildings")
        print(f"    - Avg confidence: {row['avg_confidence']:.2f}")
        print(f"    - Year range: {row['min_year']} - {row['max_year']}")

    # Show some examples
    print("\nExample estimates (exact dates from SEFRAK):")
    examples = conn.execute("""
        SELECT e.*, b.name
        FROM estimates e
        JOIN buildings b ON e.building_id = b.building_id
        WHERE e.method = 'exact'
        ORDER BY e.start_year
        LIMIT 5
    """).fetchall()

    for ex in examples:
        name = ex['name'] or 'Unnamed'
        print(f"  {ex['building_id']}: {name}")
        print(f"    Built: {ex['start_year']} (confidence: {ex['confidence']})")

    # Show date distribution
    print("\nBuildings by era:")
    eras = conn.execute("""
        SELECT
            CASE
                WHEN start_year < 1800 THEN 'Pre-1800'
                WHEN start_year < 1850 THEN '1800-1849'
                WHEN start_year < 1900 THEN '1850-1899'
                WHEN start_year < 1950 THEN '1900-1949'
                WHEN start_year < 2000 THEN '1950-1999'
                ELSE '2000+'
            END as era,
            COUNT(*) as count
        FROM estimates
        WHERE start_year IS NOT NULL
        GROUP BY era
        ORDER BY era
    """).fetchall()

    for era in eras:
        print(f"  {era['era']}: {era['count']} buildings")

    # Check OSM date coverage
    osm_with_dates = conn.execute("""
        SELECT COUNT(*) FROM evidence
        WHERE source_id = 'osm' AND evidence_type = 'exact'
    """).fetchone()[0]

    print(f"\nOSM buildings with explicit dates: {osm_with_dates}")

    conn.close()


if __name__ == "__main__":
    main()
