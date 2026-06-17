const test = require('node:test');
const assert = require('node:assert/strict');

const {
    getContextState,
    getExplorerMessage,
    getNetworkBlockedMessage,
    getNoAccessibleWorkspaceMessage,
    isHubEnabled,
    isNetworkAllowed,
} = require('../out/security_policy.js');

test('isNetworkAllowed blocks network access when strict local-only mode is enabled', () => {
    assert.equal(isNetworkAllowed(true), false);
    assert.equal(isNetworkAllowed(false), true);
});

test('isHubEnabled requires both network access and enabled Hub features', () => {
    assert.equal(isHubEnabled(true, true), false);
    assert.equal(isHubEnabled(false, false), false);
    assert.equal(isHubEnabled(false, true), true);
});

test('getNoAccessibleWorkspaceMessage returns the isolation warning when access is blocked', () => {
    assert.equal(
        getNoAccessibleWorkspaceMessage('generate receipts', true),
        'AIIR: Automatic access is blocked in this multi-root workspace until aiir.allowedWorkspaceFolders is configured.',
    );
    assert.equal(
        getNoAccessibleWorkspaceMessage('generate receipts', false),
        'AIIR: Open a folder or workspace to generate receipts',
    );
});

test('getExplorerMessage returns a warning only when isolation is blocking access', () => {
    assert.equal(
        getExplorerMessage(true),
        'Automatic discovery is disabled in this multi-root workspace until aiir.allowedWorkspaceFolders is configured.',
    );
    assert.equal(getExplorerMessage(false), undefined);
});

test('getNetworkBlockedMessage explains how to re-enable network actions', () => {
    assert.equal(
        getNetworkBlockedMessage('connect to Hub'),
        'Local-only mode is enabled. Disable aiir.strictLocalOnly to connect to Hub.',
    );
});

test('getContextState derives all command palette context keys consistently', () => {
    assert.deepEqual(getContextState(true, true), {
        strictLocalOnly: true,
        networkAllowed: false,
        hubEnabled: false,
    });

    assert.deepEqual(getContextState(false, true), {
        strictLocalOnly: false,
        networkAllowed: true,
        hubEnabled: true,
    });
});