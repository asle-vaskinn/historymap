# Georeferencing Editor v2 - Implementation Plan

## Overview

Iterative refinement workflow for georeferencing historical maps with live feedback.

**Key Features:**
1. Draggable GCPs on both maps
2. Live overlay preview (historical on modern)
3. Per-point error display
4. Proper affine transform in browser

## Architecture

### Current State

```
┌─────────────────────────────────────────────────────────────┐
│  georef_editor.html (single file, ~1300 lines)              │
│  ├── Global state variables                                 │
│  ├── Canvas rendering (historical map + GCP markers)        │
│  ├── Leaflet map (modern OSM + GCP markers)                │
│  ├── Click workflow (historical → modern)                   │
│  ├── GCP storage (load/save JSON)                          │
│  └── Auto-match system (building overlay)                   │
└─────────────────────────────────────────────────────────────┘
```

### Proposed Changes

```
┌─────────────────────────────────────────────────────────────┐
│  georef_editor.html                                         │
│  ├── State                                                  │
│  │   ├── gcps[], selectedGcpIndex (existing)               │
│  │   ├── + draggingGcpIndex, dragSource ('canvas'|'map')   │
│  │   ├── + transform {forward, inverse, rms, residuals[]}  │
│  │   └── + overlayState {enabled, opacity, imageOverlay}   │
│  │                                                          │
│  ├── Canvas (historical)                                    │
│  │   ├── Pan/zoom (existing)                               │
│  │   ├── Click to place/select (existing)                  │
│  │   ├── + Drag GCP markers                                │
│  │   └── + Error indicator rings                           │
│  │                                                          │
│  ├── Leaflet (modern)                                       │
│  │   ├── OSM tiles (existing)                              │
│  │   ├── GCP markers (existing)                            │
│  │   ├── + Draggable markers                               │
│  │   └── + Historical image overlay layer                  │
│  │                                                          │
│  ├── Transform Engine (NEW)                                 │
│  │   ├── calculateAffineTransform(gcps)                    │
│  │   ├── applyForward(pixelX, pixelY) → {geoX, geoY}      │
│  │   ├── applyInverse(geoX, geoY) → {pixelX, pixelY}      │
│  │   └── calculateResiduals() → [{gcpId, errorMeters}]    │
│  │                                                          │
│  └── UI Updates                                             │
│      ├── GCP list with error badges                        │
│      ├── Overlay toggle + opacity slider                   │
│      └── Total RMS display                                  │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1: Draggable GCPs (Foundation)

**Goal:** Allow repositioning existing GCPs without delete/recreate.

#### 1.1 Canvas GCP Dragging

**New State:**
```javascript
let draggingGcpIndex = null;  // Index of GCP being dragged
let dragSource = null;        // 'canvas' or 'leaflet'
let gcpDragStart = null;      // {x, y} at drag start
```

**Modified mousedown (lines 383-391):**
```javascript
canvas.addEventListener('mousedown', e => {
    if (e.button === 0) {
        const rect = canvas.getBoundingClientRect();
        const p = canvasToPixel(e.clientX - rect.left, e.clientY - rect.top);

        // Check if clicking on existing GCP
        const hitIndex = findGcpAtPixel(p.x, p.y);

        if (hitIndex !== null) {
            // Start GCP drag
            draggingGcpIndex = hitIndex;
            dragSource = 'canvas';
            gcpDragStart = { x: p.x, y: p.y };
            canvas.style.cursor = 'move';
        } else {
            // Existing pan behavior
            isDragging = true;
            dragMoved = false;
            dragStart = { x: e.clientX, y: e.clientY };
            lastPan = { x: panX, y: panY };
            canvas.style.cursor = 'grabbing';
        }
    }
});
```

**New helper:**
```javascript
function findGcpAtPixel(px, py) {
    const threshold = 15 / zoom;  // 15 screen pixels
    for (let i = gcps.length - 1; i >= 0; i--) {
        const dx = gcps[i].pixelX - px;
        const dy = gcps[i].pixelY - py;
        if (Math.sqrt(dx*dx + dy*dy) < threshold) {
            return i;
        }
    }
    return null;
}
```

**Modified mousemove:**
```javascript
if (draggingGcpIndex !== null && dragSource === 'canvas') {
    const rect = canvas.getBoundingClientRect();
    const p = canvasToPixel(e.clientX - rect.left, e.clientY - rect.top);

    // Clamp to image bounds
    gcps[draggingGcpIndex].pixelX = Math.max(0, Math.min(historicalImage.width, Math.round(p.x)));
    gcps[draggingGcpIndex].pixelY = Math.max(0, Math.min(historicalImage.height, Math.round(p.y)));

    recalculateTransform();
    render();
}
```

**Modified mouseup:**
```javascript
if (draggingGcpIndex !== null) {
    draggingGcpIndex = null;
    dragSource = null;
    canvas.style.cursor = 'crosshair';
    updateGCPList();
    // Don't trigger click-to-place
    return;
}
```

#### 1.2 Leaflet Marker Dragging

**Modified createModernMarker():**
```javascript
function createModernMarker(gcp, index) {
    const marker = L.circleMarker([gcp.geoY, gcp.geoX], {
        radius: 8,
        color: '#4ecca3',
        fillColor: '#4ecca3',
        fillOpacity: 0.5,
        weight: 2,
        draggable: false  // CircleMarker doesn't support draggable
    }).addTo(modernMap);

    // Use standard Marker for dragging capability
    // Alternative: implement custom drag handling
    marker.on('mousedown', (e) => startLeafletDrag(e, index));

    marker.bindTooltip(gcp.id, { permanent: true, direction: 'right', offset: [10, 0] });
    modernMarkers[gcp.id] = marker;
}
```

**Better approach - use L.Marker with custom icon:**
```javascript
function createModernMarker(gcp, index) {
    const icon = L.divIcon({
        className: 'gcp-marker',
        html: `<div class="gcp-dot" data-id="${gcp.id}"></div>`,
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    });

    const marker = L.marker([gcp.geoY, gcp.geoX], {
        icon: icon,
        draggable: true
    }).addTo(modernMap);

    marker.on('drag', (e) => {
        const latlng = e.target.getLatLng();
        gcp.geoX = latlng.lng;
        gcp.geoY = latlng.lat;
        recalculateTransform();
        updateOverlay();
    });

    marker.on('dragend', () => {
        updateGCPList();
    });

    marker.bindTooltip(gcp.id, { permanent: true, direction: 'right', offset: [10, 0] });
    modernMarkers[gcp.id] = marker;
}
```

**CSS for custom marker:**
```css
.gcp-marker {
    background: transparent;
}
.gcp-dot {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: rgba(78, 204, 163, 0.5);
    border: 2px solid #4ecca3;
    cursor: move;
}
.gcp-dot:hover {
    background: rgba(78, 204, 163, 0.8);
    transform: scale(1.2);
}
```

---

### Phase 2: Transform Engine

**Goal:** Calculate proper 6-parameter affine transform with error metrics.

#### 2.1 Affine Transform Calculation

```javascript
/**
 * Calculate 6-parameter affine transform using least squares.
 *
 * Transform: [geoX]   [a b c] [pixelX]
 *            [geoY] = [d e f] [pixelY]
 *                             [1     ]
 *
 * @param {Array} gcps - Array of {pixelX, pixelY, geoX, geoY}
 * @returns {Object} {matrix, inverse, rms, residuals}
 */
