# Testing

## Automated Frontend Tests

Run the automated frontend validation tests:

```bash
node scripts/test_frontend.js
```

This validates:
1. **JavaScript syntax** - Ensures app.js has no syntax errors
2. **MapLibre data expressions** - Checks that data expressions are not used in unsupported paint properties (like `line-dasharray`)
3. **Required functions** - Verifies key functions exist (createBuildingFilter, createRoadFilter, etc.)
4. **Layer definitions** - Ensures all required map layers are defined
5. **Common MapLibre errors** - Checks for potential issues with filters and sources
6. **CSS validation** - Verifies CSS syntax and required classes

Expected output:
```
============================================================
FRONTEND VALIDATION TESTS
============================================================
[Test 1] JavaScript Syntax Validation
  ✓ app.js syntax is valid
...
============================================================
RESULTS
============================================================
  Passed: 24
  Failed: 0

All tests passed!
```

---

# Testing the Source Filter Fix

## Quick Start

1. **Start the development server:**
   ```bash
   cd /Users/vaskinn/Development/private/historymap/frontend
   python3 -m http.server 8080
   ```

2. **Open the test page:**
   - Main app: http://localhost:8080/index.html
   - Test page: http://localhost:8080/test_source_filter.html

3. **Open browser console** (F12) to see debug logs

## What Was Fixed

### Problem 1: Source Counts Not Displaying
- **Before**: Count badges showed `-` instead of actual numbers
- **After**: Shows actual building counts (OSM: ~16,000, ML: ~117, etc.)

### Problem 2: Source Filtering May Not Work
- **Before**: Unclear if checkboxes actually filtered the map
- **After**: Checkboxes now properly filter buildings on map display

## Automated Tests (test_source_filter.html)

The test page runs 5 automated checks:

1. **Data Cache** - Verifies GeoJSON data was loaded and cached
2. **Source Counts** - Verifies count badges display numbers
3. **OSM Count Sanity** - Verifies OSM has >1000 buildings (expected)
4. **Checkbox Controls** - Verifies UI elements exist
5. **Map Loaded** - Verifies MapLibre initialized correctly

**Expected Results:**
- All 5 tests should show ✓ (pass)
- Source counts should show real numbers within 3 seconds
- Console should show:
  ```
  Loaded 16234 buildings for counting
  Loaded 432 demolished buildings for counting
  Source counts updated: {sef: 89, tk: 0, mat: 0, ml: 117, osm: 16028}
  ```

## Manual Tests

### Test 1: Source Count Display
1. Open main app or test page
2. Wait 3 seconds for data to load
3. Look at "Filter by Source" panel
4. **Expected**: Numbers displayed next to each source (not `-`)
5. **Actual counts** (approximate):
   - SEFRAK: ~89
   - Trondheim Kommune: 0
   - Matrikkelen: 0
   - ML Detection: ~117
   - OpenStreetMap: ~16,000

### Test 2: Filter OpenStreetMap
1. Start with all sources checked
2. Uncheck "OpenStreetMap"
3. **Expected**: Most buildings disappear (only ~200 historical buildings remain)
4. Check browser console for log:
   ```
   Building filter - source filter: {sef: true, tk: true, mat: true, ml: true, osm: false}
   ```

### Test 3: Filter ML Detection
1. Check all sources again
2. Uncheck "ML Detection"
3. **Expected**: ML-detected buildings disappear (~117 buildings)
4. Map should still show modern OSM buildings

### Test 4: Clear All Sources
1. Click "None" button
2. **Expected**: All buildings disappear
3. Console should show:
   ```
   Building filter - source filter: {sef: false, tk: false, mat: false, ml: false, osm: false}
   ```

### Test 5: Select All Sources
1. Click "All" button
2. **Expected**: All buildings reappear
3. Counts should remain the same (not reset)

### Test 6: Toggle Individual Sources
1. Start with all sources checked
2. Uncheck SEFRAK
3. Re-check SEFRAK
4. **Expected**: SEFRAK buildings disappear then reappear
5. Each toggle should trigger map style update

## Console Logs to Expect

### On Page Load:
```
Initializing Trondheim Historical Map application...
PMTiles protocol initialized
Controls initialized
Map loaded successfully
Loaded 16234 buildings for counting
Loaded 432 demolished buildings for counting
Source counts updated: {sef: 89, tk: 0, mat: 0, ml: 117, osm: 16028}
```

### On Source Filter Change:
```
Building filter - source filter: {sef: true, tk: true, mat: true, ml: false, osm: true}
Building filter - ML source filter: {kv1880: true, kv1904: true, air1947: true}
Combined building filter: [
  "all",
  ["in", "src", "sef", "tk", "mat", "osm"],
  ["any", ["!=", "src", "ml"], ["!has", "ml_src"], ["in", "ml_src", "kv1880", "kv1904", "air1947"]],
  ["has", "$type"]
]
Updating map to year: 2020
Style data loaded for year: 2020
```

## Debugging

### If counts show `-`:
1. Check console for errors loading GeoJSON
2. Verify files exist:
   ```bash
   ls -lh data/buildings.geojson
   ls -lh data/buildings_demolished.geojson
   ```
3. Verify files are symlinked correctly
4. Check network tab for 404 errors

### If filtering doesn't work:
1. Check console for filter expressions
2. Verify `sourceFilter` state is updating
3. Look for `updateMapYear()` being called
4. Check if style is being recreated with new filters

### If map doesn't load:
1. Check for JavaScript syntax errors
2. Verify MapLibre GL JS loaded (check network tab)
3. Check for GeoJSON parsing errors
4. Try simpler data files first

## Known Limitations

### ML Sub-source Filtering
- ML sub-source checkboxes (Kartverket 1880, 1904, Aerial 1947) are displayed but **don't function**
- Reason: Current data doesn't include `ml_src` property
- All ML buildings shown together when "ML Detection" is checked
- **To fix**: Re-export data with proper `ml_src` field

### Performance
- Caching adds ~15-16MB to memory usage
- Should be acceptable for most browsers
- If issues occur, consider:
  - Only caching IDs and source fields (not geometries)
  - Using Web Workers for counting
  - Server-side counting API

## Success Criteria

- ✓ Source counts display actual numbers (not `-`)
- ✓ Counts load within 3 seconds of page load
- ✓ Unchecking a source removes those buildings from map
- ✓ "All" button shows all buildings
- ✓ "None" button hides all buildings
- ✓ Console logs show filter state changes
- ✓ No JavaScript errors in console
- ✓ Buildings reappear when source is re-checked

## Next Steps

If all tests pass:
1. Remove debug logging from `createBuildingFilter()` (lines 615-617, 649)
2. Test with production data
3. Verify performance with full dataset
4. Consider implementing filtered counts (show count for current year)
5. Fix ML sub-source data export to enable sub-filtering

## Files Modified

- `/Users/vaskinn/Development/private/historymap/frontend/app.js`
- `/Users/vaskinn/Development/private/historymap/data/buildings.geojson` (symlink)
- `/Users/vaskinn/Development/private/historymap/data/buildings_demolished.geojson` (symlink)

## Documentation

- Full fix details: `SOURCE_FILTER_FIX.md`
- Original issues: `docs/loose_ends.md` (lines 49-54)
