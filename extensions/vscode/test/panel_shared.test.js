const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const panelSharedSourcePath = path.join(__dirname, '..', 'src', 'panel_shared.ts');
const panelSharedSource = fs.readFileSync(panelSharedSourcePath, 'utf8');

test('shared panel script falls back to inline command attributes at click time', () => {
    assert.match(
        panelSharedSource,
        /closest\('\[data-aiir-command\], \[onclick\]'\)/,
        'expected click handling to recognize buttons that still carry inline command attributes',
    );
    assert.match(
        panelSharedSource,
        /const parsed = parseInlineCommand\(element\.getAttribute\('onclick'\)\);/,
        'expected click handling to lazily parse inline command attributes when data attributes are missing',
    );
    assert.match(
        panelSharedSource,
        /wirePanelCommands\(\);\n\n        if \(document\.readyState === 'loading'\)/,
        'expected command wiring to run immediately instead of waiting only for DOMContentLoaded',
    );
    assert.match(
        panelSharedSource,
        /export function renderCommandAttributes\(command: string, args: unknown\[] = \[]\): string \{[\s\S]*data-aiir-command=/,
        'expected shared panels to expose CSP-safe command attributes for editor popup buttons',
    );
});