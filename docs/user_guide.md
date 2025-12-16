# Trondheim Historical Map - User Guide

Welcome to the Trondheim Historical Map! This interactive application allows you to explore how the Trondheim region has evolved over time, from 1850 to the present day.

## Overview

The Trondheim Historical Map combines modern OpenStreetMap data with machine learning-extracted features from historical maps to show you how buildings, roads, railways, and other features appeared and changed throughout history.

**Coverage Area**: Trondheim++ region (~3,000 km²)
- Trondheim
- Malvik, Stjørdal, Meråker
- Melhus, Skaun, Klæbu

**Time Range**: 1850 - Present

## Getting Started

### Opening the Map

1. Open the application in your web browser
2. The map will load centered on Trondheim, Norway
3. You'll see the current state of the region with all available features

### Basic Navigation

#### Zooming
- **Mouse wheel**: Scroll up to zoom in, scroll down to zoom out
- **Double-click**: Zoom in on the clicked location
- **Touch**: Pinch to zoom in/out on mobile devices
- **Buttons**: Use the +/- buttons in the top-left corner

#### Panning
- **Mouse**: Click and drag to move around the map
- **Touch**: Swipe to pan on mobile devices
- **Keyboard**: Use arrow keys to pan

#### Tilting and Rotating
- **Tilt**: Right-click and drag (or Ctrl+drag on Mac)
- **Rotate**: Ctrl+click and drag (or Cmd+click on Mac)
- **Reset**: Double-click the compass icon to reset north

## Using the Time Slider

The time slider is the key feature of this application, allowing you to travel through time.

### Time Slider Controls

1. **Location**: The time slider is located at the bottom of the screen
2. **Range**: Covers years from 1850 to the present (2025)
3. **Current Year**: Displayed prominently on the slider

### How to Use

1. **Drag the slider**: Click and drag the slider handle to any year
2. **Click on timeline**: Click anywhere on the timeline to jump to that year
3. **Watch features appear/disappear**: As you move through time, you'll see:
   - Buildings appearing when they were constructed
   - Buildings disappearing when they were demolished
   - Roads being built
   - Railways appearing and being abandoned
   - Changes in water bodies and land use

### How Features Are Shown

Features are displayed based on their temporal attributes:

- **Feature is visible when**:
  - Start date ≤ Selected year AND
  - (End date ≥ Selected year OR End date is not specified)

- **Feature is hidden when**:
  - Not yet built (start date > selected year)
  - Already demolished (end date < selected year)

### Examples

- **Selecting 1900**: You'll see buildings and roads that existed in 1900
- **Selecting 1950**: New buildings from 1900-1950 appear, old demolished ones disappear
- **Selecting 2025**: Shows the current state with all existing features

## Feature Types and Colors

The map displays different types of features with distinct visual styles:

### Buildings
- **Color**: Gray to brown tones
- **Style**: Filled polygons with outlines
- **What to look for**: Urban development, city expansion, demolished structures

### Roads
- **Color**: Yellow to orange (major roads), white (minor roads)
- **Style**: Lines of varying width
- **What to look for**: New road construction, road widening, historical routes

### Railways
- **Color**: Dark gray with cross-hatching
- **Style**: Lines with railway symbols
- **What to look for**: Railway expansion, abandoned lines, station locations

### Water Bodies
- **Color**: Blue
- **Style**: Filled polygons
- **What to look for**: Rivers, lakes, coastal changes

### Land Use (when available)
- **Parks**: Green
- **Commercial**: Pink/red tones
- **Industrial**: Purple/gray
- **Agricultural**: Light green/yellow

## Mobile Usage Tips

The application is fully responsive and works on mobile devices:

### Touch Gestures
- **One finger drag**: Pan the map
- **Two finger pinch**: Zoom in/out
- **Two finger rotate**: Rotate the map
- **Two finger tilt**: Tilt for 3D view

### Mobile Considerations
- **Battery**: 3D rendering can be power-intensive
- **Data**: Initial load downloads map tiles (use WiFi for first visit)
- **Performance**: Newer devices will have smoother performance
- **Screen orientation**: Works in both portrait and landscape modes

