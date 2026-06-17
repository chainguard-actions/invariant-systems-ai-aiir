export interface JsonRecordLike {
    [key: string]: unknown;
}

export interface HubConnectionSnapshot {
    configured: boolean;
    connected: boolean;
    authenticated: boolean;
    baseUrl?: string;
    tenantId?: string;
    session?: JsonRecordLike;
    onboarding?: JsonRecordLike;
    error?: string;
}

export type HubEntitlementState =
    | 'localOnly'
    | 'eligibleForUpgrade'
    | 'connecting'
    | 'connectedNoPlan'
    | 'trialActive'
    | 'paidActive'
    | 'seatPending'
    | 'paymentActionRequired'
    | 'expired'
    | 'connectionError';

export type HubOfferFamily = 'local_free' | 'hub_individual' | 'hub_team' | 'hub_enterprise' | 'unknown';

export interface HubCapabilities {
    localCore: boolean;
    hubConnection: boolean;
    remoteReceiptSync: boolean;
    sharedRepositories: boolean;
    teamVisibility: boolean;
    policyManagement: boolean;
    complianceExports: boolean;
    adminControls: boolean;
    prioritySupport: boolean;
}

export interface ResolvedHubState {
    entitlementState: HubEntitlementState;
    offerFamily: HubOfferFamily;
    capabilities: HubCapabilities;
    networkAllowed: boolean;
    hubEnabled: boolean;
    configured: boolean;
    connected: boolean;
    authenticated: boolean;
    stateLabel: string;
    stateDetail: string;
    primaryActionLabel: string;
    primaryActionCommandId: string;
    secondaryActionLabel?: string;
    secondaryActionCommandId?: string;
}

interface ResolveHubStateOptions {
    networkAllowed: boolean;
    hubEnabled: boolean;
}

const EMPTY_CAPABILITIES: HubCapabilities = {
    localCore: true,
    hubConnection: false,
    remoteReceiptSync: false,
    sharedRepositories: false,
    teamVisibility: false,
    policyManagement: false,
    complianceExports: false,
    adminControls: false,
    prioritySupport: false,
};

function asRecord(value: unknown): JsonRecordLike | undefined {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return undefined;
    }

    return value as JsonRecordLike;
}

function getPathValue(root: unknown, path: string[]): unknown {
    let current: unknown = root;
    for (const segment of path) {
        const record = asRecord(current);
        if (!record || !(segment in record)) {
            return undefined;
        }
        current = record[segment];
    }

    return current;
}

function readFirstString(root: unknown, paths: string[][]): string | undefined {
    for (const path of paths) {
        const value = getPathValue(root, path);
        if (typeof value === 'string') {
            const trimmed = value.trim();
            if (trimmed) {
                return trimmed;
            }
        }
    }

    return undefined;
}

function readFirstBoolean(root: unknown, paths: string[][]): boolean | undefined {
    for (const path of paths) {
        const value = getPathValue(root, path);
        if (typeof value === 'boolean') {
            return value;
        }
        if (typeof value === 'string') {
            const normalized = value.trim().toLowerCase();
            if (normalized === 'true') {
                return true;
            }
            if (normalized === 'false') {
                return false;
            }
        }
    }

    return undefined;
}

function collectStringTokens(value: unknown, tokens: Set<string>): void {
    if (!value) {
        return;
    }

    if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        if (normalized) {
            tokens.add(normalized);
        }
        return;
    }

    if (Array.isArray(value)) {
        for (const entry of value) {
            collectStringTokens(entry, tokens);
        }
        return;
    }

    const record = asRecord(value);
    if (!record) {
        return;
    }

    for (const [key, entry] of Object.entries(record)) {
        if (typeof entry === 'boolean' && entry) {
            tokens.add(key.trim().toLowerCase());
        }
        collectStringTokens(entry, tokens);
    }
}

function hasToken(tokens: Set<string>, candidates: string[]): boolean {
    return candidates.some(candidate => tokens.has(candidate));
}

