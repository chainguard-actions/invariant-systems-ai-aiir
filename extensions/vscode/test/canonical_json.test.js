const test = require('node:test');
const assert = require('node:assert/strict');

const { canonicalJson } = require('../out/canonical_json.js');

test('canonicalJson preserves provenance-style JSON by default', () => {
    const input = { greeting: 'cafe\u0301', word: 'naïve' };
    const encoded = canonicalJson(input);

    assert.equal(encoded, '{"greeting":"café","word":"naïve"}');
});

test('canonicalJson supports verifier-style Unicode escaping and finite-number checks', () => {
    const input = { greeting: 'cafe\u0301', word: 'naïve' };
    const encoded = canonicalJson(input, {
        escapeUnicode: true,
        maxDepth: 64,
        rejectNonFiniteNumbers: true,
    });

    assert.equal(encoded, '{"greeting":"cafe\\u0301","word":"na\\u00efve"}');
    assert.throws(
        () => canonicalJson({ bad: Number.NaN }, { rejectNonFiniteNumbers: true }),
        /NaN\/Infinity not allowed/,
    );
});

test('canonicalJson enforces the configured depth limit', () => {
    assert.throws(
        () => canonicalJson({ a: { b: { c: 1 } } }, { maxDepth: 1 }),
        /depth limit exceeded/,
    );
});
