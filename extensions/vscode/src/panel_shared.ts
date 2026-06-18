export type PanelId = 'readiness' | 'summary' | 'health' | 'control' | 'hub' | 'billing' | 'security' | 'presets' | 'settings' | 'signup';

const WEBVIEW_NONCE_TOKEN = '__AIIR_WEBVIEW_NONCE__';

export interface PanelNavOptions {
    hubVisible?: boolean;
    networkAllowed?: boolean;
    commandTarget?: string;
    showAdvanced?: boolean;
}

export function escapeHtml(value: string): string {
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function renderCommandCall(command: string, args: unknown[] = []): string {
    const renderedArgs = args
        .map(arg => `, ${JSON.stringify(arg).replace(/"/g, '&quot;')}`)
        .join('');
    return `cmd('${command}'${renderedArgs})`;
}

export function renderCommandAttributes(command: string, args: unknown[] = []): string {
    return `data-aiir-command="${escapeHtml(command)}" data-aiir-args="${escapeHtml(JSON.stringify(args))}"`;
}

export function getPanelNavStyles(): string {
    return `
        .panel-nav {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 0 0 20px;
            padding: 10px;
            border: 1px solid var(--vscode-panel-border);
            border-radius: 12px;
            background: color-mix(in srgb, var(--vscode-editor-background) 96%, var(--vscode-panel-border) 4%);
        }
        .panel-nav button {
            font: inherit;
            cursor: pointer;
            border: 1px solid var(--vscode-panel-border);
            border-radius: 999px;
            padding: 8px 14px;
            background: transparent;
            color: inherit;
        }
        .panel-nav button.active {
            border-color: color-mix(in srgb, var(--vscode-charts-blue) 55%, var(--vscode-panel-border));
            background: color-mix(in srgb, var(--vscode-charts-blue) 12%, transparent);
            color: var(--vscode-charts-blue);
        }
    `;
}

export function getPanelNavHtml(active: PanelId, options?: PanelNavOptions): string {
    const showAdvanced = options?.showAdvanced ?? false;
    const buttons = [
        { id: 'readiness', label: 'Status', command: 'aiir.readinessCheck', visible: true },
        { id: 'summary', label: 'Summary', command: 'aiir.showSummary', visible: true },
        { id: 'health', label: 'Health', command: 'aiir.healthCheck', visible: true },
        { id: 'control', label: 'Advanced', command: 'aiir.controlPanel', visible: showAdvanced || active === 'control' },
        { id: 'security', label: 'Security', command: 'aiir.securityPosture', visible: showAdvanced || active === 'security' },
        { id: 'presets', label: 'Presets', command: 'aiir.rolloutPresets', visible: showAdvanced || active === 'presets' },
        { id: 'settings', label: 'Settings', command: 'aiir.advancedSettings', visible: showAdvanced || active === 'settings' },
        { id: 'billing', label: 'Plans', command: 'aiir.hubBilling', visible: true },
        { id: 'hub', label: 'Hub Status', command: 'aiir.hubStatus', visible: !!options?.hubVisible },
        { id: 'signup', label: 'Request Access', command: 'aiir.signUpForHub', visible: !!options?.networkAllowed },
    ];

    return `<div class="panel-nav">${buttons
        .filter(button => button.visible)
        .map(button => `<button class="${button.id === active ? 'active' : ''}" onclick="${renderCommandCall(button.command, options?.commandTarget ? [options.commandTarget] : [])}">${button.label}</button>`)
        .join('')}</div>`;
}

export function getPanelScript(): string {
    return `<script nonce="${WEBVIEW_NONCE_TOKEN}">
        const vscode = acquireVsCodeApi();
        function cmd(command, ...args) { vscode.postMessage({ command, args }); }

        function parseInlineCommand(expression) {
            if (typeof expression !== 'string') {
                return undefined;
            }

            const trimmed = expression.trim();
            const match = /^cmd\('([^']+)'(.*)\);?$/.exec(trimmed);
            if (!match) {
                return undefined;
            }

            const command = match[1];
            const argsSource = match[2].trim();
            if (!argsSource) {
                return { command, args: [] };
            }

            const serializedArgs = argsSource.replace(/^,\s*/, '');
            try {
                return { command, args: JSON.parse('[' + serializedArgs + ']') };
            } catch {
                console.warn('AIIR: Failed to parse panel command', trimmed);
                return undefined;
            }
        }

        function getPanelCommand(element) {
            const existingCommand = element.getAttribute('data-aiir-command');
            if (existingCommand) {
                const argsRaw = element.getAttribute('data-aiir-args');
                let args = [];
                if (argsRaw) {
                    try {
                        args = JSON.parse(argsRaw);
                    } catch {
                        console.warn('AIIR: Failed to parse panel command args', existingCommand);
                    }
                }
                return { command: existingCommand, args };
            }

            const parsed = parseInlineCommand(element.getAttribute('onclick'));
            if (!parsed) {
                return undefined;
            }

            element.setAttribute('data-aiir-command', parsed.command);
            element.setAttribute('data-aiir-args', JSON.stringify(parsed.args));
            element.removeAttribute('onclick');
            return parsed;
        }

        function wirePanelCommands() {
            for (const element of document.querySelectorAll('[onclick]')) {
                getPanelCommand(element);
            }
        }

        document.addEventListener('click', event => {
            const target = event.target instanceof Element
                ? event.target.closest('[data-aiir-command], [onclick]')
                : null;
            const fallbackTarget = !target && event.target instanceof Element ? event.target.closest('[onclick]') : null;
            const commandTarget = target || fallbackTarget;
            if (!commandTarget) {
                return;
            }

            const datasetCommand = commandTarget.getAttribute('data-aiir-command');
            const inlineCommand = datasetCommand ? undefined : parseInlineCommand(commandTarget.getAttribute('onclick'));
            let args = [];
            if (datasetCommand) {
                const argsRaw = commandTarget.getAttribute('data-aiir-args');
                if (argsRaw) {
                    try {
                        args = JSON.parse(argsRaw);
                    } catch {
                        console.warn('AIIR: Failed to parse panel command args', datasetCommand);
                    }
                } else if (inlineCommand?.args) {
                    args = inlineCommand.args;
                }
            }

            const panelCommand = datasetCommand
                ? { command: datasetCommand, args }
                : (inlineCommand ?? getPanelCommand(commandTarget));
            if (!panelCommand?.command) {
                return;
            }

            event.preventDefault();
            cmd(panelCommand.command, ...panelCommand.args);
        });

        wirePanelCommands();

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', wirePanelCommands, { once: true });
        }
    </script>`;
}
