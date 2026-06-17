import * as vscode from 'vscode';

import {
    getAttestedSystemSummary,
    getAgentAttestation,
    getAIInvolvementSummary,
    getEditorProvenance,
    getEditorProvenanceSummary,
    hasEditorProvenance,
    isAIAuthored,
    signalCount,
    authorshipClass,
} from './receipt_metadata';
import {
    EVIDENCE_TIER_LABELS,
    EVIDENCE_TIER_SHORT_LABELS,
    EVIDENCE_TIER_UPGRADE_GUIDANCE,
    getEvidenceTier,
} from './evidence_tier';
import {
    getReceiptReviewStatusLabel,
    type ReceiptReviewInfo,
} from './review_metadata';
import {
    type ReceiptRecordLike as ReceiptFailureRecordLike,
    type ReceiptRepairPlan,
} from './receipt_commands';
import {
    escapeHtml,
    getPanelScript,
    renderCommandCall,
} from './panel_shared';
import { type ReceiptData, type VerifyResult } from './receipt_verifier';

export interface ReceiptArtifactsLike {
    cborStatus: 'present' | 'missing';
    sigstoreStatus: 'present' | 'missing';
}

export interface ReceiptRecordLike extends ReceiptFailureRecordLike {
    receipt: ReceiptData;
    result: VerifyResult;
    artifacts: ReceiptArtifactsLike;
    review?: ReceiptReviewInfo;
}

function summarizeAttestedDiff(beforeHash?: string, afterHash?: string): string {
    const before = beforeHash ? beforeHash.slice(0, 12) : 'unknown';
    const after = afterHash ? afterHash.slice(0, 12) : 'unknown';
    return `${before} -> ${after}`;
}

interface ViewerDecisionSummary {
    title: string;
    detail: string;
    nextStep: string;
    tone: 'ok' | 'warning' | 'error';
}

function hasInferenceBinding(receipt: ReceiptData): boolean {
    if (receipt.model_fingerprint && receipt.tokens && receipt.granularity) {
        return true;
    }
    const ext = receipt.extensions as Record<string, unknown> | undefined;
    if (!ext || typeof ext !== 'object') {
        return false;
    }
    const ir = ext.inference_receipt as Record<string, unknown> | undefined;
    return !!(ir && typeof ir === 'object' && (ir.hash || ir.receipt_hash));
}

function getViewerDecisionSummary(
    record: ReceiptRecordLike,
    reviewExpected: boolean,
    evidenceTier: keyof typeof EVIDENCE_TIER_SHORT_LABELS,
    primaryRepairLabel: string,
): ViewerDecisionSummary {
    if (!record.result.valid) {
        return {
            title: 'Verification failed. Repair or regenerate for the same commit.',
            detail: 'The receipt body no longer matches the integrity fields stored inside it, so AIIR cannot treat this proof as trustworthy.',
            nextStep: `${primaryRepairLabel} to replace the failed proof with a fresh receipt for the intended commit.`,
            tone: 'error',
        };
    }

    if (record.review?.outcome === 'approve' && evidenceTier === 'signed') {
        return {
            title: 'Signed and reviewed. No action needed.',
            detail: 'This receipt has passing integrity checks, a Sigstore signing layer, and a recorded approval.',
            nextStep: 'Keep working or open the raw JSON if you need to inspect the original proof.',
            tone: 'ok',
        };
    }

    if (record.review?.outcome === 'reject' || record.review?.outcome === 'flag') {
        return {
            title: 'Receipt valid, but review raised concerns.',
            detail: 'The proof still verifies, but the recorded review outcome says this commit needs attention before you treat it as compliant.',
            nextStep: 'Review this commit again, address the reviewer feedback, or record an explicit exception if policy allows it.',
            tone: 'warning',
        };
    }

    if (reviewExpected && !record.review) {
        return {
            title: 'Receipt valid, but review is still missing.',
            detail: 'The proof verifies, but AI involvement is present and no human review attestation is attached yet.',
            nextStep: 'Review this commit now so the receipt carries both machine-verifiable evidence and human sign-off.',
            tone: 'warning',
        };
    }

    if (evidenceTier === 'provable') {
        return {
            title: 'Provable evidence present, but unsigned for stricter workflow.',
            detail: 'Deterministic editor provenance is attached, but there is no Sigstore signature yet for audit-grade non-repudiation.',
            nextStep: 'Sign this in CI if your workflow requires stronger release evidence.',
            tone: 'warning',
        };
    }

    if (evidenceTier === 'inference-bound') {
        return {
            title: 'Inference binding present, but stronger evidence is still available.',
            detail: 'This receipt cryptographically binds model output to inference parameters, but it does not yet have a Sigstore signing layer.',
            nextStep: 'Sign this in CI if you need audit-grade non-repudiation on top of inference binding.',
            tone: 'warning',
        };
    }

    if (evidenceTier === 'heuristic') {
        return {
            title: 'Receipt valid, but stronger evidence is still missing.',
            detail: 'AI involvement is detected, but this receipt still relies on heuristic signals rather than deterministic editor provenance or signing.',
            nextStep: 'Generate with provenance next time so AIIR records deterministic editor attestation for this workflow.',
            tone: 'warning',
        };
    }

    if (evidenceTier === 'unsigned') {
        return {
            title: 'Receipt valid, but the evidence bar is still low.',
            detail: 'The receipt verifies, but it has neither deterministic editor provenance nor a signing layer.',
            nextStep: 'Generate with provenance next time, then add CI signing if you need stronger public evidence.',
            tone: 'warning',
        };
    }

    return {
        title: 'Receipt valid. No action needed.',
        detail: 'The receipt passes integrity checks and does not currently require extra review or stronger evidence for the default workflow.',
        nextStep: 'Copy the Markdown summary or open the raw JSON if you need to share or inspect the proof.',
        tone: 'ok',
    };
}

