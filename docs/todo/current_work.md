# Current Work

No active work. Run `/propose` to start a new task.

---

## Archive

### Multi-Source Date Merging with Geometry Selection (2025-12-20) - IMPLEMENTED

Implemented date-aware merge strategy for construction years (`sd`) from SEFRAK, FINN, and MANUAL sources with priority: MANUAL → FINN → SEFRAK. Added osm_ref matching for FINN (56 matches), geometry selection preferring OSM polygons, and cluster schema placeholders.

**Files changed:**
- `data/merged/merge_config.json` - Added FINN source with date_priority
- `scripts/merge/merge_sources.py` - osm_ref matching, date priority resolution
- `docs/tech/DATA_SCHEMA.md` - Date priority rules, cluster fields

### Visual Feedback for Annotated Buildings (2025-12-20) - IMPLEMENTED

Add visual feedback for annotated buildings in the source viewer.

### Unified Filter UI with Collapsible Sections (2025-12-20) - IMPLEMENTED

Replace Buildings/Roads tabs with collapsible sections in main map UI.

### Link Main UI, Source Viewer, and Inspection Mode (2025-12-20) - IMPLEMENTED

Navigation and deep-linking between views.

### Dual-Mode Source Selection UI (2025-12-20) - IMPLEMENTED

Type A (Date Sources) and Type B (Historical Snapshots) panels.
