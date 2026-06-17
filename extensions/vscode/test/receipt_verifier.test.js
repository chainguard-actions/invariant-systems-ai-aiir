const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { canonicalJson, sha256, verify } = require('../out/receipt_verifier.js');

const testVectorsPath = path.join(__dirname, '..', '..', '..', 'schemas', 'test_vectors.json');
const testVectors = JSON.parse(fs.readFileSync(testVectorsPath, 'utf-8'));

test('canonicalJson matches expected Unicode-safe hashing behavior', () => {
    const input = { greeting: 'cafe\u0301', word: 'naïve' };
    const encoded = canonicalJson(input);
    assert.equal(encoded, '{"greeting":"cafe\\u0301","word":"na\\u00efve"}');
    assert.equal(sha256(encoded).length, 64);
});

test('verify matches published public conformance vectors', async (t) => {
    for (const vector of testVectors.vectors) {
        await t.test(vector.id, () => {
            const result = verify(vector.receipt);
            assert.deepEqual(result, vector.expected);
        });
    }
});

test('verify treats non-string integrity fields as mismatches', () => {
    const receipt = {
        type: 'aiir.commit_receipt',
        schema: 'aiir/commit_receipt/v1',
        version: '1.0.0',
        commit: {
            sha: 'abc',
        },
        ai_attestation: {
            is_ai_authored: false,
        },
        provenance: {
            generator: 'aiir-test',
        },
        content_hash: 7,
        receipt_id: null,
    };

    const result = verify(receipt);
    assert.equal(result.valid, false);
    assert.deepEqual(result.errors, ['content hash mismatch', 'receipt_id mismatch']);
});

test('verify accepts a valid inference receipt', () => {
    const core = {
        granularity: 'session',
        model_fingerprint: 'abc123',
        sampling_params: { temperature: 0.7, top_p: 0.9 },
        tokens: [101, 202, 303],
    };
    const hash = sha256(canonicalJson(core));
    const result = verify({ ...core, hash });
    assert.deepEqual(result, { valid: true, errors: [] });
});

test('verify accepts receipt_hash alias for inference receipt', () => {
    const core = {
        granularity: 'token',
        model_fingerprint: 'abc123',
        sampling_params: { temperature: 0.7 },
        tokens: [1],
    };
    const receipt_hash = sha256(canonicalJson(core));
    const result = verify({ ...core, receipt_hash });
    assert.deepEqual(result, { valid: true, errors: [] });
});

test('verify rejects tampered inference receipt', () => {
    const receipt = {
        granularity: 'session',
        model_fingerprint: 'abc123',
        sampling_params: { temperature: 0.7 },
        tokens: [101, 202, 303],
        hash: '0'.repeat(64),
    };
    const result = verify(receipt);
    assert.equal(result.valid, false);
    assert.deepEqual(result.errors, ['hash mismatch — receipt content does not match stored hash']);
});

test('verify rejects malformed inference receipt without crashing', () => {
    const receipt = {
        granularity: 'invalid',
        model_fingerprint: 'abc123',
        sampling_params: { temperature: 0.7 },
        tokens: [101, 202, 303],
        hash: 'abc',
    };
    const result = verify(receipt);
    assert.equal(result.valid, false);
    assert.match(result.errors[0], /invalid granularity/);
});
