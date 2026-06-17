export type HomeState = 'no-workspace' | 'access-blocked' | 'cli-missing' | 'not-initialized' | 'ready-no-receipts' | 'head-missing' | 'regulated-incomplete' | 'healthy' | 'failing';
export type TrustVertex = 'open' | 'install' | 'initialize' | 'generate' | 'covered' | 'regulated' | 'attention';
export type TrustHookKind = 'managed' | 'custom' | 'missing';

export type HomeStatusLevel = 'good' | 'warn' | 'info';

export interface TrustLatestReceipt {
    label: string;
    author: string;
    timestamp: string;
    uri: string;
}

export interface TrustStateInput {
    workspaceOpen: boolean;
    accessBlocked: boolean;
    repoName?: string;
    branch?: string;
    folderCount: number;
    receiptCount: number;
    invalidReceiptCount: number;
    cliAvailable: boolean;
    repoInitialized: boolean;
    headReceiptStatus: 'present' | 'missing' | 'unknown';
    latestReceipt?: TrustLatestReceipt;
    activeAITool?: string;
    hookKind?: TrustHookKind;
    headSha?: string;
    regulatedMode?: boolean;
    policyEnabled?: boolean;
    reviewAttestationPresent?: boolean;
    currentEvidenceTier?: string;
    sigstoreReceiptCount?: number;
    activeExceptionCount?: number;
}

export interface HomeStateInput {
    workspaceOpen: boolean;
    accessBlocked: boolean;
    cliAvailable: boolean;
    repoInitialized: boolean;
    policyEnabled?: boolean;
    receiptsExist: boolean;
    allReceiptsValid: boolean;
    headCovered: boolean;
    regulatedMode?: boolean;
    meetsEvidenceBar?: boolean;
}

export interface HomeActionDefinition {
    label: string;
    description: string;
    commandId: string;
    iconId: string;
}

export interface HomePrimaryCardDefinition {
    headline: string;
    detail: string;
    primaryAction: {
        label: string;
        commandId: string;
    };
    secondaryAction?: {
        label: string;
        commandId: string;
    };
}

export interface ResolvedTrustState {
    homeState: HomeState;
    vertex: TrustVertex;
    level: HomeStatusLevel;
    title: string;
    nextAction: HomeActionDefinition;
    primaryCard: HomePrimaryCardDefinition;
    repoName?: string;
    branch?: string;
    folderCount: number;
    receiptCount: number;
    invalidReceiptCount: number;
    hasReceipts: boolean;
    headCovered: boolean;
    headReceiptStatus: 'present' | 'missing' | 'unknown';
    latestReceipt?: TrustLatestReceipt;
    primaryAction: {
        label: string;
        commandId: string;
        args?: unknown[];
    };
    cliAvailable: boolean;
    repoInitialized: boolean;
    activeAITool?: string;
    hookKind?: TrustHookKind;
    headSha?: string;
    accessBlocked: boolean;
    workspaceOpen: boolean;
}

export function resolveHomeState(input: HomeStateInput): HomeState {
    if (!input.workspaceOpen) {
        return 'no-workspace';
    }
    if (input.accessBlocked) {
        return 'access-blocked';
    }
    if (input.receiptsExist && !input.allReceiptsValid) {
        return 'failing';
    }
    if (input.receiptsExist && !input.headCovered && input.cliAvailable && input.repoInitialized) {
        return 'head-missing';
    }
    if (input.receiptsExist && input.regulatedMode && !input.meetsEvidenceBar) {
        return 'regulated-incomplete';
    }
    if (input.receiptsExist) {
        return 'healthy';
    }
    if (!input.cliAvailable) {
        return 'cli-missing';
    }
    if (!input.repoInitialized) {
        return 'not-initialized';
    }
    return 'ready-no-receipts';
}

export function getHomeStateLevel(state: HomeState): HomeStatusLevel {
    if (state === 'access-blocked' || state === 'failing' || state === 'regulated-incomplete') {
        return 'warn';
    }
    if (state === 'healthy' || state === 'ready-no-receipts' || state === 'head-missing') {
        return 'good';
    }
    return 'info';
}

export function getHomeStateTitle(state: HomeState): string {
    switch (state) {
        case 'no-workspace':
            return 'Open a repository to start using AIIR';
        case 'access-blocked':
            return 'Repository hidden by workspace policy';
        case 'cli-missing':
            return 'This commit needs the AIIR CLI';
        case 'not-initialized':
            return 'This commit needs repository setup';
        case 'ready-no-receipts':
            return 'This commit is ready to record';
        case 'head-missing':
            return 'Latest commit needs a record';
        case 'regulated-incomplete':
            return 'Needs stronger evidence';
        case 'healthy':
            return 'Current commit activity is recorded';
        case 'failing':
            return 'Receipts need attention';
    }
}

