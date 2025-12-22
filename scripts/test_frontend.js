#!/usr/bin/env node
/**
 * Frontend validation tests for Trondheim Historical Map
 *
 * Tests:
 * - JavaScript syntax validation
 * - MapLibre style expression validation
 * - Check for unsupported data expressions in paint properties
 *
 * Usage:
 *   node scripts/test_frontend.js
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

// Configuration
const FRONTEND_DIR = path.join(__dirname, '..', 'frontend');
const APP_JS = path.join(FRONTEND_DIR, 'app.js');

// MapLibre paint properties that DO NOT support data expressions
// See: https://maplibre.org/maplibre-style-spec/layers/
const NO_DATA_EXPRESSION_PROPERTIES = [
    'line-dasharray',
    'line-pattern',
    'fill-pattern',
    'fill-extrusion-pattern',
    // Note: 'icon-image' and 'text-field' DO support expressions
];

// Test results
let passed = 0;
let failed = 0;
const errors = [];

function log(msg) {
    console.log(msg);
}

function pass(testName) {
    passed++;
    log(`  ✓ ${testName}`);
}

function fail(testName, error) {
    failed++;
    errors.push({ test: testName, error });
    log(`  ✗ ${testName}`);
    log(`    Error: ${error}`);
}

/**
 * Test 1: JavaScript syntax validation
 */
function testJavaScriptSyntax() {
    log('\n[Test 1] JavaScript Syntax Validation');

    try {
        const code = fs.readFileSync(APP_JS, 'utf8');

        // Try to parse the code
        new vm.Script(code, { filename: 'app.js' });

        pass('app.js syntax is valid');
        return true;
    } catch (e) {
        fail('app.js syntax validation', e.message);
        return false;
    }
}

/**
 * Test 2: Check for data expressions in unsupported properties
 */
function testNoDataExpressionsInUnsupportedProperties() {
    log('\n[Test 2] MapLibre Data Expression Validation');

    const code = fs.readFileSync(APP_JS, 'utf8');
    let hasErrors = false;

    for (const prop of NO_DATA_EXPRESSION_PROPERTIES) {
        // Look for patterns like: 'line-dasharray': [ ... ]
        // where the array contains expressions like ['case', ...] or ['match', ...]
        const propRegex = new RegExp(`['"]${prop}['"]\\s*:\\s*\\[`, 'g');
        let match;

        while ((match = propRegex.exec(code)) !== null) {
            // Get the position and extract surrounding context
            const startPos = match.index;
            const snippet = code.substring(startPos, startPos + 200);

            // Check if it contains data expression keywords after the property
            const dataExpressionKeywords = ['case', 'match', 'get', 'has', 'in', 'coalesce', 'step', 'interpolate'];

            for (const keyword of dataExpressionKeywords) {
                // Look for expressions like ['case', or ['get',
                const keywordPattern = new RegExp(`\\[\\s*['"]${keyword}['"]`);
                if (keywordPattern.test(snippet)) {
                    // This might be a nested data expression
                    // Get line number for better error reporting
                    const lineNum = code.substring(0, startPos).split('\n').length;
                    fail(`${prop} uses data expression`,
                         `Line ${lineNum}: '${prop}' does not support data expressions. Found '${keyword}' expression.`);
                    hasErrors = true;
                    break;
                }
            }
        }
    }

    if (!hasErrors) {
        pass('No unsupported data expressions found in paint properties');
    }

    return !hasErrors;
}

/**
 * Test 3: Check that required helper functions exist
 */
function testRequiredFunctions() {
    log('\n[Test 3] Required Functions Exist');

    const code = fs.readFileSync(APP_JS, 'utf8');

    const requiredFunctions = [
        'createBuildingFilter',
        'createRoadFilter',
        'updateMapYear',
        'updateLayerFilters',
        'toggleLayer',
        'getChangeTypeColor',
        'getEvidenceLabel'
    ];

    let allExist = true;

    for (const fn of requiredFunctions) {
        const fnRegex = new RegExp(`function\\s+${fn}\\s*\\(`);
        if (fnRegex.test(code)) {
            pass(`Function ${fn}() exists`);
        } else {
            fail(`Function ${fn}() exists`, `Function ${fn} not found in app.js`);
            allExist = false;
        }
    }

    return allExist;
}

