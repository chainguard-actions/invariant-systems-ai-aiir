/**
 * AIIR Language Model Tools — native tool contributions for Copilot Chat.
 *
 * Registers tools via the vscode.lm API so that Copilot Chat can invoke
 * AIIR operations directly without an MCP server.  These tools complement
 * the chat participant (@aiir) by letting the model call AIIR functions
 * as part of agentic workflows.
 *
 * Tools:
 *   aiir_receipt      — Generate a receipt for a commit
 *   aiir_verify       — Verify a receipt file
 *   aiir_stats        — Show receipt statistics
 *   aiir_explain      — Explain what a receipt proves
 *   aiir_policy_check — Check policy compliance
 *
 * @license Apache-2.0
 */

import * as vscode from 'vscode';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);
const COMMAND_TIMEOUT_MS = 30_000;

export interface LanguageModelToolDeps {
    getCliPath(): string;
    resolveWorkspaceFolder(): vscode.WorkspaceFolder | undefined;
    isCliAvailable(folder: vscode.WorkspaceFolder): Promise<boolean>;
    getLatestReceiptFile(folder: vscode.WorkspaceFolder): Promise<string | undefined>;
}

async function runCli(
    deps: LanguageModelToolDeps,
    args: string[],
    cwd: string,
): Promise<{ stdout: string; stderr: string }> {
    return await execFileAsync(deps.getCliPath(), args, {
        cwd,
        timeout: COMMAND_TIMEOUT_MS,
        maxBuffer: 1024 * 1024,
    });
}

function formatCliOutput(stdout: string, stderr: string): string {
    return stderr.trim() || stdout.trim() || 'AIIR command completed with no output.';
}

async function resolveReceiptFile(
    deps: LanguageModelToolDeps,
    folder: vscode.WorkspaceFolder,
    file?: string,
): Promise<string | undefined> {
    const trimmed = file?.trim();
    if (trimmed) {
        return trimmed;
    }

    return await deps.getLatestReceiptFile(folder);
}

function requireFolder(deps: LanguageModelToolDeps): vscode.WorkspaceFolder {
    const folder = deps.resolveWorkspaceFolder();
    if (!folder) {
        throw new Error('No workspace folder is open. Open a git repository first.');
    }
    return folder;
}

async function requireCli(deps: LanguageModelToolDeps, folder: vscode.WorkspaceFolder): Promise<void> {
    if (!await deps.isCliAvailable(folder)) {
        throw new Error('The AIIR CLI is not installed. Run `pip install aiir` to get started.');
    }
}

// ── Receipt Tool ──────────────────────────────────────────────────────

interface ReceiptInput {
    commit?: string;
    range?: string;
    pretty?: boolean;
}

class ReceiptTool implements vscode.LanguageModelTool<ReceiptInput> {
    constructor(private readonly deps: LanguageModelToolDeps) {}

    async invoke(
        options: vscode.LanguageModelToolInvocationOptions<ReceiptInput>,
        _token: vscode.CancellationToken,
    ): Promise<vscode.LanguageModelToolResult> {
        const folder = requireFolder(this.deps);
        await requireCli(this.deps, folder);
        const args: string[] = [];
        if (options.input.pretty !== false) {
            args.push('--pretty');
        }
        if (options.input.commit) {
            args.push('--commit', options.input.commit);
        }
        if (options.input.range) {
            args.push('--range', options.input.range);
        }
        const { stdout, stderr } = await runCli(this.deps, args, folder.uri.fsPath);
        return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(formatCliOutput(stdout, stderr))]);
    }
}

// ── Verify Tool ───────────────────────────────────────────────────────

interface VerifyInput {
    file?: string;
}

class VerifyTool implements vscode.LanguageModelTool<VerifyInput> {
    constructor(private readonly deps: LanguageModelToolDeps) {}

    async invoke(
        options: vscode.LanguageModelToolInvocationOptions<VerifyInput>,
        _token: vscode.CancellationToken,
    ): Promise<vscode.LanguageModelToolResult> {
        const folder = requireFolder(this.deps);
        await requireCli(this.deps, folder);
        const receiptFile = await resolveReceiptFile(this.deps, folder, options.input.file);
        if (!receiptFile) {
            throw new Error('No receipt file was provided and AIIR could not find a latest active receipt to verify.');
        }
        const { stdout, stderr } = await runCli(this.deps, ['--verify', receiptFile], folder.uri.fsPath);
        return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(formatCliOutput(stdout, stderr))]);
    }
}

// ── Stats Tool ────────────────────────────────────────────────────────

class StatsTool implements vscode.LanguageModelTool<Record<string, never>> {
    constructor(private readonly deps: LanguageModelToolDeps) {}

    async invoke(
        _options: vscode.LanguageModelToolInvocationOptions<Record<string, never>>,
        _token: vscode.CancellationToken,
    ): Promise<vscode.LanguageModelToolResult> {
        const folder = requireFolder(this.deps);
        await requireCli(this.deps, folder);
        const { stdout, stderr } = await runCli(this.deps, ['--stats', '--pretty'], folder.uri.fsPath);
        return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(formatCliOutput(stdout, stderr))]);
    }
}

// ── Explain Tool ──────────────────────────────────────────────────────

interface ExplainInput {
    file?: string;
}

class ExplainTool implements vscode.LanguageModelTool<ExplainInput> {
    constructor(private readonly deps: LanguageModelToolDeps) {}

    async invoke(
        options: vscode.LanguageModelToolInvocationOptions<ExplainInput>,
        _token: vscode.CancellationToken,
    ): Promise<vscode.LanguageModelToolResult> {
        const folder = requireFolder(this.deps);
        await requireCli(this.deps, folder);
        const receiptFile = await resolveReceiptFile(this.deps, folder, options.input.file);
        if (!receiptFile) {
            throw new Error('No receipt file was provided and AIIR could not find a latest active receipt to explain.');
        }
        const { stdout, stderr } = await runCli(this.deps, ['--verify', receiptFile, '--explain'], folder.uri.fsPath);
        return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(formatCliOutput(stdout, stderr))]);
    }
}

// ── Policy Check Tool ─────────────────────────────────────────────────

class PolicyCheckTool implements vscode.LanguageModelTool<Record<string, never>> {
    constructor(private readonly deps: LanguageModelToolDeps) {}

    async invoke(
        _options: vscode.LanguageModelToolInvocationOptions<Record<string, never>>,
        _token: vscode.CancellationToken,
    ): Promise<vscode.LanguageModelToolResult> {
        const folder = requireFolder(this.deps);
        await requireCli(this.deps, folder);
        const { stdout, stderr } = await runCli(this.deps, ['--check', '--policy', '.aiir/policy.json'], folder.uri.fsPath);
        return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(formatCliOutput(stdout, stderr))]);
    }
}

// ── Registration ──────────────────────────────────────────────────────

export function registerLanguageModelTools(
    context: vscode.ExtensionContext,
    deps: LanguageModelToolDeps,
): void {
    const lm = vscode.lm;
    if (typeof lm?.registerTool !== 'function') {
        return;
    }

    context.subscriptions.push(
        lm.registerTool('aiir_receipt', new ReceiptTool(deps)),
        lm.registerTool('aiir_verify', new VerifyTool(deps)),
        lm.registerTool('aiir_stats', new StatsTool(deps)),
        lm.registerTool('aiir_explain', new ExplainTool(deps)),
        lm.registerTool('aiir_policy_check', new PolicyCheckTool(deps)),
    );
}
