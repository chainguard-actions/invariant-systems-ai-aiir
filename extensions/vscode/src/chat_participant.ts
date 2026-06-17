/**
 * AIIR Chat Participant — @aiir in Copilot Chat.
 *
 * Registers a native chat participant so users can interact with AIIR
 * through Copilot Chat without configuring an MCP server first.
 *
 * Slash commands:
 *   /receipt  — Generate a receipt for the current or specified commit
 *   /verify   — Verify an AIIR receipt file
 *   /stats    — Show receipt statistics for the repository
 *   /explain  — Explain what an AIIR receipt proves
 *   /policy   — Check repository policy compliance
 *
 * @license Apache-2.0
 */

import * as vscode from 'vscode';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);
const COMMAND_TIMEOUT_MS = 30_000;

export interface ChatParticipantDeps {
    getCliPath(): string;
    resolveWorkspaceFolder(): vscode.WorkspaceFolder | undefined;
    isCliAvailable(folder: vscode.WorkspaceFolder): Promise<boolean>;
    getLatestReceiptFile(folder: vscode.WorkspaceFolder): Promise<string | undefined>;
}

async function runCli(
    deps: ChatParticipantDeps,
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
    deps: ChatParticipantDeps,
    folder: vscode.WorkspaceFolder,
    prompt: string,
): Promise<string | undefined> {
    const trimmed = prompt.trim();
    if (trimmed) {
        return trimmed;
    }

    return await deps.getLatestReceiptFile(folder);
}

function resolveFolder(
    deps: ChatParticipantDeps,
): vscode.WorkspaceFolder | undefined {
    return deps.resolveWorkspaceFolder();
}

async function handleReceipt(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    deps: ChatParticipantDeps,
): Promise<void> {
    const folder = resolveFolder(deps);
    if (!folder) {
        stream.markdown('No workspace folder is open. Open a git repository first.');
        return;
    }
    if (!await deps.isCliAvailable(folder)) {
        stream.markdown('The AIIR CLI is not installed. Run `pip install aiir` to get started.');
        return;
    }

    const args = ['--pretty'];
    const prompt = request.prompt.trim();
    if (prompt) {
        // If the user provided a commit SHA or range, pass it through.
        if (/^[0-9a-f]{6,40}$/i.test(prompt)) {
            args.push('--commit', prompt);
        } else if (prompt.includes('..')) {
            args.push('--range', prompt);
        }
    }

    try {
        const { stdout, stderr } = await runCli(deps, args, folder.uri.fsPath);
        stream.markdown('```\n' + formatCliOutput(stdout, stderr) + '\n```');
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        stream.markdown(`Receipt generation failed:\n\n\`\`\`\n${message}\n\`\`\``);
    }
}

async function handleVerify(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    deps: ChatParticipantDeps,
): Promise<void> {
    const folder = resolveFolder(deps);
    if (!folder) {
        stream.markdown('No workspace folder is open. Open a git repository first.');
        return;
    }
    if (!await deps.isCliAvailable(folder)) {
        stream.markdown('The AIIR CLI is not installed. Run `pip install aiir` to get started.');
        return;
    }

    const receiptFile = await resolveReceiptFile(deps, folder, request.prompt);
    if (!receiptFile) {
        stream.markdown('No receipt file was provided and AIIR could not find a latest active receipt to verify.');
        return;
    }

    try {
        const { stdout, stderr } = await runCli(deps, ['--verify', receiptFile], folder.uri.fsPath);
        stream.markdown('```\n' + formatCliOutput(stdout, stderr) + '\n```');
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        stream.markdown(`Verification failed:\n\n\`\`\`\n${message}\n\`\`\``);
    }
}

async function handleStats(
    _request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    deps: ChatParticipantDeps,
): Promise<void> {
    const folder = resolveFolder(deps);
    if (!folder) {
        stream.markdown('No workspace folder is open. Open a git repository first.');
        return;
    }
    if (!await deps.isCliAvailable(folder)) {
        stream.markdown('The AIIR CLI is not installed. Run `pip install aiir` to get started.');
        return;
    }

    try {
        const { stdout, stderr } = await runCli(deps, ['--stats', '--pretty'], folder.uri.fsPath);
        stream.markdown('```\n' + formatCliOutput(stdout, stderr) + '\n```');
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        stream.markdown(`Stats retrieval failed:\n\n\`\`\`\n${message}\n\`\`\``);
    }
}

