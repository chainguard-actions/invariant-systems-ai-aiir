const test = require('node:test');
const assert = require('node:assert/strict');
const {
    resolveHomeState,
    resolveTrustState,
    getHomeStateTitle,
    getHomeStateNextAction,
    getHomePrimaryCardDefinition,
} = require('../out/home_state.js');

test('resolveHomeState collapses user conditions into the expected dashboard states', () => {
    assert.equal(resolveHomeState({
        workspaceOpen: false,
        accessBlocked: false,
        cliAvailable: false,
        repoInitialized: false,
        receiptsExist: false,
        allReceiptsValid: true,
        headCovered: false,
    }), 'no-workspace');

    assert.equal(resolveHomeState({
        workspaceOpen: true,
        accessBlocked: true,
        cliAvailable: true,
        repoInitialized: true,
        receiptsExist: false,
        allReceiptsValid: true,
        headCovered: false,
    }), 'access-blocked');

    assert.equal(resolveHomeState({
        workspaceOpen: true,
        accessBlocked: false,
        cliAvailable: false,
        repoInitialized: false,
        receiptsExist: false,
        allReceiptsValid: true,
        headCovered: false,
    }), 'cli-missing');

    assert.equal(resolveHomeState({
        workspaceOpen: true,
        accessBlocked: false,
        cliAvailable: true,
        repoInitialized: false,
        receiptsExist: false,
        allReceiptsValid: true,
        headCovered: false,
    }), 'not-initialized');

    assert.equal(resolveHomeState({
        workspaceOpen: true,
        accessBlocked: false,
        cliAvailable: true,
        repoInitialized: true,
        receiptsExist: false,
        allReceiptsValid: true,
        headCovered: false,
    }), 'ready-no-receipts');

    assert.equal(resolveHomeState({
        workspaceOpen: true,
        accessBlocked: false,
        cliAvailable: true,
        repoInitialized: true,
        policyEnabled: false,
        receiptsExist: false,
        allReceiptsValid: true,
        headCovered: false,
    }), 'ready-no-receipts');

    assert.equal(resolveHomeState({
        workspaceOpen: true,
        accessBlocked: false,
        cliAvailable: false,
        repoInitialized: false,
        receiptsExist: true,
        allReceiptsValid: true,
        headCovered: false,
    }), 'healthy');

    assert.equal(resolveHomeState({
        workspaceOpen: true,
        accessBlocked: false,
        cliAvailable: true,
        repoInitialized: true,
        receiptsExist: true,
        allReceiptsValid: false,
        headCovered: true,
    }), 'failing');

    // Regulated mode: evidence bar not met → regulated-incomplete
    assert.equal(resolveHomeState({
        workspaceOpen: true,
        accessBlocked: false,
        cliAvailable: true,
        repoInitialized: true,
        receiptsExist: true,
        allReceiptsValid: true,
        headCovered: true,
        regulatedMode: true,
        meetsEvidenceBar: false,
    }), 'regulated-incomplete');

    // Regulated mode: evidence bar met → healthy
    assert.equal(resolveHomeState({
        workspaceOpen: true,
        accessBlocked: false,
        cliAvailable: true,
        repoInitialized: true,
        receiptsExist: true,
        allReceiptsValid: true,
        headCovered: true,
        regulatedMode: true,
        meetsEvidenceBar: true,
    }), 'healthy');
});

