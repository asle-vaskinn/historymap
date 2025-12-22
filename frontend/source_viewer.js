/**
 * Data Source Viewer
 * Debug page for inspecting individual data sources
 */

// Configuration - georeferenced historical maps from various WMS sources
const SOURCES = {
    amt1: {
        name: 'Amtskart (1870-1920)',
        year: 1900,
        bounds: [10.30, 63.38, 10.50, 63.48],
        raster: {
            type: 'wms',
            url: 'https://wms.geonorge.no/skwms1/wms.historiskekart',
            layers: 'amt1',
            attribution: '© Kartverket'
        },
        buildings: 'data/sources/sefrak/normalized/buildings.geojson',  // 1894 SEFRAK buildings
        roads: 'data/sources/ml_detected/kartverket_1880/roads/roads.geojson'  // 215 ML-extracted roads
    },
    gen1880: {
        name: 'Generated 1880 (PoC)',
        year: 1880,
        bounds: [10.35, 63.38, 10.45, 63.46],  // Match road extraction bounds
        raster: {
            type: 'wms',
            url: 'https://wms.geonorge.no/skwms1/wms.historiskekart',
            layers: 'amt1',
            attribution: '© Kartverket'
        },
        buildings: 'data/sources/generated/kv1880/buildings_test.geojson',  // 52 test buildings
        roads: 'data/sources/ml_detected/kartverket_1880/roads/roads.geojson',  // 215 ML-extracted roads
        generatedMode: true  // Use special styling for generated buildings
    },
    ortofoto1937: {
        name: 'Flyfoto 1937',
        year: 1937,
        bounds: [10.38, 63.42, 10.44, 63.45],  // Extended bounds
        raster: {
            type: 'wms',
            url: 'https://kart.trondheim.kommune.no/geoserver/Raster/wms',
            layers: 'ortofoto1937',
            attribution: '© Trondheim kommune'
        },
        buildings: 'data/sources/ml_detected/ortofoto1937/verified_buildings.geojson',
        roads: 'data/sources/ml_detected/ortofoto1937/roads_extracted.geojson',  // Color-extracted roads
        verificationMode: true  // Use status-based coloring
    },
    ortofoto2006: {
        name: 'Flyfoto 2006',
        year: 2006,
        bounds: [10.30, 63.38, 10.50, 63.48],
        raster: {
            type: 'wms',
            url: 'https://kart.trondheim.kommune.no/geoserver/Raster/wms',
            layers: 'ortofoto2006',
            attribution: '© Trondheim kommune'
        },
        buildings: null
    },
    ortofoto2023: {
        name: 'Flyfoto 2023',
        year: 2023,
        bounds: [10.30, 63.38, 10.50, 63.48],
        raster: {
            type: 'wms',
            url: 'https://kart.trondheim.kommune.no/geoserver/Raster/wms',
            layers: 'ortofoto2023',
            attribution: '© Trondheim kommune'
        },
        buildings: null
    }
};

const BASE_MAP_STYLE = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';

// Trondheim center
const DEFAULT_CENTER = [10.40, 63.43];
const DEFAULT_ZOOM = 13;

// State
let map = null;
let currentSource = 'amt1';
let buildingsData = null;
let roadsData = null;  // ML-extracted roads
let annotations = {};  // osm_id -> { existed: bool, annotated: true }
let annotationPopup = null;
let ws = null;  // WebSocket for logs
let currentJob = null;

// Source ID mapping from main app to source viewer
const SOURCE_ID_MAP = {
    'kv1880': 'amt1',      // Kartverket 1880 -> Amtskart
    'kv1904': 'amt1',      // Kartverket 1904 -> Amtskart (same WMS)
    'air1947': 'ortofoto1937'  // Aerial 1947 -> closest available (1937)
};

// Reverse mapping: source viewer ID to main app snapshot ID
const REVERSE_SOURCE_MAP = {
    'amt1': 'kv1880',
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

    if (sourceParam) {
        // Map from main app source IDs to source viewer IDs
        const mappedSource = SOURCE_ID_MAP[sourceParam] || sourceParam;
        if (SOURCES[mappedSource]) {
            currentSource = mappedSource;
            // Update dropdown to match
            const select = document.getElementById('sourceSelect');
            if (select) {
                select.value = mappedSource;
            }
        }
    }

    // Initialize map with empty style (will be updated based on view)
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
        zoom: DEFAULT_ZOOM
    });

    map.on('load', () => {
        loadSource(currentSource);
        setupAnnotationHandlers();
        fetchStatus();  // Load ML pipeline status
        connectWebSocket();  // Connect to log stream
    });

    // Source selector - also update URL when changed
    document.getElementById('sourceSelect').addEventListener('change', (e) => {
        const sourceId = e.target.value;
        loadSource(sourceId);
        // Update URL without reload
        const url = new URL(window.location);
        url.searchParams.set('source', sourceId);
        window.history.replaceState({}, '', url);
        // Update "View on Map" link
        updateViewOnMapLink(sourceId);
    });

    // Initialize "View on Map" link
    updateViewOnMapLink(currentSource);
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

function setupLayers() {
    const source = SOURCES[currentSource];
    if (!source) return;

    // Remove existing layers and sources
    const layersToRemove = ['raster-0', 'raster-1', 'raster-2', 'raster-3',
                           'buildings-overlay', 'buildings-annotation-border',
                           'roads-overlay', 'roads-outline'];
    layersToRemove.forEach(id => {
        if (map.getLayer(id)) map.removeLayer(id);
    });

    const sourcesToRemove = ['raster-0', 'raster-1', 'raster-2', 'raster-3', 'buildings', 'roads'];
    sourcesToRemove.forEach(id => {
        if (map.getSource(id)) map.removeSource(id);
    });

    // Always show aerial photo/raster
    addRasterLayers(source);

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

// Make functions available globally for onclick handlers
window.annotateBuilding = annotateBuilding;
window.clearAnnotation = clearAnnotation;
window.exportAnnotations = exportAnnotations;
window.generateMoreTraining = generateMoreTraining;
window.retrain = retrain;
window.verify = verify;
window.applyAnnotations = applyAnnotations;
window.toggleLogs = toggleLogs;

// Export for debugging
window.SourceViewer = {
    map: () => map,
    sources: () => SOURCES,
    buildingsData: () => buildingsData,
    annotations: () => annotations,
    loadSource,
    exportAnnotations,
    fetchStatus
};
