#!/usr/bin/env python3
"""
Date evidence management and estimate calculation.
"""

import json
import sqlite3
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Evidence:
    """Date evidence from a single source."""
    building_id: str
    source_id: str
    evidence_type: str  # presence, absence, exact, range

    min_year: Optional[int] = None
    max_year: Optional[int] = None
    exact_year: Optional[int] = None

    end_year: Optional[int] = None
    end_year_max: Optional[int] = None

    confidence: float = 0.5
    confidence_reason: Optional[str] = None

    source_local_id: Optional[str] = None
    method: Optional[str] = None
    raw_properties: Optional[Dict] = None


@dataclass
class DateEstimate:
    """Computed date estimate for a building."""
    building_id: str

    start_year: Optional[int] = None
    start_year_min: Optional[int] = None
    start_year_max: Optional[int] = None

    end_year: Optional[int] = None
    end_year_min: Optional[int] = None
    end_year_max: Optional[int] = None

    confidence: float = 0.0
    method: str = "none"  # exact, bounded, range, inferred

    contributing_sources: List[str] = field(default_factory=list)
    primary_source: Optional[str] = None
    evidence_count: int = 0


def add_evidence(
    conn: sqlite3.Connection,
    evidence: Evidence
) -> None:
    """Add or update evidence for a building from a source."""

    raw_json = None
    if evidence.raw_properties:
        raw_json = json.dumps(evidence.raw_properties)

    conn.execute("""
        INSERT INTO evidence
        (building_id, source_id, evidence_type, min_year, max_year, exact_year,
         end_year, end_year_max, confidence, confidence_reason,
         source_local_id, method, raw_properties_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(building_id, source_id) DO UPDATE SET
            evidence_type = excluded.evidence_type,
            min_year = excluded.min_year,
            max_year = excluded.max_year,
            exact_year = excluded.exact_year,
            end_year = excluded.end_year,
            end_year_max = excluded.end_year_max,
            confidence = excluded.confidence,
            confidence_reason = excluded.confidence_reason,
            source_local_id = excluded.source_local_id,
            method = excluded.method,
            raw_properties_json = excluded.raw_properties_json,
            extracted_at = CURRENT_TIMESTAMP
    """, (
        evidence.building_id,
        evidence.source_id,
        evidence.evidence_type,
        evidence.min_year,
        evidence.max_year,
        evidence.exact_year,
        evidence.end_year,
        evidence.end_year_max,
        evidence.confidence,
        evidence.confidence_reason,
        evidence.source_local_id,
        evidence.method,
        raw_json
    ))


def get_evidence_for_building(
    conn: sqlite3.Connection,
    building_id: str
) -> List[Evidence]:
    """Get all evidence for a building."""
    rows = conn.execute("""
        SELECT e.*, s.priority, s.evidence_strength
        FROM evidence e
        JOIN sources s ON e.source_id = s.source_id
        WHERE e.building_id = ?
        ORDER BY s.priority
    """, (building_id,)).fetchall()

    evidences = []
    for row in rows:
        raw_props = None
        if row['raw_properties_json']:
            raw_props = json.loads(row['raw_properties_json'])

        evidences.append(Evidence(
            building_id=row['building_id'],
            source_id=row['source_id'],
            evidence_type=row['evidence_type'],
            min_year=row['min_year'],
            max_year=row['max_year'],
            exact_year=row['exact_year'],
            end_year=row['end_year'],
            end_year_max=row['end_year_max'],
            confidence=row['confidence'],
            confidence_reason=row['confidence_reason'],
            source_local_id=row['source_local_id'],
            method=row['method'],
            raw_properties=raw_props,
        ))

    return evidences


