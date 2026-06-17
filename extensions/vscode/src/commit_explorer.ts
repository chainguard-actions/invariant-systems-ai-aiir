/**
 * Commit-centric tree view for AIIR.
 *
 * Shows recent commits as the primary axis with receipt status, AI involvement,
 * file-level diffs, Sigstore signing state, and ledger coverage as inline
 * badges.  This replaces the Home view as the default landing surface.
 *
 * Mental model:
 *   commit → files changed → AI involvement per file → receipt + evidence tier
 *
 * @license Apache-2.0
 */

import * as vscode from 'vscode';

// ── Public types consumed by extension.ts ─────────────────────────────

export interface CommitInfo {
    sha: string;
    shortSha: string;
    subject: string;
    authorName: string;
    authorDate: string;          // ISO-8601
    files: CommitFileInfo[];
}

export interface CommitFileInfo {
    /** Path relative to the repository root. */
    path: string;
    /** Git status letter: A, M, D, R, C, etc. */
    status: string;
}

export interface CommitReceiptOverlay {
    /** Receipt exists for this commit SHA. */
    hasReceipt: boolean;
    /** Receipt is valid (passes SPEC §9 verification). */
    valid: boolean;
    /** Evidence tier when receipt exists. */
    evidenceTier?: 'signed' | 'inference-bound' | 'provable' | 'heuristic' | 'unsigned';
    /** Sigstore bundle present. */
    sigstorePresent: boolean;
    /** Receipt recorded in ledger (.aiir/receipts.jsonl). */
    inLedger: boolean;
    /** URI of the receipt JSON file for direct open. */
    receiptUri?: vscode.Uri;
    /** Per-file AI involvement flags keyed by relative path. */
    aiFiles: ReadonlyMap<string, CommitFileAI>;
    /** Human-readable error summary when receipt is invalid. */
    errorSummary?: string;
}

export interface CommitFileAI {
    aiAssisted: boolean;
    tool?: string;
    /** 'provable' when deterministic editor provenance exists for this file. */
    evidenceKind?: 'provable' | 'heuristic' | 'none';
}

// ── Tree node types ───────────────────────────────────────────────────

export type CommitExplorerNode =
    | CommitItem
    | CommitFileItem
    | CommitReceiptStatusItem
    | CommitActionItem
    | CommitPlaceholderItem
    | CommitCoverageFooter;

function treeIdPart(value: unknown): string {
    return String(value ?? '')
        .replace(/[^a-zA-Z0-9._:-]+/g, '_')
        .replace(/^_+|_+$/g, '')
        || 'item';
}

/**
 * Top-level node — one per recent commit.
 */
export class CommitItem extends vscode.TreeItem {
    constructor(
        public readonly commit: CommitInfo,
        public readonly overlay: CommitReceiptOverlay,
        public readonly folderPath: string,
    ) {
        super(commit.subject, vscode.TreeItemCollapsibleState.Collapsed);
        this.description = formatCommitDescription(commit, overlay);
        this.id = `commit:${treeIdPart(folderPath)}:${treeIdPart(commit.sha)}`;
        this.iconPath = commitIcon(overlay);
        this.tooltip = formatCommitTooltip(commit, overlay);
        this.contextValue = overlay.hasReceipt
            ? (overlay.valid ? 'commit-receipted' : 'commit-failing')
            : 'commit-uncovered';
    }
}

/**
 * File changed in a commit — shown when a commit node is expanded.
 */
export class CommitFileItem extends vscode.TreeItem {
    constructor(
        public readonly file: CommitFileInfo,
        public readonly ai: CommitFileAI | undefined,
        public readonly commitSha: string,
        public readonly folderPath: string,
        public readonly covered: boolean,
    ) {
        super(file.path, vscode.TreeItemCollapsibleState.None);
        this.id = `commit-file:${treeIdPart(folderPath)}:${treeIdPart(commitSha)}:${treeIdPart(file.path)}`;
        this.description = formatFileDescription(file, ai);
        this.iconPath = fileIcon(file, ai, covered);
        this.tooltip = formatFileTooltip(file, ai);
        this.contextValue = 'commit-file';

        // Open diff on click: compare parent version vs commit version.
        this.command = {
            title: 'View Diff',
            command: 'aiir.viewCommitFileDiff',
            arguments: [commitSha, file.path, folderPath],
        };
    }
}