export function getHomeStateNextAction(state: HomeState): HomeActionDefinition {
    switch (state) {
        case 'no-workspace':
            return {
                label: 'Open Folder',
                description: 'Open a repository so AIIR can inspect the current workspace',
                commandId: 'workbench.action.files.openFolder',
                iconId: 'folder-opened',
            };
        case 'access-blocked':
            return {
                label: 'Fix Workspace Access',
                description: 'Review workspace isolation and allowlist settings so AIIR can see this repository again',
                commandId: 'aiir.securityPosture',
                iconId: 'shield',
            };
        case 'cli-missing':
            return {
                label: 'Install the CLI',
                description: 'Install AIIR into a dedicated user-local environment so this repository can record and verify commit activity',
                commandId: 'aiir.installCliNow',
                iconId: 'terminal',
            };
        case 'not-initialized':
            return {
                label: 'Initialize Repository',
                description: 'Create the local .aiir scaffolding so the current commit can be recorded from inside VS Code',
                commandId: 'aiir.initializeRepo',
                iconId: 'new-folder',
            };
        case 'ready-no-receipts':
            return {
                label: 'Record Commit Activity',
                description: 'Create a verifiable record for the current commit. AIIR prefers deterministic provenance when the active file supports it, then falls back automatically.',
                commandId: 'aiir.generatePreferred',
                iconId: 'sparkle',
            };
        case 'head-missing':
            return {
                label: 'Record Commit Activity',
                description: 'The latest commit is not recorded yet. Create a verifiable record for the current commit now.',
                commandId: 'aiir.generatePreferred',
                iconId: 'sparkle',
            };
        case 'regulated-incomplete':
            return {
                label: 'Strengthen Evidence',
                description: 'The repository is recorded, but the evidence bar for regulated mode is not met. Review the health check for details.',
                commandId: 'aiir.healthCheck',
                iconId: 'shield',
            };
        case 'failing':
            return {
                label: 'Check Receipts',
                description: 'Inspect failing receipts and refresh their status',
                commandId: 'aiir.verifyAll',
                iconId: 'warning',
            };
        case 'healthy':
            return {
                label: 'View Latest Receipt',
                description: 'Open the latest clean receipt for this repository and verify what was recorded.',
                commandId: 'aiir.viewReceipt',
                iconId: 'preview',
            };
    }
}

export function getHomePrimaryCardDefinition(
    state: HomeState,
    invalidReceiptCount: number,
    hasLatestReceipt: boolean,
    extra?: { sigstoreReceiptCount?: number; activeExceptionCount?: number },
): HomePrimaryCardDefinition {
    switch (state) {
        case 'no-workspace':
            return {
                headline: 'Open a folder to get started',
                detail: 'AIIR can tell you whether AI-assisted work is being recorded and verified as soon as you open a repository.',
                primaryAction: { label: 'Open Folder', commandId: 'workbench.action.files.openFolder' },
            };
        case 'access-blocked':
            return {
                headline: 'Allow this repository in workspace policy',
                detail: 'A repository is open, but AIIR is currently prevented from reading it by workspace isolation or the allowlist.',
                primaryAction: { label: 'Fix Workspace Access', commandId: 'aiir.securityPosture' },
            };
        case 'cli-missing':
            return {
                headline: 'This commit needs the AIIR CLI',
                detail: 'The repository is open, but AIIR needs the public CLI before it can record or automate commit activity here. AIIR can install it into a dedicated user-local environment.',
                primaryAction: { label: 'Install CLI', commandId: 'aiir.installCliNow' },
                secondaryAction: { label: 'Commit Status', commandId: 'aiir.readinessCheck' },
            };
        case 'not-initialized':
            return {
                headline: 'This commit needs repository setup',
                detail: 'The repository is open and the CLI is ready, but local AIIR scaffolding is missing. Initialize it once so AIIR can record the current and future commits here.',
                primaryAction: { label: 'Initialize Repository', commandId: 'aiir.initializeRepo' },
            };
        case 'ready-no-receipts':
            return {
                headline: 'This commit is ready to record',
                detail: 'AIIR is ready. Record the current commit now. The default action prefers deterministic provenance when an active file is available.',
                primaryAction: { label: 'Record Commit Activity', commandId: 'aiir.generatePreferred' },
            };
        case 'head-missing':
            return {
                headline: 'Latest commit needs a record',
                detail: 'Historical receipts exist, but the current commit still needs coverage. Record it now. The default action prefers deterministic provenance when an active file is available.',
                primaryAction: { label: 'Record Commit Activity', commandId: 'aiir.generatePreferred' },
            };
        case 'regulated-incomplete':
            return {
                headline: 'Needs stronger evidence',
                detail: `Receipts exist but regulated mode requires stronger evidence. Review the health check to see what is missing.${(extra?.activeExceptionCount ?? 0) > 0 ? ` (${extra!.activeExceptionCount} active exception${extra!.activeExceptionCount === 1 ? '' : 's'})` : ''}`,
                primaryAction: { label: 'Open Health Check', commandId: 'aiir.healthCheck' },
                secondaryAction: { label: 'Record Exception', commandId: 'aiir.recordException' },
            };
        case 'failing':
            return {
                headline: `${invalidReceiptCount} receipt${invalidReceiptCount === 1 ? '' : 's'} need attention`,
                detail: 'One or more receipts failed verification. Review them before relying on the current record.',
                primaryAction: { label: 'Check Receipts', commandId: 'aiir.verifyAll' },
            };
        case 'healthy':
            return {
                headline: 'Current commit activity is recorded',
                detail: 'This repository is covered for the current workflow and the latest receipt is verifying cleanly.',
                primaryAction: { label: hasLatestReceipt ? 'View Latest Receipt' : 'Record Commit Activity', commandId: hasLatestReceipt ? 'aiir.viewReceipt' : 'aiir.generatePreferred' },
                secondaryAction: (extra?.sigstoreReceiptCount ?? 0) === 0
                    ? { label: 'Signing Guide', commandId: 'aiir.openSigningGuide' }
                    : undefined,
            };
    }
}

