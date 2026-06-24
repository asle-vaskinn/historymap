/**
 * Data Source Viewer
 * Multi-layer viewer for comparing historical maps and data sources
 */

// ==========================================
// Configuration
// ==========================================

// Background map styles
const BACKGROUND_STYLES = {
    none: null,
    positron: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
    dark: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
};

// Raster map sources (WMS-based historical maps and aerial photos)
// URLs use local proxy to avoid CORS issues
const RASTER_SOURCES = {
    amt1: {
        name: 'Amtskart (1870-1920)',
        year: 1900,
        bounds: [10.30, 63.38, 10.50, 63.48],
        type: 'wms',
        url: '/wms/geonorge/wms.historiskekart',
        layers: 'amt1',
        attribution: '© Kartverket'
    },
    // Note: kv1904 layer removed - not available in Geonorge WMS
    ortofoto1937: {
        name: 'Flyfoto 1937',
        year: 1937,
        bounds: [10.38, 63.42, 10.44, 63.45],
        type: 'wms',
        url: '/wms/trondheim/Raster/wms',
        layers: 'ortofoto1937',
        attribution: '© Trondheim kommune'
    },
    ortofoto2006: {
        name: 'Flyfoto 2006',
        year: 2006,
        bounds: [10.30, 63.38, 10.50, 63.48],
        type: 'wms',
        url: '/wms/trondheim/Raster/wms',
        layers: 'ortofoto2006',
        attribution: '© Trondheim kommune'
    },
    ortofoto2023: {
        name: 'Flyfoto 2023',
        year: 2023,
        bounds: [10.30, 63.38, 10.50, 63.48],
        type: 'wms',
        url: '/wms/trondheim/Raster/wms',
        layers: 'ortofoto2023',
        attribution: '© Trondheim kommune'
    }
};

// Data layer sources (GeoJSON files)
const DATA_SOURCES = {
    sefrak: {
        name: 'SEFRAK Buildings',
        path: 'data/sources/sefrak/normalized/buildings.geojson',
        type: 'buildings',
        color: '#22c55e',  // Green
        outlineColor: '#166534'
    },
    osm: {
        name: 'OSM Buildings',
        path: 'data/sources/ml_detected/ortofoto1937/osm_cache.geojson',
        type: 'buildings',
        color: '#06b6d4',  // Cyan
        outlineColor: '#0891b2'
    },
    ml: {
        name: 'ML Detected',
        path: 'data/sources/ml_detected/ortofoto1937/verified_buildings.geojson',
        type: 'buildings',
        color: '#f59e0b',  // Amber
        outlineColor: '#d97706'
    },
    manual: {
        name: 'Manual Buildings',
        path: 'data/sources/manual/buildings.geojson',
        type: 'buildings',
        color: '#a855f7',  // Purple
        outlineColor: '#7c3aed'
    },
    roads: {
        name: 'Historical Roads',
        path: 'data/sources/ml_detected/kartverket_1880/roads/roads.geojson',
        type: 'roads',
        color: '#FF6B6B',
        outlineColor: '#8B0000'
    },
    water: {
        name: 'Water Features',
        paths: {
            osm: 'data/sources/osm/water.geojson',
            manual: 'data/sources/manual/water.geojson'
        },
        type: 'water'
    },
    finn: {
        name: 'Finn.no Listings',
        path: 'data/sources/finn/listings.geojson',
        type: 'points',
        color: '#ec4899',  // Pink
        icon: 'marker'
    },
    hist1904: {
        name: '1904 Detected',
        path: 'data/matched_1904/historical_buildings.geojson',
        type: 'buildings',
        color: '#dc2626',  // Red - for historical/demolished
        outlineColor: '#991b1b'
    }
};

// Legacy compatibility - kept for existing code
const SOURCES = {
    amt1: { ...RASTER_SOURCES.amt1, raster: RASTER_SOURCES.amt1 },
    ortofoto1937: { ...RASTER_SOURCES.ortofoto1937, raster: RASTER_SOURCES.ortofoto1937, verificationMode: true },
    ortofoto2006: { ...RASTER_SOURCES.ortofoto2006, raster: RASTER_SOURCES.ortofoto2006 },
    ortofoto2023: { ...RASTER_SOURCES.ortofoto2023, raster: RASTER_SOURCES.ortofoto2023 }
};

const BASE_MAP_STYLE = BACKGROUND_STYLES.positron;

// Water sources
const WATER_SOURCES = {
    osm: 'data/sources/osm/water.geojson',        // Current OSM water
    manual: 'data/sources/manual/water.geojson'   // Historical water edits
};

// OSM buildings cache (used for alignment comparison)
const OSM_BUILDINGS_CACHE = 'data/sources/ml_detected/ortofoto1937/osm_cache.geojson';

// Trondheim center
const DEFAULT_CENTER = [10.40, 63.43];
const DEFAULT_ZOOM = 13;

// Water type colors
const WATER_TYPE_COLORS = {
    fjord: '#0077be',
    river: '#4a90d9',
    lake: '#5da5da',
    canal: '#7ec8e3',
    harbor: '#2c5f8a'
};

// ==========================================
// State
// ==========================================

let map = null;

// Layer state
const layerState = {
    background: 'positron',      // Current background (none, positron, dark, or raster ID)
    overlay: 'none',             // Current overlay raster (none or raster ID)
    overlayOpacity: 0.7,         // Overlay opacity (0-1)
    dataLayers: {                // Data layer visibility and opacity (input sources only)
        sefrak: { visible: false, opacity: 0.8 },
        osm: { visible: true, opacity: 0.6 },
        ml: { visible: false, opacity: 0.7 },
        manual: { visible: false, opacity: 0.8 },
        roads: { visible: false, opacity: 0.8 },
        finn: { visible: false, opacity: 0.8 },
        hist1904: { visible: false, opacity: 0.8 }
    }
};

// Cached data
const dataCache = {};  // layerId -> GeoJSON data
let waterData = null;  // OSM water baseline
let manualWaterData = null;  // Manual/historical water edits

// Legacy state (for annotation system)
let currentSource = 'amt1';
let buildingsData = null;
let roadsData = null;
let osmBuildingsData = null;
let showOsmBuildings = true;
let annotations = {};
let waterAnnotations = {};
let annotationPopup = null;
let ws = null;
let currentJob = null;
let draw = null;
let waterEditMode = false;

// Source ID mapping from main app to source viewer
const SOURCE_ID_MAP = {
    'kv1880': 'amt1',
    'kv1904': 'kv1904',
    'air1947': 'ortofoto1937'
};

// Reverse mapping: source viewer ID to main app snapshot ID
const REVERSE_SOURCE_MAP = {
    'amt1': 'kv1880',
    'kv1904': 'kv1904',
    'ortofoto1937': 'air1947',
    'ortofoto2006': null,
    'ortofoto2023': null
};

// Initialize
document.addEventListener('DOMContentLoaded', init);

async function init() {
    // Check for URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const sourceParam = urlParams.get('source');
    const bgParam = urlParams.get('bg');
    const overlayParam = urlParams.get('overlay');

    // Apply URL parameters to layer state
    if (bgParam && (BACKGROUND_STYLES[bgParam] !== undefined || RASTER_SOURCES[bgParam])) {
        layerState.background = bgParam;
    }
    if (overlayParam && (overlayParam === 'none' || RASTER_SOURCES[overlayParam])) {
        layerState.overlay = overlayParam;
    }
    if (sourceParam) {
        // Legacy source param - set as overlay
        const mappedSource = SOURCE_ID_MAP[sourceParam] || sourceParam;
        if (RASTER_SOURCES[mappedSource]) {
            layerState.overlay = mappedSource;
        }
    }

    // Initialize map with empty style
    map = new maplibregl.Map({
        container: 'map',
        style: {
            version: 8,
            sources: {},
            layers: [{
                id: 'background',
                type: 'background',
                paint: { 'background-color': '#1a1a2e' }
            }]
        },
        center: DEFAULT_CENTER,
        zoom: DEFAULT_ZOOM,
        // Transform WMS requests to convert XYZ to bbox
        transformRequest: (url, resourceType) => {
            // Check if this is our WMS XYZ request pattern
            if (resourceType === 'Tile' && url.includes('bbox=') && url.includes('request=GetMap')) {
                // Extract x, y, z from URL pattern bbox={x},{y},{z}
                const match = url.match(/bbox=(\d+),(\d+),(\d+)/);
                if (match) {
                    const x = parseInt(match[1]);
                    const y = parseInt(match[2]);
                    const z = parseInt(match[3]);

                    // Convert XYZ to EPSG:3857 bbox
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

    map.on('load', async () => {
        // Setup layer control event handlers
        setupLayerControls();

        // Load initial layers
        await refreshAllLayers();

        // Legacy handlers
        setupAnnotationHandlers();
        fetchStatus();
        connectWebSocket();
    });

    // Sync UI with layer state
    syncUIWithState();
}

/**
 * Setup event handlers for layer control panel
 */
function setupLayerControls() {
    // Background layer radio buttons
    document.querySelectorAll('input[name="background"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            layerState.background = e.target.value;
            refreshBackgroundLayer();
            updateURL();
        });
    });

    // Overlay layer radio buttons
    document.querySelectorAll('input[name="overlay"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            layerState.overlay = e.target.value;
            refreshOverlayLayer();
            updateURL();
        });
    });

    // Overlay opacity slider
    const overlayOpacitySlider = document.getElementById('overlayOpacity');
    if (overlayOpacitySlider) {
        overlayOpacitySlider.addEventListener('input', (e) => {
            const opacity = parseInt(e.target.value) / 100;
            layerState.overlayOpacity = opacity;
            document.getElementById('overlayOpacityValue').textContent = `${e.target.value}%`;
            updateOverlayOpacity();
        });
    }

    // Data layer checkboxes
    document.querySelectorAll('input[name="dataLayer"]').forEach(checkbox => {
        checkbox.addEventListener('change', (e) => {
            const layerId = e.target.value;
            layerState.dataLayers[layerId].visible = e.target.checked;
            refreshDataLayer(layerId);
        });
    });

    // Data layer opacity sliders
    document.querySelectorAll('.mini-slider').forEach(slider => {
        slider.addEventListener('input', (e) => {
            const layerId = e.target.dataset.layer;
            const opacity = parseInt(e.target.value) / 100;
            layerState.dataLayers[layerId].opacity = opacity;
            updateDataLayerOpacity(layerId);
        });
    });
}

/**
 * Sync UI controls with current layer state
 */