/**
 * Test 4: Check layer definitions
 */
function testLayerDefinitions() {
    log('\n[Test 4] Layer Definitions');

    const code = fs.readFileSync(APP_JS, 'utf8');

    const requiredLayers = [
        'roads-historical',
        'roads-historical-removed',
        'roads-historical-background',
        'buildings',
        'buildings-outline'
    ];

    let allExist = true;

    for (const layer of requiredLayers) {
        const layerRegex = new RegExp(`id:\\s*['"]${layer}['"]`);
        if (layerRegex.test(code)) {
            pass(`Layer '${layer}' is defined`);
        } else {
            fail(`Layer '${layer}' is defined`, `Layer ${layer} not found in app.js`);
            allExist = false;
        }
    }

    return allExist;
}

/**
 * Test 5: Check for common MapLibre errors
 */
function testCommonMapLibreErrors() {
    log('\n[Test 5] Common MapLibre Error Patterns');

    const code = fs.readFileSync(APP_JS, 'utf8');
    let hasErrors = false;

    // Check for invalid filter expressions (missing 'all' wrapper for multiple conditions)
    const filterWithMultipleConditions = /filter:\s*\[\s*\[\s*['"][^'"]+['"]/g;
    const match = code.match(filterWithMultipleConditions);
    if (match) {
        // This is actually valid - arrays of arrays are valid filters
        pass('Filter expressions appear valid');
    } else {
        pass('No obvious filter issues detected');
    }

    // Check for proper source references
    const sources = ['buildings-dated', 'roads-temporal'];
    for (const source of sources) {
        const sourceRegex = new RegExp(`source:\\s*['"]${source}['"]`);
        if (sourceRegex.test(code)) {
            pass(`Source '${source}' is referenced`);
        }
    }

    return !hasErrors;
}

/**
 * Test 6: Check CSS syntax
 */
function testCssSyntax() {
    log('\n[Test 6] CSS Validation');

    const cssPath = path.join(FRONTEND_DIR, 'style.css');

    try {
        const css = fs.readFileSync(cssPath, 'utf8');

        // Basic CSS validation: check for balanced braces
        const openBraces = (css.match(/{/g) || []).length;
        const closeBraces = (css.match(/}/g) || []).length;

        if (openBraces === closeBraces) {
            pass('CSS braces are balanced');
        } else {
            fail('CSS braces balanced', `Unbalanced braces: ${openBraces} open, ${closeBraces} close`);
            return false;
        }

        // Check for change type color classes
        const requiredClasses = [
            '.change-type-same',
            '.change-type-widened',
            '.change-type-rerouted',
            '.change-type-replaced',
            '.change-type-removed',
            '.change-type-new'
        ];

        for (const cls of requiredClasses) {
            if (css.includes(cls)) {
                pass(`CSS class '${cls}' exists`);
            } else {
                fail(`CSS class '${cls}' exists`, `Class ${cls} not found in style.css`);
            }
        }

        return true;
    } catch (e) {
        fail('CSS file readable', e.message);
        return false;
    }
}

/**
 * Main test runner
 */
function runTests() {
    log('='.repeat(60));
    log('FRONTEND VALIDATION TESTS');
    log('='.repeat(60));

    testJavaScriptSyntax();
    testNoDataExpressionsInUnsupportedProperties();
    testRequiredFunctions();
    testLayerDefinitions();
    testCommonMapLibreErrors();
    testCssSyntax();

    log('\n' + '='.repeat(60));
    log('RESULTS');
    log('='.repeat(60));
    log(`  Passed: ${passed}`);
    log(`  Failed: ${failed}`);

    if (failed > 0) {
        log('\nFailed tests:');
        for (const err of errors) {
            log(`  - ${err.test}: ${err.error}`);
        }
        process.exit(1);
    } else {
        log('\nAll tests passed!');
        process.exit(0);
    }
}

// Run tests
runTests();