/**
 * Inline status line showing receipt + Sigstore + ledger at a glance.
 */
export class CommitReceiptStatusItem extends vscode.TreeItem {
    constructor(
        public readonly overlay: CommitReceiptOverlay,
        public readonly commitSha: string,
        public readonly folderPath: string,
    ) {
        super(formatReceiptStatusLabel(overlay), vscode.TreeItemCollapsibleState.None);
        this.id = `commit-status:${treeIdPart(folderPath)}:${treeIdPart(commitSha)}`;
        this.iconPath = overlay.hasReceipt && overlay.valid
            ? new vscode.ThemeIcon('pass', new vscode.ThemeColor('charts.green'))
            : new vscode.ThemeIcon('circle-slash', new vscode.ThemeColor('list.errorForeground'));
        this.contextValue = 'commit-receipt-status';

        if (overlay.hasReceipt) {
            this.command = {
                title: 'View Proof',
                command: 'aiir.viewReceiptForCommit',
                arguments: [commitSha, folderPath],
            };
        }
    }
}

/**
 * Inline action button — "Generate Receipt", "Repair Receipt", "Sign".
 */
export class CommitActionItem extends vscode.TreeItem {
    constructor(
        label: string,
        public readonly commandId: string,
        public readonly commandArgs: unknown[],
        iconId: string,
    ) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.id = `commit-action:${treeIdPart(commandId)}:${commandArgs.map(treeIdPart).join(':') || treeIdPart(label)}`;
        this.iconPath = new vscode.ThemeIcon(iconId);
        this.contextValue = 'commit-action';
        this.command = {
            title: label,
            command: commandId,
            arguments: commandArgs,
        };
    }
}

/**
 * Informational placeholder shown when the tree has no actionable commit rows.
 */
export class CommitPlaceholderItem extends vscode.TreeItem {
    constructor(
        label: string,
        description: string,
        iconId: string,
    ) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.id = `commit-placeholder:${treeIdPart(label)}`;
        this.description = description;
        this.iconPath = new vscode.ThemeIcon(iconId);
        this.contextValue = 'commit-placeholder';
    }
}

/**
 * Footer node at the bottom of the tree showing aggregate coverage.
 */
export class CommitCoverageFooter extends vscode.TreeItem {
    constructor(
        public readonly stats: CoverageStats,
        public readonly folderPath: string,
    ) {
        super(formatCoverageLabel(stats), vscode.TreeItemCollapsibleState.None);
        this.id = `commit-coverage:${treeIdPart(folderPath)}`;
        this.description = formatCoverageDescription(stats);
        this.iconPath = new vscode.ThemeIcon(stats.gaps > 0 ? 'warning' : 'verified');
        this.contextValue = 'coverage-footer';
        if (stats.gaps > 0) {
            this.command = {
                title: 'Generate Missing Receipts',
                command: 'aiir.generateMissingReceipts',
                arguments: [folderPath],
            };
            this.tooltip = `${stats.gaps} commit${stats.gaps === 1 ? '' : 's'} without receipts — click to generate all`;
        }
    }
}

export interface CoverageStats {
    totalCommits: number;
    coveredCommits: number;
    signedCommits: number;
    gaps: number;
    ledgerEntries: number;
    listenerActive: boolean;
}

// ── Tree data provider ────────────────────────────────────────────────

export interface CommitExplorerDeps {
    /** Return the N most recent commits for the given workspace folder. */
    getRecentCommits(folderPath: string, limit: number): Promise<CommitInfo[]>;
    /** Return the receipt overlay for a commit SHA, or a default no-receipt overlay. */
    getReceiptOverlay(folderPath: string, commitSha: string): Promise<CommitReceiptOverlay>;
    /** Return the number of entries in .aiir/receipts.jsonl. */
    getLedgerEntryCount(folderPath: string): Promise<number>;
    /** Whether passive AI edit tracking is currently active. */
    isListenerActive(): boolean;
}

export class CommitExplorerProvider implements vscode.TreeDataProvider<CommitExplorerNode> {
    private _onDidChangeTreeData = new vscode.EventEmitter<void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private commits: CommitInfo[] = [];
    private overlays = new Map<string, CommitReceiptOverlay>();
    private folderPath: string | undefined;
    private coverageStats: CoverageStats | undefined;

