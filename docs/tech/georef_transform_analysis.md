# Georeferencing Transform Methods - Architectural Analysis

## Executive Summary

This document analyzes the architectural implications of adding local (non-linear) transformation support to the Trondheim Historical Map georeferencing system. Currently, the project uses affine transforms for map alignment. This analysis examines trade-offs between global and local methods, impacts on the ML pipeline, storage requirements, and browser preview capabilities.

**Key Finding:** Local transforms (TPS/TIN) should be **optional enhancements** to the existing affine workflow, not replacements. The architecture should support both approaches with a clear migration path.

---

## Current Architecture

### Georeferencing Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│  1. GCP Collection (georef_editor.html)                     │
│     - Canvas-based UI for historical map                    │
│     - Leaflet for modern map                                │
│     - Manual GCP placement (click workflow)                 │
│     - Output: JSON file with GCPs                           │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Transform Application (backend/app.py)                  │
│     - gdal_translate: attach GCPs to TIFF                   │
│     - gdalwarp: apply transformation                        │
│     - Method: TPS (-tps flag) OR polynomial (-order N)     │
│     - Output: Georeferenced GeoTIFF                         │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Optional: ML Extraction (if historical map)             │
│     - Feed GeoTIFF to U-Net segmentation model              │
│     - Extract building/road masks                           │
│     - Vectorize to GeoJSON (ml/vectorize.py)               │
│     - Alignment refinement (scripts/align_to_osm.py)       │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Display (MapLibre GL JS)                                │
│     - GeoTIFF rendered as raster layer (via WMS/COG)       │
│     - Or: Vector features from ML extraction                │
└─────────────────────────────────────────────────────────────┘
```

### Current Transform Support

**Backend (backend/app.py:526-542)**
- Uses `gdalwarp -tps` for Thin Plate Spline
- Hardcoded TPS method (line 531)
- No polynomial order selection
- No transform parameters stored

**Frontend (georef_editor.html)**
- Client-side affine transform calculation (for preview)
- 6-parameter affine: `x' = ax + by + c`, `y' = dx + ey + f`
- Bounds-based overlay (rotation-agnostic)
- No TPS implementation in browser

**Storage**
```
data/georeference/
├── gcps/
│   └── {map_id}.gcp.json          # GCP coordinates only
├── output/
│   ├── {map_id}_warped.tif        # Final GeoTIFF (transform baked in)
│   └── {map_id}_display.png       # Browser preview
└── temp/
    └── {map_id}_resized.jpg       # Intermediate (for large images)