def get_all_evidence_for_source(
    conn: sqlite3.Connection,
    source_id: str
) -> List[Evidence]:
    """Get all evidence from a specific source."""
    rows = conn.execute("""
        SELECT * FROM evidence WHERE source_id = ?
    """, (source_id,)).fetchall()

    evidences = []
    for row in rows:
        raw_props = None
        if row['raw_properties_json']:
            raw_props = json.loads(row['raw_properties_json'])

        evidences.append(Evidence(
            building_id=row['building_id'],
            source_id=row['source_id'],
            evidence_type=row['evidence_type'],
            min_year=row['min_year'],
            max_year=row['max_year'],
            exact_year=row['exact_year'],
            end_year=row['end_year'],
            end_year_max=row['end_year_max'],
            confidence=row['confidence'],
            confidence_reason=row['confidence_reason'],
            source_local_id=row['source_local_id'],
            method=row['method'],
            raw_properties=raw_props,
        ))

    return evidences


def calculate_best_estimate(evidences: List[Evidence]) -> DateEstimate:
    """
    Combine all evidence into best estimate.

    Algorithm:
    1. If any source has exact date with high confidence, use it
    2. Otherwise, intersect all bounds (presence → max_year, absence → min_year)
    3. Only estimate if we have meaningful bounds (not just "exists now")
    4. Calculate midpoint and confidence based on range width
    """
    if not evidences:
        return DateEstimate(
            building_id="unknown",
            method="none",
            confidence=0.0
        )

    building_id = evidences[0].building_id

    # Check for exact dates first (sorted by source priority)
    for ev in evidences:
        if ev.evidence_type == 'exact' and ev.exact_year and ev.confidence >= 0.7:
            return DateEstimate(
                building_id=building_id,
                start_year=ev.exact_year,
                start_year_min=ev.exact_year,
                start_year_max=ev.exact_year,
                end_year=ev.end_year,
                confidence=ev.confidence,
                method="exact",
                contributing_sources=[ev.source_id],
                primary_source=ev.source_id,
                evidence_count=len(evidences)
            )

    # Collect all bounds
    min_year = 1700  # Earliest reasonable
    max_year = datetime.now().year
    has_temporal_evidence = False  # Track if we have real date constraints
    contributing = []

    # Track end year evidence separately
    end_year = None
    end_year_min = None
    end_year_max = None

    for ev in evidences:
        contributing.append(ev.source_id)

        if ev.evidence_type == 'presence':
            # Building existed by this year
            if ev.max_year and ev.max_year < 2020:
                # Only count as temporal evidence if from historical source
                max_year = min(max_year, ev.max_year)
                has_temporal_evidence = True

        elif ev.evidence_type == 'absence':
            # Building didn't exist yet
            if ev.min_year:
                min_year = max(min_year, ev.min_year)
                has_temporal_evidence = True

        elif ev.evidence_type == 'range':
            # Known range
            if ev.min_year:
                min_year = max(min_year, ev.min_year)
                has_temporal_evidence = True
            if ev.max_year:
                max_year = min(max_year, ev.max_year)
                has_temporal_evidence = True

        elif ev.evidence_type == 'exact' and ev.exact_year:
            # Exact but low confidence - treat as range
            min_year = max(min_year, ev.exact_year - 10)
            max_year = min(max_year, ev.exact_year + 10)
            has_temporal_evidence = True

        # Handle end year
        if ev.end_year:
            if end_year is None or ev.end_year < end_year:
                end_year = ev.end_year
        if ev.end_year_max:
            if end_year_max is None or ev.end_year_max > end_year_max:
                end_year_max = ev.end_year_max

    # If no temporal evidence, return unknown
    if not has_temporal_evidence:
        return DateEstimate(
            building_id=building_id,
            start_year=None,
            confidence=0.0,
            method="unknown",
            contributing_sources=list(set(contributing)),
            primary_source=contributing[0] if contributing else None,
            evidence_count=len(evidences)
        )

    # Validate bounds
    if min_year > max_year:
        # Contradiction in evidence - widen range
        mid = (min_year + max_year) // 2
        min_year = mid - 20
        max_year = mid + 20

    # Calculate estimate
    range_width = max_year - min_year
    estimated_year = (min_year + max_year) // 2

    # Confidence based on range width and evidence count
    if range_width == 0:
        confidence = 0.95
        method = "bounded"
    elif range_width <= 10:
        confidence = 0.85
        method = "bounded"
    elif range_width <= 30:
        confidence = 0.7
        method = "range"
    elif range_width <= 50:
        confidence = 0.5
        method = "range"
    elif range_width <= 100:
        confidence = 0.35
        method = "estimated"
    else:
        confidence = 0.2
        method = "estimated"

    # Boost confidence based on evidence count
    evidence_boost = min(0.1, len(evidences) * 0.02)
    confidence = min(0.95, confidence + evidence_boost)

    return DateEstimate(
        building_id=building_id,
        start_year=estimated_year,
        start_year_min=min_year,
        start_year_max=max_year,
        end_year=end_year,
        end_year_min=end_year_min if end_year else None,
        end_year_max=end_year_max if end_year else None,
        confidence=round(confidence, 3),
        method=method,
        contributing_sources=list(set(contributing)),
        primary_source=contributing[0] if contributing else None,
        evidence_count=len(evidences)
    )


