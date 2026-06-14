/**
 * Data Prep Tool
 * Simple two-layer map viewer: Focus (overlay) + Reference (background)
 */

// ==========================================
// Configuration
// ==========================================

const TRONDHEIM_CENTER = [10.40, 63.43];
const TRONDHEIM_BOUNDS = [10.2, 63.35, 10.6, 63.5];

// Default options (always available)
const DEFAULT_OPTIONS = [
    { id: 'none', name: 'None', type: 'none' },
    { id: 'osm_positron', name: 'OpenStreetMap (Light)', type: 'vector-style', url: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json' },
    { id: 'osm_dark', name: 'OpenStreetMap (Dark)', type: 'vector-style', url: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json' }
];

// ==========================================
// State
// ==========================================

let map = null;
let sources = [];
let activeFocus = 'none';
let activeReference = 'osm_positron';
let focusOpacity = 0.7;

// ==========================================
// Initialization
// ==========================================

async function init() {
    await loadSources();
    initMap();
    setupUI();
    document.getElementById('status').textContent = `${sources.length} sources loaded`;
}

async function loadSources() {
    try {
        const response = await fetch('/api/sources');
        const data = await response.json();
        sources = data.sources || [];
    } catch (error) {
        console.error('Failed to load sources:', error);
        sources = [];
    }
}

function initMap() {
    map = new maplibregl.Map({
        container: 'map',
        style: {
            version: 8,
            sources: {},
            layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#1a1a2e' } }]
        },
        center: TRONDHEIM_CENTER,
        zoom: 13,
        maxBounds: [
            [TRONDHEIM_BOUNDS[0] - 0.1, TRONDHEIM_BOUNDS[1] - 0.1],
            [TRONDHEIM_BOUNDS[2] + 0.1, TRONDHEIM_BOUNDS[3] + 0.1]
        ],
        // Transform WMS requests to convert XYZ to bbox (Safari doesn't support {bbox-epsg-*} placeholders)
        transformRequest: (url, resourceType) => {
            if (resourceType === 'Tile' && url.includes('bbox=') && url.includes('request=GetMap')) {
                const match = url.match(/bbox=(\d+),(\d+),(\d+)/);
                if (match) {
                    const x = parseInt(match[1]);
                    const y = parseInt(match[2]);
                    const z = parseInt(match[3]);

                    const tileSize = 256;
                    const initialResolution = 2 * Math.PI * 6378137 / tileSize;
                    const originShift = 2 * Math.PI * 6378137 / 2.0;
                    const resolution = initialResolution / Math.pow(2, z);

                    const minX = x * tileSize * resolution - originShift;
                    const maxX = (x + 1) * tileSize * resolution - originShift;
                    const minY = originShift - (y + 1) * tileSize * resolution;
                    const maxY = originShift - y * tileSize * resolution;

                    const bbox = `${minX},${minY},${maxX},${maxY}`;
                    const newUrl = url.replace(/bbox=\d+,\d+,\d+/, `bbox=${bbox}`);
                    return { url: newUrl };
                }
            }
            return { url };
        }
    });

    map.addControl(new maplibregl.NavigationControl(), 'top-right');

    map.on('load', () => {
        console.log('Map loaded');
        updateLayers();
    });
}

// ==========================================
// UI Setup
// ==========================================

function setupUI() {
    populateFocusRadios();
    populateReferenceSelect();
    populateSourceList();
    setupEventListeners();
}

// ==========================================
// Source List (Read-only)
// ==========================================

function populateSourceList() {
    const container = document.getElementById('sourceList');
    if (!container) return;

    container.innerHTML = '';

    sources.forEach(source => {
        const item = document.createElement('div');
        item.className = 'source-item';
        item.innerHTML = `
            <span class="source-name">${source.name}</span>
            <span class="source-type-badge">${source.type}</span>
        `;
        container.appendChild(item);
    });
}

function getAllSources() {
    // Combine default options with API sources
    const all = [];

    // Add default basemaps
    DEFAULT_OPTIONS.filter(o => o.type === 'vector-style').forEach(opt => {
        all.push({ ...opt, category: 'basemap' });
    });

    // Add API sources
    sources.forEach(source => {
        all.push(source);
    });

    return all;
}

function populateFocusRadios() {
    const container = document.getElementById('focusList');
    container.innerHTML = '';

    const allSources = getAllSources();
    const categories = { historical: [], aerial: [] };

    // Group by category (exclude basemaps from focus - they're reference only)
    allSources.forEach(source => {
        const cat = source.category;
        if (cat === 'historical' || cat === 'aerial') {
            if (!categories[cat]) categories[cat] = [];
            categories[cat].push(source);
        }
    });

    // Add "None" option first
    const noneItem = createRadioItem('focus', { id: 'none', name: 'None' }, activeFocus === 'none');
    container.appendChild(noneItem);

    // Render categories
    const categoryOrder = ['historical', 'aerial'];
    const categoryNames = { historical: 'Historical Maps', aerial: 'Aerial Photos' };

    categoryOrder.forEach(cat => {
        const items = categories[cat];
        if (!items || items.length === 0) return;

        const header = document.createElement('div');
        header.className = 'layer-category';
        header.textContent = categoryNames[cat];
        container.appendChild(header);

        items.forEach(source => {
            const item = createRadioItem('focus', source, source.id === activeFocus);
            container.appendChild(item);
        });
    });
}

function createRadioItem(name, source, checked) {
    const item = document.createElement('div');
    item.className = 'layer-item';
    if (source.georeferenced === false) {
        item.classList.add('not-georeferenced');
    }

    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = name;
    radio.id = `${name}-${source.id}`;
    radio.value = source.id;
    radio.checked = checked;

    const label = document.createElement('label');
    label.htmlFor = radio.id;
    label.textContent = source.year ? `${source.name} (${source.year})` : source.name;

    item.appendChild(radio);
    item.appendChild(label);

    return item;
}

function populateReferenceSelect() {
    const select = document.getElementById('referenceSelect');
    select.innerHTML = '';

    const allSources = getAllSources();
    const categories = { basemap: [], historical: [], aerial: [] };

    allSources.forEach(source => {
        const cat = source.category || 'other';
        if (!categories[cat]) categories[cat] = [];
        categories[cat].push(source);
    });

    // Add "None" option
    const noneOption = document.createElement('option');
    noneOption.value = 'none';
    noneOption.textContent = 'None';
    if (activeReference === 'none') noneOption.selected = true;
    select.appendChild(noneOption);

    const categoryOrder = ['basemap', 'historical', 'aerial'];
    const categoryNames = { basemap: 'Basemaps', historical: 'Historical Maps', aerial: 'Aerial Photos' };

    categoryOrder.forEach(cat => {
        const items = categories[cat];
        if (!items || items.length === 0) return;

        const optgroup = document.createElement('optgroup');
        optgroup.label = categoryNames[cat];

        items.forEach(source => {
            const option = document.createElement('option');
            option.value = source.id;
            option.textContent = source.year ? `${source.name} (${source.year})` : source.name;
            if (source.georeferenced === false) {
                option.textContent += ' *';
            }
            if (source.id === activeReference) option.selected = true;
            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);
    });
}

function setupEventListeners() {
    // Focus layer radio buttons
    document.getElementById('focusList').addEventListener('change', (e) => {
        if (e.target.type === 'radio') {
            activeFocus = e.target.value;
            updateLayers();
            updateInfo();
        }
    });

    // Reference layer dropdown
    document.getElementById('referenceSelect').addEventListener('change', (e) => {
        activeReference = e.target.value;
        updateLayers();
        updateInfo();
    });

    // Opacity slider
    const opacitySlider = document.getElementById('focusOpacity');
    const opacityValue = document.getElementById('opacityValue');

    opacitySlider.addEventListener('input', (e) => {
        focusOpacity = e.target.value / 100;
        opacityValue.textContent = `${e.target.value}%`;
        if (map.getLayer('focus-layer')) {
            map.setPaintProperty('focus-layer', 'raster-opacity', focusOpacity);
        }
        // Also update georef preview if active
        if (map.getLayer('georef-preview')) {
            map.setPaintProperty('georef-preview', 'raster-opacity', focusOpacity);
        }
        // Also update image overlay opacity
        if (imageOverlay) {
            imageOverlay.style.opacity = focusOpacity;
        }
    });
}

function updateInfo() {
    const infoPanel = document.getElementById('infoPanel');
    const focusSource = getSource(activeFocus);
    const refSource = getSource(activeReference);

    let html = '';
    if (focusSource && focusSource.id !== 'none') {
        html += `<p><strong>Focus:</strong> ${focusSource.name}</p>`;
        if (focusSource.year) html += `<p>Year: ${focusSource.year}</p>`;
        if (focusSource.georeferenced === false) {
            html += `<p style="color:#f59e0b">* Not georeferenced</p>`;
            html += `<button class="georef-button" onclick="startGeoreferencing()">Georeference</button>`;
        } else if (focusSource.gcps_file) {
            // Georeferenced source with editable GCPs
            html += `<p style="color:#22c55e">✓ Georeferenced</p>`;
            html += `<button class="georef-button" onclick="editGcps('${focusSource.id}')">Edit GCPs</button>`;
        }
    }
    if (refSource && refSource.id !== 'none') {
        html += `<p><strong>Reference:</strong> ${refSource.name}</p>`;
    }
    infoPanel.innerHTML = html || '<p>Select layers to compare.</p>';
}

async function editGcps(sourceId) {
    // Find the original (non-georeferenced) source and its GCPs
    const georefSource = sources.find(s => s.id === sourceId);
    if (!georefSource || !georefSource.gcps_file) {
        alert('No GCP file found for this source');
        return;
    }

    // Load existing GCPs
    try {
        const response = await fetch('/' + georefSource.gcps_file);
        if (!response.ok) throw new Error('Failed to load GCPs');
        const gcpData = await response.json();

        // Find original source (remove _georef suffix)
        const originalId = sourceId.replace('_georef', '');
        const originalSource = sources.find(s => s.id === originalId);

        if (!originalSource) {
            alert('Original source not found');
            return;
        }

        // Switch to original source and start georeferencing with existing GCPs
        activeFocus = originalId;
        document.querySelector(`input[name="focus"][value="${originalId}"]`).checked = true;
        updateLayers();

        // Start georeferencing mode
        georefMode = true;
        georefSource = originalSource;
        gcpList = gcpData.gcps.map((gcp, i) => ({
            id: i + 1,
            imgX: gcp.pixel_x,
            imgY: gcp.pixel_y,
            mapLng: gcp.geo_x,
            mapLat: gcp.geo_y
        }));
        gcpNextId = gcpList.length + 1;
        gcpPlacementState = null;

        // Load image overlay
        loadImageOverlay(originalSource);

        // Update UI
        updateGeorefUI();

        // Place existing GCP markers after image loads
        setTimeout(() => {
            if (!imageOverlay) return;
            const img = imageOverlay.querySelector('img');
            if (!img) return;
            const rect = img.getBoundingClientRect();

            gcpList.forEach(gcp => {
                // Add image marker
                const imgMarker = document.createElement('div');
                imgMarker.className = 'gcp-marker gcp-marker-confirmed';
                imgMarker.id = `gcp-img-${gcp.id}`;
                imgMarker.textContent = gcp.id;
                imgMarker.style.left = (gcp.imgX / img.naturalWidth * rect.width) + 'px';
                imgMarker.style.top = (gcp.imgY / img.naturalHeight * rect.height) + 'px';
                imageOverlay.appendChild(imgMarker);

                // Add map marker
                const mapMarker = document.createElement('div');
                mapMarker.className = 'gcp-marker gcp-marker-map';
                mapMarker.id = `gcp-map-${gcp.id}`;
                mapMarker.textContent = gcp.id;
                new maplibregl.Marker({ element: mapMarker })
                    .setLngLat([gcp.mapLng, gcp.mapLat])
                    .addTo(map);
            });
            updateGcpList();
        }, 1000);

    } catch (error) {
        console.error('Failed to load GCPs:', error);
        alert('Failed to load GCPs: ' + error.message);
    }
}

// ==========================================
// Layer Management
// ==========================================

function getSource(id) {
    if (id === 'none') return { id: 'none', name: 'None', type: 'none' };
    const defaultOpt = DEFAULT_OPTIONS.find(o => o.id === id);
    if (defaultOpt) return defaultOpt;
    return sources.find(s => s.id === id);
}

function updateLayers() {
    if (!map.loaded()) {
        map.once('load', updateLayers);
        return;
    }

    // Remove existing layers
    ['focus-layer', 'reference-layer'].forEach(layerId => {
        if (map.getLayer(layerId)) map.removeLayer(layerId);
        if (map.getSource(layerId)) map.removeSource(layerId);
    });

    // Add reference layer first (bottom)
    const refSource = getSource(activeReference);
    if (refSource && refSource.type !== 'none') {
        addLayer(refSource, 'reference-layer', 1.0);
    }

    // Add focus layer on top
    const focusSource = getSource(activeFocus);
    if (focusSource && focusSource.type !== 'none') {
        addLayer(focusSource, 'focus-layer', focusOpacity);
    }
}

function addLayer(source, layerId, opacity) {
    if (source.type === 'vector-style') {
        // Use raster tile fallback for vector styles
        const tileUrl = source.id === 'osm_dark'
            ? 'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'
            : 'https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png';

        map.addSource(layerId, {
            type: 'raster',
            tiles: [tileUrl],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap contributors, &copy; CARTO'
        });
        map.addLayer({
            id: layerId,
            type: 'raster',
            source: layerId,
            paint: { 'raster-opacity': opacity }
        });
    } else if (source.type === 'wms') {
        const wmsUrl = `${source.url}?service=WMS&version=1.1.1&request=GetMap` +
            `&layers=${source.layer}&styles=&format=image/png&transparent=true` +
            `&srs=EPSG:3857&width=256&height=256&bbox={x},{y},{z}`;

        map.addSource(layerId, {
            type: 'raster',
            tiles: [wmsUrl],
            tileSize: 256,
            bounds: source.bounds
        });
        map.addLayer({
            id: layerId,
            type: 'raster',
            source: layerId,
            paint: { 'raster-opacity': opacity }
        });
    } else if (source.type === 'georeferenced-image' && source.corners) {
        // Georeferenced image with corner coordinates
        map.addSource(layerId, {
            type: 'image',
            url: source.path,
            coordinates: source.corners
        });
        map.addLayer({
            id: layerId,
            type: 'raster',
            source: layerId,
            paint: { 'raster-opacity': opacity }
        });
    }
}

// ==========================================
// Georeferencing Mode
// ==========================================

let georefMode = false;
let georefSource = null;
let gcpList = [];  // Array of {id, imgX, imgY, mapLng, mapLat}
let gcpNextId = 1;
let gcpPlacementState = null;  // null, 'waiting_for_image', 'waiting_for_map'
let imageOverlay = null;  // DOM element for the raw image
let imageInitialBounds = null;  // Initial rough placement
let imageDimensions = { width: 0, height: 0 };  // Store image dimensions

function startGeoreferencing() {
    const focusSource = getSource(activeFocus);
    if (!focusSource || focusSource.georeferenced !== false) {
        console.error('Cannot georeference this source');
        return;
    }

    georefMode = true;
    georefSource = focusSource;
    gcpList = [];
    gcpNextId = 1;
    gcpPlacementState = null;

    // Update UI to show georef controls
    updateGeorefUI();

    // Load and display the raw image as an overlay
    loadImageOverlay(focusSource);

    console.log('Georeferencing mode started for:', focusSource.name);
}

function stopGeoreferencing() {
    georefMode = false;
    georefSource = null;
    gcpList = [];
    gcpPlacementState = null;
    affineTransform = null;
    imageDimensions = { width: 0, height: 0 };

    // Remove image overlay
    if (imageOverlay) {
        imageOverlay.remove();
        imageOverlay = null;
    }

    // Remove preview layer
    if (map.getLayer('georef-preview')) map.removeLayer('georef-preview');
    if (map.getSource('georef-preview')) map.removeSource('georef-preview');

    // Remove GCP markers
    document.querySelectorAll('.gcp-marker').forEach(m => m.remove());

    // Restore normal UI
    updateInfo();
    const panel = document.getElementById('georefPanel');
    if (panel) panel.style.display = 'none';
}

function updateGeorefUI() {
    // Show georef panel
    let panel = document.getElementById('georefPanel');
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'georefPanel';
        panel.className = 'georef-panel';
        document.querySelector('.control-panel').appendChild(panel);
    }
    panel.style.display = 'block';

    let html = `
        <div class="panel-section">
            <h2>Georeferencing: ${georefSource.name}</h2>
            <p class="georef-hint">Click image, then click reference map to place GCP</p>
            <button class="georef-action" onclick="startGcpPlacement()">+ Add GCP</button>
            <div id="gcpListContainer"></div>
            <div id="gcpStats"></div>
            <div class="georef-actions">
                <button class="georef-action" onclick="previewTransform()" ${gcpList.length < 3 ? 'disabled' : ''}>Preview</button>
                <button class="georef-action primary" onclick="applyTransform()" ${gcpList.length < 3 ? 'disabled' : ''}>Apply</button>
                <button class="georef-action cancel" onclick="stopGeoreferencing()">Cancel</button>
            </div>
        </div>
    `;
    panel.innerHTML = html;

    updateGcpList();
}

function updateGcpList() {
    const container = document.getElementById('gcpListContainer');
    if (!container) return;

    if (gcpList.length === 0) {
        container.innerHTML = '<p class="no-gcps">No GCPs placed yet</p>';
    } else {
        let html = '<ul class="gcp-list">';
        gcpList.forEach(gcp => {
            html += `<li>
                GCP ${gcp.id}: (${gcp.imgX.toFixed(0)}, ${gcp.imgY.toFixed(0)}) →
                (${gcp.mapLng.toFixed(5)}, ${gcp.mapLat.toFixed(5)})
                <button class="gcp-delete" onclick="deleteGcp(${gcp.id})">×</button>
            </li>`;
        });
        html += '</ul>';
        container.innerHTML = html;
    }

    // Update stats
    const stats = document.getElementById('gcpStats');
    if (stats) {
        if (gcpList.length >= 3) {
            const rms = calculateRMS();
            stats.innerHTML = `<p>GCPs: ${gcpList.length} | RMS Error: ${rms.toFixed(2)}m</p>`;
        } else {
            stats.innerHTML = `<p>GCPs: ${gcpList.length} (need at least 3)</p>`;
        }
    }

    // Update button states
    const previewBtn = document.querySelector('.georef-actions button:first-child');
    const applyBtn = document.querySelector('.georef-actions button.primary');
    if (previewBtn) previewBtn.disabled = gcpList.length < 3;
    if (applyBtn) applyBtn.disabled = gcpList.length < 3;
}

function loadImageOverlay(source) {
    // Create image overlay element
    imageOverlay = document.createElement('div');
    imageOverlay.id = 'imageOverlay';
    imageOverlay.className = 'image-overlay';

    const img = document.createElement('img');
    img.src = source.path;
    img.onload = () => {
        console.log('Image loaded:', img.naturalWidth, 'x', img.naturalHeight);
        // Store dimensions for later use
        imageDimensions = { width: img.naturalWidth, height: img.naturalHeight };
        // Position initially centered on map
        positionImageOverlay();
    };
    img.onerror = () => {
        console.error('Failed to load image:', source.path);
        alert('Failed to load image. Check the path in map_sources.json');
    };

    imageOverlay.appendChild(img);
    document.getElementById('map').appendChild(imageOverlay);

    // Make overlay draggable for rough positioning
    makeOverlayDraggable(imageOverlay);

    // Add click handler for GCP placement
    imageOverlay.addEventListener('click', onImageClick);
}

function positionImageOverlay() {
    if (!imageOverlay) return;

    const img = imageOverlay.querySelector('img');
    const mapContainer = document.getElementById('map');
    const mapRect = mapContainer.getBoundingClientRect();

    // Position in center, scaled to fit
    const scale = Math.min(
        (mapRect.width * 0.6) / img.naturalWidth,
        (mapRect.height * 0.6) / img.naturalHeight
    );

    const width = img.naturalWidth * scale;
    const height = img.naturalHeight * scale;

    imageOverlay.style.width = width + 'px';
    imageOverlay.style.height = height + 'px';
    imageOverlay.style.left = (mapRect.width - width) / 2 + 'px';
    imageOverlay.style.top = (mapRect.height - height) / 2 + 'px';

    img.style.width = '100%';
    img.style.height = '100%';
}

function makeOverlayDraggable(element) {
    let isDragging = false;
    let startX, startY, startLeft, startTop;

    element.addEventListener('mousedown', (e) => {
        if (gcpPlacementState) return;  // Don't drag while placing GCP
        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;
        startLeft = element.offsetLeft;
        startTop = element.offsetTop;
        element.style.cursor = 'grabbing';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        element.style.left = (startLeft + dx) + 'px';
        element.style.top = (startTop + dy) + 'px';
    });

    document.addEventListener('mouseup', () => {
        isDragging = false;
        if (element) element.style.cursor = 'grab';
    });
}

function startGcpPlacement() {
    gcpPlacementState = 'waiting_for_image';
    if (imageOverlay) {
        imageOverlay.style.cursor = 'crosshair';
    }
    document.querySelector('.georef-hint').textContent = 'Click on the image to place first point...';
}

function onImageClick(e) {
    if (gcpPlacementState !== 'waiting_for_image') return;

    e.stopPropagation();

    // Get click position relative to image
    const img = imageOverlay.querySelector('img');
    const rect = img.getBoundingClientRect();
    const imgX = ((e.clientX - rect.left) / rect.width) * img.naturalWidth;
    const imgY = ((e.clientY - rect.top) / rect.height) * img.naturalHeight;

    // Store temporarily
    window.pendingGcp = { imgX, imgY };

    // Add visual marker on image
    const marker = document.createElement('div');
    marker.className = 'gcp-marker gcp-marker-pending';
    marker.style.left = (e.clientX - rect.left) + 'px';
    marker.style.top = (e.clientY - rect.top) + 'px';
    marker.id = 'pendingImageMarker';
    imageOverlay.appendChild(marker);

    // Now wait for map click
    gcpPlacementState = 'waiting_for_map';
    imageOverlay.style.cursor = 'default';
    map.getCanvas().style.cursor = 'crosshair';
    document.querySelector('.georef-hint').textContent = 'Now click on the reference map...';

    // Add one-time click handler to map
    map.once('click', onMapClick);
}

function onMapClick(e) {
    if (gcpPlacementState !== 'waiting_for_map') return;

    const pending = window.pendingGcp;
    if (!pending) return;

    // Create GCP
    const gcp = {
        id: gcpNextId++,
        imgX: pending.imgX,
        imgY: pending.imgY,
        mapLng: e.lngLat.lng,
        mapLat: e.lngLat.lat
    };
    gcpList.push(gcp);

    // Update pending marker to confirmed
    const pendingMarker = document.getElementById('pendingImageMarker');
    if (pendingMarker) {
        pendingMarker.id = `gcp-img-${gcp.id}`;
        pendingMarker.className = 'gcp-marker gcp-marker-confirmed';
        pendingMarker.textContent = gcp.id;
    }

    // Add marker on map
    const mapMarker = document.createElement('div');
    mapMarker.className = 'gcp-marker gcp-marker-map';
    mapMarker.id = `gcp-map-${gcp.id}`;
    mapMarker.textContent = gcp.id;
    new maplibregl.Marker({ element: mapMarker })
        .setLngLat([gcp.mapLng, gcp.mapLat])
        .addTo(map);

    // Reset state
    gcpPlacementState = null;
    window.pendingGcp = null;
    map.getCanvas().style.cursor = '';
    document.querySelector('.georef-hint').textContent = 'Click image, then click reference map to place GCP';

    updateGcpList();
}

function deleteGcp(id) {
    gcpList = gcpList.filter(g => g.id !== id);

    // Remove markers
    const imgMarker = document.getElementById(`gcp-img-${id}`);
    const mapMarker = document.getElementById(`gcp-map-${id}`);
    if (imgMarker) imgMarker.remove();
    if (mapMarker) mapMarker.remove();

    updateGcpList();
}

// Affine transform: maps image coords (x,y) to map coords (lng,lat)
// lng = a*x + b*y + c
// lat = d*x + e*y + f
let affineTransform = null;

function calculateAffineTransform() {
    if (gcpList.length < 3) return null;

    const n = gcpList.length;

    // Build matrices for least squares: A * params = B
    // For lng: [x, y, 1] * [a, b, c]^T = lng
    // For lat: [x, y, 1] * [d, e, f]^T = lat

    let sumX = 0, sumY = 0, sumX2 = 0, sumY2 = 0, sumXY = 0;
    let sumLng = 0, sumLat = 0;
    let sumXLng = 0, sumYLng = 0, sumXLat = 0, sumYLat = 0;

    gcpList.forEach(gcp => {
        sumX += gcp.imgX;
        sumY += gcp.imgY;
        sumX2 += gcp.imgX * gcp.imgX;
        sumY2 += gcp.imgY * gcp.imgY;
        sumXY += gcp.imgX * gcp.imgY;
        sumLng += gcp.mapLng;
        sumLat += gcp.mapLat;
        sumXLng += gcp.imgX * gcp.mapLng;
        sumYLng += gcp.imgY * gcp.mapLng;
        sumXLat += gcp.imgX * gcp.mapLat;
        sumYLat += gcp.imgY * gcp.mapLat;
    });

    // Solve using normal equations (A^T * A) * params = A^T * B
    // Matrix: [[sumX2, sumXY, sumX], [sumXY, sumY2, sumY], [sumX, sumY, n]]
    const det = sumX2 * (sumY2 * n - sumY * sumY)
              - sumXY * (sumXY * n - sumY * sumX)
              + sumX * (sumXY * sumY - sumY2 * sumX);

    if (Math.abs(det) < 1e-10) return null;

    // Inverse of 3x3 matrix multiplied by right-hand side
    const invDet = 1 / det;

    // Cofactors for inverse
    const c00 = sumY2 * n - sumY * sumY;
    const c01 = -(sumXY * n - sumY * sumX);
    const c02 = sumXY * sumY - sumY2 * sumX;
    const c10 = -(sumXY * n - sumX * sumY);
    const c11 = sumX2 * n - sumX * sumX;
    const c12 = -(sumX2 * sumY - sumXY * sumX);
    const c20 = sumXY * sumY - sumX * sumY2;
    const c21 = -(sumX2 * sumY - sumX * sumXY);
    const c22 = sumX2 * sumY2 - sumXY * sumXY;

    // Solve for lng params (a, b, c)
    const a = invDet * (c00 * sumXLng + c01 * sumYLng + c02 * sumLng);
    const b = invDet * (c10 * sumXLng + c11 * sumYLng + c12 * sumLng);
    const c = invDet * (c20 * sumXLng + c21 * sumYLng + c22 * sumLng);

    // Solve for lat params (d, e, f)
    const d = invDet * (c00 * sumXLat + c01 * sumYLat + c02 * sumLat);
    const e = invDet * (c10 * sumXLat + c11 * sumYLat + c12 * sumLat);
    const f = invDet * (c20 * sumXLat + c21 * sumYLat + c22 * sumLat);

    return { a, b, c, d, e, f };
}

function transformPoint(imgX, imgY, transform) {
    return {
        lng: transform.a * imgX + transform.b * imgY + transform.c,
        lat: transform.d * imgX + transform.e * imgY + transform.f
    };
}

function calculateRMS() {
    if (gcpList.length < 3) return 0;

    const transform = calculateAffineTransform();
    if (!transform) return 0;

    let sumSqError = 0;
    gcpList.forEach(gcp => {
        const predicted = transformPoint(gcp.imgX, gcp.imgY, transform);
        // Convert to approximate meters (rough approximation at this latitude)
        const dLng = (predicted.lng - gcp.mapLng) * 111320 * Math.cos(gcp.mapLat * Math.PI / 180);
        const dLat = (predicted.lat - gcp.mapLat) * 110540;
        sumSqError += dLng * dLng + dLat * dLat;
    });

    return Math.sqrt(sumSqError / gcpList.length);
}

function previewTransform() {
    if (gcpList.length < 3) {
        alert('Need at least 3 GCPs');
        return;
    }

    const transform = calculateAffineTransform();
    if (!transform) {
        alert('Could not calculate transform');
        return;
    }

    affineTransform = transform;
    console.log('Affine transform:', transform);

    // Get image dimensions
    const img = imageOverlay.querySelector('img');
    const imgWidth = img.naturalWidth;
    const imgHeight = img.naturalHeight;

    // Calculate corner coordinates
    const topLeft = transformPoint(0, 0, transform);
    const topRight = transformPoint(imgWidth, 0, transform);
    const bottomRight = transformPoint(imgWidth, imgHeight, transform);
    const bottomLeft = transformPoint(0, imgHeight, transform);

    console.log('Corners:', { topLeft, topRight, bottomRight, bottomLeft });

    // Hide the draggable overlay
    imageOverlay.style.display = 'none';

    // Remove existing preview
    if (map.getLayer('georef-preview')) map.removeLayer('georef-preview');
    if (map.getSource('georef-preview')) map.removeSource('georef-preview');

    // Add as MapLibre image source
    map.addSource('georef-preview', {
        type: 'image',
        url: img.src,
        coordinates: [
            [topLeft.lng, topLeft.lat],
            [topRight.lng, topRight.lat],
            [bottomRight.lng, bottomRight.lat],
            [bottomLeft.lng, bottomLeft.lat]
        ]
    });

    map.addLayer({
        id: 'georef-preview',
        type: 'raster',
        source: 'georef-preview',
        paint: { 'raster-opacity': 0.7 }
    });

    // Update hint
    document.querySelector('.georef-hint').textContent = 'Preview shown. Click Apply to save, or add more GCPs.';
}

async function applyTransform() {
    if (gcpList.length < 3) {
        alert('Need at least 3 GCPs');
        return;
    }

    const transform = affineTransform || calculateAffineTransform();
    if (!transform) {
        alert('Could not calculate transform');
        return;
    }

    // Prepare GCP data for backend (use stored dimensions)
    const gcpData = {
        source_id: georefSource.id,
        source_path: georefSource.path,
        image_width: imageDimensions.width,
        image_height: imageDimensions.height,
        gcps: gcpList.map(gcp => ({
            img_x: gcp.imgX,
            img_y: gcp.imgY,
            map_lng: gcp.mapLng,
            map_lat: gcp.mapLat
        })),
        transform: transform
    };

    console.log('Sending GCP data to backend:', gcpData);

    try {
        const response = await fetch('/api/georeference', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(gcpData)
        });

        if (!response.ok) {
            let errorMsg = `Server error: ${response.status}`;
            try {
                const error = await response.json();
                errorMsg = error.detail || errorMsg;
            } catch (e) {
                // Response wasn't JSON, try text
                const text = await response.text();
                errorMsg = text || errorMsg;
            }
            throw new Error(errorMsg);
        }

        const result = await response.json();
        console.log('Georeference result:', result);

        alert(`Georeferencing complete!\nOutput: ${result.output_path}\nRMS: ${result.rms.toFixed(2)}m`);

        // Reload sources to show the new georeferenced layer
        await loadSources();
        populateFocusRadios();
        populateReferenceSelect();

        stopGeoreferencing();

    } catch (error) {
        console.error('Georeference failed:', error);
        alert('Georeference failed: ' + error.message);
    }
}

// ==========================================
// Start
// ==========================================

document.addEventListener('DOMContentLoaded', init);