function syncUIWithState() {
    // Background radios
    const bgRadio = document.querySelector(`input[name="background"][value="${layerState.background}"]`);
    if (bgRadio) bgRadio.checked = true;

    // Overlay radios
    const overlayRadio = document.querySelector(`input[name="overlay"][value="${layerState.overlay}"]`);
    if (overlayRadio) overlayRadio.checked = true;

    // Overlay opacity
    const overlaySlider = document.getElementById('overlayOpacity');
    if (overlaySlider) {
        overlaySlider.value = Math.round(layerState.overlayOpacity * 100);
        document.getElementById('overlayOpacityValue').textContent = `${overlaySlider.value}%`;
    }

    // Data layer checkboxes and sliders
    Object.entries(layerState.dataLayers).forEach(([layerId, state]) => {
        const checkbox = document.querySelector(`input[name="dataLayer"][value="${layerId}"]`);
        if (checkbox) checkbox.checked = state.visible;

        const slider = document.querySelector(`.mini-slider[data-layer="${layerId}"]`);
        if (slider) slider.value = Math.round(state.opacity * 100);
    });
}

/**
 * Update URL to reflect current layer state
 */
function updateURL() {
    const url = new URL(window.location);
    if (layerState.background !== 'positron') {
        url.searchParams.set('bg', layerState.background);
    } else {
        url.searchParams.delete('bg');
    }
    if (layerState.overlay !== 'none') {
        url.searchParams.set('overlay', layerState.overlay);
    } else {
        url.searchParams.delete('overlay');
    }
    window.history.replaceState({}, '', url);
}

// ==========================================
// Layer Management Functions
// ==========================================

/**
 * Refresh all layers (called on init)
 */
async function refreshAllLayers() {
    await refreshBackgroundLayer();
    await refreshOverlayLayer();

    // Load all data layers
    for (const layerId of Object.keys(layerState.dataLayers)) {
        if (layerState.dataLayers[layerId].visible) {
            await refreshDataLayer(layerId);
        }
    }

    // Load water features (displayed in right panel)
    await loadWaterData();
    addWaterLayers(0.5);

    updateStats();
}

/**
 * Refresh background layer (opaque base map or aerial)
 */
async function refreshBackgroundLayer() {
    // Remove existing background layers
    removeLayerIfExists('background-raster');
    removeSourceIfExists('background-raster');
    removeLayerIfExists('background-tiles');
    removeSourceIfExists('background-tiles');

    const bgId = layerState.background;

    if (bgId === 'none') {
        return;
    }

    // Check if it's a vector tile style (positron, dark)
    if (bgId === 'positron' || bgId === 'dark') {
        // Use CARTO's raster tile endpoint
        let tileUrl;
        if (bgId === 'positron') {
            tileUrl = 'https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png';
        } else if (bgId === 'dark') {
            tileUrl = 'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png';
        }

        map.addSource('background-tiles', {
            type: 'raster',
            tiles: [
                tileUrl,
                tileUrl.replace('://a.', '://b.'),
                tileUrl.replace('://a.', '://c.')
            ],
            tileSize: 256,
            attribution: '© CARTO © OpenStreetMap contributors'
        });

        map.addLayer({
            id: 'background-tiles',
            type: 'raster',
            source: 'background-tiles',
            paint: { 'raster-opacity': 1 }
        }, findFirstDataLayer());
        return;
    }

    // Raster background (aerial photo from WMS)
    if (RASTER_SOURCES[bgId]) {
        const source = RASTER_SOURCES[bgId];
        addWMSLayer('background-raster', source, 1.0);
    }
}

/**
 * Refresh overlay layer (semi-transparent map)
 */
async function refreshOverlayLayer() {
    removeLayerIfExists('overlay-raster');
    removeSourceIfExists('overlay-raster');

    const overlayId = layerState.overlay;

    if (overlayId === 'none') {
        return;
    }

    if (RASTER_SOURCES[overlayId]) {
        const source = RASTER_SOURCES[overlayId];
        addWMSLayer('overlay-raster', source, layerState.overlayOpacity);
    }
}

/**
 * Update overlay layer opacity
 */
function updateOverlayOpacity() {
    if (map.getLayer('overlay-raster')) {
        map.setPaintProperty('overlay-raster', 'raster-opacity', layerState.overlayOpacity);
    }
}

/**
 * Refresh a specific data layer
 */
async function refreshDataLayer(layerId) {
    const state = layerState.dataLayers[layerId];
    const config = DATA_SOURCES[layerId];

    if (!config) {
        console.warn(`Unknown data layer: ${layerId}`);
        return;
    }

    // Remove existing layers for this data source
    removeDataLayerFromMap(layerId);

    if (!state.visible) {
        return;
    }

    // Load data if not cached
    if (!dataCache[layerId]) {
        await loadDataSource(layerId);
    }

    // Add layer based on type
    if (config.type === 'buildings') {
        addBuildingsLayer(layerId, dataCache[layerId], config, state.opacity);
    } else if (config.type === 'roads') {
        addRoadsLayer(layerId, dataCache[layerId], config, state.opacity);
    } else if (config.type === 'water') {
        await loadWaterData();
        addWaterLayers(state.opacity);
    } else if (config.type === 'points') {
        addPointsLayer(layerId, dataCache[layerId], config, state.opacity);
    }
}

/**
 * Update data layer opacity
 */
function updateDataLayerOpacity(layerId) {
    const state = layerState.dataLayers[layerId];
    const config = DATA_SOURCES[layerId];

    if (!state.visible || !config) return;

    if (config.type === 'buildings') {
        if (map.getLayer(`${layerId}-fill`)) {
            map.setPaintProperty(`${layerId}-fill`, 'fill-opacity', state.opacity);
        }
    } else if (config.type === 'roads') {
        if (map.getLayer(`${layerId}-line`)) {
            map.setPaintProperty(`${layerId}-line`, 'line-opacity', state.opacity);
        }
    } else if (config.type === 'water') {
        if (map.getLayer('water-osm-fill')) {
            map.setPaintProperty('water-osm-fill', 'fill-opacity', state.opacity);
        }
        if (map.getLayer('water-manual-fill')) {
            map.setPaintProperty('water-manual-fill', 'fill-opacity', state.opacity);
        }
    } else if (config.type === 'points') {
        if (map.getLayer(`${layerId}-circle`)) {
            map.setPaintProperty(`${layerId}-circle`, 'circle-opacity', state.opacity);
        }
    }
}

/**
 * Load data source GeoJSON
 */
async function loadDataSource(layerId) {
    const config = DATA_SOURCES[layerId];
    if (!config || !config.path) {
        return null;
    }

    try {
        const response = await fetch(config.path);
        if (response.ok) {
            const data = await response.json();
            dataCache[layerId] = data;
            return data;
        } else {
            // Data file not found - use empty collection
            dataCache[layerId] = { type: 'FeatureCollection', features: [] };
        }
    } catch (err) {
        // Network error - use empty collection
        dataCache[layerId] = { type: 'FeatureCollection', features: [] };
    }
    return dataCache[layerId];
}

/**
 * Add WMS raster layer using XYZ tile scheme with client-side bbox conversion
 */
function addWMSLayer(id, source, opacity) {
    const baseUrl = source.url;

    // Use XYZ tile scheme - transformRequest converts to WMS bbox
    const wmsUrl = `${baseUrl}?service=WMS&version=1.1.1&request=GetMap` +
        `&layers=${source.layers}&styles=&format=image/png` +
        `&srs=EPSG:3857&width=256&height=256&bbox={x},{y},{z}`;

    map.addSource(id, {
        type: 'raster',
        tiles: [wmsUrl],
        tileSize: 256,
        bounds: source.bounds,
        attribution: source.attribution
    });

    // Find the right position for the layer
    const beforeLayer = findFirstDataLayer();

    map.addLayer({
        id: id,
        type: 'raster',
        source: id,
        paint: { 'raster-opacity': opacity }
    }, beforeLayer);
}

/**
 * Add buildings layer (fill + outline)
 */
function addBuildingsLayer(layerId, data, config, opacity) {
    if (!data || !data.features?.length) return;

    map.addSource(layerId, {
        type: 'geojson',
        data: data
    });

    // Fill layer
    map.addLayer({
        id: `${layerId}-fill`,
        type: 'fill',
        source: layerId,
        paint: {
            'fill-color': config.color,
            'fill-opacity': opacity
        }
    });

    // Outline layer
    map.addLayer({
        id: `${layerId}-outline`,
        type: 'line',
        source: layerId,
        paint: {
            'line-color': config.outlineColor,
            'line-width': 1
        }
    });
}

/**
 * Add roads layer (line)
 */
function addRoadsLayer(layerId, data, config, opacity) {
    if (!data || !data.features?.length) return;

    map.addSource(layerId, {
        type: 'geojson',
        data: data
    });

    // Road outline
    map.addLayer({
        id: `${layerId}-outline`,
        type: 'line',
        source: layerId,
        paint: {
            'line-color': config.outlineColor,
            'line-width': 4,
            'line-opacity': opacity * 0.6
        }
    });

    // Road line
    map.addLayer({
        id: `${layerId}-line`,
        type: 'line',
        source: layerId,
        paint: {
            'line-color': config.color,
            'line-width': 2,
            'line-opacity': opacity
        }
    });
}

/**
 * Add points layer (for finn.no listings etc)
 */
function addPointsLayer(layerId, data, config, opacity) {
    if (!data || !data.features?.length) return;

    map.addSource(layerId, {
        type: 'geojson',
        data: data
    });

    map.addLayer({
        id: `${layerId}-circle`,
        type: 'circle',
        source: layerId,
        paint: {
            'circle-radius': 6,
            'circle-color': config.color,
            'circle-opacity': opacity,
            'circle-stroke-width': 2,
            'circle-stroke-color': '#ffffff'
        }
    });
}

/**
 * Remove data layer from map
 */
function removeDataLayerFromMap(layerId) {
    const config = DATA_SOURCES[layerId];
    if (!config) return;

    if (config.type === 'buildings') {
        removeLayerIfExists(`${layerId}-fill`);
        removeLayerIfExists(`${layerId}-outline`);
        removeSourceIfExists(layerId);
    } else if (config.type === 'roads') {
        removeLayerIfExists(`${layerId}-line`);
        removeLayerIfExists(`${layerId}-outline`);
        removeSourceIfExists(layerId);
    } else if (config.type === 'water') {
        removeLayerIfExists('water-osm-fill');
        removeLayerIfExists('water-osm-outline');
        removeLayerIfExists('water-manual-fill');
        removeLayerIfExists('water-manual-outline');
        removeSourceIfExists('water-osm');
        removeSourceIfExists('water-manual');
    } else if (config.type === 'points') {
        removeLayerIfExists(`${layerId}-circle`);
        removeSourceIfExists(layerId);
    }
}