def save_estimate(conn: sqlite3.Connection, estimate: DateEstimate) -> None:
    """Save computed estimate to database."""
    conn.execute("""
        INSERT INTO estimates
        (building_id, start_year, start_year_min, start_year_max,
         end_year, end_year_min, end_year_max,
         confidence, method, contributing_sources, primary_source, evidence_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(building_id) DO UPDATE SET
            start_year = excluded.start_year,
            start_year_min = excluded.start_year_min,
            start_year_max = excluded.start_year_max,
            end_year = excluded.end_year,
            end_year_min = excluded.end_year_min,
            end_year_max = excluded.end_year_max,
            confidence = excluded.confidence,
            method = excluded.method,
            contributing_sources = excluded.contributing_sources,
            primary_source = excluded.primary_source,
            evidence_count = excluded.evidence_count,
            calculated_at = CURRENT_TIMESTAMP
    """, (
        estimate.building_id,
        estimate.start_year,
        estimate.start_year_min,
        estimate.start_year_max,
        estimate.end_year,
        estimate.end_year_min,
        estimate.end_year_max,
        estimate.confidence,
        estimate.method,
        json.dumps(estimate.contributing_sources),
        estimate.primary_source,
        estimate.evidence_count
    ))

    # Also update denormalized fields on building
    conn.execute("""
        UPDATE buildings
        SET est_start_year = ?,
            est_end_year = ?,
            est_confidence = ?,
            est_method = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE building_id = ?
    """, (
        estimate.start_year,
        estimate.end_year,
        estimate.confidence,
        estimate.method,
        estimate.building_id
    ))


def update_all_estimates(conn: sqlite3.Connection, batch_size: int = 1000) -> int:
    """Recalculate estimates for all buildings with evidence."""

    # Get all buildings with evidence
    building_ids = conn.execute("""
        SELECT DISTINCT building_id FROM evidence
    """).fetchall()

    count = 0
    for (building_id,) in building_ids:
        evidences = get_evidence_for_building(conn, building_id)
        if evidences:
            estimate = calculate_best_estimate(evidences)
            save_estimate(conn, estimate)
            count += 1

            if count % batch_size == 0:
                conn.commit()
                print(f"  Processed {count} buildings...")

    conn.commit()
    return count


def get_estimate(conn: sqlite3.Connection, building_id: str) -> Optional[DateEstimate]:
    """Get computed estimate for a building."""
    row = conn.execute("""
        SELECT * FROM estimates WHERE building_id = ?
    """, (building_id,)).fetchone()

    if not row:
        return None

    contributing = []
    if row['contributing_sources']:
        contributing = json.loads(row['contributing_sources'])

    return DateEstimate(
        building_id=row['building_id'],
        start_year=row['start_year'],
        start_year_min=row['start_year_min'],
        start_year_max=row['start_year_max'],
        end_year=row['end_year'],
        end_year_min=row['end_year_min'],
        end_year_max=row['end_year_max'],
        confidence=row['confidence'],
        method=row['method'],
        contributing_sources=contributing,
        primary_source=row['primary_source'],
        evidence_count=row['evidence_count']
    )
