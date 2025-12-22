#!/usr/bin/env python3
"""
SQLite database schema for building date evidence.

Tables:
- sources: Data source metadata
- buildings: Master building records
- evidence: Per-source date evidence
- estimates: Computed best estimates
"""

import sqlite3
from pathlib import Path
from typing import Optional

# Default database path
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "db" / "buildings.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get database connection with row factory."""
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # Better concurrency
    return conn


def init_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Initialize database with schema."""
    conn = get_connection(db_path)

    # Sources table - metadata about each data source
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            source_id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            source_type TEXT NOT NULL,  -- registry, map, aerial, osm, ml
            reference_year INTEGER,      -- Year the source represents (for maps)
            priority INTEGER DEFAULT 100,
            trust_dates BOOLEAN DEFAULT 0,
            evidence_strength TEXT DEFAULT 'low',  -- low, medium, high
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Buildings table - master record for each building
    conn.execute("""
        CREATE TABLE IF NOT EXISTS buildings (
            building_id TEXT PRIMARY KEY,

            -- Best geometry (from highest priority source)
            geometry_json TEXT,
            geometry_source TEXT,

            -- Centroid for spatial queries
            centroid_lon REAL,
            centroid_lat REAL,

            -- Basic attributes
            building_type TEXT,
            name TEXT,

            -- Computed best estimate (denormalized for performance)
            est_start_year INTEGER,
            est_end_year INTEGER,
            est_confidence REAL,
            est_method TEXT,  -- exact, bounded, inferred

            -- Metadata
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (geometry_source) REFERENCES sources(source_id)
        )
    """)

    # Evidence table - per-source date evidence
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            building_id TEXT NOT NULL,
            source_id TEXT NOT NULL,

            -- Evidence type
            evidence_type TEXT NOT NULL,  -- presence, absence, exact, range

            -- Date bounds
            min_year INTEGER,  -- Earliest possible (NULL = unknown)
            max_year INTEGER,  -- Latest possible (NULL = still exists)
            exact_year INTEGER,  -- If precisely known

            -- For demolished buildings
            end_year INTEGER,  -- Demolition year if known
            end_year_max INTEGER,  -- Latest possible demolition

            -- Confidence
            confidence REAL DEFAULT 0.5,
            confidence_reason TEXT,

            -- Source-specific ID
            source_local_id TEXT,  -- ID in the source system

            -- Extraction metadata
            method TEXT,  -- manual, ml_detection, registry, tag
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            -- Raw data preserved
            raw_properties_json TEXT,

            UNIQUE(building_id, source_id),
            FOREIGN KEY (building_id) REFERENCES buildings(building_id),
            FOREIGN KEY (source_id) REFERENCES sources(source_id)
        )
    """)

    # Estimates table - computed best estimates with full provenance
    conn.execute("""
        CREATE TABLE IF NOT EXISTS estimates (
            building_id TEXT PRIMARY KEY,

            -- Best estimate
            start_year INTEGER,
            start_year_min INTEGER,  -- Confidence interval
            start_year_max INTEGER,

            end_year INTEGER,  -- NULL = still exists
            end_year_min INTEGER,
            end_year_max INTEGER,

            -- Confidence and method
            confidence REAL,
            method TEXT,  -- exact, bounded, range, inferred

            -- Which sources contributed
            contributing_sources TEXT,  -- JSON array
            primary_source TEXT,  -- Most authoritative source

            -- Calculation metadata
            calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            evidence_count INTEGER,

            FOREIGN KEY (building_id) REFERENCES buildings(building_id)
        )
    """)

    # Indexes for common queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_building ON evidence(building_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_buildings_centroid ON buildings(centroid_lon, centroid_lat)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_buildings_start_year ON buildings(est_start_year)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_estimates_start_year ON estimates(start_year)")

    # Insert default sources
    default_sources = [
        ('sefrak', 'SEFRAK Cultural Heritage Registry', 'registry', None, 1, 1, 'high', 'Official pre-1900 building registry'),
        ('fkb_bygning', 'FKB-Bygning (Kartverket)', 'registry', None, 2, 0, 'high', 'Official cadastral geometry'),
        ('osm', 'OpenStreetMap', 'osm', None, 5, 0, 'medium', 'Community-sourced, trust explicit dates'),
        ('map_1868', 'Trondheim Map 1868', 'map', 1868, 20, 0, 'medium', 'Historical city map'),
        ('map_1880', 'Kartverket Map 1880', 'map', 1880, 21, 0, 'medium', 'Historical map'),
        ('map_1909', 'Trondheim Map 1909', 'map', 1909, 22, 0, 'medium', 'Historical city map'),
        ('map_1936', 'Trondheim Map 1936', 'map', 1936, 23, 0, 'medium', 'Historical city map'),
        ('map_1979', 'Trondheim Map 1979', 'map', 1979, 24, 0, 'medium', 'Historical city map'),
    ]

    conn.executemany("""
        INSERT OR IGNORE INTO sources
        (source_id, source_name, source_type, reference_year, priority, trust_dates, evidence_strength, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, default_sources)

    conn.commit()
    return conn


def get_stats(conn: sqlite3.Connection) -> dict:
    """Get database statistics."""
    stats = {}

    stats['sources'] = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    stats['buildings'] = conn.execute("SELECT COUNT(*) FROM buildings").fetchone()[0]
    stats['evidence'] = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    stats['estimates'] = conn.execute("SELECT COUNT(*) FROM estimates").fetchone()[0]

    stats['buildings_with_estimates'] = conn.execute(
        "SELECT COUNT(*) FROM buildings WHERE est_start_year IS NOT NULL"
    ).fetchone()[0]

    stats['evidence_by_source'] = {}
    for row in conn.execute("SELECT source_id, COUNT(*) as cnt FROM evidence GROUP BY source_id"):
        stats['evidence_by_source'][row['source_id']] = row['cnt']

    return stats


if __name__ == "__main__":
    # Initialize database and show stats
    print("Initializing database...")
    conn = init_db()

    stats = get_stats(conn)
    print(f"\nDatabase stats:")
    print(f"  Sources: {stats['sources']}")
    print(f"  Buildings: {stats['buildings']}")
    print(f"  Evidence records: {stats['evidence']}")
    print(f"  Estimates: {stats['estimates']}")

    print(f"\nDatabase location: {DEFAULT_DB_PATH}")
    conn.close()