function calculateAffineTransform(gcps) {
    const complete = gcps.filter(g =>
        g.pixelX != null && g.pixelY != null &&
        g.geoX != null && g.geoY != null
    );

    if (complete.length < 3) {
        return null;  // Need minimum 3 points
    }

    const n = complete.length;

    // Build matrices for least squares: A * x = b
    // For X: [px py 1] * [a b c]^T = geoX
    // For Y: [px py 1] * [d e f]^T = geoY

    // Matrix A (n x 3)
    const A = complete.map(g => [g.pixelX, g.pixelY, 1]);

    // Vectors b
    const bX = complete.map(g => g.geoX);
    const bY = complete.map(g => g.geoY);

    // Solve using normal equations: (A^T * A) * x = A^T * b
    const AtA = matMul3x3(transpose(A), A);
    const AtbX = matVecMul(transpose(A), bX);
    const AtbY = matVecMul(transpose(A), bY);

    // Solve 3x3 systems
    const [a, b, c] = solve3x3(AtA, AtbX);
    const [d, e, f] = solve3x3(AtA, AtbY);

    const matrix = { a, b, c, d, e, f };

    // Calculate inverse transform (geo → pixel)
    const det = a * e - b * d;
    if (Math.abs(det) < 1e-10) {
        return null;  // Singular matrix
    }
    const inverse = {
        a: e / det,
        b: -b / det,
        c: (b * f - c * e) / det,
        d: -d / det,
        e: a / det,
        f: (c * d - a * f) / det
    };

    // Calculate residuals
    const residuals = complete.map(gcp => {
        const predicted = applyTransform(gcp.pixelX, gcp.pixelY, matrix);
        const errorMeters = geoDistanceMeters(
            predicted.x, predicted.y,
            gcp.geoX, gcp.geoY
        );
        return { id: gcp.id, error: errorMeters };
    });

    // RMS error
    const rms = Math.sqrt(
        residuals.reduce((sum, r) => sum + r.error * r.error, 0) / residuals.length
    );

    return { matrix, inverse, rms, residuals };
}
```

#### 2.2 Helper Functions

```javascript
function applyTransform(px, py, matrix) {
    return {
        x: matrix.a * px + matrix.b * py + matrix.c,
        y: matrix.d * px + matrix.e * py + matrix.f
    };
}

