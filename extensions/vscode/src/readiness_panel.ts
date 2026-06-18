import { escapeHtml, getPanelNavHtml, getPanelNavStyles, getPanelScript, renderCommandCall } from './panel_shared';

export interface ReadinessChecklistItem {
    label: string;
    detail: string;
    ready: boolean;
    live?: boolean;
}

export interface ReadinessPendingActionViewModel {
    label: string;
    canContinue: boolean;
    detail?: string;
    recoveryLabel?: string;
    recoveryCommandId?: string;
    recoveryCommandArgs?: string[];
}

export interface DetectedAIToolViewModel {
    toolName: string;
    isActive: boolean;
}

export interface ReadinessRepositoryStateInput {
    cliAvailable: boolean;
    gitAvailable: boolean;
    aiirDirExists: boolean;
    hasLedger: boolean;
    policyExists: boolean;
    hookState: 'managed' | 'custom' | 'missing';
    provenanceQueueExists: boolean;
    activeAIToolName?: string;
    activeAIToolPresent: boolean;
}

export interface ReadinessViewModelInput {
    workspaceCount: number;
    accessibleWorkspaceCount: number;
    selectedWorkspaceName?: string;
    selectedWorkspaceUri?: string;
    repositoryState?: ReadinessRepositoryStateInput;
    receiptCount: number;
    isolationBlockingAccess: boolean;
    installCommand: string;
    strictLocalOnly: boolean;
    enforceWorkspaceIsolation: boolean;
    cliVersion?: string;
    detectedAITools: DetectedAIToolViewModel[];
    sortChecklist: <T extends { key: string; ready: boolean }>(items: readonly T[]) => T[];
}

export interface ReadinessViewModel {
    state: 'ready' | 'verify-only' | 'action-needed';
    headline: string;
    detail: string;
    installCommand: string;
    workspaceCount: number;
    accessibleWorkspaceCount: number;
    selectedWorkspaceName?: string;
    selectedWorkspaceUri?: string;
    cliAvailable: boolean;
    cliVersion?: string;
    gitAvailable: boolean;
    hasReceipts: boolean;
    receiptCount: number;
    aiirInitialized: boolean;
    hasLedger: boolean;
    policyExists: boolean;
    hookState: 'managed' | 'custom' | 'missing';
    provenanceQueueExists: boolean;
    activeAIToolName?: string;
    activeAIToolPresent: boolean;
    strictLocalOnly: boolean;
    enforceWorkspaceIsolation: boolean;
    isolationBlockingAccess: boolean;
    canInitialize: boolean;
    canCreatePolicy: boolean;
    canGenerate: boolean;
    checklist: ReadinessChecklistItem[];
    detectedAITools: DetectedAIToolViewModel[];
}