    constructor(private readonly deps: CommitExplorerDeps) { }

    async refresh(folderPath: string | undefined): Promise<void> {
        this.folderPath = folderPath;
        this.commits = [];
        this.overlays.clear();
        this.coverageStats = undefined;

        if (!folderPath) {
            this._onDidChangeTreeData.fire();
            return;
        }

        const limit = vscode.workspace.getConfiguration('aiir').get<number>('commitExplorerLimit', 20);
        this.commits = await this.deps.getRecentCommits(folderPath, limit);

        let covered = 0;
        let signed = 0;
        for (const commit of this.commits) {
            const overlay = await this.deps.getReceiptOverlay(folderPath, commit.sha);
            this.overlays.set(commit.sha, overlay);
            if (overlay.hasReceipt) {
                covered += 1;
            }
            if (overlay.sigstorePresent) {
                signed += 1;
            }
        }

        const ledgerEntries = await this.deps.getLedgerEntryCount(folderPath);

        this.coverageStats = {
            totalCommits: this.commits.length,
            coveredCommits: covered,
            signedCommits: signed,
            gaps: this.commits.length - covered,
            ledgerEntries,
            listenerActive: this.deps.isListenerActive(),
        };

        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: CommitExplorerNode): vscode.TreeItem {
        return element;
    }

    getChildren(element?: CommitExplorerNode): CommitExplorerNode[] {
        if (!element) {
            return this.getRootItems();
        }
        if (element instanceof CommitItem) {
            return this.getCommitChildren(element);
        }
        return [];
    }

    // ── Private helpers -----------------------------------------------

    private getRootItems(): CommitExplorerNode[] {
        if (!this.folderPath) {
            return buildNoRepositoryItems();
        }

        if (this.commits.length === 0) {
            return buildNoCommitItems();
        }

        const items: CommitExplorerNode[] = this.commits.map(commit => {
            const overlay = this.overlays.get(commit.sha) ?? emptyOverlay();
            return new CommitItem(commit, overlay, this.folderPath!);
        });

        if (this.coverageStats) {
            items.push(new CommitCoverageFooter(this.coverageStats, this.folderPath!));
        }

        return items;
    }

    private getCommitChildren(item: CommitItem): CommitExplorerNode[] {
        const children: CommitExplorerNode[] = [];
        const { commit, overlay, folderPath } = item;

        // 1. Commit metadata line
        const metaItem = new vscode.TreeItem(
            `${commit.authorName}  \u2022  ${friendlyDate(commit.authorDate)}  \u2022  ${commit.shortSha}`,
        );
        metaItem.id = `commit-meta:${treeIdPart(folderPath)}:${treeIdPart(commit.sha)}`;
        metaItem.iconPath = new vscode.ThemeIcon('git-commit');
        metaItem.contextValue = 'commit-meta';
        metaItem.tooltip = `Full SHA: ${commit.sha}`;
        children.push(metaItem as unknown as CommitExplorerNode);

        // 2. File list with AI annotations + coverage color
        const covered = overlay.hasReceipt && overlay.valid;
        const aiFileCount = [...overlay.aiFiles.values()].filter(a => a.aiAssisted).length;
        const humanFileCount = commit.files.length - aiFileCount;
        if (commit.files.length > 0) {
            const summaryParts: string[] = [];
            if (aiFileCount > 0) {
                summaryParts.push(`${aiFileCount} AI-assisted`);
            }
            if (humanFileCount > 0) {
                summaryParts.push(`${humanFileCount} human-authored`);
            }
            const filesHeader = new vscode.TreeItem(
                `${commit.files.length} file${commit.files.length === 1 ? '' : 's'} changed  \u2022  ${summaryParts.join(', ')}`,
            );
            filesHeader.id = `commit-files-header:${treeIdPart(folderPath)}:${treeIdPart(commit.sha)}`;
            filesHeader.iconPath = new vscode.ThemeIcon('files');
            filesHeader.contextValue = 'commit-files-header';
            children.push(filesHeader as unknown as CommitExplorerNode);
        }
        for (const file of commit.files) {
            const ai = overlay.aiFiles.get(file.path);
            children.push(new CommitFileItem(file, ai, commit.sha, folderPath, covered));
        }

        // 3. Receipt status line
        children.push(new CommitReceiptStatusItem(overlay, commit.sha, folderPath));

        // 4. Context-specific action
        if (!overlay.hasReceipt) {
            children.push(new CommitActionItem(
                'Generate Receipt',
                'aiir.generateReceiptForCommit',
                [commit.sha, folderPath],
                'add',
            ));
        } else if (!overlay.valid) {
            children.push(new CommitActionItem(
                'Repair Receipt',
                'aiir.generateReceiptForCommit',
                [commit.sha, folderPath],
                'wrench',
            ));
            if (overlay.errorSummary) {
                const errorItem = new vscode.TreeItem(overlay.errorSummary);
                errorItem.id = `commit-error:${treeIdPart(folderPath)}:${treeIdPart(commit.sha)}`;
                errorItem.iconPath = new vscode.ThemeIcon('error');
                // Cast to satisfy the union — this is a leaf info node.
                children.push(errorItem as unknown as CommitExplorerNode);
            }
        } else if (!overlay.sigstorePresent) {
            children.push(new CommitActionItem(
                'Set Up Sigstore',
                'aiir.installSigstoreSupport',
                [],
                'lock',
            ));
        }

        return children;
    }
}

