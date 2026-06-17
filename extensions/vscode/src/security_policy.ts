export function isNetworkAllowed(strictLocalOnly: boolean): boolean {
    return !strictLocalOnly;
}

export function isHubEnabled(strictLocalOnly: boolean, enableHubFeatures: boolean): boolean {
    return isNetworkAllowed(strictLocalOnly) && enableHubFeatures;
}

export function getNoAccessibleWorkspaceMessage(action: string, isolationBlockingAccess: boolean): string {
    if (isolationBlockingAccess) {
        return 'AIIR: Automatic access is blocked in this multi-root workspace until aiir.allowedWorkspaceFolders is configured.';
    }

    return `AIIR: Open a folder or workspace to ${action}`;
}

export function getExplorerMessage(isolationBlockingAccess: boolean): string | undefined {
    return isolationBlockingAccess
        ? 'Automatic discovery is disabled in this multi-root workspace until aiir.allowedWorkspaceFolders is configured.'
        : undefined;
}

export function getNetworkBlockedMessage(action: string): string {
    return `Local-only mode is enabled. Disable aiir.strictLocalOnly to ${action}.`;
}

export function getContextState(strictLocalOnly: boolean, enableHubFeatures: boolean): {
    strictLocalOnly: boolean;
    networkAllowed: boolean;
    hubEnabled: boolean;
} {
    const networkAllowed = isNetworkAllowed(strictLocalOnly);
    return {
        strictLocalOnly,
        networkAllowed,
        hubEnabled: isHubEnabled(strictLocalOnly, enableHubFeatures),
    };
}