export function getTrustVertex(state: HomeState): TrustVertex {
    switch (state) {
        case 'no-workspace':
        case 'access-blocked':
            return 'open';
        case 'cli-missing':
            return 'install';
        case 'not-initialized':
            return 'initialize';
        case 'ready-no-receipts':
        case 'head-missing':
            return 'generate';
        case 'regulated-incomplete':
            return 'regulated';
        case 'healthy':
            return 'covered';
        case 'failing':
            return 'attention';
    }
}

export function resolveTrustState(input: TrustStateInput): ResolvedTrustState {
    const meetsEvidenceBar = !input.regulatedMode || (
        input.headReceiptStatus === 'present' &&
        input.policyEnabled !== false &&
        (input.currentEvidenceTier === 'signed' || input.currentEvidenceTier === 'inference-bound' || input.currentEvidenceTier === 'provable')
    );
    const homeState = resolveHomeState({
        workspaceOpen: input.workspaceOpen,
        accessBlocked: input.accessBlocked,
        cliAvailable: input.cliAvailable,
        repoInitialized: input.repoInitialized,
        policyEnabled: input.policyEnabled,
        receiptsExist: input.receiptCount > 0,
        allReceiptsValid: input.invalidReceiptCount === 0,
        headCovered: input.headReceiptStatus === 'present',
        regulatedMode: input.regulatedMode,
        meetsEvidenceBar,
    });
    const primaryCard = getHomePrimaryCardDefinition(homeState, input.invalidReceiptCount, !!input.latestReceipt, {
        sigstoreReceiptCount: input.sigstoreReceiptCount,
        activeExceptionCount: input.activeExceptionCount,
    });

    return {
        homeState,
        vertex: getTrustVertex(homeState),
        level: getHomeStateLevel(homeState),
        title: getHomeStateTitle(homeState),
        nextAction: getHomeStateNextAction(homeState),
        primaryCard,
        repoName: input.repoName,
        branch: input.branch,
        folderCount: input.folderCount,
        receiptCount: input.receiptCount,
        invalidReceiptCount: input.invalidReceiptCount,
        hasReceipts: input.receiptCount > 0,
        headCovered: input.headReceiptStatus === 'present',
        headReceiptStatus: input.headReceiptStatus,
        latestReceipt: input.latestReceipt,
        primaryAction: {
            label: primaryCard.primaryAction.label,
            commandId: primaryCard.primaryAction.commandId,
            args: primaryCard.primaryAction.commandId === 'aiir.viewReceipt' && input.latestReceipt
                ? [input.latestReceipt.uri]
                : undefined,
        },
        cliAvailable: input.cliAvailable,
        repoInitialized: input.repoInitialized,
        activeAITool: input.activeAITool,
        hookKind: input.hookKind,
        headSha: input.headSha,
        accessBlocked: input.accessBlocked,
        workspaceOpen: input.workspaceOpen,
    };
}