test('healthy and failing states expose the right user-facing actions', () => {
    assert.equal(getHomeStateTitle('healthy'), 'Current commit activity is recorded');
    assert.equal(getHomeStateTitle('access-blocked'), 'Repository hidden by workspace policy');
    assert.equal(getHomeStateTitle('cli-missing'), 'This commit needs the AIIR CLI');
    assert.equal(getHomeStateTitle('not-initialized'), 'This commit needs repository setup');
    assert.deepEqual(getHomeStateNextAction('ready-no-receipts'), {
        label: 'Record Commit Activity',
        description: 'Create a verifiable record for the current commit. AIIR prefers deterministic provenance when the active file supports it, then falls back automatically.',
        commandId: 'aiir.generatePreferred',
        iconId: 'sparkle',
    });

    assert.deepEqual(getHomePrimaryCardDefinition('access-blocked', 0, false), {
        headline: 'Allow this repository in workspace policy',
        detail: 'A repository is open, but AIIR is currently prevented from reading it by workspace isolation or the allowlist.',
        primaryAction: { label: 'Fix Workspace Access', commandId: 'aiir.securityPosture' },
    });

    assert.deepEqual(getHomePrimaryCardDefinition('not-initialized', 0, false), {
        headline: 'This commit needs repository setup',
        detail: 'The repository is open and the CLI is ready, but local AIIR scaffolding is missing. Initialize it once so AIIR can record the current and future commits here.',
        primaryAction: { label: 'Initialize Repository', commandId: 'aiir.initializeRepo' },
    });

    assert.deepEqual(getHomePrimaryCardDefinition('healthy', 0, true), {
        headline: 'Current commit activity is recorded',
        detail: 'This repository is covered for the current workflow and the latest receipt is verifying cleanly.',
        primaryAction: { label: 'View Latest Receipt', commandId: 'aiir.viewReceipt' },
        secondaryAction: { label: 'Signing Guide', commandId: 'aiir.openSigningGuide' },
    });

    assert.deepEqual(getHomePrimaryCardDefinition('healthy', 0, true, { sigstoreReceiptCount: 5 }), {
        headline: 'Current commit activity is recorded',
        detail: 'This repository is covered for the current workflow and the latest receipt is verifying cleanly.',
        primaryAction: { label: 'View Latest Receipt', commandId: 'aiir.viewReceipt' },
        secondaryAction: undefined,
    });

    assert.deepEqual(getHomePrimaryCardDefinition('failing', 2, true), {
        headline: '2 receipts need attention',
        detail: 'One or more receipts failed verification. Review them before relying on the current record.',
        primaryAction: { label: 'Check Receipts', commandId: 'aiir.verifyAll' },
    });
});

test('resolveTrustState returns structured readiness and coverage data for shared consumers', () => {
    assert.deepEqual(resolveTrustState({
        workspaceOpen: true,
        accessBlocked: false,
        repoName: 'aiir',
        branch: 'main',
        folderCount: 1,
        receiptCount: 3,
        invalidReceiptCount: 0,
        cliAvailable: true,
        repoInitialized: true,
        headReceiptStatus: 'present',
        latestReceipt: {
            label: 'Add trust state resolver',
            author: 'Kale',
            timestamp: 'just now',
            uri: 'file:///receipt.json',
        },
        activeAITool: 'copilot',
        hookKind: 'managed',
        headSha: 'abc123',
    }), {
        homeState: 'healthy',
        vertex: 'covered',
        level: 'good',
        title: 'Current commit activity is recorded',
        nextAction: {
            label: 'View Latest Receipt',
            description: 'Open the latest clean receipt for this repository and verify what was recorded.',
            commandId: 'aiir.viewReceipt',
            iconId: 'preview',
        },
        primaryCard: {
            headline: 'Current commit activity is recorded',
            detail: 'This repository is covered for the current workflow and the latest receipt is verifying cleanly.',
            primaryAction: { label: 'View Latest Receipt', commandId: 'aiir.viewReceipt' },
            secondaryAction: { label: 'Signing Guide', commandId: 'aiir.openSigningGuide' },
        },
        repoName: 'aiir',
        branch: 'main',
        folderCount: 1,
        receiptCount: 3,
        invalidReceiptCount: 0,
        hasReceipts: true,
        headCovered: true,
        headReceiptStatus: 'present',
        latestReceipt: {
            label: 'Add trust state resolver',
            author: 'Kale',
            timestamp: 'just now',
            uri: 'file:///receipt.json',
        },
        primaryAction: {
            label: 'View Latest Receipt',
            commandId: 'aiir.viewReceipt',
            args: ['file:///receipt.json'],
        },
        cliAvailable: true,
        repoInitialized: true,
        activeAITool: 'copilot',
        hookKind: 'managed',
        headSha: 'abc123',
        accessBlocked: false,
        workspaceOpen: true,
    });
});
