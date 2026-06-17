// SPDX-License-Identifier: Apache-2.0

/**
 * Evidence tier classification for AIIR receipts.
 *
 * Tiers are ordered by assurance level:
 *   signed > inference-bound > provable > heuristic > unsigned
 */

export type EvidenceTier = 'signed' | 'inference-bound' | 'provable' | 'heuristic' | 'unsigned';

export interface EvidenceTierInput {
    sigstorePresent: boolean;
    inferenceReceiptPresent: boolean;
    editorProvenancePresent: boolean;
    aiInvolvementDetected: boolean;
}

export function getEvidenceTier(input: EvidenceTierInput): EvidenceTier {
    if (input.sigstorePresent) {
        return 'signed';
    }
    if (input.inferenceReceiptPresent) {
        return 'inference-bound';
    }
    if (input.editorProvenancePresent) {
        return 'provable';
    }
    if (input.aiInvolvementDetected) {
        return 'heuristic';
    }
    return 'unsigned';
}

export const EVIDENCE_TIER_LABELS: Record<EvidenceTier, string> = {
    signed: 'Signed — Sigstore bundle present; audit-grade non-repudiable evidence',
    'inference-bound': 'Inference-Bound — model output cryptographically committed via hash chain',
    provable: 'Provable — deterministic editor provenance recorded',
    heuristic: 'Heuristic — AI involvement detected from commit signals or agent declaration',
    unsigned: 'Unsigned — receipt present but no signing or provenance layer',
};

export const EVIDENCE_TIER_SHORT_LABELS: Record<EvidenceTier, string> = {
    signed: 'Signed',
    'inference-bound': 'Inference-Bound',
    provable: 'Provable',
    heuristic: 'Heuristic',
    unsigned: 'Unsigned',
};

export const EVIDENCE_TIER_UPGRADE_GUIDANCE: Record<EvidenceTier, string> = {
    signed: 'Signed receipts already carry the strongest public evidence tier. Keep deterministic provenance enabled so the AI system and edit session stay attached before CI signing.',
    'inference-bound': 'This receipt binds model output tokens to inference parameters via a verifiable hash chain. Add Sigstore signing in CI when you need audit-grade non-repudiation on top of inference binding.',
    provable: 'Deterministic editor provenance is present. Add Sigstore signing in CI or release automation when you need audit-grade non-repudiation.',
    heuristic: 'This receipt relies on heuristic or declared AI signals. Next time, use Generate from an active file or Generate With Provenance before commit so AIIR records deterministic editor attestation.',
    unsigned: 'The receipt is present, but there is no deterministic provenance or signing layer yet. Prefer Generate With Provenance for the next edit session, then sign in CI for the strongest release evidence.',
};
