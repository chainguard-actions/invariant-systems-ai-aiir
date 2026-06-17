import {
    escapeHtml,
    getPanelNavHtml,
    getPanelNavStyles,
    getPanelScript,
} from './panel_shared';
import type {
    HubCapabilities,
    HubEntitlementState,
    ResolvedHubState,
} from './hub_state';

export interface JsonRecordLike {
    [key: string]: unknown;
}

export interface HubConnectionStateLike {
    configured: boolean;
    connected: boolean;
    authenticated: boolean;
    baseUrl?: string;
    tenantId?: string;
    session?: JsonRecordLike;
    onboarding?: JsonRecordLike;
    error?: string;
    resolvedState: ResolvedHubState;
}

export interface HubBillingViewModel {
    networkAllowed: boolean;
    hubEnabled: boolean;
    hubConfigured: boolean;
    hubConnected: boolean;
    hubBaseUrl?: string;
    pricingUrl: string;
    signupUrl: string;
    resolvedState: ResolvedHubState;
}

function getStateBadgeClass(state: HubEntitlementState): 'ok' | 'warn' | 'off' {
    switch (state) {
        case 'trialActive':
        case 'paidActive':
            return 'ok';
        case 'connectedNoPlan':
        case 'seatPending':
        case 'paymentActionRequired':
        case 'expired':
        case 'connectionError':
            return 'warn';
        default:
            return 'off';
    }
}

function renderCapabilitySummary(capabilities: HubCapabilities): string {
    const labels = [
        capabilities.remoteReceiptSync ? 'Remote Sync' : undefined,
        capabilities.sharedRepositories ? 'Shared Repositories' : undefined,
        capabilities.teamVisibility ? 'Team Visibility' : undefined,
        capabilities.policyManagement ? 'Policy Management' : undefined,
        capabilities.complianceExports ? 'Compliance Exports' : undefined,
        capabilities.adminControls ? 'Admin Controls' : undefined,
        capabilities.prioritySupport ? 'Priority Support' : undefined,
    ].filter((value): value is string => !!value);

    if (labels.length === 0) {
        return 'Local-only capabilities are active.';
    }

    return labels.join(' · ');
}

