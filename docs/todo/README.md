# Project TODOs

## Workflow

Use the following commands to manage work:

| Command | Purpose |
|---------|---------|
| `/propose <request>` | Start new work - analyze and propose changes |
| `/implement` | Execute approved work using agents |
| `/test` | Run tests and fix failures |
| `/sync` | Ensure docs match code |

**Current work** is tracked in: `current_work.md`

---

## Implementation Tasks

### High Priority

#### Data Pipeline
- [ ] **Fine-tune ML model on real historical maps**
  - Current model trained on synthetic tiles has domain gap
  - Need labeled samples from actual Kartverket 1880s maps
  - Target: Improve building detection accuracy

- [ ] **Add more historical map sources**
  - [ ] 1920s maps (if available from Kartverket)
  - [ ] 1950s aerial photos (requires norgeibilder.no access)
  - [ ] 1980s aerial photos
  - [ ] Cross-reference dates across eras

- [ ] **Integrate Matrikkelen API**
  - Official property registry has construction dates
  - Would provide high-evidence dates for modern buildings
  - API documentation: [Matrikkelen API](https://kartkatalog.geonorge.no/)

#### Frontend
- [ ] **Source filter UI**
  - Filter buildings by data source (SEFRAK, Trondheim Kommune, ML, OSM)
  - Hierarchical checkbox list with expandable ML sub-sources
  - Show count of buildings per source
  - "Select All" / "Clear All" quick actions

- [ ] **Building click details panel**
  - Show source, date, evidence level
  - Link to SEFRAK registry if applicable
  - Show historical photos if available

- [ ] **Address search**
  - Geocoding integration
  - Fly-to location on search

- [ ] **Side-by-side comparison mode**
  - Compare two years simultaneously
  - Sync pan/zoom between views

### Medium Priority

#### Data Quality
- [ ] **Building replacement logic**
  - When new building replaces old, hide the old one
  - Detect overlapping footprints with different dates
  - Requires spatial analysis in processing pipeline

- [ ] **Improve demolished building detection**
  - Currently only comparing ML 1880 vs modern OSM
  - Need intermediate time points

- [ ] **Validate SEFRAK data**
  - Cross-reference with other sources
  - Flag inconsistencies

#### Performance
- [ ] **Convert to PMTiles**
  - Current: GeoJSON (~19MB)
  - Target: Streaming vector tiles
  - Expected improvement: <500ms initial load

- [ ] **Tile-based data loading**
  - Only load visible area
  - Progressive detail at zoom levels

### Low Priority

#### Features
- [ ] **User contributions**
  - Submit old photos
  - Suggest date corrections
  - Community verification

- [ ] **3D building heights**
  - Extract from historical sources
  - Extrude buildings in MapLibre

- [ ] **Street-level historical photos**
  - Integration with digitaltmuseum.no
  - Mapillary historical imagery

#### Infrastructure
- [ ] **Set up CI/CD**
  - GitHub Actions for deployment
  - Automated testing
  - Data validation pipeline

- [ ] **Docker containerization**
  - Reproducible builds
  - Easy deployment

## Specification Tasks

- [ ] **Define detailed UX flows**
  - Mobile interaction patterns
  - Accessibility requirements
  - Keyboard navigation

- [ ] **Color palette refinement**
  - User testing for color blindness
  - High contrast mode

- [ ] **Localization**
  - Norwegian translations
  - Multilingual support structure

## Architecture Updates

- [ ] **Data schema versioning**
  - Handle schema migrations
  - Backwards compatibility

- [ ] **Caching strategy**
  - Service worker for offline
  - CDN for static assets

- [ ] **API design** (future)
  - REST endpoints for building queries
  - GraphQL for complex queries

## Completed

- [x] Basic frontend with MapLibre GL JS
- [x] PMTiles integration for OSM base map
- [x] Year slider with animation
- [x] Era-based filtering logic
- [x] Evidence strength model (h/m/l)
- [x] Confidence overlay (Red→Yellow→Green)
- [x] SEFRAK data integration
- [x] ML model training pipeline
- [x] 1880 map building extraction (263 buildings)
- [x] Building comparison script
- [x] Documentation structure (need/spec/tech/todo)

## Notes

### Evidence Model
Current implementation uses three evidence levels:
- **High (h)**: SEFRAK, Matrikkelen, ML detection, OSM with explicit date
- **Medium (m)**: Style inference (future), statistical models
- **Low (l)**: OSM without date

### Era-Based Display Rules
- **Pre-1900**: Only show buildings with high evidence
- **1900-1950**: Show high evidence + modern buildings
- **Post-1950**: Show all buildings

### Known Limitations
1. ML model has domain gap (trained on synthetic, applied to real)
2. Only one historical map era (1880s) currently processed
3. No building replacement detection yet
4. Performance with large GeoJSON files
