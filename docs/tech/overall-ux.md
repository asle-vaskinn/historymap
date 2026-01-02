# Overall UX Workflow

## Status: DRAFT
## Date: 2025-12-23

---

## Overview

This document describes the overall workflow for creating temporal historical maps. The workflow is designed to be:

- **Iterative** - Start with one source, add more, refine as you go
- **Interactive** - Manual touchpoints at each stage, not fully automated
- **City-agnostic** - In principle applicable to any city, though Trondheim is the reference implementation

---

## Two-Track Model

The project has two parallel tracks:

### 1. Operator Workflow (Data Preparation)

Tools for ingesting, aligning, verifying, and merging data. These are **not end-user features** but internal tools for preparing the map.

### 2. End User Product (Timeline Map)

The final output: a simple map with a timeline slider that shows how the city looked at different points in history.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        OPERATOR WORKFLOW                                 │
│  (Preparing data for a city)                                            │
│                                                                          │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐             │
│  │  INGEST  │ → │  ALIGN   │ → │  VERIFY  │ → │  MERGE   │             │
│  │          │   │          │   │          │   │          │             │
│  │ • WMS    │   │ • OSM    │   │ • Data   │   │ • Config │             │
│  │ • APIs   │   │   match  │   │   Prep   │   │ • Merge  │             │
│  │ • Files  │   │ • TPS/   │   │   Tool   │   │   rules  │             │
│  │          │   │   Affine │   │          │   │          │             │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘             │
│       ↓              ↓              ↓              ↓                    │
│  raw/*.json    *_aligned.json   verified.json  merged.geojson          │
│                                                      ↓                  │
│                                               ┌──────────┐             │
│                                               │  EXPORT  │             │
│                                               │ PMTiles  │             │
│                                               └──────────┘             │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                         END USER PRODUCT                                 │
│  (Public-facing timeline map)                                           │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │                     TIMELINE MAP                                │    │
│  │  ┌──────────────────────────────────────────────────────────┐  │    │
│  │  │                                                          │  │    │
│  │  │                    [MAP VIEW]                            │  │    │
│  │  │                                                          │  │    │
│  │  └──────────────────────────────────────────────────────────┘  │    │
│  │  < 1880 ════════════════●════════════════════════════ 2024 >  │    │
│  │         [Filters: Buildings] [Roads] [Water]                  │    │
│  └────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Iterative Source-by-Source Approach

Each data source is an iteration. Start simple, add layers, refine previous work, repeat.

```
ITERATION 1: OSM (baseline)
════════════════════════════
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
│ Ingest  │ → │Normalize│ → │  Merge  │ → │   MAP   │
│   OSM   │   │         │   │ (solo)  │   │  v0.1   │
└─────────┘   └─────────┘   └─────────┘   └─────────┘
                                              ↓
                                         Review: "Works, but
                                         no historical dates"

ITERATION 2: + SEFRAK (heritage dates)
══════════════════════════════════════
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
│ Ingest  │ → │Normalize│ → │  Merge  │ → │   MAP   │
│ SEFRAK  │   │ + dates │   │ OSM+SEF │   │  v0.2   │
└─────────┘   └─────────┘   └─────────┘   └─────────┘
                                              ↓
                                         Review: "Old buildings
                                         have dates, but missing
                                         demolished ones"

ITERATION 3: + ML 1937 (historical evidence)
════════════════════════════════════════════
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌────────┐
│ Ingest  │ → │Normalize│ → │  ALIGN  │ → │ VERIFY  │ → │  Merge │
│ ML 1937 │   │         │   │ to OSM  │   │ DataPrep│   │        │
└─────────┘   └─────────┘   └─────────┘   └─────────┘   └────────┘
                                                             ↓
                                                        ┌─────────┐
                                                        │   MAP   │
                                                        │  v0.3   │
                                                        └─────────┘
                                                             ↓
                                         Review: "Can see 1937!
                                         But alignment off in
                                         some areas"
                                              ↓
                                         GO BACK: Improve alignment

ITERATION 4: + Water (fills over time)
══════════════════════════════════════
...

ITERATION 5: + Roads (temporal network)
═══════════════════════════════════════
...

ITERATION N: + Matrikkelen, + Finn, + Kommune archives...
═════════════════════════════════════════════════════════
...
```

---

## The Feedback Loop

```
     ┌──────────────────────────────────────────┐
     │                                          │
     ▼                                          │
┌─────────┐    ┌─────────┐    ┌─────────┐      │
│  ADD    │ →  │  BUILD  │ →  │ REVIEW  │ ─────┘
│ SOURCE  │    │   MAP   │    │   MAP   │
└─────────┘    └─────────┘    └─────────┘
                                   │
                                   ▼
                         "What's wrong/missing?"
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
              ┌─────────┐   ┌─────────┐   ┌─────────┐
              │ Fix     │   │ Add new │   │ Improve │
              │ current │   │ source  │   │ tooling │
              │ source  │   │         │   │         │
              └─────────┘   └─────────┘   └─────────┘
```

Each review answers: **"What's the biggest gap?"**

| Gap | Action |
|-----|--------|
| Missing dates | Add source with dates |
| Wrong positions | Improve alignment |
| Can't verify | Improve Data Prep Tool |
| Missing features | Add roads/water/etc. |

---

## Interactive Workflow Steps

### Step 1: Gather Sources

**Manual research**: Identify what data exists for this city

- Historical maps (WMS endpoints?)
- SEFRAK coverage (heritage buildings)
- Local archives (kommune orthophotos?)
- Property listings (finn.no, etc.)

**Output**: List of sources to ingest

### Step 2: Ingest Raw Data

**Tool**: `scripts/ingest/*.py`

- Run ingestors for each source
- May need to write new ingestor for city-specific source

**Output**: `data/sources/{source}/raw/*.geojson`

### Step 3: Normalize to Schema

**Tool**: `scripts/normalize/*.py`

- Convert to common schema (sd, ed, ev, src)
- Extract dates, assign evidence levels

**Output**: `data/sources/{source}/normalized/*.geojson`

### Step 4: Align ML Sources (if applicable)

**Tool**: `scripts/align_to_osm.py`

- Match ML-detected buildings to OSM
- Fit spatial transform (affine/TPS)
- Review RMSE, adjust parameters

**Output**: `*_aligned.geojson` + `alignment_report.json`

### Step 5: Verify & Annotate

**Tool**: Data Prep Tool (`frontend/data_prep.html`)

- Toggle layers: OSM buildings, ML buildings, historical WMS
- Annotate: "this building existed/didn't exist in 1937"
- Trace water fills, road alignments
- Export annotations for training or manual corrections

**Output**: Verified/annotated data, training feedback

### Step 6: Merge Sources

**Tool**: `scripts/merge/merge_sources.py`

- Configure source priorities
- Spatial matching, conflict resolution
- Replacement detection

**Output**: `data/merged/buildings_merged.geojson`

### Step 7: Build & Deploy

**Tool**: `./build.sh` + docker compose

- Generate PMTiles
- Deploy to server

**Output**: THE MAP (`frontend/index.html` with timeline)

### Step 8: Iterate

- Review map, find issues
- Go back to Step 5 (verify/annotate) or Step 2 (new source)
- Refine until quality is good

**Output**: Improved map, documented learnings

---

## Tools Summary

| Tool | File | Purpose |
|------|------|---------|
| **Data Prep Tool** | `frontend/data_prep.html` + `data_prep/` | Verify, annotate, compare layers, water tracing |
| **Alignment Tool** | `scripts/align_to_osm.py` | Fix georeferencing (IoU matching, TPS/TIN) |
| **Timeline Map** | `frontend/index.html` | End-user product |
| **Build Pipeline** | `build.sh` | Generate deployable assets |

### Data Prep Tool Modules

| Module | Purpose |
|--------|---------|
| `data_prep/core.js` | Config, state, initialization |
| `data_prep/layers.js` | Map layer management, overlays |
| `data_prep/buildings.js` | Building annotation workflow |
| `data_prep/water.js` | Water tracing workflow |
| `data_prep/ml_pipeline.js` | ML training jobs, alignment, WebSocket |

### Data Prep Tool Features

| Feature | Description |
|---------|-------------|
| Data Overlays | Toggle merged buildings/roads/water on any source |
| Georeferencing Alignment | TPS/TIN/Affine alignment with UI controls |
| Water Editor | Draw and edit historical water features |
| Building Annotations | Mark buildings as existed/not existed |
| ML Pipeline | Training data generation, model training, verification |

---

## Current Status (Trondheim)

| Iteration | Source | Status | Notes |
|-----------|--------|--------|-------|
| 1 | OSM | Done | Baseline buildings & roads |
| 2 | SEFRAK | Done | ~1,900 heritage buildings with dates |
| 3 | ML ortofoto1937 | Done | Alignment script complete, verification UI ready |
| 4 | Water | In progress | Tooling done, manual tracing needed |
| 5 | ML kartverket 1880 | Partial | Roads extracted, buildings need work |
| 6 | Roads temporal | Done | Inferred from ML + buildings |
| - | Matrikkelen | Not started | Would add modern construction dates |
| - | Finn.no | Not started | Would add property listing dates |

---

## City-Agnostic Design Principles

While Trondheim is the reference implementation, the workflow is designed to work for other cities:

### What's Generic (Reusable)

- OSM ingestor (any city)
- SEFRAK ingestor (any Norwegian city with coverage)
- Data schema (sd, ed, ev, src)
- Data Prep Tool (layer comparison, annotation)
- Alignment Tool (OSM-based georeferencing)
- Merge pipeline (config-driven)
- Timeline Map (data-driven visualization)

### What's City-Specific

- Historical map WMS endpoints
- Local archive sources (kommune orthophotos)
- Specific SEFRAK coverage area
- Merge priority configuration
- Map bounds and center point

### Configuration Approach

Keep loose for now. Don't over-engineer city abstraction until there's a second city to implement. Current Trondheim config is embedded in scripts and can be extracted when needed.

---

## Next Actions

1. ~~Rename `source_viewer.*` → `data_prep.*`~~ DONE - Refactored to modular `data_prep/` structure
2. ~~Water tooling~~ DONE - Ready for manual tracing
3. Continue water tracing (Brattøra, Nedre Elvehavn, etc.)
4. Update this document as workflow evolves

---

## Related Documents

- `docs/tech/DATA_SCHEMA.md` - Field definitions for buildings, roads, water
- `docs/tech/DATA_PIPELINE.md` - Technical pipeline implementation
- `docs/todo/current_work.md` - Current iteration tasks