function geoDistanceMeters(lon1, lat1, lon2, lat2) {
    // Approximate meters at Trondheim latitude
    const latRad = (lat1 + lat2) / 2 * Math.PI / 180;
    const dx = (lon2 - lon1) * 111320 * Math.cos(latRad);
    const dy = (lat2 - lat1) * 110540;
    return Math.sqrt(dx * dx + dy * dy);
}

// Simple 3x3 matrix operations (no external deps)
function transpose(A) { /* ... */ }
function matMul3x3(A, B) { /* ... */ }
function matVecMul(A, v) { /* ... */ }
function solve3x3(A, b) { /* Cramer's rule or Gaussian elimination */ }
```

#### 2.3 State Integration

```javascript
let currentTransform = null;  // Cached transform result

function recalculateTransform() {
    currentTransform = calculateAffineTransform(gcps);
    updateErrorDisplay();
    updateOverlay();
}
```

---

### Phase 3: Per-Point Error Display

**Goal:** Show which points are good/bad so user knows what to fix.

#### 3.1 GCP List Enhancement

**Modified updateGCPList():**
```javascript
function updateGCPList() {
    const list = document.getElementById('gcpList');
    const complete = gcps.filter(g => g.geoX !== null).length;
    document.getElementById('gcpCount').textContent = `${complete}/${gcps.length}`;

    // Show RMS if transform available
    if (currentTransform) {
        document.getElementById('rmsDisplay').textContent =
            `RMS: ${currentTransform.rms.toFixed(1)}m`;
    }

    if (gcps.length === 0) {
        list.innerHTML = '<div class="empty-hint">Click on historical map to add GCPs</div>';
        return;
    }

    list.innerHTML = gcps.map((gcp, i) => {
        const done = gcp.geoX !== null;
        const sel = i === selectedGcpIndex;

        // Find residual for this GCP
        let errorHtml = '';
        if (done && currentTransform) {
            const residual = currentTransform.residuals.find(r => r.id === gcp.id);
            if (residual) {
                const err = residual.error;
                const cls = err < 10 ? 'error-good' : err < 25 ? 'error-warn' : 'error-bad';
                const icon = err < 10 ? '✓' : err < 25 ? '⚠' : '✗';
                errorHtml = `<span class="gcp-error ${cls}">${err.toFixed(1)}m ${icon}</span>`;
            }
        }

        return `
            <div class="gcp-item ${done ? 'complete' : 'incomplete'} ${sel ? 'selected' : ''}"
                 onclick="selectGCP(${i})">
                <div class="gcp-header">
                    <span class="gcp-id">${gcp.id}</span>
                    ${errorHtml}
                </div>
                <div class="gcp-coords">
                    px: (${gcp.pixelX}, ${gcp.pixelY})<br>
                    ${done ? `geo: (${gcp.geoX.toFixed(5)}, ${gcp.geoY.toFixed(5)})` : 'geo: click modern map'}
                </div>
                <div class="gcp-actions">
                    <button class="btn-danger" onclick="event.stopPropagation();deleteGCP(${i})">Delete</button>
                </div>
            </div>
        `;
    }).join('');
}
```

#### 3.2 Error Styling

```css
.gcp-error {
    font-size: 0.75rem;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 3px;
}
.error-good { background: #27ae60; color: white; }
.error-warn { background: #f39c12; color: white; }
.error-bad { background: #e74c3c; color: white; }

#rmsDisplay {
    font-size: 0.85rem;
    color: #4ecca3;
    font-weight: 600;
}
```

#### 3.3 Canvas Error Indicators

**Modified render() - draw error rings:**
```javascript
// After drawing GCP markers, add error rings
if (currentTransform) {
    gcps.forEach((gcp, i) => {
        if (gcp.geoX === null) return;

        const residual = currentTransform.residuals.find(r => r.id === gcp.id);
        if (!residual) return;

        const x = gcp.pixelX * zoom + panX;
        const y = gcp.pixelY * zoom + panY;

        // Draw error ring - size proportional to error
        const ringRadius = Math.min(50, 10 + residual.error / 2);

        ctx.beginPath();
        ctx.arc(x, y, ringRadius, 0, Math.PI * 2);
        ctx.strokeStyle = residual.error < 10 ? '#27ae60' :
                          residual.error < 25 ? '#f39c12' : '#e74c3c';
        ctx.lineWidth = 2;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
    });
}
```

---

### Phase 4: Live Overlay Preview

**Goal:** See historical map overlaid on modern map to visually verify alignment.

#### 4.1 Overlay State

```javascript
let overlayState = {
    enabled: false,
    opacity: 0.5,
    imageOverlay: null,
    canvasOverlay: null
};
```

#### 4.2 UI Controls

**Add to header:**
```html
<div class="overlay-controls" id="overlayControls" style="display: none;">
    <label>
        <input type="checkbox" id="overlayToggle" onchange="toggleOverlay()">
        Overlay
    </label>
    <input type="range" id="overlayOpacity" min="0" max="100" value="50"
           oninput="setOverlayOpacity(this.value / 100)">
    <select id="blendMode" onchange="setBlendMode(this.value)">
        <option value="normal">Normal</option>
        <option value="multiply">Multiply</option>
        <option value="difference">Difference</option>
    </select>
</div>
```

#### 4.3 Canvas-Based Overlay (Recommended)

Using Leaflet's `L.ImageOverlay` won't work well because it doesn't support affine transforms (only rectangular bounds). Instead, use a canvas overlay:

```javascript
// Custom Leaflet layer for transformed image
L.TransformedImageOverlay = L.Layer.extend({
    initialize: function(image, transform, options) {
        this._image = image;
        this._transform = transform;
        L.setOptions(this, options);
    },

    onAdd: function(map) {
        this._map = map;

        // Create canvas element
        this._canvas = L.DomUtil.create('canvas', 'leaflet-transformed-image');
        this._canvas.style.position = 'absolute';
        this._canvas.style.pointerEvents = 'none';

        map.getPanes().overlayPane.appendChild(this._canvas);

        map.on('moveend', this._reset, this);
        this._reset();
    },

    onRemove: function(map) {
        L.DomUtil.remove(this._canvas);
        map.off('moveend', this._reset, this);
    },

    setTransform: function(transform) {
        this._transform = transform;
        this._reset();
    },

    setOpacity: function(opacity) {
        this._canvas.style.opacity = opacity;
    },

    _reset: function() {
        if (!this._transform || !this._image) return;

        const map = this._map;
        const bounds = map.getBounds();
        const size = map.getSize();

        this._canvas.width = size.x;
        this._canvas.height = size.y;

        const ctx = this._canvas.getContext('2d');
        ctx.clearRect(0, 0, size.x, size.y);

        // For each screen pixel, find corresponding image pixel
        // (This is slow - optimize with WebGL or sampling)
        this._renderTransformed(ctx, bounds, size);

        // Position canvas
        const topLeft = map.latLngToLayerPoint(bounds.getNorthWest());
        L.DomUtil.setPosition(this._canvas, topLeft);
    },

    _renderTransformed: function(ctx, bounds, size) {
        const inv = this._transform.inverse;
        const img = this._image;

        // Sample at lower resolution for performance
        const step = 2;

        for (let y = 0; y < size.y; y += step) {
            for (let x = 0; x < size.x; x += step) {
                // Screen to geo
                const latlng = this._map.containerPointToLatLng([x, y]);

                // Geo to pixel (inverse transform)
                const px = inv.a * latlng.lng + inv.b * latlng.lat + inv.c;
                const py = inv.d * latlng.lng + inv.e * latlng.lat + inv.f;

                // Sample image
                if (px >= 0 && px < img.width && py >= 0 && py < img.height) {
                    // Get pixel color (requires pre-rendered ImageData)
                    ctx.fillStyle = this._getPixelColor(Math.floor(px), Math.floor(py));
                    ctx.fillRect(x, y, step, step);
                }
            }
        }
    }
});
```

#### 4.4 Simplified Approach: Bounds-Based Overlay

For a simpler (though less accurate) implementation, calculate bounding box from transform:

```javascript
function updateOverlay() {
    if (!overlayState.enabled || !currentTransform || !historicalImage) {
        if (overlayState.imageOverlay) {
            modernMap.removeLayer(overlayState.imageOverlay);
            overlayState.imageOverlay = null;
        }
        return;
    }

    const t = currentTransform.matrix;

    // Transform image corners to geo coordinates
    const corners = [
        applyTransform(0, 0, t),                                    // top-left
        applyTransform(historicalImage.width, 0, t),                // top-right
        applyTransform(historicalImage.width, historicalImage.height, t),  // bottom-right
        applyTransform(0, historicalImage.height, t)                // bottom-left
    ];

    // Calculate bounds (this ignores rotation/skew - approximate only)
    const lats = corners.map(c => c.y);
    const lngs = corners.map(c => c.x);
    const bounds = [
        [Math.min(...lats), Math.min(...lngs)],
        [Math.max(...lats), Math.max(...lngs)]
    ];

    if (overlayState.imageOverlay) {
        overlayState.imageOverlay.setBounds(bounds);
    } else {
        overlayState.imageOverlay = L.imageOverlay(
            historicalImage.src,
            bounds,
            { opacity: overlayState.opacity }
        ).addTo(modernMap);
    }
}

function toggleOverlay() {
    overlayState.enabled = document.getElementById('overlayToggle').checked;
    updateOverlay();
}

function setOverlayOpacity(opacity) {
    overlayState.opacity = opacity;
    if (overlayState.imageOverlay) {
        overlayState.imageOverlay.setOpacity(opacity);
    }
}
```

**Note:** The bounds-based approach won't handle rotation. For v2.0, this is acceptable. A proper canvas-based solution can be added later if needed.

---

## Implementation Order

### Step 1: Core Transform Engine
1. Add `calculateAffineTransform()` function
2. Add helper math functions
3. Add `currentTransform` state
4. Add `recalculateTransform()` that updates on GCP changes
5. **Test:** Console log transform and residuals

### Step 2: Error Display
1. Add RMS display to header
2. Modify `updateGCPList()` to show per-point errors
3. Add CSS for error badges
4. **Test:** Place 4+ GCPs, verify errors display correctly

### Step 3: Canvas GCP Dragging
1. Add drag state variables
2. Modify mousedown to detect GCP hit
3. Modify mousemove to update GCP position
4. Modify mouseup to finalize drag
5. Call `recalculateTransform()` during drag
6. **Test:** Drag GCPs on canvas, verify smooth movement and error updates

### Step 4: Leaflet Marker Dragging
1. Change marker creation to use draggable L.marker
2. Add CSS for custom marker styling
3. Add drag event handlers
4. **Test:** Drag markers on modern map, verify position updates

### Step 5: Simple Overlay Preview
1. Add overlay state and UI controls
2. Implement bounds-based `updateOverlay()`
3. Add toggle and opacity controls
4. **Test:** Enable overlay, adjust opacity, verify it moves with GCP changes

### Step 6: Polish
1. Add undo/redo stack (optional)
2. Add keyboard shortcuts for overlay toggle
3. Add projection hints UI
4. Performance optimization if needed

---

## File Changes Summary

| File | Changes |
|------|---------|
| `scripts/georef_editor.html` | Major updates: transform engine, dragging, overlay, error display |
| `docs/spec/feat_georeferencing/SPEC.md` | Already updated with v2 requirements |

## Testing Checklist

- [ ] Place 3 GCPs → transform calculates, RMS shows
- [ ] Place 4+ GCPs → per-point errors display
- [ ] Drag GCP on canvas → position updates, errors recalculate
- [ ] Drag marker on modern map → geo coords update, errors recalculate
- [ ] Enable overlay → historical map shows on modern map
- [ ] Adjust opacity slider → overlay transparency changes
- [ ] Move GCP with overlay on → overlay updates in real-time
- [ ] Bad GCP (high error) → red badge, visible error ring
- [ ] Save/load → all state preserved correctly

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Performance with large images | Use sampling for overlay, throttle recalc |
| Transform accuracy | Use proper least squares, not centroid hack |
| Overlay distortion | Accept bounds-based for v2, note limitation |
| Click vs drag confusion | Use threshold, clear cursor feedback |
