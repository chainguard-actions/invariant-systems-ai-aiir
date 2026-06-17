import * as fs from 'fs';
import * as path from 'path';

export interface WorkspaceFolderTarget<T> {
    name?: string;
    fsPath: string;
    value: T;
}

function usesWindowsPaths(fsPath: string): boolean {
    return /^[a-zA-Z]:[\\/]/.test(fsPath) || fsPath.includes('\\');
}

function getPathModule(fsPath: string): typeof path.posix | typeof path.win32 {
    return usesWindowsPaths(fsPath) ? path.win32 : path.posix;
}

function normalizeFsPath(fsPath: string): string {
    const pathModule = getPathModule(fsPath);
    let resolvedPath = pathModule.resolve(fsPath);
    try {
        resolvedPath = typeof fs.realpathSync.native === 'function'
            ? fs.realpathSync.native(resolvedPath)
            : fs.realpathSync(resolvedPath);
    } catch {
        // Fall back to the normalized absolute path when the target does not exist yet.
    }

    let normalized = pathModule.normalize(resolvedPath).replace(/\\/g, '/');
    if (normalized.endsWith('/')) {
        return normalized.slice(0, -1);
    }

    if (/^[A-Z]:/.test(normalized)) {
        normalized = normalized[0].toLowerCase() + normalized.slice(1);
    }

    return normalized;
}

export function isPathInside(rootPath: string, targetPath: string): boolean {
    const normalizedRoot = normalizeFsPath(rootPath);
    const normalizedTarget = normalizeFsPath(targetPath);
    const pathModule = usesWindowsPaths(rootPath) || usesWindowsPaths(targetPath) ? path.win32 : path.posix;
    const relativePath = pathModule.relative(normalizedRoot, normalizedTarget);

    return relativePath === '' || (!relativePath.startsWith('..') && !pathModule.isAbsolute(relativePath));
}

function normalizeFolderSelector(value: string): string {
    return value.trim();
}

export function matchesWorkspaceFolderSelector<T>(folder: WorkspaceFolderTarget<T>, selector: string): boolean {
    const normalizedSelector = normalizeFolderSelector(selector);
    if (!normalizedSelector) {
        return false;
    }

    if (folder.name) {
        if (folder.name === normalizedSelector) {
            return true;
        }
    }

    return normalizeFsPath(folder.fsPath) === normalizeFsPath(normalizedSelector);
}

function getNormalizedAllowedFolders(allowedFolders: string[]): string[] {
    const selectors: string[] = [];
    for (const allowedFolder of allowedFolders) {
        const normalizedSelector = normalizeFolderSelector(allowedFolder);
        if (normalizedSelector) {
            selectors.push(normalizedSelector);
        }
    }

    return selectors;
}

function resolveFirstMatchingWorkspaceFolderTarget<T>(folders: WorkspaceFolderTarget<T>[], targetPath: string): T | undefined {
    let bestMatch: WorkspaceFolderTarget<T> | undefined;

    for (const folder of folders) {
        if (!isPathInside(folder.fsPath, targetPath)) {
            continue;
        }

        if (!bestMatch || folder.fsPath.length > bestMatch.fsPath.length) {
            bestMatch = folder;
        }
    }

    if (bestMatch) {
        return bestMatch.value;
    }

    return undefined;
}

function resolveSingleWorkspaceFolderTarget<T>(folders: WorkspaceFolderTarget<T>[]): T | undefined {
    if (folders.length === 1) {
        return folders[0].value;
    }

    return undefined;
}

export function filterWorkspaceFolderTargets<T>(
    folders: WorkspaceFolderTarget<T>[],
    allowedFolders: string[],
    enforceIsolation: boolean,
): WorkspaceFolderTarget<T>[] {
    const selectors = getNormalizedAllowedFolders(allowedFolders);
    if (selectors.length > 0) {
        const matchedFolders: WorkspaceFolderTarget<T>[] = [];

        for (const folder of folders) {
            for (const selector of selectors) {
                if (matchesWorkspaceFolderSelector(folder, selector)) {
                    matchedFolders.push(folder);
                    break;
                }
            }
        }

        return matchedFolders;
    }

    if (!enforceIsolation) {
        return folders;
    }

    if (folders.length <= 1) {
        return folders;
    }

    return [];
}

export function isWorkspaceIsolationBlockingAccess(
    workspaceFolderCount: number,
    allowedFolders: string[],
    enforceIsolation: boolean,
): boolean {
    if (!enforceIsolation) {
        return false;
    }

    if (workspaceFolderCount <= 1) {
        return false;
    }

    return getNormalizedAllowedFolders(allowedFolders).length === 0;
}

export function resolveWorkspaceFolderTarget<T>(
    folders: WorkspaceFolderTarget<T>[],
    targetPath?: string,
): T | undefined {
    if (targetPath) {
        const match = resolveFirstMatchingWorkspaceFolderTarget(folders, targetPath);
        if (match !== undefined) {
            return match;
        }
    }

    return resolveSingleWorkspaceFolderTarget(folders);
}

export function resolvePreferredWorkspaceFolderTarget<T>(
    folders: WorkspaceFolderTarget<T>[],
    targetPath?: string,
    preferredPath?: string,
): T | undefined {
    const directMatch = resolveWorkspaceFolderTarget(folders, targetPath);
    if (directMatch !== undefined) {
        return directMatch;
    }

    if (preferredPath) {
        const preferredMatch = resolveFirstMatchingWorkspaceFolderTarget(folders, preferredPath);
        if (preferredMatch !== undefined) {
            return preferredMatch;
        }
    }

    return resolveSingleWorkspaceFolderTarget(folders);
}