/**
 * Helper: Remove layer if it exists
 */
function removeLayerIfExists(id) {
    if (map.getLayer(id)) {
        map.removeLayer(id);
    }
}

/**
 * Helper: Remove source if it exists
 */
function removeSourceIfExists(id) {
    if (map.getSource(id)) {
        map.removeSource(id);
    }
}

/**
 * Helper: Find first data layer (for layer ordering)
 */
function findFirstDataLayer() {
    const dataLayerPrefixes = ['sefrak', 'osm', 'ml', 'manual', 'roads', 'water', 'finn'];
    for (const prefix of dataLayerPrefixes) {
        const fillLayer = `${prefix}-fill`;
        const lineLayer = `${prefix}-line`;
        const circleLayer = `${prefix}-circle`;
        if (map.getLayer(fillLayer)) return fillLayer;
        if (map.getLayer(lineLayer)) return lineLayer;
        if (map.getLayer(circleLayer)) return circleLayer;
    }
    return undefined;
}

/**
 * Update stats display
 */
function updateStats() {
    let totalFeatures = 0;
    const parts = [];

    Object.entries(layerState.dataLayers).forEach(([layerId, state]) => {
        if (state.visible && dataCache[layerId]) {
            const count = dataCache[layerId].features?.length || 0;
            if (count > 0) {
                parts.push(`${count} ${layerId}`);
                totalFeatures += count;
            }
        }
    });

    const statsEl = document.getElementById('stats');
    if (statsEl) {
        if (parts.length > 0) {
            statsEl.textContent = parts.join(', ');
        } else {
            statsEl.textContent = 'No data layers visible';
        }
    }
}

/**
 * Update the "View on Map" link based on current source
 */
function updateViewOnMapLink(sourceId) {
    const link = document.getElementById('viewOnMapLink');
    if (!link) return;

    const snapshotId = REVERSE_SOURCE_MAP[sourceId];
    if (snapshotId) {
        link.href = `index.html?snapshot=${snapshotId}`;
        link.style.display = 'inline';
    } else {
        // No corresponding snapshot in main app
        link.href = 'index.html';
        link.style.display = 'none';
    }
}

async function loadSource(sourceId) {
    currentSource = sourceId;
    const source = SOURCES[sourceId];

    console.log('Loading source:', sourceId, source);

    if (!source) {
        console.error('Source not found:', sourceId);
        return;
    }

    document.getElementById('stats').textContent = 'Loading...';
    document.getElementById('annotationCount').textContent = '0 annotated';  // Reset annotation count

    // Load buildings GeoJSON (if available)
    if (source.buildings) {
        try {
            console.log('Fetching buildings from:', source.buildings);
            const response = await fetch(source.buildings);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            buildingsData = await response.json();
            console.log('Buildings loaded:', buildingsData.features?.length || 0, 'features');

            const count = buildingsData.features?.length || 0;

            // Show verification stats if available
            if (source.verificationMode && buildingsData.metadata?.stats) {
                const s = buildingsData.metadata.stats;
                const existed = (s.existed_high_conf || 0) + (s.existed_low_conf || 0);
                const notExisted = (s.not_existed_high_conf || 0) + (s.not_existed_low_conf || 0);
                const lowConf = (s.existed_low_conf || 0) + (s.not_existed_low_conf || 0);
                document.getElementById('stats').innerHTML =
                    `<span style="color:#22c55e">${existed}</span> / ` +
                    `<span style="color:#eab308">${lowConf}</span> / ` +
                    `<span style="color:#ef4444">${notExisted}</span> ` +
                    `<span style="color:#888">(${count} total)</span>`;
            } else {
                document.getElementById('stats').textContent = `${count} buildings`;
            }
        } catch (err) {
            console.error('Failed to load buildings:', err);
            document.getElementById('stats').textContent = 'No buildings data';
            buildingsData = null;
        }
    } else {
        buildingsData = null;
        document.getElementById('stats').textContent = `${source.name} (${source.year})`;
    }

    // Load roads GeoJSON (if available)
    if (source.roads) {
        try {
            console.log('Fetching roads from:', source.roads);
            const response = await fetch(source.roads);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            roadsData = await response.json();
            const roadCount = roadsData.features?.length || 0;
            console.log('Roads loaded:', roadCount, 'segments');

            // Update stats to include roads
            const buildingCount = buildingsData?.features?.length || 0;
            document.getElementById('stats').textContent = `${buildingCount} buildings, ${roadCount} roads`;
        } catch (err) {
            console.error('Failed to load roads:', err);
            roadsData = null;
        }
    } else {
        roadsData = null;
    }

    // Always load water data (OSM baseline + manual edits)
    await loadWaterData();

    // Load OSM buildings for comparison
    await loadOsmBuildings();

    // Setup layers for current view
    setupLayers();

    // Fit to bounds
    if (source.bounds) {
        map.fitBounds([
            [source.bounds[0], source.bounds[1]],
            [source.bounds[2], source.bounds[3]]
        ], { padding: 50 });
    }
}

/**
 * Load water data from OSM and manual sources
 */
async function loadWaterData() {
    // Load OSM water baseline
    try {
        const response = await fetch(WATER_SOURCES.osm);
        if (response.ok) {
            waterData = await response.json();
            console.log('OSM water loaded:', waterData.features?.length || 0, 'features');
        } else {
            waterData = { type: 'FeatureCollection', features: [] };
        }
    } catch (err) {
        console.error('Failed to load OSM water:', err);
        waterData = { type: 'FeatureCollection', features: [] };
    }

    // Load manual water edits
    try {
        const response = await fetch(WATER_SOURCES.manual);
        if (response.ok) {
            manualWaterData = await response.json();
            console.log('Manual water loaded:', manualWaterData.features?.length || 0, 'features');
        } else {
            manualWaterData = { type: 'FeatureCollection', features: [] };
        }
    } catch (err) {
        console.error('Failed to load manual water:', err);
        manualWaterData = { type: 'FeatureCollection', features: [] };
    }

    // Update stats
    updateWaterStats();
}

/**
 * Load OSM buildings for comparison overlay
 */
async function loadOsmBuildings() {
    try {
        const response = await fetch(OSM_BUILDINGS_CACHE);
        if (response.ok) {
            osmBuildingsData = await response.json();
            console.log('OSM buildings loaded:', osmBuildingsData.features?.length || 0, 'features');
        } else {
            osmBuildingsData = { type: 'FeatureCollection', features: [] };
        }
    } catch (err) {
        console.error('Failed to load OSM buildings:', err);
        osmBuildingsData = { type: 'FeatureCollection', features: [] };
    }
}

/**
 * Update water feature statistics in UI
 */
function updateWaterStats() {
    const osmCount = waterData?.features?.length || 0;
    const manualCount = manualWaterData?.features?.length || 0;
    const waterStatsEl = document.getElementById('waterStats');
    if (waterStatsEl) {
        waterStatsEl.textContent = `${osmCount} OSM, ${manualCount} historical`;
    }
}

function setupLayers() {
    const source = SOURCES[currentSource];
    if (!source) return;

    // Remove existing layers and sources
    const layersToRemove = ['raster-0', 'raster-1', 'raster-2', 'raster-3',
                           'buildings-overlay', 'buildings-annotation-border',
                           'osm-buildings-fill', 'osm-buildings-outline',
                           'roads-overlay', 'roads-outline',
                           'water-osm-fill', 'water-osm-outline',
                           'water-manual-fill', 'water-manual-outline'];
    layersToRemove.forEach(id => {
        if (map.getLayer(id)) map.removeLayer(id);
    });

    const sourcesToRemove = ['raster-0', 'raster-1', 'raster-2', 'raster-3', 'buildings', 'osm-buildings', 'roads',
                            'water-osm', 'water-manual'];
    sourcesToRemove.forEach(id => {
        if (map.getSource(id)) map.removeSource(id);
    });

    // Always show aerial photo/raster
    addRasterLayers(source);

    // Add OSM buildings as comparison layer (under ML buildings)
    if (osmBuildingsData && osmBuildingsData.features?.length > 0 && showOsmBuildings) {
        map.addSource('osm-buildings', {
            type: 'geojson',
            data: osmBuildingsData
        });

        // OSM buildings fill - cyan/blue to contrast with ML (orange/green/red)
        map.addLayer({
            id: 'osm-buildings-fill',
            type: 'fill',
            source: 'osm-buildings',
            paint: {
                'fill-color': '#06b6d4',  // Cyan for OSM
                'fill-opacity': 0.25
            }
        });

        // OSM buildings outline
        map.addLayer({
            id: 'osm-buildings-outline',
            type: 'line',
            source: 'osm-buildings',
            paint: {
                'line-color': '#0891b2',  // Darker cyan
                'line-width': 1
            }
        });
    }

    // Overlay buildings if available (unified view)
    if (buildingsData) {
        // Apply saved annotations to feature properties before adding source
        applyAnnotationsToFeatures();

        map.addSource('buildings', {
            type: 'geojson',
            data: buildingsData
        });

        const isVerificationMode = source.verificationMode === true;
        const isGeneratedMode = source.generatedMode === true;

        if (isGeneratedMode) {
            // Generated buildings styling - amber/orange with hatched appearance
            map.addLayer({
                id: 'buildings-overlay',
                type: 'fill',
                source: 'buildings',
                paint: {
                    'fill-color': '#f59e0b',  // Amber color for generated
                    'fill-opacity': 0.5,
                    'fill-outline-color': '#d97706'
                }
            });

            // Dashed border to indicate "estimated"
            map.addLayer({
                id: 'buildings-annotation-border',
                type: 'line',
                source: 'buildings',
                paint: {
                    'line-color': '#92400e',  // Dark amber
                    'line-width': 2,
                    'line-dasharray': [3, 2]  // Dashed to show estimated
                }
            });
        } else if (isVerificationMode) {
            // Fill layer with annotation-aware styling
            // Unannotated: 0.3 opacity, Annotated: 0.7 opacity
            map.addLayer({
                id: 'buildings-overlay',
                type: 'fill',
                source: 'buildings',
                paint: {
                    'fill-color': [
                        'case',
                        // Low confidence -> yellow
                        ['<', ['get', 'confidence'], 0.7], '#eab308',
                        // High confidence + existed -> green
                        ['get', 'existed'], '#22c55e',
                        // High confidence + not existed -> red
                        '#ef4444'
                    ],
                    'fill-opacity': [
                        'case',
                        // Annotated buildings: higher opacity (0.7)
                        ['==', ['get', '_annotated'], true], 0.7,
                        // Unannotated: lower opacity (0.3) to see aerial photo
                        0.3
                    ],
                    'fill-outline-color': '#000000'
                }
            });

            // Add line layer for annotation borders (2px for annotated)
            map.addLayer({
                id: 'buildings-annotation-border',
                type: 'line',
                source: 'buildings',
                paint: {
                    'line-color': [
                        'case',
                        // Annotated as existed -> green border
                        ['==', ['get', '_annotation_existed'], true], '#22c55e',
                        // Annotated as not existed -> red border
                        ['==', ['get', '_annotation_existed'], false], '#ef4444',
                        // Not annotated -> black border
                        '#000000'
                    ],
                    'line-width': [
                        'case',
                        // Annotated buildings: 2px border
                        ['==', ['get', '_annotated'], true], 2,
                        // Unannotated: 1px border
                        1
                    ]
                }
            });
        } else {
            // Confidence-colored polygons for ML detected buildings
            map.addLayer({
                id: 'buildings-overlay',
                type: 'fill',
                source: 'buildings',
                paint: {
                    'fill-color': [
                        'interpolate',
                        ['linear'],
                        ['coalesce', ['get', 'mlc'], 0.5],
                        0, '#ff4444',
                        0.5, '#ffaa00',
                        1, '#44ff44'
                    ],
                    'fill-opacity': [
                        'case',
                        ['==', ['get', '_annotated'], true], 0.7,
                        0.3
                    ],
                    'fill-outline-color': '#000000'
                }
            });

            // Add line layer for annotation borders
            map.addLayer({
                id: 'buildings-annotation-border',
                type: 'line',
                source: 'buildings',
                paint: {
                    'line-color': [
                        'case',
                        ['==', ['get', '_annotation_existed'], true], '#22c55e',
                        ['==', ['get', '_annotation_existed'], false], '#ef4444',
                        '#000000'
                    ],
                    'line-width': [
                        'case',
                        ['==', ['get', '_annotated'], true], 2,
                        1
                    ]
                }
            });
        }
    }

    // Overlay roads if available (LineStrings)
    if (roadsData) {
        map.addSource('roads', {
            type: 'geojson',
            data: roadsData
        });

        // Road outline (wider, darker)
        map.addLayer({
            id: 'roads-outline',
            type: 'line',
            source: 'roads',
            paint: {
                'line-color': '#8B0000',  // Dark red
                'line-width': 4,
                'line-opacity': 0.6
            }
        });

        // Road centerline (narrower, brighter)
        map.addLayer({
            id: 'roads-overlay',
            type: 'line',
            source: 'roads',
            paint: {
                'line-color': '#FF6B6B',  // Coral red
                'line-width': 2,
                'line-opacity': 0.9
            }
        });
    }

    // Add water layers (OSM baseline + manual historical fills)
    addWaterLayers();
}

