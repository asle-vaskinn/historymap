# Product Specification

## Features

### Core Features

#### 1. Temporal Navigation
- **Year slider**: 1700-2025 range
- **Play/pause animation**: Auto-advance through years
- **Era indicator**: Shows current period context

#### 2. Building Visualization
- Buildings appear/disappear based on construction/demolition dates
- Color coding by data source and age
- Opacity reflects evidence strength

#### 3. Road Visualization
- Roads appear/disappear based on ML-detected temporal bounds
- Color coding by era and detection confidence
- Source: ML extraction from historical Kartverket maps (no authoritative registry)

**Temporal Inference (ML-based):**
- Road detected in 1880 map → existed by 1880 (not-later-than bound)
- Road absent in 1880 but present in 1904 → built between 1880-1904
- Road in historical maps but not in OSM → demolished/rerouted
- Road in OSM but not historical maps → built after last historical map

**Key Difference from Buildings:**
Buildings have authoritative sources (SEFRAK, Matrikkelen) providing exact construction dates.
Roads rely entirely on ML detection - dates are decade-level bounds, not exact values.

#### 4. Evidence Transparency
- **Confidence overlay**: Toggle to see Red→Green evidence strength
- **Legend**: Explains what colors mean
- **Era rules**: Clear explanation of filtering logic

#### 5. Source Filtering
Filter buildings and roads by data source to explore specific datasets:

**Building Sources:**
| Source | Description | Use Case |
|--------|-------------|----------|
| SEFRAK | Cultural heritage registry (pre-1900) | Historical research |
| Trondheim Kommune | Municipal records | Official data |
| AI-detected | ML extraction from historical maps | Each map source selectable |
| - Kartverket 1880 | 1880s topographic maps | Late 1800s verification |
| - Kartverket 1904 | Early 1900s maps | Turn of century |
| - Aerial 1947 | Post-war aerial photos | Mid-century reference |
| Modern (OSM) | OpenStreetMap current data | Present-day baseline |

**Road Sources (ML-only):**
| Source | Description | Use Case |
|--------|-------------|----------|
| ML Kartverket 1880 | Roads extracted from 1880s maps | Historical street layout |
| ML Kartverket 1904 | Roads extracted from 1904 maps | Early 1900s network |
| ML Aerial 1947 | Roads extracted from aerial photos | Mid-century comparison |
| Modern (OSM) | OpenStreetMap roads | Present-day baseline |

Note: Roads have no authoritative registry like SEFRAK. All historical dates are ML-inferred bounds.

**UI Elements:**
- Dropdown or checkbox list for source selection
- Multi-select enabled (show buildings from multiple sources)
- "All sources" quick toggle
- Source-specific color coding in map view
- Count of buildings per source shown

### Implementation Status

#### Phase 1 (Implemented)
- [x] Temporal navigation with year slider (1700-2025)
- [x] Building visualization with temporal filtering
- [x] Evidence transparency and confidence overlay
- [x] Source filtering (SEFRAK, Trondheim Kommune, ML-detected maps, OSM)
- [x] Era-based display rules (pre-1900, 1900-1950, post-1950)
- [x] Building replacement detection and visualization

#### Phase 2 (In Progress)
- [ ] Road temporal visualization with ML-inferred dates
- [ ] Road source filtering (ML 1880, ML 1904, ML 1947, OSM)
- [ ] Click building/road for details (source, date range, photos)
- [ ] Search by address

**Note**: Phase 2 road features are documented but implementation in progress. Building temporal features are complete.

#### Phase 3 (Future)
- [ ] Compare two years side-by-side
- [ ] User contributions (submit old photos)
- [ ] 3D building heights from historical sources
- [ ] Street-level historical photos integration

## UX Specification

### Map Interaction
- Pan/zoom with mouse or touch
- Scroll to zoom
- Double-click to zoom in

### Time Controls
- Drag slider for quick navigation
- Click specific year
- Play button for animation (adjustable speed)

### Layer Controls
- Toggle: Buildings, Roads, Water, Confidence overlay
- Each toggle clearly labeled

### Source Filter Controls
- Collapsible panel with source checkboxes
- Hierarchical structure:
  - Registry Sources (SEFRAK, Trondheim Kommune, Matrikkelen)
  - AI-Detected (expandable list of map sources)
  - Modern (OpenStreetMap)
- Visual indicator showing active filters
- Quick actions: "Select All" / "Clear All"

### Information Display
- Current year prominently shown
- Era name (e.g., "Late 1800s")
- Building count for current view

## Visual Design

### Color Palette

#### Buildings by Source
| Source | Color | Hex |
|--------|-------|-----|
| SEFRAK 1700s | Dark ochre | #8b6914 |
| SEFRAK 1800s | Medium brown | #a67c2c |
| SEFRAK 1850+ | Tan | #b89968 |
| ML-verified | Saddle brown | #8b4513 |
| Modern/Unknown | Light tan | #d4a373 |
| Demolished | Sienna (dashed) | #a0522d |

#### Roads by Era (ML-detected)
| Era | Color | Hex |
|-----|-------|-----|
| Pre-1880 (detected in 1880) | Dark slate | #4a5568 |
| 1880-1904 | Slate gray | #718096 |
| 1904-1947 | Gray | #a0aec0 |
| Post-1947/Modern | Light gray | #cbd5e0 |
| Historical only (demolished) | Dashed dark | #2d3748 |

#### Confidence Overlay
| Level | Color | Hex |
|-------|-------|-----|
| High (registry/multi-map) | Green | #00cc00 |
| Medium (single ML detection) | Yellow | #ffff00 |
| Low (OSM only, no historical) | Red | #ff4444 |

### Typography
- Clean sans-serif for UI
- High contrast for readability
- Year display: Large, bold

## Era-Based Display Rules

### Pre-1900
- **Requirement**: Strong evidence only
- **Shown**: SEFRAK buildings, ML-verified
- **Hidden**: Buildings without historical proof
- **Rationale**: Don't show modern buildings in historical view

### 1900-1950
- **Requirement**: Strong evidence OR exists in modern map
- **Shown**: Proven historical + assumed modern
- **Rationale**: Transitional period, some uncertainty acceptable

### Post-1950
- **Requirement**: None (show all)
- **Shown**: All buildings from modern OSM
- **Rationale**: These buildings exist today

## Building Replacement Logic

When a new building is constructed on the same location as an old building, the old building should disappear from the timeline.

### User Experience

1. **Sliding forward in time**: Old building visible → new building appears → old building disappears
2. **Sliding backward in time**: New building visible → old building reappears → new building disappears
3. **Visual cue**: Replaced buildings briefly flash/fade to indicate transition (optional enhancement)

### Display Rules

| Scenario | What User Sees |
|----------|----------------|
| Year < old building start | Neither building shown |
| Year >= old start AND year < replacement | Old building shown |
| Year >= replacement date | New building shown, old building hidden |

### Evidence Requirements for Replacement

| Era of Old Building | Replacement Triggered When |
|---------------------|---------------------------|
| Pre-1900 | New building has HIGH evidence of start date |
| 1900-1950 | New building has MEDIUM+ evidence |
| Post-1950 | New building exists in modern map |

### Edge Cases

- **Same footprint, different date sources**: Prefer registry dates (SEFRAK, Matrikkelen) over ML/inferred
- **Partial overlap**: If overlap < 50%, treat as separate buildings (extension, not replacement)
- **Multiple replacements**: Chain of replacements shown sequentially (A→B→C)
- **Unknown replacement date**: If new building has no date, old building remains visible until strong evidence
