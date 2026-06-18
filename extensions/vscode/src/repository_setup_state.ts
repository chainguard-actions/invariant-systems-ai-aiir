export type RepositoryHookState = 'managed' | 'custom' | 'missing';

export interface RepositorySetupState {
    gitAvailable: boolean;
    cliAvailable: boolean;
    aiirDirExists: boolean;
    hasLedger: boolean;
    policyExists: boolean;
    hookState: RepositoryHookState;
    provenanceQueueExists: boolean;
    hasReceipts: boolean;
}

export type RepositoryHeadReceiptStatus = 'present' | 'missing' | 'unknown';

export interface RepositoryViewStateSnapshot extends RepositorySetupState {
    branch?: string;
    headSha?: string;
    receiptCount: number;
    headReceiptStatus: RepositoryHeadReceiptStatus;
    activeAIToolName?: string;
    activeAIToolPresent: boolean;
}

export interface RepositoryViewProbeSnapshot {
    gitAvailable: boolean;
    branch?: string;
    headSha?: string;
    cliAvailable: boolean;
    aiirDirExists: boolean;
    hasLedger: boolean;
    policyExists: boolean;
    hookState: RepositoryHookState;
    provenanceQueueExists: boolean;
    receiptCount: number;
    hasReceipts: boolean;
    headReceiptStatus: RepositoryHeadReceiptStatus;
    activeAIToolName?: string;
}

export type SetupPriorityKey =
    | 'git'
    | 'cli'
    | 'aiir'
    | 'ledger'
    | 'policy'
    | 'hook'
    | 'provenance'
    | 'live-activity';

export interface OrderedSetupChecklistItem {
    key: SetupPriorityKey;
    ready: boolean;
    live?: boolean;
}

export const SETUP_PRIORITY_CHAIN: readonly SetupPriorityKey[] = [
    'git',
    'cli',
    'aiir',
    'ledger',
    'policy',
    'hook',
    'provenance',
    'live-activity',
];

export function shouldShowRepository(state: RepositorySetupState | undefined): boolean {
    if (!state) {
        return false;
    }

    return state.hasReceipts || state.hasLedger || state.aiirDirExists;
}

export function isRepositoryFullyReady(state: RepositorySetupState | undefined): boolean {
    if (!state) {
        return false;
    }

    return state.aiirDirExists && state.hasLedger && state.cliAvailable && state.policyExists;
}

export function sortSetupChecklist<T extends OrderedSetupChecklistItem>(items: readonly T[]): T[] {
    return [...items].sort((left, right) => {
        if (!!left.live !== !!right.live) {
            return left.live ? 1 : -1;
        }
        if (left.ready !== right.ready) {
            return Number(left.ready) - Number(right.ready);
        }

        return SETUP_PRIORITY_CHAIN.indexOf(left.key) - SETUP_PRIORITY_CHAIN.indexOf(right.key);
    });
}

export function resolveRepositoryViewStateSnapshot(snapshot: RepositoryViewProbeSnapshot): RepositoryViewStateSnapshot {
    return {
        gitAvailable: snapshot.gitAvailable,
        branch: snapshot.branch,
        headSha: snapshot.headSha,
        cliAvailable: snapshot.cliAvailable,
        aiirDirExists: snapshot.aiirDirExists,
        hasLedger: snapshot.hasLedger,
        policyExists: snapshot.policyExists,
        hookState: snapshot.hookState,
        provenanceQueueExists: snapshot.provenanceQueueExists,
        receiptCount: snapshot.receiptCount,
        hasReceipts: snapshot.hasReceipts,
        headReceiptStatus: snapshot.headReceiptStatus,
        activeAIToolName: snapshot.activeAIToolName,
        activeAIToolPresent: !!snapshot.activeAIToolName,
    };
}
