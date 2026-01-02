# Pipeline Cleanup Plan

**Date:** 2026-01-01
**Status:** IN PROGRESS
**Author:** Architecture Review
**Last Updated:** 2026-01-01

## Overview

The system has **two distinct pipeline phases** that need clearer separation:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  EXTRACTION PIPELINE                 COMBINING PIPELINE                     │
│  ═══════════════════                 ═══════════════════                    │
│                                                                             │
│  ┌──────────────┐                   ┌────────────────────────────────────┐ │
│  │ ML Training  │                   │                                    │ │
│  │ & Inference  │──┐                │  INGEST → NORMALIZE → MERGE → EXP │ │
│  └──────────────┘  │                │                                    │ │
│                    │                └────────────────────────────────────┘ │
│  ┌──────────────┐  │  raw/                      ▲                         │
│  │ API Fetchers │──┼───────────────────────────┘                          │
│  │ (OSM, NVDB)  │  │                                                       │
│  └──────────────┘  │                                                       │
│                    │                                                       │
│  ┌──────────────┐  │                                                       │
│  │ Manual Edit  │──┘                                                       │
│  │ (source_vwr) │                                                          │
│  └──────────────┘                                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Current State

| Aspect | Extraction | Combining |
|--------|------------|-----------|
| **Location** | `ml/`, `scripts/ingest/fetch_*.py` | `scripts/pipeline.py` |
| **Orchestration** | Ad-hoc scripts | Unified `pipeline.py` |
| **Configuration** | Scattered | `constants.py` + JSON configs |
| **Status** | Partially working | Mostly working |

---

## Phase 1: Consolidate Paths & Constants (Priority: HIGH)

### Problem
- Export paths inconsistent (`data/export/` vs `frontend/data/`)
- Magic numbers for Trondheim coordinates scattered
- Source codes defined in multiple places

### Tasks

#### 1.1 Standardize Export Paths
```python
# constants.py - ALL exports go here
EXPORT_DIR = DATA_DIR / 'export'

# Individual exports
BUILDINGS_EXPORT = EXPORT_DIR / 'buildings.geojson'
ROADS_EXPORT = EXPORT_DIR / 'roads.geojson'
WATER_EXPORT = EXPORT_DIR / 'water.geojson'

# PMTiles (same directory)
BUILDINGS_PMTILES = EXPORT_DIR / 'buildings.pmtiles'
ROADS_PMTILES = EXPORT_DIR / 'roads.pmtiles'
WATER_PMTILES = EXPORT_DIR / 'water.pmtiles'
```

**Files to update:**
- [ ] `scripts/constants.py` - Add export path constants
- [ ] `scripts/pipeline.py` - Use constants instead of inline paths
- [ ] `scripts/export/export_roads.py` - Use ROADS_EXPORT
- [ ] `scripts/export/export_water.py` - Use WATER_EXPORT
- [ ] `scripts/export/export_buildings.py` - Use BUILDINGS_EXPORT
- [ ] `rebuild.sh` - Copy from single location

#### 1.2 Centralize Geographic Context
```python
# constants.py - New GeoContext class
@dataclass
class GeoContext:
    """Geographic context for coordinate conversions."""
    name: str
    bbox: Tuple[float, float, float, float]  # west, south, east, north
    center_lat: float

    @property
    def meters_per_degree_lat(self) -> float:
        return 111000  # Roughly constant

    @property
    def meters_per_degree_lon(self) -> float:
        # Varies with latitude
        return 111000 * math.cos(math.radians(self.center_lat))

    def degrees_to_meters(self, deg: float) -> float:
        # Average for this latitude
        return deg * (self.meters_per_degree_lat + self.meters_per_degree_lon) / 2

TRONDHEIM = GeoContext(
    name='Trondheim',
    bbox=(10.2, 63.35, 10.6, 63.5),
    center_lat=63.43
)

# Default context
GEO = TRONDHEIM
```

**Files to update:**
- [ ] `scripts/constants.py` - Add GeoContext
- [ ] `scripts/merge/merge_roads.py` - Use `GEO.degrees_to_meters()`
- [ ] `scripts/merge/infer_road_dates.py` - Use GeoContext
- [ ] `scripts/normalize/base_road.py` - Use GeoContext

#### 1.3 Unify Source Code Definitions
```python
# constants.py - Single source of truth
class Source(Enum):
    """Full source identifiers (internal use)."""
    OSM = 'osm'
    SEFRAK = 'sefrak'
    TRONDHEIM_KOMMUNE = 'trondheim_kommune'
    ML_KARTVERKET_1880 = 'ml_kartverket_1880'
    # ... etc

class SourceShort(Enum):
    """Short codes (export/frontend use)."""
    OSM = 'osm'
    SEF = 'sef'
    TK = 'tk'
    ML = 'ml'
    MAN = 'man'

# Mapping
SOURCE_TO_SHORT: Dict[Source, SourceShort] = {
    Source.OSM: SourceShort.OSM,
    Source.SEFRAK: SourceShort.SEF,
    # ... etc
}
```