function resolveOfferFamily(tokens: Set<string>): HubOfferFamily {
    if (hasToken(tokens, ['starter'])) {
        return 'hub_individual';
    }
    if (hasToken(tokens, ['hub_enterprise', 'enterprise', 'fortress', 'enterprise_plus'])) {
        return 'hub_enterprise';
    }
    if (hasToken(tokens, ['hub_team', 'team', 'org', 'organization', 'business'])) {
        return 'hub_team';
    }
    if (hasToken(tokens, ['hub_individual', 'individual', 'personal', 'pro'])) {
        return 'hub_individual';
    }
    if (hasToken(tokens, ['local_free', 'free'])) {
        return 'local_free';
    }

    return 'unknown';
}

function resolveCapabilities(tokens: Set<string>, offerFamily: HubOfferFamily, active: boolean): HubCapabilities {
    const capabilities: HubCapabilities = {
        ...EMPTY_CAPABILITIES,
        hubConnection: active,
        remoteReceiptSync: hasToken(tokens, ['remotereceiptsync', 'receipt-sync', 'sync', 'remote_sync']),
        sharedRepositories: hasToken(tokens, ['sharedrepositories', 'shared-repositories', 'shared-repos', 'shared_repo']),
        teamVisibility: hasToken(tokens, ['teamvisibility', 'team-visibility', 'team', 'org-visibility']),
        policyManagement: hasToken(tokens, ['policymanagement', 'policy-management', 'policy', 'governance']),
        complianceExports: hasToken(tokens, ['complianceexports', 'compliance-exports', 'evidence-pack', 'audit-export']),
        adminControls: hasToken(tokens, ['admincontrols', 'admin-controls', 'admin', 'seat-admin']),
        prioritySupport: hasToken(tokens, ['prioritysupport', 'priority-support', 'support']),
    };

    if (!active) {
        return capabilities;
    }

    if (offerFamily === 'hub_individual') {
        capabilities.remoteReceiptSync = true;
    }
    if (offerFamily === 'hub_team' || offerFamily === 'hub_enterprise') {
        capabilities.remoteReceiptSync = true;
        capabilities.sharedRepositories = true;
        capabilities.teamVisibility = true;
        capabilities.policyManagement = true;
    }
    if (offerFamily === 'hub_enterprise') {
        capabilities.complianceExports = true;
        capabilities.adminControls = true;
        capabilities.prioritySupport = true;
    }

    return capabilities;
}

