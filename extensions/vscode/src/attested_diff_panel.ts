import {
    escapeHtml,
    getPanelScript,
    renderCommandCall,
} from './panel_shared';

export interface AttestedDiffPanelEvent {
    beforeHash?: string;
    afterHash?: string;
    command?: string;
    source?: string;
    promptKind?: string;
    createdAt?: string;
    baseCommitSha?: string;
    sessionId?: string;
    comparisonTarget?: {
        receiptUri: string;
        filePath: string;
        fileUri?: string;
        beforeHash?: string;
        afterHash?: string;
        baseCommitSha?: string;
        createdAt?: string;
    };
}

export interface AttestedDiffPanelInput {
    filePath: string;
    fileUri?: string;
    receiptUri: string;
    receiptSubject: string;
    receiptShaShort: string;
    eventCount: number;
    events: AttestedDiffPanelEvent[];
}

function summarizeAttestedDiffHashes(beforeHash?: string, afterHash?: string): string {
    const before = beforeHash ? beforeHash.slice(0, 12) : 'unknown';
    const after = afterHash ? afterHash.slice(0, 12) : 'unknown';
    return `${before} -> ${after}`;
}

export function getAttestedDiffPanelHtml(input: AttestedDiffPanelInput): string {
    const latest = input.events[input.events.length - 1];
    const historyCards = input.events.slice().reverse().map((event, index) => `
        <div class="history-card">
            <div class="history-card-header">
                <strong>Update ${input.eventCount - index}</strong>
                <span>${escapeHtml(event.createdAt || 'unknown time')}</span>
            </div>
            <div class="history-card-grid">
                <div class="field"><span class="dim">Diff</span><code>${escapeHtml(summarizeAttestedDiffHashes(event.beforeHash, event.afterHash))}</code></div>
                <div class="field"><span class="dim">Command</span>${escapeHtml(event.command || 'update')}</div>
                <div class="field"><span class="dim">Source</span>${escapeHtml(event.source || 'unknown source')}</div>
                <div class="field"><span class="dim">Prompt Kind</span>${escapeHtml(event.promptKind || '—')}</div>
                <div class="field"><span class="dim">Base Commit</span><code>${escapeHtml(event.baseCommitSha ? event.baseCommitSha.slice(0, 12) : '—')}</code></div>
                <div class="field"><span class="dim">Session</span><code>${escapeHtml(event.sessionId || '—')}</code></div>
            </div>
            ${event.comparisonTarget ? `<div class="actions history-actions"><button class="secondary" onclick="${renderCommandCall('aiir.openAttestedDiffComparison', [event.comparisonTarget])}">Open Recoverable Diff</button></div>` : ''}
        </div>`).join('');

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${escapeHtml(input.filePath)}</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: var(--vscode-font-family);
            color: var(--vscode-foreground);
            padding: 24px;
            max-width: 980px;
            line-height: 1.6;
        }
        h1 {
            font-size: 1.25em;
            margin: 0 0 6px;
        }
        h2 {
            font-size: 1.05em;
            margin: 0 0 12px;
        }
        code {
            font-family: var(--vscode-editor-font-family);
            font-size: 0.92em;
        }
        .subtitle {
            opacity: 0.72;
            margin-bottom: 18px;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px;
            margin: 18px 0 22px;
        }
        .field {
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 8px;
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 4px;
            min-width: 0;
            word-break: break-word;
        }
        .dim {
            font-size: 0.8em;
            opacity: 0.6;
        }
        .actions {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 0 0 22px;
        }
        button {
            font: inherit;
            cursor: pointer;
            border: none;
            border-radius: 6px;
            padding: 8px 14px;
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
        }
        button:hover { background: var(--vscode-button-hoverBackground); }
        button.secondary {
            background: var(--vscode-button-secondaryBackground);
            color: var(--vscode-button-secondaryForeground);
        }
        button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
        .history-shell {
            border: 1px solid var(--vscode-panel-border);
            border-radius: 10px;
            background: var(--vscode-editor-background);
            padding: 14px;
        }
        .history-list {
            display: grid;
            gap: 10px;
            max-height: 520px;
            overflow-y: auto;
            padding-right: 4px;
        }
        .history-card {
            border: 1px solid var(--vscode-panel-border);
            border-radius: 8px;
            padding: 12px;
            background: color-mix(in srgb, var(--vscode-editor-background) 94%, var(--vscode-panel-border) 6%);
        }
        .history-card-header {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 10px;
            font-size: 0.9em;
        }
        .history-card-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px;
        }
        .history-actions {
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <h1>${escapeHtml(input.filePath)}</h1>
    <p class="subtitle">Attested deterministic editor history for ${escapeHtml(input.receiptSubject)} (${escapeHtml(input.receiptShaShort)})</p>

    <div class="actions">
        ${input.fileUri ? `<button onclick="${renderCommandCall('aiir.openTreeFile', [input.fileUri])}">Open Tracked File</button>` : ''}
        ${latest?.comparisonTarget ? `<button onclick="${renderCommandCall('aiir.openAttestedDiffComparison', [latest.comparisonTarget])}">Open Latest Recoverable Diff</button>` : ''}
        <button class="secondary" onclick="${renderCommandCall('aiir.viewReceipt', [input.receiptUri])}">Open Pretty Receipt</button>
        <button class="secondary" onclick="${renderCommandCall('aiir.openReceiptSource', [input.receiptUri])}">Open Receipt JSON</button>
    </div>

    <div class="summary-grid">
        <div class="field"><span class="dim">Recorded Updates</span>${escapeHtml(String(input.eventCount))}</div>
        <div class="field"><span class="dim">Latest Diff</span><code>${escapeHtml(summarizeAttestedDiffHashes(latest?.beforeHash, latest?.afterHash))}</code></div>
        <div class="field"><span class="dim">Latest Command</span>${escapeHtml(latest?.command || 'update')}</div>
        <div class="field"><span class="dim">Latest Source</span>${escapeHtml(latest?.source || 'unknown source')}</div>
    </div>

    <section class="history-shell">
        <h2>Attested Update History</h2>
        <p class="subtitle">Compare is available when hashes match recoverable base, receipt, or workspace snapshots. Diff titles name the exact matched sources when compare is available.</p>
        <div class="history-list">
            ${historyCards}
        </div>
    </section>

    ${getPanelScript()}
</body>
</html>`;
}
