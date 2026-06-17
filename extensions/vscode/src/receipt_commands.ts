import * as path from 'path';
import * as vscode from 'vscode';

import { buildGenerateReceiptArgs } from './cli_contract';

export interface VerifyResultLike {
    valid: boolean;
    errors: string[];
}

export interface ReceiptArtifactsLike {
    cborStatus: 'present' | 'missing';
    sigstoreStatus: 'present' | 'missing';
}

export interface ReceiptCommitLike {
    sha?: string;
}

export interface ReceiptDataLike {
    commit?: ReceiptCommitLike;
}

export interface ReceiptRecordLike {
    receipt: ReceiptDataLike;
    uri: vscode.Uri;
    result: VerifyResultLike;
    artifacts: ReceiptArtifactsLike;
    workspaceFolderPath?: string;
}

export interface ReceiptRepairAction {
    label: string;
    description: string;
    command: string;
    args: unknown[];
}

export interface ReceiptRepairPlan {
    headline: string;
    detail: string;
    primaryAction?: ReceiptRepairAction;
    secondaryActions: ReceiptRepairAction[];
}

export interface GenerateReceiptOptions {
    commitSha?: string;
    includeEditorContext?: boolean;
}

export interface ReceiptExplorerLike<TReceiptRecord extends ReceiptRecordLike> {
    refresh(): Promise<void>;
    getReceiptForCommit(commitSha: string, folder: vscode.WorkspaceFolder): TReceiptRecord | undefined;
    getLatestReceipt(folder: vscode.WorkspaceFolder): TReceiptRecord | undefined;
}

export interface HomeProviderLike {
    refresh(target?: vscode.Uri): Promise<void>;
}

export interface StatusBarLike<TReceiptRecord extends ReceiptRecordLike> {
    refresh(explorer: ReceiptExplorerLike<TReceiptRecord>): Promise<void>;
}

export interface PendingActionLike {
    commandId: 'aiir.generatePreferred' | 'aiir.generateReceipt' | 'aiir.initializeRepo' | 'aiir.enableAutoReceipting' | 'aiir.createWorkspacePolicy' | 'aiir.disableAutoReceipting';
    label: string;
    folderPath: string;
}

export interface RegisterReceiptCommandsDependencies<TReceiptRecord extends ReceiptRecordLike> {
    output: vscode.OutputChannel;
    explorer: ReceiptExplorerLike<TReceiptRecord>;
    homeProvider: HomeProviderLike;
    statusBar: StatusBarLike<TReceiptRecord>;
    resolveCommandWorkspaceFolder(target: unknown, placeHolder: string): Promise<vscode.WorkspaceFolder | undefined>;
    showWorkspaceAccessRecovery(action: string): Promise<void>;
    isCliAvailable(folder: vscode.WorkspaceFolder): Promise<boolean>;
    isRepositoryInitialized(folder: vscode.WorkspaceFolder): Promise<boolean>;
    openSetupForPendingAction(action: PendingActionLike): Promise<void>;
    canUseProvenanceGeneration(folder: vscode.WorkspaceFolder): boolean;
    runWithReceiptGenerationLock<T>(folderPath: string, output: vscode.OutputChannel, operation: () => Promise<T>): Promise<T>;
    getCliPath(): string;
    buildAgentArgs(): string[];
    buildEditorProvenanceArgs(): string[];
    runCommand(executable: string, args: string[], cwd: string, output: vscode.OutputChannel): Promise<unknown>;
    getCurrentCommitSha(folder: vscode.WorkspaceFolder): Promise<string | undefined>;
    getPostCommitHookKind(folder: vscode.WorkspaceFolder): Promise<'managed' | 'custom' | 'missing'>;
    getTargetReceiptRecord(target: unknown, explorer: ReceiptExplorerLike<TReceiptRecord>): Promise<TReceiptRecord | undefined>;
    onReceiptGenerated?(): Promise<void>;
}

export interface RegisteredReceiptCommands<TReceiptRecord extends ReceiptRecordLike> {
    commands: vscode.Disposable[];
    generateReceiptForFolder(folder: vscode.WorkspaceFolder, options?: GenerateReceiptOptions): Promise<TReceiptRecord | undefined>;
}

