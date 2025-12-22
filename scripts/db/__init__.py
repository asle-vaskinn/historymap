"""
Database module for building date evidence tracking.

Provides SQLite-based storage for:
- Building records from multiple sources
- Date evidence from each source
- Computed date estimates with confidence
"""

from .schema import init_db, get_connection
from .evidence import (
    add_evidence,
    get_evidence_for_building,
    get_all_evidence_for_source,
    calculate_best_estimate,
    update_all_estimates,
)
from .buildings import (
    upsert_building,
    get_building,
    get_buildings_with_estimates,
)