function getStatePresentation(state: HubEntitlementState, offerFamily: HubOfferFamily): Omit<ResolvedHubState, 'entitlementState' | 'offerFamily' | 'capabilities' | 'networkAllowed' | 'hubEnabled' | 'configured' | 'connected' | 'authenticated'> {
    switch (state) {
        case 'localOnly':
            return {
                stateLabel: 'Local-Only',
                stateDetail: 'AIIR remains fully usable without an account. Connect Hub only when you want shared or governed workflows.',
                primaryActionLabel: 'Review Plans',
                primaryActionCommandId: 'aiir.hubBilling',
                secondaryActionLabel: 'Continue Local',
                secondaryActionCommandId: 'aiir.readinessCheck',
            };
        case 'eligibleForUpgrade':
            return {
                stateLabel: 'Upgrade Available',
                stateDetail: 'Hub is optional. Use it only for shared repositories, policy coordination, or hosted evidence workflows.',
                primaryActionLabel: 'Open Hosted Signup',
                primaryActionCommandId: 'aiir.openHostedHubSignup',
                secondaryActionLabel: 'Review Plans',
                secondaryActionCommandId: 'aiir.hubBilling',
            };
        case 'connecting':
            return {
                stateLabel: 'Connecting',
                stateDetail: 'Finish the browser-based account flow, then refresh Hub status in VS Code.',
                primaryActionLabel: 'Open Hosted Signup',
                primaryActionCommandId: 'aiir.openHostedHubSignup',
                secondaryActionLabel: 'Hub Status',
                secondaryActionCommandId: 'aiir.hubStatus',
            };
        case 'connectedNoPlan':
            return {
                stateLabel: 'Connected, No Plan',
                stateDetail: 'The account is connected, but no active Hub entitlement is visible yet.',
                primaryActionLabel: 'Choose Plan',
                primaryActionCommandId: 'aiir.openHostedHubSignup',
                secondaryActionLabel: 'Hub Status',
                secondaryActionCommandId: 'aiir.hubStatus',
            };
        case 'trialActive':
            return {
                stateLabel: 'Trial Active',
                stateDetail: 'Hub capabilities are temporarily enabled. Upgrade in the browser when you are ready to keep them.',
                primaryActionLabel: 'Open Hub Dashboard',
                primaryActionCommandId: 'aiir.openHubDashboard',
                secondaryActionLabel: 'Upgrade Plan',
                secondaryActionCommandId: 'aiir.openHostedHubSignup',
            };
        case 'paidActive':
            return {
                stateLabel: offerFamily === 'hub_enterprise' ? 'Enterprise Active' : offerFamily === 'hub_team' ? 'Team Active' : 'Hub Active',
                stateDetail: 'Hub capabilities are available in this workspace according to the connected account entitlement.',
                primaryActionLabel: 'Open Hub Dashboard',
                primaryActionCommandId: 'aiir.openHubDashboard',
                secondaryActionLabel: 'Hub Status',
                secondaryActionCommandId: 'aiir.hubStatus',
            };
        case 'seatPending':
            return {
                stateLabel: 'Seat Pending',
                stateDetail: 'The account is connected, but seat assignment or admin approval is still pending. Local AIIR remains available.',
                primaryActionLabel: 'Hub Status',
                primaryActionCommandId: 'aiir.hubStatus',
                secondaryActionLabel: 'Continue Local',
                secondaryActionCommandId: 'aiir.readinessCheck',
            };
        case 'paymentActionRequired':
            return {
                stateLabel: 'Payment Action Required',
                stateDetail: 'Hub access is paused pending billing action. Local AIIR workflows remain available.',
                primaryActionLabel: 'Manage Plan',
                primaryActionCommandId: 'aiir.openHostedHubSignup',
                secondaryActionLabel: 'Continue Local',
                secondaryActionCommandId: 'aiir.readinessCheck',
            };
        case 'expired':
            return {
                stateLabel: 'Expired',
                stateDetail: 'The prior Hub entitlement is no longer active. Local AIIR continues to work without disruption.',
                primaryActionLabel: 'Renew Hub',
                primaryActionCommandId: 'aiir.openHostedHubSignup',
                secondaryActionLabel: 'Continue Local',
                secondaryActionCommandId: 'aiir.readinessCheck',
            };
        case 'connectionError':
            return {
                stateLabel: 'Connection Error',
                stateDetail: 'AIIR could not refresh Hub status. Retry or continue locally until network access is available again.',
                primaryActionLabel: 'Hub Status',
                primaryActionCommandId: 'aiir.hubStatus',
                secondaryActionLabel: 'Continue Local',
                secondaryActionCommandId: 'aiir.readinessCheck',
            };
    }
}