export function buildReadinessViewModel(input: ReadinessViewModelInput): ReadinessViewModel {
    const repositoryState = input.repositoryState;
    const hasReceipts = input.receiptCount > 0;
    const canInitialize = !!input.selectedWorkspaceName && !!repositoryState?.cliAvailable;
    const canCreatePolicy = !!input.selectedWorkspaceName && !!repositoryState?.cliAvailable && !!repositoryState?.aiirDirExists;
    const canGenerate = !!input.selectedWorkspaceName && !!repositoryState?.cliAvailable && !!repositoryState?.aiirDirExists;

    let state: ReadinessViewModel['state'] = 'action-needed';
    let headline = 'This repository is not ready to cover the current commit yet.';
    let detail = 'Open a repository and let AIIR check what is still needed before the current commit can be recorded.';

    if (input.isolationBlockingAccess) {
        headline = 'Workspace policy is hiding this repository from AIIR.';
        detail = 'Workspace isolation is blocking access in this multi-root workspace. Open Security Posture to allow this repository or turn isolation off.';
    } else if (input.workspaceCount === 0) {
        headline = 'Open a repository to check commit status.';
        detail = 'The extension is installed, but there is no workspace folder open yet.';
    } else if (!repositoryState?.gitAvailable) {
        headline = 'Open a git repository to check commit status.';
        detail = 'A workspace folder is open, but AIIR has not found a usable git repository in the current target yet.';
    } else if (hasReceipts && !repositoryState?.cliAvailable) {
        state = 'verify-only';
        headline = 'This workspace is ready to verify existing receipts.';
        detail = 'Install the AIIR CLI when you want to initialize repositories, record new commit activity, or enable managed auto-receipting.';
    } else if (hasReceipts && repositoryState?.cliAvailable) {
        state = 'ready';
        headline = 'This repository can verify receipts and record the next commit.';
        detail = repositoryState.aiirDirExists
            ? 'Receipts are present and the AIIR CLI is available, so the normal local workflow is ready.'
            : 'Receipts are present and the AIIR CLI is available. Initialize AIIR here if you want local setup files and automation.';
    } else if (repositoryState?.cliAvailable && !repositoryState.aiirDirExists) {
        headline = 'This commit needs repository setup before it can be recorded.';
        detail = 'The CLI is available. Initialize AIIR once so this repository can record current and future commits from inside VS Code.';
    } else if (repositoryState?.cliAvailable && repositoryState.aiirDirExists) {
        state = 'ready';
        headline = 'This commit is ready to record.';
        detail = repositoryState.policyExists
            ? 'This repository is initialized and ready. Record the current commit now.'
            : 'This repository is initialized and can record the current commit now. Add the repo policy file later if you want repo-local access defaults.';
    }

    const checklist = input.sortChecklist([
        {
            key: 'git',
            label: 'Repository open',
            detail: repositoryState?.gitAvailable ? 'Git repository detected in the current target' : 'No usable git repository detected in the current target',
            ready: !!repositoryState?.gitAvailable,
        },
        {
            key: 'cli',
            label: 'CLI installed',
            detail: repositoryState?.cliAvailable ? 'AIIR CLI is ready for local recording and verification' : 'Install the CLI to initialize this repository and record commits',
            ready: !!repositoryState?.cliAvailable,
        },
        {
            key: 'aiir',
            label: 'Repository prepared',
            detail: repositoryState?.aiirDirExists ? 'Local AIIR setup files are present' : 'Initialize the repository to create local AIIR setup files',
            ready: !!repositoryState?.aiirDirExists,
        },
        {
            key: 'ledger',
            label: 'Commit activity recorded',
            detail: hasReceipts ? `${input.receiptCount} receipt${input.receiptCount === 1 ? '' : 's'} found for this workspace` : 'No recorded commit activity yet',
            ready: hasReceipts,
        },
        {
            key: 'live-activity',
            label: 'AI tool active now',
            detail: repositoryState?.activeAIToolPresent ? `Active tool: ${repositoryState.activeAIToolName}` : 'No active AI tool detected right now',
            ready: !!repositoryState?.activeAIToolPresent,
            live: true,
        },
    ]).map(({ key, ...item }) => item);

    return {
        state,
        headline,
        detail,
        installCommand: input.installCommand,
        workspaceCount: input.workspaceCount,
        accessibleWorkspaceCount: input.accessibleWorkspaceCount,
        selectedWorkspaceName: input.selectedWorkspaceName,
        selectedWorkspaceUri: input.selectedWorkspaceUri,
        cliAvailable: !!repositoryState?.cliAvailable,
        cliVersion: input.cliVersion,
        gitAvailable: !!repositoryState?.gitAvailable,
        hasReceipts,
        receiptCount: input.receiptCount,
        aiirInitialized: !!repositoryState?.aiirDirExists,
        hasLedger: !!repositoryState?.hasLedger,
        policyExists: !!repositoryState?.policyExists,
        hookState: repositoryState?.hookState || 'missing',
        provenanceQueueExists: !!repositoryState?.provenanceQueueExists,
        activeAIToolName: repositoryState?.activeAIToolName,
        activeAIToolPresent: !!repositoryState?.activeAIToolPresent,
        strictLocalOnly: input.strictLocalOnly,
        enforceWorkspaceIsolation: input.enforceWorkspaceIsolation,
        isolationBlockingAccess: input.isolationBlockingAccess,
        canInitialize,
        canCreatePolicy,
        canGenerate,
        checklist,
        detectedAITools: input.detectedAITools,
    };
}