/**
 * Add water layers to map (OSM baseline in blue, manual historical in orange)
 */
function addWaterLayers(opacity = 0.5) {
    // OSM water - current water features (blue)
    if (waterData && waterData.features?.length > 0) {
        map.addSource('water-osm', {
            type: 'geojson',
            data: waterData
        });

        // Fill layer with type-based coloring
        map.addLayer({
            id: 'water-osm-fill',
            type: 'fill',
            source: 'water-osm',
            paint: {
                'fill-color': [
                    'match',
                    ['get', 'wtype'],
                    'fjord', WATER_TYPE_COLORS.fjord,
                    'river', WATER_TYPE_COLORS.river,
                    'lake', WATER_TYPE_COLORS.lake,
                    'canal', WATER_TYPE_COLORS.canal,
                    'harbor', WATER_TYPE_COLORS.harbor,
                    WATER_TYPE_COLORS.fjord  // default
                ],
                'fill-opacity': opacity
            }
        });

        // Outline
        map.addLayer({
            id: 'water-osm-outline',
            type: 'line',
            source: 'water-osm',
            paint: {
                'line-color': '#004080',
                'line-width': 1
            }
        });
    }

    // Manual water - historical filled areas (orange to distinguish from current)
    if (manualWaterData && manualWaterData.features?.length > 0) {
        map.addSource('water-manual', {
            type: 'geojson',
            data: manualWaterData
        });

        // Fill layer - orange/amber for historical fills
        map.addLayer({
            id: 'water-manual-fill',
            type: 'fill',
            source: 'water-manual',
            paint: {
                'fill-color': '#d97706',  // Amber for historical
                'fill-opacity': opacity
            }
        });

        // Outline - dashed to indicate historical
        map.addLayer({
            id: 'water-manual-outline',
            type: 'line',
            source: 'water-manual',
            paint: {
                'line-color': '#92400e',
                'line-width': 2,
                'line-dasharray': [4, 2]
            }
        });
    }
}

/**
 * Apply saved annotations from localStorage to GeoJSON features
 */
function applyAnnotationsToFeatures() {
    if (!buildingsData || !buildingsData.features) return;

    buildingsData.features.forEach(feature => {
        const osmId = feature.properties.osm_id;
        if (osmId && annotations[osmId]) {
            feature.properties._annotated = true;
            feature.properties._annotation_existed = annotations[osmId].existed;
        } else {
            // Clear any stale annotation properties
            delete feature.properties._annotated;
            delete feature.properties._annotation_existed;
        }
    });
}

function addRasterLayers(source) {
    if (!source.raster) {
        console.log('No raster config for source');
        return;
    }

    if (source.raster.type === 'wms') {
        // WMS tile source - georeferenced historical maps
        // Use WMS 1.1.1 with EPSG:4326 to match training data download
        // This ensures ML predictions align with the WMS display
        const bounds = source.bounds;  // [west, south, east, north]
        const wmsUrl = `${source.raster.url}?service=WMS&version=1.1.1&request=GetMap` +
            `&layers=${source.raster.layers}&styles=&format=image/png` +
            `&srs=EPSG:4326&width=512&height=512&bbox={bbox-epsg-4326}`;

        console.log('Adding WMS source:', source.raster.layers);
        console.log('WMS URL template:', wmsUrl);
        console.log('Bounds:', bounds);

        try {
            map.addSource('raster-0', {
                type: 'raster',
                tiles: [wmsUrl],
                tileSize: 512,
                bounds: bounds,
                attribution: source.raster.attribution
            });
            map.addLayer({
                id: 'raster-0',
                type: 'raster',
                source: 'raster-0',
                paint: { 'raster-opacity': 1 }
            });
            console.log('WMS layer added successfully');
        } catch (err) {
            console.error('Failed to add WMS layer:', err);
        }
    } else if (source.raster.type === 'mosaic') {
        // Multiple image tiles
        source.raster.images.forEach((img, i) => {
            const sourceId = `raster-${i}`;
            map.addSource(sourceId, {
                type: 'image',
                url: img.url,
                coordinates: [
                    [img.bounds[0], img.bounds[3]], // top-left
                    [img.bounds[2], img.bounds[3]], // top-right
                    [img.bounds[2], img.bounds[1]], // bottom-right
                    [img.bounds[0], img.bounds[1]]  // bottom-left
                ]
            });
            map.addLayer({
                id: sourceId,
                type: 'raster',
                source: sourceId,
                paint: { 'raster-opacity': 1 }
            });
        });
    } else if (source.raster.type === 'image') {
        // Single image
        const img = source.raster.images[0];
        map.addSource('raster-0', {
            type: 'image',
            url: img.url,
            coordinates: [
                [img.bounds[0], img.bounds[3]],
                [img.bounds[2], img.bounds[3]],
                [img.bounds[2], img.bounds[1]],
                [img.bounds[0], img.bounds[1]]
            ]
        });
        map.addLayer({
            id: 'raster-0',
            type: 'raster',
            source: 'raster-0',
            paint: { 'raster-opacity': 1 }
        });
    }
}

// ML Pipeline API Functions

async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();

        // Update UI with status
        document.getElementById('tilesCount').textContent = data.training_tiles || 0;
        document.getElementById('modelIoU').textContent = data.model_iou ? data.model_iou.toFixed(3) : '-';

        if (data.verification_stats) {
            const stats = data.verification_stats;
            document.getElementById('existedCount').textContent = (stats.existed_high_conf || 0) + (stats.existed_low_conf || 0);
            document.getElementById('lowConfCount').textContent = (stats.existed_low_conf || 0) + (stats.not_existed_low_conf || 0);
            document.getElementById('notExistedCount').textContent = (stats.not_existed_high_conf || 0) + (stats.not_existed_low_conf || 0);
        }

        updateAnnotationCount();
    } catch (err) {
        console.error('Failed to fetch ML status:', err);
        addLog('Error: Failed to fetch ML status');
    }
}

async function generateMoreTraining() {
    if (currentJob) {
        addLog('Job already running, please wait...');
        return;
    }

    setJobStatus(true, 'Generating training data...');
    addLog('Starting training data generation...');

    try {
        const response = await fetch('/api/generate-training', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: currentSource, count: 100 })
        });

        const result = await response.json();
        if (result.job_id) {
            currentJob = result.job_id;
            addLog(`Job started: ${result.job_id}`);
        }
    } catch (err) {
        console.error('Failed to generate training data:', err);
        addLog('Error: ' + err.message);
        setJobStatus(false);
    }
}

async function retrain() {
    if (currentJob) {
        addLog('Job already running, please wait...');
        return;
    }

    setJobStatus(true, 'Training model...');
    addLog('Starting model training...');

    try {
        const response = await fetch('/api/train', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: currentSource })
        });

        const result = await response.json();
        if (result.job_id) {
            currentJob = result.job_id;
            addLog(`Job started: ${result.job_id}`);
        }
    } catch (err) {
        console.error('Failed to start training:', err);
        addLog('Error: ' + err.message);
        setJobStatus(false);
    }
}

async function verify() {
    if (currentJob) {
        addLog('Job already running, please wait...');
        return;
    }

    setJobStatus(true, 'Running verification...');
    addLog('Starting verification...');

    try {
        const response = await fetch('/api/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: currentSource })
        });

        const result = await response.json();
        if (result.job_id) {
            currentJob = result.job_id;
            addLog(`Job started: ${result.job_id}`);
        }
    } catch (err) {
        console.error('Failed to start verification:', err);
        addLog('Error: ' + err.message);
        setJobStatus(false);
    }
}

async function applyAnnotations() {
    if (Object.keys(annotations).length === 0) {
        addLog('No annotations to apply');
        return;
    }

    if (currentJob) {
        addLog('Job already running, please wait...');
        return;
    }

    setJobStatus(true, 'Applying annotations...');
    addLog(`Applying ${Object.keys(annotations).length} annotations to training data...`);

    try {
        const response = await fetch('/api/apply-annotations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source: currentSource,
                annotations: Object.entries(annotations).map(([osmId, ann]) => ({
                    osm_id: parseInt(osmId),
                    existed: ann.existed
                }))
            })
        });

        const result = await response.json();
        if (result.job_id) {
            currentJob = result.job_id;
            addLog(`Job started: ${result.job_id}`);
        } else {
            addLog('Annotations applied successfully');
            setJobStatus(false);
        }
    } catch (err) {
        console.error('Failed to apply annotations:', err);
        addLog('Error: ' + err.message);
        setJobStatus(false);
    }
}

