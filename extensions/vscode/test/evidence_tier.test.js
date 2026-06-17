const test = require('node:test');
const assert = require('node:assert/strict');

const {
    getEvidenceTier,
    EVIDENCE_TIER_LABELS,
    EVIDENCE_TIER_SHORT_LABELS,
    EVIDENCE_TIER_UPGRADE_GUIDANCE,
} = require('../out/evidence_tier.js');

test('signed tier when sigstore is present', () => {
    assert.equal(
        getEvidenceTier({
            sigstorePresent: true,
            inferenceReceiptPresent: true,
            editorProvenancePresent: true,
            aiInvolvementDetected: true,
        }),
        'signed'
    );
});

test('inference-bound tier when inference receipt present but no sigstore', () => {
    assert.equal(
        getEvidenceTier({
            sigstorePresent: false,
            inferenceReceiptPresent: true,
            editorProvenancePresent: true,
            aiInvolvementDetected: true,
        }),
        'inference-bound'
    );
});

test('provable tier when editor provenance present but no sigstore or inference', () => {
    assert.equal(
        getEvidenceTier({
            sigstorePresent: false,
            inferenceReceiptPresent: false,
            editorProvenancePresent: true,
            aiInvolvementDetected: true,
        }),
        'provable'
    );
});

test('heuristic tier when AI involvement detected but no provenance or sigstore', () => {
    assert.equal(
        getEvidenceTier({
            sigstorePresent: false,
            inferenceReceiptPresent: false,
            editorProvenancePresent: false,
            aiInvolvementDetected: true,
        }),
        'heuristic'
    );
});

test('unsigned tier when no signals present', () => {
    assert.equal(
        getEvidenceTier({
            sigstorePresent: false,
            inferenceReceiptPresent: false,
            editorProvenancePresent: false,
            aiInvolvementDetected: false,
        }),
        'unsigned'
    );
});

test('tier priority: signed > inference-bound > provable', () => {
    // Even with all lower tiers, sigstore wins
    assert.equal(
        getEvidenceTier({
            sigstorePresent: true,
            inferenceReceiptPresent: true,
            editorProvenancePresent: true,
            aiInvolvementDetected: false,
        }),
        'signed'
    );
    // inference-bound beats provable
    assert.equal(
        getEvidenceTier({
            sigstorePresent: false,
            inferenceReceiptPresent: true,
            editorProvenancePresent: true,
            aiInvolvementDetected: false,
        }),
        'inference-bound'
    );
});

test('tier priority: provable > heuristic', () => {
    assert.equal(
        getEvidenceTier({
            sigstorePresent: false,
            inferenceReceiptPresent: false,
            editorProvenancePresent: true,
            aiInvolvementDetected: false,
        }),
        'provable'
    );
});

test('EVIDENCE_TIER_LABELS covers all tiers', () => {
    const tiers = ['signed', 'inference-bound', 'provable', 'heuristic', 'unsigned'];
    for (const tier of tiers) {
        assert.ok(EVIDENCE_TIER_LABELS[tier], `missing label for ${tier}`);
        assert.equal(typeof EVIDENCE_TIER_LABELS[tier], 'string');
    }
});

test('EVIDENCE_TIER_LABELS has no extra keys', () => {
    const keys = Object.keys(EVIDENCE_TIER_LABELS);
    assert.deepEqual(keys.sort(), ['heuristic', 'inference-bound', 'provable', 'signed', 'unsigned']);
});

test('short tier labels cover all tiers', () => {
    const keys = Object.keys(EVIDENCE_TIER_SHORT_LABELS);
    assert.deepEqual(keys.sort(), ['heuristic', 'inference-bound', 'provable', 'signed', 'unsigned']);
    assert.equal(EVIDENCE_TIER_SHORT_LABELS.heuristic, 'Heuristic');
    assert.equal(EVIDENCE_TIER_SHORT_LABELS.signed, 'Signed');
    assert.equal(EVIDENCE_TIER_SHORT_LABELS['inference-bound'], 'Inference-Bound');
});

test('upgrade guidance covers all tiers', () => {
    const keys = Object.keys(EVIDENCE_TIER_UPGRADE_GUIDANCE);
    assert.deepEqual(keys.sort(), ['heuristic', 'inference-bound', 'provable', 'signed', 'unsigned']);
    assert.match(EVIDENCE_TIER_UPGRADE_GUIDANCE.heuristic, /Generate With Provenance/);
    assert.match(EVIDENCE_TIER_UPGRADE_GUIDANCE.provable, /Sigstore signing in CI/);
    assert.match(EVIDENCE_TIER_UPGRADE_GUIDANCE['inference-bound'], /hash chain/);
});