export function getHubStatusHtml(state: HubConnectionStateLike, networkAllowed: boolean, options?: { showAdvanced?: boolean }): string {
    const resolved = state.resolvedState;
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIIR Hub Status</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 24px; max-width: 860px; line-height: 1.7; }
        h1 { font-size: 1.5em; margin-bottom: 8px; }
        h2 { font-size: 1.08em; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--vscode-panel-border); }
        ${getPanelNavStyles()}
        .hero { padding: 18px 20px; border-radius: 14px; border: 1px solid var(--vscode-panel-border); background: linear-gradient(180deg, color-mix(in srgb, var(--vscode-editor-background) 92%, var(--vscode-charts-blue) 8%), var(--vscode-editor-background)); }
        .meta { opacity: 0.75; margin-top: 8px; }
        .hero-badges, .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 18px; }
        .card { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 10px; padding: 14px; }
        pre { white-space: pre-wrap; word-break: break-word; background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 10px; padding: 14px; margin-top: 14px; }
        code { font-family: var(--vscode-editor-font-family); }
        .badge { display: inline-block; font-size: 0.72em; font-weight: 600; border: 1.5px solid; border-radius: 99px; padding: 0.15em 0.65em; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; }
        .badge.ok { border-color: var(--vscode-testing-iconPassed); color: var(--vscode-testing-iconPassed); }
        .badge.warn { border-color: var(--vscode-editorWarning-foreground); color: var(--vscode-editorWarning-foreground); }
        .badge.off { border-color: var(--vscode-descriptionForeground); color: var(--vscode-descriptionForeground); opacity: 0.65; }
        button { font: inherit; cursor: pointer; border: none; border-radius: 6px; padding: 8px 16px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
        button:hover { background: var(--vscode-button-hoverBackground); }
        button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
        button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
    </style>
</head>
<body>
    ${getPanelNavHtml('hub', { networkAllowed, hubVisible: true, showAdvanced: options?.showAdvanced })}
    <div class="hero">
        <h1>AIIR Hub Status</h1>
        <div class="meta">Base URL: <code>${escapeHtml(state.baseUrl || '—')}</code>${state.tenantId ? ` · Tenant: <code>${escapeHtml(state.tenantId)}</code>` : ''}</div>
        <div class="hero-badges">
            <span class="badge ${getStateBadgeClass(resolved.entitlementState)}">${escapeHtml(resolved.stateLabel)}</span>
            <span class="badge ${state.configured ? 'ok' : 'off'}">${state.configured ? 'configured' : 'not configured'}</span>
            <span class="badge ${state.connected ? 'ok' : state.configured ? 'warn' : 'off'}">${state.connected ? 'reachable' : state.configured ? 'unreachable' : 'offline'}</span>
            <span class="badge ${state.authenticated ? 'ok' : 'off'}">${state.authenticated ? 'token stored' : 'anonymous'}</span>
        </div>
        <div class="meta">${escapeHtml(resolved.stateDetail)}</div>
        <div class="actions">
            <button onclick="cmd('${resolved.primaryActionCommandId}')">${escapeHtml(resolved.primaryActionLabel)}</button>
            ${resolved.secondaryActionCommandId && resolved.secondaryActionLabel ? `<button class="secondary" onclick="cmd('${resolved.secondaryActionCommandId}')">${escapeHtml(resolved.secondaryActionLabel)}</button>` : ''}
        </div>
    </div>
    <div class="grid">
        <div class="card"><strong>Entitlement</strong>${escapeHtml(resolved.stateLabel)}${resolved.offerFamily !== 'unknown' ? ` · <code>${escapeHtml(resolved.offerFamily)}</code>` : ''}</div>
        <div class="card"><strong>Configuration</strong>${state.configured ? '✅ Configured' : '⚪ Not configured'}</div>
        <div class="card"><strong>Connection</strong>${state.connected ? '✅ Hub reachable' : `❌ ${escapeHtml(state.error || 'Hub unreachable')}`}</div>
        <div class="card"><strong>Authentication</strong>${state.authenticated ? '✅ API token stored' : '⚪ Anonymous or token missing'}</div>
        <div class="card"><strong>Onboarding</strong>${state.onboarding ? '✅ Onboarding status loaded' : '⚪ No onboarding payload yet'}</div>
    </div>
    <h2>Capabilities</h2>
    <pre>${escapeHtml(renderCapabilitySummary(resolved.capabilities))}</pre>
    <h2>Session</h2>
    <pre>${escapeHtml(JSON.stringify(state.session || {}, null, 2))}</pre>
    <h2>Onboarding</h2>
    <pre>${escapeHtml(JSON.stringify(state.onboarding || {}, null, 2))}</pre>
    ${getPanelScript()}
</body>
</html>`;
}

export function getHubBillingHtml(view: HubBillingViewModel, options?: { showAdvanced?: boolean }): string {
    const resolved = view.resolvedState;
    const accessButton = view.networkAllowed
        ? `<button onclick="cmd('${resolved.primaryActionCommandId}')">${escapeHtml(resolved.primaryActionLabel)}</button>`
        : '<button class="secondary" onclick="cmd(\'aiir.advancedSettings\')">Open Advanced Settings</button>';
    const secondaryButton = resolved.secondaryActionCommandId && resolved.secondaryActionLabel
        ? `<button class="secondary" onclick="cmd('${resolved.secondaryActionCommandId}')">${escapeHtml(resolved.secondaryActionLabel)}</button>`
        : '';
    const accessNote = view.networkAllowed
        ? resolved.stateDetail
        : 'Local-only mode is enabled. Review workspace settings or open the public pricing page before enabling in-editor Hub request flows.';

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIIR Hub Plans and Access</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 24px; max-width: 860px; line-height: 1.7; }
        h1 { font-size: 1.5em; margin-bottom: 8px; }
        h2 { font-size: 1.08em; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--vscode-panel-border); }
        ${getPanelNavStyles()}
        p { opacity: 0.8; }
        .hero { padding: 18px 20px; border-radius: 14px; border: 1px solid var(--vscode-panel-border); background: linear-gradient(180deg, color-mix(in srgb, var(--vscode-editor-background) 90%, var(--vscode-charts-blue) 10%), var(--vscode-editor-background)); }
        .hero-badges, .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
        .tier-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
        .tier { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 12px; padding: 16px; }
        .tier.featured { border-color: color-mix(in srgb, var(--vscode-charts-blue) 45%, var(--vscode-panel-border)); }
        .tier h3 { font-size: 1.05em; margin-bottom: 4px; }
        .price { font-size: 1.5em; font-weight: 800; margin-bottom: 10px; color: var(--vscode-charts-blue); }
        ul { margin: 10px 0 0 18px; opacity: 0.85; }
        li + li { margin-top: 4px; }
        .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }
        .status-card { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 10px; padding: 12px; }
        .label { font-size: 0.8em; opacity: 0.55; text-transform: uppercase; letter-spacing: 0.04em; }
        .value { margin-top: 4px; font-size: 0.96em; }
        .badge { display: inline-block; font-size: 0.72em; font-weight: 600; border: 1.5px solid; border-radius: 99px; padding: 0.15em 0.65em; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; }
        .badge.ok { border-color: var(--vscode-testing-iconPassed); color: var(--vscode-testing-iconPassed); }
        .badge.warn { border-color: var(--vscode-editorWarning-foreground); color: var(--vscode-editorWarning-foreground); }
        .badge.off { border-color: var(--vscode-descriptionForeground); color: var(--vscode-descriptionForeground); opacity: 0.65; }
        button { font: inherit; cursor: pointer; border: none; border-radius: 6px; padding: 8px 16px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
        button:hover { background: var(--vscode-button-hoverBackground); }
        button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
        button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
        .note { margin-top: 12px; font-size: 0.9em; opacity: 0.72; }
        .faq { display: grid; gap: 10px; }
        .faq-card { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 10px; padding: 14px; }
        .faq-card h3 { font-size: 0.96em; margin-bottom: 4px; }
        code { font-family: var(--vscode-editor-font-family); }
    </style>
</head>
<body>
    ${getPanelNavHtml('billing', { networkAllowed: view.networkAllowed, hubVisible: view.hubEnabled, showAdvanced: options?.showAdvanced })}
    <div class="hero">
        <h1>Hub Plans and Access</h1>
        <p>AIIR is free and open source. Hub is the public governance layer for teams that need centralized policy, review workflows, and audit reporting across many repositories.</p>
        <div class="hero-badges">
            <span class="badge off">AIIR free</span>
            <span class="badge ${getStateBadgeClass(resolved.entitlementState)}">${escapeHtml(resolved.stateLabel)}</span>
            <span class="badge ${view.networkAllowed ? 'ok' : 'warn'}">${view.networkAllowed ? 'request flow available' : 'local-only mode'}</span>
            <span class="badge ${view.hubConfigured ? 'ok' : 'off'}">${view.hubConfigured ? 'Hub configured' : 'Hub not configured'}</span>
        </div>
        <div class="actions">
            <button onclick="cmd('aiir.openHubPricingPage')">Open Public Pricing</button>
            ${accessButton}
            ${secondaryButton}
            ${view.hubEnabled && view.hubConfigured ? '<button class="secondary" onclick="cmd(\'aiir.openHubDashboard\')">Open Hub Dashboard</button>' : ''}
        </div>
        <div class="note">${escapeHtml(accessNote)}</div>
    </div>

    <section>
        <h2>Plans</h2>
        <div class="tier-grid">
            <div class="tier">
                <h3>AIIR</h3>
                <div class="price">Free</div>
                <p>Local operator surfaces for generating, verifying, and inspecting AI integrity receipts inside one repository.</p>
                <ul>
                    <li>CLI, VS Code extension, GitHub Action, GitLab CI, and MCP</li>
                    <li>Content-addressed receipts and local verification</li>
                    <li>No usage limits or built-in telemetry</li>
                </ul>
            </div>
            <div class="tier featured">
                <h3>Hub</h3>
                <div class="price">Governed</div>
                <p>Managed governance for organizations already using AIIR and needing policy rollout, review workflows, and centralized reporting.</p>
                <ul>
                    <li>Cross-repo receipt review workflows</li>
                    <li>Policy rules, waivers, and exception handling</li>
                    <li>Organization-wide audit search and export</li>
                </ul>
            </div>
        </div>
    </section>

    <section>
        <h2>Current Access State</h2>
        <div class="status-grid">
            <div class="status-card"><div class="label">Local-only mode</div><div class="value">${view.networkAllowed ? 'Disabled — network actions allowed' : 'Enabled — Hub request flow blocked'}</div></div>
            <div class="status-card"><div class="label">Entitlement state</div><div class="value">${escapeHtml(resolved.stateLabel)}${resolved.offerFamily !== 'unknown' ? ` · <code>${escapeHtml(resolved.offerFamily)}</code>` : ''}</div></div>
            <div class="status-card"><div class="label">Hub configuration</div><div class="value">${view.hubConfigured ? `Configured${view.hubBaseUrl ? ` · ${escapeHtml(view.hubBaseUrl)}` : ''}` : 'Not configured'}</div></div>
            <div class="status-card"><div class="label">Connection</div><div class="value">${view.hubConnected ? 'Hub reachable' : 'No active Hub connection'}</div></div>
            <div class="status-card"><div class="label">Public pricing page</div><div class="value"><code>${escapeHtml(view.pricingUrl)}</code></div></div>
            <div class="status-card"><div class="label">Hosted signup</div><div class="value"><code>${escapeHtml(view.signupUrl)}</code></div></div>
            <div class="status-card"><div class="label">Capabilities</div><div class="value">${escapeHtml(renderCapabilitySummary(resolved.capabilities))}</div></div>
        </div>
    </section>

    <section>
        <h2>Common Questions</h2>
        <div class="faq">
            <div class="faq-card"><h3>Does the extension replace Hub?</h3><p>No. The extension remains the local operator surface for one repository. Hub is the cross-repo governance layer.</p></div>
            <div class="faq-card"><h3>Can I use AIIR without Hub?</h3><p>Yes. AIIR remains fully usable without Hub, with local receipts, verification, and repo-level automation.</p></div>
        </div>
    </section>

    ${getPanelScript()}
</body>
</html>`;
}