// ── Formatting helpers ────────────────────────────────────────────────

function emptyOverlay(): CommitReceiptOverlay {
    return {
        hasReceipt: false,
        valid: false,
        sigstorePresent: false,
        inLedger: false,
        aiFiles: new Map(),
    };
}

function buildNoRepositoryItems(): CommitExplorerNode[] {
    const workspaceCount = vscode.workspace.workspaceFolders?.length ?? 0;

    if (workspaceCount === 0) {
        return [
            new CommitPlaceholderItem(
                'Open a folder to start using AIIR',
                'Commit coverage appears here after you open a repository.',
                'folder-opened',
            ),
            new CommitActionItem('Open Folder', 'vscode.openFolder', [], 'folder-opened'),
            new CommitActionItem('Check Status', 'aiir.readinessCheck', [], 'checklist'),
            new CommitActionItem('Open Getting Started', 'aiir.openWalkthrough', [], 'milestone'),
        ];
    }

    return [
        new CommitPlaceholderItem(
            'No repository available for commit coverage',
            'Open a git repository or check commit status to see what AIIR can use in this workspace.',
            'source-control',
        ),
        new CommitActionItem('Check Status', 'aiir.readinessCheck', [], 'checklist'),
        new CommitActionItem('Open Getting Started', 'aiir.openWalkthrough', [], 'milestone'),
    ];
}

function buildNoCommitItems(): CommitExplorerNode[] {
    return [
        new CommitPlaceholderItem(
            'No recent commits yet',
            'Make the first commit, then generate a receipt to cover it.',
            'git-commit',
        ),
        new CommitActionItem('Check Status', 'aiir.readinessCheck', [], 'checklist'),
        new CommitActionItem('Open Getting Started', 'aiir.openWalkthrough', [], 'milestone'),
    ];
}

function formatCommitDescription(commit: CommitInfo, overlay: CommitReceiptOverlay): string {
    const parts: string[] = [];

    if (overlay.hasReceipt && overlay.valid) {
        parts.push('covered');
        parts.push(overlay.evidenceTier ?? 'receipted');
    } else if (overlay.hasReceipt && !overlay.valid) {
        parts.push('needs repair');
    } else {
        parts.push('needs receipt');
    }

    if (overlay.sigstorePresent) {
        parts.push('signed');
    }
    if (overlay.inLedger) {
        parts.push('recorded');
    }

    parts.push(commit.shortSha);

    return parts.join(' \u2502 ');
}

function commitIcon(overlay: CommitReceiptOverlay): vscode.ThemeIcon {
    if (!overlay.hasReceipt) {
        return new vscode.ThemeIcon('circle-large-outline', new vscode.ThemeColor('list.errorForeground'));
    }
    if (!overlay.valid) {
        return new vscode.ThemeIcon('error', new vscode.ThemeColor('list.errorForeground'));
    }
    if (overlay.sigstorePresent) {
        return new vscode.ThemeIcon('verified-filled', new vscode.ThemeColor('charts.green'));
    }
    return new vscode.ThemeIcon('verified', new vscode.ThemeColor('charts.green'));
}

