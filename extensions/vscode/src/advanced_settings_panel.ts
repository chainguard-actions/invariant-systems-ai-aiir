import { escapeHtml, getPanelNavHtml, getPanelNavStyles, getPanelScript, renderCommandCall } from './panel_shared';

export interface PolicyWorkspaceTargetStateViewModel {
    name: string;
    path: string;
    enabled: boolean;
    matchesOpenWorkspace: boolean;
}

export interface AdvancedSettingsViewModelInput {
    selectedWorkspaceName?: string;
    selectedWorkspaceUri?: string;
    cliPath: string;
    agentModelHint: string;
    autoReceiptArgs: string[];
    enforceWorkspaceIsolation: boolean;
    allowedWorkspaceFolders: string[];
    strictLocalOnly: boolean;
    enableHubFeatures: boolean;
    hubEnabled: boolean;
    hubBaseUrl: string;
    hubTenantId: string;
    hubSignupEndpoint: string;
    policyExists: boolean;
    policyPath: string;
    policyTargetSummary: string;
    policyTargets: PolicyWorkspaceTargetStateViewModel[];
    currentPolicyTargetLabel: string;
}

export interface AdvancedSettingsViewModel extends AdvancedSettingsViewModelInput { }

export function buildAdvancedSettingsViewModel(input: AdvancedSettingsViewModelInput): AdvancedSettingsViewModel {
    return { ...input };
}