export function getReadinessHtml(
    view: ReadinessViewModel,
    pendingAction?: ReadinessPendingActionViewModel,
    options?: { showAdvanced?: boolean },
): string {
    const targetArgs = view.selectedWorkspaceUri ? [view.selectedWorkspaceUri] : [];
    const stateBadge = view.state === 'ready'
        ? '<span class="badge ok">ready</span>'
        : view.state === 'verify-only'
            ? '<span class="badge warn">verify-only</span>'
            : '<span class="badge err">action needed</span>';
    const cliState = view.cliAvailable
        ? `<span class="badge ok">${escapeHtml(view.cliVersion || 'available')}</span>`
        : '<span class="badge err">missing</span>';
    const workspaceState = view.selectedWorkspaceName
        ? `${escapeHtml(view.selectedWorkspaceName)} · ${view.accessibleWorkspaceCount}/${view.workspaceCount} accessible`
        : `${view.accessibleWorkspaceCount}/${view.workspaceCount} accessible workspace folders`;
    const heroActionCommand = !view.cliAvailable
        ? "cmd('aiir.installCliNow')"
        : !view.aiirInitialized
            ? renderCommandCall('aiir.initializeRepo', targetArgs)
            : view.canGenerate
                ? renderCommandCall('aiir.generatePreferred', targetArgs)
                : "cmd('aiir.verifyAll')";
    const heroActionLabel = !view.cliAvailable
        ? 'Install CLI'
        : !view.aiirInitialized
            ? 'Initialize Repository'
            : view.canGenerate
                ? 'Record Commit Activity'
                : 'Verify All Receipts';
    const setupState = view.aiirInitialized
        ? '<span class="badge ok">ready</span>'
        : '<span class="badge off">needs setup</span>';
    const coverageState = view.hasReceipts
        ? `<span class="badge ok">${view.receiptCount} receipt${view.receiptCount === 1 ? '' : 's'}</span>`
        : '<span class="badge off">none yet</span>';
    const pendingPrimaryCommand = pendingAction?.canContinue
        ? "cmd('aiir.continuePendingAction')"
        : pendingAction?.recoveryCommandId
            ? renderCommandCall(pendingAction.recoveryCommandId, pendingAction.recoveryCommandArgs || [])
            : undefined;
    const pendingPrimaryLabel = pendingAction?.canContinue
        ? `Continue ${pendingAction.label}`
        : pendingAction?.recoveryLabel || 'Refresh Readiness';
    const pendingDetail = pendingAction?.detail
        || (pendingAction
            ? `AIIR remembered that you were trying to ${pendingAction.label}.`
            : '');
    const installRecoveryActive = !pendingAction?.canContinue && pendingAction?.recoveryCommandId === 'aiir.installCliNow';
    const unlockRecordingDetail = view.cliAvailable
        ? 'The AIIR CLI is already available. Use the manual install path only if you need to repair or relocate the local setup.'
        : installRecoveryActive
            ? 'Use the pending action above to install the CLI and continue the flow you already started.'
            : 'Install AIIR into a dedicated user-local environment when you want initialization, receipt generation, or managed hooks.';

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIIR Commit Status</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 24px; max-width: 860px; line-height: 1.7; }
        h1 { font-size: 1.5em; margin-bottom: 8px; }
        h2 { font-size: 1.08em; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--vscode-panel-border); }
        ${getPanelNavStyles()}
        p { opacity: 0.8; }
        code, pre { font-family: var(--vscode-editor-font-family); }
        .hero { padding: 18px 20px; border-radius: 14px; border: 1px solid var(--vscode-panel-border); background: linear-gradient(180deg, color-mix(in srgb, var(--vscode-editor-background) 92%, var(--vscode-charts-blue) 8%), var(--vscode-editor-background)); }
        .hero-badges, .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
        .status-grid, .next-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
        .card { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 12px; padding: 14px; }
        .label { font-size: 0.8em; opacity: 0.55; text-transform: uppercase; letter-spacing: 0.04em; }
        .value { margin-top: 4px; font-size: 0.96em; word-break: break-word; }
        .badge { display: inline-block; font-size: 0.72em; font-weight: 600; border: 1.5px solid; border-radius: 99px; padding: 0.15em 0.65em; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; }
        .badge.ok { border-color: var(--vscode-testing-iconPassed); color: var(--vscode-testing-iconPassed); }
        .badge.warn { border-color: var(--vscode-editorWarning-foreground); color: var(--vscode-editorWarning-foreground); }
        .badge.err { border-color: var(--vscode-testing-iconFailed); color: var(--vscode-testing-iconFailed); }
        .badge.off { border-color: var(--vscode-descriptionForeground); color: var(--vscode-descriptionForeground); opacity: 0.65; }
        button { font: inherit; cursor: pointer; border: none; border-radius: 6px; padding: 8px 16px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
        button:hover { background: var(--vscode-button-hoverBackground); }
        button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
        button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
        button:disabled { opacity: 0.45; cursor: not-allowed; }
        pre { margin-top: 12px; white-space: pre-wrap; word-break: break-word; background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 10px; padding: 14px; }
        .hint { margin-top: 12px; font-size: 0.9em; opacity: 0.72; }
    </style>
</head>
<body>
    ${getPanelNavHtml('readiness', { networkAllowed: !view.strictLocalOnly, commandTarget: view.selectedWorkspaceUri, showAdvanced: options?.showAdvanced })}
    <div class="hero">
        <h1>Check Commit Status</h1>
        ${view.selectedWorkspaceName ? `<div class="hint">Repository: <strong>${escapeHtml(view.selectedWorkspaceName)}</strong></div>` : ''}
        <p>${escapeHtml(view.headline)}</p>
        <div class="hint">${escapeHtml(view.detail)}</div>
        <div class="hero-badges">
            ${stateBadge}
            <span class="badge ${view.strictLocalOnly ? 'ok' : 'warn'}">${view.strictLocalOnly ? 'local-only' : 'network allowed'}</span>
            <span class="badge ${view.enforceWorkspaceIsolation ? 'ok' : 'warn'}">${view.enforceWorkspaceIsolation ? 'isolation enforced' : 'discovery relaxed'}</span>
            <span class="badge ${view.hasReceipts ? 'ok' : 'off'}">${view.hasReceipts ? `${view.receiptCount} receipts found` : 'no receipts yet'}</span>
        </div>
        <div class="actions">
            <button onclick="${heroActionCommand}">${heroActionLabel}</button>
            <button onclick="cmd('aiir.openWalkthrough')">Open Getting Started</button>
            ${view.hasReceipts ? `<button class="secondary" onclick="cmd('aiir.verifyAll')">Verify All Receipts</button>` : ''}
            <button onclick="cmd('aiir.refresh')">Re-check Workspace</button>
        </div>
    </div>

    ${pendingAction ? `
    <section>
        <h2>Continue What You Started</h2>
        <div class="card">
            <div class="label">Pending action</div>
            <div class="value">${escapeHtml(pendingDetail)}</div>
            <div class="actions">
                <button ${pendingPrimaryCommand ? '' : 'disabled'}${pendingPrimaryCommand ? ` onclick="${pendingPrimaryCommand}"` : ''}>${escapeHtml(pendingPrimaryLabel)}</button>
                ${!pendingAction.canContinue && pendingAction.recoveryCommandId === 'aiir.installCliNow'
                ? `<button class="secondary" onclick="cmd('aiir.copyCliInstallCommand')">Copy Install Command</button>
                <button class="secondary" onclick="cmd('aiir.openCliInstallTerminal')">Open Terminal</button>`
                : ''}
                <button class="secondary" onclick="cmd('aiir.refresh')">Refresh Readiness</button>
            </div>
        </div>
    </section>` : ''}

    <section>
        <h2>Commit Status Checklist</h2>
        <div class="status-grid">
            ${view.checklist.map(item => `
            <div class="card">
                <div class="label">${escapeHtml(item.label)}</div>
                <div class="value">${item.ready
                        ? '<span class="badge ok">ready</span>'
                        : item.live
                            ? '<span class="badge off">inactive</span>'
                            : '<span class="badge warn">missing</span>'}</div>
                <div class="hint">${escapeHtml(item.detail)}</div>
            </div>`).join('')}
        </div>
    </section>

    <section>
        <h2>Current State</h2>
        <div class="status-grid">
            <div class="card"><div class="label">Workspace</div><div class="value">${workspaceState}</div></div>
            <div class="card"><div class="label">CLI</div><div class="value">${cliState}</div></div>
            <div class="card"><div class="label">Repository</div><div class="value">${view.gitAvailable ? '<span class="badge ok">available</span>' : '<span class="badge err">not found</span>'}</div></div>
            <div class="card"><div class="label">Setup</div><div class="value">${setupState}</div></div>
            <div class="card"><div class="label">Coverage</div><div class="value">${coverageState}</div></div>
            <div class="card"><div class="label">AI tools</div><div class="value">${view.detectedAITools.length > 0
            ? view.detectedAITools.map(tool => `<span class="badge ${tool.isActive ? 'ok' : 'off'}">${escapeHtml(tool.toolName)}</span>`).join(' ')
            : '<span class="badge off">none detected</span>'}</div></div>
        </div>
    </section>

    <section>
        <h2>Recommended Next Actions</h2>
        <div class="next-grid">
            <div class="card">
                <div class="label">Unlock recording</div>
                <div class="value">${escapeHtml(unlockRecordingDetail)}</div>
                ${view.cliAvailable ? '' : `<pre>${escapeHtml(view.installCommand)}</pre>`}
                <div class="actions">
                    ${view.cliAvailable
            ? `<button class="secondary" onclick="cmd('aiir.refresh')">Re-check Workspace</button>`
            : installRecoveryActive
                ? `<button class="secondary" onclick="cmd('aiir.refresh')">Retry Readiness</button>`
                : `<button class="secondary" onclick="cmd('aiir.copyCliInstallCommand')">Copy Install Command</button>
                    <button class="secondary" onclick="cmd('aiir.openCliInstallTerminal')">Open Terminal</button>
                    <button class="secondary" onclick="cmd('aiir.refresh')">Retry Readiness</button>`}
                </div>
            </div>
            <div class="card">
                <div class="label">Prepare this repository</div>
                <div class="value">${view.canInitialize ? 'Create the local AIIR setup files once so this repository can record commit activity from inside VS Code.' : 'Install the CLI or open an accessible repository before initialization is available.'}</div>
                <div class="actions"><button ${view.canInitialize ? '' : 'disabled'} onclick="${renderCommandCall('aiir.initializeRepo', view.selectedWorkspaceUri ? [view.selectedWorkspaceUri] : [])}">Initialize Repository</button></div>
            </div>
            <div class="card">
                <div class="label">Record this commit</div>
                <div class="value">${view.canGenerate ? 'Create a record for the current commit. AIIR prefers deterministic provenance when an active file supports it, then falls back automatically.' : 'This unlocks after the CLI is installed and the repository is initialized.'}</div>
                <div class="actions">
                    <button ${view.canGenerate ? '' : 'disabled'} onclick="${renderCommandCall('aiir.generatePreferred', view.selectedWorkspaceUri ? [view.selectedWorkspaceUri] : [])}">Record Commit Activity</button>
                    <button class="secondary" onclick="cmd('aiir.verifyAll')">Verify All Receipts</button>
                </div>
            </div>
            <div class="card">
                <div class="label">Keep it automatic</div>
                <div class="value">${view.canGenerate ? 'Enable managed auto-receipting later if you want new commits recorded with less manual work.' : 'Auto-receipting becomes available after the CLI is installed and the repository is initialized.'}</div>
                <div class="actions"><button ${view.canGenerate ? '' : 'disabled'} onclick="${renderCommandCall('aiir.enableAutoReceipting', targetArgs)}">Enable Auto-Receipting</button></div>
            </div>
        </div>
    </section>

    <section>
        <h2>What Works Right Now</h2>
        <div class="status-grid">
            <div class="card"><div class="label">Verification</div><div class="value">${view.hasReceipts ? 'Existing receipts can be inspected and verified in place.' : 'Open a repository with existing receipts to verify immediately.'}</div></div>
            <div class="card"><div class="label">Workspace posture</div><div class="value">${view.isolationBlockingAccess ? 'Workspace isolation is currently blocking automatic discovery in this multi-root workspace.' : 'Workspace access matches the current local-only and isolation settings.'}</div></div>
            <div class="card"><div class="label">Next lowest-friction path</div><div class="value">${view.hasReceipts ? 'Verify a receipt, then record the next commit when new work lands.' : !view.aiirInitialized ? 'Install the CLI if needed, initialize the repository once, then record the current commit.' : 'Record commit activity for HEAD now.'}</div></div>
        </div>
    </section>

    ${options?.showAdvanced ? `
    <section>
        <h2>Advanced Setup Details</h2>
        <div class="status-grid">
            <div class="card"><div class="label">Policy file</div><div class="value">${view.policyExists ? '<span class="badge ok">present</span>' : '<span class="badge off">not created</span>'}</div></div>
            <div class="card"><div class="label">Hook</div><div class="value">${view.hookState === 'managed' ? '<span class="badge ok">managed</span>' : view.hookState === 'custom' ? '<span class="badge warn">custom</span>' : '<span class="badge off">missing</span>'}</div></div>
            <div class="card"><div class="label">Provenance queue</div><div class="value">${view.provenanceQueueExists ? '<span class="badge ok">configured</span>' : '<span class="badge off">not configured</span>'}</div></div>
            <div class="card"><div class="label">Ledger</div><div class="value">${view.hasLedger ? '<span class="badge ok">present</span>' : '<span class="badge off">missing</span>'}</div></div>
        </div>
        <div class="actions">
            <button class="secondary" onclick="cmd('workbench.action.openWorkspaceSettingsFile')">Open Workspace Settings JSON</button>
            <button ${view.policyExists || view.canCreatePolicy ? '' : 'disabled'} onclick="${renderCommandCall(view.policyExists ? 'aiir.openPolicyFile' : 'aiir.createWorkspacePolicy', targetArgs)}">${view.policyExists ? 'Open Policy File' : 'Create Policy File'}</button>
            <button class="secondary" ${view.policyExists || view.canCreatePolicy ? '' : 'disabled'} onclick="${renderCommandCall('aiir.editPolicyTargets', targetArgs)}">Edit Workspace Targets</button>
            <button class="secondary" ${view.aiirInitialized ? '' : 'disabled'} onclick="${renderCommandCall(view.provenanceQueueExists ? 'aiir.generateWithProvenance' : 'aiir.configureProvenanceQueue', targetArgs)}">${view.provenanceQueueExists ? 'Generate With Provenance' : 'Configure Provenance'}</button>
        </div>
    </section>` : ''}

    ${getPanelScript()}
</body>
</html>`;
}
