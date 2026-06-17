/**
 * AIIR VS Code Extension — AI Integrity Receipt verification in the editor.
 *
 * Features:
 *   - Status bar indicator showing receipt count + verification status
 *   - Receipt Explorer tree view (sidebar)
 *   - Diagnostics integration (Problems panel)
 *   - Verify receipt from file or selection
 *   - CodeLens on receipt files showing verification status inline
 *   - Auto-discovery of .aiir.json and .receipts/ directories
 *   - File watcher for live receipt updates
 *   - Summary webview dashboard
 *
 * Zero external dependencies — embeds the verification algorithm from SPEC.md §9.
 *
 * @license Apache-2.0
 */

import * as vscode from 'vscode';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { execFile } from 'child_process';
import { promisify } from 'util';
import {
    resolveTrustState,
    type HomeState,
    type ResolvedTrustState,
} from './home_state';
import {
    getContextState,
    getExplorerMessage as getSecurityExplorerMessage,
    getNetworkBlockedMessage,
    getNoAccessibleWorkspaceMessage as getSecurityNoAccessibleWorkspaceMessage,
    isHubEnabled as computeHubEnabled,
    isNetworkAllowed as computeNetworkAllowed,
} from './security_policy';
import {
    filterWorkspaceFolderTargets,
    isPathInside,
    isWorkspaceIsolationBlockingAccess,
    resolvePreferredWorkspaceFolderTarget,
    resolveWorkspaceFolderTarget,
} from './workspace_target';
import {
    isRepositoryFullyReady,
    resolveRepositoryViewStateSnapshot,
    shouldShowRepository,
    sortSetupChecklist,
    type RepositorySetupState,
    type RepositoryViewStateSnapshot,
} from './repository_setup_state';
import {
    PROVABLE_QUEUE_FILENAME,
    appendProvenanceRecord,
    parseStructuredEditPlan,
    sha256Text,
    type StructuredEditOperation,
} from './provable_mode';
import {
    getEvidenceTier,
    EVIDENCE_TIER_LABELS,
    EVIDENCE_TIER_SHORT_LABELS,
    EVIDENCE_TIER_UPGRADE_GUIDANCE,
    type EvidenceTier,
} from './evidence_tier';
import {
    buildReviewReceiptArgs,
    buildVerifyReceiptArgs,
    buildGenerateRangeArgs,
    mapReviewOutcomeToCli,
    type ReviewSelectionValue,
} from './cli_contract';
import {
    collectChatResponseText,
    createProvableUserMessage,
    hasLanguageModelSupport,
    selectProvableChatModel,
} from './language_model_bridge';
import {
    authorshipClass,
    getAgentAttestation,
    getAIInvolvementSummary,
    getAISignalsSummary,
    getAttestedSystemSummary,
    getEditorProvenance,
    getEditorProvenanceSummary,
    hasAIInvolvement,
    hasEditorProvenance,
    isAIAuthored,
    signalCount,
} from './receipt_metadata';
import {
    verify as verifyReceipt,
    type ReceiptData,
    type VerifyResult,
} from './receipt_verifier';
import {
    buildAdvancedSettingsViewModel,
    getAdvancedSettingsHtml,
    type AdvancedSettingsViewModel,
} from './advanced_settings_panel';
import {
    getHubBillingHtml,
    getHubSignupHtml,
    getHubStatusHtml,
} from './hub_panels';
import {
    resolveHubState,
    type ResolvedHubState,
} from './hub_state';
import {
    getDetectedToolsHtml,
    getReviewHistoryHtml,
    getSigningGuideHtml,
} from './operator_static_panels';
import {
    getReceiptReviewInfo,
    getReceiptReviewStatusLabel,
    getReceiptReviewStatusSummary,
    type ReceiptReviewInfo,
} from './review_metadata';
import {
    escapeHtml,
    getPanelNavHtml,
    getPanelNavStyles,
    getPanelScript,
    renderCommandCall,
} from './panel_shared';
import { getAttestedDiffPanelHtml } from './attested_diff_panel';
import { getReceiptViewerHtml } from './receipt_viewer_panel';
import {
    buildReadinessViewModel,
    getReadinessHtml,
    type ReadinessViewModel,
} from './readiness_panel';
import {
    buildReceiptRepairPlan,
    getReceiptFailureExplanation,
    registerReceiptCommands,
    type ReceiptRepairPlan,
} from './receipt_commands';
import {
    CommitExplorerProvider,
    type CommitExplorerDeps,
    type CommitExplorerNode,
    type CommitInfo,
    type CommitFileInfo,
    type CommitReceiptOverlay,
    type CommitFileAI,
} from './commit_explorer';
import {
    CopilotListener,
    type ListenerDeps,
    type ListenerCaptureRecord,
} from './copilot_listener';
import {
    buildGovernanceDiffViewModel,
    getGovernanceDiffHtml,
    type GovernanceDiffBuildInput,
} from './governance_diff';
import { registerChatParticipant, type ChatParticipantDeps } from './chat_participant';
import { registerLanguageModelTools, type LanguageModelToolDeps } from './language_model_tools';
import { registerAIBlameDecorations, invalidateReceiptIndex } from './ai_blame_decorations';

// ── Constants ─────────────────────────────────────────────────────────
const execFileAsync = promisify(execFile);
const COMMAND_TIMEOUT_MS = 30_000;
const REQUEST_TIMEOUT_MS = 30_000;
const MANAGED_HOOK_START = '# >>> AIIR managed post-commit hook >>>';
const MANAGED_HOOK_END = '# <<< AIIR managed post-commit hook <<<';
const HUB_TOKEN_SECRET = 'aiir.hubToken';
const HUB_PRICING_URL = 'https://invariantsystems.io/pricing';
const FIRST_RUN_READINESS_KEY = 'aiir.firstRunReadinessShown.v1';
const PENDING_ACTION_KEY = 'aiir.pendingAction.v1';
const LOCK_PRESET_SETTING = 'aiir.lockPreset';
const WEBVIEW_NONCE_TOKEN = '__AIIR_WEBVIEW_NONCE__';
const WEBVIEW_ALLOWED_COMMANDS = new Set([
    'workbench.action.openSettings',
    'workbench.action.openWorkspaceSettingsFile',
]);
const provenanceQueueMutations = new Map<string, Promise<unknown>>();
const receiptGenerationMutations = new Map<string, Promise<unknown>>();
let recentWorkspaceFolderPath: string | undefined;

// ── AI Extension Detection ────────────────────────────────────────────
// Maps VS Code extension IDs to the tool name the AIIR CLI expects.
// This is how the extension closes the detection gap: editor-based AI
// tools that don't leave Co-authored-by trailers are detected here
// and reported via --agent-tool when generating receipts.
const AI_EXTENSION_MAP: ReadonlyMap<string, string> = new Map([
    ['github.copilot', 'copilot'],
    ['github.copilot-chat', 'copilot'],
    ['saoudrizwan.claude-dev', 'claude-code'],
    ['continue.continue', 'continue'],
    ['codeium.codeium', 'codeium'],
    ['amazonwebservices.amazon-q-vscode', 'amazon-q'],
    ['tabnine.tabnine-vscode', 'tabnine'],
    ['supermaven.supermaven', 'supermaven'],
    ['sourcegraph.cody-ai', 'cody'],
    ['gitlab.gitlab-workflow', 'gitlab-duo'],
    ['mistralai.codestral', 'codestral'],
    ['jetbrains.jetbrains-ai', 'jetbrains-ai'],
    ['cursor.cursor', 'cursor'],
]);

interface DetectedAITool {
    extensionId: string;
    toolName: string;
    isActive: boolean;
}

type MarketplaceCaptureSurface = 'coverage' | 'setup' | 'receipts' | 'control' | 'security' | 'presets';

type GenerateCommandId = 'aiir.generatePreferred' | 'aiir.generateReceipt' | 'aiir.initializeRepo' | 'aiir.enableAutoReceipting' | 'aiir.createWorkspacePolicy';

function createNonce(): string {
    return crypto.randomBytes(16).toString('base64');
}

function getWebviewCspMeta(cspSource: string, nonce?: string): string {
    const scriptSource = nonce ? `'nonce-${nonce}' 'unsafe-inline'` : `'none'`;
    return `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${cspSource} https: data:; style-src ${cspSource} 'unsafe-inline'; font-src ${cspSource}; script-src ${scriptSource}; base-uri 'none'; form-action 'none';">`;
}

function finalizeScriptedWebviewHtml(html: string, cspSource: string): string {
    const nonce = createNonce();
    return html
        .replace('<head>', `<head>\n    ${getWebviewCspMeta(cspSource, nonce)}`)
        .replaceAll(WEBVIEW_NONCE_TOKEN, nonce);
}

function finalizeStaticWebviewHtml(html: string, cspSource: string): string {
    return html.replace('<head>', `<head>\n    ${getWebviewCspMeta(cspSource)}`);
}

async function execFileBounded(
    executable: string,
    args: string[],
    options?: { cwd?: string; maxBuffer?: number },
): Promise<{ stdout: string; stderr: string }> {
    return await execFileAsync(executable, args, {
        ...options,
        timeout: COMMAND_TIMEOUT_MS,
    });
}

/**
 * Detect AI coding extensions installed in VS Code.
 * Returns deduplicated tool names with their activation status.
 */
function detectEditorAITools(): DetectedAITool[] {
    const detected: DetectedAITool[] = [];
    for (const [extId, toolName] of AI_EXTENSION_MAP) {
        const ext = vscode.extensions.getExtension(extId);
        if (ext) {
            detected.push({ extensionId: extId, toolName, isActive: ext.isActive });
        }
    }
    return detected;
}

/**
 * Build --agent-tool and --agent-context args from detected AI tools.
 * Returns an empty array when no active AI extensions are found.
 *
 * When multiple tools are detected, the first *active* tool is the
 * primary --agent-tool value.  Additional active tools are reported
 * via repeated --agent-tool flags so the receipt records them all.
 * Installed-but-inactive tools are omitted to avoid overstating AI involvement.
 */
function buildAgentArgs(): string[] {
    const active = detectEditorAITools().filter(t => t.isActive);
    if (active.length === 0) {
        return [];
    }
    // De-duplicate tool names while preserving order.
    const seen = new Set<string>();
    const args: string[] = [];
    for (const t of active) {
        if (!seen.has(t.toolName)) {
            seen.add(t.toolName);
            args.push('--agent-tool', t.toolName);
        }
    }
    args.push('--agent-context', 'ide:active');
    const modelHint = getAgentModelHint();
    if (modelHint) {
        args.push('--agent-model', modelHint);
    }
    return args;
}

function buildEditorProvenanceArgs(): string[] {
    return ['--editor-provenance'];
}

function canUseProvenanceGeneration(folder: vscode.WorkspaceFolder): boolean {
    if (!hasLanguageModelSupport()) {
        return false;
    }

    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.uri.scheme !== 'file') {
        return false;
    }

    return isPathInside(folder.uri.fsPath, editor.document.uri.fsPath);
}

interface CommandResult {
    stdout: string;
    stderr: string;
}

interface HealthCheckResult {
    workspaceName: string;
    cliAvailable: boolean;
    cliVersion?: string;
    gitAvailable: boolean;
    gitDir?: string;
    currentCommit?: string;
    aiirDirExists: boolean;
    ledgerExists: boolean;
    indexExists: boolean;
    policyExists: boolean;
    postCommitHook: 'managed' | 'custom' | 'missing';
    headReceiptStatus: 'present' | 'missing' | 'unknown';
    headCborStatus: 'present' | 'missing' | 'unknown';
    cborReceipts: number;
    missingCborReceipts: number;
    sigstoreReceipts: number;
    tierSigned: number;
    tierProvable: number;
    tierHeuristic: number;
    tierUnsigned: number;
    hubConfigured: boolean;
    hubConnected: boolean;
    hubAuthenticated: boolean;
    hubBaseUrl?: string;
    hubTenantId?: string;
    hubError?: string;
    mcpConfigured: boolean;
    trailerInjection: boolean;
    regulatedMode: boolean;
    lockPreset: string;
}

interface JsonRecord {
    [key: string]: unknown;
}

interface HubConnectionState {
    configured: boolean;
    connected: boolean;
    authenticated: boolean;
    tokenStored: boolean;
    baseUrl?: string;
    tenantId?: string;
    session?: JsonRecord;
    onboarding?: JsonRecord;
    error?: string;
}

type RequiredHubCapability = 'remoteReceiptSync' | 'sharedRepositories' | 'policyManagement' | 'complianceExports';

interface ReceiptArtifacts {
    cborUri?: vscode.Uri;
    sigstoreUri?: vscode.Uri;
    cborStatus: 'present' | 'missing';
    sigstoreStatus: 'present' | 'missing';
    cborSize?: number;
    cborHash?: string;
    sigstoreSize?: number;
    sigstoreHash?: string;
}

interface ReceiptRecord {
    receipt: ReceiptData;
    uri: vscode.Uri;
    result: VerifyResult;
    artifacts: ReceiptArtifacts;
    review?: ReceiptReviewInfo;
    workspaceFolderName?: string;
    workspaceFolderPath?: string;
    workspaceBranch?: string;
    workspaceHeadSha?: string;
    uiFiles?: string[];
}

interface ReceiptStats {
    total: number;
    valid: number;
    invalid: number;
    aiAuthored: number;
    cborPresent: number;
    sigstorePresent: number;
    tierSigned: number;
    tierProvable: number;
    tierHeuristic: number;
    tierUnsigned: number;
}

interface RepositoryViewState extends RepositoryViewStateSnapshot {
    folder: vscode.WorkspaceFolder;
}

interface RepositoryReceiptInfo {
    receiptCount: number;
    hasReceipts: boolean;
    headReceiptStatus: HealthCheckResult['headReceiptStatus'];
}

interface PolicyWorkspaceTargetState {
    name: string;
    path: string;
    enabled: boolean;
    matchesOpenWorkspace: boolean;
}

interface PolicyWorkspaceState {
    targets: PolicyWorkspaceTargetState[];
    enabledCount: number;
    disabledCount: number;
    currentFolderEnabled?: boolean;
}

interface HubBillingViewModel {
    networkAllowed: boolean;
    hubEnabled: boolean;
    hubConfigured: boolean;
    hubConnected: boolean;
    hubBaseUrl?: string;
    pricingUrl: string;
}

interface SecurityPostureViewModel {
    workspaceCount: number;
    accessibleWorkspaceCount: number;
    allowedWorkspaceFolders: string[];
    isolationBlockingAccess: boolean;
    enforceWorkspaceIsolation: boolean;
    strictLocalOnly: boolean;
    networkAllowed: boolean;
    hubEnabled: boolean;
    enableHubFeatures: boolean;
    cliPath: string;
    hubBaseUrl: string;
    lockPreset: string;
}

interface RolloutPresetDefinition {
    id: string;
    title: string;
    description: string;
    settings: Record<string, unknown>;
    actionLabel?: string;
    note?: string;
}

interface RolloutPresetViewModel {
    selectedWorkspaceName?: string;
    selectedWorkspaceUri?: string;
    presets: RolloutPresetDefinition[];
}

interface WorkingTreeSummary {
    staged: number;
    changed: number;
    untracked: number;
}



interface PendingAction {
    commandId: GenerateCommandId | 'aiir.disableAutoReceipting';
    label: string;
    folderPath: string;
}

interface PendingActionContinuationOptions {
    prompt?: boolean;
}

// ── Evidence Tiers ────────────────────────────────────────────────────

function getReceiptEvidenceTier(receipt: ReceiptData, artifacts: ReceiptArtifacts): EvidenceTier {
    return getEvidenceTier({
        sigstorePresent: artifacts.sigstoreStatus === 'present',
        inferenceReceiptPresent: hasInferenceBinding(receipt),
        editorProvenancePresent: hasEditorProvenance(receipt),
        aiInvolvementDetected: hasAIInvolvement(receipt),
    });
}

function hasInferenceBinding(receipt: ReceiptData): boolean {
    // Direct inference receipt: has the core inference fields
    if (receipt.model_fingerprint && receipt.tokens && receipt.granularity) {
        return true;
    }
    // Commit receipt with an inference receipt reference in extensions
    const ext = receipt.extensions as Record<string, unknown> | undefined;
    if (ext && typeof ext === 'object') {
        const ir = ext.inference_receipt as Record<string, unknown> | undefined;
        if (ir && typeof ir === 'object' && (ir.hash || ir.receipt_hash)) {
            return true;
        }
    }
    return false;
}

function isSupportedReceiptDocument(value: unknown): value is ReceiptData {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return false;
    }
    const receipt = value as ReceiptData;
    return receipt.type === 'aiir.commit_receipt' || hasInferenceBinding(receipt);
}

function getWorkspaceFolder(uri?: vscode.Uri): vscode.WorkspaceFolder | undefined {
    if (uri) {
        const folder = vscode.workspace.getWorkspaceFolder(uri);
        if (folder) {
            return folder;
        }
    }

    const activeUri = vscode.window.activeTextEditor?.document.uri;
    if (activeUri) {
        const folder = vscode.workspace.getWorkspaceFolder(activeUri);
        if (folder) {
            return folder;
        }
    }

    return vscode.workspace.workspaceFolders?.[0];
}

function resolveWorkspaceFolderFromPath(targetPath?: string): vscode.WorkspaceFolder | undefined {
    const folders = getAccessibleWorkspaceFolders();
    return resolveWorkspaceFolderTarget(
        folders.map(folder => ({ name: folder.name, fsPath: folder.uri.fsPath, value: folder })),
        targetPath,
    );
}

function rememberWorkspaceFolder(folder: vscode.WorkspaceFolder | undefined): void {
    recentWorkspaceFolderPath = folder?.uri.fsPath;
}

async function resolveCommandWorkspaceFolder(
    target: unknown,
    placeHolder: string,
): Promise<vscode.WorkspaceFolder | undefined> {
    const targetPath = resolveCommandTargetPath(target) || vscode.window.activeTextEditor?.document.uri.fsPath;
    const folders = getAccessibleWorkspaceFolders();
    const resolved = resolvePreferredWorkspaceFolderTarget(
        folders.map(folder => ({ name: folder.name, fsPath: folder.uri.fsPath, value: folder })),
        targetPath,
        recentWorkspaceFolderPath,
    );
    if (resolved) {
        rememberWorkspaceFolder(resolved);
        return resolved;
    }

    if (folders.length === 0) {
        return undefined;
    }

    const picked = await vscode.window.showQuickPick(
        folders.map(folder => ({
            label: folder.name,
            description: folder.uri.fsPath,
            folder,
        })),
        { placeHolder },
    );

    rememberWorkspaceFolder(picked?.folder);
    return picked?.folder;
}

function resolveCommandTargetPath(target: unknown): string | undefined {
    const uri = resolveTargetUri(target);
    if (uri) {
        return uri.fsPath;
    }

    if (typeof target === 'string') {
        if (/^[a-z][a-z0-9+.-]*:/i.test(target)) {
            try {
                return vscode.Uri.parse(target).fsPath;
            } catch {
                return undefined;
            }
        }
        return target;
    }

    return undefined;
}

function getCliPath(): string {
    const configured = vscode.workspace.getConfiguration('aiir').get<string>('cliPath', 'aiir').trim() || 'aiir';
    if (configured !== 'aiir') {
        return configured;
    }

    const managedCliPath = getManagedCliPath();
    return fs.existsSync(managedCliPath) ? managedCliPath : configured;
}

function getConfiguredCliPathSetting(): string {
    return vscode.workspace.getConfiguration('aiir').get<string>('cliPath', 'aiir').trim() || 'aiir';
}

function getManagedCliInstallDir(): string {
    if (process.platform === 'win32') {
        return path.join(os.homedir(), '.aiir-cli');
    }

    return path.join(os.homedir(), '.local', 'share', 'aiir-cli');
}

function getManagedCliPath(): string {
    return process.platform === 'win32'
        ? path.join(getManagedCliInstallDir(), 'Scripts', 'aiir.exe')
        : path.join(getManagedCliInstallDir(), 'bin', 'aiir');
}

function getManagedPipPath(): string {
    return process.platform === 'win32'
        ? path.join(getManagedCliInstallDir(), 'Scripts', 'pip.exe')
        : path.join(getManagedCliInstallDir(), 'bin', 'pip');
}

function getAgentModelHint(): string {
    return vscode.workspace.getConfiguration('aiir').get<string>('agentModelHint', '').trim();
}

function getAllowedWorkspaceFolderSelectors(): string[] {
    return vscode.workspace.getConfiguration('aiir').get<string[]>('allowedWorkspaceFolders', []);
}

function isWorkspaceIsolationEnabled(): boolean {
    return vscode.workspace.getConfiguration('aiir').get<boolean>('enforceWorkspaceIsolation', false);
}

function isStrictLocalOnly(): boolean {
    return vscode.workspace.getConfiguration('aiir').get<boolean>('strictLocalOnly', true);
}

function isNetworkAllowed(): boolean {
    return computeNetworkAllowed(isStrictLocalOnly());
}

function getAccessibleWorkspaceFolders(): vscode.WorkspaceFolder[] {
    const folders = vscode.workspace.workspaceFolders ?? [];
    return filterWorkspaceFolderTargets(
        folders.map(folder => ({ name: folder.name, fsPath: folder.uri.fsPath, value: folder })),
        getAllowedWorkspaceFolderSelectors(),
        isWorkspaceIsolationEnabled(),
    ).map(folder => folder.value);
}

function isWorkspaceFolderAccessible(folder: vscode.WorkspaceFolder | undefined): boolean {
    if (!folder) {
        return false;
    }

    return getAccessibleWorkspaceFolders().some(candidate => candidate.uri.fsPath === folder.uri.fsPath);
}

function isUriAccessible(uri: vscode.Uri): boolean {
    const folder = vscode.workspace.getWorkspaceFolder(uri);
    if (!folder) {
        return true;
    }

    return isWorkspaceFolderAccessible(folder);
}

function getNoAccessibleWorkspaceMessage(action: string): string {
    const workspaceCount = vscode.workspace.workspaceFolders?.length || 0;
    const isolationBlockingAccess = isWorkspaceIsolationBlockingAccess(
        workspaceCount,
        getAllowedWorkspaceFolderSelectors(),
        isWorkspaceIsolationEnabled(),
    );

    if (workspaceCount === 0 || isolationBlockingAccess) {
        return getSecurityNoAccessibleWorkspaceMessage(action, isolationBlockingAccess);
    }

    return `AIIR: A workspace is open, but AIIR could not find a usable repository folder to ${action}.`;
}

async function showWorkspaceAccessRecovery(action: string): Promise<void> {
    const workspaceCount = vscode.workspace.workspaceFolders?.length || 0;
    if (workspaceCount === 0) {
        const choice = await vscode.window.showWarningMessage(
            `AIIR: ${getNoAccessibleWorkspaceMessage(action)}`,
            'Open Getting Started',
        );
        if (choice === 'Open Getting Started') {
            await vscode.commands.executeCommand('aiir.openWalkthrough');
        }
        return;
    }

    if (isIsolationBlockingAccess()) {
        const choice = await vscode.window.showWarningMessage(
            `AIIR: ${getNoAccessibleWorkspaceMessage(action)}`,
            'Open Advanced Settings',
            'Open Security Posture',
        );
        if (choice === 'Open Advanced Settings') {
            await vscode.commands.executeCommand('aiir.advancedSettings');
        } else if (choice === 'Open Security Posture') {
            await vscode.commands.executeCommand('aiir.securityPosture');
        }
        return;
    }

    vscode.window.showErrorMessage(`AIIR: ${getNoAccessibleWorkspaceMessage(action)}`);
}

function getExplorerMessage(): string | undefined {
    return getSecurityExplorerMessage(isWorkspaceIsolationBlockingAccess(
        vscode.workspace.workspaceFolders?.length || 0,
        getAllowedWorkspaceFolderSelectors(),
        isWorkspaceIsolationEnabled(),
    ));
}

function isIsolationBlockingAccess(): boolean {
    return isWorkspaceIsolationBlockingAccess(
        vscode.workspace.workspaceFolders?.length || 0,
        getAllowedWorkspaceFolderSelectors(),
        isWorkspaceIsolationEnabled(),
    );
}

function ensureNetworkAllowed(action: string): void {
    if (isNetworkAllowed()) {
        return;
    }

    throw new Error(getNetworkBlockedMessage(action));
}

async function showNetworkAccessRecovery(action: string): Promise<void> {
    const choice = await vscode.window.showWarningMessage(
        `AIIR: ${getNetworkBlockedMessage(action)}`,
        'Open Advanced Settings',
        'Open Public Pricing',
    );
    if (choice === 'Open Advanced Settings') {
        await vscode.commands.executeCommand('aiir.advancedSettings');
    } else if (choice === 'Open Public Pricing') {
        await vscode.commands.executeCommand('aiir.openHubPricingPage');
    }
}

function getHubCapabilityLabel(requiredCapability: RequiredHubCapability): string {
    switch (requiredCapability) {
        case 'remoteReceiptSync':
            return 'remote receipt sync';
        case 'sharedRepositories':
            return 'shared repositories';
        case 'policyManagement':
            return 'policy management';
        case 'complianceExports':
            return 'compliance exports';
    }
}

async function showHubCapabilityRecovery(
    action: string,
    requirement: RequiredHubCapability | 'connection',
    resolved: ResolvedHubState,
): Promise<void> {
    const requirementLabel = requirement === 'connection'
        ? 'an active Hub connection'
        : getHubCapabilityLabel(requirement);
    const actions = [resolved.primaryActionLabel];
    if (resolved.secondaryActionLabel && resolved.secondaryActionCommandId !== resolved.primaryActionCommandId) {
        actions.push(resolved.secondaryActionLabel);
    }

    const choice = await vscode.window.showWarningMessage(
        `AIIR: ${action} needs ${requirementLabel}. Current Hub state: ${resolved.stateLabel}. ${resolved.stateDetail}`,
        ...actions,
    );
    if (choice === resolved.primaryActionLabel) {
        await vscode.commands.executeCommand(resolved.primaryActionCommandId);
    } else if (choice === resolved.secondaryActionLabel && resolved.secondaryActionCommandId) {
        await vscode.commands.executeCommand(resolved.secondaryActionCommandId);
    }
}

function getAutoReceiptArgs(): string[] {
    return vscode.workspace.getConfiguration('aiir').get<string[]>('autoReceiptArgs', ['--pretty']);
}

function getHubBaseUrl(): string {
    return vscode.workspace.getConfiguration('aiir').get<string>('hubBaseUrl', '').trim();
}

function getHubTenantId(): string {
    return vscode.workspace.getConfiguration('aiir').get<string>('hubTenantId', '').trim();
}

function getHubSignupEndpoint(): string {
    return vscode.workspace.getConfiguration('aiir').get<string>('hubSignupEndpoint', '').trim();
}

function getHubPricingUrl(): string {
    return HUB_PRICING_URL;
}

function getHostedHubSignupUrl(): string {
    const configured = getHubSignupEndpoint();
    const rawUrl = /^https?:\/\//.test(configured) ? configured : getHubPricingUrl();

    try {
        const signupUrl = new URL(rawUrl);
        signupUrl.searchParams.set('source', 'aiir-vscode-extension');
        signupUrl.searchParams.set('entry', 'vscode');
        return signupUrl.toString();
    } catch {
        return getHubPricingUrl();
    }
}

function getShowAdvancedCommands(): boolean {
    return vscode.workspace.getConfiguration('aiir').get<boolean>('showAdvancedCommands', false);
}

function getBugReportUrl(extensionVersion: string): string {
    const params = new URLSearchParams({
        title: '[VS Code] ',
        body: [
            '## Summary',
            '',
            '<!-- What happened? What did you expect? -->',
            '',
            '## Environment',
            '',
            `- AIIR VS Code extension: ${extensionVersion}`,
            `- VS Code: ${vscode.version}`,
            `- OS: ${process.platform} ${process.arch}`,
            '',
            '## Steps To Reproduce',
            '',
            '1. ',
            '2. ',
            '3. ',
            '',
            '## Notes',
            '',
            '<!-- Include screenshots or output snippets if they help. -->',
        ].join('\n'),
    });

    return `https://github.com/invariant-systems-ai/aiir/issues/new?${params.toString()}`;
}

function formatDocumentWithLineNumbers(text: string): string {
    return text
        .split(/\r?\n/)
        .map((line, index) => `${index}: ${line}`)
        .join('\n');
}

function buildProvablePrompt(
    relativePath: string,
    documentText: string,
    instruction: string,
    selection: vscode.Selection,
): string {
    const hasSelection = !selection.isEmpty;
    const scope = hasSelection
        ? `Only modify content inside the current selection in ${relativePath}.`
        : `Only modify the active file ${relativePath}.`;
    const selectionContext = hasSelection
        ? `Current selection: startLine=${selection.start.line}, startCharacter=${selection.start.character}, endLine=${selection.end.line}, endCharacter=${selection.end.character}`
        : 'No selection is active. Operate on the active file only.';
    return [
        'You are preparing a deterministic AIIR provable-mode edit plan.',
        'Return exactly one JSON object and no markdown fences.',
        'Supported operation types are replace-range and create-file.',
        'For replace-range include path, startLine, startCharacter, endLine, endCharacter, rangeText, and text.',
        'For create-file include path and text.',
        scope,
        selectionContext,
        `Instruction: ${instruction}`,
        `Active file: ${relativePath}`,
        'Current file with zero-based line numbers:',
        formatDocumentWithLineNumbers(documentText),
    ].join('\n\n');
}

function getProvableQueuePath(folder: vscode.WorkspaceFolder): string {
    return path.join(folder.uri.fsPath, '.aiir', PROVABLE_QUEUE_FILENAME);
}

function toWorkspaceRelativePath(folder: vscode.WorkspaceFolder, uri: vscode.Uri): string {
    return path.relative(folder.uri.fsPath, uri.fsPath).replace(/\\/g, '/');
}

async function ensureProvableQueueInfrastructure(folder: vscode.WorkspaceFolder, options?: {
    allowCreateAiir?: boolean;
    promptOnCreateAiir?: boolean;
}): Promise<string | undefined> {
    const aiirDir = path.join(folder.uri.fsPath, '.aiir');
    const queuePath = getProvableQueuePath(folder);
    const gitignorePath = path.join(aiirDir, '.gitignore');
    const allowCreateAiir = options?.allowCreateAiir ?? true;
    const promptOnCreateAiir = options?.promptOnCreateAiir ?? allowCreateAiir;

    if (!await pathExists(aiirDir)) {
        if (!allowCreateAiir) {
            return undefined;
        }
        if (promptOnCreateAiir) {
            const choice = await vscode.window.showInformationMessage(
                'AIIR provable mode needs local .aiir working state. Create it and ignore editor_provenance.jsonl?',
                { modal: true },
                'Continue',
                'Cancel',
            );
            if (choice !== 'Continue') {
                return undefined;
            }
        }
        await vscode.workspace.fs.createDirectory(vscode.Uri.file(aiirDir));
    }

    const ignoreEntry = 'editor_provenance.jsonl';
    const existingIgnore = await readTextFile(gitignorePath);
    if (!existingIgnore) {
        await writeTextFile(gitignorePath, `${ignoreEntry}\n`);
    } else if (!existingIgnore.split(/\r?\n/).map(line => line.trim()).includes(ignoreEntry)) {
        await writeTextFile(gitignorePath, `${existingIgnore.replace(/\s*$/, '')}\n${ignoreEntry}\n`);
    }

    if (!await pathExists(queuePath)) {
        await writeTextFile(queuePath, '');
    }

    return queuePath;
}

function summarizeProvablePlan(planSummary: string, operations: StructuredEditOperation[]): string {
    const fileCount = new Set(operations.map(operation => operation.path)).size;
    return `${planSummary} Apply ${operations.length} operation${operations.length === 1 ? '' : 's'} across ${fileCount} file${fileCount === 1 ? '' : 's'}?`;
}

async function prepareProvableOperations(
    folder: vscode.WorkspaceFolder,
    editor: vscode.TextEditor,
    operations: StructuredEditOperation[],
): Promise<Array<{ operation: StructuredEditOperation; uri: vscode.Uri; range?: vscode.Range }>> {
    const relativeActivePath = toWorkspaceRelativePath(folder, editor.document.uri);
    const selectionMode = !editor.selection.isEmpty;
    const prepared: Array<{ operation: StructuredEditOperation; uri: vscode.Uri; range?: vscode.Range }> = [];

    for (const operation of operations) {
        const normalizedPath = operation.path.replace(/\\/g, '/');
        const absolutePath = path.resolve(folder.uri.fsPath, normalizedPath);
        if (!isPathInside(folder.uri.fsPath, absolutePath)) {
            throw new Error(`Operation path escapes the workspace: ${normalizedPath}`);
        }
        const uri = vscode.Uri.file(absolutePath);

        if (operation.type === 'replace-range') {
            if (normalizedPath !== relativeActivePath) {
                throw new Error('Phase 1 only supports replace-range operations on the active file.');
            }
            if (
                operation.startLine === undefined ||
                operation.startCharacter === undefined ||
                operation.endLine === undefined ||
                operation.endCharacter === undefined ||
                operation.rangeText === undefined
            ) {
                throw new Error('replace-range operations must include a full range and rangeText.');
            }
            const range = new vscode.Range(
                new vscode.Position(operation.startLine, operation.startCharacter),
                new vscode.Position(operation.endLine, operation.endCharacter),
            );
            if (selectionMode && !editor.selection.contains(range)) {
                throw new Error('Selection mode only allows edits inside the current selection.');
            }
            const currentText = editor.document.getText(range);
            if (currentText !== operation.rangeText) {
                throw new Error('The expected rangeText does not match the current document contents.');
            }
            prepared.push({ operation, uri, range });
            continue;
        }

        if (selectionMode) {
            throw new Error('Selection mode does not allow create-file operations in Phase 1.');
        }
        if (await pathExists(uri.fsPath)) {
            throw new Error(`create-file target already exists: ${normalizedPath}`);
        }
        prepared.push({ operation, uri });
    }

    return prepared;
}

async function computeProvableFileHashes(
    folder: vscode.WorkspaceFolder,
    prepared: Array<{ operation: StructuredEditOperation }>,
): Promise<Map<string, string>> {
    const hashes = new Map<string, string>();
    for (const item of prepared) {
        const relativePath = item.operation.path.replace(/\\/g, '/');
        if (hashes.has(relativePath)) {
            continue;
        }
        const absolutePath = path.join(folder.uri.fsPath, relativePath);
        const beforeText = await pathExists(absolutePath)
            ? Buffer.from(await vscode.workspace.fs.readFile(vscode.Uri.file(absolutePath))).toString('utf-8')
            : '';
        hashes.set(relativePath, sha256Text(beforeText));
    }
    return hashes;
}

async function finalizeProvableFileHashes(
    folder: vscode.WorkspaceFolder,
    beforeHashes: Map<string, string>,
): Promise<Array<{ path: string; beforeHash: string; afterHash: string }>> {
    const files: Array<{ path: string; beforeHash: string; afterHash: string }> = [];
    for (const [relativePath, beforeHash] of beforeHashes.entries()) {
        const absolutePath = path.join(folder.uri.fsPath, relativePath);
        const afterText = await pathExists(absolutePath)
            ? Buffer.from(await vscode.workspace.fs.readFile(vscode.Uri.file(absolutePath))).toString('utf-8')
            : '';
        files.push({
            path: relativePath,
            beforeHash,
            afterHash: sha256Text(afterText),
        });
    }
    return files;
}

function getCliInstallCommand(): string {
    if (process.platform === 'win32') {
        const installDir = getManagedCliInstallDir();
        const pipPath = getManagedPipPath();
        return `py -m venv "${installDir}" && "${pipPath}" install --upgrade pip aiir`;
    }

    const installDir = shellQuote(getManagedCliInstallDir());
    const pipPath = shellQuote(getManagedPipPath());
    return `python3 -m venv ${installDir} && ${pipPath} install --upgrade pip aiir`;
}

async function copyCliInstallCommand(): Promise<void> {
    const command = getCliInstallCommand();
    await vscode.env.clipboard.writeText(command);
    vscode.window.showInformationMessage(`AIIR: Copied install command - ${command}`);
}

async function openCliInstallTerminal(): Promise<void> {
    const terminal = vscode.window.createTerminal({ name: 'AIIR Setup' });
    terminal.show();
    terminal.sendText(getCliInstallCommand(), false);
}

async function installCliNow(output: vscode.OutputChannel): Promise<string> {
    const installDir = getManagedCliInstallDir();
    const workspaceFolder = getDefaultWorkspaceFolderCandidate();
    const cwd = workspaceFolder?.uri.fsPath || os.homedir();
    const pythonExecutable = process.platform === 'win32' ? 'py' : 'python3';

    await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: 'AIIR: Installing CLI',
        cancellable: false,
    }, async progress => {
        progress.report({ message: 'Creating a dedicated user-local environment' });
        await runCommand(pythonExecutable, ['-m', 'venv', installDir], cwd, output);
        progress.report({ message: 'Installing the AIIR package' });
        await runCommand(getManagedPipPath(), ['install', '--upgrade', 'pip', 'aiir'], cwd, output);
    });

    const cliPath = getManagedCliPath();
    if (!fs.existsSync(cliPath)) {
        throw new Error(`AIIR CLI install completed without producing ${cliPath}`);
    }

    await updateAiirSetting('cliPath', cliPath);
    return cliPath;
}

async function installSigstoreSupport(output: vscode.OutputChannel): Promise<string> {
    const configuredCliPath = getConfiguredCliPathSetting();
    const managedCliPath = getManagedCliPath();

    if (configuredCliPath !== 'aiir' && configuredCliPath !== managedCliPath) {
        throw new Error('Sigstore support can only be installed automatically for the managed AIIR CLI. Reset aiir.cliPath to default or use the signing guide for your custom installation.');
    }

    const cliPath = fs.existsSync(managedCliPath)
        ? managedCliPath
        : await installCliNow(output);
    const workspaceFolder = getDefaultWorkspaceFolderCandidate();
    const cwd = workspaceFolder?.uri.fsPath || os.homedir();

    await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: 'AIIR: Installing Sigstore support',
        cancellable: false,
    }, async progress => {
        progress.report({ message: 'Installing optional signing dependencies' });
        await runCommand(getManagedPipPath(), ['install', '--upgrade', 'aiir[sigstore]'], cwd, output);
    });

    await updateAiirSetting('cliPath', cliPath);
    return cliPath;
}

function isHubEnabled(): boolean {
    return computeHubEnabled(
        isStrictLocalOnly(),
        vscode.workspace.getConfiguration('aiir').get<boolean>('enableHubFeatures', false),
    );
}

async function getAdvancedSettingsViewModel(target?: unknown): Promise<AdvancedSettingsViewModel> {
    const enableHubFeatures = vscode.workspace.getConfiguration('aiir').get<boolean>('enableHubFeatures', false);
    const candidate = getDefaultWorkspaceFolderCandidate(target);
    const policyPath = candidate ? getPolicyFilePath(candidate) : '';
    const policyState = await getWorkspacePolicyState(candidate);
    return buildAdvancedSettingsViewModel({
        selectedWorkspaceName: candidate?.name,
        selectedWorkspaceUri: candidate?.uri.toString(),
        cliPath: getCliPath(),
        agentModelHint: getAgentModelHint(),
        autoReceiptArgs: getAutoReceiptArgs(),
        enforceWorkspaceIsolation: isWorkspaceIsolationEnabled(),
        allowedWorkspaceFolders: getAllowedWorkspaceFolderSelectors(),
        strictLocalOnly: isStrictLocalOnly(),
        enableHubFeatures,
        hubEnabled: computeHubEnabled(isStrictLocalOnly(), enableHubFeatures),
        hubBaseUrl: getHubBaseUrl(),
        hubTenantId: getHubTenantId(),
        hubSignupEndpoint: getHubSignupEndpoint(),
        policyExists: policyPath ? await pathExists(policyPath) : false,
        policyPath,
        policyTargetSummary: formatPolicyTargetSummary(policyState),
        policyTargets: policyState?.targets || [],
        currentPolicyTargetLabel: formatCurrentPolicyTargetLabel(policyState),
    });
}

function getDefaultWorkspaceFolderCandidate(target?: unknown): vscode.WorkspaceFolder | undefined {
    const targetPath = resolveCommandTargetPath(target) || vscode.window.activeTextEditor?.document.uri.fsPath;
    const folders = getAccessibleWorkspaceFolders();
    return resolvePreferredWorkspaceFolderTarget(
        folders.map(folder => ({ name: folder.name, fsPath: folder.uri.fsPath, value: folder })),
        targetPath,
        recentWorkspaceFolderPath,
    ) || folders[0];
}

async function getReadinessViewModel(
    explorer: ReceiptExplorerProvider,
    output: vscode.OutputChannel,
    target?: unknown,
): Promise<ReadinessViewModel> {
    const workspaceCount = vscode.workspace.workspaceFolders?.length || 0;
    const accessibleWorkspaceCount = getAccessibleWorkspaceFolders().length;
    const selectedFolder = getDefaultWorkspaceFolderCandidate(target);
    if (selectedFolder && !explorer.getRepositoryState(selectedFolder)) {
        await explorer.refresh();
    }
    const repositoryState = selectedFolder ? explorer.getRepositoryState(selectedFolder) : undefined;
    const receiptStats = selectedFolder ? explorer.getStats(selectedFolder) : explorer.getStats();
    const health = selectedFolder ? await collectHealthCheck(selectedFolder, explorer, output) : undefined;
    const sortChecklist = <T extends { key: string; ready: boolean }>(items: readonly T[]): T[] => (
        sortSetupChecklist(items as never) as T[]
    );

    return buildReadinessViewModel({
        installCommand: getCliInstallCommand(),
        workspaceCount,
        accessibleWorkspaceCount,
        selectedWorkspaceName: selectedFolder?.name,
        selectedWorkspaceUri: selectedFolder?.uri.toString(),
        cliVersion: health?.cliVersion,
        receiptCount: receiptStats.total,
        repositoryState,
        strictLocalOnly: isStrictLocalOnly(),
        enforceWorkspaceIsolation: isWorkspaceIsolationEnabled(),
        isolationBlockingAccess: isIsolationBlockingAccess(),
        detectedAITools: detectEditorAITools().map(tool => ({
            toolName: tool.toolName,
            isActive: tool.isActive,
        })),
        sortChecklist,
    });
}

function getSecurityPostureViewModel(): SecurityPostureViewModel {
    const enableHubFeatures = vscode.workspace.getConfiguration('aiir').get<boolean>('enableHubFeatures', false);

    return {
        workspaceCount: vscode.workspace.workspaceFolders?.length || 0,
        accessibleWorkspaceCount: getAccessibleWorkspaceFolders().length,
        allowedWorkspaceFolders: getAllowedWorkspaceFolderSelectors(),
        isolationBlockingAccess: isIsolationBlockingAccess(),
        enforceWorkspaceIsolation: isWorkspaceIsolationEnabled(),
        strictLocalOnly: isStrictLocalOnly(),
        networkAllowed: isNetworkAllowed(),
        hubEnabled: computeHubEnabled(isStrictLocalOnly(), enableHubFeatures),
        enableHubFeatures,
        cliPath: getCliPath(),
        hubBaseUrl: getHubBaseUrl(),
        lockPreset: vscode.workspace.getConfiguration('aiir').get<string>('lockPreset', ''),
    };
}

function getRolloutPresetViewModel(target?: unknown): RolloutPresetViewModel {
    const candidate = getDefaultWorkspaceFolderCandidate(target);
    return {
        selectedWorkspaceName: candidate?.name,
        selectedWorkspaceUri: candidate?.uri.toString(),
        presets: getRolloutPresetDefinitions(candidate),
    };
}

function getRolloutPresetDefinitions(candidate?: vscode.WorkspaceFolder): RolloutPresetDefinition[] {
    const lockedFolder = candidate?.name || candidate?.uri.fsPath;

    return [
        {
            id: 'local-public',
            title: 'Local-Only Public Repo',
            description: 'Strict local-only mode with conservative defaults for one public repository.',
            settings: {
                'aiir.strictLocalOnly': true,
                'aiir.enableHubFeatures': false,
                'aiir.enforceWorkspaceIsolation': true,
                'aiir.allowedWorkspaceFolders': [],
            },
        },
        {
            id: 'single-dev',
            title: 'Single-Repo Developer Mode',
            description: 'Fewer multi-root constraints while keeping local-only mode enabled.',
            settings: {
                'aiir.strictLocalOnly': true,
                'aiir.enableHubFeatures': false,
                'aiir.enforceWorkspaceIsolation': false,
                'aiir.allowedWorkspaceFolders': [],
            },
        },
        {
            id: 'multi-root-locked',
            title: 'Multi-Root Locked-Down Mode',
            description: 'Constrain discovery to the currently selected repository and keep all network-backed commands blocked.',
            settings: {
                'aiir.strictLocalOnly': true,
                'aiir.enableHubFeatures': false,
                'aiir.enforceWorkspaceIsolation': true,
                'aiir.allowedWorkspaceFolders': lockedFolder ? [lockedFolder] : [],
            },
        },
        {
            id: 'ci-sign-when-supported',
            title: 'CI Signing When Supported',
            description: 'Keep local provenance-first defaults in VS Code, and guide CI or release jobs toward Sigstore signing when ambient OIDC credentials and the optional sigstore package are available. Signed receipts are the minimum evidence tier for formal compliance use.',
            settings: {},
            actionLabel: 'Open Guidance',
            note: 'This preset does not change local workspace settings. It opens public guidance for CI and release signing workflows.',
        },
        {
            id: 'hub-eval',
            title: 'Hub Evaluation Mode',
            description: 'Keep isolation in place while allowing public Hub connection and evaluation flows.',
            settings: {
                'aiir.strictLocalOnly': false,
                'aiir.enableHubFeatures': false,
                'aiir.enforceWorkspaceIsolation': true,
                'aiir.allowedWorkspaceFolders': lockedFolder ? [lockedFolder] : [],
            },
        },
    ];
}

function shellQuote(value: string): string {
    return `'${value.replace(/'/g, `'"'"'`)}'`;
}

function trimOutput(value?: string): string {
    return value?.trim() || '';
}

/**
 * Lightweight glob matching without external dependencies.
 * Supports **, *, and ? patterns.  Used by the passive AI edit listener
 * to filter excluded paths.
 */
function minimatchLite(filePath: string, pattern: string): boolean {
    const regexBody = pattern
        .replace(/[.+^${}()|[\]\\]/g, '\\$&')
        .replace(/\*\*/g, '\u0000')
        .replace(/\*/g, '[^/]*')
        .replace(/\u0000/g, '.*')
        .replace(/\?/g, '[^/]');
    return new RegExp(`^${regexBody}$`).test(filePath);
}

function joinUrl(baseUrl: string, requestPath: string): string {
    const trimmed = baseUrl.trim();
    if (!trimmed) {
        return requestPath;
    }
    return trimmed.endsWith('/')
        ? `${trimmed.slice(0, -1)}${requestPath}`
        : `${trimmed}${requestPath}`;
}

function asJsonRecord(value: unknown): JsonRecord {
    return (value && typeof value === 'object' && !Array.isArray(value)) ? value as JsonRecord : {};
}

async function pathExists(filePath: string): Promise<boolean> {
    try {
        await vscode.workspace.fs.stat(vscode.Uri.file(filePath));
        return true;
    } catch {
        return false;
    }
}

async function readTextFile(filePath: string): Promise<string | undefined> {
    try {
        const bytes = await vscode.workspace.fs.readFile(vscode.Uri.file(filePath));
        return Buffer.from(bytes).toString('utf-8');
    } catch {
        return undefined;
    }
}

async function writeTextFile(filePath: string, content: string): Promise<void> {
    await vscode.workspace.fs.writeFile(vscode.Uri.file(filePath), Buffer.from(content, 'utf-8'));
}

function getPolicyFilePath(folder: vscode.WorkspaceFolder): string {
    return path.join(folder.uri.fsPath, '.aiir', 'policy.json');
}

function buildWorkspacePolicyTargets(folders: vscode.WorkspaceFolder[]): Array<Record<string, unknown>> {
    return folders.map(folder => ({
        name: folder.name,
        path: folder.uri.fsPath,
        enabled: true,
    }));
}

function normalizeWorkspaceSelectors(selectors: string[]): string[] {
    const seen = new Set<string>();
    const normalized: string[] = [];

    for (const selector of selectors) {
        const value = selector.trim();
        if (!value || seen.has(value)) {
            continue;
        }
        seen.add(value);
        normalized.push(value);
    }

    return normalized;
}

async function applySafeWorkspaceSettings(
    targetFolders: vscode.WorkspaceFolder[],
    options?: { replaceAllowedFolders?: boolean },
): Promise<string[]> {
    const targetSelectors = normalizeWorkspaceSelectors(targetFolders.map(folder => folder.uri.fsPath));
    const nextAllowedFolders = options?.replaceAllowedFolders
        ? targetSelectors
        : normalizeWorkspaceSelectors([...getAllowedWorkspaceFolderSelectors(), ...targetSelectors]);

    await updateAiirSetting('strictLocalOnly', true);
    await updateAiirSetting('enforceWorkspaceIsolation', true);
    await updateAiirSetting('allowedWorkspaceFolders', nextAllowedFolders);

    return nextAllowedFolders;
}

async function getWorkspacePolicyState(folder: vscode.WorkspaceFolder | undefined): Promise<PolicyWorkspaceState | undefined> {
    if (!folder) {
        return undefined;
    }

    const policyPath = getPolicyFilePath(folder);
    const raw = await readTextFile(policyPath);
    if (!raw) {
        return undefined;
    }

    try {
        const parsed = asJsonRecord(JSON.parse(raw));
        const extensions = asJsonRecord(parsed.extensions);
        const vscodePolicy = asJsonRecord(extensions.vscode);
        const rawTargets = Array.isArray(vscodePolicy.workspace_targets) ? vscodePolicy.workspace_targets : [];
        const openFolders = vscode.workspace.workspaceFolders ?? [];

        const targets = rawTargets
            .map(candidate => asJsonRecord(candidate))
            .map(candidate => {
                const name = typeof candidate.name === 'string' ? candidate.name : '';
                const targetPath = typeof candidate.path === 'string' ? candidate.path : '';
                const enabled = candidate.enabled !== false;
                const matchesOpenWorkspace = openFolders.some(openFolder =>
                    (name && openFolder.name === name) || (targetPath && openFolder.uri.fsPath === targetPath),
                );
                return {
                    name,
                    path: targetPath,
                    enabled,
                    matchesOpenWorkspace,
                } satisfies PolicyWorkspaceTargetState;
            })
            .filter(target => target.name || target.path);

        const currentTarget = targets.find(target =>
            target.path === folder.uri.fsPath || (target.name && target.name === folder.name),
        );

        return {
            targets,
            enabledCount: targets.filter(target => target.enabled).length,
            disabledCount: targets.filter(target => !target.enabled).length,
            currentFolderEnabled: currentTarget?.enabled,
        };
    } catch {
        return undefined;
    }
}

function formatPolicyTargetSummary(policyState: PolicyWorkspaceState | undefined): string {
    if (!policyState || policyState.targets.length === 0) {
        return 'No workspace target list';
    }

    return `${policyState.enabledCount} enabled • ${policyState.disabledCount} disabled`;
}

function formatCurrentPolicyTargetLabel(policyState: PolicyWorkspaceState | undefined): string {
    if (!policyState || policyState.targets.length === 0) {
        return 'No workspace target rule';
    }
    if (policyState.currentFolderEnabled === false) {
        return 'Disabled in policy file';
    }
    if (policyState.currentFolderEnabled === true) {
        return 'Enabled in policy file';
    }
    return 'Not listed in policy targets';
}

function getCurrentPolicyToggleAction(
    policyState: PolicyWorkspaceState | undefined,
): {
    label: string;
    description: string;
    commandId: string;
    iconId: string;
} {
    if (policyState?.currentFolderEnabled === false) {
        return {
            label: 'Enable Current Repo',
            description: 'Add this repository back into the active workspace policy',
            commandId: 'aiir.toggleCurrentPolicyTarget',
            iconId: 'check',
        };
    }

    return {
        label: 'Disable Current Repo',
        description: 'Turn this repository off in the active workspace policy',
        commandId: 'aiir.toggleCurrentPolicyTarget',
        iconId: 'circle-slash',
    };
}

function getPolicyTargetKey(target: { name: string; path: string }): string {
    return target.path || `name:${target.name}`;
}

function buildEditablePolicyTargets(
    policyState: PolicyWorkspaceState | undefined,
    openFolders: vscode.WorkspaceFolder[],
): PolicyWorkspaceTargetState[] {
    const targetMap = new Map<string, PolicyWorkspaceTargetState>();

    for (const target of policyState?.targets || []) {
        targetMap.set(getPolicyTargetKey(target), target);
    }

    for (const folder of openFolders) {
        const key = getPolicyTargetKey({ name: folder.name, path: folder.uri.fsPath });
        const existing = targetMap.get(key);
        targetMap.set(key, {
            name: folder.name,
            path: folder.uri.fsPath,
            enabled: existing?.enabled ?? true,
            matchesOpenWorkspace: true,
        });
    }

    return Array.from(targetMap.values()).sort((left, right) => {
        if (left.matchesOpenWorkspace !== right.matchesOpenWorkspace) {
            return left.matchesOpenWorkspace ? -1 : 1;
        }
        return (left.name || left.path).localeCompare(right.name || right.path);
    });
}

async function updateWorkspacePolicyTargets(
    folder: vscode.WorkspaceFolder,
    targets: PolicyWorkspaceTargetState[],
): Promise<void> {
    const policyPath = getPolicyFilePath(folder);
    const raw = await readTextFile(policyPath);
    const parsed = raw ? asJsonRecord(JSON.parse(raw)) : {};
    const extensions = asJsonRecord(parsed.extensions);
    const vscodePolicy = asJsonRecord(extensions.vscode);

    const nextPolicy: Record<string, unknown> = {
        ...parsed,
        extensions: {
            ...extensions,
            vscode: {
                ...vscodePolicy,
                workspace_targets: targets.map(target => ({
                    name: target.name,
                    path: target.path,
                    enabled: target.enabled,
                })),
                workspace_count: targets.length,
                multi_root_window: targets.length > 1,
                last_updated_by: 'aiir-vscode',
            },
        },
    };

    await writeTextFile(policyPath, JSON.stringify(nextPolicy, null, 2) + '\n');
}

async function ensureWorkspaceBaselinePolicy(
    folder: vscode.WorkspaceFolder,
    allFolders: vscode.WorkspaceFolder[],
    preset: 'balanced' | 'strict' | 'permissive' = 'balanced',
): Promise<string> {
    const policyPath = getPolicyFilePath(folder);
    const raw = await readTextFile(policyPath);
    const parsed = raw ? asJsonRecord(JSON.parse(raw)) : {};
    const extensions = asJsonRecord(parsed.extensions);
    const vscodePolicy = asJsonRecord(extensions.vscode);

    const nextPolicy: Record<string, unknown> = {
        ...parsed,
        preset: typeof parsed.preset === 'string' ? parsed.preset : preset,
        extensions: {
            ...extensions,
            vscode: {
                ...vscodePolicy,
                workspace_targets: buildWorkspacePolicyTargets(allFolders),
                workspace_count: allFolders.length,
                multi_root_window: allFolders.length > 1,
                last_updated_by: 'aiir-vscode',
            },
        },
    };

    await writeTextFile(policyPath, JSON.stringify(nextPolicy, null, 2) + '\n');
    return policyPath;
}

async function initializeWorkspaceFolder(
    folder: vscode.WorkspaceFolder,
    output: vscode.OutputChannel,
    policyPreset?: 'balanced' | 'strict' | 'permissive',
    baselineFolders?: vscode.WorkspaceFolder[],
): Promise<string | undefined> {
    const args = ['--init'];
    if (policyPreset) {
        args.push('--policy', policyPreset);
    }

    await runCommand(getCliPath(), args, folder.uri.fsPath, output);
    await ensureProvableQueueInfrastructure(folder, { allowCreateAiir: false, promptOnCreateAiir: false });

    if (baselineFolders && baselineFolders.length > 0) {
        return ensureWorkspaceBaselinePolicy(folder, baselineFolders, policyPreset || 'balanced');
    }

    return undefined;
}

async function createOrEnsureWorkspacePolicy(
    folder: vscode.WorkspaceFolder,
    output: vscode.OutputChannel,
    preset: 'balanced' | 'strict' | 'permissive' = 'balanced',
    baselineFolders?: vscode.WorkspaceFolder[],
): Promise<string> {
    const policyPath = getPolicyFilePath(folder);
    if (await pathExists(policyPath)) {
        if (baselineFolders && baselineFolders.length > 0) {
            await ensureWorkspaceBaselinePolicy(folder, baselineFolders, preset);
        }
        return policyPath;
    }

    const aiirDirExists = await pathExists(path.join(folder.uri.fsPath, '.aiir'));
    if (aiirDirExists) {
        await runCommand(getCliPath(), ['--policy-init', preset], folder.uri.fsPath, output);
        if (baselineFolders && baselineFolders.length > 0) {
            await ensureWorkspaceBaselinePolicy(folder, baselineFolders, preset);
        }
        return policyPath;
    }

    await initializeWorkspaceFolder(folder, output, preset, baselineFolders);
    return policyPath;
}

async function editWorkspacePolicyTargets(folder: vscode.WorkspaceFolder): Promise<boolean> {
    const policyState = await getWorkspacePolicyState(folder);
    const editableTargets = buildEditablePolicyTargets(policyState, getAccessibleWorkspaceFolders());

    const picks = await vscode.window.showQuickPick(
        editableTargets.map(target => ({
            label: target.name || target.path,
            description: target.matchesOpenWorkspace ? 'open in this window' : 'from policy file',
            detail: target.path,
            picked: target.enabled,
            target,
        })),
        {
            canPickMany: true,
            placeHolder: 'Select the repositories that should stay enabled in this workspace policy',
        },
    );

    if (!picks) {
        return false;
    }

    const enabledKeys = new Set(picks.map(pick => getPolicyTargetKey(pick.target)));
    const nextTargets = editableTargets.map(target => ({
        ...target,
        enabled: enabledKeys.has(getPolicyTargetKey(target)),
    }));

    await updateWorkspacePolicyTargets(folder, nextTargets);
    return true;
}

async function hasAiirGitHubActionWorkflow(folder: vscode.WorkspaceFolder): Promise<boolean> {
    const workflowsDir = path.join(folder.uri.fsPath, '.github', 'workflows');
    if (!await pathExists(workflowsDir)) {
        return false;
    }

    try {
        const entries = await vscode.workspace.fs.readDirectory(vscode.Uri.file(workflowsDir));
        for (const [name, kind] of entries) {
            if (kind !== vscode.FileType.File || !/\.ya?ml$/i.test(name)) {
                continue;
            }

            const content = await readTextFile(path.join(workflowsDir, name));
            if (content && /uses:\s*invariant-systems-ai\/aiir@/i.test(content)) {
                return true;
            }
        }
    } catch {
        return false;
    }

    return false;
}

async function runCommand(
    executable: string,
    args: string[],
    cwd: string,
    output: vscode.OutputChannel,
): Promise<CommandResult> {
    output.appendLine(`$ (${path.basename(cwd)}) ${executable} ${args.join(' ')}`.trimEnd());
    const { stdout, stderr } = await execFileBounded(executable, args, {
        cwd,
        maxBuffer: 10 * 1024 * 1024,
    });

    if (stdout) {
        output.appendLine(stdout.trimEnd());
    }
    if (stderr) {
        output.appendLine(stderr.trimEnd());
    }

    return { stdout: trimOutput(stdout), stderr: trimOutput(stderr) };
}

async function runJsonCommand(
    executable: string,
    args: string[],
    cwd: string,
    output: vscode.OutputChannel,
): Promise<JsonRecord> {
    const result = await runCommand(executable, args, cwd, output);
    if (!result.stdout) {
        throw new Error(`AIIR CLI returned no JSON for ${args.join(' ')}`);
    }

    return asJsonRecord(JSON.parse(result.stdout));
}

async function requestJson(
    baseUrl: string,
    requestPath: string,
    token: string,
    output: vscode.OutputChannel,
    init?: RequestInit,
): Promise<JsonRecord> {
    const url = joinUrl(baseUrl, requestPath);
    output.appendLine(`HTTP ${init?.method || 'GET'} ${url}`);

    const headers = new Headers(init?.headers);
    headers.set('Accept', 'application/json');
    if (init?.body) {
        headers.set('Content-Type', 'application/json');
    }
    if (token.trim()) {
        headers.set('Authorization', `Bearer ${token.trim()}`);
    }

    const controller = new AbortController();
    const upstreamSignal = init?.signal;
    if (upstreamSignal?.aborted) {
        controller.abort();
    }

    const abortFromUpstream = () => controller.abort();
    upstreamSignal?.addEventListener('abort', abortFromUpstream, { once: true });
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    let response: Response;
    try {
        response = await fetch(url, {
            ...init,
            headers,
            signal: controller.signal,
        });
    } catch (error) {
        if (controller.signal.aborted) {
            throw new Error(`Request timed out after ${REQUEST_TIMEOUT_MS}ms`);
        }
        throw error;
    } finally {
        clearTimeout(timeout);
        upstreamSignal?.removeEventListener('abort', abortFromUpstream);
    }

    const text = await response.text();
    let payload: JsonRecord = {};
    try {
        payload = text ? asJsonRecord(JSON.parse(text)) : {};
    } catch {
        payload = { raw: text };
    }

    if (!response.ok) {
        const detail = typeof payload.detail === 'string'
            ? payload.detail
            : (typeof payload.error === 'string' ? payload.error : response.statusText);
        throw new Error(`${response.status} ${detail}`);
    }

    return payload;
}

function areSettingValuesEqual(left: unknown, right: unknown): boolean {
    return JSON.stringify(left) === JSON.stringify(right);
}

function toAiirSettingKey(key: string): string {
    return key.startsWith('aiir.') ? key : `aiir.${key}`;
}

function toAiirSettingLeaf(key: string): string {
    return key.replace(/^aiir\./, '');
}

async function runWithProvenanceQueueLock<T>(queuePath: string, operation: () => Promise<T>): Promise<T> {
    const previous = provenanceQueueMutations.get(queuePath) ?? Promise.resolve();
    const current = previous.catch(() => undefined).then(operation);
    provenanceQueueMutations.set(queuePath, current);

    try {
        return await current;
    } finally {
        if (provenanceQueueMutations.get(queuePath) === current) {
            provenanceQueueMutations.delete(queuePath);
        }
    }
}

async function runWithReceiptGenerationLock<T>(
    folderPath: string,
    output: vscode.OutputChannel,
    operation: () => Promise<T>,
): Promise<T> {
    const previous = receiptGenerationMutations.get(folderPath);
    if (previous) {
        output.appendLine(`AIIR: Receipt generation already in progress for ${path.basename(folderPath)}. Waiting for the active run to finish.`);
    }

    const current = (previous ?? Promise.resolve())
        .catch(() => undefined)
        .then(operation);
    receiptGenerationMutations.set(folderPath, current);

    try {
        return await current;
    } finally {
        if (receiptGenerationMutations.get(folderPath) === current) {
            receiptGenerationMutations.delete(folderPath);
        }
    }
}

function getActiveLockPreset(): RolloutPresetDefinition | undefined {
    const lockPreset = vscode.workspace.getConfiguration('aiir').get<string>('lockPreset', '').trim();
    if (lockPreset === '') {
        return undefined;
    }

    return getRolloutPresetDefinitions().find(entry => entry.id === lockPreset);
}

function getLockedPresetSetting(key: string): { preset: RolloutPresetDefinition; expectedValue: unknown } | undefined {
    const preset = getActiveLockPreset();
    if (!preset) {
        return undefined;
    }

    const normalizedKey = toAiirSettingKey(key);
    if (!Object.prototype.hasOwnProperty.call(preset.settings, normalizedKey)) {
        return undefined;
    }

    return {
        preset,
        expectedValue: preset.settings[normalizedKey],
    };
}

async function enforceLockedPresetSettings(event?: vscode.ConfigurationChangeEvent): Promise<string[]> {
    const preset = getActiveLockPreset();
    if (!preset) {
        return [];
    }

    const config = vscode.workspace.getConfiguration('aiir');
    const lockPresetChanged = event?.affectsConfiguration('aiir.lockPreset') || false;
    const coveredKeys = Object.keys(preset.settings);
    const relevantCoveredChange = !event || lockPresetChanged || coveredKeys.some(fullKey => event.affectsConfiguration(fullKey));
    if (!relevantCoveredChange) {
        return [];
    }

    const revertedKeys: string[] = [];
    for (const [fullKey, expectedValue] of Object.entries(preset.settings)) {
        const leafKey = toAiirSettingLeaf(fullKey);
        const actualValue = config.get<unknown>(leafKey);
        if (areSettingValuesEqual(actualValue, expectedValue)) {
            continue;
        }

        await updateAiirSetting(leafKey, expectedValue, { ignoreLockPreset: true });
        revertedKeys.push(fullKey);
    }

    return revertedKeys;
}

async function updateAiirSetting<T>(key: string, value: T, options?: { ignoreLockPreset?: boolean }): Promise<void> {
    if (!options?.ignoreLockPreset) {
        const lockedSetting = getLockedPresetSetting(key);
        if (lockedSetting && !areSettingValuesEqual(value, lockedSetting.expectedValue)) {
            throw new Error(
                `Setting '${toAiirSettingKey(key)}' is locked by preset '${lockedSetting.preset.title}'. Clear ${LOCK_PRESET_SETTING} to change it.`,
            );
        }
    }

    await vscode.workspace.getConfiguration('aiir').update(key, value, vscode.ConfigurationTarget.Workspace);
}

async function getHubToken(context: vscode.ExtensionContext): Promise<string> {
    return (await context.secrets.get(HUB_TOKEN_SECRET)) || '';
}

async function setHubToken(context: vscode.ExtensionContext, token: string): Promise<void> {
    await context.secrets.store(HUB_TOKEN_SECRET, token.trim());
}

async function deleteHubToken(context: vscode.ExtensionContext): Promise<void> {
    await context.secrets.delete(HUB_TOKEN_SECRET);
}

async function getHubConnectionState(
    context: vscode.ExtensionContext,
    output: vscode.OutputChannel,
): Promise<HubConnectionState> {
    if (!isNetworkAllowed()) {
        return {
            configured: false,
            connected: false,
            authenticated: false,
            tokenStored: !!(await getHubToken(context)),
        };
    }

    const baseUrl = getHubBaseUrl();
    const tenantId = getHubTenantId();
    const token = await getHubToken(context);

    if (!baseUrl) {
        return {
            configured: false,
            connected: false,
            authenticated: false,
            tokenStored: !!token,
        };
    }

    try {
        const session = await requestJson(baseUrl, '/api/portal/session', token, output);
        const onboarding = tenantId
            ? await requestJson(
                baseUrl,
                `/api/portal/tenants/${encodeURIComponent(tenantId)}/onboarding/status`,
                token,
                output,
            )
            : undefined;

        return {
            configured: true,
            connected: true,
            authenticated: !!token,
            tokenStored: !!token,
            baseUrl,
            tenantId: tenantId || undefined,
            session,
            onboarding,
        };
    } catch (error) {
        return {
            configured: true,
            connected: false,
            authenticated: !!token,
            tokenStored: !!token,
            baseUrl,
            tenantId: tenantId || undefined,
            error: (error as Error).message,
        };
    }
}

async function getResolvedHubState(
    context: vscode.ExtensionContext,
    output: vscode.OutputChannel,
): Promise<{ connection: HubConnectionState; resolved: ResolvedHubState }> {
    const connection = await getHubConnectionState(context, output);
    return {
        connection,
        resolved: resolveHubState(connection, {
            networkAllowed: isNetworkAllowed(),
            hubEnabled: isHubEnabled(),
        }),
    };
}

async function ensureHubConfigured(
    context: vscode.ExtensionContext,
    output: vscode.OutputChannel,
    options: {
        action: string;
        requiredCapability?: RequiredHubCapability;
        requireTenant?: boolean;
    },
): Promise<{ baseUrl: string; tenantId?: string; token: string; resolved: ResolvedHubState } | undefined> {
    try {
        ensureNetworkAllowed(options.action);
    } catch {
        await showNetworkAccessRecovery(options.action);
        return undefined;
    }

    const { connection, resolved } = await getResolvedHubState(context, output);
    if (!connection.configured || !connection.connected || !connection.authenticated) {
        await showHubCapabilityRecovery(options.action, 'connection', resolved);
        return undefined;
    }

    if (options.requiredCapability && !resolved.capabilities[options.requiredCapability]) {
        await showHubCapabilityRecovery(options.action, options.requiredCapability, resolved);
        return undefined;
    }

    const baseUrl = getHubBaseUrl();
    const tenantId = getHubTenantId();
    const token = await getHubToken(context);

    if (!baseUrl) {
        await showHubCapabilityRecovery(options.action, 'connection', resolved);
        return undefined;
    }
    if (options.requireTenant && !tenantId) {
        await showHubCapabilityRecovery(options.action, 'connection', resolved);
        return undefined;
    }
    if (!token) {
        await showHubCapabilityRecovery(options.action, 'connection', resolved);
        return undefined;
    }

    output.appendLine(`Hub configured for ${baseUrl}${tenantId ? ` (tenant ${tenantId})` : ''}`);
    return { baseUrl, tenantId: tenantId || undefined, token, resolved };
}

async function showJsonPanel(title: string, payload: JsonRecord): Promise<void> {
    const panel = vscode.window.createWebviewPanel(title.toLowerCase().replace(/\s+/g, '.'), title, vscode.ViewColumn.One, {
        enableScripts: false,
    });
    panel.webview.html = finalizeStaticWebviewHtml(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  <style>
    body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 20px; }
    pre { white-space: pre-wrap; word-break: break-word; background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 8px; padding: 16px; }
  </style>
</head>
<body>
  <h1>${title}</h1>
  <pre>${escapeHtml(JSON.stringify(payload, null, 2))}</pre>
</body>
</html>`, panel.webview.cspSource);
}

async function resolveGitDir(folder: vscode.WorkspaceFolder, output?: vscode.OutputChannel): Promise<string | undefined> {
    try {
        const { stdout, stderr } = await execFileBounded('git', ['rev-parse', '--git-dir'], {
            cwd: folder.uri.fsPath,
            maxBuffer: 1024 * 1024,
        });

        if (output && stderr) {
            output.appendLine(stderr.trimEnd());
        }

        const gitDir = trimOutput(stdout);
        if (!gitDir) {
            return undefined;
        }

        return path.isAbsolute(gitDir)
            ? gitDir
            : path.resolve(folder.uri.fsPath, gitDir);
    } catch {
        return undefined;
    }
}

async function getCurrentCommitSha(folder: vscode.WorkspaceFolder): Promise<string | undefined> {
    try {
        const { stdout } = await execFileBounded('git', ['rev-parse', 'HEAD'], {
            cwd: folder.uri.fsPath,
            maxBuffer: 1024 * 1024,
        });
        return trimOutput(stdout) || undefined;
    } catch {
        return undefined;
    }
}

async function getCurrentBranchName(folder: vscode.WorkspaceFolder): Promise<string | undefined> {
    try {
        const { stdout } = await execFileBounded('git', ['rev-parse', '--abbrev-ref', 'HEAD'], {
            cwd: folder.uri.fsPath,
            maxBuffer: 1024 * 1024,
        });
        const branch = trimOutput(stdout);
        return branch || undefined;
    } catch {
        return undefined;
    }
}

async function materializeReceiptForCli(record: ReceiptRecord): Promise<string> {
    const ledgerSuffix = `${path.sep}.aiir${path.sep}receipts.jsonl`;
    if (!record.uri.fsPath.endsWith(ledgerSuffix)) {
        return record.uri.fsPath;
    }

    const commitShort = (record.receipt.commit?.sha || 'receipt').slice(0, 12).replace(/[^a-zA-Z0-9_-]/g, '_');
    const hashShort = (record.receipt.content_hash || 'content').replace(/[^a-fA-F0-9]/g, '').slice(0, 16) || 'content';
    const tempDir = path.join(os.tmpdir(), 'aiir-vscode');
    const filePath = path.join(tempDir, `receipt_${commitShort}_${hashShort}.json`);

    await fs.promises.mkdir(tempDir, { recursive: true });
    await fs.promises.writeFile(filePath, JSON.stringify(record.receipt, null, 2) + '\n', 'utf-8');

    return filePath;
}

async function getCommitFilesFromGit(folder: vscode.WorkspaceFolder, commitSha: string): Promise<string[]> {
    try {
        const { stdout } = await execFileBounded('git', ['show', '--pretty=format:', '--name-only', commitSha], {
            cwd: folder.uri.fsPath,
            maxBuffer: 1024 * 1024,
        });

        return trimOutput(stdout)
            .split(/\r?\n/)
            .map(line => line.trim())
            .filter(Boolean);
    } catch {
        return [];
    }
}

async function getWorkingTreeSummary(folder: vscode.WorkspaceFolder): Promise<WorkingTreeSummary> {
    try {
        const { stdout } = await execFileBounded('git', ['status', '--porcelain'], {
            cwd: folder.uri.fsPath,
            maxBuffer: 1024 * 1024,
        });

        const summary: WorkingTreeSummary = { staged: 0, changed: 0, untracked: 0 };
        for (const line of trimOutput(stdout).split(/\r?\n/)) {
            if (!line) {
                continue;
            }
            if (line.startsWith('??')) {
                summary.untracked += 1;
                continue;
            }

            const indexStatus = line[0];
            const workTreeStatus = line[1];
            if (indexStatus && indexStatus !== ' ') {
                summary.staged += 1;
            }
            if (workTreeStatus && workTreeStatus !== ' ') {
                summary.changed += 1;
            }
        }

        return summary;
    } catch {
        return { staged: 0, changed: 0, untracked: 0 };
    }
}

function formatWorkingTreeSummary(summary: WorkingTreeSummary): string {
    if (summary.staged === 0 && summary.changed === 0 && summary.untracked === 0) {
        return 'Clean working tree';
    }

    return `${summary.staged} staged • ${summary.changed} changed • ${summary.untracked} untracked`;
}

async function getPostCommitHookKind(folder: vscode.WorkspaceFolder): Promise<HealthCheckResult['postCommitHook']> {
    const gitDir = await resolveGitDir(folder);
    if (!gitDir) {
        return 'missing';
    }

    const hookPath = path.join(gitDir, 'hooks', 'post-commit');
    const hookContents = await readTextFile(hookPath);
    if (!hookContents) {
        return 'missing';
    }

    return hookContents.includes(MANAGED_HOOK_START) ? 'managed' : 'custom';
}

function formatHeadReceiptState(kind: HealthCheckResult['headReceiptStatus']): string {
    if (kind === 'present') {
        return 'HEAD recorded';
    }
    if (kind === 'missing') {
        return 'HEAD missing proof';
    }
    return 'HEAD proof unknown';
}

async function isCliAvailable(folder: vscode.WorkspaceFolder): Promise<boolean> {
    try {
        await execFileBounded(getCliPath(), ['--version'], {
            cwd: folder.uri.fsPath,
            maxBuffer: 1024 * 1024,
        });
        return true;
    } catch {
        return false;
    }
}

async function resolveRepositoryViewState(
    folder: vscode.WorkspaceFolder,
    receiptInfo: RepositoryReceiptInfo,
): Promise<RepositoryViewState> {
    const activeAITool = detectEditorAITools().find(tool => tool.isActive);
    const aiirDir = path.join(folder.uri.fsPath, '.aiir');
    const policyPath = path.join(aiirDir, 'policy.json');
    const [gitDir, branch, headSha, cliAvailable, aiirDirExists, hasLedger, policyExists, provenanceQueueExists] = await Promise.all([
        resolveGitDir(folder),
        getCurrentBranchName(folder),
        getCurrentCommitSha(folder),
        isCliAvailable(folder),
        pathExists(aiirDir),
        pathExists(path.join(aiirDir, 'receipts.jsonl')),
        pathExists(policyPath),
        pathExists(getProvableQueuePath(folder)),
    ]);

    let hookState: HealthCheckResult['postCommitHook'] = 'missing';
    if (gitDir) {
        const hookPath = path.join(gitDir, 'hooks', 'post-commit');
        const hookContents = await readTextFile(hookPath);
        if (hookContents) {
            hookState = hookContents.includes(MANAGED_HOOK_START) ? 'managed' : 'custom';
        }
    }

    return {
        folder,
        ...resolveRepositoryViewStateSnapshot({
            gitAvailable: !!gitDir,
            branch,
            headSha,
            cliAvailable,
            aiirDirExists,
            hasLedger,
            policyExists,
            hookState,
            provenanceQueueExists,
            receiptCount: receiptInfo.receiptCount,
            hasReceipts: receiptInfo.hasReceipts,
            headReceiptStatus: receiptInfo.headReceiptStatus,
            activeAIToolName: activeAITool?.toolName,
        }),
    };
}

async function getResolvedTrustState(
    explorer: ReceiptExplorerProvider,
    target?: unknown,
): Promise<ResolvedTrustState> {
    const workspaceOpen = (vscode.workspace.workspaceFolders?.length || 0) > 0;
    const accessBlocked = isIsolationBlockingAccess();
    const folderCount = vscode.workspace.workspaceFolders?.length || 0;
    const folder = getDefaultWorkspaceFolderCandidate(target);

    if (!workspaceOpen || !folder) {
        return resolveTrustState({
            workspaceOpen,
            accessBlocked,
            repoName: folder?.name,
            branch: undefined,
            folderCount,
            receiptCount: 0,
            invalidReceiptCount: 0,
            cliAvailable: false,
            repoInitialized: false,
            headReceiptStatus: 'unknown',
        });
    }

    let repositoryState = explorer.getRepositoryState(folder);
    if (!repositoryState) {
        await explorer.refresh();
        repositoryState = explorer.getRepositoryState(folder);
    }
    const stats = explorer.getStats(folder);
    const latestReceipt = explorer.getLatestReceipt(folder);
    const headSha = repositoryState?.headSha;
    const hookKind = repositoryState?.hookState;
    const cliAvailable = repositoryState?.cliAvailable ?? false;
    const repoInitialized = repositoryState?.aiirDirExists ?? false;
    const headReceiptStatus = repositoryState?.headReceiptStatus ?? 'unknown';

    const regulatedMode = vscode.workspace.getConfiguration('aiir').get<boolean>('regulatedMode', false);
    const headRecord = headSha ? explorer.getReceiptForCommit(headSha, folder) : undefined;
    const currentEvidenceTier = headRecord
        ? getReceiptEvidenceTier(headRecord.receipt, headRecord.artifacts)
        : undefined;
    const policyEnabled = repositoryState?.policyExists ?? false;

    return resolveTrustState({
        workspaceOpen,
        accessBlocked,
        repoName: folder.name,
        branch: repositoryState?.branch,
        folderCount,
        receiptCount: stats.total,
        invalidReceiptCount: stats.invalid,
        cliAvailable,
        repoInitialized,
        headReceiptStatus,
        latestReceipt: latestReceipt
            ? {
                label: getReceiptSubject(latestReceipt.receipt),
                author: latestReceipt.receipt.commit?.author?.name || 'Unknown author',
                timestamp: formatReceiptTimestamp(latestReceipt.receipt.timestamp),
                uri: latestReceipt.uri.toString(),
            }
            : undefined,
        activeAITool: repositoryState?.activeAIToolName,
        hookKind,
        headSha,
        regulatedMode,
        policyEnabled,
        currentEvidenceTier,
        sigstoreReceiptCount: stats.sigstorePresent,
    });
}

function buildManagedHook(cliPath: string, args: string[]): string {
    // Include detected AI tools so the hook generates accurate receipts
    // even when the commit happens outside an explicit "Generate Receipt" command.
    const agentArgs = buildAgentArgs();
    const trailerArgs = vscode.workspace.getConfiguration('aiir').get<boolean>('injectTrailers', false)
        ? ['--trailer']
        : [];
    const allArgs = [...args, ...buildEditorProvenanceArgs(), ...agentArgs, ...trailerArgs];
    const command = [shellQuote(cliPath), ...allArgs.map(shellQuote)].join(' ');
    return [
        MANAGED_HOOK_START,
        '# Managed by the AIIR VS Code extension.',
        `${command} >/dev/null 2>&1 || ${command}`,
        MANAGED_HOOK_END,
    ].join('\n');
}

async function installManagedPostCommitHook(
    folder: vscode.WorkspaceFolder,
    output: vscode.OutputChannel,
): Promise<'installed' | 'updated' | 'replaced' | 'cancelled'> {
    const gitDir = await resolveGitDir(folder, output);
    if (!gitDir) {
        throw new Error('Current workspace folder is not a git repository');
    }

    const hookPath = path.join(gitDir, 'hooks', 'post-commit');
    const managedBlock = buildManagedHook(getCliPath(), getAutoReceiptArgs());
    const existing = await readTextFile(hookPath);

    let nextContent = '#!/bin/sh\n\n' + managedBlock + '\n';
    let result: 'installed' | 'updated' | 'replaced' = 'installed';

    if (existing) {
        if (existing.includes(MANAGED_HOOK_START) && existing.includes(MANAGED_HOOK_END)) {
            nextContent = existing.replace(
                new RegExp(`${MANAGED_HOOK_START}[\\s\\S]*?${MANAGED_HOOK_END}`),
                managedBlock,
            );
            result = 'updated';
        } else {
            const firstLine = existing.split(/\r?\n/, 1)[0] || '';
            const looksShell = firstLine.startsWith('#!')
                ? /(sh|bash|zsh|dash)/.test(firstLine)
                : true;

            if (!looksShell) {
                const choice = await vscode.window.showWarningMessage(
                    'AIIR found an existing non-shell post-commit hook. Replace it with a managed AIIR hook?',
                    { modal: true },
                    'Replace Hook',
                    'Cancel',
                );
                if (choice !== 'Replace Hook') {
                    return 'cancelled';
                }
                result = 'replaced';
            } else {
                const choice = await vscode.window.showWarningMessage(
                    'AIIR found an existing custom post-commit hook. Append a managed AIIR block to it?',
                    { modal: true },
                    'Append AIIR Block',
                    'Replace Hook',
                    'Cancel',
                );

                if (choice === 'Cancel' || !choice) {
                    return 'cancelled';
                }

                if (choice === 'Replace Hook') {
                    result = 'replaced';
                } else {
                    nextContent = existing.replace(/\s*$/, '\n\n') + managedBlock + '\n';
                    result = 'updated';
                }
            }
        }
    }

    await vscode.workspace.fs.writeFile(vscode.Uri.file(hookPath), Buffer.from(nextContent, 'utf-8'));
    await execFileBounded('chmod', ['755', hookPath]);
    return result;
}

async function disableManagedPostCommitHook(folder: vscode.WorkspaceFolder): Promise<boolean> {
    const gitDir = await resolveGitDir(folder);
    if (!gitDir) {
        throw new Error('Current workspace folder is not a git repository');
    }

    const hookPath = path.join(gitDir, 'hooks', 'post-commit');
    const existing = await readTextFile(hookPath);
    if (!existing || !existing.includes(MANAGED_HOOK_START) || !existing.includes(MANAGED_HOOK_END)) {
        return false;
    }

    const stripped = existing
        .replace(new RegExp(`\n?${MANAGED_HOOK_START}[\\s\\S]*?${MANAGED_HOOK_END}\n?`, 'm'), '\n')
        .replace(/\n{3,}/g, '\n\n')
        .trim();

    if (!stripped || stripped === '#!/bin/sh') {
        await vscode.workspace.fs.delete(vscode.Uri.file(hookPath), { useTrash: false });
        return true;
    }

    await vscode.workspace.fs.writeFile(vscode.Uri.file(hookPath), Buffer.from(stripped + '\n', 'utf-8'));
    return true;
}

async function collectHealthCheck(
    folder: vscode.WorkspaceFolder,
    explorer: ReceiptExplorerProvider,
    output: vscode.OutputChannel,
    hubState?: HubConnectionState,
): Promise<HealthCheckResult> {
    const result: HealthCheckResult = {
        workspaceName: folder.name,
        cliAvailable: false,
        gitAvailable: false,
        aiirDirExists: false,
        ledgerExists: false,
        indexExists: false,
        policyExists: false,
        postCommitHook: 'missing',
        headReceiptStatus: 'unknown',
        headCborStatus: 'unknown',
        cborReceipts: 0,
        missingCborReceipts: 0,
        sigstoreReceipts: 0,
        tierSigned: 0,
        tierProvable: 0,
        tierHeuristic: 0,
        tierUnsigned: 0,
        hubConfigured: false,
        hubConnected: false,
        hubAuthenticated: false,
        mcpConfigured: false,
        trailerInjection: false,
        regulatedMode: false,
        lockPreset: '',
    };

    try {
        const cli = await runCommand(getCliPath(), ['--version'], folder.uri.fsPath, output);
        result.cliAvailable = true;
        result.cliVersion = cli.stdout || cli.stderr || 'available';
    } catch {
        result.cliAvailable = false;
    }

    result.gitDir = await resolveGitDir(folder, output);
    result.gitAvailable = !!result.gitDir;
    result.currentCommit = await getCurrentCommitSha(folder);

    const aiirDir = path.join(folder.uri.fsPath, '.aiir');
    const ledgerPath = path.join(aiirDir, 'receipts.jsonl');
    const indexPath = path.join(aiirDir, 'index.json');
    const policyPath = path.join(aiirDir, 'policy.json');

    result.aiirDirExists = await pathExists(aiirDir);
    result.ledgerExists = await pathExists(ledgerPath);
    result.indexExists = await pathExists(indexPath);
    result.policyExists = await pathExists(policyPath);

    if (result.gitDir) {
        const hookPath = path.join(result.gitDir, 'hooks', 'post-commit');
        const hookContents = await readTextFile(hookPath);
        if (!hookContents) {
            result.postCommitHook = 'missing';
        } else if (hookContents.includes(MANAGED_HOOK_START)) {
            result.postCommitHook = 'managed';
        } else {
            result.postCommitHook = 'custom';
        }
    }

    if (result.currentCommit) {
        const headReceipt = explorer.getReceiptForCommit(result.currentCommit, folder);
        result.headReceiptStatus = headReceipt ? 'present' : 'missing';
        result.headCborStatus = headReceipt?.artifacts.cborStatus || 'unknown';
    }

    const stats = explorer.getStats(folder);
    result.cborReceipts = stats.cborPresent;
    result.missingCborReceipts = stats.total - stats.cborPresent;
    result.sigstoreReceipts = stats.sigstorePresent;
    result.tierSigned = stats.tierSigned;
    result.tierProvable = stats.tierProvable;
    result.tierHeuristic = stats.tierHeuristic;
    result.tierUnsigned = stats.tierUnsigned;

    if (hubState) {
        result.hubConfigured = hubState.configured;
        result.hubConnected = hubState.connected;
        result.hubAuthenticated = hubState.authenticated;
        result.hubBaseUrl = hubState.baseUrl;
        result.hubTenantId = hubState.tenantId;
        result.hubError = hubState.error;
    }

    const mcpJsonPath = path.join(folder.uri.fsPath, '.vscode', 'mcp.json');
    const mcpContent = await readTextFile(mcpJsonPath);
    if (mcpContent) {
        try {
            const mcpConfig = JSON.parse(mcpContent);
            result.mcpConfigured = !!(mcpConfig?.servers?.aiir);
        } catch {
            // Invalid JSON — treat as not configured
        }
    }

    const config = vscode.workspace.getConfiguration('aiir');
    result.trailerInjection = config.get<boolean>('injectTrailers', false);
    result.regulatedMode = config.get<boolean>('regulatedMode', false);
    result.lockPreset = config.get<string>('lockPreset', '');

    if (result.cliAvailable) {
        try {
            const doctor = await runJsonCommand(getCliPath(), ['--doctor', '--json'], folder.uri.fsPath, output);
            result.cliVersion = typeof doctor.cli_version === 'string' ? doctor.cli_version : result.cliVersion;
            result.gitAvailable = typeof doctor.git_available === 'boolean' ? doctor.git_available : result.gitAvailable;
            result.currentCommit = typeof doctor.head_sha === 'string' ? doctor.head_sha : result.currentCommit;
            result.aiirDirExists = typeof doctor.aiir_dir_exists === 'boolean' ? doctor.aiir_dir_exists : result.aiirDirExists;
            result.ledgerExists = typeof doctor.ledger_exists === 'boolean' ? doctor.ledger_exists : result.ledgerExists;
            result.indexExists = typeof doctor.index_exists === 'boolean' ? doctor.index_exists : result.indexExists;
            result.policyExists = typeof doctor.policy_exists === 'boolean' ? doctor.policy_exists : result.policyExists;
            if (doctor.managed_hook_state === 'managed' || doctor.managed_hook_state === 'custom' || doctor.managed_hook_state === 'missing') {
                result.postCommitHook = doctor.managed_hook_state;
            }
            if (doctor.head_receipt_status === 'present' || doctor.head_receipt_status === 'missing' || doctor.head_receipt_status === 'unknown') {
                result.headReceiptStatus = doctor.head_receipt_status;
            }
        } catch (error) {
            output.appendLine(`AIIR doctor fallback: ${(error as Error).message}`);
        }
    }

    return result;
}

// ── Receipt Discovery ─────────────────────────────────────────────────

async function discoverReceipts(): Promise<vscode.Uri[]> {
    const patterns = [
        '**/*.aiir.json',
        '**/.receipts/*.json',
        '**/.aiir-receipts/*.json',
        '**/.aiir/*.json',
        '**/.aiir/receipts/*.json',
    ];

    const uris: vscode.Uri[] = [];
    for (const folder of getAccessibleWorkspaceFolders()) {
        for (const pattern of patterns) {
            const found = await vscode.workspace.findFiles(
                new vscode.RelativePattern(folder, pattern),
                '**/node_modules/**',
                500,
            );
            uris.push(...found);
        }
    }

    // Deduplicate
    const seen = new Set<string>();
    return uris.filter(u => {
        if (seen.has(u.fsPath)) { return false; }
        seen.add(u.fsPath);
        return true;
    });
}

async function loadReceipt(uri: vscode.Uri): Promise<ReceiptData | null> {
    try {
        const content = await vscode.workspace.fs.readFile(uri);
        const text = Buffer.from(content).toString('utf-8');
        const parsed = JSON.parse(text);
        if (isSupportedReceiptDocument(parsed)) {
            return parsed as ReceiptData;
        }
    } catch {
        // Not a valid receipt — skip
    }
    return null;
}

function getReceiptArtifactPath(folder: vscode.WorkspaceFolder, receipt: ReceiptData): string | undefined {
    const commitSha = receipt.commit?.sha;
    const contentHash = receipt.content_hash;
    if (!commitSha || !contentHash) {
        return undefined;
    }

    const commitShort = commitSha.slice(0, 12).replace(/[^a-zA-Z0-9_-]/g, '_');
    const hashShort = contentHash.replace(/[^a-fA-F0-9]/g, '').slice(0, 16);
    if (!commitShort || !hashShort) {
        return undefined;
    }

    return path.join(folder.uri.fsPath, '.aiir', 'receipts', `receipt_${commitShort}_${hashShort}.json`);
}

async function loadReceiptRecordsFromLedger(folder: vscode.WorkspaceFolder): Promise<ReceiptRecord[]> {
    const ledgerUri = vscode.Uri.file(path.join(folder.uri.fsPath, '.aiir', 'receipts.jsonl'));
    if (!isUriAccessible(ledgerUri)) {
        return [];
    }

    const ledgerContent = await readTextFile(ledgerUri.fsPath);
    if (!ledgerContent) {
        return [];
    }

    const records: ReceiptRecord[] = [];
    for (const line of ledgerContent.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed) {
            continue;
        }

        try {
            const parsed = JSON.parse(trimmed);
            if (!parsed || typeof parsed !== 'object' || parsed.type !== 'aiir.commit_receipt') {
                continue;
            }

            const receipt = parsed as ReceiptData;
            const review = getReceiptReviewInfo(parsed);
            const artifactPath = getReceiptArtifactPath(folder, receipt);
            const artifactUri = artifactPath && await pathExists(artifactPath)
                ? vscode.Uri.file(artifactPath)
                : ledgerUri;

            records.push({
                receipt,
                uri: artifactUri,
                result: verifyReceipt(receipt),
                artifacts: await getReceiptArtifacts(artifactUri),
                review,
                workspaceFolderName: folder.name,
                workspaceFolderPath: folder.uri.fsPath,
            });
        } catch {
            // Skip malformed ledger lines.
        }
    }

    return records;
}

function getReceiptRecordKey(record: ReceiptRecord): string {
    return [
        record.workspaceFolderPath || '',
        record.receipt.commit?.sha || '',
        record.receipt.content_hash || '',
    ].join('::');
}

async function getReceiptArtifacts(uri: vscode.Uri): Promise<ReceiptArtifacts> {
    const parsed = path.parse(uri.fsPath);
    const cborPath = path.join(parsed.dir, parsed.name + '.cbor');
    const sigstorePath = uri.fsPath + '.sigstore';
    const cborUri = vscode.Uri.file(cborPath);
    let cborExists = false;
    let cborSize: number | undefined;
    let cborHash: string | undefined;
    try {
        const stat = await vscode.workspace.fs.stat(cborUri);
        cborExists = true;
        cborSize = stat.size;
        const bytes = await vscode.workspace.fs.readFile(cborUri);
        cborHash = 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
    } catch { /* not present */ }
    const sigstoreUri = vscode.Uri.file(sigstorePath);
    let sigstoreExists = false;
    let sigstoreSize: number | undefined;
    let sigstoreHash: string | undefined;
    try {
        const stat = await vscode.workspace.fs.stat(sigstoreUri);
        sigstoreExists = true;
        sigstoreSize = stat.size;
        const bytes = await vscode.workspace.fs.readFile(sigstoreUri);
        sigstoreHash = 'sha256:' + crypto.createHash('sha256').update(bytes).digest('hex');
    } catch { /* not present */ }

    return {
        cborUri: cborExists ? cborUri : undefined,
        sigstoreUri: sigstoreExists ? sigstoreUri : undefined,
        cborStatus: cborExists ? 'present' : 'missing',
        sigstoreStatus: sigstoreExists ? 'present' : 'missing',
        cborSize,
        cborHash,
        sigstoreSize,
        sigstoreHash,
    };
}

async function loadReceiptRecord(uri: vscode.Uri): Promise<ReceiptRecord | null> {
    if (!isUriAccessible(uri)) {
        return null;
    }

    const receipt = await loadReceipt(uri);
    if (!receipt) {
        return null;
    }

    const folder = vscode.workspace.getWorkspaceFolder(uri);

    return {
        receipt,
        uri,
        result: verifyReceipt(receipt),
        artifacts: await getReceiptArtifacts(uri),
        workspaceFolderName: folder?.name,
        workspaceFolderPath: folder?.uri.fsPath,
    };
}

async function getTargetReceiptRecord(
    target: unknown,
    explorer: ReceiptExplorerProvider,
): Promise<ReceiptRecord | undefined> {
    const directRecord = getReceiptRecordFromTarget(target);
    if (directRecord) {
        rememberWorkspaceFolder(vscode.workspace.getWorkspaceFolder(directRecord.uri));
        return directRecord;
    }

    const candidate = resolveTargetUri(target) || vscode.window.activeTextEditor?.document.uri;
    if (candidate) {
        const cachedRecord = explorer.getReceiptByUri(candidate);
        if (cachedRecord) {
            rememberWorkspaceFolder(vscode.workspace.getWorkspaceFolder(candidate));
            return cachedRecord;
        }

        const record = await loadReceiptRecord(candidate);
        if (record) {
            rememberWorkspaceFolder(vscode.workspace.getWorkspaceFolder(candidate));
            return record;
        }
    }

    const folder = await resolveCommandWorkspaceFolder(candidate, 'Choose a repository to inspect');
    if (!folder) {
        return undefined;
    }

    const headSha = await getCurrentCommitSha(folder);
    if (!headSha) {
        return undefined;
    }

    return explorer.getReceiptForCommit(headSha, folder);
}

function resolveTargetUri(target: unknown): vscode.Uri | undefined {
    if (target instanceof vscode.Uri) {
        return target;
    }

    if (typeof target === 'string') {
        try {
            return vscode.Uri.parse(target);
        } catch {
            return undefined;
        }
    }

    if (target && typeof target === 'object') {
        const candidate = target as {
            uri?: vscode.Uri | string;
            resourceUri?: vscode.Uri | string;
            record?: { uri?: vscode.Uri | string };
        };

        if (candidate.uri instanceof vscode.Uri) {
            return candidate.uri;
        }
        if (typeof candidate.uri === 'string') {
            try {
                return vscode.Uri.parse(candidate.uri);
            } catch {
                return undefined;
            }
        }
        if (candidate.resourceUri instanceof vscode.Uri) {
            return candidate.resourceUri;
        }
        if (typeof candidate.resourceUri === 'string') {
            try {
                return vscode.Uri.parse(candidate.resourceUri);
            } catch {
                return undefined;
            }
        }
        if (candidate.record?.uri instanceof vscode.Uri) {
            return candidate.record.uri;
        }
        if (typeof candidate.record?.uri === 'string') {
            try {
                return vscode.Uri.parse(candidate.record.uri);
            } catch {
                return undefined;
            }
        }
    }

    return undefined;
}

function getReceiptRecordFromTarget(target: unknown): ReceiptRecord | undefined {
    if (!target || typeof target !== 'object') {
        return undefined;
    }

    const candidate = target as { record?: ReceiptRecord };
    return candidate.record;
}

// ── Sidebar Tree Views ───────────────────────────────────────────────

function compareReceipts(left: ReceiptRecord, right: ReceiptRecord): number {
    if (left.result.valid !== right.result.valid) {
        return left.result.valid ? 1 : -1;
    }

    return (right.receipt.timestamp || '').localeCompare(left.receipt.timestamp || '');
}

function getReceiptSubject(receipt: ReceiptData): string {
    const subject = (receipt.commit?.subject || '').trim();
    return subject || 'Untitled commit receipt';
}

function formatBytes(bytes: number): string {
    if (bytes < 1024) { return `${bytes} B`; }
    if (bytes < 1024 * 1024) { return `${(bytes / 1024).toFixed(1)} KB`; }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatReceiptTimestamp(value?: string): string {
    if (!value) {
        return 'Unknown time';
    }

    const timestamp = Date.parse(value);
    if (Number.isNaN(timestamp)) {
        return value;
    }

    const deltaMinutes = Math.max(0, Math.round((Date.now() - timestamp) / 60000));
    if (deltaMinutes < 1) {
        return 'Just now';
    }
    if (deltaMinutes < 60) {
        return `${deltaMinutes}m ago`;
    }

    const deltaHours = Math.round(deltaMinutes / 60);
    if (deltaHours < 24) {
        return `${deltaHours}h ago`;
    }

    const deltaDays = Math.round(deltaHours / 24);
    if (deltaDays < 14) {
        return `${deltaDays}d ago`;
    }

    return new Intl.DateTimeFormat(undefined, {
        month: 'short',
        day: 'numeric',
    }).format(new Date(timestamp));
}

function getReceiptTimestampValue(value?: string): number {
    if (!value) {
        return 0;
    }

    const timestamp = Date.parse(value);
    return Number.isNaN(timestamp) ? 0 : timestamp;
}

function compareReceiptFreshness(left: ReceiptRecord, right: ReceiptRecord): number {
    const timestampDelta = getReceiptTimestampValue(right.receipt.timestamp) - getReceiptTimestampValue(left.receipt.timestamp);
    if (timestampDelta !== 0) {
        return timestampDelta;
    }

    return right.uri.toString().localeCompare(left.uri.toString());
}

function getReceiptActivityKey(record: ReceiptRecord): string {
    const commitSha = record.receipt.commit?.sha?.trim();
    return commitSha ? `commit:${commitSha}` : `receipt:${record.uri.toString()}`;
}

function getActiveReceiptRecords(records: ReceiptRecord[]): ReceiptRecord[] {
    const latestByKey = new Map<string, ReceiptRecord>();

    for (const record of records) {
        const key = getReceiptActivityKey(record);
        const existing = latestByKey.get(key);
        if (!existing || compareReceiptFreshness(record, existing) < 0) {
            latestByKey.set(key, record);
        }
    }

    return Array.from(latestByKey.values());
}

function getActiveReceiptForCommit(records: ReceiptRecord[], commitSha: string): ReceiptRecord | undefined {
    return getActiveReceiptRecords(records).find(record => record.receipt.commit?.sha === commitSha);
}

function getReceiptStatusSummary(record: ReceiptRecord): string {
    const tier = getReceiptEvidenceTier(record.receipt, record.artifacts);
    const parts = [record.result.valid ? 'compliant' : 'needs attention'];
    parts.push(`${EVIDENCE_TIER_SHORT_LABELS[tier].toLowerCase()} evidence`);
    parts.push(hasAIInvolvement(record.receipt) ? 'AI-assisted' : 'human');
    if (record.artifacts.cborStatus === 'present') {
        parts.push('cbor');
    }
    parts.push(formatReceiptTimestamp(record.receipt.timestamp));
    return parts.join(' • ');
}

function getReceiptListDescription(record: ReceiptRecord): string {
    const { receipt, result } = record;
    const tier = getReceiptEvidenceTier(receipt, record.artifacts);
    const commitShort = receipt.commit?.sha?.slice(0, 8) || '?';
    const parts = [commitShort, EVIDENCE_TIER_SHORT_LABELS[tier], formatReceiptTimestamp(receipt.timestamp)];
    const reviewSummary = getReceiptReviewStatusSummary(record.review, hasAIInvolvement(receipt));
    if (reviewSummary) {
        parts.push(reviewSummary);
    }
    if (!result.valid) {
        parts.push('Needs attention');
    } else if (hasAIInvolvement(receipt)) {
        parts.push('AI-assisted');
    }
    return parts.join(' \u00b7 ');
}

function getReceiptAuthorName(record: ReceiptRecord): string {
    const name = (record.receipt.commit?.author?.name || '').trim();

    return name || 'Unknown author';
}

function buildReceiptClipboardSummary(record: ReceiptRecord): string {
    const { receipt, result, artifacts, workspaceFolderName } = record;
    const sha = receipt.commit?.sha || '—';
    const shaShort = sha.slice(0, 12) || '—';
    const artifactParts: string[] = [];
    const filesChanged = receipt.commit?.files_changed ?? receipt.commit?.files?.length ?? 0;
    const evidenceTier = EVIDENCE_TIER_LABELS[getReceiptEvidenceTier(receipt, artifacts)];
    const verificationLabel = result.valid ? 'Verified' : 'Needs attention';
    const summaryLead = result.valid
        ? `Current commit \`${shaShort}\` in ${workspaceFolderName || 'this repository'} is recorded and verified.`
        : `Current commit \`${shaShort}\` in ${workspaceFolderName || 'this repository'} is recorded but needs attention.`;

    if (artifacts.sigstoreStatus === 'present') {
        artifactParts.push('sigstore');
    }
    if (artifacts.cborStatus === 'present') {
        artifactParts.push('cbor');
    }

    const lines = [
        '## AIIR PR Summary',
        '',
        summaryLead,
        '',
        '### Snapshot',
        '',
        `- Repository: ${workspaceFolderName || 'Unknown workspace'}`,
        `- Commit: \`${shaShort}\``,
        `- Subject: ${getReceiptSubject(receipt)}`,
        `- Author: ${receipt.commit?.author?.name || 'Unknown author'}`,
        `- Verification: ${verificationLabel}`,
        `- Evidence tier: ${evidenceTier}`,
        `- Files changed: ${filesChanged}`,
        `- Timestamp: ${receipt.timestamp || '—'}`,
        '',
        '### AI Evidence',
        '',
        `- Attested tool: ${getAttestedSystemSummary(receipt)}`,
        `- AI involvement: ${getAIInvolvementSummary(receipt)}`,
        `- AI signals: ${getAISignalsSummary(receipt)}`,
        `- Artifacts: ${artifactParts.length > 0 ? artifactParts.join(', ') : 'json only'}`,
    ];

    if (!result.valid) {
        lines.push('');
        lines.push('### Review Follow-Up');
        lines.push('');
        lines.push(`- Verification details: ${result.errors.join('; ') || 'verification error'}`);
    }

    return lines.join('\n');
}

class ReceiptRepositoryItem extends vscode.TreeItem {
    constructor(
        public readonly repositoryName: string,
        public readonly repositoryPath: string | undefined,
        public readonly records: ReceiptRecord[],
        stats: ReceiptStats,
        state: RepositoryViewState | undefined,
        branch?: string,
        headSha?: string,
    ) {
        super(repositoryName, vscode.TreeItemCollapsibleState.Expanded);

        const branchText = branch ? `${branch} \u00b7 ` : '';
        this.description = getRepositoryHeadBadge(branchText, headSha, records, stats, state);
        this.tooltip = new vscode.MarkdownString(
            `**Repository:** ${repositoryName}\n\n` +
            `**Receipts:** ${stats.total}\n\n` +
            `**Verified:** ${stats.valid}\n\n` +
            `**Failed:** ${stats.invalid}`,
        );
        this.iconPath = new vscode.ThemeIcon('repo');
        this.contextValue = 'receipt-repository';
    }
}

function getRepositoryHeadBadge(
    branchText: string,
    headSha: string | undefined,
    records: ReceiptRecord[],
    stats: ReceiptStats,
    state?: RepositoryViewState,
): string {
    if (stats.total === 0) {
        if (state?.aiirDirExists) {
            return isRepositoryFullyReady(state)
                ? `${branchText}\u25cb ready for first receipt`
                : `${branchText}\u25cb setup in progress`;
        }
        return `${branchText}\u25cb no receipts`;
    }
    if (!headSha) {
        return `${branchText}${stats.total} receipt${stats.total === 1 ? '' : 's'}`;
    }
    const headRecord = getActiveReceiptForCommit(records, headSha);
    if (!headRecord) {
        return `${branchText}\u26a0 HEAD not recorded`;
    }
    if (!headRecord.result.valid) {
        return `${branchText}\u2717 HEAD failed`;
    }
    return `${branchText}\u2713 HEAD recorded`;
}

class ReceiptSectionItem extends vscode.TreeItem {
    constructor(
        public readonly sectionLabel: string,
        public readonly records: ReceiptRecord[],
        iconId: string,
        description?: string,
        expanded = true,
    ) {
        super(sectionLabel, expanded
            ? vscode.TreeItemCollapsibleState.Expanded
            : vscode.TreeItemCollapsibleState.Collapsed);

        this.description = description;
        this.iconPath = new vscode.ThemeIcon(iconId);
        this.contextValue = 'receipt-section';
    }
}

type ReceiptSubsectionKind = 'overview' | 'signals' | 'files' | 'editor-diffs' | 'artifacts' | 'provenance' | 'editor-provenance';

class ReceiptSubsectionItem extends vscode.TreeItem {
    constructor(
        public readonly record: ReceiptRecord,
        public readonly subsectionKind: ReceiptSubsectionKind,
        label: string,
        description: string,
        iconId: string,
    ) {
        super(label, vscode.TreeItemCollapsibleState.Collapsed);

        this.description = description;
        this.iconPath = new vscode.ThemeIcon(iconId);
        this.contextValue = 'receipt-subsection';
    }
}

class ReceiptActionItem extends vscode.TreeItem {
    constructor(
        label: string,
        description: string,
        iconId: string,
        commandId: string,
        args?: unknown[],
    ) {
        super(label, vscode.TreeItemCollapsibleState.None);

        this.description = description;
        this.iconPath = new vscode.ThemeIcon(iconId);
        this.contextValue = 'receipt-action';
        this.command = {
            command: commandId,
            title: label,
            arguments: args,
        };
    }
}

class ReceiptFileItem extends vscode.TreeItem {
    constructor(label: string, resourceUri: vscode.Uri, description = 'open file') {
        super(label, vscode.TreeItemCollapsibleState.None);

        this.resourceUri = resourceUri;
        this.tooltip = resourceUri.fsPath;
        this.description = description;
        this.iconPath = new vscode.ThemeIcon('file');
        this.contextValue = 'receipt-file';
        this.command = {
            command: 'aiir.openTreeFile',
            title: 'Open File',
            arguments: [resourceUri],
        };
    }
}

interface EditorDiffEvent {
    beforeHash?: string;
    afterHash?: string;
    command?: string;
    source?: string;
    promptKind?: string;
    createdAt?: string;
    baseCommitSha?: string;
    sessionId?: string;
}

interface AttestedDiffComparisonTarget {
    receiptUri: string;
    filePath: string;
    fileUri?: string;
    beforeHash?: string;
    afterHash?: string;
    baseCommitSha?: string;
    createdAt?: string;
}

interface RecoverableAttestedSnapshot {
    label: string;
    content: string;
}

function getRecoverableSnapshotMatchLabel(snapshot: RecoverableAttestedSnapshot, hashKind: 'before' | 'after'): string {
    return `${snapshot.label} matched ${hashKind}Hash`;
}

async function getFileContentFromCommit(
    folder: vscode.WorkspaceFolder,
    commitSha: string,
    filePath: string,
): Promise<string | undefined> {
    try {
        const { stdout } = await execFileBounded('git', ['show', `${commitSha}:${filePath}`], {
            cwd: folder.uri.fsPath,
            maxBuffer: 10 * 1024 * 1024,
        });
        return stdout;
    } catch {
        return undefined;
    }
}

async function getWorkspaceFileContent(fileUri: vscode.Uri | undefined): Promise<string | undefined> {
    if (!fileUri || fileUri.scheme !== 'file') {
        return undefined;
    }

    try {
        const bytes = await vscode.workspace.fs.readFile(fileUri);
        return Buffer.from(bytes).toString('utf-8');
    } catch {
        return undefined;
    }
}

function parseAttestedDiffComparisonTarget(target: unknown): AttestedDiffComparisonTarget | undefined {
    if (!target || typeof target !== 'object') {
        return undefined;
    }

    const candidate = target as Record<string, unknown>;
    if (typeof candidate.receiptUri !== 'string' || typeof candidate.filePath !== 'string') {
        return undefined;
    }

    return {
        receiptUri: candidate.receiptUri,
        filePath: candidate.filePath,
        fileUri: typeof candidate.fileUri === 'string' ? candidate.fileUri : undefined,
        beforeHash: typeof candidate.beforeHash === 'string' ? candidate.beforeHash : undefined,
        afterHash: typeof candidate.afterHash === 'string' ? candidate.afterHash : undefined,
        baseCommitSha: typeof candidate.baseCommitSha === 'string' ? candidate.baseCommitSha : undefined,
        createdAt: typeof candidate.createdAt === 'string' ? candidate.createdAt : undefined,
    };
}

async function resolveRecoverableAttestedDiff(
    record: ReceiptRecord,
    target: AttestedDiffComparisonTarget,
): Promise<{ before: RecoverableAttestedSnapshot; after: RecoverableAttestedSnapshot } | undefined> {
    const folder = vscode.workspace.getWorkspaceFolder(record.uri);
    const receiptCommitSha = record.receipt.commit?.sha;
    const fileUri = resolveTargetUri(target.fileUri)
        || (record.workspaceFolderPath ? vscode.Uri.file(path.join(record.workspaceFolderPath, target.filePath)) : undefined);
    const candidates: RecoverableAttestedSnapshot[] = [];

    if (folder && target.baseCommitSha) {
        const baseContent = await getFileContentFromCommit(folder, target.baseCommitSha, target.filePath);
        if (baseContent !== undefined) {
            candidates.push({ label: `base ${target.baseCommitSha.slice(0, 8)}`, content: baseContent });
        }
    }

    if (folder && receiptCommitSha) {
        const receiptContent = await getFileContentFromCommit(folder, receiptCommitSha, target.filePath);
        if (receiptContent !== undefined) {
            candidates.push({ label: `receipt ${receiptCommitSha.slice(0, 8)}`, content: receiptContent });
        }
    }

    const workspaceContent = await getWorkspaceFileContent(fileUri);
    if (workspaceContent !== undefined) {
        candidates.push({ label: 'workspace', content: workspaceContent });
    }

    const before = candidates.find(candidate => target.beforeHash && sha256Text(candidate.content) === target.beforeHash);
    const after = candidates.find(candidate => target.afterHash && sha256Text(candidate.content) === target.afterHash);

    if (!before || !after) {
        return undefined;
    }

    return { before, after };
}

function summarizeEditorDiffHashes(beforeHash?: string, afterHash?: string): string {
    const hashBefore = beforeHash ? beforeHash.slice(0, 8) : '—';
    const hashAfter = afterHash ? afterHash.slice(0, 8) : '—';
    return `${hashBefore} → ${hashAfter}`;
}

class EditorDiffFileItem extends vscode.TreeItem {
    constructor(
        public readonly record: ReceiptRecord,
        public readonly filePath: string,
        public readonly fileUri: vscode.Uri | undefined,
        public readonly events: EditorDiffEvent[],
    ) {
        super(filePath, vscode.TreeItemCollapsibleState.None);

        const latest = events[events.length - 1];
        const summary = summarizeEditorDiffHashes(latest?.beforeHash, latest?.afterHash);
        this.description = `${events.length} update${events.length === 1 ? '' : 's'} • ${summary}`;
        this.tooltip = fileUri?.fsPath || filePath;
        this.resourceUri = fileUri;
        this.iconPath = new vscode.ThemeIcon('diff');
        this.contextValue = 'editor-diff-file';
        this.command = {
            command: 'aiir.viewAttestedDiffFile',
            title: 'View Attested Diff History',
            arguments: [this],
        };
    }
}

class ReceiptTreeItem extends vscode.TreeItem {
    constructor(
        public readonly record: ReceiptRecord,
    ) {
        const { receipt, uri, result, artifacts } = record;
        const isAI = isAIAuthored(receipt);
        const aiInvolvement = getAIInvolvementSummary(receipt);
        const author = receipt.commit?.author?.name || 'Unknown author';
        const cborBadge = artifacts.cborStatus === 'present' ? 'CBOR' : 'No CBOR';
        const sigstoreBadge = artifacts.sigstoreStatus === 'present' ? 'Signed' : 'Unsigned';
        const showWorkspace = !!record.workspaceFolderName;

        super(
            getReceiptSubject(receipt),
            vscode.TreeItemCollapsibleState.Collapsed,
        );

        this.description = getReceiptListDescription(record);

        this.tooltip = new vscode.MarkdownString(
            `| | |\n|---|---|\n` +
            `| **Subject** | ${getReceiptSubject(receipt)} |\n` +
            `${showWorkspace ? `| **Workspace** | ${record.workspaceFolderName} |\n` : ''}` +
            `| **Commit** | \`${receipt.commit?.sha}\` |\n` +
            `| **Author** | ${author} |\n` +
            `| **Evidence Tier** | ${EVIDENCE_TIER_SHORT_LABELS[getReceiptEvidenceTier(receipt, artifacts)]} |\n` +
            `| **Review** | ${getReceiptReviewStatusLabel(record.review, hasAIInvolvement(receipt))} |\n` +
            `| **Attested Tool** | ${getAttestedSystemSummary(receipt)} |\n` +
            `| **Editor Provenance** | ${getEditorProvenanceSummary(receipt)} |\n` +
            `| **AI Involvement** | ${aiInvolvement} |\n` +
            `| **AI Signals** | ${getAISignalsSummary(receipt)} |\n` +
            `| **AI Authored** | ${isAI ? 'Yes' : 'No'} |\n` +
            `| **Artifacts** | ${cborBadge} \u00b7 ${sigstoreBadge} |\n` +
            `| **Status** | ${result.valid ? '\u2705 Verified' : '\u274c ' + result.errors.join(', ')} |\n` +
            `| **Timestamp** | ${receipt.timestamp || '\u2014'} |`
        );

        this.iconPath = new vscode.ThemeIcon(
            result.valid ? 'verified-filled' : 'error',
            result.valid
                ? new vscode.ThemeColor('charts.green')
                : new vscode.ThemeColor('charts.red'),
        );

        this.contextValue = result.valid ? 'receipt-valid' : 'receipt-invalid';
        this.resourceUri = uri;
        this.command = {
            command: 'aiir.viewReceipt',
            title: 'Open Pretty Receipt',
            arguments: [uri],
        };
    }
}

class ReceiptDetailItem extends vscode.TreeItem {
    constructor(label: string, value: string, icon?: string) {
        super(`${label}: ${value}`, vscode.TreeItemCollapsibleState.None);
        if (icon) {
            this.iconPath = new vscode.ThemeIcon(icon);
        }
    }
}

type ProvenanceCategoryKind = 'intent' | 'chat' | 'commit';

class ProvenanceCategoryItem extends vscode.TreeItem {
    constructor(
        public readonly record: ReceiptRecord,
        public readonly categoryKind: ProvenanceCategoryKind,
        label: string,
        description: string,
        iconId: string,
    ) {
        super(label, vscode.TreeItemCollapsibleState.Collapsed);
        this.description = description;
        this.iconPath = new vscode.ThemeIcon(iconId);
        this.contextValue = 'provenance-category';
    }
}

type ReceiptExplorerNode = ReceiptRepositoryItem | ReceiptSectionItem | ReceiptTreeItem | ReceiptSubsectionItem | ReceiptDetailItem | ReceiptActionItem | ReceiptFileItem | EditorDiffFileItem | ProvenanceCategoryItem;

class ReceiptExplorerProvider implements vscode.TreeDataProvider<ReceiptExplorerNode> {
    private _onDidChangeTreeData = new vscode.EventEmitter<void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private receipts: ReceiptRecord[] = [];
    private repositoryState = new Map<string, RepositoryViewState>();

    async refresh(): Promise<void> {
        const uris = await discoverReceipts();
        const nextRecords = new Map<string, ReceiptRecord>();
        this.receipts = [];
        this.repositoryState.clear();

        for (const uri of uris) {
            const record = await loadReceiptRecord(uri);
            if (record) {
                nextRecords.set(getReceiptRecordKey(record), record);
            }
        }

        const accessibleFolders = getAccessibleWorkspaceFolders();
        for (const folder of accessibleFolders) {
            const ledgerRecords = await loadReceiptRecordsFromLedger(folder);
            for (const record of ledgerRecords) {
                nextRecords.set(getReceiptRecordKey(record), record);
            }
        }

        this.receipts = Array.from(nextRecords.values());

        this.receipts.sort(compareReceipts);

        for (const folder of accessibleFolders) {
            const folderRecords = this.receipts.filter(record => record.workspaceFolderPath === folder.uri.fsPath);
            const currentHeadSha = await getCurrentCommitSha(folder);
            const receiptInfo: RepositoryReceiptInfo = {
                receiptCount: folderRecords.length,
                hasReceipts: folderRecords.length > 0,
                headReceiptStatus: currentHeadSha
                    ? (folderRecords.some(record => record.receipt.commit?.sha === currentHeadSha) ? 'present' : 'missing')
                    : 'unknown',
            };
            this.repositoryState.set(folder.uri.fsPath, await resolveRepositoryViewState(folder, receiptInfo));
        }

        for (const record of this.receipts) {
            const repoState = record.workspaceFolderPath ? this.repositoryState.get(record.workspaceFolderPath) : undefined;
            record.workspaceBranch = repoState?.branch;
            record.workspaceHeadSha = repoState?.headSha;
            const embeddedFiles = record.receipt.commit?.files || [];
            if (embeddedFiles.length > 0) {
                record.uiFiles = embeddedFiles;
            } else if (repoState?.folder && record.receipt.commit?.sha) {
                record.uiFiles = await getCommitFilesFromGit(repoState.folder, record.receipt.commit.sha);
            }
        }

        this._onDidChangeTreeData.fire();
    }

    getRepositoryState(folder: vscode.WorkspaceFolder): RepositoryViewState | undefined {
        return this.getRepositoryStateByPath(folder.uri.fsPath);
    }

    getRepositoryStateByPath(folderPath: string): RepositoryViewState | undefined {
        const state = this.repositoryState.get(folderPath);
        if (!state) {
            return undefined;
        }

        const activeAITool = detectEditorAITools().find(tool => tool.isActive);
        return {
            ...state,
            activeAIToolName: activeAITool?.toolName,
            activeAIToolPresent: !!activeAITool,
        };
    }

    getTreeItem(element: ReceiptExplorerNode): vscode.TreeItem {
        return element;
    }

    getChildren(element?: ReceiptExplorerNode): ReceiptExplorerNode[] {
        if (!element) {
            if (this.isMultiRoot()) {
                return this.getRepositoryItems();
            }

            const folder = getAccessibleWorkspaceFolders()[0];
            if (folder && this.getReceipts(folder).length === 0) {
                return this.buildEmptyRepositoryItems(folder.uri.fsPath);
            }

            return this.buildRecentList(this.receipts, folder?.uri.fsPath);
        }

        if (element instanceof ReceiptRepositoryItem) {
            if (element.records.length === 0) {
                return this.buildEmptyRepositoryItems(element.repositoryPath);
            }
            return this.buildRecentList(element.records, element.repositoryPath);
        }

        if (element instanceof ReceiptSectionItem) {
            return element.records.map(record => new ReceiptTreeItem(record));
        }

        if (element instanceof ReceiptTreeItem) {
            return this.buildReceiptSubsections(element.record);
        }

        if (element instanceof ReceiptSubsectionItem) {
            const { receipt: r, artifacts } = element.record;
            const details: Array<ReceiptDetailItem | ReceiptActionItem | ReceiptFileItem | EditorDiffFileItem> = [];

            if (element.subsectionKind === 'overview') {
                details.push(new ReceiptActionItem('Open Pretty Receipt', 'Open the full receipt panel', 'preview', 'aiir.viewReceipt', [element.record.uri]));
                if (!element.record.result.valid) {
                    details.push(new ReceiptActionItem('Repair Failed Receipt', 'Choose the lowest-friction recovery path for this invalid receipt', 'tools', 'aiir.repairReceipt', [element.record]));
                }
                details.push(new ReceiptActionItem('Open Receipt JSON', 'Open the raw receipt file', 'json', 'aiir.openReceiptSource', [element.record.uri]));
                details.push(new ReceiptActionItem('Copy Markdown Summary', 'Copy a PR-ready Markdown receipt summary', 'copy', 'aiir.copyReceiptSummary', [element.record]));
                details.push(new ReceiptActionItem('Review This Commit', 'Record a review attestation for this commit', 'checklist', 'aiir.reviewReceipt', [{ sha: r.commit?.sha, uri: element.record.workspaceFolderPath ? vscode.Uri.file(element.record.workspaceFolderPath) : element.record.uri }]));
                details.push(new ReceiptActionItem('View Review History', 'Open recorded review attestations for this repository', 'history', 'aiir.viewReviewHistory', [element.record.workspaceFolderPath ? vscode.Uri.file(element.record.workspaceFolderPath) : element.record.uri]));
                details.push(new ReceiptDetailItem('Commit', r.commit?.sha?.slice(0, 12) || '?', 'git-commit'));
                if (element.record.workspaceBranch) {
                    details.push(new ReceiptDetailItem('Branch', element.record.workspaceBranch, 'git-branch'));
                }
                if (element.record.workspaceHeadSha && r.commit?.sha) {
                    details.push(new ReceiptDetailItem('Matches HEAD', element.record.workspaceHeadSha === r.commit.sha ? 'Yes' : 'No', 'check'));
                }
                details.push(new ReceiptDetailItem('Subject', getReceiptSubject(r), 'comment'));
                if (element.record.workspaceFolderName) {
                    details.push(new ReceiptDetailItem('Workspace', element.record.workspaceFolderName, 'folder'));
                }
                details.push(new ReceiptDetailItem('Author', r.commit?.author?.name || '—', 'person'));
                if (r.commit?.committer?.name) {
                    details.push(new ReceiptDetailItem('Committer', r.commit.committer.name, 'person'));
                }
                details.push(new ReceiptDetailItem('Authorship', authorshipClass(r), 'tag'));
                const tier = getReceiptEvidenceTier(r, artifacts);
                details.push(new ReceiptDetailItem('Evidence Tier', EVIDENCE_TIER_LABELS[tier], 'verified'));
                details.push(new ReceiptDetailItem('Review Status', getReceiptReviewStatusLabel(element.record.review, hasAIInvolvement(r)), 'checklist'));
                details.push(new ReceiptDetailItem('AI Involvement', getAIInvolvementSummary(r), 'hubot'));
                details.push(new ReceiptDetailItem('AI Signals', getAISignalsSummary(r), 'search'));
                details.push(new ReceiptDetailItem('AI Authored', isAIAuthored(r) ? 'Yes' : 'No', 'hubot'));
                if (element.record.review?.reviewer) {
                    details.push(new ReceiptDetailItem('Reviewer', element.record.review.reviewer, 'person'));
                }
                if (element.record.review?.timestamp) {
                    details.push(new ReceiptDetailItem('Reviewed At', element.record.review.timestamp, 'calendar'));
                }
                if (element.record.review?.comment) {
                    details.push(new ReceiptDetailItem('Review Comment', element.record.review.comment, 'comment'));
                }
                details.push(new ReceiptDetailItem('Timestamp', r.timestamp || '—', 'calendar'));
                // v2 DAG binding
                if (r.commit?.tree_sha) {
                    details.push(new ReceiptDetailItem('Tree SHA', r.commit.tree_sha.slice(0, 12), 'list-tree'));
                }
                if (r.commit?.parent_shas && r.commit.parent_shas.length > 0) {
                    details.push(new ReceiptDetailItem('Parents', r.commit.parent_shas.map(s => s.slice(0, 8)).join(', '), 'git-merge'));
                }
                // Content hashes
                if (r.commit?.message_hash) {
                    details.push(new ReceiptDetailItem('Message Hash', r.commit.message_hash.slice(0, 23) + '\u2026', 'note'));
                }
                if (r.commit?.diff_hash) {
                    details.push(new ReceiptDetailItem('Diff Hash', r.commit.diff_hash.slice(0, 23) + '\u2026', 'diff'));
                }
            }

            if (element.subsectionKind === 'signals') {
                details.push(new ReceiptDetailItem('Signal Count', String(signalCount(r)), 'search'));
                const signals = r.ai_attestation?.signals_detected || [];
                details.push(new ReceiptDetailItem('Signals', signals.length > 0 ? signals.join(', ') : 'None', 'sparkle'));
                const botSignals = r.ai_attestation?.bot_signals_detected || [];
                if (botSignals.length > 0) {
                    details.push(new ReceiptDetailItem('Bot Signals', botSignals.join(', '), 'hubot'));
                }
                if (r.ai_attestation?.detection_method) {
                    details.push(new ReceiptDetailItem('Detection Method', r.ai_attestation.detection_method, 'symbol-method'));
                }
                if (r.extensions?.agent_attestation) {
                    const agent = getAgentAttestation(r) as Record<string, string>;
                    details.push(new ReceiptDetailItem('Agent Tool', agent.tool_id || '—', 'robot'));
                    if (agent.model_class) {
                        details.push(new ReceiptDetailItem('Model', agent.model_class, 'symbol-class'));
                    }
                    if (agent.confidence) {
                        details.push(new ReceiptDetailItem('Attestation Confidence', agent.confidence, 'pulse'));
                    }
                    if (agent.tool_version) {
                        details.push(new ReceiptDetailItem('Tool Version', agent.tool_version, 'versions'));
                    }
                    if (agent.run_context) {
                        details.push(new ReceiptDetailItem('Run Context', agent.run_context, 'server-environment'));
                    }
                }

            }

            if (element.subsectionKind === 'files') {
                const files = element.record.uiFiles || r.commit?.files || [];
                if (files.length === 0) {
                    details.push(new ReceiptDetailItem('Files', `${r.commit?.files_changed ?? 0} changed`, 'file'));
                } else {
                    for (const filePath of files) {
                        const repositoryRoot = element.record.workspaceFolderPath || path.dirname(element.record.uri.fsPath);
                        details.push(new ReceiptFileItem(filePath, vscode.Uri.file(path.join(repositoryRoot, filePath))));
                    }
                }
            }

            if (element.subsectionKind === 'editor-diffs') {
                const editor = getEditorProvenance(r);
                const repositoryRoot = element.record.workspaceFolderPath || path.dirname(element.record.uri.fsPath);
                const trackedFiles = new Map<string, EditorDiffEvent[]>();

                details.push(new ReceiptActionItem('Browse Attested Diffs', 'Open the pretty receipt viewer and scroll through all recorded attested file updates', 'preview', 'aiir.viewReceipt', [element.record.uri]));

                for (const rec of editor?.records ?? []) {
                    for (const file of rec.files ?? []) {
                        if (file.path) {
                            const events = trackedFiles.get(file.path) || [];
                            events.push({
                                beforeHash: file.beforeHash,
                                afterHash: file.afterHash,
                                command: rec.command,
                                source: rec.source,
                                promptKind: rec.promptKind,
                                createdAt: rec.createdAt,
                                baseCommitSha: rec.baseCommitSha,
                                sessionId: rec.sessionId,
                            });
                            trackedFiles.set(file.path, events);
                        }
                    }
                }

                for (const [filePath, events] of trackedFiles) {
                    const fileUri = vscode.Uri.file(path.join(repositoryRoot, filePath));
                    if (fs.existsSync(fileUri.fsPath)) {
                        details.push(new EditorDiffFileItem(element.record, filePath, fileUri, events));
                    } else {
                        details.push(new EditorDiffFileItem(element.record, filePath, undefined, events));
                    }
                }

                if (details.length === 0) {
                    details.push(new ReceiptDetailItem('Status', 'No file changes recorded', 'info'));
                }
            }

            if (element.subsectionKind === 'artifacts') {
                details.push(new ReceiptDetailItem('Receipt ID', r.receipt_id || '—', 'tag'));
                details.push(new ReceiptDetailItem('Content Hash', r.content_hash || '—', 'key'));
                if (artifacts.cborStatus === 'present') {
                    details.push(new ReceiptDetailItem('CBOR Sidecar', 'Present', 'package'));
                    if (artifacts.cborSize !== undefined) {
                        details.push(new ReceiptDetailItem('CBOR Size', formatBytes(artifacts.cborSize), 'file-binary'));
                    }
                    if (artifacts.cborHash) {
                        details.push(new ReceiptDetailItem('CBOR Hash', artifacts.cborHash.slice(0, 23) + '…', 'key'));
                    }
                    if (artifacts.cborUri) {
                        details.push(new ReceiptActionItem('Verify CBOR Integrity', 'Run CLI CBOR verification', 'beaker', 'aiir.verifyCbor', [element.record.uri]));
                    }
                } else {
                    details.push(new ReceiptDetailItem('CBOR Sidecar', 'Missing', 'package'));
                }
                if (artifacts.sigstoreStatus === 'present') {
                    details.push(new ReceiptDetailItem('Sigstore Bundle', 'Present', 'lock'));
                    if (artifacts.sigstoreSize !== undefined) {
                        details.push(new ReceiptDetailItem('Bundle Size', formatBytes(artifacts.sigstoreSize), 'file-binary'));
                    }
                    if (artifacts.sigstoreHash) {
                        details.push(new ReceiptDetailItem('Bundle Hash', artifacts.sigstoreHash.slice(0, 23) + '…', 'key'));
                    }
                    if (artifacts.sigstoreUri) {
                        details.push(new ReceiptActionItem('Verify Sigstore Signature', 'Run CLI signature verification', 'shield', 'aiir.verifySigstore', [element.record.uri]));
                    }
                } else {
                    details.push(new ReceiptDetailItem('Sigstore Bundle', 'Missing', 'lock'));
                }
            }

            if (element.subsectionKind === 'provenance') {
                details.push(new ReceiptDetailItem('Generator', r.provenance?.generator || '—', 'tools'));
                if (r.provenance?.tool) {
                    details.push(new ReceiptDetailItem('Tool URI', r.provenance.tool, 'link'));
                }
                details.push(new ReceiptDetailItem('Repository', r.provenance?.repository || '—', 'repo'));
                details.push(new ReceiptDetailItem('Schema', r.schema || '—', 'symbol-structure'));
                details.push(new ReceiptDetailItem('Version', r.version || '—', 'tag'));
            }

            if (element.subsectionKind === 'editor-provenance') {
                const editor = getEditorProvenance(r);
                const records = editor?.records ?? [];
                const firstRecord = records[0];
                const model = firstRecord ? [firstRecord.modelVendor, firstRecord.modelFamily].filter(Boolean).join(' ') : '';
                const commitMsg = r.commit?.subject?.split('\n')[0] || '—';

                // 1. Intent — what was the goal
                const intentDesc = firstRecord?.command || 'unknown';
                const categories: ReceiptExplorerNode[] = [];
                categories.push(new ProvenanceCategoryItem(element.record, 'intent', 'Intent', intentDesc, 'target'));

                // 2. AI Chat — which model assisted
                const chatDesc = model || editor?.toolId || 'no model recorded';
                categories.push(new ProvenanceCategoryItem(element.record, 'chat', 'AI Chat', chatDesc, 'comment-discussion'));

                // 3. Commit — final commit message
                categories.push(new ProvenanceCategoryItem(element.record, 'commit', 'Commit', commitMsg.slice(0, 60), 'git-commit'));

                return categories;
            }

            return details;
        }

        if (element instanceof EditorDiffFileItem) {
            const details: Array<ReceiptDetailItem | ReceiptActionItem> = [];
            const latest = element.events[element.events.length - 1];
            const recentEvents = element.events.slice().reverse();

            if (element.fileUri) {
                details.push(new ReceiptActionItem('Open File', 'Open the tracked file in the editor', 'go-to-file', 'aiir.openTreeFile', [element.fileUri]));
            }

            details.push(new ReceiptDetailItem('Latest Diff', summarizeEditorDiffHashes(latest?.beforeHash, latest?.afterHash), 'diff'));
            details.push(new ReceiptDetailItem('Recorded Updates', String(element.events.length), 'history'));
            details.push(new ReceiptDetailItem('Receipt Commit', getReceiptSubject(element.record.receipt), 'git-commit'));

            if (latest?.createdAt) {
                details.push(new ReceiptDetailItem('Latest Recorded', latest.createdAt, 'calendar'));
            }
            if (latest?.command) {
                details.push(new ReceiptDetailItem('Latest Command', latest.command, 'terminal'));
            }
            if (latest?.source) {
                details.push(new ReceiptDetailItem('Latest Source', latest.source, 'symbol-event'));
            }
            if (latest?.promptKind) {
                details.push(new ReceiptDetailItem('Prompt Kind', latest.promptKind, 'symbol-keyword'));
            }
            if (latest?.baseCommitSha) {
                details.push(new ReceiptDetailItem('Base Commit', latest.baseCommitSha.slice(0, 12), 'git-commit'));
            }

            recentEvents.forEach((event, index) => {
                const eventSummary = [
                    event.createdAt || 'unknown time',
                    event.command || event.source || 'update',
                    summarizeEditorDiffHashes(event.beforeHash, event.afterHash),
                ].join(' • ');
                details.push(new ReceiptDetailItem(`Update ${index + 1}`, eventSummary, 'history'));
            });

            return details;
        }

        if (element instanceof ProvenanceCategoryItem) {
            const { receipt: r } = element.record;
            const editor = getEditorProvenance(r);
            const records = editor?.records ?? [];
            const firstRecord = records[0];
            const items: ReceiptDetailItem[] = [];

            if (element.categoryKind === 'intent') {
                items.push(new ReceiptDetailItem('Command', firstRecord?.command || '—', 'terminal'));
                if (firstRecord?.source) {
                    items.push(new ReceiptDetailItem('Source', firstRecord.source, 'symbol-event'));
                }
                if (firstRecord?.promptKind) {
                    items.push(new ReceiptDetailItem('Prompt Kind', firstRecord.promptKind, 'symbol-keyword'));
                }
                if (firstRecord?.sessionId) {
                    items.push(new ReceiptDetailItem('Session', firstRecord.sessionId.slice(0, 8), 'key'));
                }
                if (editor?.mode) {
                    items.push(new ReceiptDetailItem('Mode', editor.mode, 'gear'));
                }
            }

            if (element.categoryKind === 'chat') {
                if (editor?.toolId) {
                    items.push(new ReceiptDetailItem('Editor Tool', editor.toolId, 'robot'));
                }
                if (firstRecord?.modelVendor) {
                    items.push(new ReceiptDetailItem('Vendor', firstRecord.modelVendor, 'organization'));
                }
                if (firstRecord?.modelFamily) {
                    items.push(new ReceiptDetailItem('Model', firstRecord.modelFamily, 'hubot'));
                }
                const recordCount = records.length;
                items.push(new ReceiptDetailItem('Interactions', `${recordCount} provenance record${recordCount === 1 ? '' : 's'}`, 'history'));
            }

            if (element.categoryKind === 'commit') {
                const commit = r.commit;
                items.push(new ReceiptDetailItem('Subject', commit?.subject?.split('\n')[0] || '—', 'git-commit'));
                items.push(new ReceiptDetailItem('SHA', commit?.sha?.slice(0, 12) || '—', 'symbol-key'));
                items.push(new ReceiptDetailItem('Author', commit?.author?.name || '—', 'person'));
                if (commit?.author?.email) {
                    items.push(new ReceiptDetailItem('Email', commit.author.email, 'mail'));
                }
                if (firstRecord?.createdAt) {
                    items.push(new ReceiptDetailItem('Recorded', firstRecord.createdAt, 'calendar'));
                }
            }

            return items;
        }

        return [];
    }

    private getRepositoryKey(record: ReceiptRecord): string {
        return record.workspaceFolderPath || path.dirname(record.uri.fsPath);
    }

    private getRepositoryLabel(records: ReceiptRecord[]): string {
        return records[0]?.workspaceFolderName || path.basename(this.getRepositoryKey(records[0]));
    }

    private getRepositoryItems(): ReceiptExplorerNode[] {
        const grouped = new Map<string, ReceiptRecord[]>();

        for (const record of this.receipts) {
            const key = this.getRepositoryKey(record);
            const existing = grouped.get(key) || [];
            existing.push(record);
            grouped.set(key, existing);
        }

        const order = getAccessibleWorkspaceFolders().map(folder => folder.uri.fsPath);
        const allPaths = Array.from(new Set([
            ...order,
            ...Array.from(grouped.keys()),
        ])).sort((left, right) => {
            const leftIndex = order.indexOf(left);
            const rightIndex = order.indexOf(right);
            if (leftIndex === -1 && rightIndex === -1) {
                return left.localeCompare(right);
            }
            if (leftIndex === -1) {
                return 1;
            }
            if (rightIndex === -1) {
                return -1;
            }
            return leftIndex - rightIndex;
        });

        // Only show repos that have a receipt ledger or discovered receipts.
        const repositoryPaths = allPaths.filter(repositoryPath => shouldShowRepository(this.getRepositoryStateByPath(repositoryPath)));

        const items: ReceiptExplorerNode[] = repositoryPaths.map(repositoryPath => {
            const records = grouped.get(repositoryPath) || [];
            const state = this.repositoryState.get(repositoryPath);
            const label = state?.folder.name || this.getRepositoryLabel(records);
            return new ReceiptRepositoryItem(
                label,
                repositoryPath,
                records,
                this.buildStats(records),
                state,
                state?.branch,
                state?.headSha,
            );
        });

        const unconfiguredCount = allPaths.length - repositoryPaths.length;
        const manageRepositoriesDetail = unconfiguredCount > 0
            ? `${unconfiguredCount} workspace folder${unconfiguredCount === 1 ? '' : 's'} not yet enabled`
            : `${repositoryPaths.length} workspace folder${repositoryPaths.length === 1 ? '' : 's'} active in this workspace`;
        if (getShowAdvancedCommands()) {
            items.push(new ReceiptActionItem(
                'Manage Repositories',
                manageRepositoriesDetail,
                'settings-gear',
                'aiir.manageRepositories',
            ));
        }

        return items;
    }

    private buildEmptyRepositoryItems(repositoryPath?: string): ReceiptExplorerNode[] {
        const state = repositoryPath ? this.getRepositoryStateByPath(repositoryPath) : undefined;
        const uri = state?.folder.uri;
        const primaryLabel = !state?.aiirDirExists
            ? 'Set up receipts'
            : !isRepositoryFullyReady(state)
                ? 'Continue status check'
                : 'Open commit status';
        const primaryCommand = 'aiir.readinessCheck';
        const primaryDetail = !state?.aiirDirExists
            ? 'Open the readiness check to get started'
            : !isRepositoryFullyReady(state)
                ? 'Open the readiness check to finish repository setup'
                : 'Open the readiness check for setup details and next steps';
        const items: ReceiptExplorerNode[] = [
            new ReceiptActionItem(primaryLabel, primaryDetail, 'checklist', primaryCommand, uri ? [uri] : undefined),
        ];

        if (state?.cliAvailable && !state.aiirDirExists) {
            items.push(new ReceiptActionItem('Initialize repository', 'Create .aiir scaffolding for this repository', 'new-folder', 'aiir.initializeRepo', uri ? [uri] : undefined));
        }

        items.push(new ReceiptDetailItem('AIIR setup', state?.aiirDirExists ? 'Initialized' : 'Missing', state?.aiirDirExists ? 'repo' : 'new-folder'));
        items.push(new ReceiptDetailItem('Policy', state?.policyExists ? 'Configured' : 'Missing', state?.policyExists ? 'json' : 'warning'));
        items.push(new ReceiptDetailItem('Receipts', state?.hasLedger ? 'Ledger ready' : 'No receipts yet', state?.hasLedger ? 'verified' : 'circle-outline'));

        return items;
    }

    private static readonly RECEIPT_RECENT_LIMIT = 10;

    private buildRecentList(records: ReceiptRecord[], repositoryPath?: string): ReceiptExplorerNode[] {
        const activeRecords = getActiveReceiptRecords(records);
        const sorted = [...activeRecords].sort(compareReceipts);
        const recent = sorted.slice(0, ReceiptExplorerProvider.RECEIPT_RECENT_LIMIT);
        const earlierCount = activeRecords.length - recent.length;

        const state = repositoryPath ? this.repositoryState.get(repositoryPath) : undefined;
        const headSha = state?.headSha;
        const needsAttention = recent.filter(record => !record.result.valid);
        const currentCommit = headSha
            ? recent.filter(record => record.result.valid && record.receipt.commit?.sha === headSha)
            : [];
        const recentHistory = recent.filter(record => !needsAttention.includes(record) && !currentCommit.includes(record));
        const items: ReceiptExplorerNode[] = [];

        if (needsAttention.length > 0) {
            items.push(new ReceiptSectionItem(
                'Needs Attention',
                needsAttention,
                'warning',
                `${needsAttention.length} receipt${needsAttention.length === 1 ? '' : 's'} need follow-up`,
            ));
        }

        if (currentCommit.length > 0) {
            items.push(new ReceiptSectionItem(
                'Current Commit',
                currentCommit,
                'git-commit',
                'HEAD is covered',
                false,
            ));
        }

        if (recentHistory.length > 0) {
            items.push(new ReceiptSectionItem(
                currentCommit.length > 0 ? 'Recent History' : 'Compliant',
                recentHistory,
                currentCommit.length > 0 ? 'history' : 'verified',
                currentCommit.length > 0
                    ? `${recentHistory.length} recent receipt${recentHistory.length === 1 ? '' : 's'}`
                    : `${recentHistory.length} compliant receipt${recentHistory.length === 1 ? '' : 's'}`,
                currentCommit.length === 0,
            ));
        }

        if (earlierCount > 0) {
            const uri = state?.folder.uri;
            items.push(new ReceiptActionItem(
                `${earlierCount} earlier commit${earlierCount === 1 ? '' : 's'}`,
                'Open the full summary view',
                'archive',
                'aiir.showSummary',
                uri ? [uri] : undefined,
            ));
        }

        return items;
    }

    private buildReceiptSubsections(record: ReceiptRecord): ReceiptSubsectionItem[] {
        const receipt = record.receipt;
        const files = record.uiFiles || receipt.commit?.files || [];
        const artifactsLabel = `${record.artifacts.cborStatus === 'present' ? 'CBOR' : 'No CBOR'} • ${record.artifacts.sigstoreStatus === 'present' ? 'Signed' : 'Unsigned'}`;
        const overviewLabel = `${receipt.commit?.author?.name || 'Unknown'} • ${formatReceiptTimestamp(receipt.timestamp)}`;

        const editor = getEditorProvenance(receipt);
        const editorFileCount = editor?.records?.reduce((sum, rec) => sum + (rec.files?.length ?? 0), 0) ?? 0;
        const subsections: ReceiptSubsectionItem[] = [
            new ReceiptSubsectionItem(record, 'overview', 'Overview', overviewLabel, 'info'),
            new ReceiptSubsectionItem(record, 'signals', 'Signals', `${signalCount(receipt)} signal${signalCount(receipt) === 1 ? '' : 's'} • ${authorshipClass(receipt)}`, 'search'),
            new ReceiptSubsectionItem(record, 'files', 'Files', files.length > 0 ? `${files.length} listed` : `${receipt.commit?.files_changed ?? 0} changed`, 'files'),
        ];
        if (hasEditorProvenance(receipt)) {
            subsections.push(new ReceiptSubsectionItem(record, 'editor-diffs', 'Editor Diffs', `${editorFileCount} file${editorFileCount === 1 ? '' : 's'} tracked`, 'diff'));
            subsections.push(new ReceiptSubsectionItem(record, 'editor-provenance', 'Editor Provenance', `${editorFileCount} file${editorFileCount === 1 ? '' : 's'} tracked`, 'wand'));
        }
        subsections.push(
            new ReceiptSubsectionItem(record, 'artifacts', 'Artifacts', artifactsLabel, 'package'),
            new ReceiptSubsectionItem(record, 'provenance', 'Provenance', receipt.provenance?.generator || 'Generator details', 'repo'),
        );
        return subsections;
    }

    private getReceipts(folder?: vscode.WorkspaceFolder): ReceiptRecord[] {
        if (!folder) {
            return this.receipts;
        }

        return this.receipts.filter(record => isPathInside(folder.uri.fsPath, record.uri.fsPath));
    }

    /** Public accessor for cross-provider queries (e.g. commit explorer overlay). */
    getAllReceipts(): ReceiptRecord[] {
        return this.receipts;
    }

    private buildStats(receipts: ReceiptRecord[]): ReceiptStats {
        const activeReceipts = getActiveReceiptRecords(receipts);
        const total = activeReceipts.length;
        const valid = activeReceipts.filter(r => r.result.valid).length;
        const invalid = total - valid;
        const aiAuthored = activeReceipts.filter(r => isAIAuthored(r.receipt)).length;
        const cborPresent = activeReceipts.filter(r => r.artifacts.cborStatus === 'present').length;
        const sigstorePresent = activeReceipts.filter(r => r.artifacts.sigstoreStatus === 'present').length;
        let tierSigned = 0;
        let tierProvable = 0;
        let tierHeuristic = 0;
        let tierUnsigned = 0;
        for (const r of activeReceipts) {
            switch (getReceiptEvidenceTier(r.receipt, r.artifacts)) {
                case 'signed': tierSigned++; break;
                case 'provable': tierProvable++; break;
                case 'heuristic': tierHeuristic++; break;
                case 'unsigned': tierUnsigned++; break;
            }
        }
        return { total, valid, invalid, aiAuthored, cborPresent, sigstorePresent, tierSigned, tierProvable, tierHeuristic, tierUnsigned };
    }

    isMultiRoot(): boolean {
        return (vscode.workspace.workspaceFolders?.length || 0) > 1;
    }

    getFolderStats(): Map<string, ReceiptStats> {
        const grouped = new Map<string, ReceiptRecord[]>();

        for (const record of this.receipts) {
            const name = record.workspaceFolderName || path.basename(record.workspaceFolderPath || path.dirname(record.uri.fsPath));
            const existing = grouped.get(name) || [];
            existing.push(record);
            grouped.set(name, existing);
        }

        return new Map(Array.from(grouped.entries()).map(([name, receipts]) => [name, this.buildStats(receipts)]));
    }

    getStats(folder?: vscode.WorkspaceFolder): ReceiptStats {
        return this.buildStats(this.getReceipts(folder));
    }

    hasReceiptForCommit(commitSha: string): boolean {
        return this.receipts.some(r => r.receipt.commit?.sha === commitSha);
    }

    getReceiptForCommit(commitSha: string, folder?: vscode.WorkspaceFolder): ReceiptRecord | undefined {
        return getActiveReceiptForCommit(this.getReceipts(folder), commitSha);
    }

    getReceiptByUri(uri: vscode.Uri, folder?: vscode.WorkspaceFolder): ReceiptRecord | undefined {
        return this.getReceipts(folder).find(r => r.uri.toString() === uri.toString());
    }

    getLatestReceipt(folder?: vscode.WorkspaceFolder): ReceiptRecord | undefined {
        return [...getActiveReceiptRecords(this.getReceipts(folder))].sort(compareReceiptFreshness)[0];
    }
    getRecentReceipts(limit = 6, folder?: vscode.WorkspaceFolder): ReceiptRecord[] {
        return [...getActiveReceiptRecords(this.getReceipts(folder))].sort(compareReceiptFreshness).slice(0, limit);
    }
}

type HomeHealthTone = 'ok' | 'warn' | 'err';

interface HomeHealthDot {
    label: 'Repo' | 'This Commit' | 'Proof' | 'Auto';
    stateLabel: string;
    detail: string;
    tone: HomeHealthTone;
    commandId: string;
    args?: unknown[];
}

function getHomeHealthDotIcon(tone: HomeHealthTone): vscode.ThemeIcon {
    const colorId = tone === 'ok'
        ? 'testing.iconPassed'
        : tone === 'warn'
            ? 'editorWarning.foreground'
            : 'testing.iconFailed';
    return new vscode.ThemeIcon('circle-filled', new vscode.ThemeColor(colorId));
}

function getHomeHealthDots(
    trustState: ResolvedTrustState,
    targetArgs: unknown[],
    latestReceiptArgs: unknown[],
): HomeHealthDot[] {
    const repoDot: HomeHealthDot = !trustState.workspaceOpen
        ? {
            label: 'Repo',
            stateLabel: 'no folder',
            detail: 'Open a repository so AIIR can inspect the current workspace.',
            tone: 'err',
            commandId: 'workbench.action.files.openFolder',
        }
        : trustState.accessBlocked
            ? {
                label: 'Repo',
                stateLabel: 'blocked',
                detail: 'Workspace isolation or the allowlist is blocking this repository.',
                tone: 'err',
                commandId: 'aiir.securityPosture',
            }
            : {
                label: 'Repo',
                stateLabel: 'ready',
                detail: 'AIIR can read the current repository.',
                tone: 'ok',
                commandId: 'aiir.readinessCheck',
                args: targetArgs,
            };

    const recordDot: HomeHealthDot = !trustState.workspaceOpen
        ? {
            label: 'This Commit',
            stateLabel: 'blocked',
            detail: 'Open a repository before you can record commit activity.',
            tone: 'err',
            commandId: 'workbench.action.files.openFolder',
        }
        : trustState.accessBlocked
            ? {
                label: 'This Commit',
                stateLabel: 'blocked',
                detail: 'Fix workspace access before AIIR can record this repository.',
                tone: 'err',
                commandId: 'aiir.securityPosture',
            }
            : !trustState.cliAvailable
                ? {
                    label: 'This Commit',
                    stateLabel: 'install CLI',
                    detail: 'Install the AIIR CLI before recording commit activity.',
                    tone: 'err',
                    commandId: 'aiir.installCliNow',
                }
                : !trustState.repoInitialized
                    ? {
                        label: 'This Commit',
                        stateLabel: 'initialize',
                        detail: 'Initialize this repository before recording commit activity.',
                        tone: 'err',
                        commandId: 'aiir.initializeRepo',
                        args: targetArgs,
                    }
                    : trustState.headReceiptStatus === 'present'
                        ? {
                            label: 'This Commit',
                            stateLabel: 'recorded',
                            detail: 'The latest commit already has a record.',
                            tone: 'ok',
                            commandId: trustState.latestReceipt ? 'aiir.viewReceipt' : 'aiir.generatePreferred',
                            args: trustState.latestReceipt ? latestReceiptArgs : targetArgs,
                        }
                        : {
                            label: 'This Commit',
                            stateLabel: 'needs record',
                            detail: 'Create a record for the current commit.',
                            tone: 'warn',
                            commandId: 'aiir.generatePreferred',
                            args: targetArgs,
                        };

    const verifyDot: HomeHealthDot = !trustState.workspaceOpen
        ? {
            label: 'Proof',
            stateLabel: 'blocked',
            detail: 'Open a repository before AIIR can verify receipts.',
            tone: 'err',
            commandId: 'workbench.action.files.openFolder',
        }
        : trustState.invalidReceiptCount > 0
            ? {
                label: 'Proof',
                stateLabel: 'needs repair',
                detail: 'One or more receipts failed verification. Review them now.',
                tone: 'err',
                commandId: 'aiir.verifyAll',
            }
            : trustState.receiptCount === 0
                ? {
                    label: 'Proof',
                    stateLabel: 'none yet',
                    detail: 'No receipts are present yet, so there is nothing to verify.',
                    tone: 'warn',
                    commandId: trustState.cliAvailable && trustState.repoInitialized ? 'aiir.generatePreferred' : 'aiir.readinessCheck',
                    args: trustState.cliAvailable && trustState.repoInitialized ? targetArgs : targetArgs,
                }
                : trustState.homeState === 'regulated-incomplete'
                    ? {
                        label: 'Proof',
                        stateLabel: 'weaker evidence',
                        detail: 'Receipts verify cleanly, but the evidence bar is below the configured target.',
                        tone: 'warn',
                        commandId: 'aiir.healthCheck',
                        args: targetArgs,
                    }
                    : {
                        label: 'Proof',
                        stateLabel: 'clean',
                        detail: 'The current receipt set is verifying cleanly.',
                        tone: 'ok',
                        commandId: trustState.latestReceipt ? 'aiir.viewReceipt' : 'aiir.verifyAll',
                        args: trustState.latestReceipt ? latestReceiptArgs : undefined,
                    };

    const autoDot: HomeHealthDot = !trustState.workspaceOpen
        ? {
            label: 'Auto',
            stateLabel: 'blocked',
            detail: 'Open a repository before AIIR can manage post-commit automation.',
            tone: 'err',
            commandId: 'workbench.action.files.openFolder',
        }
        : trustState.accessBlocked
            ? {
                label: 'Auto',
                stateLabel: 'blocked',
                detail: 'Fix workspace access before AIIR can manage automation for this repository.',
                tone: 'err',
                commandId: 'aiir.securityPosture',
            }
            : !trustState.cliAvailable || !trustState.repoInitialized
                ? {
                    label: 'Auto',
                    stateLabel: 'unavailable',
                    detail: 'Install the CLI and initialize the repository before enabling auto-receipting.',
                    tone: 'err',
                    commandId: !trustState.cliAvailable ? 'aiir.installCliNow' : 'aiir.initializeRepo',
                    args: !trustState.cliAvailable ? undefined : targetArgs,
                }
                : trustState.hookKind === 'managed'
                    ? {
                        label: 'Auto',
                        stateLabel: 'on',
                        detail: 'Managed auto-receipting is enabled. Click to turn it off.',
                        tone: 'ok',
                        commandId: 'aiir.disableAutoReceipting',
                        args: targetArgs,
                    }
                    : trustState.hookKind === 'custom'
                        ? {
                            label: 'Auto',
                            stateLabel: 'custom',
                            detail: 'A custom post-commit hook is present. Review the health check before changing it.',
                            tone: 'warn',
                            commandId: 'aiir.healthCheck',
                            args: targetArgs,
                        }
                        : {
                            label: 'Auto',
                            stateLabel: 'manual',
                            detail: 'Enable managed auto-receipting if you want new commits recorded automatically.',
                            tone: 'warn',
                            commandId: 'aiir.enableAutoReceipting',
                            args: targetArgs,
                        };

    return [repoDot, recordDot, verifyDot, autoDot];
}

function getHomeHealthTonePriority(tone: HomeHealthTone): number {
    return tone === 'err' ? 2 : tone === 'warn' ? 1 : 0;
}

function getHomeHealthSummaryText(trustState: ResolvedTrustState, stats: ReceiptStats): string {
    const scopeSuffix = trustState.repoName ? ` · ${trustState.repoName}` : '';

    switch (trustState.homeState) {
        case 'no-workspace':
            return `$(info) AIIR: Open a repository${scopeSuffix}`;
        case 'access-blocked':
            return `$(error) AIIR: Repo access blocked${scopeSuffix}`;
        case 'cli-missing':
            return `$(tools) AIIR: Install CLI${scopeSuffix}`;
        case 'not-initialized':
            return `$(repo-create) AIIR: Initialize repository${scopeSuffix}`;
        case 'ready-no-receipts':
            return `$(shield) AIIR: Ready to record${scopeSuffix}`;
        case 'head-missing':
            return `$(warning) AIIR: Record needed${scopeSuffix}${trustState.activeAITool ? ` · ${trustState.activeAITool}` : ''}`;
        case 'regulated-incomplete':
            return `$(warning) AIIR: Verify weaker evidence${scopeSuffix}`;
        case 'failing':
            return `$(error) AIIR: Verify needs repair${scopeSuffix}${stats.invalid > 0 ? ` · ${stats.invalid}` : ''}`;
        case 'healthy':
            return `$(verified-filled) AIIR: Current commit recorded${scopeSuffix}`;
    }
}

function buildStatusBarTooltip(trustState: ResolvedTrustState, stats: ReceiptStats): vscode.MarkdownString {
    const healthDots = getHomeHealthDots(trustState, [], trustState.latestReceipt ? [trustState.latestReceipt.uri] : []);
    const healthRows = healthDots
        .map(dot => `| ${dot.label} | ${dot.stateLabel} | ${dot.detail} |`)
        .join('\n');
    const message =
        `**AIIR Current Repository**\n\n` +
        `| Metric | Value |\n|---|---|\n` +
        `| Repository | ${trustState.repoName || '—'} |\n` +
        `| Branch | ${trustState.branch || '—'} |\n` +
        `${trustState.activeAITool ? `| Active AI Tool | ${trustState.activeAITool} |\n` : ''}` +
        `| Receipts | ${stats.total} total / ${stats.valid} clean / ${stats.invalid} need attention |\n` +
        `| HEAD Coverage | ${receiptLabel(trustState.headReceiptStatus)} |\n` +
        `| Post-Commit Hook | ${hookLabel(trustState.hookKind || 'missing')} |\n\n` +
        `**Health**\n\n` +
        `| Check | State | Next step |\n|---|---|---|\n` +
        `${healthRows}\n\n` +
        `Click to open the AIIR summary view.`;
    return new vscode.MarkdownString(message);
}

class HomeProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
    private cachedState?: ResolvedTrustState;
    private cachedHubState?: ResolvedHubState;
    private cachedFolder?: vscode.WorkspaceFolder;

    constructor(
        private readonly explorer: ReceiptExplorerProvider,
        private readonly output: vscode.OutputChannel,
        private readonly resolveHubState: () => Promise<ResolvedHubState>,
    ) { }

    async refresh(target?: vscode.Uri): Promise<void> {
        this.cachedFolder = target ? getDefaultWorkspaceFolderCandidate(target) : getDefaultWorkspaceFolderCandidate();
        this.cachedState = await getResolvedTrustState(this.explorer, target);
        this.cachedHubState = await this.resolveHubState();
        this._onDidChangeTreeData.fire();
    }

    getCurrentFolderPath(): string | undefined {
        return this.cachedFolder?.uri.fsPath;
    }

    getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: vscode.TreeItem): Promise<vscode.TreeItem[]> {
        if (element) {
            return [];
        }

        if (!this.cachedState) {
            this.cachedFolder = getDefaultWorkspaceFolderCandidate();
            this.cachedState = await getResolvedTrustState(this.explorer);
            this.cachedHubState = await this.resolveHubState();
        }

        const trustState = this.cachedState;
        const hubState = this.cachedHubState;
        const card = trustState.primaryCard;
        const items: vscode.TreeItem[] = [];
        const selectedFolder = this.cachedFolder || getDefaultWorkspaceFolderCandidate();
        const targetArgs = selectedFolder ? [selectedFolder.uri] : [];
        const latestReceiptArgs = trustState.latestReceipt ? [trustState.latestReceipt.uri] : [];

        // State headline
        const stateItem = new vscode.TreeItem(card.headline, vscode.TreeItemCollapsibleState.None);
        stateItem.description = trustState.repoName
            ? `${trustState.repoName}${trustState.branch ? ` · ${trustState.branch}` : ''}`
            : '';
        stateItem.iconPath = new vscode.ThemeIcon(
            trustState.level === 'good' ? 'verified-filled' : trustState.level === 'warn' ? 'warning' : 'info',
        );
        stateItem.tooltip = card.detail;
        items.push(stateItem);

        const healthSummary = new vscode.TreeItem('Current repository status', vscode.TreeItemCollapsibleState.None);
        healthSummary.iconPath = new vscode.ThemeIcon('info');
        healthSummary.description = 'Repo · This Commit · Proof · Auto';
        healthSummary.tooltip = 'Green means ready, yellow means usable but incomplete, and red means blocked or broken.';
        items.push(healthSummary);

        for (const dot of getHomeHealthDots(trustState, targetArgs, latestReceiptArgs)) {
            const dotItem = new vscode.TreeItem(dot.label, vscode.TreeItemCollapsibleState.None);
            dotItem.iconPath = getHomeHealthDotIcon(dot.tone);
            dotItem.description = dot.stateLabel;
            dotItem.tooltip = dot.detail;
            dotItem.command = { command: dot.commandId, title: dot.label, arguments: dot.args };
            items.push(dotItem);
        }

        if (hubState) {
            const hubItem = new vscode.TreeItem(`Hub: ${hubState.stateLabel}`, vscode.TreeItemCollapsibleState.None);
            hubItem.iconPath = new vscode.ThemeIcon(
                hubState.entitlementState === 'paidActive' || hubState.entitlementState === 'trialActive'
                    ? 'cloud'
                    : hubState.entitlementState === 'connectionError'
                        ? 'cloud-offline'
                        : 'warning',
            );
            hubItem.description = hubState.offerFamily === 'local_free' ? 'local-first' : hubState.offerFamily.replaceAll('_', ' ');
            hubItem.tooltip = hubState.stateDetail;
            hubItem.command = { command: hubState.primaryActionCommandId, title: hubState.primaryActionLabel };
            items.push(hubItem);
        }

        // Primary action
        const primaryArgs = card.primaryAction.commandId === 'aiir.viewReceipt' && trustState.latestReceipt
            ? latestReceiptArgs
            : [];
        const actionItem = new vscode.TreeItem(card.primaryAction.label, vscode.TreeItemCollapsibleState.None);
        actionItem.iconPath = new vscode.ThemeIcon('sparkle');
        actionItem.command = { command: card.primaryAction.commandId, title: card.primaryAction.label, arguments: primaryArgs };
        items.push(actionItem);

        // Secondary action (if present)
        if (card.secondaryAction) {
            const secondaryItem = new vscode.TreeItem(card.secondaryAction.label, vscode.TreeItemCollapsibleState.None);
            secondaryItem.iconPath = new vscode.ThemeIcon('gear');
            secondaryItem.command = { command: card.secondaryAction.commandId, title: card.secondaryAction.label };
            items.push(secondaryItem);
        }

        const setupItem = new vscode.TreeItem('Commit Status', vscode.TreeItemCollapsibleState.None);
        setupItem.iconPath = new vscode.ThemeIcon('checklist');
        setupItem.command = { command: 'aiir.readinessCheck', title: 'Commit Status', arguments: targetArgs };
        items.push(setupItem);

        if (trustState.workspaceOpen) {
            const healthItem = new vscode.TreeItem('Health Check', vscode.TreeItemCollapsibleState.None);
            healthItem.iconPath = new vscode.ThemeIcon('pulse');
            healthItem.command = { command: 'aiir.healthCheck', title: 'Health Check', arguments: targetArgs };
            items.push(healthItem);
        }

        return items;
    }
}

// ── Status Bar ────────────────────────────────────────────────────────

class StatusBarManager {
    private item: vscode.StatusBarItem;

    constructor() {
        this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
        this.item.command = 'aiir.showSummary';
        this.item.name = 'AIIR Receipts';
    }

    async refresh(explorer: ReceiptExplorerProvider): Promise<void> {
        const stats = explorer.getStats();
        const trustState = await getResolvedTrustState(explorer);
        await vscode.commands.executeCommand('setContext', 'aiir.headReceiptMissing', trustState.headReceiptStatus === 'missing');
        await vscode.commands.executeCommand('setContext', 'aiir.headReceiptPresent', trustState.headReceiptStatus === 'present');
        await vscode.commands.executeCommand('setContext', 'aiir.activeAIToolDetected', !!trustState.activeAITool);
        await vscode.commands.executeCommand('setContext', 'aiir.autoReceiptingManaged', trustState.hookKind === 'managed');
        await vscode.commands.executeCommand('setContext', 'aiir.cliAvailable', trustState.cliAvailable === true);
        this.update(stats, trustState);
    }

    update(stats: ReceiptStats, trustState: ResolvedTrustState) {
        this.item.text = getHomeHealthSummaryText(trustState, stats);
        this.item.tooltip = buildStatusBarTooltip(trustState, stats);

        const highestTone = getHomeHealthDots(trustState, [], trustState.latestReceipt ? [trustState.latestReceipt.uri] : [])
            .reduce<HomeHealthTone>((current, dot) => {
                return getHomeHealthTonePriority(dot.tone) > getHomeHealthTonePriority(current) ? dot.tone : current;
            }, 'ok');

        this.item.backgroundColor = highestTone === 'err'
            ? new vscode.ThemeColor('statusBarItem.errorBackground')
            : highestTone === 'warn'
                ? new vscode.ThemeColor('statusBarItem.warningBackground')
                : undefined;

        this.item.show();
    }

    dispose() {
        this.item.dispose();
    }
}

// ── Diagnostics ───────────────────────────────────────────────────────

function updateDiagnostics(
    diagnosticCollection: vscode.DiagnosticCollection,
    uri: vscode.Uri,
    receipt: ReceiptData,
    result: VerifyResult,
) {
    if (result.valid) {
        diagnosticCollection.delete(uri);
        return;
    }

    const diagnostics: vscode.Diagnostic[] = result.errors.map(error => {
        const range = new vscode.Range(0, 0, 0, 1);
        const diag = new vscode.Diagnostic(
            range,
            `AIIR: ${error}`,
            vscode.DiagnosticSeverity.Error,
        );
        diag.source = 'AIIR';
        diag.code = 'receipt-integrity';
        return diag;
    });

    diagnosticCollection.set(uri, diagnostics);
}

// ── CodeLens Provider ─────────────────────────────────────────────────

class ReceiptCodeLensProvider implements vscode.CodeLensProvider {
    private _onDidChangeCodeLenses = new vscode.EventEmitter<void>();
    readonly onDidChangeCodeLenses = this._onDidChangeCodeLenses.event;

    refresh() {
        this._onDidChangeCodeLenses.fire();
    }

    provideCodeLenses(document: vscode.TextDocument): vscode.CodeLens[] {
        if (!isUriAccessible(document.uri)) {
            return [];
        }

        if (!document.fileName.endsWith('.aiir.json') &&
            !document.uri.fsPath.includes('.receipts') &&
            !document.uri.fsPath.includes('.aiir')) {
            return [];
        }

        try {
            const receipt = JSON.parse(document.getText());
            if (!isSupportedReceiptDocument(receipt)) { return []; }

            const result = verifyReceipt(receipt);
            const range = new vscode.Range(0, 0, 0, 0);
            const lenses: vscode.CodeLens[] = [];

            if (result.valid) {
                lenses.push(new vscode.CodeLens(range, {
                    title: '✅ Receipt Verified — integrity intact',
                    command: 'aiir.verifyFile',
                }));
            } else {
                lenses.push(new vscode.CodeLens(range, {
                    title: `❌ Receipt INVALID — ${result.errors.join(', ')}`,
                    command: 'aiir.verifyFile',
                }));
            }

            // Show key receipt info inline
            if (receipt.type === 'aiir.commit_receipt') {
                const isAI = isAIAuthored(receipt);
                const signals = signalCount(receipt);
                const sha = receipt.commit?.sha?.slice(0, 8) || '?';
                lenses.push(new vscode.CodeLens(range, {
                    title: `${isAI ? '🤖 AI-authored' : '👤 Human-authored'} · ${signals} signals · commit ${sha}`,
                    command: '',
                }));
            } else {
                const tokenCount = Array.isArray(receipt.tokens) ? receipt.tokens.length : 0;
                const granularity = typeof receipt.granularity === 'string' ? receipt.granularity : '?';
                const modelFingerprint = typeof receipt.model_fingerprint === 'string'
                    ? receipt.model_fingerprint.slice(0, 12)
                    : '?';
                lenses.push(new vscode.CodeLens(range, {
                    title: `🧠 Inference receipt · ${tokenCount} tokens · ${granularity} · ${modelFingerprint}`,
                    command: '',
                }));
            }

            if (receipt.type === 'aiir.commit_receipt' && receipt.extensions?.sigstore) {
                lenses.push(new vscode.CodeLens(range, {
                    title: '🔐 Sigstore signed',
                    command: '',
                }));
            }

            return lenses;
        } catch {
            return [];
        }
    }
}

// ── File System Watcher ───────────────────────────────────────────────

function createReceiptWatcher(
    explorer: ReceiptExplorerProvider,
    statusBar: StatusBarManager,
    diagnosticCollection: vscode.DiagnosticCollection,
    onStatsChange?: (stats: ReceiptStats) => void,
    onTreeRefresh?: () => Promise<void>,
): vscode.Disposable {
    const disposables: vscode.Disposable[] = [];

    const handleChange = async (uri: vscode.Uri) => {
        if (!isUriAccessible(uri)) {
            diagnosticCollection.delete(uri);
            return;
        }

        if (!uri.fsPath.includes('.aiir') && !uri.fsPath.includes('.receipts') && !uri.fsPath.endsWith('.aiir.json')) {
            return;
        }
        const receipt = await loadReceipt(uri);
        if (receipt) {
            const result = verifyReceipt(receipt);
            updateDiagnostics(diagnosticCollection, uri, receipt, result);
        }
        await explorer.refresh();
        const stats = explorer.getStats();
        await statusBar.refresh(explorer);
        onStatsChange?.(stats);
        await onTreeRefresh?.();
    };

    const handleSidecarChange = async () => {
        await explorer.refresh();
        const stats = explorer.getStats();
        await statusBar.refresh(explorer);
        onStatsChange?.(stats);
        await onTreeRefresh?.();
    };

    const handleAiirStateChange = async () => {
        // Invalidate cached blame receipt indexes when ledger changes
        for (const folder of getAccessibleWorkspaceFolders()) {
            invalidateReceiptIndex(folder.uri.fsPath);
        }
        await explorer.refresh();
        const stats = explorer.getStats();
        await statusBar.refresh(explorer);
        onStatsChange?.(stats);
        await onTreeRefresh?.();
    };

    for (const folder of getAccessibleWorkspaceFolders()) {
        const watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(folder, '**/*.{aiir.json,json}'));
        const sidecarWatcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(folder, '**/*.{cbor,sigstore}'));
        const aiirStateWatcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(folder, '.aiir/**'));

        watcher.onDidCreate(handleChange);
        watcher.onDidChange(handleChange);
        watcher.onDidDelete(async uri => {
            diagnosticCollection.delete(uri);
            await explorer.refresh();
            const stats = explorer.getStats();
            await statusBar.refresh(explorer);
            onStatsChange?.(stats);
            await onTreeRefresh?.();
        });

        sidecarWatcher.onDidCreate(handleSidecarChange);
        sidecarWatcher.onDidChange(handleSidecarChange);
        sidecarWatcher.onDidDelete(handleSidecarChange);

        aiirStateWatcher.onDidCreate(handleAiirStateChange);
        aiirStateWatcher.onDidChange(handleAiirStateChange);
        aiirStateWatcher.onDidDelete(handleAiirStateChange);

        disposables.push(watcher, sidecarWatcher, aiirStateWatcher);
    }

    return vscode.Disposable.from(...disposables);
}

async function createGitStateWatcher(onRepositoryChange: () => Promise<void>): Promise<vscode.Disposable> {
    const disposables: vscode.Disposable[] = [];
    let timer: NodeJS.Timeout | undefined;

    const scheduleRefresh = () => {
        if (timer) {
            clearTimeout(timer);
        }
        timer = setTimeout(() => {
            void onRepositoryChange();
        }, 200);
    };

    for (const folder of getAccessibleWorkspaceFolders()) {
        const gitDir = await resolveGitDir(folder);
        if (!gitDir) {
            continue;
        }

        const patterns = ['HEAD', 'index', 'packed-refs', 'refs/heads/**', 'hooks/post-commit'];
        for (const pattern of patterns) {
            const watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(gitDir, pattern));
            watcher.onDidCreate(scheduleRefresh);
            watcher.onDidChange(scheduleRefresh);
            watcher.onDidDelete(scheduleRefresh);
            disposables.push(watcher);
        }
    }

    disposables.push(new vscode.Disposable(() => {
        if (timer) {
            clearTimeout(timer);
        }
    }));

    return vscode.Disposable.from(...disposables);
}

// ── Extension Activation ──────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext) {
    const output = vscode.window.createOutputChannel('AIIR');
    context.subscriptions.push(output);
    const walkthroughId = `${context.extension.id}#aiirGettingStarted`;
    const marketplaceCaptureSurface = process.env.AIIR_MARKETPLACE_CAPTURE_SURFACE as MarketplaceCaptureSurface | undefined;
    const marketplaceCaptureReadyFile = process.env.AIIR_MARKETPLACE_CAPTURE_READY_FILE;

    // Diagnostics collection
    const diagnosticCollection = vscode.languages.createDiagnosticCollection('aiir');
    context.subscriptions.push(diagnosticCollection);

    // Sidebar views
    const explorer = new ReceiptExplorerProvider();
    const homeProvider = new HomeProvider(explorer, output, async () => (await getResolvedHubState(context, output)).resolved);
    const homeTreeView = vscode.window.createTreeView('aiir.homeView', { treeDataProvider: homeProvider });
    context.subscriptions.push(homeTreeView);
    const receiptTreeView = vscode.window.createTreeView('aiir.receiptExplorer', {
        treeDataProvider: explorer,
        showCollapseAll: true,
    });
    receiptTreeView.message = getExplorerMessage();
    context.subscriptions.push(receiptTreeView);
    receiptTreeView.onDidChangeSelection(async event => {
        const selected = event.selection[0];
        if (!selected) {
            return;
        }

        let folder: vscode.WorkspaceFolder | undefined;
        if (selected instanceof ReceiptRepositoryItem) {
            folder = selected.repositoryPath
                ? explorer.getRepositoryStateByPath(selected.repositoryPath)?.folder
                : undefined;
        } else if (selected instanceof ReceiptTreeItem || selected instanceof ReceiptSubsectionItem || selected instanceof ProvenanceCategoryItem) {
            const folderPath = selected.record.workspaceFolderPath;
            folder = folderPath ? explorer.getRepositoryStateByPath(folderPath)?.folder : undefined;
        }

        if (!folder || homeProvider.getCurrentFolderPath() === folder.uri.fsPath) {
            return;
        }

        rememberWorkspaceFolder(folder);
        await homeProvider.refresh(folder.uri);
    });

    // ── Commit Explorer (commit-centric governance view) ──────────────
    const commitExplorerDeps: CommitExplorerDeps = {
        async getRecentCommits(folderPath: string, limit: number): Promise<CommitInfo[]> {
            try {
                const { stdout } = await execFileBounded('git', [
                    'log', `--max-count=${limit}`,
                    '--format=%H%x00%h%x00%s%x00%an%x00%aI',
                    '--name-status',
                ], { cwd: folderPath, maxBuffer: 1024 * 1024 });

                const commits: CommitInfo[] = [];
                let current: CommitInfo | undefined;
                for (const line of stdout.split(/\r?\n/)) {
                    const trimmed = line.trim();
                    if (!trimmed) {
                        // Git inserts a blank line between the format header
                        // and the --name-status block — just skip it.  The
                        // header-detection branch already pushes the previous
                        // commit when a new header arrives.
                        continue;
                    }
                    const parts = trimmed.split('\0');
                    if (parts.length >= 5) {
                        if (current) {
                            commits.push(current);
                        }
                        current = {
                            sha: parts[0],
                            shortSha: parts[1],
                            subject: parts[2],
                            authorName: parts[3],
                            authorDate: parts[4],
                            files: [],
                        };
                    } else if (current && /^[AMDRC]\t/.test(trimmed)) {
                        const [status, ...pathParts] = trimmed.split('\t');
                        const filePath = pathParts.join('\t');
                        if (filePath) {
                            current.files.push({ path: filePath, status });
                        }
                    }
                }
                if (current) {
                    commits.push(current);
                }
                return commits;
            } catch {
                return [];
            }
        },
        async getReceiptOverlay(folderPath: string, commitSha: string): Promise<CommitReceiptOverlay> {
            const records = explorer.getAllReceipts().filter(
                r => r.receipt.commit?.sha === commitSha && r.workspaceFolderPath === folderPath,
            );
            if (records.length === 0) {
                return {
                    hasReceipt: false,
                    valid: false,
                    sigstorePresent: false,
                    inLedger: false,
                    aiFiles: new Map(),
                };
            }
            const best = records[0];
            const editorProv = getEditorProvenance(best.receipt);
            const aiFileMap = new Map<string, CommitFileAI>();
            if (editorProv?.records) {
                for (const rec of editorProv.records) {
                    for (const file of rec.files ?? []) {
                        if (file.path) {
                            aiFileMap.set(file.path, {
                                aiAssisted: true,
                                tool: editorProv.toolId,
                                evidenceKind: 'provable',
                            });
                        }
                    }
                }
            }
            if (hasAIInvolvement(best.receipt)) {
                for (const filePath of best.uiFiles ?? []) {
                    if (!aiFileMap.has(filePath)) {
                        const agent = getAgentAttestation(best.receipt);
                        aiFileMap.set(filePath, {
                            aiAssisted: true,
                            tool: agent?.tool_id,
                            evidenceKind: 'heuristic',
                        });
                    }
                }
            }
            const tier = getEvidenceTier({
                sigstorePresent: best.artifacts.sigstoreStatus === 'present',
                inferenceReceiptPresent: hasInferenceBinding(best.receipt),
                editorProvenancePresent: hasEditorProvenance(best.receipt),
                aiInvolvementDetected: hasAIInvolvement(best.receipt),
            });
            return {
                hasReceipt: true,
                valid: best.result.valid,
                evidenceTier: tier,
                sigstorePresent: best.artifacts.sigstoreStatus === 'present',
                inLedger: best.artifacts.cborStatus === 'present',
                receiptUri: best.uri,
                aiFiles: aiFileMap,
                errorSummary: best.result.valid ? undefined : best.result.errors.join('; '),
            };
        },
        async getLedgerEntryCount(folderPath: string): Promise<number> {
            try {
                const ledgerPath = path.join(folderPath, '.aiir', 'receipts.jsonl');
                const content = await fs.promises.readFile(ledgerPath, 'utf-8');
                return content.split(/\r?\n/).filter(line => line.trim().length > 0).length;
            } catch {
                return 0;
            }
        },
        isListenerActive(): boolean {
            return copilotListener?.getState().active ?? false;
        },
    };
    const commitExplorer = new CommitExplorerProvider(commitExplorerDeps);
    const commitTreeView = vscode.window.createTreeView('aiir.commitExplorer', {
        treeDataProvider: commitExplorer,
        showCollapseAll: true,
    });
    context.subscriptions.push(commitTreeView);

    const writeMarketplaceCaptureMarker = async (status: 'ready' | 'error', detail?: Record<string, unknown>) => {
        if (!marketplaceCaptureReadyFile) {
            return;
        }

        await fs.promises.mkdir(path.dirname(marketplaceCaptureReadyFile), { recursive: true });
        await fs.promises.writeFile(
            marketplaceCaptureReadyFile,
            JSON.stringify({
                status,
                surface: marketplaceCaptureSurface,
                timestamp: new Date().toISOString(),
                ...(detail || {}),
            }, null, 2),
            'utf8',
        );
    };

    const pauseForCapture = async (ms = 700) => {
        await new Promise(resolve => setTimeout(resolve, ms));
    };

    const tryExecuteCommands = async (commands: Array<{ id: string; args?: unknown[] }>) => {
        for (const command of commands) {
            try {
                await vscode.commands.executeCommand(command.id, ...(command.args || []));
                return;
            } catch {
                // Keep going until one focus strategy succeeds.
            }
        }
    };

    const maybeRunMarketplaceCaptureSurface = async () => {
        if (!marketplaceCaptureSurface) {
            return;
        }

        try {
            await explorer.refresh();
            const defaultFolder = getDefaultWorkspaceFolderCandidate() || getAccessibleWorkspaceFolders()[0];
            const targetUri = defaultFolder?.uri;

            await homeProvider.refresh(targetUri);
            await commitExplorer.refresh(defaultFolder?.uri.fsPath);
            await vscode.commands.executeCommand('workbench.view.extension.aiir');
            await pauseForCapture(500);

            if (marketplaceCaptureSurface === 'coverage') {
                await tryExecuteCommands([
                    { id: 'aiir.commitExplorer.focus' },
                    { id: 'workbench.actions.treeView.aiir.commitExplorer.focus' },
                ]);

                const coverageItems = commitExplorer.getChildren();
                if (coverageItems[0]) {
                    try {
                        await commitTreeView.reveal(coverageItems[0], { focus: true, select: true, expand: true });
                    } catch {
                        // Focus command fallback is sufficient for capture mode.
                    }
                }
            } else if (marketplaceCaptureSurface === 'setup') {
                await vscode.commands.executeCommand('aiir.readinessCheck', targetUri);
            } else if (marketplaceCaptureSurface === 'receipts') {
                await tryExecuteCommands([
                    { id: 'aiir.receiptExplorer.focus' },
                    { id: 'workbench.actions.treeView.aiir.receiptExplorer.focus' },
                ]);

                const latestReceipt = defaultFolder ? explorer.getLatestReceipt(defaultFolder) : explorer.getLatestReceipt();
                if (!latestReceipt) {
                    throw new Error('No receipt is available for the Marketplace receipts capture');
                }

                await vscode.commands.executeCommand('aiir.viewReceipt', latestReceipt.uri);
            } else if (marketplaceCaptureSurface === 'control') {
                if (!targetUri) {
                    throw new Error('No repository is available for the Control Panel capture');
                }
                await vscode.commands.executeCommand('aiir.controlPanel', targetUri);
            } else if (marketplaceCaptureSurface === 'security') {
                await vscode.commands.executeCommand('aiir.securityPosture');
            } else if (marketplaceCaptureSurface === 'presets') {
                await vscode.commands.executeCommand('aiir.rolloutPresets', targetUri);
            } else {
                throw new Error(`Unknown Marketplace capture surface: ${marketplaceCaptureSurface}`);
            }

            await pauseForCapture(1200);
            await writeMarketplaceCaptureMarker('ready');
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            output.appendLine(`AIIR: Marketplace capture failed — ${message}`);
            await writeMarketplaceCaptureMarker('error', { message });
        }
    };

    // ── Passive AI edit listener (passive provenance capture) ─────────
    const listenerDeps: ListenerDeps = {
        async appendToProvenanceQueue(folderPath: string, record: ListenerCaptureRecord): Promise<void> {
            const queuePath = path.join(folderPath, '.aiir', PROVABLE_QUEUE_FILENAME);
            await runWithProvenanceQueueLock(queuePath, async () => {
                await fs.promises.mkdir(path.dirname(queuePath), { recursive: true });
                await fs.promises.appendFile(queuePath, JSON.stringify(record) + '\n', 'utf-8');
            });
        },
        getActiveAITools(): string[] {
            return detectEditorAITools().filter(t => t.isActive).map(t => t.toolName);
        },
        resolveWorkspaceFolder(doc: vscode.TextDocument): string | undefined {
            const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
            return folder?.uri.fsPath;
        },
        isExcluded(relativePath: string): boolean {
            const patterns = vscode.workspace.getConfiguration('aiir').get<string[]>('listener.excludePatterns', []);
            for (const pattern of patterns) {
                if (new vscode.RelativePattern('', pattern).pattern && minimatchLite(relativePath, pattern)) {
                    return true;
                }
            }
            return false;
        },
    };
    const copilotListener = new CopilotListener(listenerDeps);
    copilotListener.start();
    context.subscriptions.push(copilotListener);
    copilotListener.onDidChangeState(state => {
        commitTreeView.description = state.active
            ? `AI listener: on \u2022 ${state.totalCaptures} captures`
            : 'AI listener: off';
    });

    const updateSidebarChrome = (stats: ReceiptStats) => {
        receiptTreeView.description = stats.total === 0
            ? 'No receipts'
            : stats.invalid > 0
                ? `${stats.invalid} failed`
                : `${stats.total} verified`;
        receiptTreeView.badge = stats.total > 0
            ? { value: stats.total, tooltip: 'AIIR receipts in this workspace' }
            : undefined;
    };

    // Status bar
    const statusBar = new StatusBarManager();
    context.subscriptions.push({ dispose: () => statusBar.dispose() });

    // Diff content provider for commit file diffs
    const diffContentProvider = new class implements vscode.TextDocumentContentProvider {
        async provideTextDocumentContent(uri: vscode.Uri): Promise<string> {
            try {
                const params = JSON.parse(uri.query) as { commitSha: string; filePath: string; folderPath: string };
                const { stdout } = await execFileBounded('git', ['show', `${params.commitSha}:${params.filePath}`], {
                    cwd: params.folderPath,
                    maxBuffer: 4 * 1024 * 1024,
                });
                return stdout;
            } catch {
                return '';
            }
        }
    };
    context.subscriptions.push(
        vscode.workspace.registerTextDocumentContentProvider('aiir-diff', diffContentProvider),
    );

    // CodeLens
    const codeLensProvider = new ReceiptCodeLensProvider();
    context.subscriptions.push(
        vscode.languages.registerCodeLensProvider(
            [
                { pattern: '**/*.aiir.json' },
                { pattern: '**/.receipts/*.json' },
                { pattern: '**/.aiir-receipts/*.json' },
                { pattern: '**/.aiir/*.json' },
            ],
            codeLensProvider,
        ),
    );

    // File watcher
    const refreshCommitExplorerOverlays = async () => {
        const commitFolders = getAccessibleWorkspaceFolders();
        const preferredFolder = resolvePreferredWorkspaceFolderTarget(
            commitFolders.map(f => ({ name: f.name, fsPath: f.uri.fsPath, value: f })),
            undefined,
            recentWorkspaceFolderPath,
        );
        await commitExplorer.refresh(preferredFolder?.uri.fsPath);
    };
    let watcher = createReceiptWatcher(explorer, statusBar, diagnosticCollection, updateSidebarChrome, async () => {
        await homeProvider.refresh();
        await refreshCommitExplorerOverlays();
    });
    context.subscriptions.push({ dispose: () => watcher.dispose() });
    let gitWatcher: vscode.Disposable = vscode.Disposable.from();
    context.subscriptions.push({ dispose: () => gitWatcher.dispose() });
    let lastObservedHeadKey: string | undefined;
    let lastNudgedHeadKey: string | undefined;

    const getPendingAction = (): PendingAction | undefined => {
        const value = context.workspaceState.get<PendingAction | null>(PENDING_ACTION_KEY);
        return value || undefined;
    };

    const clearPendingAction = async (): Promise<void> => {
        await context.workspaceState.update(PENDING_ACTION_KEY, undefined);
    };

    const rememberPendingAction = async (action: PendingAction): Promise<void> => {
        await context.workspaceState.update(PENDING_ACTION_KEY, action);
    };

    const openSetupForPendingAction = async (action: PendingAction): Promise<void> => {
        await rememberPendingAction(action);
        const choice = await vscode.window.showInformationMessage(
            `AIIR: ${action.label} needs the AIIR CLI first. Run ${getCliInstallCommand()} and then continue.`,
            'Install CLI',
            'Copy Install Command',
            'Open Terminal',
            'See What\'s Missing',
            'Follow Quick Setup',
        );

        if (choice === 'Install CLI') {
            await vscode.commands.executeCommand('aiir.installCliNow');
        } else if (choice === 'Copy Install Command') {
            await copyCliInstallCommand();
        } else if (choice === 'Open Terminal') {
            await openCliInstallTerminal();
        } else if (choice === 'See What\'s Missing') {
            await openReadinessPanel();
        } else if (choice === 'Follow Quick Setup') {
            await vscode.commands.executeCommand('aiir.openWalkthrough');
        }
    };

    const maybeContinuePendingAction = async (options?: PendingActionContinuationOptions): Promise<boolean> => {
        const pending = getPendingAction();
        if (!pending) {
            return false;
        }

        const folder = getAccessibleWorkspaceFolders().find(candidate => candidate.uri.fsPath === pending.folderPath);
        if (!folder) {
            await clearPendingAction();
            return false;
        }

        const needsCli = pending.commandId === 'aiir.generateReceipt' ||
            pending.commandId === 'aiir.generatePreferred' ||
            pending.commandId === 'aiir.initializeRepo' ||
            pending.commandId === 'aiir.createWorkspacePolicy' ||
            pending.commandId === 'aiir.enableAutoReceipting';
        if (needsCli && !await isCliAvailable(folder)) {
            return false;
        }

        const shouldPrompt = options?.prompt !== false;
        if (shouldPrompt) {
            const choice = await vscode.window.showInformationMessage(
                `AIIR: Setup is ready. Continue to ${pending.label}?`,
                'Continue',
                'Dismiss',
            );

            if (!choice || choice === 'Dismiss') {
                await clearPendingAction();
                return true;
            }
        }

        const keepPendingThroughInitialization = pending.commandId === 'aiir.generatePreferred'
            && !await pathExists(path.join(folder.uri.fsPath, '.aiir'));

        if (keepPendingThroughInitialization) {
            await vscode.commands.executeCommand(pending.commandId, folder.uri);
            return true;
        }

        await clearPendingAction();
        await vscode.commands.executeCommand(pending.commandId, folder.uri);
        return true;
    };

    const syncContextKeys = async () => {
        const state = getContextState(
            isStrictLocalOnly(),
            vscode.workspace.getConfiguration('aiir').get<boolean>('enableHubFeatures', false),
        );
        const accessibleFolders = getAccessibleWorkspaceFolders();
        const { resolved: resolvedHub } = await getResolvedHubState(context, output);
        await vscode.commands.executeCommand('setContext', 'aiir.strictLocalOnly', state.strictLocalOnly);
        await vscode.commands.executeCommand('setContext', 'aiir.networkAllowed', state.networkAllowed);
        await vscode.commands.executeCommand('setContext', 'aiir.hubEnabled', state.hubEnabled);
        await vscode.commands.executeCommand('setContext', 'aiir.hubConnected', resolvedHub.connected && resolvedHub.authenticated);
        await vscode.commands.executeCommand('setContext', 'aiir.hubState', resolvedHub.entitlementState);
        await vscode.commands.executeCommand('setContext', 'aiir.entitlementLevel', resolvedHub.offerFamily);
        await vscode.commands.executeCommand('setContext', 'aiir.canRemoteSync', resolvedHub.capabilities.remoteReceiptSync);
        await vscode.commands.executeCommand('setContext', 'aiir.canUseSharedRepositories', resolvedHub.capabilities.sharedRepositories);
        await vscode.commands.executeCommand('setContext', 'aiir.canManagePolicy', resolvedHub.capabilities.policyManagement);
        await vscode.commands.executeCommand('setContext', 'aiir.canUseCompliance', resolvedHub.capabilities.complianceExports);
        await vscode.commands.executeCommand('setContext', 'aiir.showAdvancedCommands', getShowAdvancedCommands());
        await vscode.commands.executeCommand('setContext', 'aiir.multipleAccessibleRepositories', accessibleFolders.length > 1);
    };

    const refreshExtensionState = async (clearDiagnostics = false) => {
        if (clearDiagnostics) {
            diagnosticCollection.clear();
        }
        await syncContextKeys();
        receiptTreeView.message = getExplorerMessage();
        codeLensProvider.refresh();
        await explorer.refresh();
        await homeProvider.refresh();

        // Refresh commit explorer with the preferred workspace folder.
        const commitFolders = getAccessibleWorkspaceFolders();
        const preferredFolder = resolvePreferredWorkspaceFolderTarget(
            commitFolders.map(f => ({ name: f.name, fsPath: f.uri.fsPath, value: f })),
            undefined,
            recentWorkspaceFolderPath,
        );
        await commitExplorer.refresh(preferredFolder?.uri.fsPath);

        const stats = explorer.getStats();
        await statusBar.refresh(explorer);
        updateSidebarChrome(stats);
        if (await maybeContinuePendingAction()) {
            return;
        }
        await maybeShowMissingReceiptNudge();
    };

    const maybeShowMissingReceiptNudge = async () => {
        const trustState = await getResolvedTrustState(explorer);
        if (!trustState.repoName || !trustState.headSha) {
            lastObservedHeadKey = undefined;
            return;
        }

        const headKey = `${trustState.repoName}:${trustState.headSha}`;
        const isNewHead = lastObservedHeadKey !== headKey;
        lastObservedHeadKey = headKey;

        if (!isNewHead) {
            return;
        }

        if (trustState.headReceiptStatus !== 'missing' || trustState.hookKind === 'managed' || !trustState.activeAITool) {
            return;
        }

        const nudgeKey = `${headKey}:${trustState.activeAITool}`;
        if (lastNudgedHeadKey === nudgeKey) {
            return;
        }
        lastNudgedHeadKey = nudgeKey;

        const actions = [trustState.workspaceOpen ? 'Generate' : 'Generate Receipt', 'Enable Auto-Receipting'];
        const choice = await vscode.window.showInformationMessage(
            `AIIR: ${trustState.activeAITool} looks active and HEAD is missing a receipt.`,
            ...actions,
        );

        if (choice === 'Generate' || choice === 'Generate Receipt') {
            await vscode.commands.executeCommand('aiir.generatePreferred');
        } else if (choice === 'Enable Auto-Receipting') {
            await vscode.commands.executeCommand('aiir.enableAutoReceipting');
        }
    };

    const recreateGitWatcher = async () => {
        gitWatcher.dispose();
        gitWatcher = await createGitStateWatcher(async () => {
            await refreshExtensionState();
        });
    };

    const executePanelMessage = async (message: unknown) => {
        const payload = (message && typeof message === 'object') ? message as { command?: string; args?: unknown[] } : undefined;
        if (!payload?.command) {
            return;
        }

        const isAllowedCommand = payload.command.startsWith('aiir.') || WEBVIEW_ALLOWED_COMMANDS.has(payload.command);
        if (!isAllowedCommand) {
            vscode.window.showWarningMessage(`AIIR: Blocked unexpected webview command '${payload.command}'`);
            return;
        }

        const args = Array.isArray(payload.args) ? payload.args : [];
        try {
            await vscode.commands.executeCommand(payload.command, ...args);
        } catch (error) {
            const detail = error instanceof Error ? error.message : String(error);
            output.appendLine(`AIIR: Webview command ${payload.command} failed — ${detail}`);
            vscode.window.showErrorMessage(`AIIR: ${payload.command} failed — ${detail}`);
        }
    };

    const openReadinessPanel = async (target?: unknown) => {
        await explorer.refresh();
        await statusBar.refresh(explorer);
        const panel = vscode.window.createWebviewPanel(
            'aiir.readiness',
            'AIIR Commit Status',
            vscode.ViewColumn.One,
            { enableScripts: true },
        );

        const render = async () => {
            const readinessView = await getReadinessViewModel(explorer, output, target);
            const pending = getPendingAction();
            const pendingView = pending
                ? (() => {
                    const pendingFolder = getAccessibleWorkspaceFolders().find(folder => folder.uri.fsPath === pending.folderPath);
                    const pendingFolderState = pendingFolder ? explorer.getRepositoryState(pendingFolder) : undefined;
                    const pendingCliAvailable = !!pendingFolderState?.cliAvailable;

                    if (!pendingFolder) {
                        return {
                            label: pending.label,
                            canContinue: false,
                            detail: `Open or allow this repository again before AIIR can continue to ${pending.label}.`,
                        };
                    }

                    if (!pendingCliAvailable) {
                        return {
                            label: pending.label,
                            canContinue: false,
                            detail: `Install the AIIR CLI now and AIIR will continue to ${pending.label} automatically when setup is ready.`,
                            recoveryLabel: 'Install CLI and Continue',
                            recoveryCommandId: 'aiir.installCliNow',
                        };
                    }

                    if (pending.commandId === 'aiir.generatePreferred' && !pendingFolderState?.aiirDirExists) {
                        return {
                            label: pending.label,
                            canContinue: false,
                            detail: `Initialize this repository now and AIIR will continue to ${pending.label} afterward.`,
                            recoveryLabel: 'Initialize Repository and Continue',
                            recoveryCommandId: 'aiir.initializeRepo',
                            recoveryCommandArgs: [pendingFolder.uri.toString()],
                        };
                    }

                    return {
                        label: pending.label,
                        canContinue: true,
                        detail: `AIIR remembered that you were trying to ${pending.label}. Continue when you're ready.`,
                    };
                })()
                : undefined;
            panel.webview.html = finalizeScriptedWebviewHtml(
                getReadinessHtml(readinessView, pendingView, { showAdvanced: getShowAdvancedCommands() }),
                panel.webview.cspSource,
            );
        };

        await render();
        panel.webview.onDidReceiveMessage(async message => {
            if (message?.command === 'aiir.continuePendingAction') {
                await maybeContinuePendingAction();
                await render();
                return;
            }
            await executePanelMessage(message);
            await render();
        });
    };

    const maybeShowFirstRunReadiness = async () => {
        if ((vscode.workspace.workspaceFolders?.length || 0) === 0) {
            return;
        }

        if (context.workspaceState.get<boolean>(FIRST_RUN_READINESS_KEY)) {
            return;
        }

        await context.workspaceState.update(FIRST_RUN_READINESS_KEY, true);
        const view = await getReadinessViewModel(explorer, output);
        if (view.state === 'ready') {
            return;
        }

        const choice = await vscode.window.showInformationMessage(
            `AIIR: ${view.headline}`,
            'See What\'s Missing',
            'Follow Quick Setup',
        );

        if (choice === 'See What\'s Missing') {
            await openReadinessPanel();
        } else if (choice === 'Follow Quick Setup') {
            await vscode.commands.executeCommand('aiir.openWalkthrough');
        }
    };

    // ── Copilot Chat integration ──────────────────────────────────────
    const copilotIntegrationDeps: ChatParticipantDeps & LanguageModelToolDeps = {
        getCliPath,
        resolveWorkspaceFolder(): vscode.WorkspaceFolder | undefined {
            const editor = vscode.window.activeTextEditor;
            const targetPath = editor?.document.uri.fsPath || recentWorkspaceFolderPath;
            const folders = getAccessibleWorkspaceFolders();
            return resolvePreferredWorkspaceFolderTarget(
                folders.map(f => ({ name: f.name, fsPath: f.uri.fsPath, value: f })),
                targetPath,
                recentWorkspaceFolderPath,
            );
        },
        isCliAvailable,
        async getLatestReceiptFile(folder: vscode.WorkspaceFolder): Promise<string | undefined> {
            const record = explorer.getLatestReceipt(folder);
            if (!record) {
                return undefined;
            }

            return await materializeReceiptForCli(record);
        },
    };
    registerChatParticipant(context, copilotIntegrationDeps);
    registerLanguageModelTools(context, copilotIntegrationDeps);
    registerAIBlameDecorations(context, {
        getAccessibleWorkspaceFolders,
        getReceiptSummary(folder: vscode.WorkspaceFolder, commitSha: string) {
            const record = explorer.getReceiptForCommit(commitSha, folder);
            if (!record) {
                return undefined;
            }

            const attestation = record.receipt.ai_attestation as {
                is_ai_authored?: boolean;
                is_bot_authored?: boolean;
                authorship_class?: string;
                signals_detected?: unknown;
            } | undefined;
            const signals = Array.isArray(attestation?.signals_detected)
                ? attestation.signals_detected.filter((signal): signal is string => typeof signal === 'string')
                : [];

            return {
                sha: commitSha,
                isAI: attestation?.is_ai_authored === true,
                isBot: attestation?.is_bot_authored === true,
                authorshipClass: attestation?.authorship_class || 'unknown',
                signals,
                timestamp: record.receipt.timestamp || '',
            };
        },
    });

    // ── Commands ──────────────────────────────────────────────────────

    const provableSessionId = crypto.randomUUID();

    // ── Passive provenance capture ───────────────────────────────────
    // Tracks file content hashes so we can detect when AI-applied edits
    // change a file and automatically record provenance.
    const contentTracker = new Map<string, string>();

    function seedContentTrackerForFolder(folder: vscode.WorkspaceFolder): void {
        for (const document of vscode.workspace.textDocuments) {
            if (document.uri.scheme !== 'file' || !isUriAccessible(document.uri)) {
                continue;
            }
            if (!isPathInside(folder.uri.fsPath, document.uri.fsPath)) {
                continue;
            }
            contentTracker.set(document.uri.fsPath, sha256Text(document.getText()));
        }
    }

    async function configureProvenanceQueue(folder: vscode.WorkspaceFolder): Promise<string | undefined> {
        const queuePath = await ensureProvableQueueInfrastructure(folder, { allowCreateAiir: false, promptOnCreateAiir: false });
        if (!queuePath) {
            vscode.window.showInformationMessage('AIIR: Initialize this repository before configuring provenance queue support.');
            return undefined;
        }
        seedContentTrackerForFolder(folder);
        await explorer.refresh();
        await homeProvider.refresh(folder.uri);
        await statusBar.refresh(explorer);
        return queuePath;
    }

    async function capturePassiveProvenance(document: vscode.TextDocument): Promise<void> {
        try {
            if (document.uri.scheme !== 'file') { return; }
            const activeTool = detectEditorAITools().find(t => t.isActive);
            if (!activeTool) { return; }
            const folder = vscode.workspace.getWorkspaceFolder(document.uri);
            if (!folder) { return; }
            const queuePath = getProvableQueuePath(folder);
            if (!await pathExists(queuePath)) { return; }
            const afterHash = sha256Text(document.getText());
            const beforeHash = contentTracker.get(document.uri.fsPath);
            contentTracker.set(document.uri.fsPath, afterHash);
            if (!beforeHash || beforeHash === afterHash) { return; }
            const relativePath = path.relative(folder.uri.fsPath, document.uri.fsPath).replace(/\\/g, '/');
            const [branch, baseCommitSha] = await Promise.all([
                getCurrentBranchName(folder),
                getCurrentCommitSha(folder),
            ]);
            await runWithProvenanceQueueLock(queuePath, async () => {
                const existingQueue = await readTextFile(queuePath);
                const nextRecord = appendProvenanceRecord(existingQueue, {
                    id: crypto.randomUUID(),
                    sessionId: provableSessionId,
                    createdAt: new Date().toISOString(),
                    repositoryPath: folder.uri.fsPath,
                    branch,
                    baseCommitSha,
                    toolId: 'aiir-vscode',
                    mode: 'provable',
                    command: 'passive-capture',
                    source: 'passive-capture',
                    promptKind: 'auto',
                    files: [{ path: relativePath, beforeHash, afterHash }],
                    applied: true,
                    consumed: false,
                });
                await writeTextFile(queuePath, nextRecord.serialized);
            });
            output.appendLine(`AIIR: Passive provenance captured for ${relativePath}`);
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            output.appendLine(`AIIR: Passive provenance capture failed: ${message}`);
        }
    }

    const {
        commands: receiptCommandDisposables,
        generateReceiptForFolder,
    } = registerReceiptCommands<ReceiptRecord>({
        output,
        explorer,
        homeProvider,
        statusBar,
        resolveCommandWorkspaceFolder,
        showWorkspaceAccessRecovery,
        isCliAvailable,
        async isRepositoryInitialized(folder) {
            return await pathExists(path.join(folder.uri.fsPath, '.aiir'));
        },
        openSetupForPendingAction,
        canUseProvenanceGeneration,
        runWithReceiptGenerationLock,
        getCliPath,
        buildAgentArgs,
        buildEditorProvenanceArgs,
        runCommand,
        getCurrentCommitSha,
        getPostCommitHookKind,
        getTargetReceiptRecord,
        async onReceiptGenerated() {
            await refreshCommitExplorerOverlays();
        },
    });

    const configureProvenanceQueueCmd = vscode.commands.registerCommand('aiir.configureProvenanceQueue', async (uri?: vscode.Uri) => {
        const folder = await resolveCommandWorkspaceFolder(uri, 'Choose a repository to configure provenance for');
        if (!folder) {
            await showWorkspaceAccessRecovery('configure provenance');
            return;
        }

        const queuePath = await configureProvenanceQueue(folder);
        if (!queuePath) {
            return;
        }

        vscode.window.showInformationMessage(`AIIR: Provenance queue configured for ${folder.name}`);
    });

    const generateWithProvenanceCmd = vscode.commands.registerCommand('aiir.generateWithProvenance', async (uri?: vscode.Uri) => {
        const folder = await resolveCommandWorkspaceFolder(uri, 'Choose a repository for provable generation');
        if (!folder) {
            await showWorkspaceAccessRecovery('generate with provenance');
            return;
        }

        if (!await isCliAvailable(folder)) {
            vscode.window.showInformationMessage('AIIR provable mode needs the AIIR CLI first. Open commit status and try again.');
            await openReadinessPanel();
            return;
        }

        if (!hasLanguageModelSupport()) {
            vscode.window.showErrorMessage('AIIR provable mode requires a VS Code build with language model support.');
            return;
        }

        const editor = vscode.window.activeTextEditor;
        if (!editor || editor.document.uri.scheme !== 'file') {
            vscode.window.showErrorMessage('AIIR provable mode needs an active file editor.');
            return;
        }
        if (!isPathInside(folder.uri.fsPath, editor.document.uri.fsPath)) {
            vscode.window.showErrorMessage('The active editor is not inside the selected repository.');
            return;
        }
        if (editor.document.isDirty) {
            const choice = await vscode.window.showInformationMessage(
                'AIIR provable mode needs the active file saved before it can hash and queue deterministic edits.',
                { modal: true },
                'Save and Continue',
                'Cancel',
            );
            if (choice !== 'Save and Continue') {
                return;
            }
            const saved = await editor.document.save();
            if (!saved) {
                vscode.window.showErrorMessage('AIIR provable mode could not save the active file.');
                return;
            }
        }

        const instruction = await vscode.window.showInputBox({
            title: 'AIIR: Generate With Provenance',
            prompt: 'Describe the code change you want AIIR to make.',
            placeHolder: 'Refactor the selected function to handle empty input safely.',
            ignoreFocusOut: true,
        });
        if (!instruction || instruction.trim() === '') {
            return;
        }

        const model = await selectProvableChatModel();
        if (!model) {
            vscode.window.showErrorMessage('AIIR could not find an available chat model for provable mode.');
            return;
        }

        const queuePath = await ensureProvableQueueInfrastructure(folder);
        if (!queuePath) {
            return;
        }

        const selection = editor.selection;
        const promptKind = selection.isEmpty ? 'file' : 'selection';
        const relativePath = toWorkspaceRelativePath(folder, editor.document.uri);
        const cts = new vscode.CancellationTokenSource();

        try {
            const response = await model.sendRequest([
                createProvableUserMessage(
                    buildProvablePrompt(relativePath, editor.document.getText(), instruction.trim(), selection),
                ),
            ], {}, cts.token);
            const rawResponse = await collectChatResponseText(response);
            const plan = parseStructuredEditPlan(rawResponse);
            const prepared = await prepareProvableOperations(folder, editor, plan.operations);
            const approval = await vscode.window.showInformationMessage(
                `AIIR: ${summarizeProvablePlan(plan.summary, plan.operations)}`,
                { modal: true },
                'Apply Changes',
                'Cancel',
            );
            if (approval !== 'Apply Changes') {
                return;
            }

            const beforeHashes = await computeProvableFileHashes(folder, prepared);
            const edit = new vscode.WorkspaceEdit();
            for (const item of prepared) {
                if (item.operation.type === 'replace-range' && item.range) {
                    edit.replace(item.uri, item.range, item.operation.text);
                } else if (item.operation.type === 'create-file') {
                    edit.createFile(item.uri, { ignoreIfExists: false, overwrite: false });
                    edit.insert(item.uri, new vscode.Position(0, 0), item.operation.text);
                }
            }

            const applied = await vscode.workspace.applyEdit(edit);
            if (!applied) {
                throw new Error('VS Code could not apply the provable-mode edits.');
            }

            for (const item of prepared) {
                const document = await vscode.workspace.openTextDocument(item.uri);
                if (document.isDirty) {
                    const saved = await document.save();
                    if (!saved) {
                        throw new Error(`AIIR could not save ${item.operation.path} after applying provable edits.`);
                    }
                }
            }

            const branch = await getCurrentBranchName(folder);
            const baseCommitSha = await getCurrentCommitSha(folder);
            const fileRecords = await finalizeProvableFileHashes(folder, beforeHashes);
            await runWithProvenanceQueueLock(queuePath, async () => {
                const existingQueue = await readTextFile(queuePath);
                const nextRecord = appendProvenanceRecord(existingQueue, {
                    id: crypto.randomUUID(),
                    sessionId: provableSessionId,
                    createdAt: new Date().toISOString(),
                    repositoryPath: folder.uri.fsPath,
                    branch,
                    baseCommitSha,
                    toolId: 'aiir-vscode',
                    mode: 'provable',
                    command: 'generate',
                    modelVendor: model.vendor,
                    modelFamily: model.family,
                    source: 'aiir-command',
                    promptKind,
                    files: fileRecords,
                    applied: true,
                    consumed: false,
                });
                await writeTextFile(queuePath, nextRecord.serialized);
            });

            await explorer.refresh();
            await homeProvider.refresh(folder.uri);
            await statusBar.refresh(explorer);

            const choice = await vscode.window.showInformationMessage(
                'AIIR: Changes applied and provable provenance was queued. Commit these changes, then record a proof or rely on managed auto-receipting.',
                'Enable Auto-Receipting',
                'Open Source Control',
            );
            if (choice === 'Enable Auto-Receipting') {
                await vscode.commands.executeCommand('aiir.enableAutoReceipting', folder.uri);
            } else if (choice === 'Open Source Control') {
                await vscode.commands.executeCommand('workbench.view.scm');
            }
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            output.appendLine(`AIIR provable mode failed: ${message}`);
            vscode.window.showErrorMessage(`AIIR provable mode failed: ${message}`);
        } finally {
            cts.dispose();
        }
    });

    const copyReceiptSummaryCmd = vscode.commands.registerCommand('aiir.copyReceiptSummary', async (target?: unknown) => {
        const record = await getTargetReceiptRecord(target, explorer);
        if (!record) {
            vscode.window.showErrorMessage('AIIR: No receipt is available to summarize yet.');
            return;
        }

        await vscode.env.clipboard.writeText(buildReceiptClipboardSummary(record));
        vscode.window.showInformationMessage(`AIIR: Copied Markdown receipt summary for ${record.receipt.commit?.sha?.slice(0, 8) || 'receipt'}`);
    });

    const previewReceiptSummaryCmd = vscode.commands.registerCommand('aiir.previewReceiptSummary', async (target?: unknown) => {
        const record = await getTargetReceiptRecord(target, explorer);
        if (!record) {
            vscode.window.showErrorMessage('AIIR: No receipt is available to preview yet.');
            return;
        }

        const markdown = buildReceiptClipboardSummary(record);
        const document = await vscode.workspace.openTextDocument({
            content: markdown,
            language: 'markdown',
        });
        await vscode.window.showTextDocument(document, vscode.ViewColumn.Beside, true);
        await vscode.commands.executeCommand('markdown.showPreviewToSide');
    });

    // Initialize AIIR in the workspace
    const initializeRepoCmd = vscode.commands.registerCommand('aiir.initializeRepo', async (uri?: vscode.Uri) => {
        const accessibleFolders = getAccessibleWorkspaceFolders();
        let targetFolders: vscode.WorkspaceFolder[] = [];

        if (!uri && accessibleFolders.length > 1) {
            const scope = await vscode.window.showQuickPick([
                {
                    label: 'All accessible repositories',
                    description: `Initialize ${accessibleFolders.length} repositories with the standard safe workspace policy`,
                    value: 'all' as const,
                },
                {
                    label: 'Single repository',
                    description: 'Choose one repository to initialize',
                    value: 'single' as const,
                },
            ], {
                placeHolder: 'Choose the initialization scope for this multi-root workspace',
            });

            if (!scope) {
                return;
            }

            if (scope.value === 'all') {
                targetFolders = accessibleFolders;
            }
        }

        if (targetFolders.length === 0) {
            const folder = await resolveCommandWorkspaceFolder(uri, 'Choose a repository to initialize');
            if (!folder) {
                await showWorkspaceAccessRecovery('initialize AIIR');
                return;
            }
            targetFolders = [folder];
        }

        if (targetFolders.length === 0) {
            await showWorkspaceAccessRecovery('initialize AIIR');
            return;
        }

        const unavailableFolder = (await Promise.all(
            targetFolders.map(async folder => ({ folder, available: await isCliAvailable(folder) })),
        )).find(entry => !entry.available)?.folder;

        if (unavailableFolder) {
            await openSetupForPendingAction({
                commandId: 'aiir.initializeRepo',
                label: 'Initialize Repository',
                folderPath: unavailableFolder.uri.fsPath,
            });
            return;
        }

        try {
            const initialized: string[] = [];
            const starterReceipts: Array<{ folder: vscode.WorkspaceFolder; receipt?: ReceiptRecord }> = [];
            const starterReceiptFailures: string[] = [];
            const baselineFolders = targetFolders;

            await applySafeWorkspaceSettings(targetFolders);
            await syncContextKeys();

            for (const folder of targetFolders) {
                await initializeWorkspaceFolder(folder, output, 'balanced', baselineFolders);
                seedContentTrackerForFolder(folder);
                initialized.push(folder.name);

                try {
                    const receipt = await generateReceiptForFolder(folder);
                    starterReceipts.push({ folder, receipt });
                } catch (error) {
                    const err = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
                    if (err.stdout) {
                        output.appendLine(err.stdout.trimEnd());
                    }
                    if (err.stderr) {
                        output.appendLine(err.stderr.trimEnd());
                    }
                    output.appendLine(`AIIR: Starter receipt generation failed for ${folder.name}: ${err.message}`);
                    starterReceiptFailures.push(folder.name);
                }
            }

            if (targetFolders.length > 0) {
                rememberWorkspaceFolder(targetFolders[0]);
            }

            const targetLabel = initialized.length === 1
                ? initialized[0]
                : `${initialized.length} repositories`;
            let message = `AIIR: Initialized ${targetLabel} with the standard safe workspace policy`;
            if (starterReceipts.length > 0) {
                message += starterReceipts.length === 1
                    ? ' and recorded a starter proof.'
                    : ` and recorded ${starterReceipts.length} starter proofs.`;
            } else {
                message += '.';
            }
            if (starterReceiptFailures.length > 0) {
                message += ` Record proof manually after the next commit for ${starterReceiptFailures.join(', ')}.`;
            }

            const actions = ['Open Workspace Settings JSON'];
            const starterReceipt = starterReceipts.find(entry => entry.folder.uri.fsPath === targetFolders[0]?.uri.fsPath)?.receipt;
            if (starterReceipt) {
                actions.unshift('View Proof');
            }

            const choice = await vscode.window.showInformationMessage(message, ...actions);
            if (choice === 'View Proof' && starterReceipt) {
                await vscode.commands.executeCommand('aiir.viewReceipt', starterReceipt.uri);
            } else if (choice === 'Open Workspace Settings JSON') {
                await vscode.commands.executeCommand('workbench.action.openWorkspaceSettingsFile');
            }
            await maybeContinuePendingAction();
        } catch (error) {
            const err = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
            if (err.stdout) {
                output.appendLine(err.stdout.trimEnd());
            }
            if (err.stderr) {
                output.appendLine(err.stderr.trimEnd());
            }
            vscode.window.showErrorMessage(`AIIR: Initialization failed — ${err.message}`);
            output.show(true);
        }
    });

    const ensurePolicyForCommand = async (
        folder: vscode.WorkspaceFolder,
        actionLabel: string,
        options?: { openTargetsAfterCreate?: boolean },
    ): Promise<string | undefined> => {
        const policyPath = getPolicyFilePath(folder);
        if (await pathExists(policyPath)) {
            return policyPath;
        }

        if (!await isCliAvailable(folder)) {
            await openSetupForPendingAction({
                commandId: 'aiir.createWorkspacePolicy',
                label: actionLabel,
                folderPath: folder.uri.fsPath,
            });
            return undefined;
        }

        const createChoice = await vscode.window.showInformationMessage(
            'AIIR did not find .aiir/policy.json for this repository. Create the repo-local AIIR policy file now?',
            'Create Policy File',
            'Cancel',
        );

        if (createChoice !== 'Create Policy File') {
            return undefined;
        }

        await applySafeWorkspaceSettings([folder]);
        await syncContextKeys();
        await createOrEnsureWorkspacePolicy(folder, output, 'balanced', [folder]);
        if (options?.openTargetsAfterCreate) {
            await editWorkspacePolicyTargets(folder);
        }
        await explorer.refresh();
        await homeProvider.refresh(folder.uri);
        await statusBar.refresh(explorer);
        return policyPath;
    };

    const createWorkspacePolicyCmd = vscode.commands.registerCommand('aiir.createWorkspacePolicy', async (uri?: vscode.Uri) => {
        const folder = await resolveCommandWorkspaceFolder(uri, 'Choose a repository policy to create');
        if (!folder) {
            await showWorkspaceAccessRecovery('create a repository policy file');
            return;
        }

        if (!await isCliAvailable(folder)) {
            await openSetupForPendingAction({
                commandId: 'aiir.createWorkspacePolicy',
                label: 'Create Policy File',
                folderPath: folder.uri.fsPath,
            });
            return;
        }

        try {
            await applySafeWorkspaceSettings([folder]);
            await syncContextKeys();
            await createOrEnsureWorkspacePolicy(folder, output, 'balanced', [folder]);
            await explorer.refresh();
            await homeProvider.refresh(folder.uri);
            await statusBar.refresh(explorer);
            const choice = await vscode.window.showInformationMessage(
                `AIIR: Created the repository policy file for ${folder.name}. Edit the live workspace policy in settings or open the AIIR policy file for repo-local defaults.`,
                'Open Workspace Settings JSON',
                'Open Policy File',
            );
            if (choice === 'Open Workspace Settings JSON') {
                await vscode.commands.executeCommand('workbench.action.openWorkspaceSettingsFile');
            } else if (choice === 'Open Policy File') {
                await vscode.commands.executeCommand('vscode.open', vscode.Uri.file(getPolicyFilePath(folder)));
            }
            await maybeContinuePendingAction();
        } catch (error) {
            const err = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
            if (err.stdout) {
                output.appendLine(err.stdout.trimEnd());
            }
            if (err.stderr) {
                output.appendLine(err.stderr.trimEnd());
            }
            vscode.window.showErrorMessage(`AIIR: Could not create the workspace policy — ${err.message}`);
            output.show(true);
        }
    });

    const openPolicyFileCmd = vscode.commands.registerCommand('aiir.openPolicyFile', async (uri?: vscode.Uri) => {
        const folder = await resolveCommandWorkspaceFolder(uri, 'Choose a repository policy file to open');
        if (!folder) {
            await showWorkspaceAccessRecovery('open a policy file');
            return;
        }

        const policyPath = getPolicyFilePath(folder);
        const exists = await pathExists(policyPath);
        if (!exists) {
            const ensuredPath = await ensurePolicyForCommand(folder, 'Open Policy File');
            if (!ensuredPath) {
                return;
            }
        }

        await vscode.commands.executeCommand('vscode.open', vscode.Uri.file(policyPath));
    });

    const editPolicyTargetsCmd = vscode.commands.registerCommand('aiir.editPolicyTargets', async (uri?: vscode.Uri) => {
        const folder = await resolveCommandWorkspaceFolder(uri, 'Choose a repository policy file to edit');
        if (!folder) {
            await showWorkspaceAccessRecovery('edit policy targets');
            return;
        }

        const policyPath = getPolicyFilePath(folder);
        if (!await pathExists(policyPath)) {
            const ensuredPath = await ensurePolicyForCommand(folder, 'Edit Policy Targets', { openTargetsAfterCreate: true });
            if (!ensuredPath) {
                return;
            }

            return;
        }

        try {
            const updated = await editWorkspacePolicyTargets(folder);
            if (!updated) {
                return;
            }
            await refreshExtensionState();
            vscode.window.showInformationMessage(`AIIR: Updated workspace policy targets for ${folder.name}`);
        } catch (error) {
            vscode.window.showErrorMessage(`AIIR: Could not update workspace policy targets — ${(error as Error).message}`);
        }
    });

    const toggleCurrentPolicyTargetCmd = vscode.commands.registerCommand('aiir.toggleCurrentPolicyTarget', async (uri?: vscode.Uri) => {
        const folder = await resolveCommandWorkspaceFolder(uri, 'Choose a repository policy target to toggle');
        if (!folder) {
            await showWorkspaceAccessRecovery('toggle a policy target');
            return;
        }

        const policyPath = getPolicyFilePath(folder);
        if (!await pathExists(policyPath)) {
            const ensuredPath = await ensurePolicyForCommand(folder, 'Toggle Current Policy Target');
            if (!ensuredPath) {
                return;
            }
        }

        const policyState = await getWorkspacePolicyState(folder);
        const editableTargets = buildEditablePolicyTargets(policyState, getAccessibleWorkspaceFolders());
        const currentKey = getPolicyTargetKey({ name: folder.name, path: folder.uri.fsPath });
        const nextTargets = editableTargets.map(target =>
            getPolicyTargetKey(target) === currentKey
                ? { ...target, enabled: !target.enabled }
                : target,
        );
        const toggledTarget = nextTargets.find(target => getPolicyTargetKey(target) === currentKey);

        try {
            await updateWorkspacePolicyTargets(folder, nextTargets);
            await refreshExtensionState();
            vscode.window.showInformationMessage(
                `AIIR: ${folder.name} is now ${toggledTarget?.enabled ? 'enabled' : 'disabled'} in the workspace policy`,
            );
        } catch (error) {
            vscode.window.showErrorMessage(`AIIR: Could not toggle the current policy target — ${(error as Error).message}`);
        }
    });

    // Health check dashboard
    const healthCheckCmd = vscode.commands.registerCommand('aiir.healthCheck', async (uri?: vscode.Uri) => {
        const folder = await resolveCommandWorkspaceFolder(uri, 'Choose a repository to inspect');
        if (!folder) {
            await showWorkspaceAccessRecovery('run a health check');
            return;
        }

        await explorer.refresh();
        await statusBar.refresh(explorer);

        const hubState = await getHubConnectionState(context, output);
        const health = await collectHealthCheck(folder, explorer, output, hubState);
        const panel = vscode.window.createWebviewPanel(
            'aiir.healthCheck',
            'AIIR Health Check',
            vscode.ViewColumn.One,
            { enableScripts: true },
        );

        panel.webview.html = finalizeScriptedWebviewHtml(
            getHealthCheckHtml(health, folder.uri.toString()),
            panel.webview.cspSource,
        );
        panel.webview.onDidReceiveMessage(executePanelMessage);
    });

    // Manage which workspace repositories have AIIR receipt ledgers.
    const manageRepositoriesCmd = vscode.commands.registerCommand('aiir.manageRepositories', async () => {
        const accessibleFolders = getAccessibleWorkspaceFolders();
        if (accessibleFolders.length === 0) {
            await showWorkspaceAccessRecovery('manage repositories');
            return;
        }

        const items: Array<vscode.QuickPickItem & { folder: vscode.WorkspaceFolder }> = [];
        for (const folder of accessibleFolders) {
            const repositoryState = explorer.getRepositoryState(folder);
            items.push({
                label: folder.name,
                description: folder.uri.fsPath,
                picked: shouldShowRepository(repositoryState),
                folder,
            });
        }

        const selected = await vscode.window.showQuickPick(items, {
            canPickMany: true,
            placeHolder: 'Select repositories to keep active in this workspace',
            title: 'Manage Repositories',
        });

        if (!selected) {
            return;
        }

        const selectedPaths = new Set(selected.map(item => item.folder.uri.fsPath));
        const newlyEnabled = items.filter(item => selectedPaths.has(item.folder.uri.fsPath) && !item.picked);
        const newlyDisabled = items.filter(item => !selectedPaths.has(item.folder.uri.fsPath) && item.picked);

        if (newlyEnabled.length === 0 && newlyDisabled.length === 0) {
            vscode.window.showInformationMessage('AIIR: Repository selection unchanged');
            return;
        }

        try {
            await applySafeWorkspaceSettings(selected.map(item => item.folder), { replaceAllowedFolders: true });
            await syncContextKeys();

            const starterReceipts: ReceiptRecord[] = [];
            const starterReceiptFailures: string[] = [];

            for (const item of newlyEnabled) {
                if (!await isCliAvailable(item.folder)) {
                    await openSetupForPendingAction({
                        commandId: 'aiir.initializeRepo',
                        label: 'Manage Repositories',
                        folderPath: item.folder.uri.fsPath,
                    });
                    return;
                }
                await initializeWorkspaceFolder(item.folder, output, 'balanced', selected.map(entry => entry.folder));
                try {
                    const receipt = await generateReceiptForFolder(item.folder);
                    if (receipt) {
                        starterReceipts.push(receipt);
                    }
                } catch (error) {
                    const err = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
                    if (err.stdout) {
                        output.appendLine(err.stdout.trimEnd());
                    }
                    if (err.stderr) {
                        output.appendLine(err.stderr.trimEnd());
                    }
                    output.appendLine(`AIIR: Starter receipt generation failed for ${item.folder.name}: ${err.message}`);
                    starterReceiptFailures.push(item.folder.name);
                }
            }

            await explorer.refresh();
            await homeProvider.refresh();
            await statusBar.refresh(explorer);

            const changes: string[] = [];
            if (newlyEnabled.length > 0) {
                const names = newlyEnabled.map(item => item.folder.name).join(', ');
                let enableMessage = `Enabled receipt generation for ${names} with the standard safe workspace policy`;
                if (starterReceipts.length > 0) {
                    enableMessage += starterReceipts.length === 1
                        ? ' and recorded a starter proof.'
                        : ` and recorded ${starterReceipts.length} starter proofs.`;
                } else {
                    enableMessage += '.';
                }
                changes.push(enableMessage);
            }
            if (newlyDisabled.length > 0) {
                const names = newlyDisabled.map(item => item.folder.name).join(', ');
                changes.push(`Removed ${names} from the active workspace repository list.`);
            }

            let message = `AIIR: ${changes.join(' ')}`;
            if (starterReceiptFailures.length > 0) {
                message += ` Record proof manually after the next commit for ${starterReceiptFailures.join(', ')}.`;
            }

            const choice = await vscode.window.showInformationMessage(message, 'Open Workspace Settings JSON');
            if (choice === 'Open Workspace Settings JSON') {
                await vscode.commands.executeCommand('workbench.action.openWorkspaceSettingsFile');
            }
        } catch (error) {
            const err = error as Error;
            vscode.window.showErrorMessage(`AIIR: Could not initialize repositories — ${err.message}`);
        }
    });

    const switchRepositoryCmd = vscode.commands.registerCommand('aiir.switchRepository', async (target?: unknown) => {
        const targetPath = resolveCommandTargetPath(target);
        const accessibleFolders = getAccessibleWorkspaceFolders();

        if (accessibleFolders.length === 0) {
            await showWorkspaceAccessRecovery('switch repositories');
            return;
        }

        const preferredFolder = resolvePreferredWorkspaceFolderTarget(
            accessibleFolders.map(folder => ({ name: folder.name, fsPath: folder.uri.fsPath, value: folder })),
            targetPath,
            recentWorkspaceFolderPath,
        );

        const picked = await vscode.window.showQuickPick(
            accessibleFolders.map(folder => ({
                label: folder.name,
                description: folder.uri.fsPath,
                detail: folder.uri.fsPath === preferredFolder?.uri.fsPath ? 'Current AIIR repository' : undefined,
                folder,
            })),
            {
                placeHolder: 'Choose the repository AIIR should focus on',
                title: 'Switch Repository',
            },
        );

        if (!picked) {
            return;
        }

        rememberWorkspaceFolder(picked.folder);
        await refreshExtensionState();
        vscode.window.showInformationMessage(`AIIR: Focused on ${picked.folder.name}`);
    });

    // Enable managed post-commit auto-receipting
    const enableAutoReceiptingCmd = vscode.commands.registerCommand('aiir.enableAutoReceipting', async (uri?: vscode.Uri) => {
        const folder = await resolveCommandWorkspaceFolder(uri, 'Choose a repository for auto-receipting');
        if (!folder) {
            await showWorkspaceAccessRecovery('enable auto-receipting');
            return;
        }

        if (!await isCliAvailable(folder)) {
            await openSetupForPendingAction({
                commandId: 'aiir.enableAutoReceipting',
                label: 'Enable Auto-Receipting',
                folderPath: folder.uri.fsPath,
            });
            return;
        }

        const confirmed = await vscode.window.showWarningMessage(
            'AIIR will install or update a post-commit hook in this repository so every local commit gets recorded automatically.',
            { modal: true },
            'Install Hook',
            'Cancel',
        );

        if (confirmed !== 'Install Hook') {
            return;
        }

        const installHook = async (extraArgs: string[] = []): Promise<void> => {
            const installResult = await runJsonCommand(getCliPath(), ['--install-hook', '--json', ...extraArgs], folder.uri.fsPath, output);
            const status = typeof installResult.status === 'string' ? installResult.status : 'updated';
            vscode.window.showInformationMessage(`AIIR: Auto-receipting ${status} for ${folder.name}`);
        };

        try {
            await installHook();
        } catch (error) {
            const err = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
            const combined = `${err.stdout ?? ''} ${err.stderr ?? ''} ${err.message ?? ''}`;

            if (combined.includes('--hook-append') || combined.includes('--hook-replace')) {
                // Existing custom hook — ask the user how to proceed
                const hookChoice = await vscode.window.showWarningMessage(
                    'This repository already has a custom post-commit hook. How should AIIR handle it?',
                    { modal: true },
                    'Keep Both (Append)',
                    'Replace with AIIR',
                    'Cancel',
                );
                if (hookChoice === 'Keep Both (Append)') {
                    try {
                        await installHook(['--hook-append']);
                        return;
                    } catch (retryErr) {
                        const e2 = retryErr as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
                        if (e2.stdout) { output.appendLine(e2.stdout.trimEnd()); }
                        if (e2.stderr) { output.appendLine(e2.stderr.trimEnd()); }
                        vscode.window.showErrorMessage(`AIIR: Could not enable auto-receipting — ${e2.message}`);
                        output.show(true);
                        return;
                    }
                } else if (hookChoice === 'Replace with AIIR') {
                    try {
                        await installHook(['--hook-replace']);
                        return;
                    } catch (retryErr) {
                        const e2 = retryErr as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
                        if (e2.stdout) { output.appendLine(e2.stdout.trimEnd()); }
                        if (e2.stderr) { output.appendLine(e2.stderr.trimEnd()); }
                        vscode.window.showErrorMessage(`AIIR: Could not enable auto-receipting — ${e2.message}`);
                        output.show(true);
                        return;
                    }
                }
                // Cancel — do nothing
                return;
            }

            if (err.stdout) {
                output.appendLine(err.stdout.trimEnd());
            }
            if (err.stderr) {
                output.appendLine(err.stderr.trimEnd());
            }
            vscode.window.showErrorMessage(`AIIR: Could not enable auto-receipting — ${err.message}`);
            output.show(true);
        }
    });

    const connectHubCmd = vscode.commands.registerCommand('aiir.connectHub', async () => {
        try {
            ensureNetworkAllowed('connect to Hub');
        } catch (error) {
            await showNetworkAccessRecovery('connect to Hub');
            return;
        }

        const baseUrl = await vscode.window.showInputBox({
            title: 'Connect AIIR Hub',
            prompt: 'Hub base URL (provided during onboarding)',
            placeHolder: 'https://hub.example.com',
            value: getHubBaseUrl(),
            ignoreFocusOut: true,
            validateInput: value => /^https?:\/\//.test(value.trim()) ? undefined : 'Enter a valid http(s) URL',
        });
        if (!baseUrl) {
            return;
        }

        const tenantId = await vscode.window.showInputBox({
            title: 'Connect AIIR Hub',
            prompt: 'Tenant ID',
            value: getHubTenantId(),
            ignoreFocusOut: true,
            validateInput: value => value.trim() ? undefined : 'Tenant ID is required',
        });
        if (!tenantId) {
            return;
        }

        const token = await vscode.window.showInputBox({
            title: 'Connect AIIR Hub',
            prompt: 'API token',
            password: true,
            ignoreFocusOut: true,
            validateInput: value => value.trim() ? undefined : 'API token is required',
        });
        if (!token) {
            return;
        }

        try {
            await updateAiirSetting('hubBaseUrl', baseUrl.trim());
            await updateAiirSetting('hubTenantId', tenantId.trim());
            await setHubToken(context, token);

            const state = await getHubConnectionState(context, output);
            if (!state.connected) {
                throw new Error(state.error || 'Could not reach AIIR Hub');
            }

            await updateAiirSetting('enableHubFeatures', true);
            await syncContextKeys();
            vscode.window.showInformationMessage(`AIIR: Connected to Hub tenant ${tenantId.trim()}`);
        } catch (error) {
            vscode.window.showErrorMessage(`AIIR: Hub connection failed — ${(error as Error).message}`);
            output.show(true);
        }
    });

    const disconnectHubCmd = vscode.commands.registerCommand('aiir.disconnectHub', async () => {
        await deleteHubToken(context);
        await updateAiirSetting('enableHubFeatures', false);
        await syncContextKeys();
        vscode.window.showInformationMessage('AIIR: Disconnected from Hub');
    });

    const hubStatusCmd = vscode.commands.registerCommand('aiir.hubStatus', async () => {
        try {
            ensureNetworkAllowed('view Hub status');
            const { connection, resolved } = await getResolvedHubState(context, output);
            const panel = vscode.window.createWebviewPanel(
                'aiir.hubStatus',
                'AIIR Hub Status',
                vscode.ViewColumn.One,
                { enableScripts: true },
            );
            panel.webview.html = finalizeScriptedWebviewHtml(
                getHubStatusHtml({
                    ...connection,
                    resolvedState: resolved,
                }, isNetworkAllowed(), { showAdvanced: getShowAdvancedCommands() }),
                panel.webview.cspSource,
            );
            panel.webview.onDidReceiveMessage(executePanelMessage);
        } catch (error) {
            await showNetworkAccessRecovery('view Hub status');
        }
    });

    const hubVerifyReceiptCmd = vscode.commands.registerCommand('aiir.hubVerifyReceipt', async (uri?: vscode.Uri) => {
        try {
            const hubAccess = await ensureHubConfigured(context, output, {
                action: 'verify this receipt in Hub',
                requiredCapability: 'remoteReceiptSync',
            });
            if (!hubAccess) {
                return;
            }
            const { baseUrl, token } = hubAccess;
            const record = await getTargetReceiptRecord(uri, explorer);
            if (!record) {
                throw new Error('Open a receipt file or generate a receipt for HEAD first');
            }

            const receiptHash = String(record.receipt.content_hash || record.receipt.receipt_id || '').trim();
            if (!receiptHash) {
                throw new Error('Selected receipt has no content hash');
            }

            const result = await requestJson(
                baseUrl,
                `/api/portal/receipts/${encodeURIComponent(receiptHash)}/verify`,
                token,
                output,
            );
            await showJsonPanel('AIIR Hub Receipt Verification', result);
        } catch (error) {
            vscode.window.showErrorMessage(`AIIR: Hub receipt verification failed — ${(error as Error).message}`);
            output.show(true);
        }
    });

    const hubLatestReportCmd = vscode.commands.registerCommand('aiir.hubLatestReport', async () => {
        try {
            const hubAccess = await ensureHubConfigured(context, output, {
                action: 'fetch the latest Hub report',
                requiredCapability: 'remoteReceiptSync',
                requireTenant: true,
            });
            if (!hubAccess?.tenantId) {
                return;
            }
            const { baseUrl, tenantId, token } = hubAccess;
            const report = await requestJson(
                baseUrl,
                `/api/portal/tenants/${encodeURIComponent(tenantId)}/reports/latest`,
                token,
                output,
            );
            await showJsonPanel('AIIR Hub Latest Report', report);
        } catch (error) {
            vscode.window.showErrorMessage(`AIIR: Could not fetch latest Hub report — ${(error as Error).message}`);
            output.show(true);
        }
    });

    const hubEvidencePackCmd = vscode.commands.registerCommand('aiir.hubEvidencePack', async () => {
        try {
            const hubAccess = await ensureHubConfigured(context, output, {
                action: 'fetch the Hub evidence pack',
                requiredCapability: 'complianceExports',
                requireTenant: true,
            });
            if (!hubAccess?.tenantId) {
                return;
            }
            const { baseUrl, tenantId, token } = hubAccess;
            const pack = await requestJson(
                baseUrl,
                `/api/portal/tenants/${encodeURIComponent(tenantId)}/compliance/evidence-pack`,
                token,
                output,
            );
            await showJsonPanel('AIIR Hub Evidence Pack', pack);
        } catch (error) {
            vscode.window.showErrorMessage(`AIIR: Could not fetch evidence pack — ${(error as Error).message}`);
            output.show(true);
        }
    });

    const hubRunAttestationCmd = vscode.commands.registerCommand('aiir.hubRunAttestation', async () => {
        try {
            const hubAccess = await ensureHubConfigured(context, output, {
                action: 'run a Hub attestation',
                requiredCapability: 'remoteReceiptSync',
                requireTenant: true,
            });
            if (!hubAccess?.tenantId) {
                return;
            }
            const { baseUrl, tenantId, token } = hubAccess;
            const runLabel = await vscode.window.showInputBox({
                title: 'Run AIIR Hub Attestation',
                prompt: 'Run label',
                placeHolder: 'release-candidate-01',
                ignoreFocusOut: true,
                validateInput: value => value.trim() ? undefined : 'Run label is required',
            });
            if (!runLabel) {
                return;
            }

            const result = await requestJson(
                baseUrl,
                `/api/portal/tenants/${encodeURIComponent(tenantId)}/runs/attestation`,
                token,
                output,
                {
                    method: 'POST',
                    body: JSON.stringify({ run_label: runLabel.trim(), skip_pytest: true }),
                },
            );
            await showJsonPanel('AIIR Hub Attestation Run', result);
        } catch (error) {
            vscode.window.showErrorMessage(`AIIR: Could not run Hub attestation — ${(error as Error).message}`);
            output.show(true);
        }
    });

    const openHubCmd = vscode.commands.registerCommand('aiir.openHubDashboard', async () => {
        try {
            ensureNetworkAllowed('open the Hub dashboard');
            const baseUrl = getHubBaseUrl();
            if (!baseUrl) {
                vscode.window.showErrorMessage('AIIR: Configure aiir.hubBaseUrl first');
                return;
            }
            await vscode.env.openExternal(vscode.Uri.parse(baseUrl));
        } catch (error) {
            await showNetworkAccessRecovery('open the Hub dashboard');
        }
    });

    const openHubPricingCmd = vscode.commands.registerCommand('aiir.openHubPricingPage', async () => {
        await vscode.env.openExternal(vscode.Uri.parse(getHubPricingUrl()));
    });

    const openHostedHubSignupCmd = vscode.commands.registerCommand('aiir.openHostedHubSignup', async () => {
        await vscode.env.openExternal(vscode.Uri.parse(getHostedHubSignupUrl()));
    });

    const copyCliInstallCommandCmd = vscode.commands.registerCommand('aiir.copyCliInstallCommand', async () => {
        await copyCliInstallCommand();
    });

    const installCliNowCmd = vscode.commands.registerCommand('aiir.installCliNow', async () => {
        try {
            const cliPath = await installCliNow(output);
            await refreshExtensionState(true);
            const resumedPendingAction = await maybeContinuePendingAction({ prompt: false });
            if (!resumedPendingAction) {
                vscode.window.showInformationMessage(`AIIR: CLI installed and ready at ${cliPath}`);
            }
        } catch (error) {
            const err = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
            if (err.stdout) {
                output.appendLine(err.stdout.trimEnd());
            }
            if (err.stderr) {
                output.appendLine(err.stderr.trimEnd());
            }
            vscode.window.showErrorMessage(`AIIR: CLI install failed — ${err.message}`);
            output.show(true);
        }
    });

    const installSigstoreSupportCmd = vscode.commands.registerCommand('aiir.installSigstoreSupport', async () => {
        try {
            const cliPath = await installSigstoreSupport(output);
            await refreshExtensionState(true);
            vscode.window.showInformationMessage(`AIIR: Sigstore support installed for ${cliPath}`);
        } catch (error) {
            const err = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
            if (err.stdout) {
                output.appendLine(err.stdout.trimEnd());
            }
            if (err.stderr) {
                output.appendLine(err.stderr.trimEnd());
            }
            vscode.window.showErrorMessage(`AIIR: Sigstore setup failed — ${err.message}`);
            output.show(true);
        }
    });

    const openCliInstallTerminalCmd = vscode.commands.registerCommand('aiir.openCliInstallTerminal', async () => {
        await openCliInstallTerminal();
    });

    const reportBugCmd = vscode.commands.registerCommand('aiir.reportBug', async () => {
        await vscode.env.openExternal(vscode.Uri.parse(getBugReportUrl(context.extension.packageJSON.version as string)));
    });

    const signUpForHubCmd = vscode.commands.registerCommand('aiir.signUpForHub', async () => {
        try {
            ensureNetworkAllowed('sign up for Hub');
        } catch (error) {
            await showNetworkAccessRecovery('sign up for Hub');
            return;
        }

        const panel = vscode.window.createWebviewPanel(
            'aiir.hubSignup',
            'AIIR Hub Signup',
            vscode.ViewColumn.One,
            { enableScripts: true },
        );

        const { resolved } = await getResolvedHubState(context, output);

        panel.webview.html = finalizeScriptedWebviewHtml(
            getHubSignupHtml({
                networkAllowed: isNetworkAllowed(),
                signupUrl: getHostedHubSignupUrl(),
                resolvedState: resolved,
            }, { showAdvanced: getShowAdvancedCommands() }),
            panel.webview.cspSource,
        );
        panel.webview.onDidReceiveMessage(executePanelMessage);
    });

    const hubBillingCmd = vscode.commands.registerCommand('aiir.hubBilling', async () => {
        const { connection, resolved } = await getResolvedHubState(context, output);
        const panel = vscode.window.createWebviewPanel(
            'aiir.hubBilling',
            'AIIR Hub Plans and Access',
            vscode.ViewColumn.One,
            { enableScripts: true },
        );

        panel.webview.html = finalizeScriptedWebviewHtml(
            getHubBillingHtml({
                networkAllowed: isNetworkAllowed(),
                hubEnabled: isHubEnabled(),
                hubConfigured: connection.configured,
                hubConnected: connection.connected,
                hubBaseUrl: connection.baseUrl,
                pricingUrl: getHubPricingUrl(),
                signupUrl: getHostedHubSignupUrl(),
                resolvedState: resolved,
            }, {
                showAdvanced: getShowAdvancedCommands(),
            }),
            panel.webview.cspSource,
        );

        panel.webview.onDidReceiveMessage(executePanelMessage);
    });

    const advancedSettingsCmd = vscode.commands.registerCommand('aiir.advancedSettings', async (target?: unknown) => {
        const panel = vscode.window.createWebviewPanel(
            'aiir.advancedSettings',
            'AIIR Advanced Settings',
            vscode.ViewColumn.One,
            { enableScripts: true },
        );

        panel.webview.html = finalizeScriptedWebviewHtml(
            getAdvancedSettingsHtml(await getAdvancedSettingsViewModel(target), { showAdvanced: getShowAdvancedCommands() }),
            panel.webview.cspSource,
        );
        panel.webview.onDidReceiveMessage(executePanelMessage);
    });

    const readinessCheckCmd = vscode.commands.registerCommand('aiir.readinessCheck', openReadinessPanel);

    const securityPostureCmd = vscode.commands.registerCommand('aiir.securityPosture', async () => {
        const panel = vscode.window.createWebviewPanel(
            'aiir.securityPosture',
            'AIIR Security Posture',
            vscode.ViewColumn.One,
            { enableScripts: true },
        );

        panel.webview.html = finalizeScriptedWebviewHtml(
            getSecurityPostureHtml(getSecurityPostureViewModel()),
            panel.webview.cspSource,
        );
        panel.webview.onDidReceiveMessage(executePanelMessage);
    });

    const rolloutPresetsCmd = vscode.commands.registerCommand('aiir.rolloutPresets', async (target?: unknown) => {
        const panel = vscode.window.createWebviewPanel(
            'aiir.rolloutPresets',
            'AIIR Deployment Presets',
            vscode.ViewColumn.One,
            { enableScripts: true },
        );

        panel.webview.html = finalizeScriptedWebviewHtml(
            getRolloutPresetsHtml(getRolloutPresetViewModel(target)),
            panel.webview.cspSource,
        );
        panel.webview.onDidReceiveMessage(executePanelMessage);
    });

    const applyPresetCmd = vscode.commands.registerCommand('aiir.applyPreset', async (presetId?: string) => {
        const model = getRolloutPresetViewModel();
        const preset = model.presets.find(entry => entry.id === presetId);
        if (!preset) {
            vscode.window.showErrorMessage('AIIR: Unknown rollout preset');
            return;
        }

        if (preset.id === 'ci-sign-when-supported') {
            const choice = await vscode.window.showInformationMessage(
                'AIIR: Keep local generation provenance-first in VS Code. Use Sigstore signing in CI or release workflows when ambient OIDC credentials and the optional sigstore package are available.',
                'Open README',
                'Copy CI Command',
            );

            if (choice === 'Open README') {
                const readmeUri = vscode.Uri.file(path.resolve(context.extensionPath, '..', '..', 'README.md'));
                const document = await vscode.workspace.openTextDocument(readmeUri);
                await vscode.window.showTextDocument(document, { preview: false });
            } else if (choice === 'Copy CI Command') {
                await vscode.env.clipboard.writeText('aiir --sign --in-toto --output .receipts/');
                vscode.window.showInformationMessage('AIIR: Copied a CI signing command example');
            }

            return;
        }

        try {
            for (const [key, value] of Object.entries(preset.settings)) {
                await updateAiirSetting(key.replace(/^aiir\./, ''), value);
            }
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            vscode.window.showErrorMessage(`AIIR: ${message}`);
            return;
        }

        await syncContextKeys();
        await refreshExtensionState(true);
        vscode.window.showInformationMessage(`AIIR: Applied preset '${preset.title}' to this workspace`);
    });

    const openWalkthroughCmd = vscode.commands.registerCommand('aiir.openWalkthrough', async () => {
        await vscode.commands.executeCommand('workbench.action.openWalkthrough', walkthroughId, false);
    });

    // Disable managed post-commit auto-receipting
    const disableAutoReceiptingCmd = vscode.commands.registerCommand('aiir.disableAutoReceipting', async (uri?: vscode.Uri) => {
        const folder = await resolveCommandWorkspaceFolder(uri, 'Choose a repository for auto-receipting');
        if (!folder) {
            await showWorkspaceAccessRecovery('disable auto-receipting');
            return;
        }

        if (!await isCliAvailable(folder)) {
            await openSetupForPendingAction({
                commandId: 'aiir.disableAutoReceipting',
                label: 'Disable Auto-Receipting',
                folderPath: folder.uri.fsPath,
            });
            return;
        }

        try {
            const removalResult = await runJsonCommand(getCliPath(), ['--remove-hook', '--json'], folder.uri.fsPath, output);
            if (removalResult.status === 'absent') {
                vscode.window.showWarningMessage('AIIR: No managed post-commit hook was found');
                return;
            }
            vscode.window.showInformationMessage(`AIIR: Disabled managed auto-receipting for ${folder.name}`);
        } catch (error) {
            vscode.window.showErrorMessage(`AIIR: Could not disable auto-receipting — ${(error as Error).message}`);
        }
    });

    // Verify a file
    const verifyFileCmd = vscode.commands.registerCommand('aiir.verifyFile', async (target?: unknown) => {
        const fileUri = resolveTargetUri(target) || vscode.window.activeTextEditor?.document.uri;
        if (!fileUri) {
            vscode.window.showErrorMessage('AIIR: No file selected');
            return;
        }

        if (!isUriAccessible(fileUri)) {
            diagnosticCollection.delete(fileUri);
            await showWorkspaceAccessRecovery('verify receipts in this folder');
            return;
        }

        try {
            const content = await vscode.workspace.fs.readFile(fileUri);
            const text = Buffer.from(content).toString('utf-8');
            const receipt = JSON.parse(text);
            const result = verifyReceipt(receipt);
            updateDiagnostics(diagnosticCollection, fileUri, receipt, result);
            showResult(result, path.basename(fileUri.fsPath));
        } catch (e) {
            vscode.window.showErrorMessage(`AIIR: ${(e as Error).message}`);
        }
    });

    // Verify selected text
    const verifySelectionCmd = vscode.commands.registerCommand('aiir.verifySelection', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showErrorMessage('AIIR: No active editor');
            return;
        }

        if (editor.document.uri.scheme === 'file' && !isUriAccessible(editor.document.uri)) {
            await showWorkspaceAccessRecovery('verify receipts in this folder');
            return;
        }

        const selection = editor.document.getText(editor.selection);
        if (!selection.trim()) {
            vscode.window.showErrorMessage('AIIR: No text selected');
            return;
        }

        try {
            const receipt = JSON.parse(selection);
            const result = verifyReceipt(receipt);
            showResult(result, 'selection');
        } catch (e) {
            vscode.window.showErrorMessage(`AIIR: ${(e as Error).message}`);
        }
    });

    // Verify CBOR sidecar integrity via CLI
    const verifyCborCmd = vscode.commands.registerCommand('aiir.verifyCbor', async (target?: unknown) => {
        const record = await getTargetReceiptRecord(target, explorer);
        if (!record) {
            vscode.window.showErrorMessage('AIIR: No receipt selected');
            return;
        }

        if (record.artifacts.cborStatus !== 'present' || !record.artifacts.cborUri) {
            vscode.window.showWarningMessage('AIIR: No CBOR sidecar found for this receipt');
            return;
        }

        const cliPath = getCliPath();
        const folder = vscode.workspace.getWorkspaceFolder(record.uri);
        const cwd = folder?.uri.fsPath || path.dirname(record.uri.fsPath);

        try {
            const result = await runCommand(cliPath, buildVerifyReceiptArgs(record.uri.fsPath), cwd, output);
            const combined = (result.stdout + '\n' + result.stderr).toLowerCase();
            if (combined.includes('cbor') && combined.includes('ok') || combined.includes('valid')) {
                vscode.window.showInformationMessage('AIIR: CBOR sidecar integrity verified ✅');
            } else {
                vscode.window.showInformationMessage('AIIR: CLI verification complete — check Output panel for details');
                output.show(true);
            }
        } catch (error) {
            const err = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
            if (err.stdout) { output.appendLine(err.stdout.trimEnd()); }
            if (err.stderr) { output.appendLine(err.stderr.trimEnd()); }
            if (err.code === 'ENOENT') {
                vscode.window.showErrorMessage(`AIIR: Could not find '${cliPath}'. Install AIIR or set aiir.cliPath.`);
            } else {
                vscode.window.showErrorMessage(`AIIR: CBOR verification failed — ${err.message}`);
            }
            output.show(true);
        }
    });

    // Verify Sigstore signature via CLI
    const verifySigstoreCmd = vscode.commands.registerCommand('aiir.verifySigstore', async (target?: unknown) => {
        const record = await getTargetReceiptRecord(target, explorer);
        if (!record) {
            vscode.window.showErrorMessage('AIIR: No receipt selected');
            return;
        }

        if (record.artifacts.sigstoreStatus !== 'present' || !record.artifacts.sigstoreUri) {
            vscode.window.showWarningMessage('AIIR: No Sigstore bundle found for this receipt');
            return;
        }

        const cliPath = getCliPath();
        const folder = vscode.workspace.getWorkspaceFolder(record.uri);
        const cwd = folder?.uri.fsPath || path.dirname(record.uri.fsPath);

        try {
            const result = await runCommand(cliPath, buildVerifyReceiptArgs(record.uri.fsPath, true), cwd, output);
            const combined = (result.stdout + '\n' + result.stderr).toLowerCase();
            if (combined.includes('signature verified') || (combined.includes('signature') && combined.includes('ok'))) {
                vscode.window.showInformationMessage('AIIR: Sigstore signature verified ✅');
            } else {
                vscode.window.showInformationMessage('AIIR: CLI verification complete — check Output panel for details');
                output.show(true);
            }
        } catch (error) {
            const err = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
            if (err.stdout) { output.appendLine(err.stdout.trimEnd()); }
            if (err.stderr) { output.appendLine(err.stderr.trimEnd()); }
            if (err.code === 'ENOENT') {
                vscode.window.showErrorMessage(`AIIR: Could not find '${cliPath}'. Install AIIR or set aiir.cliPath.`);
            } else {
                if (err.stderr?.toLowerCase().includes('sigstore')) {
                    const choice = await vscode.window.showErrorMessage(
                        'AIIR: Sigstore verification failed — optional signing support is not installed for this CLI.',
                        'Install Sigstore Support',
                        'Open Signing Guide',
                    );
                    if (choice === 'Install Sigstore Support') {
                        await vscode.commands.executeCommand('aiir.installSigstoreSupport');
                    } else if (choice === 'Open Signing Guide') {
                        await vscode.commands.executeCommand('aiir.openSigningGuide');
                    }
                } else {
                    vscode.window.showErrorMessage(`AIIR: Sigstore verification failed — ${err.message}`);
                }
            }
            output.show(true);
        }
    });

    // Refresh receipts
    const refreshCmd = vscode.commands.registerCommand('aiir.refresh', async () => {
        await refreshExtensionState();
        vscode.window.showInformationMessage('AIIR: Receipts refreshed');
    });

    // Commit Explorer commands
    const refreshCommitExplorerCmd = vscode.commands.registerCommand('aiir.refreshCommitExplorer', async () => {
        const commitFolders = getAccessibleWorkspaceFolders();
        const preferredFolder = resolvePreferredWorkspaceFolderTarget(
            commitFolders.map(f => ({ name: f.name, fsPath: f.uri.fsPath, value: f })),
            undefined,
            recentWorkspaceFolderPath,
        );
        await commitExplorer.refresh(preferredFolder?.uri.fsPath);
    });

    const viewCommitFileDiffCmd = vscode.commands.registerCommand('aiir.viewCommitFileDiff', async (commitSha?: string, filePath?: string, folderPath?: string) => {
        if (!commitSha || !filePath || !folderPath) {
            return;
        }
        try {
            const parentSha = `${commitSha}~1`;
            const leftUri = vscode.Uri.parse(`git-show:${parentSha}:${filePath}`).with({ scheme: 'aiir-diff', query: JSON.stringify({ commitSha: parentSha, filePath, folderPath }) });
            const rightUri = vscode.Uri.parse(`git-show:${commitSha}:${filePath}`).with({ scheme: 'aiir-diff', query: JSON.stringify({ commitSha, filePath, folderPath }) });
            const title = `${filePath} (${commitSha.slice(0, 8)})`;
            await vscode.commands.executeCommand('vscode.diff', leftUri, rightUri, title);
        } catch {
            // Fallback: just open the file at the commit version.
            vscode.window.showInformationMessage(`AIIR: Could not show diff for ${filePath}`);
        }
    });

    const viewGovernanceDiffCmd = vscode.commands.registerCommand('aiir.viewGovernanceDiff', async (commitSha?: string, folderPath?: string) => {
        if (!commitSha || !folderPath) {
            return;
        }
        const commit = (await commitExplorerDeps.getRecentCommits(folderPath, 100)).find(c => c.sha === commitSha);
        if (!commit) {
            vscode.window.showErrorMessage('AIIR: Commit not found');
            return;
        }
        const overlay = await commitExplorerDeps.getReceiptOverlay(folderPath, commitSha);
        const buildInput: GovernanceDiffBuildInput = {
            commit: {
                sha: commit.sha,
                shortSha: commit.shortSha,
                subject: commit.subject,
                authorName: commit.authorName,
                authorDate: commit.authorDate,
            },
            files: commit.files.map(f => ({ path: f.path, gitStatus: f.status })),
            receipt: overlay.hasReceipt ? {
                exists: true,
                valid: overlay.valid,
                evidenceTier: overlay.evidenceTier,
                sigstorePresent: overlay.sigstorePresent,
                inLedger: overlay.inLedger,
                receiptUri: overlay.receiptUri?.toString(),
                errorSummary: overlay.errorSummary,
                aiFileMap: new Map(
                    Array.from(overlay.aiFiles.entries()).map(([path, ai]) => [
                        path,
                        { tool: ai.tool, evidenceKind: ai.evidenceKind ?? 'none', modelInfo: ai.tool },
                    ]),
                ),
            } : undefined,
        };
        const viewModel = buildGovernanceDiffViewModel(buildInput);
        const panel = vscode.window.createWebviewPanel(
            'aiirGovernanceDiff',
            `AIIR Governance: ${commit.shortSha}`,
            vscode.ViewColumn.One,
            { enableScripts: false },
        );
        panel.webview.html = finalizeStaticWebviewHtml(
            getGovernanceDiffHtml(viewModel),
            panel.webview.cspSource,
        );
    });

    const toggleListenerCmd = vscode.commands.registerCommand('aiir.toggleListener', async () => {
        const state = copilotListener.getState();
        if (state.active) {
            await copilotListener.stop();
            vscode.window.showInformationMessage('AIIR: Passive AI edit tracking paused');
        } else {
            copilotListener.start();
            vscode.window.showInformationMessage('AIIR: Passive AI edit tracking resumed');
        }
    });

    const generateMissingReceiptsCmd = vscode.commands.registerCommand('aiir.generateMissingReceipts', async (folderPathArg?: unknown) => {
        const folder = await resolveCommandWorkspaceFolder(
            typeof folderPathArg === 'string' ? folderPathArg : undefined,
            'Choose a repository to generate receipts for',
        );
        if (!folder) {
            await showWorkspaceAccessRecovery('generate receipts');
            return;
        }
        if (!await isCliAvailable(folder)) {
            await openSetupForPendingAction({
                commandId: 'aiir.generateReceipt',
                label: 'Generate Missing Receipts',
                folderPath: folder.uri.fsPath,
            });
            return;
        }

        const limit = vscode.workspace.getConfiguration('aiir').get<number>('commitExplorerLimit', 20);
        const rangeSpec = `HEAD~${limit}..HEAD`;
        const cliArgs = buildGenerateRangeArgs(rangeSpec);

        try {
            await vscode.window.withProgress(
                {
                    location: vscode.ProgressLocation.Notification,
                    title: 'AIIR: Generating receipts for recent commits…',
                    cancellable: false,
                },
                async () => {
                    await runCommand(getCliPath(), cliArgs, folder.uri.fsPath, output);
                    await explorer.refresh();
                    await refreshCommitExplorerOverlays();
                    await statusBar.refresh(explorer);
                },
            );
            vscode.window.showInformationMessage(`AIIR: Receipts generated for recent commits in ${folder.name}`);
        } catch (error) {
            const err = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
            if (err.stdout) { output.appendLine(err.stdout.trimEnd()); }
            if (err.stderr) { output.appendLine(err.stderr.trimEnd()); }
            vscode.window.showErrorMessage(`AIIR: Batch receipt generation failed — ${err.message}`);
            output.show(true);
        }
    });

    const openReceiptSourceCmd = vscode.commands.registerCommand('aiir.openReceiptSource', async (target?: unknown) => {
        const fileUri = resolveTargetUri(target) || vscode.window.activeTextEditor?.document.uri;
        if (!fileUri) {
            vscode.window.showErrorMessage('AIIR: No receipt selected');
            return;
        }

        await vscode.commands.executeCommand('vscode.open', fileUri);
    });

    const openTreeFileCmd = vscode.commands.registerCommand('aiir.openTreeFile', async (target?: unknown) => {
        const fileUri = resolveTargetUri(target);
        if (!fileUri) {
            vscode.window.showErrorMessage('AIIR: No file selected');
            return;
        }

        await vscode.commands.executeCommand('vscode.open', fileUri);
    });

    const openAttestedDiffComparisonCmd = vscode.commands.registerCommand('aiir.openAttestedDiffComparison', async (target?: unknown) => {
        const comparisonTarget = parseAttestedDiffComparisonTarget(target);
        if (!comparisonTarget) {
            vscode.window.showErrorMessage('AIIR: No attested diff comparison target was provided');
            return;
        }

        const record = await getTargetReceiptRecord(comparisonTarget.receiptUri, explorer);
        if (!record) {
            vscode.window.showErrorMessage('AIIR: No receipt selected for comparison');
            return;
        }

        rememberWorkspaceFolder(vscode.workspace.getWorkspaceFolder(record.uri));
        await homeProvider.refresh(record.uri);

        const resolved = await resolveRecoverableAttestedDiff(record, comparisonTarget);
        if (!resolved) {
            vscode.window.showWarningMessage('AIIR: Could not reconstruct both attested snapshots for this update. Compare is available only when the hashes match recoverable base, receipt, or workspace file content.');
            return;
        }

        const [beforeDocument, afterDocument] = await Promise.all([
            vscode.workspace.openTextDocument({ content: resolved.before.content }),
            vscode.workspace.openTextDocument({ content: resolved.after.content }),
        ]);

        const beforeLabel = getRecoverableSnapshotMatchLabel(resolved.before, 'before');
        const afterLabel = getRecoverableSnapshotMatchLabel(resolved.after, 'after');

        await vscode.commands.executeCommand(
            'vscode.diff',
            beforeDocument.uri,
            afterDocument.uri,
            `${path.basename(comparisonTarget.filePath)} · ${beforeLabel} vs ${afterLabel}`,
        );
        vscode.window.showInformationMessage(`AIIR: Recoverable diff opened using ${beforeLabel} and ${afterLabel}.`);
    });

    const viewAttestedDiffFileCmd = vscode.commands.registerCommand('aiir.viewAttestedDiffFile', async (target?: unknown) => {
        if (!(target instanceof EditorDiffFileItem)) {
            vscode.window.showErrorMessage('AIIR: No attested diff file selected');
            return;
        }

        rememberWorkspaceFolder(vscode.workspace.getWorkspaceFolder(target.record.uri));
        await homeProvider.refresh(target.record.uri);

        const shaShort = target.record.receipt.commit?.sha?.slice(0, 8) || '?';
        const panel = vscode.window.createWebviewPanel(
            'aiir.attestedDiffViewer',
            `${path.basename(target.filePath)} · ${shaShort}`,
            vscode.ViewColumn.One,
            { enableScripts: true },
        );

        panel.webview.html = finalizeScriptedWebviewHtml(
            getAttestedDiffPanelHtml({
                filePath: target.filePath,
                fileUri: target.fileUri?.toString(),
                receiptUri: target.record.uri.toString(),
                receiptSubject: getReceiptSubject(target.record.receipt),
                receiptShaShort: shaShort,
                eventCount: target.events.length,
                events: target.events.map(event => ({
                    ...event,
                    comparisonTarget: {
                        receiptUri: target.record.uri.toString(),
                        filePath: target.filePath,
                        fileUri: target.fileUri?.toString(),
                        beforeHash: event.beforeHash,
                        afterHash: event.afterHash,
                        baseCommitSha: event.baseCommitSha,
                        createdAt: event.createdAt,
                    },
                })),
            }),
            panel.webview.cspSource,
        );
        panel.webview.onDidReceiveMessage(executePanelMessage);
    });

    // Show summary dashboard
    const showSummaryCmd = vscode.commands.registerCommand('aiir.showSummary', async (target?: unknown) => {
        const folder = getDefaultWorkspaceFolderCandidate(target);
        if (folder) {
            rememberWorkspaceFolder(folder);
        }

        const stats = folder ? explorer.getStats(folder) : explorer.getStats();
        const aiPercent = stats.total > 0 ? Math.round(stats.aiAuthored / stats.total * 100) : 0;
        const folderStats = !folder && explorer.isMultiRoot() ? explorer.getFolderStats() : undefined;

        const panel = vscode.window.createWebviewPanel(
            'aiir.summary',
            'AIIR Receipt Summary',
            vscode.ViewColumn.One,
            { enableScripts: true },
        );

        panel.webview.html = finalizeScriptedWebviewHtml(
            getSummaryHtml(stats, aiPercent, folderStats, folder?.uri.toString()),
            panel.webview.cspSource,
        );
        panel.webview.onDidReceiveMessage(executePanelMessage);
    });

    // Control panel dashboard
    const controlPanelCmd = vscode.commands.registerCommand('aiir.controlPanel', async (uri?: vscode.Uri) => {
        const folder = await resolveCommandWorkspaceFolder(uri, 'Choose a repository for the control panel');
        if (!folder) {
            await showWorkspaceAccessRecovery('use the control panel');
            return;
        }

        await explorer.refresh();
        await statusBar.refresh(explorer);

        const hubState = await getHubConnectionState(context, output);
        const health = await collectHealthCheck(folder, explorer, output, hubState);
        const stats = explorer.getStats(folder);

        const panel = vscode.window.createWebviewPanel(
            'aiir.controlPanel',
            'AIIR Control Panel',
            vscode.ViewColumn.One,
            { enableScripts: true },
        );

        panel.webview.html = finalizeScriptedWebviewHtml(
            getControlPanelHtml(stats, health, isHubEnabled(), folder.uri.toString()),
            panel.webview.cspSource,
        );

        panel.webview.onDidReceiveMessage(executePanelMessage);
    });

    // Human-first receipt viewer
    const viewReceiptForCommitCmd = vscode.commands.registerCommand('aiir.viewReceiptForCommit', async (commitSha?: string, folderPath?: string) => {
        if (!commitSha || !folderPath) {
            return;
        }
        const folders = getAccessibleWorkspaceFolders();
        const folder = folders.find(f => f.uri.fsPath === folderPath);
        const record = explorer.getReceiptForCommit(commitSha, folder);
        if (!record) {
            vscode.window.showErrorMessage('AIIR: No receipt found for this commit.');
            return;
        }

        rememberWorkspaceFolder(folder);
        await homeProvider.refresh(record.uri);

        const shaShort = record.receipt.commit?.sha?.slice(0, 8) || '?';
        const subject = getReceiptSubject(record.receipt);
        const panel = vscode.window.createWebviewPanel(
            'aiir.receiptViewer',
            `${subject} · ${shaShort}`,
            vscode.ViewColumn.One,
            { enableScripts: true },
        );

        const currentHeadSha = folder ? await getCurrentCommitSha(folder) : undefined;
        panel.webview.html = finalizeScriptedWebviewHtml(
            getReceiptViewerHtml(record, getReceiptFailureExplanation, buildReceiptRepairPlan(record, currentHeadSha)),
            panel.webview.cspSource,
        );
        panel.webview.onDidReceiveMessage(async message => {
            if (message?.command === 'aiir.copyReceiptSummary') {
                await vscode.commands.executeCommand('aiir.copyReceiptSummary', record);
                return;
            }
            if (message?.command === 'aiir.previewReceiptSummary') {
                await vscode.commands.executeCommand('aiir.previewReceiptSummary', record);
                return;
            }
            if (message?.command === 'aiir.openReceiptSource') {
                await vscode.commands.executeCommand('aiir.openReceiptSource', record.uri);
                return;
            }
            await executePanelMessage(message);
        });
    });

    const viewReceiptCmd = vscode.commands.registerCommand('aiir.viewReceipt', async (target?: unknown) => {
        const record = await getTargetReceiptRecord(target, explorer);
        if (!record) {
            vscode.window.showErrorMessage('AIIR: No receipt found. Open a receipt file or generate one first.');
            return;
        }

        rememberWorkspaceFolder(vscode.workspace.getWorkspaceFolder(record.uri));
        await homeProvider.refresh(record.uri);

        const shaShort = record.receipt.commit?.sha?.slice(0, 8) || '?';
        const subject = getReceiptSubject(record.receipt);
        const panel = vscode.window.createWebviewPanel(
            'aiir.receiptViewer',
            `${subject} · ${shaShort}`,
            vscode.ViewColumn.One,
            { enableScripts: true },
        );

        const folder = vscode.workspace.getWorkspaceFolder(record.uri);
        const currentHeadSha = folder ? await getCurrentCommitSha(folder) : undefined;
        panel.webview.html = finalizeScriptedWebviewHtml(
            getReceiptViewerHtml(record, getReceiptFailureExplanation, buildReceiptRepairPlan(record, currentHeadSha)),
            panel.webview.cspSource,
        );
        panel.webview.onDidReceiveMessage(async message => {
            if (message?.command === 'aiir.copyReceiptSummary') {
                await vscode.commands.executeCommand('aiir.copyReceiptSummary', record);
                return;
            }
            if (message?.command === 'aiir.previewReceiptSummary') {
                await vscode.commands.executeCommand('aiir.previewReceiptSummary', record);
                return;
            }
            if (message?.command === 'aiir.openReceiptSource') {
                await vscode.commands.executeCommand('aiir.openReceiptSource', record.uri);
                return;
            }
            await executePanelMessage(message);
        });
    });

    const fixLatestFailedReceiptCmd = vscode.commands.registerCommand('aiir.fixLatestFailedReceipt', async (target?: unknown) => {
        const folder = getDefaultWorkspaceFolderCandidate(target);
        const failedRecord = explorer.getRecentReceipts(50, folder).find(record => !record.result.valid);
        if (!failedRecord) {
            vscode.window.showInformationMessage('AIIR: No failed receipts need repair right now.');
            return;
        }

        rememberWorkspaceFolder(vscode.workspace.getWorkspaceFolder(failedRecord.uri));
        await vscode.commands.executeCommand('aiir.viewReceipt', failedRecord.uri);
    });

    // Configure MCP server for Copilot Chat integration
    const configureMcpServerCmd = vscode.commands.registerCommand('aiir.configureMcpServer', async (uri?: vscode.Uri) => {
        const folder = await resolveCommandWorkspaceFolder(uri, 'Select workspace for MCP configuration');
        if (!folder) { return; }

        const vscodeDirUri = vscode.Uri.joinPath(folder.uri, '.vscode');
        const mcpJsonUri = vscode.Uri.joinPath(vscodeDirUri, 'mcp.json');

        // Derive MCP server command from CLI path setting
        const cliPath = getCliPath();
        let mcpCommand = 'aiir-mcp-server';
        if (cliPath !== 'aiir') {
            const dir = path.dirname(cliPath);
            if (dir !== '.') {
                mcpCommand = path.join(dir, 'aiir-mcp-server');
            }
        }

        const serverConfig = {
            type: 'stdio',
            command: mcpCommand,
            args: ['--stdio'],
        };

        let existing: Record<string, unknown> | undefined;
        try {
            const bytes = await vscode.workspace.fs.readFile(mcpJsonUri);
            existing = JSON.parse(Buffer.from(bytes).toString('utf-8'));
        } catch {
            // File doesn't exist — will create
        }

        if (existing) {
            const servers = existing.servers as Record<string, unknown> | undefined;
            if (servers?.['aiir']) {
                const choice = await vscode.window.showInformationMessage(
                    'AIIR MCP server is already configured in .vscode/mcp.json. Copilot Chat can use AIIR tools.',
                    'Open mcp.json',
                    'Overwrite',
                );
                if (choice === 'Open mcp.json') {
                    await vscode.window.showTextDocument(mcpJsonUri);
                } else if (choice === 'Overwrite') {
                    servers['aiir'] = serverConfig;
                    await writeTextFile(mcpJsonUri.fsPath, JSON.stringify(existing, null, 2) + '\n');
                    vscode.window.showInformationMessage('AIIR MCP server configuration updated.');
                }
                return;
            }
            if (servers) {
                servers['aiir'] = serverConfig;
            } else {
                existing.servers = { aiir: serverConfig };
            }
            await writeTextFile(mcpJsonUri.fsPath, JSON.stringify(existing, null, 2) + '\n');
        } else {
            await vscode.workspace.fs.createDirectory(vscodeDirUri);
            const config = { servers: { aiir: serverConfig } };
            await writeTextFile(mcpJsonUri.fsPath, JSON.stringify(config, null, 2) + '\n');
        }

        const choice = await vscode.window.showInformationMessage(
            'AIIR MCP server configured. Copilot Chat can now generate, verify, and explain receipts.',
            'Open Copilot Chat',
            'Open mcp.json',
        );
        if (choice === 'Open Copilot Chat') {
            await vscode.commands.executeCommand('workbench.action.chat.open');
        } else if (choice === 'Open mcp.json') {
            await vscode.window.showTextDocument(mcpJsonUri);
        }
    });

    // Verify all receipts in workspace
    const verifyAllCmd = vscode.commands.registerCommand('aiir.verifyAll', async () => {
        await explorer.refresh();
        await homeProvider.refresh();
        const stats = explorer.getStats();
        await statusBar.refresh(explorer);

        if (stats.total === 0) {
            vscode.window.showInformationMessage('AIIR: No receipts found in workspace');
        } else if (stats.invalid === 0) {
            vscode.window.showInformationMessage(`AIIR: All ${stats.total} receipts verified ✅`);
        } else {
            vscode.window.showWarningMessage(`AIIR: ${stats.invalid}/${stats.total} receipts FAILED verification ❌`);
        }
    });

    // ── Compliance Integration Commands ────────────────────────────────────

    // Point 3: Signing guide — local webview with guidance for Sigstore signing in CI
    const openSigningGuideCmd = vscode.commands.registerCommand('aiir.openSigningGuide', async () => {
        const panel = vscode.window.createWebviewPanel(
            'aiir.signingGuide',
            'AIIR: Sigstore Signing Guide',
            vscode.ViewColumn.One,
            { enableScripts: false },
        );
        panel.webview.html = finalizeStaticWebviewHtml(getSigningGuideHtml(), panel.webview.cspSource);
    });

    // Point 4: Review a commit — approve, reject, or flag via CLI
    const reviewReceiptCmd = vscode.commands.registerCommand('aiir.reviewReceipt', async (target?: unknown) => {
        const folder = await resolveCommandWorkspaceFolder(target, 'Choose a repository');
        if (!folder || !await isCliAvailable(folder)) { return; }

        const recordTarget = getReceiptRecordFromTarget(target);
        let sha = recordTarget?.receipt.commit?.sha;
        if (!sha && target && typeof target === 'object') {
            const candidate = target as { sha?: string };
            sha = typeof candidate.sha === 'string' ? candidate.sha.trim() : undefined;
        }
        if (!sha) {
            const input = await vscode.window.showInputBox({ prompt: 'Commit SHA to review', placeHolder: 'e.g. abc1234' });
            if (!input) { return; }
            sha = input.trim();
        }

        const outcome = await vscode.window.showQuickPick(
            [
                { label: 'Approve', description: 'Mark this commit as reviewed and approved', value: 'approve' as ReviewSelectionValue },
                { label: 'Reject', description: 'Mark this commit as reviewed and rejected (reason required)', value: 'reject' as ReviewSelectionValue },
                { label: 'Flag', description: 'Flag this commit for further investigation (reason required)', value: 'flag' as ReviewSelectionValue },
            ],
            { placeHolder: 'Choose review outcome' },
        );
        if (!outcome) { return; }

        let comment = '';
        if (outcome.value === 'reject' || outcome.value === 'flag') {
            const reason = await vscode.window.showInputBox({
                prompt: `Reason for ${outcome.value} (required)`,
                validateInput: v => (v && v.trim().length >= 3) ? null : 'Please provide a reason (at least 3 characters)',
            });
            if (!reason) { return; }
            comment = reason.trim();
        }

        try {
            const args = buildReviewReceiptArgs(sha!, outcome.value, comment);
            const cliOutcome = mapReviewOutcomeToCli(outcome.value);
            await runCommand(getCliPath(), args, folder.uri.fsPath, output);
            await explorer.refresh();
            await homeProvider.refresh();
            vscode.window.showInformationMessage(`AIIR: Commit ${sha!.slice(0, 8)} marked as ${cliOutcome}`);
        } catch (error) {
            vscode.window.showErrorMessage(`AIIR: Review failed — ${(error as Error).message}`);
        }
    });

    // Point 4: View review history
    const viewReviewHistoryCmd = vscode.commands.registerCommand('aiir.viewReviewHistory', async (target?: unknown) => {
        const folder = await resolveCommandWorkspaceFolder(target, 'Choose a repository');
        if (!folder) { return; }

        const ledgerPath = path.join(folder.uri.fsPath, '.aiir', 'receipts.jsonl');
        if (!await pathExists(ledgerPath)) {
            vscode.window.showInformationMessage('AIIR: No receipt ledger found');
            return;
        }

        try {
            const content = await fs.promises.readFile(ledgerPath, 'utf-8');
            const reviews = content.split('\n')
                .filter(line => line.trim())
                .map(line => { try { return JSON.parse(line); } catch { return null; } })
                .filter(r => r?.review_outcome);

            if (reviews.length === 0) {
                vscode.window.showInformationMessage('AIIR: No review attestations found');
                return;
            }

            const panel = vscode.window.createWebviewPanel(
                'aiir.reviewHistory',
                'AIIR: Review History',
                vscode.ViewColumn.One,
                { enableScripts: false },
            );
            panel.webview.html = finalizeStaticWebviewHtml(getReviewHistoryHtml(reviews), panel.webview.cspSource);
        } catch (error) {
            vscode.window.showErrorMessage(`AIIR: Could not read review history — ${(error as Error).message}`);
        }
    });

    // Point 7: Record compliance exception
    const recordExceptionCmd = vscode.commands.registerCommand('aiir.recordException', async () => {
        const folder = await resolveCommandWorkspaceFolder(undefined, 'Choose a repository');
        if (!folder) { return; }

        const exceptionType = await vscode.window.showQuickPick(
            [
                { label: 'Coverage Gap', description: 'Missing receipt for one or more commits', value: 'coverage-gap' },
                { label: 'Unsigned Receipt', description: 'Receipt exists but lacks Sigstore signature', value: 'unsigned-receipt' },
                { label: 'Missing Review', description: 'AI-authored commit not reviewed by a human', value: 'missing-review' },
                { label: 'Heuristic Only', description: 'Evidence based on heuristic signals only', value: 'heuristic-only' },
            ],
            { placeHolder: 'Type of compliance exception' },
        );
        if (!exceptionType) { return; }

        const reason = await vscode.window.showInputBox({
            prompt: 'Required reason for this exception (min 10 characters)',
            validateInput: v => (v && v.trim().length >= 10) ? null : 'Please provide a reason with at least 10 characters',
        });
        if (!reason) { return; }

        try {
            const policyPath = path.join(folder.uri.fsPath, '.aiir', 'policy.json');
            let policy: JsonRecord = {};
            const existing = await readTextFile(policyPath);
            if (existing) {
                try { policy = JSON.parse(existing); } catch { /* start fresh */ }
            }
            if (!policy.extensions) { policy.extensions = {}; }
            const ext = policy.extensions as JsonRecord;
            if (!ext.vscode) { ext.vscode = {}; }
            const vsExt = ext.vscode as JsonRecord;
            if (!Array.isArray(vsExt.exceptions)) { vsExt.exceptions = []; }

            const headSha = await getCurrentCommitSha(folder);
            (vsExt.exceptions as unknown[]).push({
                type: exceptionType.value,
                reason: reason.trim(),
                timestamp: new Date().toISOString(),
                headSha: headSha || 'unknown',
            });

            await fs.promises.mkdir(path.dirname(policyPath), { recursive: true });
            await fs.promises.writeFile(policyPath, JSON.stringify(policy, null, 2) + '\n', 'utf-8');
            vscode.window.showInformationMessage(`AIIR: Exception recorded — ${exceptionType.label}`);
        } catch (error) {
            vscode.window.showErrorMessage(`AIIR: Could not record exception — ${(error as Error).message}`);
        }
    });

    // Point 8: Export evidence pack — local archive of all audit evidence
    const exportEvidencePackCmd = vscode.commands.registerCommand('aiir.exportEvidencePack', async () => {
        const folder = await resolveCommandWorkspaceFolder(undefined, 'Choose a repository');
        if (!folder) { return; }

        const aiirDir = path.join(folder.uri.fsPath, '.aiir');
        if (!await pathExists(aiirDir)) {
            vscode.window.showInformationMessage('AIIR: No .aiir directory found');
            return;
        }

        const destUri = await vscode.window.showSaveDialog({
            defaultUri: vscode.Uri.file(path.join(folder.uri.fsPath, `aiir-evidence-pack-${new Date().toISOString().slice(0, 10)}.json`)),
            filters: { 'JSON': ['json'] },
            title: 'Save Evidence Pack',
        });
        if (!destUri) { return; }

        try {
            const pack: JsonRecord = {
                schema: 'aiir/evidence-pack',
                version: '1',
                exportedAt: new Date().toISOString(),
                repository: folder.name,
            };
            let parsedPolicy: JsonRecord | null = null;
            const reviews: Array<JsonRecord> = [];
            let approvedCount = 0;
            let rejectedCount = 0;
            let flaggedCount = 0;

            // Collect policy
            const policyContent = await readTextFile(path.join(aiirDir, 'policy.json'));
            if (policyContent) {
                try {
                    parsedPolicy = JSON.parse(policyContent) as JsonRecord;
                    pack.policy = parsedPolicy;
                } catch {
                    pack.policy = null;
                }
            }
            const policyExtensions = parsedPolicy?.extensions as JsonRecord | undefined;
            const vscodeExtensions = policyExtensions?.vscode as JsonRecord | undefined;
            const exceptions = Array.isArray(vscodeExtensions?.exceptions)
                ? vscodeExtensions.exceptions as unknown[]
                : [];
            pack.exceptions = exceptions;

            // Collect ledger summary
            const ledgerContent = await readTextFile(path.join(aiirDir, 'receipts.jsonl'));
            if (ledgerContent) {
                const lines = ledgerContent.split('\n').filter(l => l.trim());
                pack.receiptCount = lines.length;
                for (const line of lines) {
                    try {
                        const parsed = JSON.parse(line) as JsonRecord;
                        const review = getReceiptReviewInfo(parsed);
                        if (!review) {
                            continue;
                        }

                        reviews.push({
                            commitSha: review.commitSha || '',
                            outcome: review.outcome,
                            reviewer: review.reviewer || '',
                            reviewedAt: review.timestamp || '',
                            comment: review.comment || '',
                        });
                        if (review.outcome === 'approve') {
                            approvedCount += 1;
                        } else if (review.outcome === 'reject') {
                            rejectedCount += 1;
                        } else if (review.outcome === 'flag') {
                            flaggedCount += 1;
                        }
                    } catch {
                        // Skip malformed lines.
                    }
                }
            }
            pack.reviews = reviews;
            pack.reviewSummary = {
                totalReviewed: reviews.length,
                approved: approvedCount,
                rejected: rejectedCount,
                flagged: flaggedCount,
            };

            // Collect health check
            const healthCheck = await collectHealthCheck(folder, explorer, output);
            pack.healthCheck = healthCheck;

            // Collect stats
            const stats = explorer.getStats();
            pack.stats = {
                total: stats.total,
                valid: stats.valid,
                invalid: stats.invalid,
                sigstorePresent: stats.sigstorePresent,
                tierSigned: stats.tierSigned,
                tierProvable: stats.tierProvable,
                tierHeuristic: stats.tierHeuristic,
                tierUnsigned: stats.tierUnsigned,
            };

            await fs.promises.writeFile(destUri.fsPath, JSON.stringify(pack, null, 2) + '\n', 'utf-8');
            const openChoice = await vscode.window.showInformationMessage(
                `AIIR: Evidence pack exported to ${path.basename(destUri.fsPath)}`,
                'Open File',
            );
            if (openChoice === 'Open File') {
                await vscode.window.showTextDocument(destUri);
            }
        } catch (error) {
            vscode.window.showErrorMessage(`AIIR: Export failed — ${(error as Error).message}`);
        }
    });

    // Point 10: Purge provenance queue
    const purgeProvenanceQueueCmd = vscode.commands.registerCommand('aiir.purgeProvenanceQueue', async () => {
        const folder = await resolveCommandWorkspaceFolder(undefined, 'Choose a repository');
        if (!folder) { return; }

        const queuePath = path.join(folder.uri.fsPath, '.aiir', PROVABLE_QUEUE_FILENAME);
        if (!await pathExists(queuePath)) {
            vscode.window.showInformationMessage('AIIR: No provenance queue found');
            return;
        }

        const confirm = await vscode.window.showWarningMessage(
            'This will permanently delete all provenance queue records. Consumed records that have already been committed to receipts are unaffected.',
            { modal: true },
            'Purge',
        );
        if (confirm !== 'Purge') { return; }

        try {
            await fs.promises.writeFile(queuePath, '', 'utf-8');
            vscode.window.showInformationMessage('AIIR: Provenance queue purged');
        } catch (error) {
            vscode.window.showErrorMessage(`AIIR: Purge failed — ${(error as Error).message}`);
        }
    });

    context.subscriptions.push(
        ...receiptCommandDisposables,
        generateWithProvenanceCmd,
        copyReceiptSummaryCmd,
        previewReceiptSummaryCmd,
        initializeRepoCmd,
        healthCheckCmd,
        enableAutoReceiptingCmd,
        manageRepositoriesCmd,
        switchRepositoryCmd,
        copyCliInstallCommandCmd,
        installCliNowCmd,
        installSigstoreSupportCmd,
        openCliInstallTerminalCmd,
        disableAutoReceiptingCmd,
        connectHubCmd,
        disconnectHubCmd,
        hubStatusCmd,
        hubVerifyReceiptCmd,
        hubLatestReportCmd,
        hubEvidencePackCmd,
        hubRunAttestationCmd,
        openHubCmd,
        openHostedHubSignupCmd,
        reportBugCmd,
        signUpForHubCmd,
        hubBillingCmd,
        advancedSettingsCmd,
        openPolicyFileCmd,
        createWorkspacePolicyCmd,
        configureProvenanceQueueCmd,
        editPolicyTargetsCmd,
        toggleCurrentPolicyTargetCmd,
        readinessCheckCmd,
        securityPostureCmd,
        rolloutPresetsCmd,
        applyPresetCmd,
        openWalkthroughCmd,
        openHubPricingCmd,
        verifyFileCmd,
        verifySelectionCmd,
        verifyCborCmd,
        verifySigstoreCmd,
        refreshCmd,
        refreshCommitExplorerCmd,
        viewCommitFileDiffCmd,
        viewGovernanceDiffCmd,
        toggleListenerCmd,
        generateMissingReceiptsCmd,
        openReceiptSourceCmd,
        openTreeFileCmd,
        openAttestedDiffComparisonCmd,
        viewAttestedDiffFileCmd,
        showSummaryCmd,
        controlPanelCmd,
        viewReceiptForCommitCmd,
        viewReceiptCmd,
        fixLatestFailedReceiptCmd,
        verifyAllCmd,
        configureMcpServerCmd,
        openSigningGuideCmd,
        reviewReceiptCmd,
        viewReviewHistoryCmd,
        recordExceptionCmd,
        exportEvidencePackCmd,
        purgeProvenanceQueueCmd,
    );

    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(async event => {
            const revertedKeys = await enforceLockedPresetSettings(event);
            const affectsIsolation = event.affectsConfiguration('aiir.allowedWorkspaceFolders') ||
                event.affectsConfiguration('aiir.enforceWorkspaceIsolation') ||
                revertedKeys.some(key => key === 'aiir.allowedWorkspaceFolders' || key === 'aiir.enforceWorkspaceIsolation');
            const affectsNetwork = event.affectsConfiguration('aiir.strictLocalOnly') ||
                event.affectsConfiguration('aiir.enableHubFeatures') ||
                revertedKeys.some(key => key === 'aiir.strictLocalOnly' || key === 'aiir.enableHubFeatures');
            const affectsLockPreset = event.affectsConfiguration('aiir.lockPreset');

            if (revertedKeys.length > 0) {
                const preset = getActiveLockPreset();
                const label = preset ? `'${preset.title}'` : 'the active preset';
                vscode.window.showWarningMessage(
                    `AIIR: Reverted ${revertedKeys.join(', ')} because they are locked by preset ${label}.`,
                );
            }

            if (!affectsIsolation && !affectsNetwork && !affectsLockPreset) {
                return;
            }

            if (affectsIsolation) {
                watcher.dispose();
                watcher = createReceiptWatcher(explorer, statusBar, diagnosticCollection, updateSidebarChrome, async () => {
                    await homeProvider.refresh();
                    await refreshCommitExplorerOverlays();
                });
                await recreateGitWatcher();
            }

            await syncContextKeys();
            await refreshExtensionState(affectsIsolation || revertedKeys.length > 0);
        }),
        vscode.workspace.onDidChangeWorkspaceFolders(async () => {
            watcher.dispose();
            watcher = createReceiptWatcher(explorer, statusBar, diagnosticCollection, updateSidebarChrome, async () => {
                await homeProvider.refresh();
                await refreshCommitExplorerOverlays();
            });
            await recreateGitWatcher();
            await refreshExtensionState(true);
        }),
        vscode.window.onDidChangeWindowState(async state => {
            if (state.focused && getPendingAction()) {
                await refreshExtensionState();
            }
        }),
        vscode.window.onDidChangeActiveTextEditor(async editor => {
            rememberWorkspaceFolder(editor ? vscode.workspace.getWorkspaceFolder(editor.document.uri) : undefined);
            await homeProvider.refresh();
        }),
        vscode.window.onDidCloseTerminal(async () => {
            if (getPendingAction()) {
                await refreshExtensionState();
            }
        }),
        vscode.workspace.onDidOpenTextDocument(document => {
            if (document.uri.scheme === 'file') {
                contentTracker.set(document.uri.fsPath, sha256Text(document.getText()));
            }
        }),
        vscode.workspace.onDidSaveTextDocument(async document => {
            await capturePassiveProvenance(document);
        }),
    );

    // ── Initial scan ──────────────────────────────────────────────────
    for (const doc of vscode.workspace.textDocuments) {
        if (doc.uri.scheme === 'file') {
            contentTracker.set(doc.uri.fsPath, sha256Text(doc.getText()));
        }
    }

    void (async () => {
        try {
            await syncContextKeys();
            await recreateGitWatcher();
            await explorer.refresh();

            if (marketplaceCaptureSurface) {
                await maybeRunMarketplaceCaptureSurface();
                return;
            }

            await maybeShowFirstRunReadiness();
            await refreshExtensionState();
            await maybeRunMarketplaceCaptureSurface();
        } catch (error) {
            if (marketplaceCaptureSurface) {
                const message = error instanceof Error ? error.message : String(error);
                output.appendLine(`AIIR: Marketplace capture startup failed — ${message}`);
                await writeMarketplaceCaptureMarker('error', { message, phase: 'startup' });
                return;
            }

            throw error;
        }
    })();
}

// ── UI Helpers ────────────────────────────────────────────────────────

function showResult(result: VerifyResult, source: string) {
    if (result.valid) {
        vscode.window.showInformationMessage(`✅ AIIR: Receipt verified (${source})`);
    } else {
        vscode.window.showWarningMessage(`❌ AIIR: Verification failed — ${result.errors.join('; ')} (${source})`);
    }
}

function getSecurityPostureHtml(view: SecurityPostureViewModel): string {
    const allowlist = view.allowedWorkspaceFolders.length > 0
        ? view.allowedWorkspaceFolders.map(folder => `<li><code>${escapeHtml(folder)}</code></li>`).join('')
        : '<li>No explicit allowlist configured.</li>';

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIIR Security Posture</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 24px; max-width: 860px; line-height: 1.7; }
        h1 { font-size: 1.5em; margin-bottom: 8px; }
        h2 { font-size: 1.08em; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--vscode-panel-border); }
        ${getPanelNavStyles()}
        .hero { padding: 18px 20px; border-radius: 14px; border: 1px solid var(--vscode-panel-border); background: linear-gradient(180deg, color-mix(in srgb, var(--vscode-editor-background) 92%, var(--vscode-editorWarning-foreground) 8%), var(--vscode-editor-background)); }
        .hero-badges, .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
        .card { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 12px; padding: 14px; }
        .label { font-size: 0.8em; opacity: 0.55; text-transform: uppercase; letter-spacing: 0.04em; }
        .value { margin-top: 4px; font-size: 0.96em; word-break: break-word; }
        .badge { display: inline-block; font-size: 0.72em; font-weight: 600; border: 1.5px solid; border-radius: 99px; padding: 0.15em 0.65em; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; }
        .badge.ok { border-color: var(--vscode-testing-iconPassed); color: var(--vscode-testing-iconPassed); }
        .badge.warn { border-color: var(--vscode-editorWarning-foreground); color: var(--vscode-editorWarning-foreground); }
        .badge.off { border-color: var(--vscode-descriptionForeground); color: var(--vscode-descriptionForeground); opacity: 0.65; }
        button { font: inherit; cursor: pointer; border: none; border-radius: 6px; padding: 8px 16px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
        button:hover { background: var(--vscode-button-hoverBackground); }
        button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
        button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
        ul { margin: 10px 0 0 18px; opacity: 0.86; }
        pre { margin-top: 12px; white-space: pre-wrap; word-break: break-word; background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 10px; padding: 14px; font-family: var(--vscode-editor-font-family); }
    </style>
</head>
<body>
    ${getPanelNavHtml('security', { networkAllowed: view.networkAllowed, hubVisible: view.hubEnabled, showAdvanced: getShowAdvancedCommands() })}
    <div class="hero">
        <h1>Security Posture</h1>
        <p>Review the current trust boundary for this workspace: local-only mode, multi-root isolation, accessible repositories, and the exact settings that define network and discovery behavior.</p>
        <div class="hero-badges">
            <span class="badge ${view.strictLocalOnly ? 'ok' : 'warn'}">${view.strictLocalOnly ? 'local-only enabled' : 'network allowed'}</span>
            <span class="badge ${view.enforceWorkspaceIsolation ? 'ok' : 'warn'}">${view.enforceWorkspaceIsolation ? 'isolation enforced' : 'discovery relaxed'}</span>
            <span class="badge ${view.isolationBlockingAccess ? 'warn' : 'ok'}">${view.accessibleWorkspaceCount}/${view.workspaceCount} folders accessible</span>
        </div>
        <div class="actions">
            <button onclick="cmd('aiir.advancedSettings')">Open Advanced Settings</button>
            <button class="secondary" onclick="cmd('workbench.action.openWorkspaceSettingsFile')">Open Workspace Settings JSON</button>
        </div>
    </div>

    <section>
        <h2>Trust Boundary</h2>
        <div class="grid">
            <div class="card"><div class="label">Network posture</div><div class="value">${view.networkAllowed ? 'Network-backed Hub commands may run in this workspace.' : 'All Hub and network-backed commands are blocked by default.'}</div></div>
            <div class="card"><div class="label">Discovery posture</div><div class="value">${view.enforceWorkspaceIsolation ? 'Multi-root discovery is constrained to explicitly allowed folders.' : 'All open folders may be discovered and targeted.'}</div></div>
            <div class="card"><div class="label">Settings scope</div><div class="value">AIIR writes extension settings to workspace scope, not global user scope.</div></div>
            <div class="card"><div class="label">CLI path</div><div class="value"><code>${escapeHtml(view.cliPath)}</code></div></div>
        </div>
    </section>

    <section>
        <h2>Accessible Repositories</h2>
        <div class="grid">
            <div class="card"><div class="label">Workspace folders</div><div class="value">${view.workspaceCount}</div></div>
            <div class="card"><div class="label">Accessible folders</div><div class="value">${view.accessibleWorkspaceCount}</div></div>
            <div class="card"><div class="label">Isolation lockout</div><div class="value">${view.isolationBlockingAccess ? 'Automatic discovery is blocked until an allowlist is configured.' : 'Current workspace access is aligned with the configured allowlist.'}</div></div>
        </div>
        <pre>${escapeHtml(JSON.stringify({
        'aiir.allowedWorkspaceFolders': view.allowedWorkspaceFolders,
        'aiir.enforceWorkspaceIsolation': view.enforceWorkspaceIsolation,
        'aiir.strictLocalOnly': view.strictLocalOnly,
        'aiir.enableHubFeatures': view.enableHubFeatures,
        'aiir.hubBaseUrl': view.hubBaseUrl,
    }, null, 2))}</pre>
        <ul>${allowlist}</ul>
    </section>
    ${getPanelScript()}
</body>
</html>`;
}

function getRolloutPresetsHtml(view: RolloutPresetViewModel): string {
    const cards = view.presets.map(preset => `<div class="card">
        <h3>${escapeHtml(preset.title)}</h3>
        <p>${escapeHtml(preset.description)}</p>
        ${Object.keys(preset.settings).length > 0
            ? `<pre>${escapeHtml(JSON.stringify(preset.settings, null, 2))}</pre>`
            : `<div class="note">${escapeHtml(preset.note || 'No local workspace settings are changed by this preset.')}</div>`}
        <div class="actions"><button onclick="${renderCommandCall('aiir.applyPreset', [preset.id])}">${escapeHtml(preset.actionLabel || 'Apply Preset')}</button></div>
    </div>`).join('');

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIIR Deployment Presets</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 24px; max-width: 900px; line-height: 1.7; }
        h1 { font-size: 1.5em; margin-bottom: 8px; }
        h2 { font-size: 1.08em; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--vscode-panel-border); }
        ${getPanelNavStyles()}
        .hero { padding: 18px 20px; border-radius: 14px; border: 1px solid var(--vscode-panel-border); background: linear-gradient(180deg, color-mix(in srgb, var(--vscode-editor-background) 92%, var(--vscode-charts-blue) 8%), var(--vscode-editor-background)); }
        .hint { margin-top: 10px; opacity: 0.76; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 12px; }
        .card { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 12px; padding: 16px; }
        .card h3 { margin-bottom: 6px; font-size: 1.02em; }
        .card p { opacity: 0.8; min-height: 4.4em; }
        .note { margin-top: 12px; opacity: 0.74; font-size: 0.92em; }
        pre { margin-top: 12px; white-space: pre-wrap; word-break: break-word; background: color-mix(in srgb, var(--vscode-editor-background) 96%, var(--vscode-panel-border) 4%); border: 1px solid var(--vscode-panel-border); border-radius: 10px; padding: 14px; font-family: var(--vscode-editor-font-family); font-size: 0.88em; }
        .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
        button { font: inherit; cursor: pointer; border: none; border-radius: 6px; padding: 8px 16px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
        button:hover { background: var(--vscode-button-hoverBackground); }
    </style>
</head>
<body>
    ${getPanelNavHtml('presets', { networkAllowed: isNetworkAllowed(), hubVisible: isHubEnabled(), commandTarget: view.selectedWorkspaceUri, showAdvanced: getShowAdvancedCommands() })}
    <div class="hero">
        <h1>Deployment Presets</h1>
        <p>Apply opinionated workspace-scoped setting bundles for common deployment modes instead of configuring each option manually.</p>
        <div class="hint">${escapeHtml(view.selectedWorkspaceName ? `Current repository context: ${view.selectedWorkspaceName}` : 'No single repository context is selected. Presets that need an allowlist use the current active or accessible repository when possible.')}</div>
    </div>

    <section>
        <h2>Preset Library</h2>
        <div class="grid">${cards}</div>
    </section>

    ${getPanelScript()}
</body>
</html>`;
}

function getSummaryHtml(
    stats: ReceiptStats,
    aiPercent: number,
    folderStats?: Map<string, ReceiptStats>,
    targetUri?: string,
): string {
    const targetArgs = targetUri ? [targetUri] : [];
    const fixActionDisabled = stats.invalid === 0;
    const heuristicUpgrade = stats.tierHeuristic > 0
        ? `<div class="callout"><strong>${stats.tierHeuristic} heuristic receipt${stats.tierHeuristic === 1 ? '' : 's'} need a stronger next step.</strong><p>${escapeHtml(EVIDENCE_TIER_UPGRADE_GUIDANCE.heuristic)}</p>${getShowAdvancedCommands() ? `<div class="actions"><button onclick="${renderCommandCall('aiir.generatePreferred', targetArgs)}">Generate</button><button class="secondary" onclick="${renderCommandCall('aiir.generateWithProvenance', targetArgs)}">Generate With Provenance</button></div>` : ''}</div>`
        : '';
    const signingUpgrade = stats.total > 0 && stats.tierSigned < stats.total
        ? `<div class="callout"><strong>${stats.total - stats.tierSigned} receipt${stats.total - stats.tierSigned === 1 ? '' : 's'} are not signed yet.</strong><p>${escapeHtml(EVIDENCE_TIER_UPGRADE_GUIDANCE.provable)}</p>${getShowAdvancedCommands() ? `<div class="actions"><button onclick="cmd('aiir.openSigningGuide')">Open Signing Guide</button></div>` : ''}</div>`
        : '';
    let folderSection = '';
    if (folderStats && folderStats.size > 1) {
        const rows = Array.from(folderStats.entries()).map(([name, fs]) => {
            const pct = fs.total > 0 ? Math.round(fs.aiAuthored / fs.total * 100) : 0;
            return `<tr>
                <td>${escapeHtml(name)}</td>
                <td>${fs.total}</td>
                <td>${fs.valid}</td>
                <td class="fail">${fs.invalid}</td>
                <td>${fs.aiAuthored} (${pct}%)</td>
                <td>${fs.cborPresent}</td>
                <td>${fs.sigstorePresent}</td>
            </tr>`;
        }).join('\n');

        folderSection = `
    <h2 style="margin-top:28px;">📂 Per-Repository Breakdown</h2>
    <table class="folder-table">
        <thead>
            <tr>
                <th>Repository</th>
                <th>Total</th>
                <th>✅</th>
                <th>❌</th>
                <th>🤖 AI</th>
                <th>📦 CBOR</th>
                <th>🔐 Sigstore</th>
            </tr>
        </thead>
        <tbody>
            ${rows}
        </tbody>
    </table>`;
    }

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIIR Receipt Summary</title>
    <style>
        body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 20px; }
        h1 { font-size: 1.4em; margin-bottom: 20px; }
        h2 { font-size: 1.15em; margin-bottom: 12px; }
        ${getPanelNavStyles()}
        .grid { display: grid; grid-template-columns: repeat(3, minmax(140px, 1fr)); gap: 16px; max-width: 760px; }
        .card { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border);
                border-radius: 8px; padding: 16px; text-align: center; }
        .card .value { font-size: 2em; font-weight: bold; }
        .card .label { font-size: 0.85em; opacity: 0.7; margin-top: 4px; }
        .valid .value { color: var(--vscode-testing-iconPassed); }
        .invalid .value { color: var(--vscode-testing-iconFailed); }
        .bar { height: 8px; border-radius: 4px; background: var(--vscode-progressBar-background);
               margin-top: 20px; max-width: 500px; }
        .bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
        .bar-label { font-size: 0.85em; opacity: 0.7; margin-top: 6px; }
        .folder-table { border-collapse: collapse; margin-top: 8px; width: 100%; max-width: 760px; }
        .folder-table th, .folder-table td { text-align: left; padding: 6px 12px; border-bottom: 1px solid var(--vscode-panel-border); }
        .folder-table th { opacity: 0.7; font-size: 0.85em; }
        .folder-table .fail { color: var(--vscode-testing-iconFailed); }
        .callout { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 8px; padding: 14px 16px; margin-top: 18px; max-width: 760px; }
        .hero { max-width: 760px; margin-bottom: 18px; }
        .hero p { margin-top: 8px; opacity: 0.8; }
        .callout p { margin-top: 6px; opacity: 0.8; }
        .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
        button { font: inherit; cursor: pointer; border: none; border-radius: 6px; padding: 8px 16px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
        button:hover { background: var(--vscode-button-hoverBackground); }
        button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
        button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
        button:disabled { opacity: 0.45; cursor: not-allowed; }
    </style>
</head>
<body>
    ${getPanelNavHtml('summary', { networkAllowed: isNetworkAllowed(), hubVisible: isHubEnabled(), commandTarget: targetUri, showAdvanced: getShowAdvancedCommands() })}
    <h1>🛡️ AIIR Receipt Summary</h1>
    <div class="callout hero">
        <strong>Core Workflow</strong>
        <p>Stay on the default path: set up the repository, generate receipts for current work, verify what exists, and jump straight into the latest failure when something needs attention.</p>
        <div class="actions">
            <button onclick="${renderCommandCall('aiir.readinessCheck', targetArgs)}">Setup</button>
            <button onclick="${renderCommandCall('aiir.generatePreferred', targetArgs)}">Generate</button>
            <button ${stats.total === 0 ? 'disabled' : ''} onclick="cmd('aiir.verifyAll')">Verify</button>
            <button class="secondary" ${fixActionDisabled ? 'disabled' : ''} onclick="${renderCommandCall('aiir.fixLatestFailedReceipt', targetArgs)}">Fix</button>
        </div>
    </div>
    <div class="grid">
        <div class="card">
            <div class="value">${stats.total}</div>
            <div class="label">Total Receipts</div>
        </div>
        <div class="card valid">
            <div class="value">${stats.valid}</div>
            <div class="label">✅ Verified</div>
        </div>
        <div class="card invalid">
            <div class="value">${stats.invalid}</div>
            <div class="label">❌ Failed</div>
        </div>
        <div class="card">
            <div class="value">${stats.aiAuthored}</div>
            <div class="label">🤖 AI-Authored</div>
        </div>
        <div class="card">
            <div class="value">${stats.cborPresent}</div>
            <div class="label">📦 CBOR Sidecars</div>
        </div>
        <div class="card">
            <div class="value">${stats.sigstorePresent}</div>
            <div class="label">🔐 Sigstore Bundles</div>
        </div>
    </div>
    <div class="bar">
        <div class="bar-fill" style="width:${aiPercent}%; background: var(--vscode-charts-blue);"></div>
    </div>
    <div class="bar-label">${aiPercent}% AI-authored commits</div>
    <h2 style="margin-top:28px;">Evidence Tiers</h2>
    <div class="grid">
        <div class="card">
            <div class="value">${stats.tierSigned}</div>
            <div class="label">Signed</div>
        </div>
        <div class="card">
            <div class="value">${stats.tierProvable}</div>
            <div class="label">Provable</div>
        </div>
        <div class="card">
            <div class="value">${stats.tierHeuristic}</div>
            <div class="label">Heuristic</div>
        </div>
    </div>
    <div class="grid" style="margin-top:16px; max-width: 240px;">
        <div class="card">
            <div class="value">${stats.tierUnsigned}</div>
            <div class="label">Unsigned</div>
        </div>
    </div>
    ${heuristicUpgrade}
    ${signingUpgrade}
    ${folderSection}
    ${getPanelScript()}
</body>
</html>`;
}

function healthValue(ok: boolean, label: string): string {
    return ok ? `✅ ${label}` : `❌ ${label}`;
}

function hookLabel(kind: HealthCheckResult['postCommitHook']): string {
    if (kind === 'managed') {
        return '✅ Managed AIIR hook installed';
    }
    if (kind === 'custom') {
        return '⚠️ Custom post-commit hook present';
    }
    return '❌ No post-commit hook';
}

function receiptLabel(kind: HealthCheckResult['headReceiptStatus']): string {
    if (kind === 'present') {
        return '✅ HEAD commit has a receipt';
    }
    if (kind === 'missing') {
        return '❌ HEAD commit is not recorded';
    }
    return '⚪ Receipt status unknown';
}

function cborLabel(kind: HealthCheckResult['headCborStatus']): string {
    if (kind === 'present') {
        return '✅ HEAD receipt has a CBOR sidecar';
    }
    if (kind === 'missing') {
        return '❌ HEAD receipt is missing a CBOR sidecar';
    }
    return '⚪ CBOR sidecar status unknown';
}

function hubLabel(health: HealthCheckResult): string {
    if (!health.hubConfigured) {
        return '⚪ Hub not configured';
    }
    if (health.hubConnected) {
        return `✅ Connected${health.hubTenantId ? ` · tenant ${health.hubTenantId}` : ''}`;
    }
    return `❌ ${health.hubError || 'Hub unreachable'}`;
}

function getHealthCheckHtml(health: HealthCheckResult, targetUri?: string): string {
    const currentCommit = health.currentCommit ? health.currentCommit.slice(0, 12) : '—';
    const targetArgs = targetUri ? [targetUri] : [];
    const nextAction = !health.cliAvailable
        ? {
            label: 'Open Commit Status',
            detail: 'Install the AIIR CLI to unlock initialization, receipt generation, and managed automation.',
            command: renderCommandCall('aiir.readinessCheck', targetArgs),
        }
        : !health.aiirDirExists
            ? {
                label: 'Initialize Repository',
                detail: 'Scaffold .aiir so this repository can generate receipts and track policy state.',
                command: renderCommandCall('aiir.initializeRepo', targetArgs),
            }
            : health.headReceiptStatus !== 'present'
                ? {
                    label: 'Generate',
                    detail: 'HEAD is missing a receipt. The default Generate action prefers deterministic provenance when an active file is available.',
                    command: renderCommandCall('aiir.generatePreferred', targetArgs),
                }
                : health.postCommitHook !== 'managed'
                    ? {
                        label: 'Enable Auto-Receipting',
                        detail: 'Install the managed post-commit hook so new local commits are recorded automatically.',
                        command: renderCommandCall('aiir.enableAutoReceipting', targetArgs),
                    }
                    : {
                        label: 'Review Coverage',
                        detail: 'The repository is recording cleanly. Review proof coverage and verification status in the summary view.',
                        command: renderCommandCall('aiir.showSummary'),
                    };
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIIR Health Check</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 24px; max-width: 860px; line-height: 1.7; }
        h1 { font-size: 1.5em; margin-bottom: 8px; }
        h2 { font-size: 1.08em; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--vscode-panel-border); }
        ${getPanelNavStyles()}
        .hero { padding: 18px 20px; border-radius: 14px; border: 1px solid var(--vscode-panel-border); background: linear-gradient(180deg, color-mix(in srgb, var(--vscode-editor-background) 92%, var(--vscode-testing-iconPassed) 8%), var(--vscode-editor-background)); }
        .meta { opacity: 0.75; margin-top: 8px; }
        .hero-badges { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
        .card { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); border-radius: 10px; padding: 14px; }
        .card strong { display: block; margin-bottom: 6px; }
        .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
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
    ${getPanelNavHtml('health', { networkAllowed: isNetworkAllowed(), hubVisible: isHubEnabled(), commandTarget: targetUri, showAdvanced: getShowAdvancedCommands() })}
    <div class="hero">
        <h1>AIIR Health Check</h1>
        <div class="meta">Workspace: <strong>${health.workspaceName}</strong> · HEAD: <code>${currentCommit}</code></div>
        <div class="meta">Local provenance is the default VS Code path. Use Sigstore signing in CI or release workflows when OIDC and the optional sigstore package are available.</div>
        <div class="hero-badges">
            <span class="badge ${health.cliAvailable ? 'ok' : 'warn'}">${health.cliAvailable ? 'CLI available' : 'CLI missing'}</span>
            <span class="badge ${health.gitAvailable ? 'ok' : 'warn'}">${health.gitAvailable ? 'git repository' : 'git missing'}</span>
            <span class="badge ${health.headReceiptStatus === 'present' ? 'ok' : health.headReceiptStatus === 'missing' ? 'warn' : 'off'}">${receiptLabel(health.headReceiptStatus).replace(/^[^ ]+ /, '')}</span>
        </div>
    </div>

    <h2>Recommended Next Step</h2>
    <div class="card">
        <strong>${nextAction.label}</strong>
        <div>${nextAction.detail}</div>
        <div class="actions">
            <button onclick="${nextAction.command}">${nextAction.label}</button>
            <button class="secondary" onclick="${renderCommandCall('aiir.advancedSettings', targetArgs)}">Review Settings</button>
        </div>
    </div>

    <h2>Platform</h2>
    <div class="grid">
        <div class="card"><strong>CLI</strong>${healthValue(health.cliAvailable, health.cliVersion || 'AIIR CLI unavailable')}</div>
        <div class="card"><strong>Git</strong>${healthValue(health.gitAvailable, health.gitDir || 'Not a git repository')}</div>
    </div>

    <h2>Repository State</h2>
    <div class="grid">
        <div class="card"><strong>AIIR Directory</strong>${healthValue(health.aiirDirExists, '.aiir scaffold present')}</div>
        <div class="card"><strong>Ledger</strong>${healthValue(health.ledgerExists, '.aiir/receipts.jsonl present')}</div>
        <div class="card"><strong>Index</strong>${healthValue(health.indexExists, '.aiir/index.json present')}</div>
        <div class="card"><strong>Policy</strong>${healthValue(health.policyExists, '.aiir/policy.json present')}</div>
        <div class="card"><strong>CBOR Coverage</strong>${health.cborReceipts} present · ${health.missingCborReceipts} missing</div>
        <div class="card"><strong>Sigstore Coverage</strong>${health.sigstoreReceipts} receipt bundles detected</div>
    </div>

    <h2>Evidence Tier Distribution</h2>
    <div class="grid">
        <div class="card"><strong>Signed</strong>${health.tierSigned} receipt${health.tierSigned === 1 ? '' : 's'} — audit-grade</div>
        <div class="card"><strong>Provable</strong>${health.tierProvable} receipt${health.tierProvable === 1 ? '' : 's'} — editor provenance</div>
        <div class="card"><strong>Heuristic</strong>${health.tierHeuristic} receipt${health.tierHeuristic === 1 ? '' : 's'} — signal-based</div>
        <div class="card"><strong>Unsigned</strong>${health.tierUnsigned} receipt${health.tierUnsigned === 1 ? '' : 's'} — baseline</div>
    </div>
    ${health.sigstoreReceipts === 0 ? '<div class="card" style="border-left:3px solid var(--vscode-editorWarning-foreground);margin:12px 0"><strong>No signed receipts detected.</strong> Unsigned receipts are tamper-evident but cannot serve as formal control evidence. Enable Sigstore signing in CI for audit-grade non-repudiation.</div>' : ''}
    ${health.trailerInjection !== undefined ? `<div class="card"><strong>Trailer Injection</strong> ${health.trailerInjection ? '✅ Enabled — AIIR trailers appended to commit messages' : '⚪ Disabled'}</div>` : ''}

    <h2>Automation</h2>
    <div class="grid">
        <div class="card"><strong>Post-Commit Hook</strong>${hookLabel(health.postCommitHook)}</div>
        <div class="card"><strong>HEAD Receipt</strong>${receiptLabel(health.headReceiptStatus)}</div>
        <div class="card"><strong>HEAD CBOR</strong>${cborLabel(health.headCborStatus)}</div>
    </div>

    <h2>AI Tool Detection</h2>
    ${getDetectedToolsHtml(detectEditorAITools())}

    <h2>Compliance Posture</h2>
    <div class="grid">
        <div class="card"><strong>Regulated Mode</strong>${health.regulatedMode ? '<span class="badge ok">active</span>' : '⚪ Off'}</div>
        <div class="card"><strong>Lock Preset</strong>${health.lockPreset ? `<span class="badge ok">${escapeHtml(health.lockPreset)}</span>` : '⚪ None'}</div>
        <div class="card"><strong>Trailer Injection</strong>${health.trailerInjection ? '<span class="badge ok">enabled</span>' : '⚪ Disabled'}</div>
    </div>

    <h2>Hub</h2>
    <div class="grid">
        <div class="card"><strong>Connection</strong>${hubLabel(health)}</div>
        <div class="card"><strong>Auth</strong>${health.hubConfigured ? healthValue(health.hubAuthenticated, health.hubAuthenticated ? 'API token stored' : 'No API token stored') : '⚪ Not configured'}</div>
    </div>
    ${getPanelScript()}
</body>
</html>`;
}

function getControlPanelHtml(
    stats: ReceiptStats,
    health: HealthCheckResult,
    hubEnabled: boolean,
    targetUri?: string,
): string {
    const showAdvanced = getShowAdvancedCommands();
    const aiPercent = stats.total > 0 ? Math.round(stats.aiAuthored / stats.total * 100) : 0;
    const humanPercent = 100 - aiPercent;
    const validPercent = stats.total > 0 ? Math.round(stats.valid / stats.total * 100) : 0;
    const targetArgs = targetUri ? [targetUri] : [];
    const generateAction = !health.cliAvailable
        ? { label: 'Open Commit Status', command: renderCommandCall('aiir.readinessCheck', targetArgs), secondary: false }
        : !health.aiirDirExists
            ? { label: 'Initialize Repo', command: renderCommandCall('aiir.initializeRepo', targetArgs), secondary: false }
            : { label: 'Generate', command: renderCommandCall('aiir.generatePreferred', targetArgs), secondary: false };
    const verifyAllDisabled = stats.total === 0;
    const repoAction = !health.aiirDirExists
        ? { label: 'Initialize Repo', command: renderCommandCall('aiir.initializeRepo', targetArgs), secondary: true }
        : !health.policyExists
            ? { label: 'Create Policy File', command: renderCommandCall('aiir.createWorkspacePolicy', targetArgs), secondary: true }
            : { label: 'Open Policy File', command: renderCommandCall('aiir.openPolicyFile', targetArgs), secondary: true };
    const autoReceiptAction = !health.cliAvailable
        ? { label: 'Open Commit Status', command: renderCommandCall('aiir.readinessCheck', targetArgs), secondary: true }
        : health.postCommitHook === 'managed'
            ? { label: 'Disable Auto-Receipting', command: renderCommandCall('aiir.disableAutoReceipting', targetArgs), secondary: true }
            : { label: 'Enable Auto-Receipting', command: renderCommandCall('aiir.enableAutoReceipting', targetArgs), secondary: true };
    const fixActionDisabled = stats.invalid === 0;

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIIR Control Panel</title>
    <style>
        /* ── Base (echoes invariantsystems.io design system) ── */
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: var(--vscode-font-family);
            color: var(--vscode-foreground);
            padding: 24px;
            max-width: 820px;
            line-height: 1.7;
        }
        ${getPanelNavStyles()}
        h1 { font-size: 1.5em; margin-bottom: 6px; display: flex; align-items: center; gap: 10px; }
        h1 .subtitle { font-size: 0.55em; opacity: 0.5; font-weight: normal; }
        .eyebrow { font-size: 0.78em; text-transform: uppercase; letter-spacing: 0.08em; opacity: 0.6; }
        .hero {
            padding: 18px 20px;
            border-radius: 14px;
            border: 1px solid var(--vscode-panel-border);
            background:
                radial-gradient(circle at top right, color-mix(in srgb, var(--vscode-charts-blue) 18%, transparent), transparent 35%),
                linear-gradient(180deg, color-mix(in srgb, var(--vscode-editor-background) 92%, var(--vscode-charts-blue) 8%), var(--vscode-editor-background));
        }
        .hero p { opacity: 0.76; max-width: 62ch; }
        .hero-badges { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
        h2 {
            font-size: 1.1em;
            margin-bottom: 12px;
            padding-bottom: 6px;
            border-bottom: 1px solid var(--vscode-panel-border);
        }
        section { margin-top: 28px; }
        code { font-family: var(--vscode-editor-font-family); font-size: 0.92em; }
        .page-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 12px;
        }
        .page-card {
            border: 1px solid var(--vscode-panel-border);
            border-radius: 12px;
            padding: 16px;
            background: var(--vscode-editor-background);
        }
        .page-card h3 { font-size: 1em; margin-bottom: 6px; }
        .page-card p { font-size: 0.88em; opacity: 0.72; min-height: 3.6em; }
        .page-card .actions { margin-top: 12px; }

        /* ── Stats (matches .demo-stat from invariantsystems.io/demo) ── */
        .stats {
            display: flex;
            flex-wrap: wrap;
            gap: 1.5rem;
            margin-top: 0.5rem;
        }
        .stat .val {
            font-size: 1.8em;
            font-weight: 800;
            letter-spacing: -0.03em;
            color: var(--vscode-charts-blue);
            line-height: 1.1;
        }
        .stat .lbl {
            font-size: 0.8em;
            opacity: 0.6;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-top: 2px;
        }
        .stat.ok .val { color: var(--vscode-testing-iconPassed); }
        .stat.err .val { color: var(--vscode-testing-iconFailed); }

        /* ── AI/Human bar ── */
        .ai-bar-container { margin-top: 20px; }
        .ai-bar {
            height: 10px; border-radius: 5px; display: flex; overflow: hidden;
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
        }
        .ai-bar .ai { background: var(--vscode-charts-blue); transition: width 0.3s; }
        .ai-bar .human { background: var(--vscode-testing-iconPassed); transition: width 0.3s; }
        .ai-bar-legend { display: flex; gap: 20px; margin-top: 8px; font-size: 0.85em; opacity: 0.7; }
        .ai-bar-legend span::before {
            content: ''; display: inline-block; width: 10px; height: 10px;
            border-radius: 3px; margin-right: 6px; vertical-align: middle;
        }
        .ai-bar-legend .ai-legend::before { background: var(--vscode-charts-blue); }
        .ai-bar-legend .human-legend::before { background: var(--vscode-testing-iconPassed); }

        /* ── Pipeline (matches .demo-pipeline from invariantsystems.io/demo) ── */
        .pipeline {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1px;
            margin-top: 0.5rem;
            background: var(--vscode-panel-border);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 10px;
            overflow: hidden;
        }
        .pipeline-step {
            display: flex;
            flex-direction: column;
            gap: 0.3em;
            padding: 1em 1.25em;
            background: var(--vscode-editor-background);
        }
        .pipeline-step strong { font-size: 0.9em; }
        .pipeline-step span { font-size: 0.8em; opacity: 0.6; line-height: 1.4; }
        .pipeline-num {
            width: 24px; height: 24px; border-radius: 50%;
            background: var(--vscode-testing-iconPassed); color: #fff;
            font-weight: 700; font-size: 0.75em;
            display: flex; align-items: center; justify-content: center;
            margin-bottom: 0.2em;
        }
        .pipeline-num.warn { background: var(--vscode-editorWarning-foreground); }
        .pipeline-num.err { background: var(--vscode-testing-iconFailed); }
        .pipeline-num.off { background: var(--vscode-descriptionForeground); opacity: 0.5; }

        /* ── Health grid ── */
        .health-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 10px;
        }
        .health-item {
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 8px;
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .health-label { font-size: 0.8em; opacity: 0.5; }

        /* ── Badges (matches .demo-badge from invariantsystems.io) ── */
        .badge {
            display: inline-block;
            font-size: 0.72em;
            font-weight: 600;
            border: 1.5px solid;
            border-radius: 99px;
            padding: 0.15em 0.65em;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            white-space: nowrap;
        }
        .badge.ok { border-color: var(--vscode-testing-iconPassed); color: var(--vscode-testing-iconPassed); }
        .badge.err { border-color: var(--vscode-testing-iconFailed); color: var(--vscode-testing-iconFailed); }
        .badge.warn { border-color: var(--vscode-editorWarning-foreground); color: var(--vscode-editorWarning-foreground); }
        .badge.off { opacity: 0.5; border-color: var(--vscode-descriptionForeground); color: var(--vscode-descriptionForeground); }

        /* ── Actions ── */
        .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
        button {
            font: inherit; cursor: pointer; border: none; border-radius: 6px; padding: 8px 16px;
            background: var(--vscode-button-background); color: var(--vscode-button-foreground);
            font-size: 0.88em;
        }
        button:hover { background: var(--vscode-button-hoverBackground); }
        button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
        button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
        button:disabled { opacity: 0.45; cursor: not-allowed; }

        /* ── Callout (matches .callout-panel from invariantsystems.io) ── */
        .callout-panel {
            padding: 1em 1.25em;
            border-radius: 8px;
            border: 1px solid var(--vscode-panel-border);
            background: var(--vscode-editor-background);
            margin-top: 20px;
            font-size: 0.88em;
            line-height: 1.6;
        }
        .callout-panel strong { display: block; margin-bottom: 0.4em; }
        .callout-panel p { margin: 0.25em 0; opacity: 0.8; }
        .pass-rate { margin-top: 12px; font-size: 0.85em; opacity: 0.6; }
    </style>
</head>
<body>
    ${getPanelNavHtml('control', { networkAllowed: isNetworkAllowed(), hubVisible: isHubEnabled(), commandTarget: targetUri, showAdvanced: getShowAdvancedCommands() })}
    <div class="hero">
        <div class="eyebrow">Advanced Operator Surface</div>
        <h1>AIIR Control Panel <span class="subtitle">${escapeHtml(health.workspaceName)}</span></h1>
        <p>Use the control panel to recover or advance the current repository without leaving the core loop. Operator-only pages stay behind advanced mode.</p>
        <div class="hero-badges">
            <span class="badge ${stats.invalid === 0 ? 'ok' : 'err'}">${stats.invalid === 0 ? 'all receipts valid' : `${stats.invalid} failed`}</span>
            <span class="badge ${health.postCommitHook === 'managed' ? 'ok' : health.postCommitHook === 'custom' ? 'warn' : 'off'}">${hookLabel(health.postCommitHook).replace(/^[^ ]+ /, '')}</span>
            <span class="badge ${hubEnabled ? 'ok' : 'off'}">${hubEnabled ? 'Hub features available' : 'local-only mode'}</span>
            <span class="badge ${health.mcpConfigured ? 'ok' : 'off'}">${health.mcpConfigured ? 'Copilot Chat connected' : 'MCP not configured'}</span>
        </div>
    </div>

    <section>
        <h2>Core Workflow</h2>
        <div class="callout-panel">
            <strong>Default path for this repository</strong>
            <p>Use setup when prerequisites are missing, generate for the current work, verify the repository receipts, and jump directly into the latest failure when something needs repair.</p>
            <div class="actions">
                <button ${generateAction.secondary ? 'class="secondary"' : ''} onclick="${generateAction.command}">${generateAction.label}</button>
                <button ${verifyAllDisabled ? 'disabled' : ''} onclick="cmd('aiir.verifyAll')">Verify</button>
                <button class="secondary" ${fixActionDisabled ? 'disabled' : ''} onclick="${renderCommandCall('aiir.fixLatestFailedReceipt', targetArgs)}">Fix</button>
                <button class="secondary" onclick="${renderCommandCall('aiir.readinessCheck', targetArgs)}">Setup</button>
            </div>
        </div>
    </section>

    ${showAdvanced ? `<section>
        <h2>Pages</h2>
        <div class="page-grid">
            <div class="page-card">
                <h3>Receipt Summary</h3>
                <p>Open the focused summary view for counts, verification coverage, and multi-repo breakdowns.</p>
                <div class="actions"><button onclick="cmd('aiir.showSummary')">Review Coverage</button></div>
            </div>
            <div class="page-card">
                <h3>Health Check</h3>
                <p>Inspect local CLI, git state, ledger coverage, hooks, and current repository integrity posture.</p>
                <div class="actions"><button onclick="${renderCommandCall('aiir.healthCheck', targetUri ? [targetUri] : [])}">Open Health Check</button></div>
            </div>
            <div class="page-card">
                <h3>Hub Plans and Access</h3>
                <p>See the public Hub pricing boundary, request access, and jump to the public pricing page.</p>
                <div class="actions"><button onclick="cmd('aiir.hubBilling')">Review Plans</button></div>
            </div>
            <div class="page-card">
                <h3>Advanced Settings</h3>
                <p>Review local-only mode, workspace isolation, CLI paths, and workspace-scoped Hub configuration.</p>
                <div class="actions"><button onclick="${renderCommandCall('aiir.advancedSettings', targetUri ? [targetUri] : [])}">Review Settings</button></div>
            </div>
            <div class="page-card">
                <h3>Security Posture</h3>
                <p>See the current trust boundary for this workspace, including network posture, allowlists, and accessible repositories.</p>
                <div class="actions"><button onclick="cmd('aiir.securityPosture')">Review Security</button></div>
            </div>
            <div class="page-card">
                <h3>Deployment Presets</h3>
                <p>Apply workspace-scoped deployment presets for local-only, locked-down multi-root, or Hub evaluation modes.</p>
                <div class="actions"><button onclick="${renderCommandCall('aiir.rolloutPresets', targetUri ? [targetUri] : [])}">Review Presets</button></div>
            </div>
            <div class="page-card">
                <h3>Copilot Chat</h3>
                <p>Configure the AIIR MCP server so Copilot Chat can generate, verify, and explain receipts via natural language.</p>
                <div class="actions"><button ${health.mcpConfigured ? 'class="secondary"' : ''} onclick="${renderCommandCall('aiir.configureMcpServer', targetArgs)}">${health.mcpConfigured ? 'Reconfigure' : 'Connect to Copilot Chat'}</button></div>
            </div>
        </div>
    </section>` : ''}

    <section>
        <h2>Receipts</h2>
        <div class="stats">
            <div class="stat"><div class="val">${stats.total}</div><div class="lbl">Total receipts</div></div>
            <div class="stat ok"><div class="val">${stats.valid}</div><div class="lbl">Verified</div></div>
            <div class="stat err"><div class="val">${stats.invalid}</div><div class="lbl">Failed</div></div>
            <div class="stat"><div class="val">${stats.aiAuthored}</div><div class="lbl">AI-authored</div></div>
            <div class="stat"><div class="val">${stats.cborPresent}</div><div class="lbl">CBOR sidecars</div></div>
            <div class="stat"><div class="val">${stats.sigstorePresent}</div><div class="lbl">Sigstore</div></div>
        </div>

        <div class="ai-bar-container">
            <div class="ai-bar">
                <div class="ai" style="width:${aiPercent}%"></div>
                <div class="human" style="width:${humanPercent}%"></div>
            </div>
            <div class="ai-bar-legend">
                <span class="ai-legend">${aiPercent}% AI-authored</span>
                <span class="human-legend">${humanPercent}% Human-authored</span>
            </div>
        </div>
        <div class="pass-rate">${validPercent}% integrity pass rate</div>
    </section>

    <section>
        <h2>Pipeline</h2>
        <div class="pipeline">
            <div class="pipeline-step">
                <div class="pipeline-num ${health.gitAvailable ? '' : 'err'}">1</div>
                <strong>Commit lands</strong>
                <span>${health.gitAvailable ? 'Git available' : 'Git not found'}</span>
            </div>
            <div class="pipeline-step">
                <div class="pipeline-num ${health.postCommitHook === 'managed' ? '' : health.postCommitHook === 'custom' ? 'warn' : 'off'}">2</div>
                <strong>Proof recorded</strong>
                <span>${health.postCommitHook === 'managed' ? 'Auto-receipting active' : health.postCommitHook === 'custom' ? 'Custom hook' : 'Manual only'}</span>
            </div>
            <div class="pipeline-step">
                <div class="pipeline-num ${health.headReceiptStatus === 'present' ? '' : health.headReceiptStatus === 'missing' ? 'err' : 'off'}">3</div>
                <strong>Hash verified</strong>
                <span>${health.headReceiptStatus === 'present' ? 'HEAD recorded' : health.headReceiptStatus === 'missing' ? 'HEAD missing proof' : 'Unknown'}</span>
            </div>
            <div class="pipeline-step">
                <div class="pipeline-num ${health.headCborStatus === 'present' ? '' : 'off'}">4</div>
                <strong>CBOR sealed</strong>
                <span>${health.headCborStatus === 'present' ? 'Binary sidecar present' : 'No CBOR sidecar'}</span>
            </div>
        </div>
    </section>

    <section>
        <h2>Workspace Health</h2>
        <div class="health-grid">
            <div class="health-item"><span class="health-label">CLI</span>${health.cliAvailable ? `<span class="badge ok">${escapeHtml(health.cliVersion || 'available')}</span>` : '<span class="badge err">not found</span>'}</div>
            <div class="health-item"><span class="health-label">Git</span>${health.gitAvailable ? '<span class="badge ok">available</span>' : '<span class="badge err">not found</span>'}</div>
            <div class="health-item"><span class="health-label">.aiir directory</span>${health.aiirDirExists ? '<span class="badge ok">present</span>' : '<span class="badge off">missing</span>'}</div>
            <div class="health-item"><span class="health-label">Policy</span>${health.policyExists ? '<span class="badge ok">configured</span>' : '<span class="badge off">none</span>'}</div>
            <div class="health-item"><span class="health-label">Hub posture</span>${hubEnabled
            ? health.hubConnected
                ? '<span class="badge ok">reachable</span>'
                : health.hubConfigured
                    ? '<span class="badge err">configured but unreachable</span>'
                    : '<span class="badge warn">enabled, not configured</span>'
            : '<span class="badge off">local-only</span>'}</div>
            <div class="health-item"><span class="health-label">MCP Server</span>${health.mcpConfigured ? '<span class="badge ok">configured</span>' : '<span class="badge off">not configured</span>'}</div>
        </div>
    </section>

    <section>
        <h2>Quick Actions</h2>
        <div class="actions">
            <button ${generateAction.secondary ? 'class="secondary"' : ''} onclick="${generateAction.command}">${generateAction.label}</button>
            <button ${verifyAllDisabled ? 'disabled' : ''} onclick="cmd('aiir.verifyAll')">Verify</button>
            <button class="secondary" ${fixActionDisabled ? 'disabled' : ''} onclick="${renderCommandCall('aiir.fixLatestFailedReceipt', targetArgs)}">Fix Latest Failure</button>
            <button class="secondary" onclick="${renderCommandCall('aiir.readinessCheck', targetArgs)}">Setup</button>
            ${showAdvanced ? `<button onclick="${renderCommandCall('aiir.healthCheck', targetArgs)}">Health Check</button>
            <button onclick="cmd('aiir.refresh')">Refresh</button>
            <button class="secondary" onclick="${repoAction.command}">${repoAction.label}</button>
            <button class="secondary" onclick="${autoReceiptAction.command}">${autoReceiptAction.label}</button>
            <button class="secondary" onclick="cmd('aiir.hubBilling')">Review Plans</button>
            <button class="secondary" onclick="cmd('aiir.securityPosture')">Review Security</button>
            <button class="secondary" onclick="${renderCommandCall('aiir.rolloutPresets', targetArgs)}">Review Presets</button>
            <button class="secondary" onclick="${renderCommandCall('aiir.advancedSettings', targetArgs)}">Advanced Settings</button>
            <button ${health.mcpConfigured ? 'class="secondary"' : ''} onclick="${renderCommandCall('aiir.configureMcpServer', targetArgs)}">${health.mcpConfigured ? 'MCP Connected' : 'Connect to Copilot Chat'}</button>` : ''}
        </div>
    </section>

    <div class="callout-panel">
        <strong>AI tool detection</strong>
        <p>This extension automatically detects AI coding tools installed in your editor
        (Copilot, Cursor, Cline, Codeium, etc.) and reports them via <code>--agent-tool</code>
        when generating receipts. This closes the gap where the CLI heuristic alone can
        miss editor-based AI that adds no <code>Co-authored-by</code> trailers.</p>
        ${(() => {
            const tools = detectEditorAITools(); return tools.length > 0
                ? '<p><strong>Detected:</strong> ' + tools.map(t => escapeHtml(t.toolName) + (t.isActive ? ' ✅' : '')).join(', ') + '</p>'
                : '<p>No AI coding extensions detected in this editor.</p>';
        })()}
    </div>

    ${getPanelScript()}
</body>
</html>`;
}

export function deactivate() { }