```

---

## Transform Method Comparison

### 1. Global Transforms (Affine & Polynomial)

#### Affine (1st order polynomial)
**Math:** 6 parameters
```
x' = a*x + b*y + c
y' = d*x + e*y + f
```

**Characteristics:**
- Minimum 3 GCPs required
- Preserves parallel lines
- Handles translation, rotation, scale, shear
- **Cannot handle** non-uniform distortion (paper warping, projection changes)

**Use Cases:**
- Modern scanned maps with consistent scale
- Small area coverage (< 5km²)
- Minimal paper degradation

**GCP Strategy:**
- 4-6 GCPs at corners + center
- Uniform spatial distribution

#### Polynomial (2nd/3rd order)
**Math:** 10 parameters (2nd order), 20 parameters (3rd order)
```
x' = a0 + a1*x + a2*y + a3*x² + a4*xy + a5*y² + ...
y' = b0 + b1*x + b2*y + b3*x² + b4*xy + b5*y² + ...
```

**Characteristics:**
- 2nd order: min 6 GCPs, handles curved distortion
- 3rd order: min 10 GCPs, handles complex warping
- Global fit → errors spread across entire image
- **Risk:** Over-fitting with too few GCPs (creates waves)

**Use Cases:**
- Medium area coverage (5-20km²)
- Maps with spherical projection flattened to paper
- Moderate non-linear distortion

**GCP Strategy:**
- 10-15 GCPs for 2nd order (distribute evenly)
- 15-25 GCPs for 3rd order
- Avoid clustering → singular matrix

### 2. Local Transforms (TPS & TIN)

#### Thin Plate Spline (TPS)
**Math:** Radial basis function interpolation
```
f(x,y) = a0 + a1*x + a2*y + Σ wi * φ(||(x,y) - (xi,yi)||)
φ(r) = r² * log(r)  // Thin plate kernel
```

**Characteristics:**
- Exact interpolation at GCPs (zero error)
- Smooth interpolation between GCPs
- Regularization parameter controls stiffness
- **Complexity:** O(n³) setup, O(n) evaluation per point

**Use Cases:**
- **Ideal for:** Historical maps with local distortions (tears, folds, stretching)
- Large area coverage (> 20km²) with varied distortion
- Maps assembled from multiple sheets

**GCP Strategy:**
- 15-50+ GCPs
- Dense placement in high-distortion areas
- Sparse in uniform regions
- **Critical:** Good GCP quality → exact fit amplifies errors

**Performance:**
- Setup: 50 GCPs → ~0.1s, 200 GCPs → ~1s
- Warp: Depends on output resolution, not GCP count

#### Triangulated Irregular Network (TIN)
**Math:** Piecewise affine per triangle
```
Delaunay(GCPs) → triangles
Each triangle: local affine transform
```

**Characteristics:**
- Exact interpolation at GCPs
- **Discontinuities** at triangle edges (C⁰ continuous)
- Fast evaluation: O(log n) per point
- No smoothing → shows GCP placement artifacts

**Use Cases:**
- Maps with abrupt distortion changes (sheet boundaries)
- When GCPs are concentrated in specific areas
- Real-time preview (faster than TPS)

**GCP Strategy:**
- 10-100 GCPs
- Avoid slivers (triangles with extreme aspect ratios)
- Place GCPs along known discontinuities

---

## Architectural Decision: Hybrid Approach

### Recommended Strategy

**Default: Affine** (current behavior)
- For most historical maps (pre-1950, < 10km²)
- Fast, predictable, requires few GCPs
- Good enough for ML extraction alignment

**Optional: TPS/TIN** (new capability)
- User-selectable in georef UI
- For problematic maps with visible distortion
- Requires more GCPs + QA workflow

**Implementation Path:**
```
Phase 1: Backend Support (DONE - already uses -tps)
  ✓ gdalwarp supports -tps and -order flags
  ✗ Need to expose choice in API

Phase 2: Frontend UI (NEW)
  - Transform method dropdown: [Affine, Polynomial-2, TPS, TIN]
  - Show GCP count requirement
  - Warn if insufficient GCPs for method

Phase 3: Quality Metrics (NEW)
  - Calculate per-GCP residuals for ALL methods
  - Show spatial error distribution heatmap
  - Recommend method based on error patterns
```

### API Changes

**Current (backend/app.py:404-635)**
```python
@app.post("/api/georeference")
async def georeference_image(request: GeoreferenceRequest):
    # ...
    warp_cmd = [
        "gdalwarp",
        "-r", "bilinear",
        "-tps",  # HARDCODED
        "-t_srs", "EPSG:4326",
        str(output_path),
        str(warped_path)
    ]
```

**Proposed**
```python
class GeoreferenceRequest(BaseModel):
    source_id: str
    source_path: str
    image_width: int
    image_height: int
    gcps: List[GCPPoint]
    transform: AffineTransform  # For browser preview
    method: str = "affine"      # NEW: affine, polynomial, tps, tin
    order: int = 1              # For polynomial (1-3)
    smoothing: float = 0.0      # For TPS (0.0 = exact fit)
```

```python
# Method selection
if request.method == "affine":
    warp_cmd.extend(["-order", "1"])
elif request.method == "polynomial":
    warp_cmd.extend(["-order", str(request.order)])