export function resolveHubState(connection: HubConnectionSnapshot, options: ResolveHubStateOptions): ResolvedHubState {
    if (!options.networkAllowed) {
        return {
            entitlementState: 'localOnly',
            offerFamily: 'local_free',
            capabilities: EMPTY_CAPABILITIES,
            networkAllowed: options.networkAllowed,
            hubEnabled: options.hubEnabled,
            configured: connection.configured,
            connected: connection.connected,
            authenticated: connection.authenticated,
            ...getStatePresentation('localOnly', 'local_free'),
        };
    }

    const tokens = new Set<string>();
    collectStringTokens(connection.session, tokens);
    collectStringTokens(connection.onboarding, tokens);

    const canonicalTier = readFirstString(connection.session, [
        ['tenant', 'tier'],
        ['plan', 'offer_family'],
        ['plan', 'code'],
        ['offer_family'],
        ['tier'],
    ]) || readFirstString(connection.onboarding, [
        ['tier'],
        ['plan', 'offer_family'],
        ['offer_family'],
    ]);

    if (canonicalTier) {
        tokens.add(canonicalTier.trim().toLowerCase());
    }

    const onboardingStatus = (readFirstString(connection.onboarding, [
        ['status'],
    ]) || '').trim().toLowerCase();
    if (onboardingStatus) {
        tokens.add(onboardingStatus);
    }

    const tenantEnabled = readFirstBoolean(connection.session, [
        ['tenant', 'enabled'],
        ['entitlement', 'active'],
        ['subscription', 'active'],
        ['active'],
    ]);
    const onboardingComplete = readFirstBoolean(connection.onboarding, [
        ['onboarding_complete'],
    ]);

    const lifecycleToken = (readFirstString(connection.session, [
        ['subscription', 'status'],
        ['tenant', 'status'],
        ['entitlement', 'state'],
        ['state'],
        ['status'],
    ]) || readFirstString(connection.onboarding, [
        ['state'],
        ['status'],
        ['subscription', 'status'],
    ]) || '').trim().toLowerCase();
    if (lifecycleToken) {
        tokens.add(lifecycleToken);
    }

    const offerToken = readFirstString(connection.session, [
        ['tenant', 'tier'],
        ['plan', 'offer_family'],
        ['plan', 'code'],
        ['plan', 'slug'],
        ['plan'],
        ['offer_family'],
        ['offer'],
        ['tier'],
    ]) || readFirstString(connection.onboarding, [
        ['plan', 'offer_family'],
        ['plan'],
        ['offer'],
        ['tier'],
    ]);
    if (offerToken) {
        tokens.add(offerToken.trim().toLowerCase());
    }

    const trialActive = readFirstBoolean(connection.session, [
        ['subscription', 'trial_active'],
        ['trial_active'],
        ['trial', 'active'],
    ]) === true || hasToken(tokens, ['trial', 'trialing', 'trial_active', 'trial-active']);
    const paymentActionRequired = hasToken(tokens, ['payment_action_required', 'payment-action-required', 'past_due', 'incomplete', 'payment_required']);
    const expired = hasToken(tokens, ['expired', 'canceled', 'cancelled', 'ended', 'inactive']);
    const seatPending = hasToken(tokens, ['seat_pending', 'seat-pending', 'pending', 'awaiting_approval', 'awaiting-approval', 'provisioning']);
    const activeEntitlement = hasToken(tokens, ['active', 'paid']) || tenantEnabled === true;
    const canonicalReady = onboardingStatus === 'ready' || onboardingComplete === true || tenantEnabled === true;
    const canonicalDisabled = onboardingStatus === 'disabled' || onboardingComplete === false || tenantEnabled === false;
    const canonicalPending = onboardingStatus === 'pending' || onboardingStatus === 'provisioning' || onboardingStatus === 'awaiting_approval' || onboardingStatus === 'awaiting-approval';

    const offerFamily = resolveOfferFamily(tokens);
    let entitlementState: HubEntitlementState;
    if (connection.configured && !connection.connected && connection.error) {
        entitlementState = 'connectionError';
    } else if (paymentActionRequired) {
        entitlementState = 'paymentActionRequired';
    } else if (expired) {
        entitlementState = 'expired';
    } else if (seatPending || canonicalPending) {
        entitlementState = 'seatPending';
    } else if (trialActive) {
        entitlementState = 'trialActive';
    } else if (canonicalReady && offerFamily !== 'unknown') {
        entitlementState = 'paidActive';
    } else if (activeEntitlement && offerFamily !== 'unknown') {
        entitlementState = 'paidActive';
    } else if (canonicalDisabled && connection.connected && connection.authenticated) {
        entitlementState = 'connectedNoPlan';
    } else if ((connection.configured || connection.authenticated) && connection.connected) {
        entitlementState = 'connectedNoPlan';
    } else if (connection.configured || connection.authenticated) {
        entitlementState = 'connecting';
    } else if (options.hubEnabled) {
        entitlementState = 'eligibleForUpgrade';
    } else {
        entitlementState = 'localOnly';
    }

    const effectiveOffer = entitlementState === 'localOnly' ? 'local_free' : offerFamily;
    const capabilities = resolveCapabilities(tokens, effectiveOffer, entitlementState === 'trialActive' || entitlementState === 'paidActive');

    return {
        entitlementState,
        offerFamily: effectiveOffer,
        capabilities,
        networkAllowed: options.networkAllowed,
        hubEnabled: options.hubEnabled,
        configured: connection.configured,
        connected: connection.connected,
        authenticated: connection.authenticated,
        ...getStatePresentation(entitlementState, effectiveOffer),
    };
}