export function getReceiptFailureExplanation(record: ReceiptRecordLike): string {
    const errors = record.result.errors;
    if (errors.some(error => error === 'content hash mismatch' || error === 'receipt_id mismatch')) {
        return 'This receipt failed integrity checks. The JSON body no longer matches the content-addressed identifiers stored inside it.';
    }

    if (errors.some(error =>
        error === 'receipt is not a dict'
        || error.startsWith('unknown receipt type:')
        || error.startsWith('unknown schema:')
        || error.startsWith('invalid version format:'),
    )) {
        return 'This receipt file is malformed or uses a schema/version the local verifier does not accept.';
    }

    return 'This receipt did not pass local verification. Use the repair flow below to replace it with a fresh proof or inspect the attached artifacts.';
}

export function buildReceiptRepairPlan(record: ReceiptRecordLike, currentHeadSha?: string): ReceiptRepairPlan {
    const receiptSha = record.receipt.commit?.sha?.trim();
    const receiptShaShort = receiptSha?.slice(0, 8) || 'unknown';
    const folderUri = record.workspaceFolderPath ? vscode.Uri.file(record.workspaceFolderPath) : undefined;
    const headMatchesReceipt = !!(currentHeadSha && receiptSha && currentHeadSha === receiptSha);
    const secondaryActions: ReceiptRepairAction[] = [];
    const repairArgs = [record.uri];

    if (folderUri) {
        secondaryActions.push({
            label: `Open Coverage Check (${receiptShaShort})`,
            description: 'Review repository health and proof coverage before replacing this proof.',
            command: 'aiir.healthCheck',
            args: [folderUri],
        });
        secondaryActions.push({
            label: `Open Receipt Summary (${receiptShaShort})`,
            description: 'Open the local receipt summary for this repository.',
            command: 'aiir.showSummary',
            args: [folderUri],
        });
    }

    if (record.artifacts.cborStatus === 'present') {
        secondaryActions.push({
            label: `Verify CBOR Sidecar (${receiptShaShort})`,
            description: 'Check whether the canonical CBOR sidecar still verifies.',
            command: 'aiir.verifyCbor',
            args: [record.uri],
        });
    }

    if (record.artifacts.sigstoreStatus === 'present') {
        secondaryActions.push({
            label: `Verify Sigstore Bundle (${receiptShaShort})`,
            description: 'Check whether the Sigstore bundle still verifies.',
            command: 'aiir.verifySigstore',
            args: [record.uri],
        });
    }

    secondaryActions.push({
        label: `Open Receipt JSON (${receiptShaShort})`,
        description: 'Inspect the original receipt file directly.',
        command: 'aiir.openReceiptSource',
        args: [record.uri],
    });

    if (!folderUri) {
        return {
            headline: 'Receipt source is outside the active workspace',
            detail: `${getReceiptFailureExplanation(record)} AIIR can only record a replacement receipt when the repository is open in the current workspace.`,
            secondaryActions,
        };
    }

    if (headMatchesReceipt) {
        return {
            headline: 'Replace this failed receipt with a fresh proof for the same commit',
            detail: `${getReceiptFailureExplanation(record)} The repository is still on the same commit, so the lowest-friction recovery is to re-record a fresh proof for ${receiptSha?.slice(0, 8) || 'this commit'}.`,
            primaryAction: {
                label: `Re-Record Receipt For ${receiptShaShort}`,
                description: 'Generate a new proof for the exact commit referenced by this failed receipt.',
                command: 'aiir.generateReceiptForCommit',
                args: repairArgs,
            },
            secondaryActions,
        };
    }

    if (currentHeadSha && receiptSha) {
        return {
            headline: 'This failed receipt points at an older commit',
            detail: `${getReceiptFailureExplanation(record)} The failed receipt references ${receiptSha.slice(0, 8)}, while this repository is now on ${currentHeadSha.slice(0, 8)}. AIIR cannot repair the file in place, but it can record a fresh proof for the exact historical commit that this failed proof was meant to cover.`,
            primaryAction: {
                label: `Generate Receipt For ${receiptShaShort}`,
                description: 'Record a fresh proof for the exact historical commit referenced by this failed receipt.',
                command: 'aiir.generateReceiptForCommit',
                args: repairArgs,
            },
            secondaryActions,
        };
    }

    return {
        headline: 'Repair this receipt by recording a fresh proof',
        detail: `${getReceiptFailureExplanation(record)} AIIR proofs are content-addressed, so the supported recovery path is to record a fresh proof for the referenced commit instead of editing this file in place.`,
        primaryAction: {
            label: `Re-Record Receipt For ${receiptShaShort}`,
            description: 'Generate a fresh proof for the exact commit referenced by this failed receipt.',
            command: 'aiir.generateReceiptForCommit',
            args: repairArgs,
        },
        secondaryActions,
    };
}