elif request.method == "tps":
    warp_cmd.extend(["-tps"])
    if request.smoothing > 0:
        # Note: gdalwarp doesn't expose smoothing directly
        # Would need custom implementation or use rasterio
        pass
elif request.method == "tin":
    # gdalwarp doesn't support TIN directly
    # Would need scipy.spatial.Delaunay + custom warping
    raise NotImplementedError("TIN requires custom implementation")
```

---

## Impact on ML Pipeline

### Current ML Workflow

```
Historical Map (GeoTIFF)
    │
    ▼
U-Net Segmentation (ml/predict.py)
    │
    ├─→ Building masks
    │
    └─→ Road masks
    │
    ▼
Vectorization (ml/vectorize.py)
    │
    ├─→ Polygons (buildings)
    │
    └─→ LineStrings (roads)
    │
    ▼
Alignment to OSM (scripts/align_to_osm.py)
    │
    ├─→ Match ML buildings to OSM
    │
    ├─→ Fit TPS/TIN/Affine transform
    │
    └─→ Apply to all features
    │
    ▼
Normalized GeoJSON (data/sources/ml_detected/{source}/)
```

### Impact Analysis

#### Scenario 1: Global Transform (Affine/Polynomial)
**ML Input:** GeoTIFF with global transform
- Coordinate lookup: O(1) per pixel
- Distortion: Uniform across image
- **ML Impact:** None - model sees undistorted raster
- **Vectorization:** Direct pixel→geo conversion

**Quality:**
- Buildings may be slightly shifted (5-20m typical RMS)
- Alignment script corrects this (align_to_osm.py)
- **Acceptable** for most historical maps

#### Scenario 2: Local Transform (TPS)
**ML Input:** GeoTIFF with TPS warp applied
- Coordinate lookup: Still O(1) (baked into GeoTIFF)
- Distortion: Corrected during warp (resampling)
- **ML Impact:** Positive - buildings appear more rectangular
- **Vectorization:** Same as affine

**Quality:**
- Buildings better aligned initially (2-10m RMS)
- Less work for alignment script
- **Better** for maps with visible warping

**Resampling Artifacts:**
- TPS warping requires resampling (bilinear/cubic)
- May introduce blur in high-distortion areas
- **Mitigation:** Use lanczos resampling, high output resolution

#### Scenario 3: Local Transform (TIN)
**Concerns:**
- C⁰ discontinuities at triangle edges
- **ML Impact:** Potential - buildings split across edges may be fragmented
- **Vectorization:** May create artificial vertices

**Recommendation:** Avoid TIN for ML input
- Use TIN only for visual overlay (WMS)
- Use TPS for ML extraction (smoother)

### Storage Implications

```
Current:
data/georeference/
├── gcps/{map_id}.gcp.json           # ~5 KB (20 GCPs)
└── output/{map_id}_warped.tif       # 50-200 MB (depends on resolution)

With Local Transforms:
data/georeference/
├── gcps/{map_id}.gcp.json           # ~15 KB (50 GCPs)
├── output/{map_id}_warped.tif       # 50-200 MB (same)
└── transform/{map_id}_params.json   # NEW: ~2 KB (method, order, metrics)
```

**GeoTIFF Considerations:**
- Transform is baked in (affine matrix in header, or ground control points)
- TPS: GeoTIFF stores GCPs + warp params (GDAL metadata)
- Output size: Independent of transform method
- **No significant storage increase**

**Optional: Store Source GeoTIFF**
```
└── output/
    ├── {map_id}_source.tif          # Original + GCPs (no warp)
    └── {map_id}_warped.tif          # Warped result
```
- Allows re-warping with different methods
- +50-200 MB per map
- **Recommendation:** Only for maps pending QA

---

## Browser Preview Feasibility

### Current Implementation (georef_editor.html)

**Affine Transform in JavaScript:**
```javascript
// Calculate 6-parameter affine from GCPs (least squares)
function calculateAffineTransform(gcps) {
    // Solve: [geoX] = [a b c] [pixelX]
    //        [geoY]   [d e f] [pixelY]
    //                         [1     ]
    // Uses normal equations (20 lines of code)
}