function setJobStatus(running, message = '') {
    const jobStatus = document.getElementById('jobStatus');
    const jobStatusText = document.getElementById('jobStatusText');

    if (running) {
        jobStatus.style.display = 'block';
        jobStatusText.textContent = message || 'Running...';
        // Disable action buttons
        disableButtons(true);
    } else {
        jobStatus.style.display = 'none';
        currentJob = null;
        // Enable action buttons
        disableButtons(false);
    }
}

function disableButtons(disabled) {
    const buttons = ['generateMoreBtn', 'retrainBtn', 'verifyBtn', 'applyBtn'];
    buttons.forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.disabled = disabled;
    });
}

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/logs`;

    ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'log') {
            addLog(data.message);
        } else if (data.type === 'complete') {
            addLog(`Job completed: ${data.job_id}`);
            setJobStatus(false);
            // Reload data
            loadSource(currentSource);
            fetchStatus();
        } else if (data.type === 'error') {
            addLog(`Error: ${data.message}`);
            setJobStatus(false);
        }
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };

    ws.onclose = () => {
        console.log('WebSocket closed, attempting reconnect...');
        setTimeout(connectWebSocket, 5000);
    };
}

function addLog(message) {
    const logContent = document.getElementById('logContent');
    const timestamp = new Date().toLocaleTimeString();
    const logLine = document.createElement('div');
    logLine.className = 'log-line';
    logLine.textContent = `[${timestamp}] ${message}`;
    logContent.appendChild(logLine);

    // Auto-scroll to bottom
    logContent.scrollTop = logContent.scrollHeight;

    // Expand logs if collapsed
    const logOutput = document.getElementById('logOutput');
    if (logOutput.classList.contains('collapsed') && message.includes('Error')) {
        toggleLogs();
    }
}

function toggleLogs() {
    const logOutput = document.getElementById('logOutput');
    const toggle = document.querySelector('.log-toggle');

    logOutput.classList.toggle('collapsed');
    toggle.textContent = logOutput.classList.contains('collapsed') ? '▼' : '▲';
}

// Annotation functionality
function setupAnnotationHandlers() {
    // Load saved annotations from localStorage
    const saved = localStorage.getItem('annotations_1937');
    if (saved) {
        annotations = JSON.parse(saved);
        updateAnnotationCount();
    }

    // Click handler for buildings
    map.on('click', 'buildings-overlay', (e) => {
        if (!e.features || e.features.length === 0) return;

        const feature = e.features[0];
        const props = feature.properties;
        const osmId = props.osm_id;

        // Close existing popup
        if (annotationPopup) {
            annotationPopup.remove();
        }

        // Get current annotation or ML prediction
        const annotation = annotations[osmId];
        const mlPrediction = props.existed;
        const mlConfidence = props.confidence;

        const currentStatus = annotation ? annotation.existed :
                              (mlConfidence >= 0.7 ? mlPrediction : null);

        // Create popup content
        const popupHtml = `
            <div class="annotation-popup">
                <div class="popup-title">Building ${osmId}</div>
                <div class="popup-info">
                    ML: ${mlPrediction ? 'Existed' : 'Not existed'} (${Math.round(mlConfidence * 100)}%)
                    ${annotation ? '<br><strong>Annotated</strong>' : ''}
                </div>
                <div class="popup-buttons">
                    <button class="btn-existed ${currentStatus === true ? 'active' : ''}"
                            onclick="annotateBuilding(${osmId}, true)">
                        ✓ Existed in 1937
                    </button>
                    <button class="btn-not-existed ${currentStatus === false ? 'active' : ''}"
                            onclick="annotateBuilding(${osmId}, false)">
                        ✗ Did NOT exist
                    </button>
                    ${annotation ? `
                    <button class="btn-clear" onclick="clearAnnotation(${osmId})">
                        Clear annotation
                    </button>
                    ` : ''}
                </div>
            </div>
        `;

        annotationPopup = new maplibregl.Popup({ closeOnClick: true })
            .setLngLat(e.lngLat)
            .setHTML(popupHtml)
            .addTo(map);
    });

    // Change cursor on hover
    map.on('mouseenter', 'buildings-overlay', () => {
        map.getCanvas().style.cursor = 'pointer';
    });
    map.on('mouseleave', 'buildings-overlay', () => {
        map.getCanvas().style.cursor = '';
    });

    // Water click handlers
    setupWaterClickHandlers();
}

/**
 * Setup click handlers for water features
 */
function setupWaterClickHandlers() {
    // Click handler for OSM water features
    map.on('click', 'water-osm-fill', (e) => {
        if (!e.features || e.features.length === 0) return;
        showWaterPopup(e.features[0], e.lngLat, 'osm');
    });

    // Click handler for manual water features
    map.on('click', 'water-manual-fill', (e) => {
        if (!e.features || e.features.length === 0) return;
        showWaterPopup(e.features[0], e.lngLat, 'manual');
    });

    // Change cursor on hover for water layers
    ['water-osm-fill', 'water-manual-fill'].forEach(layerId => {
        map.on('mouseenter', layerId, () => {
            map.getCanvas().style.cursor = 'pointer';
        });
        map.on('mouseleave', layerId, () => {
            map.getCanvas().style.cursor = '';
        });
    });
}

/**
 * Show popup for water feature editing
 */
function showWaterPopup(feature, lngLat, sourceType) {
    if (annotationPopup) {
        annotationPopup.remove();
    }

    const props = feature.properties;
    const waterId = props.osm_id || props._src_id || `water_${Date.now()}`;
    const name = props.name || props.nm || '';
    const wtype = props.wtype || 'fjord';
    const sd = props.sd || '';
    const ed = props.ed || '';

    const isOsm = sourceType === 'osm';
    const title = isOsm ? 'OSM Water Feature' : 'Historical Water';

    const popupHtml = `
        <div class="water-popup">
            <div class="popup-title">${title}</div>
            <div class="popup-info">
                <strong>Name:</strong> ${name || 'Unnamed'}<br>
                <strong>Type:</strong> ${wtype}<br>
                ${sd ? `<strong>Start:</strong> ${sd}<br>` : ''}
                ${ed ? `<strong>End (filled):</strong> ${ed}<br>` : ''}
                <strong>Source:</strong> ${isOsm ? 'OSM' : 'Manual'}
            </div>
            ${isOsm ? `
            <div class="popup-buttons">
                <button class="btn-trace" onclick="traceHistoricalFill('${waterId}', ${JSON.stringify(lngLat).replace(/"/g, '&quot;')})">
                    📍 Trace filled area from this
                </button>
            </div>
            ` : `
            <form class="water-edit-form" onsubmit="saveWaterEdit(event, '${waterId}')">
                <label>Name: <input type="text" name="name" value="${name}"></label>
                <label>Type:
                    <select name="wtype">
                        <option value="fjord" ${wtype === 'fjord' ? 'selected' : ''}>Fjord</option>
                        <option value="harbor" ${wtype === 'harbor' ? 'selected' : ''}>Harbor</option>
                        <option value="river" ${wtype === 'river' ? 'selected' : ''}>River</option>
                        <option value="lake" ${wtype === 'lake' ? 'selected' : ''}>Lake</option>
                        <option value="canal" ${wtype === 'canal' ? 'selected' : ''}>Canal</option>
                    </select>
                </label>
                <label>Start year: <input type="number" name="sd" value="${sd}" placeholder="e.g. 1700"></label>
                <label>Filled year: <input type="number" name="ed" value="${ed}" placeholder="e.g. 1960"></label>
                <div class="popup-buttons">
                    <button type="submit" class="btn-save">Save</button>
                    <button type="button" class="btn-delete" onclick="deleteWaterFeature('${waterId}')">Delete</button>
                </div>
            </form>
            `}
        </div>
    `;

    annotationPopup = new maplibregl.Popup({ closeOnClick: true, maxWidth: '300px' })
        .setLngLat(lngLat)
        .setHTML(popupHtml)
        .addTo(map);
}

function annotateBuilding(osmId, existed) {
    annotations[osmId] = { existed, annotated: true, timestamp: Date.now() };
    saveAnnotations();
    updateAnnotationCount();

    // Update feature color immediately
    if (buildingsData) {
        const feature = buildingsData.features.find(f => f.properties.osm_id === osmId);
        if (feature) {
            feature.properties._annotated = true;
            feature.properties._annotation_existed = existed;
        }
        // Refresh the source
        const source = map.getSource('buildings');
        if (source) {
            source.setData(buildingsData);
        }
    }

    if (annotationPopup) {
        annotationPopup.remove();
    }
}

function clearAnnotation(osmId) {
    delete annotations[osmId];
    saveAnnotations();
    updateAnnotationCount();

    if (buildingsData) {
        const feature = buildingsData.features.find(f => f.properties.osm_id === osmId);
        if (feature) {
            delete feature.properties._annotated;
            delete feature.properties._annotation_existed;
        }
        const source = map.getSource('buildings');
        if (source) {
            source.setData(buildingsData);
        }
    }

    if (annotationPopup) {
        annotationPopup.remove();
    }
}

function saveAnnotations() {
    localStorage.setItem('annotations_1937', JSON.stringify(annotations));
}

function updateAnnotationCount() {
    const count = Object.keys(annotations).length;
    const countEl = document.getElementById('annotationsCount');
    if (countEl) {
        countEl.textContent = count;
    }
    // Also update header count
    const headerCountEl = document.getElementById('annotationCount');
    if (headerCountEl) {
        headerCountEl.textContent = `${count} annotated`;
    }
}

function exportAnnotations() {
    const data = {
        source: 'ortofoto1937',
        timestamp: new Date().toISOString(),
        count: Object.keys(annotations).length,
        annotations: Object.entries(annotations).map(([osmId, ann]) => ({
            osm_id: parseInt(osmId),
            existed: ann.existed,
            timestamp: ann.timestamp
        }))
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `annotations_1937_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

// ==========================================
// Water editing functions
// ==========================================

/**
 * Save water feature edits to backend
 */
