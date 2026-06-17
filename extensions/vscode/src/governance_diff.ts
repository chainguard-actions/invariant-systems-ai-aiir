/**
 * AI governance diff viewer for AIIR.
 *
 * Not a conventional diff viewer — this is about *governance*: what changed,
 * who (or what) changed it, and what evidence exists.  It renders a webview
 * panel for a single commit showing each file's diff annotated with:
 *
 *   - AI tool involvement per hunk (Copilot, Claude, etc.)
 *   - Evidence tier per file (signed, provable, heuristic, none)
 *   - Editor provenance records linked to specific file ranges
 *   - Receipt verification status with inline repair actions
 *
 * This makes AIIR a natural red-team reviewer: every diff is interrogated
 * for AI governance posture, not just correctness.
 *
 * @license Apache-2.0
 */

import * as vscode from 'vscode';

// ── Types ─────────────────────────────────────────────────────────────

export interface GovernanceDiffFile {
    path: string;
    status: 'added' | 'modified' | 'deleted' | 'renamed';
    aiAssisted: boolean;
    aiTool?: string;
    evidenceKind: 'provable' | 'heuristic' | 'none';
    /** Editor provenance record IDs that cover this file. */
    provenanceRecordIds: string[];
    /** Whether model vendor/family is known for this file's edits. */
    modelAttested: boolean;
    modelInfo?: string;
}

export interface GovernanceDiffCommit {
    sha: string;
    shortSha: string;
    subject: string;
    authorName: string;
    authorDate: string;
    branch?: string;
}

export interface GovernanceDiffReceipt {
    exists: boolean;
    valid: boolean;
    evidenceTier?: string;
    sigstorePresent: boolean;
    inLedger: boolean;
    receiptUri?: string;
    errorSummary?: string;
}

export interface GovernanceDiffViewModel {
    commit: GovernanceDiffCommit;
    files: GovernanceDiffFile[];
    receipt: GovernanceDiffReceipt;
    /** Aggregate: any file has AI involvement. */
    hasAIInvolvement: boolean;
    /** Aggregate: all AI-touched files have provable evidence. */
    allProvable: boolean;
    /** Summary line for the panel title bar. */
    summaryLine: string;
}

// ── HTML rendering ────────────────────────────────────────────────────