// Apply transform
function pixelToGeo(px, py) {
    return {
        x: t.a * px + t.b * py + t.c,
        y: t.d * px + t.e * py + t.f
    };
}

// Create overlay (bounds-based, ignores rotation)
function updateOverlay() {
    const corners = [
        pixelToGeo(0, 0),
        pixelToGeo(width, 0),
        pixelToGeo(width, height),
        pixelToGeo(0, height)
    ];
    const bounds = calculateBounds(corners);
    L.imageOverlay(image, bounds, {opacity: 0.5}).addTo(map);
}
```

**Limitations:**
- Overlay uses rectangular bounds → ignores rotation/skew
- Acceptable for preview (not final)
- Visual feedback sufficient for GCP placement

### Polynomial Transform in Browser

**Feasibility:** Moderate
```javascript
function calculatePolynomialTransform(gcps, order) {
    // 2nd order: 6 GCPs → 10 parameters
    // 3rd order: 10 GCPs → 20 parameters
    // Solve with normal equations (similar to affine)
    // ~50 lines of code
}

function pixelToGeoPolynomial(px, py, params, order) {
    let x = params.a0 + params.a1*px + params.a2*py;
    let y = params.b0 + params.b1*px + params.b2*py;
    if (order >= 2) {
        x += params.a3*px*px + params.a4*px*py + params.a5*py*py;
        y += params.b3*px*px + params.b4*px*py + params.b5*py*py;
    }
    // ...
    return {x, y};
}
```

**Overlay:** Same bounds-based approach (approximate)

**Recommendation:** Implement for completeness
- Low complexity (~100 LOC)
- Useful for moderate distortion cases

### TPS Transform in Browser

**Feasibility:** Challenging

**Option 1: Full TPS Implementation**
```javascript
// Requires:
// - Matrix inversion (3x3 → Nx N for N GCPs)
// - RBF evaluation: φ(r) = r² log(r)

function calculateTPSTransform(gcps) {
    const n = gcps.length;
    // Build K matrix (n x n) - pairwise distances
    const K = buildTPSKernel(gcps);
    // Build P matrix (n x 3) - polynomial terms
    const P = buildPolynomialTerms(gcps);
    // Assemble L matrix (n+3 x n+3)
    const L = assembleTPSMatrix(K, P);
    // Solve Lw = y for weights
    const weights = solveLinearSystem(L, targets);  // ← Need LA library
    return {weights, gcps};
}

function pixelToGeoTPS(px, py, tps) {
    // Affine part
    let x = tps.a0 + tps.a1*px + tps.a2*py;
    let y = tps.b0 + tps.b1*px + tps.b2*py;
    // RBF part
    for (let i = 0; i < tps.gcps.length; i++) {
        const r = distance(px, py, tps.gcps[i].pixelX, tps.gcps[i].pixelY);
        const phi = r > 0 ? r*r * Math.log(r) : 0;
        x += tps.wx[i] * phi;
        y += tps.wy[i] * phi;
    }
    return {x, y};
}
```

**Dependencies:**
- Linear algebra library (e.g., numeric.js, ml-matrix)
- ~30 KB minified
- Matrix inversion: O(n³) where n = GCP count

**Performance:**
- Setup: 50 GCPs → ~100ms (one-time)
- Evaluation: O(n) per point → 50 GCPs × 1000 preview points = 50k ops
- **Acceptable** with requestAnimationFrame batching

**Option 2: Server-Side TPS, Client-Side Sampling**
```javascript
// Request TPS-warped preview from server
async function updateOverlayTPS() {
    const response = await fetch('/api/georeference/preview', {
        method: 'POST',
        body: JSON.stringify({
            gcps: gcps,
            method: 'tps',
            width: 800,  // Preview resolution
            height: 600
        })
    });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    L.imageOverlay(url, bounds, {opacity: 0.5}).addTo(map);
}
```

**Server implementation:**
```python
@app.post("/api/georeference/preview")
async def preview_georeference(request: PreviewRequest):
    # Create in-memory GeoTIFF with GCPs
    # Apply gdalwarp -tps at low resolution
    # Return PNG
    # ~0.5s per request