async function saveWaterEdit(event, waterId) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);

    const updates = {
        id: waterId,
        name: formData.get('name'),
        wtype: formData.get('wtype'),
        sd: formData.get('sd') ? parseInt(formData.get('sd')) : null,
        ed: formData.get('ed') ? parseInt(formData.get('ed')) : null
    };

    try {
        const response = await fetch('/api/water/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });

        if (response.ok) {
            console.log('Water feature updated:', waterId);
            if (annotationPopup) annotationPopup.remove();
            // Reload water data
            await loadWaterData();
            setupLayers();
        } else {
            const err = await response.json();
            alert('Failed to save: ' + (err.error || 'Unknown error'));
        }
    } catch (err) {
        console.error('Failed to save water edit:', err);
        alert('Failed to save: ' + err.message);
    }
}

/**
 * Delete a water feature
 */
async function deleteWaterFeature(waterId) {
    if (!confirm('Delete this water feature?')) return;

    try {
        const response = await fetch('/api/water/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: waterId })
        });

        if (response.ok) {
            console.log('Water feature deleted:', waterId);
            if (annotationPopup) annotationPopup.remove();
            await loadWaterData();
            setupLayers();
        } else {
            const err = await response.json();
            alert('Failed to delete: ' + (err.error || 'Unknown error'));
        }
    } catch (err) {
        console.error('Failed to delete water feature:', err);
        alert('Failed to delete: ' + err.message);
    }
}

/**
 * Start tracing a historical fill area
 */
function traceHistoricalFill(osmWaterId, lngLat) {
    if (annotationPopup) annotationPopup.remove();

    // Enable draw mode if not already active
    if (!draw) {
        initDrawMode();
    }

    // Set mode to draw polygon
    draw.changeMode('draw_polygon');

    // Store context for when polygon is completed
    window._pendingWaterTrace = {
        osmWaterId: osmWaterId,
        startLngLat: lngLat
    };

    // Show instruction
    showDrawInstructions('Click to trace the historical water area. Double-click to finish.');
}

/**
 * Initialize MapLibre GL Draw for polygon drawing
 */
function initDrawMode() {
    if (typeof MapboxDraw === 'undefined') {
        console.error('MapboxDraw not loaded. Please add mapbox-gl-draw to HTML.');
        alert('Drawing library not loaded. Please refresh the page.');
        return;
    }

    draw = new MapboxDraw({
        displayControlsDefault: false,
        controls: {
            polygon: true,
            trash: true
        },
        defaultMode: 'simple_select',
        styles: [
            // Polygon fill
            {
                'id': 'gl-draw-polygon-fill',
                'type': 'fill',
                'filter': ['all', ['==', '$type', 'Polygon']],
                'paint': {
                    'fill-color': '#d97706',
                    'fill-opacity': 0.3
                }
            },
            // Polygon outline
            {
                'id': 'gl-draw-polygon-stroke',
                'type': 'line',
                'filter': ['all', ['==', '$type', 'Polygon']],
                'paint': {
                    'line-color': '#d97706',
                    'line-width': 2,
                    'line-dasharray': [2, 2]
                }
            },
            // Vertex points
            {
                'id': 'gl-draw-polygon-vertex',
                'type': 'circle',
                'filter': ['all', ['==', 'meta', 'vertex']],
                'paint': {
                    'circle-radius': 5,
                    'circle-color': '#d97706'
                }
            }
        ]
    });

    map.addControl(draw, 'top-left');

    // Listen for draw.create event
    map.on('draw.create', handleDrawCreate);
    map.on('draw.modechange', handleDrawModeChange);
}

/**
 * Handle completed polygon drawing
 */
async function handleDrawCreate(e) {
    const feature = e.features[0];
    if (!feature || feature.geometry.type !== 'Polygon') return;

    hideDrawInstructions();

    // Get pending trace context
    const context = window._pendingWaterTrace;
    window._pendingWaterTrace = null;

    // Show form to set properties
    const formHtml = `
        <div class="water-new-form">
            <h3>New Historical Water Area</h3>
            <form id="newWaterForm">
                <label>Name: <input type="text" name="name" placeholder="e.g. Brattøra harbor"></label>
                <label>Type:
                    <select name="wtype">
                        <option value="harbor">Harbor</option>
                        <option value="fjord">Fjord</option>
                        <option value="river">River</option>
                        <option value="lake">Lake</option>
                        <option value="canal">Canal</option>
                    </select>
                </label>
                <label>Existed since: <input type="number" name="sd" value="1700" placeholder="e.g. 1700"></label>
                <label>Filled in: <input type="number" name="ed" placeholder="e.g. 1960"></label>
                <div class="popup-buttons">
                    <button type="submit" class="btn-save">Save</button>
                    <button type="button" class="btn-cancel" onclick="cancelNewWater()">Cancel</button>
                </div>
            </form>
        </div>
    `;

    // Store geometry for save
    window._pendingNewWater = feature.geometry;
    window._pendingDrawId = feature.id;

    // Show popup at center of polygon
    const coords = feature.geometry.coordinates[0];
    const centerLng = coords.reduce((sum, c) => sum + c[0], 0) / coords.length;
    const centerLat = coords.reduce((sum, c) => sum + c[1], 0) / coords.length;

    annotationPopup = new maplibregl.Popup({ closeOnClick: false, maxWidth: '300px' })
        .setLngLat([centerLng, centerLat])
        .setHTML(formHtml)
        .addTo(map);

    // Attach form handler
    document.getElementById('newWaterForm').onsubmit = saveNewWater;
}

/**
 * Save new water polygon to backend
 */
async function saveNewWater(event) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);

    const geometry = window._pendingNewWater;
    if (!geometry) {
        alert('No geometry found');
        return;
    }

    const newFeature = {
        type: 'Feature',
        geometry: geometry,
        properties: {
            _src: 'manual',
            _src_id: `water_${Date.now()}`,
            name: formData.get('name'),
            wtype: formData.get('wtype'),
            sd: formData.get('sd') ? parseInt(formData.get('sd')) : null,
            ed: formData.get('ed') ? parseInt(formData.get('ed')) : null,
            ev: 'm',  // Medium evidence (manual trace)
            src: 'manual'
        }
    };

    try {
        const response = await fetch('/api/water/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newFeature)
        });

        if (response.ok) {
            console.log('New water feature saved');
            if (annotationPopup) annotationPopup.remove();

            // Remove drawn feature
            if (draw && window._pendingDrawId) {
                draw.delete(window._pendingDrawId);
            }

            window._pendingNewWater = null;
            window._pendingDrawId = null;

            // Reload water data
            await loadWaterData();
            setupLayers();
        } else {
            const err = await response.json();
            alert('Failed to save: ' + (err.error || 'Unknown error'));
        }
    } catch (err) {
        console.error('Failed to save new water:', err);
        alert('Failed to save: ' + err.message);
    }
}

/**
 * Cancel new water creation
 */
function cancelNewWater() {
    if (annotationPopup) annotationPopup.remove();

    // Remove drawn feature
    if (draw && window._pendingDrawId) {
        draw.delete(window._pendingDrawId);
    }

    window._pendingNewWater = null;
    window._pendingDrawId = null;
    hideDrawInstructions();
}

/**
 * Handle draw mode changes
 */
function handleDrawModeChange(e) {
    if (e.mode === 'simple_select') {
        hideDrawInstructions();
    }
}

/**
 * Show drawing instructions
 */
function showDrawInstructions(message) {
    let instructions = document.getElementById('drawInstructions');
    if (!instructions) {
        instructions = document.createElement('div');
        instructions.id = 'drawInstructions';
        instructions.className = 'draw-instructions';
        document.body.appendChild(instructions);
    }
    instructions.textContent = message;
    instructions.style.display = 'block';
}

/**
 * Hide drawing instructions
 */
function hideDrawInstructions() {
    const instructions = document.getElementById('drawInstructions');
    if (instructions) {
        instructions.style.display = 'none';
    }
}

/**
 * Toggle water edit mode (show/hide draw controls)
 */
function toggleWaterEditMode() {
    waterEditMode = !waterEditMode;

    const btn = document.getElementById('waterEditBtn');
    if (btn) {
        btn.classList.toggle('active', waterEditMode);
        btn.textContent = waterEditMode ? '✓ Water Edit Mode' : '✎ Water Edit Mode';
    }

    if (waterEditMode && !draw) {
        initDrawMode();
    }

    // Toggle draw control visibility
    if (draw) {
        const controls = document.querySelector('.mapboxgl-ctrl-group');
        if (controls) {
            controls.style.display = waterEditMode ? 'block' : 'none';
        }
    }
}

/**
 * Start drawing a new water polygon manually
 */
function startDrawWater() {
    if (!draw) {
        initDrawMode();
    }
    draw.changeMode('draw_polygon');
    showDrawInstructions('Click to draw water polygon. Double-click to finish.');
}

/**
 * Toggle OSM buildings visibility
 */
function toggleOsmBuildings() {
    showOsmBuildings = !showOsmBuildings;

    const btn = document.getElementById('osmBuildingsBtn');
    if (btn) {
        btn.classList.toggle('active', showOsmBuildings);
        btn.textContent = showOsmBuildings ? '✓ OSM Buildings' : '○ OSM Buildings';
    }

    // Rebuild layers to apply change
    setupLayers();
}

// ==========================================
// Georeferencing Functionality
// ==========================================

// Georeferencing state
const georefState = {
    active: false,
    image: null,       // { filename, path, width, height }
    gcps: [],          // Array of { id, pixel_x, pixel_y, geo_x, geo_y, description }
    selectedGcpIndex: null,
    waitingForGeo: false,  // True when waiting for map click after image click
    mapId: null
};

// Canvas state for image viewer
let georefCanvas = null;
let georefCtx = null;
let georefImage = null;
let canvasPan = { x: 0, y: 0 };
let canvasZoom = 1;
let isDragging = false;
let lastMousePos = { x: 0, y: 0 };

// GCP markers on map
let gcpMapMarkers = [];

/**
 * Refresh list of available images for georeferencing
 */
async function refreshGeorefImages() {
    const select = document.getElementById('georefImageSelect');
    if (!select) return;

    try {
        const response = await fetch('/api/georef/images');
        const data = await response.json();

        // Clear existing options except first
        select.innerHTML = '<option value="">-- Choose image --</option>';

        // Add images
        for (const img of data.images || []) {
            const option = document.createElement('option');
            option.value = img.path;
            option.textContent = img.filename;
            option.dataset.filename = img.filename;
            select.appendChild(option);
        }
    } catch (err) {
        console.error('Failed to load georef images:', err);
    }
}

/**
 * Handle image selection from dropdown
 */