function formatCommitTooltip(commit: CommitInfo, overlay: CommitReceiptOverlay): string {
    const lines = [
        `${commit.shortSha}  ${commit.subject}`,
        `Author: ${commit.authorName}`,
        `Date: ${commit.authorDate}`,
        '',
    ];

    if (!overlay.hasReceipt) {
        lines.push('No AIIR receipt — click to generate.');
    } else if (!overlay.valid) {
        lines.push(`Receipt FAILING: ${overlay.errorSummary ?? 'verification error'}`);
    } else {
        lines.push(`Evidence tier: ${overlay.evidenceTier ?? 'unknown'}`);
        lines.push(`Sigstore: ${overlay.sigstorePresent ? 'signed' : 'unsigned'}`);
        lines.push(`Ledger: ${overlay.inLedger ? 'recorded' : 'not recorded'}`);
    }

    return lines.join('\n');
}

function formatFileDescription(file: CommitFileInfo, ai: CommitFileAI | undefined): string {
    const parts: string[] = [];

    switch (file.status) {
        case 'A': parts.push('added'); break;
        case 'M': parts.push('modified'); break;
        case 'D': parts.push('deleted'); break;
        case 'R': parts.push('renamed'); break;
        case 'C': parts.push('copied'); break;
        default: if (file.status) { parts.push(file.status); }
    }

    if (ai?.aiAssisted) {
        const tool = ai.tool ? `${ai.tool}-assisted` : 'AI-assisted';
        parts.push(tool);
    } else {
        parts.push('human');
    }

    return parts.join(' \u2502 ');
}

function fileIcon(file: CommitFileInfo, ai: CommitFileAI | undefined, covered: boolean): vscode.ThemeIcon {
    const color = covered
        ? new vscode.ThemeColor('charts.green')
        : new vscode.ThemeColor('list.errorForeground');
    if (ai?.aiAssisted) {
        return new vscode.ThemeIcon('sparkle', color);
    }
    switch (file.status) {
        case 'A': return new vscode.ThemeIcon('diff-added', color);
        case 'D': return new vscode.ThemeIcon('diff-removed', color);
        case 'R': return new vscode.ThemeIcon('diff-renamed', color);
        default: return new vscode.ThemeIcon('diff-modified', color);
    }
}

function formatFileTooltip(file: CommitFileInfo, ai: CommitFileAI | undefined): string {
    const lines = [file.path];
    if (ai?.aiAssisted) {
        lines.push(`AI tool: ${ai.tool ?? 'detected'}`);
        lines.push(`Evidence: ${ai.evidenceKind ?? 'heuristic'}`);
    } else {
        lines.push('Human-authored');
    }
    return lines.join('\n');
}

function formatReceiptStatusLabel(overlay: CommitReceiptOverlay): string {
    if (!overlay.hasReceipt) {
        return 'Needs receipt — coverage gap';
    }
    if (!overlay.valid) {
        return `Needs repair: ${overlay.errorSummary ?? 'verification error'}`;
    }

    const parts = [`Covered: ${overlay.evidenceTier ?? 'present'}`];
    parts.push(overlay.sigstorePresent ? 'signed' : 'unsigned');
    parts.push(overlay.inLedger ? 'recorded' : 'not recorded');
    return parts.join(' \u2502 ');
}

function formatCoverageLabel(stats: CoverageStats): string {
    return `Coverage ${stats.coveredCommits}/${stats.totalCommits} commits`;
}

function formatCoverageDescription(stats: CoverageStats): string {
    const parts: string[] = [];
    if (stats.gaps > 0) {
        parts.push(`${stats.gaps} need receipt`);
    }
    if (stats.signedCommits > 0) {
        parts.push(`${stats.signedCommits} signed`);
    }
    parts.push(`ledger ${stats.ledgerEntries}`);
    parts.push(stats.listenerActive ? 'tracking on' : 'tracking off');
    return parts.join(' \u2502 ');
}

function friendlyDate(iso: string): string {
    try {
        const d = new Date(iso);
        const now = new Date();
        const diffMs = now.getTime() - d.getTime();
        const diffMins = Math.floor(diffMs / 60_000);
        if (diffMins < 1) { return 'just now'; }
        if (diffMins < 60) { return `${diffMins}m ago`; }
        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) { return `${diffHours}h ago`; }
        const diffDays = Math.floor(diffHours / 24);
        if (diffDays < 7) { return `${diffDays}d ago`; }
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
        return iso;
    }
}