export function registerReceiptCommands<TReceiptRecord extends ReceiptRecordLike>(
    deps: RegisterReceiptCommandsDependencies<TReceiptRecord>,
): RegisteredReceiptCommands<TReceiptRecord> {
    const generateReceiptForFolder = async (
        folder: vscode.WorkspaceFolder,
        options?: GenerateReceiptOptions,
    ): Promise<TReceiptRecord | undefined> => {
        return await deps.runWithReceiptGenerationLock(folder.uri.fsPath, deps.output, async () => {
            const cliPath = deps.getCliPath();
            const includeEditorContext = options?.includeEditorContext ?? !options?.commitSha;
            const agentArgs = includeEditorContext ? deps.buildAgentArgs() : [];
            const provenanceArgs = includeEditorContext ? deps.buildEditorProvenanceArgs() : [];
            const commandArgs = [
                ...buildGenerateReceiptArgs({ commitSha: options?.commitSha }),
                ...provenanceArgs,
                ...agentArgs,
            ];

            await deps.runCommand(cliPath, commandArgs, folder.uri.fsPath, deps.output);

            await deps.explorer.refresh();
            await deps.homeProvider.refresh(folder.uri);
            await deps.statusBar.refresh(deps.explorer);
            await deps.onReceiptGenerated?.();

            const receiptSha = options?.commitSha || await deps.getCurrentCommitSha(folder);
            return receiptSha ? deps.explorer.getReceiptForCommit(receiptSha, folder) : deps.explorer.getLatestReceipt(folder);
        });
    };

    const showReceiptGenerationError = (error: unknown, cliPath: string): void => {
        const err = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
        if (err.stdout) {
            deps.output.appendLine(err.stdout.trimEnd());
        }
        if (err.stderr) {
            deps.output.appendLine(err.stderr.trimEnd());
        }

        if (err.code === 'ENOENT') {
            vscode.window.showErrorMessage(
                `AIIR: Could not find '${cliPath}'. Install AIIR or set aiir.cliPath in settings.`,
            );
        } else {
            vscode.window.showErrorMessage(`AIIR: Receipt generation failed — ${err.message}`);
        }
        deps.output.show(true);
    };

    const promptForGeneratedReceipt = async (
        folder: vscode.WorkspaceFolder,
        receipt: TReceiptRecord | undefined,
        successMessage: string,
    ): Promise<void> => {
        const hookKind = await deps.getPostCommitHookKind(folder);
        const actions = ['Copy Summary', 'View Proof'];
        if (hookKind !== 'managed') {
            actions.push('Turn On Auto Next Time');
        }

        const choice = await vscode.window.showInformationMessage(successMessage, ...actions);

        if (choice === 'View Proof' && receipt) {
            await vscode.commands.executeCommand('aiir.viewReceipt', receipt.uri);
        } else if (choice === 'Copy Summary' && receipt) {
            await vscode.commands.executeCommand('aiir.copyReceiptSummary', receipt);
        } else if (choice === 'Turn On Auto Next Time') {
            await vscode.commands.executeCommand('aiir.enableAutoReceipting', folder.uri);
        }
    };

    const generatePreferredCmd = vscode.commands.registerCommand('aiir.generatePreferred', async (uri?: vscode.Uri) => {
        const folder = await deps.resolveCommandWorkspaceFolder(uri, 'Choose a repository to generate a receipt for');
        if (!folder) {
            await deps.showWorkspaceAccessRecovery('generate receipts');
            return;
        }

        if (!await deps.isCliAvailable(folder)) {
            await deps.openSetupForPendingAction({
                commandId: 'aiir.generatePreferred',
                label: 'Generate',
                folderPath: folder.uri.fsPath,
            });
            return;
        }

        if (!await deps.isRepositoryInitialized(folder)) {
            await vscode.commands.executeCommand('aiir.initializeRepo', folder.uri);
            return;
        }

        await vscode.commands.executeCommand(
            deps.canUseProvenanceGeneration(folder) ? 'aiir.generateWithProvenance' : 'aiir.generateReceipt',
            folder.uri,
        );
    });

    const generateReceiptCmd = vscode.commands.registerCommand('aiir.generateReceipt', async (uri?: vscode.Uri) => {
        const folder = await deps.resolveCommandWorkspaceFolder(uri, 'Choose a repository to generate a receipt for');
        if (!folder) {
            await deps.showWorkspaceAccessRecovery('generate receipts');
            return;
        }

        if (!await deps.isCliAvailable(folder)) {
            await deps.openSetupForPendingAction({
                commandId: 'aiir.generateReceipt',
                label: 'Generate Receipt',
                folderPath: folder.uri.fsPath,
            });
            return;
        }

        try {
            const receipt = await generateReceiptForFolder(folder);
            await promptForGeneratedReceipt(folder, receipt, `AIIR: Current commit recorded in ${folder.name}`);
        } catch (error) {
            showReceiptGenerationError(error, deps.getCliPath());
        }
    });

    const generateReceiptForCommitCmd = vscode.commands.registerCommand('aiir.generateReceiptForCommit', async (target?: unknown, folderPathArg?: unknown) => {
        // Two calling conventions:
        // 1. Commit explorer: target = commitSha (string), folderPathArg = folderPath (string)
        // 2. Receipt explorer / context menu: target = receipt record or URI
        let commitSha: string | undefined;
        let folder: vscode.WorkspaceFolder | undefined;

        if (typeof target === 'string' && /^[0-9a-f]{7,40}$/i.test(target) && typeof folderPathArg === 'string') {
            // Convention 1: commit SHA + folder path from commit explorer
            commitSha = target;
            folder = await deps.resolveCommandWorkspaceFolder(folderPathArg, 'Choose a repository');
        } else {
            // Convention 2: resolve from receipt record
            const record = await deps.getTargetReceiptRecord(target, deps.explorer);
            if (!record) {
                vscode.window.showErrorMessage('AIIR: No receipt is available to repair yet.');
                return;
            }
            commitSha = record.receipt.commit?.sha?.trim();
            if (!commitSha) {
                vscode.window.showErrorMessage('AIIR: This receipt does not include a commit SHA to regenerate.');
                return;
            }
            folder = vscode.workspace.getWorkspaceFolder(record.uri);
        }

        if (!folder) {
            vscode.window.showErrorMessage('AIIR: Open this repository in the current workspace to generate a receipt.');
            return;
        }

        if (!await deps.isCliAvailable(folder)) {
            await deps.openSetupForPendingAction({
                commandId: 'aiir.generateReceipt',
                label: 'Generate Receipt',
                folderPath: folder.uri.fsPath,
            });
            return;
        }

        try {
            const receipt = await generateReceiptForFolder(folder, {
                commitSha,
                includeEditorContext: false,
            });
            await promptForGeneratedReceipt(
                folder,
                receipt,
                `AIIR: Commit ${commitSha.slice(0, 8)} recorded in ${folder.name}`,
            );
        } catch (error) {
            showReceiptGenerationError(error, deps.getCliPath());
        }
    });

    const repairReceiptCmd = vscode.commands.registerCommand('aiir.repairReceipt', async (target?: unknown) => {
        const record = await deps.getTargetReceiptRecord(target, deps.explorer);
        if (!record) {
            vscode.window.showErrorMessage('AIIR: No failed receipt is available to repair.');
            return;
        }

        if (record.result.valid) {
            vscode.window.showInformationMessage('AIIR: This receipt already verifies. No repair action is needed.');
            return;
        }

        const folder = vscode.workspace.getWorkspaceFolder(record.uri);
        const currentHeadSha = folder ? await deps.getCurrentCommitSha(folder) : undefined;
        const plan = buildReceiptRepairPlan(record, currentHeadSha);
        const items = [
            ...(plan.primaryAction ? [{
                label: plan.primaryAction.label,
                description: plan.primaryAction.description,
                action: plan.primaryAction,
            }] : []),
            ...plan.secondaryActions.map(action => ({
                label: action.label,
                description: action.description,
                action,
            })),
        ];

        const choice = await vscode.window.showQuickPick(items, {
            title: 'AIIR: Repair Failed Receipt',
            placeHolder: plan.detail,
            ignoreFocusOut: true,
        });

        if (!choice) {
            return;
        }

        await vscode.commands.executeCommand(choice.action.command, ...choice.action.args);
    });

    return {
        commands: [generateReceiptCmd, generateReceiptForCommitCmd, generatePreferredCmd, repairReceiptCmd],
        generateReceiptForFolder,
    };
}