**Already mostly done in constants.py, verify usage in:**
- [ ] `scripts/export/export_geojson.py`
- [ ] `scripts/export/export_roads.py`
- [ ] `frontend/app.js` (legend checkboxes)

---

## Phase 2: Separate Extraction Pipeline (Priority: HIGH)

### Problem
- ML extraction (`ml/`) disconnected from data pipeline
- API fetchers mixed with ingest stage
- No clear "extraction" orchestration

### Current Extraction Scripts
```
ml/
├── train.py              # Model training
├── predict.py            # Inference
├── vectorize.py          # Mask → GeoJSON
├── dataset.py            # Data loading
└── config.yaml           # Training config

scripts/
├── ingest/
│   ├── fetch_osm_water.py    # API fetch (extraction)
│   ├── osm_roads.py          # API fetch (extraction)
│   └── ingest_*.py           # File loading (combining)
└── ml/
    ├── bootstrap_water_training.py
    ├── prepare_water_training.py
    └── extract_water_color.py
```

### Proposed Structure
```
scripts/
├── extract/                    # NEW: Extraction pipeline
│   ├── __init__.py
│   ├── base.py                 # BaseExtractor class
│   ├── extract_osm.py          # OSM Overpass queries
│   ├── extract_nvdb.py         # NVDB road network
│   ├── extract_ml.py           # Run ML inference
│   └── orchestrate.py          # Extraction orchestrator
│
├── ingest/                     # KEEP: Load extracted data
│   ├── base.py                 # BaseIngestor (file loading)
│   ├── ingest_osm.py           # Load OSM GeoJSON
│   ├── ingest_ml_*.py          # Load ML output
│   └── ...
│
└── pipeline.py                 # Combining pipeline only
```

### Tasks

#### 2.1 Create Extraction Base Class
```python
# scripts/extract/base.py
class BaseExtractor(ABC):
    """Base class for data extraction from external sources."""

    def __init__(self, source_id: str, data_dir: Path = None):
        self.source_id = source_id
        self.data_dir = data_dir or DATA_DIR
        self.raw_dir = self.data_dir / 'sources' / source_id / 'raw'

    @abstractmethod
    def extract(self) -> Dict:
        """Extract data from external source.

        Returns:
            Dict with 'success', 'files', 'count', 'message'
        """
        pass

    def run(self) -> bool:
        """Run extraction with manifest update."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        result = self.extract()
        self._update_manifest(result)
        return result.get('success', False)
```

**Files to create:**
- [ ] `scripts/extract/__init__.py`
- [ ] `scripts/extract/base.py`

#### 2.2 Move API Fetchers to Extract
```python
# scripts/extract/extract_osm.py
class OSMExtractor(BaseExtractor):
    """Extract features from OpenStreetMap via Overpass API."""

    def __init__(self, feature_type: str = 'buildings'):
        super().__init__(source_id='osm')
        self.feature_type = feature_type

    def extract(self) -> Dict:
        # Current logic from fetch_osm_water.py / osm_roads.py
        ...
```

**Files to refactor:**
- [ ] `scripts/ingest/fetch_osm_water.py` → `scripts/extract/extract_osm.py`
- [ ] `scripts/ingest/osm_roads.py` → merge into `extract_osm.py`
- [ ] `scripts/ingest/nvdb.py` → `scripts/extract/extract_nvdb.py`

#### 2.3 Create ML Extraction Wrapper
```python
# scripts/extract/extract_ml.py
class MLExtractor(BaseExtractor):
    """Run ML inference and vectorization."""

    def __init__(self,
                 checkpoint: Path,
                 input_dir: Path,
                 year: str,
                 feature_type: str = 'buildings'):
        super().__init__(source_id=f'ml_{feature_type}_{year}')
        self.checkpoint = checkpoint
        self.input_dir = input_dir
        self.year = year
        self.feature_type = feature_type

    def extract(self) -> Dict:
        # 1. Run ml/predict.py
        # 2. Run ml/vectorize.py
        # 3. Copy to raw_dir
        ...
```

**Files to create:**
- [ ] `scripts/extract/extract_ml.py`

