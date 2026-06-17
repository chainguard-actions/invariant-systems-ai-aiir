const test = require('node:test');
const assert = require('node:assert/strict');

const { resolveHubState } = require('../out/hub_state.js');

const defaultOptions = {
    networkAllowed: true,
    hubEnabled: true,
};

function createConnection(overrides = {}) {
    return {
        configured: false,
        connected: false,
        authenticated: false,
        ...overrides,
    };
}

test('resolveHubState stays local-only when network access is blocked', () => {
    const resolved = resolveHubState(createConnection({
        configured: true,
        connected: true,
        authenticated: true,
        session: {
            tenant: {
                tier: 'starter',
                enabled: true,
            },
        },
        onboarding: {
            status: 'ready',
            onboarding_complete: true,
        },
    }), {
        networkAllowed: false,
        hubEnabled: true,
    });

    assert.equal(resolved.entitlementState, 'localOnly');
    assert.equal(resolved.offerFamily, 'local_free');
    assert.equal(resolved.capabilities.hubConnection, false);
    assert.equal(resolved.capabilities.remoteReceiptSync, false);
});

test('resolveHubState maps canonical Foundation starter payloads to active individual Hub access', () => {
    const resolved = resolveHubState(createConnection({
        configured: true,
        connected: true,
        authenticated: true,
        session: {
            tenant: {
                tenant_id: 'tenant_starter',
                tier: 'starter',
                enabled: true,
            },
        },
        onboarding: {
            status: 'ready',
            onboarding_complete: true,
            tier: 'starter',
            hub_url: 'https://example.invalid/hub',
        },
    }), defaultOptions);

    assert.equal(resolved.entitlementState, 'paidActive');
    assert.equal(resolved.offerFamily, 'hub_individual');
    assert.equal(resolved.capabilities.hubConnection, true);
    assert.equal(resolved.capabilities.remoteReceiptSync, true);
    assert.equal(resolved.capabilities.sharedRepositories, false);
    assert.equal(resolved.primaryActionCommandId, 'aiir.openHubDashboard');
});

test('resolveHubState keeps pending onboarding in seat-pending state even with a recognized tier', () => {
    const resolved = resolveHubState(createConnection({
        configured: true,
        connected: true,
        authenticated: true,
        session: {
            tenant: {
                tier: 'starter',
            },
        },
        onboarding: {
            status: 'pending',
            onboarding_complete: false,
            tier: 'starter',
        },
    }), defaultOptions);

    assert.equal(resolved.entitlementState, 'seatPending');
    assert.equal(resolved.offerFamily, 'hub_individual');
    assert.equal(resolved.capabilities.hubConnection, false);
    assert.equal(resolved.capabilities.remoteReceiptSync, false);
    assert.equal(resolved.primaryActionCommandId, 'aiir.hubStatus');
});

test('resolveHubState downgrades disabled canonical tenants to connected-no-plan', () => {
    const resolved = resolveHubState(createConnection({
        configured: true,
        connected: true,
        authenticated: true,
        session: {
            tenant: {
                tier: 'starter',
                enabled: false,
            },
        },
        onboarding: {
            status: 'disabled',
            onboarding_complete: false,
            tier: 'starter',
        },
    }), defaultOptions);

    assert.equal(resolved.entitlementState, 'connectedNoPlan');
    assert.equal(resolved.offerFamily, 'hub_individual');
    assert.equal(resolved.capabilities.hubConnection, false);
    assert.equal(resolved.capabilities.remoteReceiptSync, false);
    assert.equal(resolved.primaryActionCommandId, 'aiir.openHostedHubSignup');
});

test('resolveHubState expands team capabilities from canonical active team tiers', () => {
    const resolved = resolveHubState(createConnection({
        configured: true,
        connected: true,
        authenticated: true,
        session: {
            tenant: {
                tier: 'team',
                enabled: true,
            },
        },
        onboarding: {
            status: 'ready',
            onboarding_complete: true,
            tier: 'team',
        },
    }), defaultOptions);

    assert.equal(resolved.entitlementState, 'paidActive');
    assert.equal(resolved.offerFamily, 'hub_team');
    assert.equal(resolved.capabilities.remoteReceiptSync, true);
    assert.equal(resolved.capabilities.sharedRepositories, true);
    assert.equal(resolved.capabilities.teamVisibility, true);
    assert.equal(resolved.capabilities.policyManagement, true);
    assert.equal(resolved.capabilities.complianceExports, false);
});

test('resolveHubState ignores unrelated false keys when inferring entitlement and capabilities', () => {
    const resolved = resolveHubState(createConnection({
        configured: true,
        connected: true,
        authenticated: true,
        session: {
            feature_flags: {
                enterprise: false,
                active: false,
                sync: false,
            },
            metadata: {
                enabled: false,
            },
        },
        onboarding: {
            feature_flags: {
                pending: false,
            },
        },
    }), defaultOptions);

    assert.equal(resolved.entitlementState, 'connectedNoPlan');
    assert.equal(resolved.offerFamily, 'unknown');
    assert.equal(resolved.capabilities.hubConnection, false);
    assert.equal(resolved.capabilities.remoteReceiptSync, false);
    assert.equal(resolved.capabilities.sharedRepositories, false);
    assert.equal(resolved.capabilities.complianceExports, false);
});
