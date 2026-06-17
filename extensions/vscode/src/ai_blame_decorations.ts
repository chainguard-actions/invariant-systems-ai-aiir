/**
 * AI Blame Decorations — gutter annotations showing which lines were
 * committed with AI assistance, based on AIIR receipt data.
 *
 * Cross-references `git blame` output with the extension's active receipt
 * projection to annotate lines from AI-assisted commits.
 *
 * @license Apache-2.0
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

// ── Decoration types ────────────────────────────────────────────────

const AI_ASSISTED_DECORATION = vscode.window.createTextEditorDecorationType({
    gutterIconPath: undefined, // Set dynamically per-theme
    gutterIconSize: '80%',
    overviewRulerColor: 'rgba(59, 130, 246, 0.6)',
    overviewRulerLane: vscode.OverviewRulerLane.Left,
    after: {
        margin: '0 0 0 1em',
        color: new vscode.ThemeColor('editorCodeLens.foreground'),
    },
});

const BOT_AUTHORED_DECORATION = vscode.window.createTextEditorDecorationType({
    gutterIconSize: '80%',
    overviewRulerColor: 'rgba(234, 179, 8, 0.6)',
    overviewRulerLane: vscode.OverviewRulerLane.Left,
    after: {
        margin: '0 0 0 1em',
        color: new vscode.ThemeColor('editorCodeLens.foreground'),
    },
});

// ── Receipt index ───────────────────────────────────────────────────

interface ReceiptSummary {
    sha: string;
    isAI: boolean;
    isBot: boolean;
    authorshipClass: string;
    signals: string[];
    timestamp: string;
}

/** Compatibility shim for existing watcher wiring. */
export function invalidateReceiptIndex(_folderPath: string): void {
    // AI blame now resolves receipt summaries from the shared explorer state.
}

// ── Git blame integration ───────────────────────────────────────────

interface BlameLine {
    sha: string;
    lineNumber: number; // 0-based
}

async function getBlameForFile(filePath: string, cwd: string): Promise<BlameLine[]> {
    const blameByLine = new Map<number, string>();
    try {
        const { stdout } = await execFileAsync('git', [
            'blame', '--porcelain', '--', filePath,
        ], { cwd, timeout: 10_000, maxBuffer: 4 * 1024 * 1024 });

        for (const line of stdout.split('\n')) {
            // Porcelain headers are either:
            //   <sha> <orig> <final> <count>
            // or
            //   <sha> <orig> <final>
            const match = line.match(/^([0-9a-f]{40})\s+\d+\s+(\d+)(?:\s+(\d+))?$/);
            if (match) {
                const sha = match[1];
                const startLine = parseInt(match[2], 10) - 1;
                const span = Math.max(1, parseInt(match[3] || '1', 10));
                for (let offset = 0; offset < span; offset++) {
                    blameByLine.set(startLine + offset, sha);
                }
            }
        }
    } catch {
        // git blame fails on new/untracked files — that's fine
    }

    return Array.from(blameByLine.entries())
        .sort((left, right) => left[0] - right[0])
        .map(([lineNumber, sha]) => ({ lineNumber, sha }));
}

// ── Decoration application ──────────────────────────────────────────

export interface AIBlameDeps {
    getAccessibleWorkspaceFolders: () => vscode.WorkspaceFolder[];
    getReceiptSummary: (folder: vscode.WorkspaceFolder, commitSha: string) => ReceiptSummary | undefined;
}

let enabled = false;
let deps: AIBlameDeps | undefined;

