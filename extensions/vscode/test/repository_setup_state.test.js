const test = require('node:test');
const assert = require('node:assert/strict');

const {
    SETUP_PRIORITY_CHAIN,
    isRepositoryFullyReady,
    resolveRepositoryViewStateSnapshot,
    shouldShowRepository,
    sortSetupChecklist,
} = require('../out/repository_setup_state.js');

test('shouldShowRepository keeps initialized and ledger-backed repositories visible', () => {
    assert.equal(shouldShowRepository(undefined), false);
    assert.equal(shouldShowRepository({
        gitAvailable: true,
        cliAvailable: false,
        aiirDirExists: false,
        hasLedger: false,
        policyExists: false,
        hookState: 'missing',
        provenanceQueueExists: false,
        hasReceipts: false,
    }), false);
    assert.equal(shouldShowRepository({
        gitAvailable: true,
        cliAvailable: false,
        aiirDirExists: true,
        hasLedger: false,
        policyExists: false,
        hookState: 'missing',
        provenanceQueueExists: false,
        hasReceipts: false,
    }), true);
    assert.equal(shouldShowRepository({
        gitAvailable: true,
        cliAvailable: false,
        aiirDirExists: false,
        hasLedger: true,
        policyExists: false,
        hookState: 'missing',
        provenanceQueueExists: false,
        hasReceipts: false,
    }), true);
});

test('isRepositoryFullyReady requires policy as part of durable setup readiness', () => {
    assert.equal(isRepositoryFullyReady(undefined), false);
    assert.equal(isRepositoryFullyReady({
        gitAvailable: true,
        cliAvailable: true,
        aiirDirExists: true,
        hasLedger: true,
        policyExists: false,
        hookState: 'missing',
        provenanceQueueExists: false,
        hasReceipts: false,
    }), false);
    assert.equal(isRepositoryFullyReady({
        gitAvailable: true,
        cliAvailable: true,
        aiirDirExists: true,
        hasLedger: true,
        policyExists: true,
        hookState: 'managed',
        provenanceQueueExists: true,
        hasReceipts: false,
    }), true);
});

test('sortSetupChecklist keeps missing prerequisites first and live activity last', () => {
    const sorted = sortSetupChecklist([
        { key: 'live-activity', ready: false, live: true, label: 'AI tool active now' },
        { key: 'policy', ready: true, label: 'Policy configured' },
        { key: 'cli', ready: false, label: 'CLI available' },
        { key: 'aiir', ready: false, label: 'AIIR initialized' },
        { key: 'git', ready: true, label: 'Git available' },
    ]);

    assert.deepEqual(SETUP_PRIORITY_CHAIN.slice(0, 4), ['git', 'cli', 'aiir', 'ledger']);
    assert.deepEqual(sorted.map(item => item.label), [
        'CLI available',
        'AIIR initialized',
        'Git available',
        'Policy configured',
        'AI tool active now',
    ]);
});

test('resolveRepositoryViewStateSnapshot assembles durable repository state from probes', () => {
    assert.deepEqual(resolveRepositoryViewStateSnapshot({
        gitAvailable: true,
        branch: 'feat/vscode-extension-wip',
        headSha: 'abc123',
        cliAvailable: true,
        aiirDirExists: true,
        hasLedger: true,
        policyExists: true,
        hookState: 'managed',
        provenanceQueueExists: true,
        receiptCount: 3,
        hasReceipts: true,
        headReceiptStatus: 'present',
        activeAIToolName: 'copilot',
    }), {
        gitAvailable: true,
        branch: 'feat/vscode-extension-wip',
        headSha: 'abc123',
        cliAvailable: true,
        aiirDirExists: true,
        hasLedger: true,
        policyExists: true,
        hookState: 'managed',
        provenanceQueueExists: true,
        receiptCount: 3,
        hasReceipts: true,
        headReceiptStatus: 'present',
        activeAIToolName: 'copilot',
        activeAIToolPresent: true,
    });
});

test('resolveRepositoryViewStateSnapshot keeps live AI activity separate from durable setup state', () => {
    const state = resolveRepositoryViewStateSnapshot({
        gitAvailable: false,
        branch: undefined,
        headSha: undefined,
        cliAvailable: false,
        aiirDirExists: true,
        hasLedger: false,
        policyExists: false,
        hookState: 'missing',
        provenanceQueueExists: false,
        receiptCount: 0,
        hasReceipts: false,
        headReceiptStatus: 'unknown',
    });

    assert.equal(state.activeAIToolName, undefined);
    assert.equal(state.activeAIToolPresent, false);
    assert.equal(state.aiirDirExists, true);
    assert.equal(state.hasLedger, false);
    assert.equal(state.headReceiptStatus, 'unknown');
});
