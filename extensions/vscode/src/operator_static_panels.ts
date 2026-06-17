import { escapeHtml } from './panel_shared';

export interface JsonRecordLike {
    [key: string]: unknown;
}

export interface DetectedAIToolLike {
    toolName: string;
    extensionId: string;
    isActive: boolean;
}

export function getSigningGuideHtml(): string {
    return `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Sigstore Signing Guide</title>
<style>
body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 24px; max-width: 720px; line-height: 1.7; }
h1 { font-size: 1.3em; margin-bottom: 16px; }
h2 { font-size: 1.1em; margin-top: 24px; margin-bottom: 8px; border-bottom: 1px solid var(--vscode-panel-border); padding-bottom: 4px; }
code { font-family: var(--vscode-editor-font-family); font-size: 0.92em; background: var(--vscode-editor-background); padding: 0.1em 0.3em; border-radius: 3px; }
pre { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 8px; padding: 12px 16px; font-size: 0.88em; overflow-x: auto; }
.callout { border-left: 3px solid var(--vscode-editorInfo-foreground); padding: 12px; margin: 16px 0; background: color-mix(in srgb, var(--vscode-editorInfo-foreground) 5%, transparent); border-radius: 4px; }
</style></head><body>
<h1>Sigstore Signing Guide</h1>
<div class="callout"><strong>Why sign?</strong> Signed receipts are non-repudiable and audit-grade. Unsigned receipts are tamper-evident but do not provide third-party verifiable proof of authorship.</div>

<h2>GitHub Actions</h2>
<p>Add the <code>--sign</code> flag to your AIIR CI step. Sigstore signing uses ambient OIDC credentials available in GitHub Actions automatically.</p>
<pre>- uses: invariant-systems-ai/aiir@v1
  with:
    sign: true</pre>

<h2>GitLab CI/CD</h2>
<p>Add <code>AIIR_SIGN=1</code> to your CI variables. Requires the optional <code>sigstore</code> Python package.</p>
<pre>aiir-receipt:
  script:
    - pip install aiir[sigstore]
    - aiir --sign</pre>

<h2>Local signing</h2>
<p>From VS Code you can run <code>AIIR: Install Sigstore Support</code>, or install the optional Sigstore package manually and use the <code>--sign</code> flag:</p>
<pre>pip install aiir[sigstore]
aiir --sign</pre>
<p>Local signing opens a browser for OIDC authentication on first use.</p>

<h2>Verifying signatures</h2>
<p>Signed receipts include a <code>.sigstore</code> bundle. Verification:</p>
<pre>aiir verify --sigstore</pre>
</body></html>`;
}

export function getReviewHistoryHtml(reviews: JsonRecordLike[]): string {
    const rows = reviews.map(review => {
        const outcome = String(review.review_outcome || 'unknown');
        const sha = String(review.commit_sha || review.sha || '').slice(0, 12);
        const ts = String(review.timestamp || review.reviewed_at || '—');
        const comment = String(review.review_comment || review.comment || '—');
        const badgeClass = outcome === 'approve' ? 'ok' : 'off';
        return `<tr><td><code>${escapeHtml(sha)}</code></td><td><span class="badge ${badgeClass}">${escapeHtml(outcome)}</span></td><td>${escapeHtml(ts)}</td><td>${escapeHtml(comment)}</td></tr>`;
    }).join('\n');

    return `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Review History</title>
<style>
body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 24px; line-height: 1.7; }
h1 { font-size: 1.3em; margin-bottom: 16px; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 8px; border-bottom: 1px solid var(--vscode-panel-border); }
th { font-weight: 600; opacity: 0.7; font-size: 0.9em; }
code { font-family: var(--vscode-editor-font-family); font-size: 0.92em; }
.badge { display: inline-block; font-size: 0.75em; font-weight: 600; border: 1.5px solid; border-radius: 99px; padding: 0.15em 0.55em; text-transform: uppercase; }
.badge.ok { border-color: var(--vscode-testing-iconPassed); color: var(--vscode-testing-iconPassed); }
.badge.off { border-color: var(--vscode-editorWarning-foreground); color: var(--vscode-editorWarning-foreground); }
</style></head><body>
<h1>Review History (${reviews.length} review${reviews.length === 1 ? '' : 's'})</h1>
<table><thead><tr><th>Commit</th><th>Outcome</th><th>Timestamp</th><th>Comment</th></tr></thead>
<tbody>${rows}</tbody></table>
</body></html>`;
}

export function getDetectedToolsHtml(tools: DetectedAIToolLike[]): string {
    if (tools.length === 0) {
        return '<p style="opacity:0.7">No AI coding extensions detected. Receipts will rely on commit-message heuristics only.</p>';
    }
    const activeCount = tools.filter(tool => tool.isActive).length;
    const installedCount = tools.length - activeCount;
    const cards = tools.map(tool => {
        const badge = tool.isActive ? '<span class="badge ok">active</span>' : '<span class="badge off">installed</span>';
        return `<div class="card"><strong>${escapeHtml(tool.toolName)}</strong>${badge}<br><code>${escapeHtml(tool.extensionId)}</code></div>`;
    }).join('\n        ');
    return `<p>${activeCount} active · ${installedCount} installed-only — active tools are declared on every commit proof generated from VS Code.</p>\n    <div class="grid">\n        ${cards}\n    </div>`;
}