function onGeorefImageSelect() {
    const select = document.getElementById('georefImageSelect');
    const path = select.value;
    const filename = select.selectedOptions[0]?.dataset?.filename;

    if (!path) {
        georefState.image = null;
        document.getElementById('georefModeBtn').disabled = true;
        return;
    }

    georefState.image = { path, filename };
    georefState.mapId = filename.replace(/\.(jpg|jpeg|png|tif|tiff)$/i, '');
    document.getElementById('georefModeBtn').disabled = false;

    // Load existing GCPs for this image
    loadGcps(georefState.mapId);
}

/**
 * Handle file upload for georeferencing
 */
async function onGeorefFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/georef/upload', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            const data = await response.json();
            console.log('Uploaded:', data);

            // Refresh dropdown and wait for it
            await refreshGeorefImages();

            // Select the uploaded image by matching the path
            const select = document.getElementById('georefImageSelect');
            for (const option of select.options) {
                if (option.value === data.path) {
                    select.value = data.path;
                    break;
                }
            }

            // Manually set the image state with the correct path
            georefState.image = { path: data.path, filename: data.filename };
            georefState.mapId = data.filename.replace(/\.(jpg|jpeg|png|tif|tiff)$/i, '');
            document.getElementById('georefModeBtn').disabled = false;

            // Load existing GCPs
            loadGcps(georefState.mapId);
        } else {
            alert('Failed to upload image');
        }
    } catch (err) {
        console.error('Upload error:', err);
        alert('Upload failed: ' + err.message);
    }
}

/**
 * Load existing GCPs for a map
 */
async function loadGcps(mapId) {
    try {
        const response = await fetch(`/api/georef/gcps/${mapId}`);
        const data = await response.json();

        if (data.exists && data.data) {
            georefState.gcps = data.data.gcps || [];
            updateGcpList();
        } else {
            georefState.gcps = [];
            updateGcpList();
        }
    } catch (err) {
        console.error('Failed to load GCPs:', err);
        georefState.gcps = [];
    }
}

/**
 * Toggle georeferencing mode (split view)
 */
function toggleGeorefMode() {
    if (georefState.active) {
        exitGeorefMode();
    } else {
        enterGeorefMode();
    }
}

/**
 * Enter georeferencing mode
 */
async function enterGeorefMode() {
    if (!georefState.image) {
        alert('Please select an image first');
        return;
    }

    georefState.active = true;

    // Show split view
    const viewContainer = document.getElementById('viewContainer');
    const imagePanel = document.getElementById('georefImagePanel');
    const gcpPanel = document.getElementById('gcpPanel');
    const georefSection = document.querySelector('.georef-section');

    viewContainer.classList.add('split-view');
    imagePanel.style.display = 'flex';
    gcpPanel.style.display = 'block';

    // Hide georef controls, show GCP panel
    if (georefSection) {
        georefSection.style.display = 'none';
    }

    // Update button
    document.getElementById('georefModeBtn').textContent = 'Exit GCP Mode';

    // Initialize canvas
    initGeorefCanvas();

    // Load image
    await loadGeorefImage();

    // Add map click handler
    map.on('click', onMapClickForGcp);

    // Resize map
    setTimeout(() => map.resize(), 100);
}

/**
 * Exit georeferencing mode
 */
function exitGeorefMode() {
    georefState.active = false;
    georefState.waitingForGeo = false;

    // Hide split view
    const viewContainer = document.getElementById('viewContainer');
    const imagePanel = document.getElementById('georefImagePanel');
    const gcpPanel = document.getElementById('gcpPanel');
    const georefSection = document.querySelector('.georef-section');

    viewContainer.classList.remove('split-view');
    imagePanel.style.display = 'none';
    gcpPanel.style.display = 'none';

    // Show georef controls
    if (georefSection) {
        georefSection.style.display = 'block';
    }

    // Update button
    document.getElementById('georefModeBtn').textContent = 'Enter GCP Mode';
    document.getElementById('georefModeBtn').disabled = !georefState.image;

    // Remove map click handler
    map.off('click', onMapClickForGcp);

    // Remove GCP markers from map
    clearGcpMapMarkers();

    // Resize map
    setTimeout(() => map.resize(), 100);
}

/**
 * Initialize the georeferencing canvas
 */
function initGeorefCanvas() {
    georefCanvas = document.getElementById('georefCanvas');
    georefCtx = georefCanvas.getContext('2d');

    // Set canvas size to match container
    const container = georefCanvas.parentElement;
    georefCanvas.width = container.clientWidth;
    georefCanvas.height = container.clientHeight - 40; // Account for header

    // Add event listeners
    georefCanvas.addEventListener('mousedown', onCanvasMouseDown);
    georefCanvas.addEventListener('mousemove', onCanvasMouseMove);
    georefCanvas.addEventListener('mouseup', onCanvasMouseUp);
    georefCanvas.addEventListener('wheel', onCanvasWheel);
    georefCanvas.addEventListener('click', onCanvasClick);

    // Handle resize
    window.addEventListener('resize', () => {
        if (georefState.active) {
            georefCanvas.width = container.clientWidth;
            georefCanvas.height = container.clientHeight - 40;
            renderCanvas();
        }
    });
}

/**
 * Load image for georeferencing
 */
async function loadGeorefImage() {
    if (!georefState.image) return;

    georefImage = new Image();
    georefImage.onload = () => {
        // Fit image to canvas
        const scaleX = georefCanvas.width / georefImage.width;
        const scaleY = georefCanvas.height / georefImage.height;
        canvasZoom = Math.min(scaleX, scaleY) * 0.9;
        canvasPan = {
            x: (georefCanvas.width - georefImage.width * canvasZoom) / 2,
            y: (georefCanvas.height - georefImage.height * canvasZoom) / 2
        };
        renderCanvas();
    };
    georefImage.onerror = () => {
        console.error('Failed to load image:', georefState.image.path);
    };
    // Path already includes 'data/' prefix from API
    georefImage.src = georefState.image.path;
}

/**
 * Render the canvas with image and GCP markers
 */
function renderCanvas() {
    if (!georefCtx || !georefCanvas) return;

    // Clear canvas
    georefCtx.fillStyle = '#2c3e50';
    georefCtx.fillRect(0, 0, georefCanvas.width, georefCanvas.height);

    // Draw image
    if (georefImage && georefImage.complete) {
        georefCtx.save();
        georefCtx.translate(canvasPan.x, canvasPan.y);
        georefCtx.scale(canvasZoom, canvasZoom);
        georefCtx.drawImage(georefImage, 0, 0);
        georefCtx.restore();
    }

    // Draw GCP markers
    for (let i = 0; i < georefState.gcps.length; i++) {
        const gcp = georefState.gcps[i];
        if (gcp.pixel_x !== null && gcp.pixel_y !== null) {
            const screenPos = pixelToScreen(gcp.pixel_x, gcp.pixel_y);
            drawGcpMarker(screenPos.x, screenPos.y, i + 1, gcp.geo_x !== null, i === georefState.selectedGcpIndex);
        }
    }
}

/**
 * Draw a GCP marker on canvas
 */
function drawGcpMarker(x, y, number, isComplete, isSelected) {
    georefCtx.save();

    // Circle
    georefCtx.beginPath();
    georefCtx.arc(x, y, 12, 0, Math.PI * 2);
    georefCtx.fillStyle = isComplete ? 'rgba(78, 204, 163, 0.3)' : 'rgba(245, 158, 11, 0.3)';
    georefCtx.fill();
    georefCtx.strokeStyle = isComplete ? '#4ecca3' : '#f59e0b';
    georefCtx.lineWidth = isSelected ? 4 : 2;
    georefCtx.stroke();

    // Number
    georefCtx.fillStyle = 'white';
    georefCtx.font = 'bold 10px sans-serif';
    georefCtx.textAlign = 'center';
    georefCtx.textBaseline = 'middle';
    georefCtx.fillText(number.toString(), x, y);

    georefCtx.restore();
}

/**
 * Convert pixel coordinates to screen coordinates
 */
function pixelToScreen(px, py) {
    return {
        x: px * canvasZoom + canvasPan.x,
        y: py * canvasZoom + canvasPan.y
    };
}

/**
 * Convert screen coordinates to pixel coordinates
 */
function screenToPixel(sx, sy) {
    return {
        x: (sx - canvasPan.x) / canvasZoom,
        y: (sy - canvasPan.y) / canvasZoom
    };
}

// Canvas event handlers
function onCanvasMouseDown(e) {
    if (e.button === 0) { // Left button
        isDragging = true;
        lastMousePos = { x: e.offsetX, y: e.offsetY };
        georefCanvas.style.cursor = 'grabbing';
    }
}

function onCanvasMouseMove(e) {
    if (isDragging) {
        const dx = e.offsetX - lastMousePos.x;
        const dy = e.offsetY - lastMousePos.y;
        canvasPan.x += dx;
        canvasPan.y += dy;
        lastMousePos = { x: e.offsetX, y: e.offsetY };
        renderCanvas();
    }
}

function onCanvasMouseUp(e) {
    isDragging = false;
    georefCanvas.style.cursor = 'crosshair';
}

function onCanvasWheel(e) {
    e.preventDefault();
    const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
    const mouseX = e.offsetX;
    const mouseY = e.offsetY;

    // Zoom around mouse position
    const oldZoom = canvasZoom;
    canvasZoom *= zoomFactor;
    canvasZoom = Math.max(0.1, Math.min(10, canvasZoom));

    canvasPan.x = mouseX - (mouseX - canvasPan.x) * (canvasZoom / oldZoom);
    canvasPan.y = mouseY - (mouseY - canvasPan.y) * (canvasZoom / oldZoom);

    renderCanvas();
}

function onCanvasClick(e) {
    if (isDragging) return; // Ignore if was dragging

    const pixel = screenToPixel(e.offsetX, e.offsetY);

    // Check if click is on image
    if (georefImage && pixel.x >= 0 && pixel.y >= 0 &&
        pixel.x < georefImage.width && pixel.y < georefImage.height) {

        // Add new GCP or update selected
        if (georefState.selectedGcpIndex !== null) {
            // Update existing GCP's pixel position
            georefState.gcps[georefState.selectedGcpIndex].pixel_x = pixel.x;
            georefState.gcps[georefState.selectedGcpIndex].pixel_y = pixel.y;
        } else {
            // Create new GCP
            const newGcp = {
                id: `GCP${georefState.gcps.length + 1}`,
                pixel_x: pixel.x,
                pixel_y: pixel.y,
                geo_x: null,
                geo_y: null,
                description: ''
            };
            georefState.gcps.push(newGcp);
            georefState.selectedGcpIndex = georefState.gcps.length - 1;
        }

        // Now waiting for map click
        georefState.waitingForGeo = true;
        updateGcpList();
        renderCanvas();
        updateGcpMapMarkers();
    }
}

/**
 * Handle map click for setting GCP geographic position
 */