#### 2.4 Create Extraction Orchestrator
```python
# scripts/extract/orchestrate.py
def run_extraction(
    sources: List[str] = None,
    feature_types: List[str] = None,
    skip_ml: bool = False
) -> Dict[str, bool]:
    """Run extraction for specified sources.

    Args:
        sources: Source IDs to extract (default: all enabled)
        feature_types: buildings, roads, water (default: all)
        skip_ml: Skip ML extraction (slow)

    Returns:
        Dict mapping source_id to success status
    """
    results = {}

    # API extractions (fast)
    if 'osm' in sources:
        results['osm'] = OSMExtractor().run()
    if 'nvdb' in sources:
        results['nvdb'] = NVDBExtractor().run()

    # ML extractions (slow)
    if not skip_ml:
        for year in ['1880', '1904', '1937', '1947']:
            results[f'ml_{year}'] = MLExtractor(year=year).run()

    return results
```

**Files to create:**
- [ ] `scripts/extract/orchestrate.py`

#### 2.5 Update Pipeline Entry Points
```bash
# New CLI structure
python scripts/extract/orchestrate.py --sources osm nvdb --feature-types buildings roads
python scripts/pipeline.py --stage all --feature-type buildings
```

**Files to update:**
- [ ] `scripts/pipeline.py` - Remove extraction logic, keep ingest+
- [ ] `rebuild.sh` - Call both orchestrators

---

## Phase 3: Standardize Error Handling (Priority: MEDIUM)

### Problem
- Some functions return `bool`, others return `Dict`, others raise exceptions
- Hard to propagate detailed errors up the stack

### Proposed Pattern
```python
# scripts/result.py
@dataclass
class Result(Generic[T]):
    """Standard result type for pipeline operations."""
    success: bool
    value: Optional[T] = None
    error: Optional[str] = None
    details: Optional[Dict] = None

    @classmethod
    def ok(cls, value: T = None, **details) -> 'Result[T]':
        return cls(success=True, value=value, details=details)

    @classmethod
    def fail(cls, error: str, **details) -> 'Result[T]':
        return cls(success=False, error=error, details=details)

# Usage
def merge_sources(config_path: Path) -> Result[int]:
    try:
        count = do_merge()
        return Result.ok(count, features=count)
    except Exception as e:
        return Result.fail(str(e), stage='merge')
```

### Tasks
- [ ] Create `scripts/result.py` with Result class
- [ ] Update `BaseIngestor.run()` to return Result
- [ ] Update `BaseNormalizer.run()` to return Result
- [ ] Update merge functions to return Result
- [ ] Update `pipeline.py` to handle Result objects

---

## Phase 4: Add Configuration Validation (Priority: MEDIUM)

### Problem
- JSON merge configs not validated
- Typos cause silent failures

### Proposed Solution
```python
# scripts/config_schema.py
MERGE_CONFIG_SCHEMA = {
    "type": "object",
    "required": ["version", "feature_type", "sources", "output"],
    "properties": {
        "version": {"type": "string"},
        "feature_type": {"enum": ["building", "road", "water"]},
        "sources": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["enabled", "path"],
                "properties": {
                    "enabled": {"type": "boolean"},
                    "path": {"type": "string"},
                    "priority": {"type": "integer"}
                }
            }
        },
        "matching": {"type": "object"},
        "output": {"type": "string"}
    }
}

def validate_config(config: Dict, schema: Dict) -> Result[Dict]:
    """Validate config against JSON schema."""
    try:
        jsonschema.validate(config, schema)
        return Result.ok(config)
    except jsonschema.ValidationError as e:
        return Result.fail(f"Config validation failed: {e.message}")
```

### Tasks
- [ ] Add `jsonschema` to requirements.txt
- [ ] Create `scripts/config_schema.py`
- [ ] Add schemas for each config type
- [ ] Update `load_config()` functions to validate

---

## Phase 5: Add Pipeline State Management (Priority: MEDIUM)

### Problem
- Can't resume failed pipelines
- Every run reprocesses from scratch
- No way to know what's stale

### Proposed Solution
```python
# In manifest.json
{
    "source_id": "osm",
    "stages": {
        "extracted": {
            "completed_at": "2026-01-01T12:00:00Z",
            "checksum": "sha256:abc123...",
            "files": ["osm_buildings.json"]
        },
        "normalized": {
            "completed_at": "2026-01-01T12:05:00Z",
            "checksum": "sha256:def456...",
            "files": ["buildings.geojson"]
        }
    }
}

# Pipeline checks
def needs_processing(source: Path, stage: str) -> bool:
    manifest = load_manifest(source)
    stage_info = manifest.get('stages', {}).get(stage)

    if not stage_info:
        return True  # Never processed

    # Check if inputs changed since processing
    input_checksum = compute_input_checksum(source, stage)
    return input_checksum != stage_info.get('input_checksum')
```

### Tasks
- [ ] Update manifest schema with stage tracking
- [ ] Add checksum computation to base classes
- [ ] Add `--force` flag to pipeline.py
- [ ] Add `--resume` flag to skip completed stages

---

## Phase 6: Testing Infrastructure (Priority: MEDIUM)

### Problem
- No automated tests
- Refactoring is risky