export function getAdvancedSettingsHtml(view: AdvancedSettingsViewModel, options?: { showAdvanced?: boolean }): string {
    const allowedFolders = view.allowedWorkspaceFolders.length > 0
        ? view.allowedWorkspaceFolders.map(folder => `<li><code>${escapeHtml(folder)}</code></li>`).join('')
        : '<li>No allowlisted folders. In multi-root workspaces, discovery stays blocked until you add one.</li>';
    const policyLabel = view.policyExists ? '<span class="badge ok">present</span>' : '<span class="badge off">not created</span>';
    const policyPathValue = view.policyPath ? `<code>${escapeHtml(view.policyPath)}</code>` : 'Open a repository to select a policy file.';
    const policyActionCommand = view.policyExists ? 'aiir.openPolicyFile' : 'aiir.createWorkspacePolicy';
    const policyActionLabel = view.policyExists ? 'Open Policy File' : 'Create Policy File';
    const workspaceTargets = view.policyTargets.length > 0
        ? view.policyTargets.map(target => `<li><span class="badge ${target.enabled ? 'ok' : 'warn'}">${target.enabled ? 'enabled' : 'disabled'}</span> ${escapeHtml(target.name || target.path)}${target.matchesOpenWorkspace ? ' <span class="badge off">open</span>' : ''}<div class="hint-inline"><code>${escapeHtml(target.path || target.name)}</code></div></li>`).join('')
        : '<li>No workspace targets recorded yet.</li>';

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIIR Advanced Settings</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 24px; max-width: 860px; line-height: 1.7; }
        h1 { font-size: 1.5em; margin-bottom: 8px; }
        h2 { font-size: 1.08em; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--vscode-panel-border); }
        ${getPanelNavStyles()}
        p { opacity: 0.8; }
        code { font-family: var(--vscode-editor-font-family); }
        .hero { padding: 18px 20px; border-radius: 14px; border: 1px solid var(--vscode-panel-border); background: linear-gradient(180deg, color-mix(in srgb, var(--vscode-editor-background) 93%, var(--vscode-editorWarning-foreground) 7%), var(--vscode-editor-background)); }
        .hero-badges { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
        .state-grid, .setting-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
        .state-card, .setting-card { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 12px; padding: 14px; }
        .label { font-size: 0.8em; opacity: 0.55; text-transform: uppercase; letter-spacing: 0.04em; }
        .value { margin-top: 4px; font-size: 0.96em; word-break: break-word; }
        .badge { display: inline-block; font-size: 0.72em; font-weight: 600; border: 1.5px solid; border-radius: 99px; padding: 0.15em 0.65em; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; }
        .badge.ok { border-color: var(--vscode-testing-iconPassed); color: var(--vscode-testing-iconPassed); }
        .badge.warn { border-color: var(--vscode-editorWarning-foreground); color: var(--vscode-editorWarning-foreground); }
        .badge.off { border-color: var(--vscode-descriptionForeground); color: var(--vscode-descriptionForeground); opacity: 0.65; }
        ul { margin: 10px 0 0 18px; opacity: 0.86; }
        .hint-inline { margin-top: 4px; opacity: 0.68; }
        .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
        button { font: inherit; cursor: pointer; border: none; border-radius: 6px; padding: 8px 16px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
        button:hover { background: var(--vscode-button-hoverBackground); }
        button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
        button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
        pre { margin-top: 12px; white-space: pre-wrap; word-break: break-word; background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 10px; padding: 14px; }
    </style>
</head>
<body>
    ${getPanelNavHtml('settings', { networkAllowed: !view.strictLocalOnly, hubVisible: view.hubEnabled, commandTarget: view.selectedWorkspaceUri, showAdvanced: options?.showAdvanced })}
    <div class="hero">
        <h1>Advanced Settings</h1>
        <p>These settings control how AIIR behaves in this workspace. The default single-repository posture is workspace-scoped and local-only. Add explicit allowlisting when you need tighter control in multi-root workspaces.</p>
        <div class="hero-badges">
            <span class="badge ${view.strictLocalOnly ? 'ok' : 'warn'}">${view.strictLocalOnly ? 'local-only enabled' : 'network access allowed'}</span>
            <span class="badge ${view.enforceWorkspaceIsolation ? 'ok' : 'warn'}">${view.enforceWorkspaceIsolation ? 'isolation enforced' : 'discovery relaxed'}</span>
            <span class="badge ${view.allowedWorkspaceFolders.length > 0 ? 'ok' : 'off'}">${view.allowedWorkspaceFolders.length > 0 ? `${view.allowedWorkspaceFolders.length} allowlisted` : 'no allowlist yet'}</span>
        </div>
        <div class="actions">
            <button onclick="${renderCommandCall('workbench.action.openSettings', ['aiir'])}">Open AIIR Settings</button>
            <button class="secondary" onclick="cmd('workbench.action.openWorkspaceSettingsFile')">Open Workspace Settings JSON</button>
            <button class="secondary" onclick="${renderCommandCall(policyActionCommand, view.selectedWorkspaceUri ? [view.selectedWorkspaceUri] : [])}">${policyActionLabel}</button>
            <button class="secondary" onclick="${renderCommandCall('aiir.editPolicyTargets', view.selectedWorkspaceUri ? [view.selectedWorkspaceUri] : [])}">Edit Workspace Targets</button>
        </div>
    </div>

    <section>
        <h2>Current Configuration</h2>
        <div class="state-grid">
            <div class="state-card"><div class="label">Local-only mode</div><div class="value"><span class="badge ${view.strictLocalOnly ? 'ok' : 'warn'}">${view.strictLocalOnly ? 'enabled' : 'disabled'}</span></div></div>
            <div class="state-card"><div class="label">Workspace isolation</div><div class="value"><span class="badge ${view.enforceWorkspaceIsolation ? 'ok' : 'warn'}">${view.enforceWorkspaceIsolation ? 'enforced' : 'relaxed'}</span></div></div>
            <div class="state-card"><div class="label">Allowlisted folders</div><div class="value">${view.allowedWorkspaceFolders.length}</div></div>
            <div class="state-card"><div class="label">Selected workspace</div><div class="value">${escapeHtml(view.selectedWorkspaceName || 'None')}</div></div>
            <div class="state-card"><div class="label">Policy file</div><div class="value">${policyLabel}</div></div>
            <div class="state-card"><div class="label">Workspace targets</div><div class="value">${escapeHtml(view.policyTargetSummary)}</div></div>
            <div class="state-card"><div class="label">Current repo target</div><div class="value">${escapeHtml(view.currentPolicyTargetLabel)}</div></div>
            <div class="state-card"><div class="label">Hub features</div><div class="value"><span class="badge ${view.hubEnabled ? 'ok' : view.enableHubFeatures ? 'warn' : 'off'}">${view.hubEnabled ? 'enabled' : view.enableHubFeatures ? 'configured but blocked by local-only mode' : 'disabled'}</span></div></div>
        </div>
    </section>

    <section>
        <h2>Workspace Defaults</h2>
        <div class="setting-grid">
            <div class="setting-card">
                <div class="label">Policy path</div>
                <div class="value">${policyPathValue}</div>
                <div class="actions">
                    <button class="secondary" onclick="cmd('workbench.action.openWorkspaceSettingsFile')">Open Workspace Settings JSON</button>
                    <button onclick="${renderCommandCall(policyActionCommand, view.selectedWorkspaceUri ? [view.selectedWorkspaceUri] : [])}">${policyActionLabel}</button>
                    <button class="secondary" onclick="${renderCommandCall('aiir.editPolicyTargets', view.selectedWorkspaceUri ? [view.selectedWorkspaceUri] : [])}">Edit Workspace Targets</button>
                    <button class="secondary" onclick="${renderCommandCall('aiir.initializeRepo', view.selectedWorkspaceUri ? [view.selectedWorkspaceUri] : [])}">Apply Recommended Defaults</button>
                </div>
            </div>
            <div class="setting-card">
                <div class="label">Baseline behavior</div>
                <div class="value">The default single-repository posture is local-only with normal discovery. When you need tighter control in multi-root workspaces, enable workspace isolation and add an explicit allowlist. AIIR also writes <code>.aiir/policy.json</code> so the repository keeps its local policy defaults in the expected layout.</div>
            </div>
            <div class="setting-card">
                <div class="label">Workspace targets</div>
                <div class="value">Enabled and disabled repositories currently recorded in the repo-local AIIR policy file.</div>
                <ul>${workspaceTargets}</ul>
            </div>
        </div>
    </section>

    <section>
        <h2>Isolation and Access</h2>
        <div class="setting-grid">
            <div class="setting-card">
                <div class="label">aiir.allowedWorkspaceFolders</div>
                <div class="value">Explicit allowlist for multi-root discovery and repo-scoped actions.</div>
                <ul>${allowedFolders}</ul>
                <div class="actions"><button onclick="${renderCommandCall('workbench.action.openSettings', ['aiir.allowedWorkspaceFolders'])}">Edit Setting</button></div>
            </div>
            <div class="setting-card">
                <div class="label">aiir.enforceWorkspaceIsolation</div>
                <div class="value">${view.enforceWorkspaceIsolation ? 'Automatic multi-root discovery is constrained to the allowlist.' : 'All open folders may be discovered.'}</div>
                <div class="actions"><button onclick="${renderCommandCall('workbench.action.openSettings', ['aiir.enforceWorkspaceIsolation'])}">Edit Setting</button></div>
            </div>
            <div class="setting-card">
                <div class="label">aiir.strictLocalOnly</div>
                <div class="value">${view.strictLocalOnly ? 'Hub and request flows are disabled until you opt in.' : 'Network-backed Hub commands may be used.'}</div>
                <div class="actions"><button onclick="${renderCommandCall('workbench.action.openSettings', ['aiir.strictLocalOnly'])}">Edit Setting</button></div>
            </div>
        </div>
    </section>

    <section>
        <h2>Operator Settings</h2>
        <div class="setting-grid">
            <div class="setting-card"><div class="label">CLI path</div><div class="value"><code>${escapeHtml(view.cliPath)}</code></div><div class="actions"><button onclick="${renderCommandCall('workbench.action.openSettings', ['aiir.cliPath'])}">Edit Setting</button></div></div>
            <div class="setting-card"><div class="label">Auto-receipt args</div><div class="value"><code>${escapeHtml(JSON.stringify(view.autoReceiptArgs))}</code></div><div class="actions"><button onclick="${renderCommandCall('workbench.action.openSettings', ['aiir.autoReceiptArgs'])}">Edit Setting</button></div></div>
            <div class="setting-card"><div class="label">Agent model hint</div><div class="value"><code>${escapeHtml(view.agentModelHint || '—')}</code></div><div class="actions"><button onclick="${renderCommandCall('workbench.action.openSettings', ['aiir.agentModelHint'])}">Edit Setting</button></div></div>
            <div class="setting-card"><div class="label">Hub base URL</div><div class="value"><code>${escapeHtml(view.hubBaseUrl || '—')}</code></div><div class="actions"><button onclick="${renderCommandCall('workbench.action.openSettings', ['aiir.hubBaseUrl'])}">Edit Setting</button></div></div>
            <div class="setting-card"><div class="label">Hub tenant ID</div><div class="value"><code>${escapeHtml(view.hubTenantId || '—')}</code></div><div class="actions"><button onclick="${renderCommandCall('workbench.action.openSettings', ['aiir.hubTenantId'])}">Edit Setting</button></div></div>
            <div class="setting-card"><div class="label">Hub signup endpoint</div><div class="value"><code>${escapeHtml(view.hubSignupEndpoint || '—')}</code></div><div class="actions"><button onclick="${renderCommandCall('workbench.action.openSettings', ['aiir.hubSignupEndpoint'])}">Edit Setting</button></div></div>
            <div class="setting-card"><div class="label">Hub feature flag</div><div class="value">${view.enableHubFeatures ? 'Requested in workspace settings' : 'Disabled in workspace settings'}</div><div class="actions"><button onclick="${renderCommandCall('workbench.action.openSettings', ['aiir.enableHubFeatures'])}">Edit Setting</button></div></div>
        </div>
        <pre>${escapeHtml(JSON.stringify({
        'aiir.enforceWorkspaceIsolation': view.enforceWorkspaceIsolation,
        'aiir.allowedWorkspaceFolders': view.allowedWorkspaceFolders,
        'aiir.strictLocalOnly': view.strictLocalOnly,
        'aiir.cliPath': view.cliPath,
        'aiir.agentModelHint': view.agentModelHint,
        'aiir.autoReceiptArgs': view.autoReceiptArgs,
        'aiir.enableHubFeatures': view.enableHubFeatures,
        'aiir.hubBaseUrl': view.hubBaseUrl,
        'aiir.hubTenantId': view.hubTenantId,
        'aiir.hubSignupEndpoint': view.hubSignupEndpoint,
    }, null, 2))}</pre>
    </section>

    ${getPanelScript()}
</body>
</html>`;
}