async function applyDecorations(editor: vscode.TextEditor): Promise<void> {
    if (!enabled || !deps) {
        editor.setDecorations(AI_ASSISTED_DECORATION, []);
        editor.setDecorations(BOT_AUTHORED_DECORATION, []);
        return;
    }

    const doc = editor.document;
    if (doc.uri.scheme !== 'file') { return; }

    const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
    if (!folder) { return; }

    const folderPath = folder.uri.fsPath;
    const relativePath = path.relative(folderPath, doc.uri.fsPath);

    const blameLines = await getBlameForFile(relativePath, folderPath);
    const summaryCache = new Map<string, ReceiptSummary | null>();

    const aiRanges: vscode.DecorationOptions[] = [];
    const botRanges: vscode.DecorationOptions[] = [];

    // Group consecutive lines by commit to produce ranges
    let i = 0;
    while (i < blameLines.length) {
        const bl = blameLines[i];
        if (!summaryCache.has(bl.sha)) {
            summaryCache.set(bl.sha, deps.getReceiptSummary(folder, bl.sha) || null);
        }
        const receipt = summaryCache.get(bl.sha) || undefined;

        if (!receipt || (!receipt.isAI && !receipt.isBot)) {
            i++;
            continue;
        }

        // Find consecutive lines with the same sha
        let end = i;
        while (end + 1 < blameLines.length && blameLines[end + 1].sha === bl.sha) {
            end++;
        }

        const endLineNumber = blameLines[end].lineNumber;
        const endCharacter = doc.lineAt(endLineNumber).range.end.character;
        const range = new vscode.Range(bl.lineNumber, 0, endLineNumber, endCharacter);
        const signalLabel = receipt.signals.length > 0
            ? receipt.signals.slice(0, 3).join(', ')
            : receipt.authorshipClass;

        const hoverMessage = new vscode.MarkdownString(
            `**AIIR**: ${receipt.isBot ? 'Bot' : 'AI'}-assisted commit \`${bl.sha.slice(0, 8)}\`\n\n` +
            `Class: **${receipt.authorshipClass}**\n\n` +
            (receipt.signals.length > 0 ? `Signals: ${receipt.signals.join(', ')}\n\n` : '') +
            `Receipted: ${receipt.timestamp}`,
        );
        hoverMessage.isTrusted = true;

        const decoration: vscode.DecorationOptions = {
            range,
            hoverMessage,
            renderOptions: {
                after: {
                    contentText: ` $(shield) ${signalLabel}`,
                },
            },
        };

        if (receipt.isBot) {
            botRanges.push(decoration);
        } else {
            aiRanges.push(decoration);
        }

        i = end + 1;
    }

    editor.setDecorations(AI_ASSISTED_DECORATION, aiRanges);
    editor.setDecorations(BOT_AUTHORED_DECORATION, botRanges);
}

// ── Public API ──────────────────────────────────────────────────────

export function registerAIBlameDecorations(
    context: vscode.ExtensionContext,
    blameDeps: AIBlameDeps,
): void {
    deps = blameDeps;

    // Restore persisted state
    enabled = context.globalState.get<boolean>('aiir.aiBlameEnabled', false);

    // Toggle command
    context.subscriptions.push(
        vscode.commands.registerCommand('aiir.toggleAIBlame', () => {
            enabled = !enabled;
            context.globalState.update('aiir.aiBlameEnabled', enabled);
            vscode.commands.executeCommand('setContext', 'aiir.aiBlameEnabled', enabled);

            if (enabled) {
                const editor = vscode.window.activeTextEditor;
                if (editor) { applyDecorations(editor); }
            } else {
                // Clear all decorations
                for (const editor of vscode.window.visibleTextEditors) {
                    editor.setDecorations(AI_ASSISTED_DECORATION, []);
                    editor.setDecorations(BOT_AUTHORED_DECORATION, []);
                }
            }
        }),
    );

    // Set initial context for when-clauses
    vscode.commands.executeCommand('setContext', 'aiir.aiBlameEnabled', enabled);

    // Apply on editor change
    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(editor => {
            if (editor) { applyDecorations(editor); }
        }),
    );

    // Reapply when visible editors change (splits)
    context.subscriptions.push(
        vscode.window.onDidChangeVisibleTextEditors(editors => {
            for (const editor of editors) {
                applyDecorations(editor);
            }
        }),
    );

    // Apply immediately if there's an active editor
    if (enabled && vscode.window.activeTextEditor) {
        applyDecorations(vscode.window.activeTextEditor);
    }
}