export function getGovernanceDiffHtml(viewModel: GovernanceDiffViewModel): string {
    const { commit, files, receipt } = viewModel;

    const fileRows = files.map(file => {
        const statusBadge = escapeHtml(file.status);
        const aiBadge = file.aiAssisted
            ? `<span class="badge ai">${escapeHtml(file.aiTool ?? 'AI-assisted')}</span>`
            : '<span class="badge human">human</span>';
        const evidenceBadge = file.evidenceKind !== 'none'
            ? `<span class="badge evidence-${escapeHtml(file.evidenceKind)}">${escapeHtml(file.evidenceKind)}</span>`
            : '';
        const modelBadge = file.modelAttested
            ? `<span class="badge model">${escapeHtml(file.modelInfo ?? 'model attested')}</span>`
            : '';

        return `<tr>
            <td class="file-path">${escapeHtml(file.path)}</td>
            <td><span class="badge status-${escapeHtml(file.status)}">${statusBadge}</span></td>
            <td>${aiBadge}</td>
            <td>${evidenceBadge}${modelBadge}</td>
        </tr>`;
    }).join('\n');

    const receiptSection = receipt.exists
        ? renderReceiptStatus(receipt)
        : renderNoReceipt(commit);

    const governanceSummary = renderGovernanceSummary(viewModel);

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIIR Governance Diff — ${escapeHtml(commit.shortSha)}</title>
    <style>
        body {
            font-family: var(--vscode-font-family);
            color: var(--vscode-foreground);
            background: var(--vscode-editor-background);
            padding: 16px;
            line-height: 1.5;
        }
        h1 { font-size: 1.3em; margin-bottom: 4px; }
        .commit-meta { color: var(--vscode-descriptionForeground); margin-bottom: 16px; }
        .governance-summary {
            background: var(--vscode-editorWidget-background);
            border: 1px solid var(--vscode-editorWidget-border);
            border-radius: 4px;
            padding: 12px 16px;
            margin-bottom: 16px;
        }
        .governance-summary .verdict {
            font-size: 1.1em;
            font-weight: 600;
            margin-bottom: 8px;
        }
        .governance-summary .detail { color: var(--vscode-descriptionForeground); }
        table { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
        th { text-align: left; border-bottom: 1px solid var(--vscode-editorWidget-border); padding: 6px 8px; font-weight: 600; }
        td { padding: 6px 8px; border-bottom: 1px solid var(--vscode-editorWidget-border, transparent); }
        .file-path { font-family: var(--vscode-editor-font-family); }
        .badge {
            display: inline-block;
            padding: 1px 6px;
            border-radius: 3px;
            font-size: 0.85em;
            font-weight: 500;
        }
        .badge.ai { background: var(--vscode-editorWarning-foreground); color: var(--vscode-editor-background); }
        .badge.human { background: var(--vscode-editorInfo-foreground); color: var(--vscode-editor-background); }
        .badge.evidence-provable { background: var(--vscode-testing-iconPassed); color: var(--vscode-editor-background); }
        .badge.evidence-heuristic { background: var(--vscode-editorWarning-foreground); color: var(--vscode-editor-background); }
        .badge.model { background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); }
        .badge.status-added { color: var(--vscode-gitDecoration-addedResourceForeground); }
        .badge.status-modified { color: var(--vscode-gitDecoration-modifiedResourceForeground); }
        .badge.status-deleted { color: var(--vscode-gitDecoration-deletedResourceForeground); }
        .receipt-status {
            background: var(--vscode-editorWidget-background);
            border: 1px solid var(--vscode-editorWidget-border);
            border-radius: 4px;
            padding: 12px 16px;
            margin-bottom: 16px;
        }
        .receipt-status .tier { font-weight: 600; margin-bottom: 4px; }
        .receipt-status .badges { display: flex; gap: 8px; }
        .action-link {
            color: var(--vscode-textLink-foreground);
            cursor: pointer;
            text-decoration: underline;
        }
        .error-text { color: var(--vscode-errorForeground); }
        .section-title { font-size: 1.1em; font-weight: 600; margin: 16px 0 8px 0; }
    </style>
</head>
<body>
    <h1>${escapeHtml(commit.subject)}</h1>
    <div class="commit-meta">
        ${escapeHtml(commit.shortSha)} by ${escapeHtml(commit.authorName)} on ${escapeHtml(commit.authorDate)}${commit.branch ? ` \u2022 ${escapeHtml(commit.branch)}` : ''}
    </div>

    ${governanceSummary}

    <div class="section-title">Files Changed</div>
    <table>
        <thead>
            <tr>
                <th>File</th>
                <th>Status</th>
                <th>Authorship</th>
                <th>Evidence</th>
            </tr>
        </thead>
        <tbody>
            ${fileRows}
        </tbody>
    </table>

    ${receiptSection}
</body>
</html>`;
}

// ── Sub-renderers ─────────────────────────────────────────────────────

function renderGovernanceSummary(vm: GovernanceDiffViewModel): string {
    let verdict: string;
    let detail: string;
    let verdictClass = '';

    if (!vm.receipt.exists) {
        verdict = '\u26A0 No receipt — this commit has no AI governance coverage';
        detail = 'Generate a receipt to establish evidence for this commit.';
        verdictClass = 'error-text';
    } else if (!vm.receipt.valid) {
        verdict = '\u274C Receipt failing — evidence is compromised';
        detail = vm.receipt.errorSummary ?? 'Receipt verification failed. Repair to restore integrity.';
        verdictClass = 'error-text';
    } else if (!vm.hasAIInvolvement) {
        verdict = '\u2705 Human-authored commit — receipt present';
        detail = `Evidence tier: ${vm.receipt.evidenceTier ?? 'unknown'}. No AI involvement detected.`;
    } else if (vm.allProvable) {
        verdict = '\u2705 AI-assisted commit — fully attested';
        detail = `All AI-touched files have deterministic editor provenance. Evidence tier: ${vm.receipt.evidenceTier ?? 'unknown'}.`;
    } else {
        verdict = '\u26A0 AI-assisted commit — partial evidence';
        detail = 'Some AI-touched files lack deterministic provenance. Use "Generate With Provenance" for stronger evidence.';
    }

    const sigstoreLine = vm.receipt.exists
        ? (vm.receipt.sigstorePresent
            ? 'Sigstore: signed \u2713'
            : 'Sigstore: unsigned — sign in CI for audit-grade evidence')
        : '';
    const ledgerLine = vm.receipt.exists
        ? (vm.receipt.inLedger
            ? 'Ledger: recorded \u2713'
            : 'Ledger: not recorded')
        : '';

    return `<div class="governance-summary">
        <div class="verdict ${verdictClass}">${verdict}</div>
        <div class="detail">${escapeHtml(detail)}</div>
        ${sigstoreLine ? `<div class="detail">${sigstoreLine}</div>` : ''}
        ${ledgerLine ? `<div class="detail">${ledgerLine}</div>` : ''}
    </div>`;
}

function renderReceiptStatus(receipt: GovernanceDiffReceipt): string {
    if (!receipt.valid) {
        return `<div class="receipt-status">
            <div class="tier error-text">Receipt: FAILING</div>
            <div>${escapeHtml(receipt.errorSummary ?? 'Verification error')}</div>
        </div>`;
    }

    return `<div class="receipt-status">
        <div class="tier">Receipt: ${escapeHtml(receipt.evidenceTier ?? 'present')}</div>
        <div class="badges">
            <span class="badge">${receipt.sigstorePresent ? 'Sigstore \u2713' : 'Sigstore \u2717'}</span>
            <span class="badge">${receipt.inLedger ? 'Ledger \u2713' : 'Ledger \u2717'}</span>
        </div>
    </div>`;
}

function renderNoReceipt(commit: GovernanceDiffCommit): string {
    return `<div class="receipt-status">
        <div class="tier error-text">No Receipt</div>
        <div>This commit has no AIIR receipt. Generate one to establish governance coverage.</div>
    </div>`;
}

// ── Build from raw data ───────────────────────────────────────────────

export interface GovernanceDiffBuildInput {
    commit: GovernanceDiffCommit;
    files: Array<{
        path: string;
        gitStatus: string;
    }>;
    receipt?: {
        exists: boolean;
        valid: boolean;
        evidenceTier?: string;
        sigstorePresent: boolean;
        inLedger: boolean;
        receiptUri?: string;
        errorSummary?: string;
        /** Per-file AI involvement from receipt signals + editor provenance. */
        aiFileMap: ReadonlyMap<string, { tool?: string; evidenceKind: 'provable' | 'heuristic' | 'none'; modelInfo?: string }>;
    };
}

export function buildGovernanceDiffViewModel(input: GovernanceDiffBuildInput): GovernanceDiffViewModel {
    const aiFileMap = input.receipt?.aiFileMap ?? new Map();

    const files: GovernanceDiffFile[] = input.files.map(f => {
        const aiInfo = aiFileMap.get(f.path);
        const status = gitStatusToLabel(f.gitStatus);
        return {
            path: f.path,
            status,
            aiAssisted: !!aiInfo,
            aiTool: aiInfo?.tool,
            evidenceKind: aiInfo?.evidenceKind ?? 'none',
            provenanceRecordIds: [],
            modelAttested: !!aiInfo?.modelInfo,
            modelInfo: aiInfo?.modelInfo,
        };
    });

    const hasAIInvolvement = files.some(f => f.aiAssisted);
    const aiFiles = files.filter(f => f.aiAssisted);
    const allProvable = aiFiles.length > 0 && aiFiles.every(f => f.evidenceKind === 'provable');

    const receipt: GovernanceDiffReceipt = input.receipt
        ? {
            exists: input.receipt.exists,
            valid: input.receipt.valid,
            evidenceTier: input.receipt.evidenceTier,
            sigstorePresent: input.receipt.sigstorePresent,
            inLedger: input.receipt.inLedger,
            receiptUri: input.receipt.receiptUri,
            errorSummary: input.receipt.errorSummary,
        }
        : { exists: false, valid: false, sigstorePresent: false, inLedger: false };

    const coverageTag = receipt.exists
        ? (receipt.valid ? receipt.evidenceTier ?? 'receipted' : 'failing')
        : 'uncovered';
    const aiTag = hasAIInvolvement
        ? (allProvable ? 'attested' : 'partial')
        : 'human';
    const summaryLine = `${input.commit.shortSha} \u2022 ${coverageTag} \u2022 ${aiTag}`;

    return {
        commit: input.commit,
        files,
        receipt,
        hasAIInvolvement,
        allProvable,
        summaryLine,
    };
}

// ── Utility ───────────────────────────────────────────────────────────

function gitStatusToLabel(status: string): 'added' | 'modified' | 'deleted' | 'renamed' {
    switch (status.charAt(0).toUpperCase()) {
        case 'A': return 'added';
        case 'D': return 'deleted';
        case 'R': return 'renamed';
        default: return 'modified';
    }
}

function escapeHtml(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