### Tips for Best Mobile Experience
1. Allow the map to fully load before interacting
2. Use two fingers for complex gestures
3. Pinch-zoom works better than double-tap on detailed maps
4. Rotate your device to landscape for timeline visibility

## Advanced Features

### Map Styles
The application shows features with historically-appropriate styling when possible:
- Historical features may appear in sepia or aged tones
- Modern features appear in contemporary colors
- Feature confidence levels may affect opacity

### Data Sources Indicator
Look for the attribution in the bottom-right corner:
- **OSM**: Modern OpenStreetMap data
- **Kartverket**: Historical Norwegian Mapping Authority maps
- **ML**: Machine learning-extracted features (may have lower confidence)

## Tips for Exploration

### Finding Interesting Changes
1. **City Center**: Start at Nidaros Cathedral and explore outward
2. **Harbor Area**: Watch the waterfront development
3. **Railway Development**: Follow the railway expansion from 1850s
4. **Suburban Growth**: See how suburbs developed over time

### Best Years to Explore
- **1850s**: Pre-railway Trondheim
- **1900**: Early industrial development
- **1950**: Post-war reconstruction
- **1980**: Modern city structure emerging
- **Present**: Current state

### Comparing Time Periods
1. Choose a specific location (e.g., Torvet square)
2. Note the year
3. Slowly drag the slider through time
4. Watch the evolution at that single spot

## Troubleshooting

### Map Not Loading
- Check your internet connection
- Try refreshing the page (F5 or Cmd+R)
- Clear browser cache if problem persists
- Ensure JavaScript is enabled

### Slow Performance
- Close other browser tabs
- Reduce zoom level (zoom out)
- Try a different browser (Chrome, Firefox, or Safari recommended)
- Ensure your device meets minimum requirements

### Time Slider Not Working
- Make sure JavaScript is enabled
- Try clicking directly on the timeline instead of dragging
- Refresh the page

### Missing Features
- Some time periods may have limited data
- Not all historical features have been extracted yet
- Zoom in for more detail at higher zoom levels

### Mobile Issues
- Ensure you're using a modern browser
- Update your browser to the latest version
- Try rotating device orientation
- Close other apps to free up memory

## Data Accuracy

### Understanding the Data

**Modern Features (OSM)**
- High accuracy for current features
- Temporal data may be incomplete
- Regular updates from OpenStreetMap community

**Historical Features (ML-extracted)**
- Accuracy varies by map quality and age
- Buildings: 70-85% accuracy
- Roads: 60-80% accuracy
- Some features may be misclassified or missed

### Limitations
- Not all historical maps have been processed yet
- Date accuracy depends on source map metadata
- Some rural areas have less detailed historical data
- Very old maps (pre-1900) may have lower accuracy

## Keyboard Shortcuts

- **Arrow Keys**: Pan the map
- **+/-**: Zoom in/out
- **Shift + Drag**: Rotate map
- **Ctrl/Cmd + Drag**: Tilt map
- **Escape**: Reset rotation and tilt

## Accessibility

The application aims to be accessible to all users:
- Keyboard navigation supported
- High contrast mode compatible
- Screen reader friendly (ARIA labels on controls)
- Scalable interface for vision-impaired users

## Providing Feedback

If you notice:
- Incorrect dates on features
- Missing historical features
- Misclassified buildings or roads
- Any bugs or issues

Please refer to the project repository for contact information and issue reporting.

## Privacy

This application:
- Does not collect personal data
- Does not track your usage
- Does not use cookies (except for essential functionality)
- Runs entirely in your browser
- Map tile requests are logged only for infrastructure purposes

## Further Learning

To learn more about:
- **How the data was created**: See [methodology.md](methodology.md)
- **Data sources and licensing**: See [data_sources.md](data_sources.md)
- **Technical details**: See the main README.md in the repository
- **Project background**: See HISTORICAL_MAP_PROJECT_PLAN.md

## Credits

This application was built using:
- MapLibre GL JS for map rendering
- PMTiles for efficient tile delivery
- Machine learning for historical feature extraction
- OpenStreetMap data
- Kartverket historical maps

---

**Enjoy exploring the history of Trondheim!**

For technical support or questions, please refer to the project repository.