export function getHubSignupHtml(view: { networkAllowed: boolean; signupUrl: string; resolvedState: ResolvedHubState }, options?: { showAdvanced?: boolean }): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIIR Hub Signup</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 24px; max-width: 820px; line-height: 1.7; }
        h1 { font-size: 1.5em; margin-bottom: 8px; }
        ${getPanelNavStyles()}
        p { opacity: 0.8; }
        .hero { padding: 18px 20px; border-radius: 14px; border: 1px solid var(--vscode-panel-border); background: linear-gradient(180deg, color-mix(in srgb, var(--vscode-editor-background) 90%, var(--vscode-charts-blue) 10%), var(--vscode-editor-background)); }
        .hero-badges, .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
        button { font: inherit; cursor: pointer; border: none; border-radius: 6px; padding: 8px 16px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
        button:hover { background: var(--vscode-button-hoverBackground); }
        button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
        button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
        .badge { display: inline-block; font-size: 0.72em; font-weight: 600; border: 1.5px solid; border-radius: 99px; padding: 0.15em 0.65em; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; }
        .badge.ok { border-color: var(--vscode-testing-iconPassed); color: var(--vscode-testing-iconPassed); }
        .badge.warn { border-color: var(--vscode-editorWarning-foreground); color: var(--vscode-editorWarning-foreground); }
        .badge.off { border-color: var(--vscode-descriptionForeground); color: var(--vscode-descriptionForeground); opacity: 0.65; }
        .note { margin-top: 18px; max-width: 58ch; font-size: 0.9em; opacity: 0.72; }
        .card { margin-top: 24px; border: 1px solid var(--vscode-panel-border); border-radius: 12px; padding: 16px; background: var(--vscode-editor-background); }
        code { font-family: var(--vscode-editor-font-family); }
    </style>
</head>
<body>
    ${getPanelNavHtml('signup', { networkAllowed: view.networkAllowed, hubVisible: false, showAdvanced: options?.showAdvanced })}
    <div class="hero">
        <h1>Connect AIIR Hub</h1>
        <p>Hub signup and plan changes happen in the browser. The extension stays the client surface for local work, status refresh, and entitlement-aware actions.</p>
        <div class="hero-badges">
            <span class="badge off">AIIR free</span>
            <span class="badge ${getStateBadgeClass(view.resolvedState.entitlementState)}">${escapeHtml(view.resolvedState.stateLabel)}</span>
        </div>
        <div class="actions">
            <button onclick="cmd('aiir.openHostedHubSignup')">Open Hosted Signup</button>
            <button class="secondary" onclick="cmd('aiir.hubBilling')">Review Plans</button>
            <button class="secondary" onclick="cmd('aiir.readinessCheck')">Continue Local</button>
        </div>
        <div class="note">${escapeHtml(view.resolvedState.stateDetail)}</div>
    </div>
    <div class="card">
        <strong>Hosted flow</strong>
        <p>Use the hosted page for account creation, trial start, plan selection, checkout, and account management.</p>
        <p><code>${escapeHtml(view.signupUrl)}</code></p>
    </div>
    <div class="note">If you are not ready for Hub yet, continue locally. Repository setup, receipt generation, verification, and provenance flows remain available without an account.</div>
    ${getPanelScript()}
</body>
</html>`;
}
