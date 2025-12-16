/**
 * Trondheim Historical Map Application
 *
 * This application displays a historical map of Trondheim with temporal filtering.
 * Features are filtered based on their start_date and end_date attributes.
 */

// Configuration
const CONFIG = {
    // Map center on Trondheim, Norway
    center: [10.39, 63.43],
    zoom: 12,
    minZoom: 8,
    maxZoom: 18,

    // PMTiles source path
    pmtilesPath: '../data/trondheim.pmtiles',

    // Default year
    defaultYear: 2020,

    // Year range
    minYear: 1850,
    maxYear: 2025
};

// Global state
let map = null;
let currentYear = CONFIG.defaultYear;

/**
 * Initialize the PMTiles protocol handler
 */
function initPMTiles() {
    const protocol = new pmtiles.Protocol();
    maplibregl.addProtocol('pmtiles', protocol.tile);
    console.log('PMTiles protocol initialized');
}

/**
 * Create the map style with temporal filtering
 * @param {number} year - The year to filter features by
 * @returns {object} MapLibre style object
 */
function createMapStyle(year) {
    return {
        version: 8,
        name: 'Trondheim Historical',
        sources: {
            trondheim: {
                type: 'vector',
                url: `pmtiles://${CONFIG.pmtilesPath}`,
                attribution: '&copy; OpenStreetMap contributors'
            }
        },
        layers: [
            // Background
            {
                id: 'background',
                type: 'background',
                paint: {
                    'background-color': '#f0ebe0'
                }
            },

            // Water bodies
            {
                id: 'water',
                type: 'fill',
                source: 'trondheim',
                'source-layer': 'water',
                filter: createTemporalFilter(year),
                paint: {
                    'fill-color': '#4a90e2',
                    'fill-opacity': 0.7
                }
            },
            {
                id: 'water-outline',
                type: 'line',
                source: 'trondheim',
                'source-layer': 'water',
                filter: createTemporalFilter(year),
                paint: {
                    'line-color': '#2e5f8a',
                    'line-width': 1,
                    'line-opacity': 0.6
                }
            },

            // Landuse (parks, forests, etc.)
            {
                id: 'landuse',
                type: 'fill',
                source: 'trondheim',
                'source-layer': 'landuse',
                filter: createTemporalFilter(year),
                paint: {
                    'fill-color': [
                        'match',
                        ['get', 'class'],
                        'park', '#7fb069',
                        'forest', '#5a8c4f',
                        'grass', '#8bc34a',
                        'cemetery', '#9eb384',
                        '#c8d5b9'
                    ],
                    'fill-opacity': 0.6
                }
            },

            // Roads - background (wider)
            {
                id: 'roads-background',
                type: 'line',
                source: 'trondheim',
                'source-layer': 'transportation',
                filter: ['all', createTemporalFilter(year), ['in', ['get', 'class'], ['literal', ['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'minor', 'service']]]],
                paint: {
                    'line-color': '#ffffff',
                    'line-width': [
                        'interpolate',
                        ['exponential', 1.5],
                        ['zoom'],
                        10, [
                            'match',
                            ['get', 'class'],
                            'motorway', 3,
                            'trunk', 2.5,
                            'primary', 2,
                            'secondary', 1.5,
                            'tertiary', 1,
                            'minor', 0.5,
                            'service', 0.3,
                            0.5
                        ],
                        14, [
                            'match',
                            ['get', 'class'],
                            'motorway', 8,
                            'trunk', 6,
                            'primary', 5,
                            'secondary', 4,
                            'tertiary', 3,
                            'minor', 2,
                            'service', 1.5,
                            1
                        ]
                    ],
                    'line-opacity': 0.8
                }
            },

            // Roads - foreground
            {
                id: 'roads',
                type: 'line',
                source: 'trondheim',
                'source-layer': 'transportation',
                filter: ['all', createTemporalFilter(year), ['in', ['get', 'class'], ['literal', ['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'minor', 'service']]]],
                paint: {
                    'line-color': [
                        'match',
                        ['get', 'class'],
                        'motorway', '#e67e22',
                        'trunk', '#d68910',
                        'primary', '#888888',
                        'secondary', '#999999',
                        'tertiary', '#aaaaaa',
                        '#bbbbbb'
                    ],
                    'line-width': [
                        'interpolate',
                        ['exponential', 1.5],
                        ['zoom'],
                        10, [
                            'match',
                            ['get', 'class'],
                            'motorway', 2,
                            'trunk', 1.5,
                            'primary', 1.2,
                            'secondary', 1,
                            'tertiary', 0.7,
                            'minor', 0.4,
                            'service', 0.2,
                            0.3
                        ],
                        14, [
                            'match',
                            ['get', 'class'],
                            'motorway', 6,
                            'trunk', 4.5,
                            'primary', 3.5,
                            'secondary', 3,
                            'tertiary', 2,
                            'minor', 1.5,
                            'service', 1,
                            0.5
                        ]
                    ],
                    'line-opacity': 1
                }
            },

            // Buildings
            {
                id: 'buildings',
                type: 'fill',
                source: 'trondheim',
                'source-layer': 'building',
                filter: createTemporalFilter(year),
                paint: {
                    'fill-color': '#d4a373',
                    'fill-opacity': 0.8
                }
            },
            {
                id: 'buildings-outline',
                type: 'line',
                source: 'trondheim',
                'source-layer': 'building',
                filter: createTemporalFilter(year),
                paint: {
                    'line-color': '#8b6f47',
                    'line-width': [
                        'interpolate',
                        ['linear'],
                        ['zoom'],
                        12, 0.5,
                        16, 1
                    ],
                    'line-opacity': 0.8
                }
            },

            // Place labels
            {
                id: 'place-labels',
                type: 'symbol',
                source: 'trondheim',
                'source-layer': 'place',
                filter: createTemporalFilter(year),
                layout: {
                    'text-field': ['get', 'name'],
                    'text-font': ['Open Sans Regular'],
                    'text-size': [
                        'interpolate',
                        ['linear'],
                        ['zoom'],
                        10, 10,
                        14, 14
                    ],
                    'text-anchor': 'center'
                },
                paint: {
                    'text-color': '#333333',
                    'text-halo-color': '#ffffff',
                    'text-halo-width': 2
                }
            }
        ]
    };
}

/**
 * Create a temporal filter expression for MapLibre
 * Features are visible if: start_date <= year AND (end_date >= year OR end_date is null)
 * @param {number} year - The year to filter by
 * @returns {array} MapLibre filter expression
 */
function createTemporalFilter(year) {
    return [
        'all',
        // start_date <= year OR start_date doesn't exist (show features without start_date)
        [
            'any',
            ['!', ['has', 'start_date']],
            ['<=', ['get', 'start_date'], year]
        ],
        // end_date >= year OR end_date doesn't exist (show features without end_date or still existing)
        [
            'any',
            ['!', ['has', 'end_date']],
            ['>=', ['get', 'end_date'], year]
        ]
    ];
}

/**
 * Initialize the map
 */
function initMap() {
    console.log('Initializing map...');

    try {
        map = new maplibregl.Map({
            container: 'map',
            style: createMapStyle(currentYear),
            center: CONFIG.center,
            zoom: CONFIG.zoom,
            minZoom: CONFIG.minZoom,
            maxZoom: CONFIG.maxZoom,
            attributionControl: true
        });

        // Add navigation controls
        map.addControl(new maplibregl.NavigationControl(), 'bottom-right');

        // Add scale control
        map.addControl(new maplibregl.ScaleControl({
            maxWidth: 200,
            unit: 'metric'
        }), 'bottom-left');

        // Map load event
        map.on('load', () => {
            console.log('Map loaded successfully');
            hideLoading();
        });

        // Error handling
        map.on('error', (e) => {
            console.error('Map error:', e);
            // Don't show error for missing tiles - this is expected if PMTiles doesn't exist yet
            if (e.error && e.error.message && !e.error.message.includes('404')) {
                showError('Map error: ' + e.error.message);
            }
        });

        // Log style data loaded
        map.on('styledata', () => {
            console.log('Style data loaded for year:', currentYear);
        });

    } catch (error) {
        console.error('Failed to initialize map:', error);
        showError('Failed to initialize map: ' + error.message);
        hideLoading();
    }
}

/**
 * Update the map to show features from a specific year
 * @param {number} year - The year to display
 */
function updateMapYear(year) {
    if (!map) {
        console.warn('Map not initialized yet');
        return;
    }

    currentYear = year;
    console.log('Updating map to year:', year);

    try {
        // Update the map style with new temporal filters
        const newStyle = createMapStyle(year);
        map.setStyle(newStyle);

        // Update the year display
        document.getElementById('currentYear').textContent = year;

    } catch (error) {
        console.error('Failed to update map year:', error);
        showError('Failed to update year: ' + error.message);
    }
}

/**
 * Initialize the time slider controls
 */
function initControls() {
    const slider = document.getElementById('yearSlider');
    const yearDisplay = document.getElementById('currentYear');

    if (!slider || !yearDisplay) {
        console.error('Controls elements not found');
        return;
    }

    // Set initial value
    slider.value = currentYear;
    yearDisplay.textContent = currentYear;

    // Handle slider input (fires continuously as user drags)
    slider.addEventListener('input', (e) => {
        const year = parseInt(e.target.value);
        yearDisplay.textContent = year;
    });

    // Handle slider change (fires when user releases)
    slider.addEventListener('change', (e) => {
        const year = parseInt(e.target.value);
        updateMapYear(year);
    });

    console.log('Controls initialized');
}

/**
 * Show loading indicator
 */
function showLoading() {
    const loading = document.getElementById('loading');
    if (loading) {
        loading.classList.remove('hidden');
        loading.style.display = 'block';
    }
}

/**
 * Hide loading indicator
 */
function hideLoading() {
    const loading = document.getElementById('loading');
    if (loading) {
        loading.classList.add('hidden');
        setTimeout(() => {
            loading.style.display = 'none';
        }, 300);
    }
}

/**
 * Show error message
 * @param {string} message - Error message to display
 */
function showError(message) {
    const errorEl = document.getElementById('error');
    const errorText = document.getElementById('errorText');

    if (errorEl && errorText) {
        errorText.textContent = message;
        errorEl.style.display = 'block';

        // Auto-hide after 5 seconds
        setTimeout(() => {
            errorEl.style.display = 'none';
        }, 5000);
    }

    console.error(message);
}

/**
 * Initialize the application
 */
function init() {
    console.log('Initializing Trondheim Historical Map application...');
    console.log('Configuration:', CONFIG);

    try {
        // Initialize PMTiles protocol
        initPMTiles();

        // Initialize controls
        initControls();

        // Initialize map
        initMap();

    } catch (error) {
        console.error('Initialization failed:', error);
        showError('Failed to initialize application: ' + error.message);
        hideLoading();
    }
}

// Start the application when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    // DOM already loaded
    init();
}

// Export for debugging in console
window.HistoricalMap = {
    map,
    currentYear,
    updateMapYear,
    CONFIG
};