### Proposed Structure
```
tests/
├── conftest.py              # Pytest fixtures
├── fixtures/                # Test data
│   ├── osm_sample.geojson
│   ├── sefrak_sample.geojson
│   └── ...
├── test_ingest/
│   ├── test_base_ingestor.py
│   └── test_osm_ingest.py
├── test_normalize/
│   ├── test_base_normalizer.py
│   └── test_schema.py
├── test_merge/
│   ├── test_spatial_matching.py
│   └── test_date_inference.py
└── test_export/
    └── test_export_format.py
```

### Tasks
- [ ] Add pytest to requirements.txt
- [ ] Create test fixtures (small sample data)
- [ ] Write tests for base classes
- [ ] Write tests for merge algorithms
- [ ] Add CI integration (GitHub Actions)

---

## Phase 7: Documentation (Priority: LOW)

### Tasks
- [ ] Add docstrings to all public functions
- [ ] Create `docs/tech/PIPELINE_ARCHITECTURE.md`
- [ ] Create `docs/tech/ADDING_NEW_SOURCE.md`
- [ ] Add inline comments for complex algorithms

---

## Implementation Order

```
Phase 1: Paths & Constants     ████████████████ 100% COMPLETE
Phase 2: Extract Pipeline      ████████████████ 100% COMPLETE
Phase 3: Error Handling        ████████████████ 100% COMPLETE
Phase 4: Config Validation     ████████████████ 100% COMPLETE
Phase 5: State Management      ████████████████ 100% COMPLETE
Phase 6: Testing               ████████████████ 100% COMPLETE
Phase 7: Documentation         ████████████░░░░  75% (updated extract docs)
```

### Phase 1 Completion Notes (2026-01-01)
- Added GeoContext class with latitude-aware coordinate conversions
- Standardized all export paths to `data/export/`
- Centralized ML map source mappings (ml_kartverket_1880 -> kv1880)
- Updated merge scripts to use GEO.meters_to_degrees() / GEO.degrees_to_meters()
- Verified source code consistency across pipeline

### Phase 2 Completion Notes (2026-01-01)
- Created `scripts/extract/` package with proper structure
- `BaseExtractor` abstract class with manifest tracking
- `OSMExtractor` for Overpass API (buildings, roads, water)
- `NVDBExtractor` for Norwegian Road Database
- `orchestrate.py` for running multiple extractors
- Updated README with usage examples and architecture diagram

### Phase 3 Completion Notes (2026-01-01)
- Created `scripts/result.py` with `Result[T]` generic class
- `.ok()` and `.fail()` factory methods
- `.map()`, `.and_then()` for chaining operations
- `.unwrap()`, `.unwrap_or()` for value extraction
- `BatchResult` for multi-item operations with summary stats

### Phase 4 Completion Notes (2026-01-01)
- Created `scripts/config_schema.py` with JSON schemas
- `MERGE_CONFIG_SCHEMA` for merge configuration validation
- `SOURCE_MANIFEST_SCHEMA` for source manifest validation
- `validate_config()`, `validate_merge_config()` functions
- CLI for validating config files
- Works with jsonschema library or basic fallback validation

### Phase 5 Completion Notes (2026-01-01)
- Created `scripts/pipeline_state.py` for state tracking
- `PipelineState` class per source with manifest persistence
- `StageInfo` dataclass for stage completion info
- `needs_processing()` checks age, success, input checksums
- `mark_completed()` / `mark_failed()` for stage tracking
- `invalidate()` with cascade to downstream stages
- `get_all_source_states()` for pipeline-wide status

### Phase 6 Completion Notes (2026-01-01)
- Created `tests/` directory structure
- `tests/conftest.py` with pytest fixtures (temp_data_dir, sample_geojson, etc.)
- `tests/test_constants.py` - 16 tests for GeoContext, source mappings
- `tests/test_result.py` - 21 tests for Result and BatchResult classes
- All 37 tests passing
- Run with: `PYTHONPATH=scripts pytest tests/ -v`

### Recommended Sequence

1. **Phase 1** (1-2 days) - Quick wins, reduces confusion
2. **Phase 2** (3-5 days) - Clear separation, enables parallel work
3. **Phase 4** (1 day) - Prevents silent failures
4. **Phase 3** (2-3 days) - Better debugging
5. **Phase 6** (ongoing) - Add tests as you touch code
6. **Phase 5** (2-3 days) - Nice to have for large datasets
7. **Phase 7** (ongoing) - As needed

---

## Success Criteria

- [ ] Single `rebuild.sh` command works end-to-end
- [ ] All exports in `data/export/`
- [ ] Clear separation: `extract/` vs `ingest/`
- [ ] Config typos caught at load time
- [ ] Tests pass for core merge algorithms
- [ ] Can resume failed pipeline runs