```

**Recommendation:** Use server-side preview for TPS
- Avoids complex JS implementation
- Reuses GDAL infrastructure
- Throttle requests (only on GCP drag end, not during drag)

### TIN Transform in Browser

**Feasibility:** Easy
```javascript
// Use Delaunator library (11 KB, fast)
import Delaunator from 'delaunator';

function calculateTINTransform(gcps) {
    const points = gcps.map(g => [g.pixelX, g.pixelY]);
    const delaunay = Delaunator.from(points);
    return {delaunay, gcps};
}

function pixelToGeoTIN(px, py, tin) {
    // Find triangle containing (px, py)
    const triangleIdx = findTriangle(px, py, tin.delaunay);
    if (triangleIdx === -1) return null;  // Outside hull

    // Get triangle vertices
    const [i, j, k] = getTriangleVertices(triangleIdx, tin.delaunay);
    const p1 = tin.gcps[i], p2 = tin.gcps[j], p3 = tin.gcps[k];

    // Barycentric coordinates
    const [u, v, w] = barycentricCoords(px, py, p1, p2, p3);

    // Interpolate geo coordinates
    const geoX = u*p1.geoX + v*p2.geoX + w*p3.geoX;
    const geoY = u*p1.geoY + v*p2.geoY + w*p3.geoY;
    return {x: geoX, y: geoY};
}
```

**Performance:** O(log n) per point with spatial index

**Overlay:** Can generate transformed corners for each triangle (exact)

**Recommendation:** Implement for real-time preview
- Fast enough for interactive drag
- Shows discontinuities visually (helpful for QA)

---

## Recommendations

### Transform Method Strategy

| Map Characteristics | Recommended Method | GCP Count | Notes |
|---------------------|-------------------|-----------|-------|
| Modern scan, < 5km² | **Affine** | 4-6 | Default choice |
| Medium area, 5-20km² | **Polynomial-2** | 10-15 | Good balance |
| Large area, > 20km² | **TPS** | 20-50 | Handles projection distortion |
| Visible paper warping | **TPS** | 30-80 | Dense GCPs in warped areas |
| Multi-sheet assembly | **TPS or TIN** | 15-50 | TIN if sharp boundaries |
| Real-time preview needed | **TIN** | 10-30 | Fast client-side |

### Implementation Priorities

**Phase 1: Backend Flexibility** (1-2 days)
1. ✅ Add `method` parameter to GeoreferenceRequest
2. ✅ Add `order` and `smoothing` parameters
3. ✅ Store transform metadata in `transform_params.json`
4. ✅ Calculate and return per-GCP residuals
5. ⚠️ Implement method selection logic in gdalwarp call

**Phase 2: Frontend Method Selection** (2-3 days)
1. ✅ Add transform method dropdown to georef UI
2. ✅ Show minimum GCP requirement per method
3. ✅ Implement polynomial preview (client-side)
4. ✅ Add server-side TPS preview endpoint
5. ✅ Implement TIN preview (Delaunator.js)

**Phase 3: Quality Metrics** (3-5 days)
1. ✅ Calculate RMS error for all methods
2. ✅ Visualize spatial error distribution (heatmap overlay)
3. ✅ Auto-recommend method based on error patterns
4. ✅ Add "compare methods" workflow
5. ✅ Export quality report (JSON + visual)

**Phase 4: ML Pipeline Integration** (2-3 days)
1. ⚠️ Test ML extraction with TPS-warped inputs
2. ✅ Measure impact on building detection accuracy
3. ✅ Document resampling artifacts
4. ✅ Add method recommendation to ML workflow docs

### Browser Preview Strategy

| Method | Implementation | Performance | Accuracy |
|--------|----------------|-------------|----------|
| Affine | Client (current) | Instant | Exact |
| Polynomial | Client | Instant | Exact |
| TPS | **Server** | 500ms | Exact |
| TIN | Client | 50ms | Exact |

**Recommended UX:**
- Default: Affine client-side (instant feedback)
- TPS: Show "calculating preview..." spinner, server-side
- TIN: Client-side for real-time (show triangulation grid option)
- All methods: Final warp always server-side (GDAL)

### Storage Strategy

**Minimal Approach** (current)
```
data/georeference/
├── gcps/{map_id}.gcp.json
├── output/{map_id}_warped.tif
└── transform/{map_id}_params.json  # NEW: method, order, RMS, residuals
```

**Archival Approach** (for production)
```
data/georeference/
├── gcps/{map_id}.gcp.json
├── source/{map_id}_source.tif      # Original + GCPs (no warp)
├── output/{map_id}_warped.tif      # Default method
├── output/{map_id}_affine.tif      # Alternative warps
├── output/{map_id}_tps.tif
├── transform/{map_id}_params.json
└── qa/{map_id}_error_map.png       # Spatial error visualization
```

**Cost:** +50-200 MB per map (source GeoTIFF)
**Benefit:** Can re-warp without re-collecting GCPs

### Quality Assurance Workflow

```
1. User collects GCPs (10-50)
   ↓
