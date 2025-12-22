# Feature: Dual-Mode Source Selection UI

## Overview

The source filter UI is redesigned to distinguish between two fundamentally different data source types, providing clearer mental models and more intuitive filtering behavior.

## Problem Statement

The current UI treats all sources identically, but they have fundamentally different semantics:

- **Registry sources** (SEFRAK, Matrikkelen, etc.) provide specific construction years
- **ML snapshot sources** (kv1880, kv1904, air1947) represent "what existed at a point in time"

Mixing these in one list creates confusion about how the timeline slider affects visibility.

## Solution

Split the source filter into two distinct sections:

### Type A: Date Sources (Timeline-Aware)

Sources that provide construction dates. Buildings appear when the timeline slider reaches their `sd` (start date).

| Source | Code | Description |
|--------|------|-------------|
| SEFRAK | `sef` | Norwegian cultural heritage registry (pre-1900) |
| Matrikkelen | `mat` | Official property cadastre |
| Trondheim Kommune | `tk` | Municipal records |
| Manual | `man` | Researcher-verified entries |
| Finn.no | `finn` | Property listings with construction dates |
| OpenStreetMap | `osm` | Community-sourced (often undated) |

**Behavior**:
- Multiple sources can be active (checkboxes)
- Timeline slider filters: show building if `sd <= selectedYear`
- Buildings from all active sources are combined

### Type B: Historical Snapshots (Static)

ML-detected features from historical maps. Shows what existed at that specific point in time, regardless of the timeline slider.

| Source | Code | Year | Description |
|--------|------|------|-------------|
| Kartverket 1880 | `kv1880` | 1880 | ML extraction from 1880 map |
| Kartverket 1904 | `kv1904` | 1904 | ML extraction from 1904 map |
| Aerial 1947 | `air1947` | 1947 | ML extraction from aerial photos |

**Behavior**:
- Multiple snapshots can be active (checkboxes)
- Timeline slider does NOT affect visibility
- All detected buildings are shown when source is active
- Can be overlaid on top of dated buildings

## UI Design

```
┌─────────────────────────────────────┐
│ 📅 Date Sources                    │
│ ─────────────────────────────────  │
│ Buildings appear when the timeline │
│ reaches their construction year.   │
│                                    │
│ [All] [None]                       │
│                                    │
│ ☑ SEFRAK (registry)        [1,234] │
│ ☑ Matrikkelen (official)     [567] │
│ ☑ Trondheim Kommune          [890] │
│ ☑ Manual (verified)           [45] │
│ ☑ Finn.no listings           [234] │
│ ☑ OpenStreetMap            [5,678] │
└────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 📷 Historical Snapshots            │
│ ─────────────────────────────────  │
│ ML-detected from historical maps.  │
│ Shows all buildings from that era. │
│                                    │
│ [All] [None]                       │
│                                    │
│ ☑ Kartverket 1880            [260] │
│ ☐ Kartverket 1904            [TBD] │
│ ☐ Aerial 1947                [TBD] │
└────────────────────────────────────┘
```

## Filter Logic

### Type A Filter (Date Sources)

```javascript
// Show if source is active AND timeline allows
['all',
  ['any',
    ['==', ['get', 'src'], 'sef'],  // if SEFRAK enabled
    ['==', ['get', 'src'], 'mat'],  // if Matrikkelen enabled
    // ... other active sources
  ],
  ['<=', ['get', 'sd'], selectedYear]  // timeline filter
]
```

### Type B Filter (Snapshot Sources)

```javascript
// Show if ml_src is active (no timeline filter)
['any',
  ['==', ['get', 'ml_src'], 'kv1880'],  // if 1880 enabled
  ['==', ['get', 'ml_src'], 'kv1904'],  // if 1904 enabled
  // ... other active snapshots
]
```

### Combined Filter

```javascript
['any',
  typeAFilter,  // Dated buildings matching timeline
  typeBFilter   // Snapshot buildings (always if enabled)
]
```

## Visual Differentiation

To help users distinguish snapshot buildings from dated buildings:

- **Dated buildings**: Solid fill, normal opacity
- **Snapshot buildings**: Slightly different opacity or outline style

## Acceptance Criteria

1. [ ] Two distinct panels for Date Sources and Historical Snapshots
2. [ ] Type A sources respond to timeline slider
3. [ ] Type B sources show all buildings regardless of timeline
4. [ ] Both panels have All/None quick actions
5. [ ] Counts are displayed for each source
6. [ ] Clear explanatory text in each section
7. [ ] No regression in existing functionality

## Navigation & Deep Linking

Each snapshot source includes navigation links:

- **View Details** → Opens `source_viewer.html?source=<id>` for detailed inspection
- **Inspect** → Enters inspection mode overlay on current map
- **URL params** → `index.html?snapshot=kv1880` enables that snapshot on load

Bidirectional navigation allows seamless movement between main map, source viewer, and inspection mode.

## Future Considerations

- Radio button mode for snapshots (compare one at a time)
- Snapshot opacity slider
- Diff view (what changed between snapshots)
- Timeline markers showing snapshot years