async function handleExplain(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    deps: ChatParticipantDeps,
): Promise<void> {
    const folder = resolveFolder(deps);
    if (!folder) {
        stream.markdown('No workspace folder is open. Open a git repository first.');
        return;
    }
    if (!await deps.isCliAvailable(folder)) {
        stream.markdown('The AIIR CLI is not installed. Run `pip install aiir` to get started.');
        return;
    }

    const receiptFile = await resolveReceiptFile(deps, folder, request.prompt);
    if (!receiptFile) {
        stream.markdown('No receipt file was provided and AIIR could not find a latest active receipt to explain.');
        return;
    }

    try {
        const { stdout, stderr } = await runCli(deps, ['--verify', receiptFile, '--explain'], folder.uri.fsPath);
        stream.markdown(formatCliOutput(stdout, stderr));
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        stream.markdown(`Explain failed:\n\n\`\`\`\n${message}\n\`\`\``);
    }
}

async function handlePolicy(
    _request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    deps: ChatParticipantDeps,
): Promise<void> {
    const folder = resolveFolder(deps);
    if (!folder) {
        stream.markdown('No workspace folder is open. Open a git repository first.');
        return;
    }
    if (!await deps.isCliAvailable(folder)) {
        stream.markdown('The AIIR CLI is not installed. Run `pip install aiir` to get started.');
        return;
    }

    try {
        const { stdout, stderr } = await runCli(deps, ['--check', '--policy', '.aiir/policy.json'], folder.uri.fsPath);
        stream.markdown('```\n' + formatCliOutput(stdout, stderr) + '\n```');
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        stream.markdown(`Policy check failed:\n\n\`\`\`\n${message}\n\`\`\``);
    }
}

async function handleDefault(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    deps: ChatParticipantDeps,
): Promise<void> {
    const prompt = request.prompt.trim().toLowerCase();

    if (prompt.includes('receipt') || prompt.includes('generate') || prompt.includes('record')) {
        await handleReceipt(request, stream, deps);
    } else if (prompt.includes('verify') || prompt.includes('check')) {
        await handleVerify(request, stream, deps);
    } else if (prompt.includes('stat')) {
        await handleStats(request, stream, deps);
    } else if (prompt.includes('explain') || prompt.includes('what')) {
        await handleExplain(request, stream, deps);
    } else if (prompt.includes('policy') || prompt.includes('compliance')) {
        await handlePolicy(request, stream, deps);
    } else {
        stream.markdown(
            'I can help with AI integrity receipts. Try one of these commands:\n\n' +
            '- `/receipt` — Generate a receipt for the current commit\n' +
            '- `/verify` — Verify receipt integrity\n' +
            '- `/stats` — Show receipt statistics\n' +
            '- `/explain` — Explain what a receipt proves\n' +
            '- `/policy` — Check policy compliance\n\n' +
            'Or just describe what you need — for example, "generate a receipt for HEAD~3..HEAD".',
        );
    }
}

export function registerChatParticipant(
    context: vscode.ExtensionContext,
    deps: ChatParticipantDeps,
): void {
    const chat = vscode.chat;
    if (typeof chat?.createChatParticipant !== 'function') {
        return;
    }

    const participant = chat.createChatParticipant('aiir.chat', async (
        request: vscode.ChatRequest,
        _context: vscode.ChatContext,
        stream: vscode.ChatResponseStream,
        _token: vscode.CancellationToken,
    ) => {
        switch (request.command) {
            case 'receipt':
                await handleReceipt(request, stream, deps);
                break;
            case 'verify':
                await handleVerify(request, stream, deps);
                break;
            case 'stats':
                await handleStats(request, stream, deps);
                break;
            case 'explain':
                await handleExplain(request, stream, deps);
                break;
            case 'policy':
                await handlePolicy(request, stream, deps);
                break;
            default:
                await handleDefault(request, stream, deps);
                break;
        }
    });

    participant.iconPath = vscode.Uri.joinPath(context.extensionUri, 'icon.png');
    context.subscriptions.push(participant);
}