export function getReceiptViewerHtml(
    record: ReceiptRecordLike,
    getReceiptFailureExplanation: (record: ReceiptFailureRecordLike) => string,
    repairPlan?: ReceiptRepairPlan,
): string {
    const { receipt: r, result, artifacts } = record;

    const sha = r.commit?.sha || '—';
    const shaShort = sha.length > 12 ? sha.slice(0, 12) : sha;
    const author = r.commit?.author?.name || '—';
    const authorEmail = r.commit?.author?.email || '';
    const subject = r.commit?.subject || '—';
    const filesChanged = r.commit?.files_changed ?? 0;
    const files = r.commit?.files || [];

    const isAI = isAIAuthored(r);
    const aiInvolvement = getAIInvolvementSummary(r);
    const aClass = authorshipClass(r);
    const signals = r.ai_attestation?.signals_detected || [];
    const botSignals = r.ai_attestation?.bot_signals_detected || [];
    const sCount = signalCount(r);
    const agent = getAgentAttestation(r);
    const editorProvenance = getEditorProvenance(r);
    const editorRecord = editorProvenance?.records?.[0];
    const inferenceBindingPresent = hasInferenceBinding(r);
    const isStandaloneInferenceReceipt = !!((r as Record<string, unknown>).model_fingerprint && (r as Record<string, unknown>).tokens && (r as Record<string, unknown>).granularity);
    const inferenceExtensions = (r.extensions as Record<string, unknown> | undefined)?.inference_receipt as Record<string, unknown> | undefined;
    const evidenceTier = getEvidenceTier({
        sigstorePresent: artifacts.sigstoreStatus === 'present',
        inferenceReceiptPresent: inferenceBindingPresent,
        editorProvenancePresent: hasEditorProvenance(r),
        aiInvolvementDetected: isAI || !!agent?.tool_id,
    });
    const reviewExpected = isAI || !!agent?.tool_id;
    const evidenceUpgradeGuidance = EVIDENCE_TIER_UPGRADE_GUIDANCE[evidenceTier];
    const reviewStatus = getReceiptReviewStatusLabel(record.review, reviewExpected);
    const attestedDiffRows = (editorProvenance?.records ?? []).flatMap((provenanceRecord, recordIndex) =>
        (provenanceRecord.files ?? []).map((file, fileIndex) => ({
            id: provenanceRecord.id || `record-${recordIndex + 1}`,
            path: file.path || `file-${fileIndex + 1}`,
            command: provenanceRecord.command || provenanceRecord.source || 'update',
            createdAt: provenanceRecord.createdAt || 'unknown time',
            source: provenanceRecord.source || 'unknown source',
            promptKind: provenanceRecord.promptKind || '',
            baseCommitSha: provenanceRecord.baseCommitSha || '',
            diffSummary: summarizeAttestedDiff(file.beforeHash, file.afterHash),
        })),
    );

    const generator = r.provenance?.generator || '—';
    const repository = r.provenance?.repository || '';

    const aiField = escapeHtml(aiInvolvement);
    const aiSignalsField = isAI
        ? `YES (${signals.map(s => escapeHtml(s)).join(', ')})`
        : 'NO';

    const badgeClass = aClass === 'human' ? 'human' : aClass === 'bot' ? 'bot' : 'ai';

    const summaryRows: [string, string][] = isStandaloneInferenceReceipt
        ? [
            ['Receipt Type', 'Inference receipt'],
            ['Evidence Tier', escapeHtml(EVIDENCE_TIER_LABELS[evidenceTier])],
            ['Review Status', escapeHtml(reviewStatus)],
            ['Version', escapeHtml(r.version || '—')],
            ['Schema', `<code>${escapeHtml(r.schema || '—')}</code>`],
            ['Timestamp', escapeHtml(r.timestamp || '—')],
        ]
        : [
            ['Receipt ID', `<code>${escapeHtml(r.receipt_id || '—')}</code>`],
            ['Commit', `<code>${escapeHtml(sha)}</code>`],
            ['Subject', escapeHtml(subject)],
            ['Author', `${escapeHtml(author)}${authorEmail ? ` &lt;${escapeHtml(authorEmail)}&gt;` : ''}`],
            ['AI Involvement', aiField],
            ['AI Signals Detected', aiSignalsField],
            ['Evidence Tier', escapeHtml(EVIDENCE_TIER_LABELS[evidenceTier])],
            ['Review Status', escapeHtml(reviewStatus)],
            ['Attested Tool', escapeHtml(getAttestedSystemSummary(r))],
            ['Editor Provenance', escapeHtml(getEditorProvenanceSummary(r))],
            ['Authorship', `<span class="badge ${badgeClass}">${escapeHtml(aClass)}</span>`],
            ['Version', escapeHtml(r.version || '—')],
            ['Schema', `<code>${escapeHtml(r.schema || '—')}</code>`],
            ['Timestamp', escapeHtml(r.timestamp || '—')],
        ];

    if (inferenceBindingPresent) {
        summaryRows.push([
            'Inference Binding',
            escapeHtml(isStandaloneInferenceReceipt ? 'Standalone inference receipt' : 'Embedded inference reference present'),
        ]);
    }

    if (isStandaloneInferenceReceipt) {
        const modelFingerprint = typeof r.model_fingerprint === 'string' ? r.model_fingerprint : '—';
        const granularity = typeof r.granularity === 'string' ? r.granularity : '—';
        const tokenCount = Array.isArray(r.tokens) ? r.tokens.length : 0;
        const storedHash = typeof r.hash === 'string'
            ? r.hash
            : typeof r.receipt_hash === 'string'
                ? r.receipt_hash
                : '—';
        summaryRows.push(['Granularity', escapeHtml(granularity)]);
        summaryRows.push(['Model Fingerprint', `<code>${escapeHtml(modelFingerprint)}</code>`]);
        summaryRows.push(['Tokens', escapeHtml(String(tokenCount))]);
        summaryRows.push(['Receipt Hash', `<code>${escapeHtml(storedHash)}</code>`]);
        if (typeof r.prev_hash === 'string' && r.prev_hash) {
            summaryRows.push(['Previous Hash', `<code>${escapeHtml(r.prev_hash)}</code>`]);
        }
    } else if (inferenceExtensions && typeof inferenceExtensions === 'object') {
        const extHash = typeof inferenceExtensions.hash === 'string'
            ? inferenceExtensions.hash
            : typeof inferenceExtensions.receipt_hash === 'string'
                ? inferenceExtensions.receipt_hash
                : '—';
        summaryRows.push(['Inference Receipt Hash', `<code>${escapeHtml(extHash)}</code>`]);
    }

    const signalTags = signals.length > 0
        ? signals.map(s => `<code class="signal">${escapeHtml(s)}</code>`).join(' ')
        : '<span class="dim">None detected</span>';

    const botSignalTags = botSignals.length > 0
        ? botSignals.map(s => `<code class="signal bot-signal">${escapeHtml(s)}</code>`).join(' ')
        : '';

    const filesList = files.length > 0
        ? `<details><summary>${filesChanged} file${filesChanged !== 1 ? 's' : ''} changed</summary><ul class="files">${files.map(f => `<li>${escapeHtml(f)}</li>`).join('')}</ul></details>`
        : `<p class="dim">${filesChanged} file${filesChanged !== 1 ? 's' : ''} changed</p>`;
    const attestedDiffsList = attestedDiffRows.length > 0
        ? `<div class="diff-list">${attestedDiffRows.map(diff => `
            <div class="diff-card">
                <div class="diff-card-header">
                    <code>${escapeHtml(diff.path)}</code>
                    <span class="badge ok">attested</span>
                </div>
                <div class="diff-meta">
                    <span>${escapeHtml(diff.createdAt)}</span>
                    <span>${escapeHtml(diff.command)}</span>
                    <span>${escapeHtml(diff.diffSummary)}</span>
                </div>
                <div class="diff-submeta">
                    <span>Record ${escapeHtml(diff.id)}</span>
                    <span>Source ${escapeHtml(diff.source)}</span>
                    ${diff.promptKind ? `<span>Prompt ${escapeHtml(diff.promptKind)}</span>` : ''}
                    ${diff.baseCommitSha ? `<span>Base ${escapeHtml(diff.baseCommitSha.slice(0, 12))}</span>` : ''}
                </div>
            </div>`).join('')}</div>`
        : '<p class="dim">No attested diff-level editor updates were recorded.</p>';

    const extensionsHtml = (() => {
        if (!r.extensions || Object.keys(r.extensions).length === 0) { return ''; }
        const parts: string[] = [];
        if (agent) {
            parts.push('<div class="ext-block"><h3>Agent Attestation</h3><div class="row">');
            if (agent.tool_id) { parts.push(`<div class="field"><span class="dim">Tool</span>${escapeHtml(agent.tool_id)}</div>`); }
            if (agent.confidence) { parts.push(`<div class="field"><span class="dim">Confidence</span>${escapeHtml(agent.confidence)}</div>`); }
            if (agent.model_class) { parts.push(`<div class="field"><span class="dim">Model</span>${escapeHtml(agent.model_class)}</div>`); }
            if (agent.session_id) { parts.push(`<div class="field"><span class="dim">Session</span><code>${escapeHtml(agent.session_id)}</code></div>`); }
            parts.push('</div></div>');
        }
        if (editorProvenance && editorRecord) {
            parts.push('<div class="ext-block"><h3>Editor Provenance</h3><div class="row">');
            if (editorProvenance.toolId) { parts.push(`<div class="field"><span class="dim">Tool</span>${escapeHtml(editorProvenance.toolId)}</div>`); }
            if (editorProvenance.mode) { parts.push(`<div class="field"><span class="dim">Mode</span>${escapeHtml(editorProvenance.mode)}</div>`); }
            if (editorRecord.id) { parts.push(`<div class="field"><span class="dim">Record</span><code>${escapeHtml(editorRecord.id)}</code></div>`); }
            if (editorRecord.command) { parts.push(`<div class="field"><span class="dim">Command</span>${escapeHtml(editorRecord.command)}</div>`); }
            if (editorRecord.modelVendor || editorRecord.modelFamily) { parts.push(`<div class="field"><span class="dim">Model</span>${escapeHtml([editorRecord.modelVendor, editorRecord.modelFamily].filter(Boolean).join(' '))}</div>`); }
            if (editorRecord.files && editorRecord.files.length > 0) { parts.push(`<div class="field"><span class="dim">Files</span>${escapeHtml(editorRecord.files.map(file => file.path || '—').join(', '))}</div>`); }
            parts.push('</div></div>');
        }
        if (r.extensions.sigstore) {
            parts.push('<div class="ext-block"><h3>Sigstore</h3><span class="badge ok">signed</span></div>');
        }
        for (const [key, val] of Object.entries(r.extensions)) {
            if (key === 'agent_attestation' || key === 'sigstore' || key === 'editor_provenance') { continue; }
            parts.push(`<div class="ext-block"><h3>${escapeHtml(key)}</h3><pre>${escapeHtml(JSON.stringify(val, null, 2))}</pre></div>`);
        }
        return `<section><h2>Extensions</h2>${parts.join('')}</section>`;
    })();

    const rawJson = JSON.stringify(r, null, 2);
    const primaryRepairLabel = escapeHtml(repairPlan?.primaryAction?.label || 'Repair Receipt');
    const primaryRepairDescription = escapeHtml(repairPlan?.primaryAction?.description || 'Choose the lowest-friction recovery path for this receipt.');
    const decisionSummary = getViewerDecisionSummary(record, reviewExpected, evidenceTier, primaryRepairLabel);
    const receiptJsonLabel = escapeHtml(`Open Receipt JSON (${shaShort})`);
    const workspaceUri = record.workspaceFolderPath ? JSON.stringify(vscode.Uri.file(record.workspaceFolderPath).toString()) : undefined;
    const reviewWorkspaceEvidenceCommand = workspaceUri
        ? `cmd('aiir.showSummary', ${workspaceUri})`
        : `cmd('aiir.showSummary')`;
    const generateWithProvenanceCommand = workspaceUri
        ? `cmd('aiir.generateWithProvenance', ${workspaceUri})`
        : `cmd('aiir.generateWithProvenance')`;
    const reviewThisCommitCommand = renderCommandCall('aiir.reviewReceipt', [{ sha, uri: workspaceUri }]);
    const reviewHistoryCommand = workspaceUri
        ? renderCommandCall('aiir.viewReviewHistory', [workspaceUri])
        : `cmd('aiir.viewReviewHistory')`;
    const recordExceptionCommand = `cmd('aiir.recordException')`;
    const outcomeActions = [
        !result.valid
            ? repairPlan?.primaryAction
                ? `<button onclick="${renderCommandCall(repairPlan.primaryAction.command, repairPlan.primaryAction.args)}">${primaryRepairLabel}</button>`
                : `<button onclick="${renderCommandCall('aiir.repairReceipt', [record.uri.toString()])}">Repair Receipt</button>`
            : reviewExpected
                ? `<button onclick="${reviewThisCommitCommand}">Review Commit</button>`
                : '',
        `<button class="secondary" onclick="cmd('aiir.copyReceiptSummary')">Copy Markdown Summary</button>`,
        `<button class="secondary" onclick="cmd('aiir.previewReceiptSummary')">Preview Markdown</button>`,
        `<button class="secondary" onclick="cmd('aiir.openReceiptSource')">Open Receipt JSON</button>`,
    ].filter(Boolean).join('');
    const recoveryActions = !result.valid ? [
        repairPlan?.primaryAction
            ? `<button onclick="${renderCommandCall(repairPlan.primaryAction.command, repairPlan.primaryAction.args)}">${primaryRepairLabel}</button>`
            : `<button onclick="${renderCommandCall('aiir.repairReceipt', [record.uri.toString()])}">Show Recovery Options</button>`,
        repairPlan?.secondaryActions?.length
            ? `<button class="secondary" onclick="${renderCommandCall('aiir.repairReceipt', [record.uri.toString()])}">More Repair Options</button>`
            : '',
        `<button class="secondary" onclick="cmd('aiir.openReceiptSource')">${receiptJsonLabel}</button>`,
        `<button class="secondary" onclick="cmd('aiir.refresh')">Refresh Receipts</button>`,
    ].filter(Boolean).join('') : '';
    const recoveryChecklist = !result.valid ? [
        `<li><strong>Do this now:</strong> ${primaryRepairLabel}${repairPlan?.primaryAction ? ` to replace the failed proof with a fresh proof for the intended commit.` : ' to choose a recovery path.'}</li>`,
        `<li><strong>What AIIR changes:</strong> It records a fresh proof instead of editing this JSON in place, because AIIR proofs are content-addressed.</li>`,
        `<li><strong>If you need more context:</strong> Open the original JSON or use More Repair Options for coverage checks and artifact verification.</li>`,
    ].join('') : '';
    const exceptionsTitle = !result.valid
        ? 'No compliance exception is attached to this failed receipt.'
        : record.review?.outcome === 'reject' || record.review?.outcome === 'flag'
            ? 'A reviewer flagged this commit, but no formal compliance exception is recorded yet.'
            : 'No compliance exception is attached to this receipt.';
    const exceptionsDetail = !result.valid
        ? 'Verification failures are not exceptions by themselves. Record an exception only if policy allows you to accept the gap temporarily.'
        : reviewExpected && !record.review
            ? 'If you need to move forward before review is completed, record an exception with a concrete reason so the workflow stays explicit.'
            : evidenceTier === 'signed' && record.review?.outcome === 'approve'
                ? 'This receipt already carries strong evidence and review coverage, so no exception flow is needed for the normal public workflow.'
                : 'Use the exception flow only when you are deliberately accepting a review or evidence gap under policy.';

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Receipt ${escapeHtml(shaShort)}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: var(--vscode-font-family);
            color: var(--vscode-foreground);
            padding: 24px;
            max-width: 820px;
            line-height: 1.7;
        }
        h2 {
            font-size: 1.1em;
            margin-bottom: 12px;
            padding-bottom: 6px;
            border-bottom: 1px solid var(--vscode-panel-border);
        }
        h3 { font-size: 0.95em; margin-bottom: 8px; }
        section { margin-top: 28px; }
        code {
            font-family: var(--vscode-editor-font-family);
            font-size: 0.92em;
        }
        pre {
            white-space: pre-wrap;
            word-break: break-word;
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 8px;
            padding: 1.25em 1.5em;
            font-size: 0.88em;
            line-height: 1.6;
            margin-top: 8px;
        }
        .dim { font-size: 0.82em; opacity: 0.5; }
        .result-box {
            padding: 1.25em;
            border-radius: 8px;
            border: 2px solid var(--vscode-panel-border);
        }
        .result-box.ok {
            border-color: var(--vscode-testing-iconPassed);
            background: color-mix(in srgb, var(--vscode-testing-iconPassed) 6%, transparent);
        }
        .result-box.err {
            border-color: var(--vscode-testing-iconFailed);
            background: color-mix(in srgb, var(--vscode-testing-iconFailed) 6%, transparent);
        }
        .result-title {
            font-size: 1.2em;
            font-weight: 700;
            margin-bottom: 0.35em;
        }
        .result-box.ok .result-title { color: var(--vscode-testing-iconPassed); }
        .result-box.err .result-title { color: var(--vscode-testing-iconFailed); }
        .result-detail { font-size: 0.9em; opacity: 0.7; }
        .decision-summary {
            margin-top: 14px;
            padding: 14px;
            border-radius: 8px;
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            display: grid;
            gap: 8px;
        }
        .decision-summary.warning {
            border-color: color-mix(in srgb, var(--vscode-editorWarning-foreground) 35%, var(--vscode-panel-border));
        }
        .decision-summary.error {
            border-color: color-mix(in srgb, var(--vscode-testing-iconFailed) 35%, var(--vscode-panel-border));
        }
        .decision-summary.ok {
            border-color: color-mix(in srgb, var(--vscode-testing-iconPassed) 35%, var(--vscode-panel-border));
        }
        .decision-summary strong {
            font-size: 1.02em;
        }
        .summary-table {
            width: 100%;
            font-size: 0.88em;
            border-collapse: collapse;
            margin-top: 16px;
        }
        .summary-table td {
            padding: 0.35em 0.75em 0.35em 0;
            border-bottom: 1px solid var(--vscode-panel-border);
        }
        .summary-table td:first-child {
            font-weight: 600;
            white-space: nowrap;
            width: 120px;
            opacity: 0.7;
        }
        .summary-table td:last-child {
            word-break: break-all;
            font-family: var(--vscode-editor-font-family);
            font-size: 0.92em;
        }
        .badge {
            display: inline-block;
            font-size: 0.72em;
            font-weight: 600;
            border: 1.5px solid;
            border-radius: 99px;
            padding: 0.15em 0.65em;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            white-space: nowrap;
        }
        .badge.human { border-color: var(--vscode-testing-iconPassed); color: var(--vscode-testing-iconPassed); }
        .badge.ai { border-color: var(--vscode-charts-blue); color: var(--vscode-charts-blue); }
        .badge.bot { border-color: var(--vscode-editorWarning-foreground); color: var(--vscode-editorWarning-foreground); }
        .badge.ok { border-color: var(--vscode-testing-iconPassed); color: var(--vscode-testing-iconPassed); }
        .signal {
            display: inline-block;
            font-size: 0.82em;
            padding: 0.1em 0.4em;
            border-radius: 3px;
            background: color-mix(in srgb, var(--vscode-charts-blue) 8%, transparent);
            color: var(--vscode-charts-blue);
            margin: 0 0.15em 0.15em 0;
        }
        .signal.bot-signal {
            background: color-mix(in srgb, var(--vscode-editorWarning-foreground) 8%, transparent);
            color: var(--vscode-editorWarning-foreground);
        }
        .row { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
        .field {
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 8px;
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .files { font-size: 0.88em; list-style: none; margin-top: 6px; }
        .files li { padding: 2px 0; font-family: var(--vscode-editor-font-family); }
        details { margin-top: 8px; }
        details summary { cursor: pointer; font-size: 0.92em; }
        .ext-block { margin-bottom: 14px; }
        .diff-list {
            display: grid;
            gap: 10px;
            max-height: 360px;
            overflow-y: auto;
            padding-right: 4px;
        }
        .diff-card {
            border: 1px solid var(--vscode-panel-border);
            border-radius: 8px;
            background: var(--vscode-editor-background);
            padding: 12px;
        }
        .diff-card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 8px;
        }
        .diff-meta,
        .diff-submeta {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            font-size: 0.84em;
            opacity: 0.86;
        }
        .diff-submeta {
            margin-top: 6px;
            opacity: 0.7;
        }
        .callout-panel {
            padding: 1em 1.25em;
            border-radius: 8px;
            border: 1px solid var(--vscode-panel-border);
            background: var(--vscode-editor-background);
            margin-top: 20px;
            font-size: 0.88em;
            line-height: 1.6;
        }
        .callout-panel strong { display: block; margin-bottom: 0.4em; }
        .callout-panel p { margin: 0.25em 0; opacity: 0.8; }
        .recovery-shell {
            display: grid;
            gap: 14px;
        }
        .recovery-primary {
            padding: 14px;
            border-radius: 10px;
            border: 1px solid color-mix(in srgb, var(--vscode-testing-iconFailed) 35%, var(--vscode-panel-border));
            background: color-mix(in srgb, var(--vscode-testing-iconFailed) 4%, var(--vscode-editor-background));
        }
        .recovery-primary .eyebrow {
            font-size: 0.76em;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--vscode-testing-iconFailed);
            margin-bottom: 6px;
        }
        .recovery-checklist {
            margin: 0;
            padding-left: 18px;
            display: grid;
            gap: 8px;
        }
        .recovery-checklist li {
            opacity: 0.9;
        }
        .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
        button {
            font: inherit;
            cursor: pointer;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            font-size: 0.88em;
        }
        button:hover { background: var(--vscode-button-hoverBackground); }
        button.secondary {
            background: var(--vscode-button-secondaryBackground);
            color: var(--vscode-button-secondaryForeground);
        }
        button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
    </style>