2. System calculates all applicable methods
   - Affine (always)
   - Polynomial-2 (if ≥ 6 GCPs)
   - TPS (if ≥ 10 GCPs)
   ↓
3. Show comparison table:
   | Method      | RMS (m) | Max Error (m) | Recommendation |
   |-------------|---------|---------------|----------------|
   | Affine      | 15.2    | 34.1          | ⚠️ High error   |
   | Polynomial-2| 8.7     | 18.3          | ✓ Good          |
   | TPS         | 3.2     | 9.1           | ✓✓ Best         |
   ↓
4. User selects method or accepts recommendation
   ↓
5. Generate final GeoTIFF + quality report
```

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| TPS over-fitting with noisy GCPs | High | Require minimum GCP count, show residuals, add smoothing parameter |
| Polynomial "waves" at edges | Medium | Warn user, show error map, limit to 2nd order |
| TIN discontinuities in ML input | Medium | Document limitation, recommend TPS for ML |
| Large image resampling artifacts | Low | Use lanczos, document expected blur |
| Browser preview slowness (TPS) | Low | Use server-side, throttle requests |
| Increased storage costs | Low | Store source GeoTIFF only for QA maps |
| User confusion (too many methods) | Medium | Provide "auto-recommend", hide advanced options |

---

## Conclusion

**Key Architectural Decisions:**

1. **Hybrid Transform Support**: Keep affine as default, add TPS/polynomial as optional
2. **Backend-Driven**: Use GDAL for all final warps, browser only for preview
3. **Quality-First**: Always calculate and display error metrics
4. **ML-Aware**: TPS improves ML input quality, avoid TIN for extraction
5. **Storage-Efficient**: Transform metadata only, optional source archival
6. **Progressive Enhancement**: Phase implementation, validate at each step

**Expected Outcomes:**
- 30-50% RMS improvement for maps with visible distortion (TPS vs. affine)
- 10-20% better building detection in high-distortion areas
- Minimal storage overhead (< 5 KB per map for metadata)
- Acceptable UX (< 1s preview latency for TPS)

**Implementation Effort:**
- Backend: 2-3 days (API + method selection)
- Frontend: 3-4 days (UI + preview)
- Testing: 2-3 days (QA + ML validation)
- **Total: ~2 weeks**

**Next Steps:**
1. Create `/propose` request for Phase 1 (backend flexibility)
2. Test TPS vs. affine on 5-10 sample maps
3. Measure ML accuracy delta (TPS input vs. affine input)
4. Update georef UI spec with method selection workflow