function onMapClickForGcp(e) {
    if (!georefState.active) return;

    if (georefState.waitingForGeo && georefState.selectedGcpIndex !== null) {
        const gcp = georefState.gcps[georefState.selectedGcpIndex];
        gcp.geo_x = e.lngLat.lng;
        gcp.geo_y = e.lngLat.lat;

        georefState.waitingForGeo = false;
        georefState.selectedGcpIndex = null;

        updateGcpList();
        renderCanvas();
        updateGcpMapMarkers();
        updateRunButton();
    }
}

/**
 * Update the GCP list UI
 */
function updateGcpList() {
    const listEl = document.getElementById('gcpList');
    const countEl = document.getElementById('gcpCount');
    const completeEl = document.getElementById('gcpComplete');

    if (!listEl) return;

    const gcps = georefState.gcps;
    const completeCount = gcps.filter(g => g.geo_x !== null && g.geo_y !== null).length;

    countEl.textContent = gcps.length;
    completeEl.textContent = completeCount;

    if (gcps.length === 0) {
        listEl.innerHTML = '<div class="gcp-empty">No GCPs yet. Click image to add.</div>';
        return;
    }

    listEl.innerHTML = gcps.map((gcp, i) => {
        const isComplete = gcp.geo_x !== null && gcp.geo_y !== null;
        const isSelected = i === georefState.selectedGcpIndex;
        const statusClass = isComplete ? 'complete' : 'incomplete';

        return `
            <div class="gcp-item ${statusClass} ${isSelected ? 'selected' : ''}" onclick="selectGcp(${i})">
                <div class="gcp-item-header">
                    <span class="gcp-item-id">${gcp.id}</span>
                    <span class="gcp-item-status ${statusClass}">${isComplete ? 'Complete' : 'Needs geo'}</span>
                </div>
                <div class="gcp-item-coords">
                    <span class="pixel">px: ${gcp.pixel_x?.toFixed(0) ?? '-'}, ${gcp.pixel_y?.toFixed(0) ?? '-'}</span>
                    <br>
                    <span class="geo">geo: ${gcp.geo_x?.toFixed(6) ?? '-'}, ${gcp.geo_y?.toFixed(6) ?? '-'}</span>
                </div>
                <div class="gcp-item-actions">
                    <button onclick="event.stopPropagation(); deleteGcp(${i})" class="delete">Delete</button>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Select a GCP for editing
 */
function selectGcp(index) {
    georefState.selectedGcpIndex = index;
    const gcp = georefState.gcps[index];

    // If GCP doesn't have geo coords, we're waiting for map click
    georefState.waitingForGeo = (gcp.geo_x === null || gcp.geo_y === null);

    // Center image canvas on GCP pixel location
    if (gcp.pixel_x !== null && gcp.pixel_y !== null && georefCanvas) {
        canvasPan.x = georefCanvas.width / 2 - gcp.pixel_x * canvasZoom;
        canvasPan.y = georefCanvas.height / 2 - gcp.pixel_y * canvasZoom;
    }

    // Center map on GCP geo location
    if (gcp.geo_x !== null && gcp.geo_y !== null && map) {
        map.easeTo({
            center: [gcp.geo_x, gcp.geo_y],
            duration: 300
        });
    }

    updateGcpList();
    renderCanvas();
}

/**
 * Delete a GCP
 */
function deleteGcp(index) {
    georefState.gcps.splice(index, 1);

    // Re-number remaining GCPs
    georefState.gcps.forEach((gcp, i) => {
        gcp.id = `GCP${i + 1}`;
    });

    if (georefState.selectedGcpIndex === index) {
        georefState.selectedGcpIndex = null;
        georefState.waitingForGeo = false;
    } else if (georefState.selectedGcpIndex > index) {
        georefState.selectedGcpIndex--;
    }

    updateGcpList();
    renderCanvas();
    updateGcpMapMarkers();
    updateRunButton();
}

/**
 * Update GCP markers on the map
 */
function updateGcpMapMarkers() {
    clearGcpMapMarkers();

    for (let i = 0; i < georefState.gcps.length; i++) {
        const gcp = georefState.gcps[i];
        if (gcp.geo_x !== null && gcp.geo_y !== null) {
            // Create marker element
            const el = document.createElement('div');
            el.className = 'gcp-map-marker';
            el.style.cssText = `
                width: 24px;
                height: 24px;
                border-radius: 50%;
                background: rgba(78, 204, 163, 0.3);
                border: 3px solid #4ecca3;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 11px;
                font-weight: bold;
                color: white;
                cursor: pointer;
            `;
            el.textContent = (i + 1).toString();

            const marker = new maplibregl.Marker({ element: el })
                .setLngLat([gcp.geo_x, gcp.geo_y])
                .addTo(map);

            gcpMapMarkers.push(marker);
        }
    }
}

/**
 * Clear GCP markers from map
 */
function clearGcpMapMarkers() {
    for (const marker of gcpMapMarkers) {
        marker.remove();
    }
    gcpMapMarkers = [];
}

/**
 * Update the Run Georef button state
 */
function updateRunButton() {
    const btn = document.getElementById('runGeorefBtn');
    if (!btn) return;

    const completeCount = georefState.gcps.filter(g => g.geo_x !== null && g.geo_y !== null).length;
    btn.disabled = completeCount < 3;
}

/**
 * Save GCPs to backend
 */
async function saveGcps() {
    if (!georefState.mapId) {
        alert('No map selected');
        return;
    }

    const gcpData = {
        version: '1.0',
        map_id: georefState.mapId,
        map_date: null, // TODO: extract from filename or let user set
        crs: 'EPSG:4326',
        source_file: georefState.image.filename,
        gcps: georefState.gcps.filter(g => g.pixel_x !== null && g.pixel_y !== null)
    };

    try {
        const response = await fetch(`/api/georef/gcps/${georefState.mapId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(gcpData)
        });

        if (response.ok) {
            const data = await response.json();
            console.log('GCPs saved:', data);
            alert(`Saved ${gcpData.gcps.length} GCPs`);
        } else {
            alert('Failed to save GCPs');
        }
    } catch (err) {
        console.error('Save GCPs error:', err);
        alert('Failed to save: ' + err.message);
    }
}

/**
 * Run georeferencing
 */
async function runGeoreferencing() {
    const completeGcps = georefState.gcps.filter(g => g.geo_x !== null && g.geo_y !== null);
    if (completeGcps.length < 3) {
        alert('Need at least 3 complete GCPs');
        return;
    }

    // First save GCPs
    await saveGcps();

    try {
        const response = await fetch('/api/georef/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                map_id: georefState.mapId,
                transform_order: 1
            })
        });

        if (response.ok) {
            const data = await response.json();
            console.log('Georef job started:', data);

            // Show job status panel
            const jobStatusEl = document.getElementById('jobStatus');
            const jobStatusText = document.getElementById('jobStatusText');
            if (jobStatusEl) {
                jobStatusEl.style.display = 'block';
                jobStatusText.textContent = 'Georeferencing...';
            }

            // Poll for job completion
            pollJobStatus(data.job_id);
        } else {
            const err = await response.json();
            alert('Failed to start georeferencing: ' + (err.detail || 'Unknown error'));
        }
    } catch (err) {
        console.error('Georef error:', err);
        alert('Failed: ' + err.message);
    }
}

/**
 * Poll job status until completion
 */
async function pollJobStatus(jobId) {
    const jobStatusEl = document.getElementById('jobStatus');
    const jobStatusText = document.getElementById('jobStatusText');

    const poll = async () => {
        try {
            const response = await fetch(`/api/jobs/${jobId}`);
            if (response.ok) {
                const job = await response.json();
                console.log('Job status:', job);

                if (job.status === 'completed') {
                    if (jobStatusText) jobStatusText.textContent = 'Completed!';
                    setTimeout(() => {
                        if (jobStatusEl) jobStatusEl.style.display = 'none';
                    }, 2000);
                    alert('Georeferencing completed successfully!');

                    // Check for output
                    const outputResponse = await fetch(`/api/georef/output/${georefState.mapId}`);
                    if (outputResponse.ok) {
                        const output = await outputResponse.json();
                        if (output.exists) {
                            console.log('Georeferenced output:', output);
                        }
                    }
                    return;
                } else if (job.status === 'failed') {
                    if (jobStatusText) jobStatusText.textContent = 'Failed';
                    setTimeout(() => {
                        if (jobStatusEl) jobStatusEl.style.display = 'none';
                    }, 2000);
                    alert('Georeferencing failed. Check logs for details.');
                    return;
                } else {
                    // Still running, poll again
                    if (jobStatusText) jobStatusText.textContent = `Running... (${job.status})`;
                    setTimeout(poll, 2000);
                }
            } else {
                console.error('Failed to get job status');
                setTimeout(poll, 3000);
            }
        } catch (err) {
            console.error('Poll error:', err);
            setTimeout(poll, 3000);
        }
    };

    poll();
}

// Initialize georef images list when page loads
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(refreshGeorefImages, 1000);
});

// Make functions available globally for onclick handlers
window.annotateBuilding = annotateBuilding;
window.clearAnnotation = clearAnnotation;
window.exportAnnotations = exportAnnotations;
window.generateMoreTraining = generateMoreTraining;
window.retrain = retrain;
window.verify = verify;
window.applyAnnotations = applyAnnotations;
window.toggleLogs = toggleLogs;
window.saveWaterEdit = saveWaterEdit;
window.deleteWaterFeature = deleteWaterFeature;
window.traceHistoricalFill = traceHistoricalFill;
window.cancelNewWater = cancelNewWater;
window.toggleWaterEditMode = toggleWaterEditMode;
window.startDrawWater = startDrawWater;
window.toggleOsmBuildings = toggleOsmBuildings;

// Georeferencing functions
window.refreshGeorefImages = refreshGeorefImages;
window.onGeorefImageSelect = onGeorefImageSelect;
window.onGeorefFileSelect = onGeorefFileSelect;
window.toggleGeorefMode = toggleGeorefMode;
window.exitGeorefMode = exitGeorefMode;
window.selectGcp = selectGcp;
window.deleteGcp = deleteGcp;
window.saveGcps = saveGcps;
window.runGeoreferencing = runGeoreferencing;

// Export for debugging
window.SourceViewer = {
    map: () => map,
    sources: () => SOURCES,
    buildingsData: () => buildingsData,
    osmBuildingsData: () => osmBuildingsData,
    waterData: () => waterData,
    manualWaterData: () => manualWaterData,
    annotations: () => annotations,
    loadSource,
    loadWaterData,
    loadOsmBuildings,
    exportAnnotations,
    fetchStatus,
    toggleOsmBuildings
};