</head>
<body>
    <section>
        <h2>Outcome</h2>
        <div class="result-box ${result.valid ? 'ok' : 'err'}">
            <div class="result-title">${result.valid ? 'Receipt is valid' : 'Verification failed'}</div>
            <div class="result-detail">${result.valid
            ? 'Content hash and receipt ID verified successfully.'
            : result.errors.map(e => escapeHtml(e)).join('; ')}</div>
            <div class="decision-summary ${decisionSummary.tone}">
                <strong>${escapeHtml(decisionSummary.title)}</strong>
                <p>${escapeHtml(decisionSummary.detail)}</p>
                <p><span class="dim">Next action</span><br>${escapeHtml(decisionSummary.nextStep)}</p>
            </div>
            <div class="actions">${outcomeActions}</div>
        </div>

        <table class="summary-table">
            <tbody>
                ${summaryRows.map(([label, value]) => `<tr><td>${label}</td><td>${value}</td></tr>`).join('\n                ')}
            </tbody>
        </table>
    </section>

    ${!result.valid ? `
    <section>
        <h2>Fix This Receipt</h2>
        <div class="callout-panel" style="border-left:3px solid var(--vscode-testing-iconFailed)">
            <div class="recovery-shell">
                <div class="recovery-primary">
                    <div class="eyebrow">Recommended Next Step</div>
                    <strong>${escapeHtml(repairPlan?.headline || 'This receipt cannot be repaired in place.')}</strong>
                    <p>${escapeHtml(repairPlan?.detail || getReceiptFailureExplanation(record))}</p>
                    <p>${primaryRepairDescription}</p>
                    <div class="actions">${recoveryActions}</div>
                </div>
                <div>
                    <strong>What Happens Next</strong>
                    <ol class="recovery-checklist">${recoveryChecklist}</ol>
                </div>
            </div>
        </div>
    </section>` : ''}

    <section>
        <h2>Evidence Tier</h2>
        <div class="callout-panel" style="border-left:3px solid ${evidenceTier === 'signed' ? 'var(--vscode-testing-iconPassed)' : evidenceTier === 'provable' ? 'var(--vscode-charts-blue)' : 'var(--vscode-editorWarning-foreground)'}">
            <strong>${escapeHtml(EVIDENCE_TIER_SHORT_LABELS[evidenceTier])} evidence</strong>
            ${evidenceTier === 'heuristic' ? '<p><strong>Heuristic only</strong></p>' : ''}
            <p>${escapeHtml(evidenceUpgradeGuidance)}</p>
            <div class="actions">
                ${evidenceTier === 'heuristic' || evidenceTier === 'unsigned'
            ? `<button onclick="${generateWithProvenanceCommand}">Generate With Provenance Next Time</button>`
            : ''}
                ${evidenceTier !== 'signed'
            ? `<button class="secondary" onclick="cmd('aiir.openSigningGuide')">Sign This In CI</button>`
            : ''}
                <button class="secondary" onclick="${reviewWorkspaceEvidenceCommand}">Review Workspace Evidence</button>
            </div>
        </div>
    </section>

    <section>
        <h2>Review</h2>
        <div class="callout-panel" style="border-left:3px solid ${record.review?.outcome === 'approve' ? 'var(--vscode-testing-iconPassed)' : record.review ? 'var(--vscode-editorWarning-foreground)' : 'var(--vscode-panel-border)'}">
            <strong>${escapeHtml(reviewStatus)}</strong>
            <p>${escapeHtml(record.review?.comment || (reviewExpected ? 'This receipt shows AI involvement and still needs human review attestation.' : 'No human review attestation is recorded for this receipt.'))}</p>
            <div class="row" style="margin-top:12px;">
                <div class="field"><span class="dim">Outcome</span>${escapeHtml(reviewStatus)}</div>
                <div class="field"><span class="dim">Reviewer</span>${escapeHtml(record.review?.reviewer || '—')}</div>
                <div class="field"><span class="dim">Reviewed At</span>${escapeHtml(record.review?.timestamp || '—')}</div>
            </div>
            <div class="actions">
                <button onclick="${reviewThisCommitCommand}">Review This Commit</button>
                <button class="secondary" onclick="${reviewHistoryCommand}">View Review History</button>
            </div>
        </div>
    </section>

    <section>
        <h2>AI Summary</h2>
        <div class="row" style="margin-bottom:12px;">
            <div class="field"><span class="dim">AI Involvement</span>${aiField}</div>
            <div class="field"><span class="dim">Authorship</span><span class="badge ${badgeClass}">${escapeHtml(aClass)}</span></div>
            <div class="field"><span class="dim">Attested Tool</span>${escapeHtml(getAttestedSystemSummary(r))}</div>
            <div class="field"><span class="dim">Editor Provenance</span>${escapeHtml(getEditorProvenanceSummary(r))}</div>
        </div>
        <div style="margin-bottom:8px"><strong style="font-size:0.88em">AI Signals</strong> (${sCount})</div>
        <div>${signalTags}</div>
        ${botSignalTags ? `<div style="margin-top:10px"><strong style="font-size:0.88em">Bot Signals</strong></div><div>${botSignalTags}</div>` : ''}
    </section>

    <section>
        <h2>Evidence</h2>
        <div class="callout-panel" style="margin-bottom:12px; border-left:3px solid ${evidenceTier === 'signed' ? 'var(--vscode-testing-iconPassed)' : evidenceTier === 'provable' ? 'var(--vscode-charts-blue)' : 'var(--vscode-editorWarning-foreground)'}">
            <strong>${escapeHtml(EVIDENCE_TIER_LABELS[evidenceTier])}</strong>
            <p>${escapeHtml(evidenceUpgradeGuidance)}</p>
        </div>
        <div class="row">
            <div class="field"><span class="dim">CBOR Sidecar</span>${artifacts.cborStatus === 'present' ? '<span class="badge ok">present</span>' : '<span class="dim">Missing</span>'}</div>
            <div class="field"><span class="dim">Sigstore Bundle</span>${artifacts.sigstoreStatus === 'present' ? '<span class="badge ok">signed</span>' : '<span class="dim">Missing</span>'}</div>
            <div class="field"><span class="dim">Content Hash</span><code style="word-break:break-all">${escapeHtml(r.content_hash || '—')}</code></div>
            <div class="field"><span class="dim">Generator</span>${escapeHtml(generator)}</div>
            ${repository ? `<div class="field"><span class="dim">Repository</span>${escapeHtml(repository)}</div>` : ''}
            <div class="field"><span class="dim">Schema</span><code>${escapeHtml(r.schema || '—')}</code> v${escapeHtml(r.version || '—')}</div>
            <div class="field"><span class="dim">Timestamp</span>${escapeHtml(r.timestamp || '—')}</div>
        </div>
        ${editorRecord ? `<div class="callout-panel"><strong>Deterministic editor provenance</strong><p>${escapeHtml(getEditorProvenanceSummary(r))}</p><p>Record: <code>${escapeHtml(editorRecord.id || '—')}</code>${editorProvenance?.toolId ? ` • Tool: ${escapeHtml(editorProvenance.toolId)}` : ''}</p></div>` : ''}
    </section>

    <section>
        <h2>Exceptions</h2>
        <div class="callout-panel" style="border-left:3px solid var(--vscode-editorWarning-foreground)">
            <strong>${escapeHtml(exceptionsTitle)}</strong>
            <p>${escapeHtml(exceptionsDetail)}</p>
            <div class="actions">
                <button class="secondary" onclick="${recordExceptionCommand}">Record Exception</button>
                <button class="secondary" onclick="${reviewWorkspaceEvidenceCommand}">Review Workspace Evidence</button>
            </div>
        </div>
    </section>

    <section>
        <h2>Files</h2>
        <div class="callout-panel" style="margin-bottom:12px;">
            <strong>Changed files</strong>
            <div style="margin-top:12px">${filesList}</div>
        </div>
        <div class="callout-panel">
            <strong>Attested diffs</strong>
            <p>${escapeHtml(attestedDiffRows.length > 0 ? `This receipt recorded ${attestedDiffRows.length} attested file update${attestedDiffRows.length === 1 ? '' : 's'}.` : 'This receipt does not include file-level deterministic editor provenance.')}</p>
            <h2>Attested Diffs</h2>
            <p>Scroll through recorded deterministic file updates and inspect the attested before/after hash chain for each file.</p>
            ${attestedDiffsList}
        </div>
    </section>

    ${!r.extensions?.sigstore ? '<div class="callout-panel" style="border-left:3px solid var(--vscode-editorWarning-foreground)"><strong>Unsigned receipt.</strong> This receipt is tamper-evident but not non-repudiable. For audit-grade evidence, enable Sigstore signing in CI.</div>' : ''}

    ${extensionsHtml}

    <section>
        <h2>Raw JSON</h2>
        <div class="callout-panel">
            <details>
                <summary>Open raw receipt JSON</summary>
                <pre>${escapeHtml(rawJson)}</pre>
            </details>
        </div>
    </section>

    <div class="callout-panel">
        <strong>Trust tiers</strong>
        <p>This viewer checks <strong>Tier 1 &mdash; content hash integrity</strong>.
        It proves the 6 core fields haven&rsquo;t been modified since the receipt was generated.</p>
        <p>For <strong>Tier 2 &mdash; Sigstore signing</strong>, verify the accompanying bundle:
        <code>aiir --verify receipt.json --verify-signature</code></p>
    </div>
    ${getPanelScript()}
</body>
</html>`;
}
