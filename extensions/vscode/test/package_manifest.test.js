const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const manifestPath = path.join(__dirname, '..', 'package.json');
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));

function getConfigurationProperty(key) {
    return manifest.contributes.configuration.properties[key];
}

function getCommandPaletteWhen(command) {
    const entry = manifest.contributes.menus.commandPalette.find(item => item.command === command);
    return entry && entry.when;
}

function getViewIds() {
    return manifest.contributes.views.aiir.map(entry => entry.id);
}

test('manifest uses the public website badge assets', () => {
    const extensionRoot = path.join(__dirname, '..');
    const packagedIconPath = path.join(extensionRoot, manifest.icon);
    const websiteBadgePath = path.join(__dirname, '..', '..', '..', '..', 'invariantsystems.io', 'logo-256.png');
    const activityBarIconPath = path.join(extensionRoot, 'media', 'aiir-shield.svg');

    assert.equal(fs.existsSync(packagedIconPath), true, 'packaged icon must exist');
    assert.equal(fs.existsSync(activityBarIconPath), true, 'activity bar icon must exist');

    // The website badge sync check only runs when the invariantsystems.io
    // repo is cloned alongside this repo (common in the full workspace,
    // but not required for standalone extension development).
    if (fs.existsSync(websiteBadgePath)) {
        assert.deepEqual(fs.readFileSync(packagedIconPath), fs.readFileSync(websiteBadgePath));
    }
});

test('manifest does not duplicate contributed AIIR commands', () => {
    const commandIds = manifest.contributes.commands.map(entry => entry.command);
    const uniqueIds = new Set(commandIds);

    assert.equal(uniqueIds.size, commandIds.length);
});

test('manifest defaults to local-only mode with workspace isolation opt-in', () => {
    assert.equal(getConfigurationProperty('aiir.enforceWorkspaceIsolation').default, false);
    assert.deepEqual(getConfigurationProperty('aiir.allowedWorkspaceFolders').default, []);
    assert.equal(getConfigurationProperty('aiir.strictLocalOnly').default, true);
    assert.equal(getConfigurationProperty('aiir.enableHubFeatures').default, false);
    assert.equal(getConfigurationProperty('aiir.agentModelHint').default, '');
    assert.equal(getConfigurationProperty('aiir.showAdvancedCommands').default, false);
    assert.equal(getConfigurationProperty('aiir.listener.enabled').default, false);
});

test('hub command palette entries reflect connection and capability gating', () => {
    const expectedWhenByCommand = {
        'aiir.connectHub': 'workspaceFolderCount > 0 && aiir.networkAllowed && !aiir.hubConnected',
        'aiir.disconnectHub': 'workspaceFolderCount > 0 && aiir.networkAllowed && aiir.hubConnected',
        'aiir.hubEvidencePack': 'workspaceFolderCount > 0 && aiir.networkAllowed && aiir.canUseCompliance',
        'aiir.hubLatestReport': 'workspaceFolderCount > 0 && aiir.networkAllowed && aiir.canRemoteSync',
        'aiir.hubRunAttestation': 'workspaceFolderCount > 0 && aiir.networkAllowed && aiir.canRemoteSync',
        'aiir.hubStatus': 'workspaceFolderCount > 0 && aiir.networkAllowed',
        'aiir.hubVerifyReceipt': 'workspaceFolderCount > 0 && aiir.networkAllowed && aiir.canRemoteSync',
        'aiir.openHubDashboard': 'workspaceFolderCount > 0 && aiir.networkAllowed && aiir.hubConnected',
        'aiir.signUpForHub': 'workspaceFolderCount > 0 && aiir.networkAllowed && !aiir.canRemoteSync',
    };

    for (const [command, expectedWhen] of Object.entries(expectedWhenByCommand)) {
        const when = getCommandPaletteWhen(command);
        assert.equal(when, expectedWhen);
    }
});

test('advanced command palette entries stay hidden by default until explicitly enabled', () => {
    assert.equal(getCommandPaletteWhen('aiir.securityPosture'), 'workspaceFolderCount > 0 && aiir.showAdvancedCommands');
    assert.equal(getCommandPaletteWhen('aiir.rolloutPresets'), 'workspaceFolderCount > 0 && aiir.showAdvancedCommands');
    assert.equal(getCommandPaletteWhen('aiir.advancedSettings'), 'workspaceFolderCount > 0 && aiir.showAdvancedCommands');
    assert.equal(getCommandPaletteWhen('aiir.manageRepositories'), 'workspaceFolderCount > 0 && aiir.canUseSharedRepositories && aiir.showAdvancedCommands');
    assert.equal(getCommandPaletteWhen('aiir.openSigningGuide'), 'workspaceFolderCount > 0 && aiir.showAdvancedCommands');
    assert.equal(getCommandPaletteWhen('aiir.reviewReceipt'), 'workspaceFolderCount > 0 && aiir.showAdvancedCommands');
    assert.equal(getCommandPaletteWhen('aiir.viewReviewHistory'), 'workspaceFolderCount > 0 && aiir.showAdvancedCommands');
    assert.equal(getCommandPaletteWhen('aiir.exportEvidencePack'), 'workspaceFolderCount > 0 && aiir.canUseCompliance && aiir.showAdvancedCommands');
    assert.equal(getCommandPaletteWhen('aiir.openWalkthrough'), undefined);
    assert.equal(getCommandPaletteWhen('aiir.hubBilling'), 'workspaceFolderCount > 0 && aiir.networkAllowed && aiir.showAdvancedCommands');
    assert.equal(getCommandPaletteWhen('aiir.configureMcpServer'), 'workspaceFolderCount > 0 && aiir.showAdvancedCommands');
});

test('manifest contributes the new operator pages', () => {
    const commands = new Set(manifest.contributes.commands.map(entry => entry.command));

    assert.equal(commands.has('aiir.generatePreferred'), true);
    assert.equal(commands.has('aiir.installCliNow'), true);
    assert.equal(commands.has('aiir.installSigstoreSupport'), true);
    assert.equal(commands.has('aiir.controlPanel'), true);
    assert.equal(commands.has('aiir.generateWithProvenance'), true);
    assert.equal(commands.has('aiir.hubBilling'), true);
    assert.equal(commands.has('aiir.advancedSettings'), true);
    assert.equal(commands.has('aiir.readinessCheck'), true);
    assert.equal(commands.has('aiir.securityPosture'), true);
    assert.equal(commands.has('aiir.rolloutPresets'), true);
    assert.equal(commands.has('aiir.openWalkthrough'), true);
    assert.equal(commands.has('aiir.createWorkspacePolicy'), true);
    assert.equal(commands.has('aiir.openPolicyFile'), true);
    assert.equal(commands.has('aiir.editPolicyTargets'), true);
    assert.equal(commands.has('aiir.toggleCurrentPolicyTarget'), true);
    assert.equal(commands.has('aiir.reportBug'), true);
    assert.equal(commands.has('aiir.switchRepository'), true);
});

test('manifest contributes the native AIIR sidebar views', () => {
    const viewIds = new Set(getViewIds());
    const homeView = manifest.contributes.views.aiir.find(entry => entry.id === 'aiir.homeView');
    const orderedViews = getViewIds();

    assert.equal(viewIds.has('aiir.homeView'), true);
    assert.equal(viewIds.has('aiir.receiptExplorer'), true);
    assert.equal(viewIds.has('aiir.actionsView'), false);
    assert.equal(viewIds.has('aiir.postureView'), false);
    assert.equal(homeView && homeView.type, undefined);
    assert.deepEqual(orderedViews, ['aiir.homeView', 'aiir.commitExplorer', 'aiir.receiptExplorer']);

    const commitExplorer = manifest.contributes.views.aiir.find(entry => entry.id === 'aiir.commitExplorer');
    assert.equal(commitExplorer && commitExplorer.visibility, 'collapsed');
});

test('manifest wires receipt tree context actions', () => {
    const contextMenus = manifest.contributes.menus['view/item/context'];
    const commands = contextMenus.map(entry => entry.command);
    const repairEntries = contextMenus.filter(entry => entry.command === 'aiir.repairReceipt');

    assert.match(JSON.stringify(contextMenus), /receipt-\(valid\|invalid\)/);
    assert.match(JSON.stringify(contextMenus), /receipt-file/);
    assert.equal(commands.includes('aiir.viewReceipt'), true);
    assert.equal(commands.includes('aiir.verifyFile'), true);
    assert.equal(commands.includes('aiir.openReceiptSource'), true);
    assert.equal(commands.includes('aiir.copyReceiptSummary'), true);
    assert.equal(repairEntries.some(entry => entry.when === 'view == aiir.receiptExplorer && viewItem == receipt-invalid' && entry.group === 'inline@3'), true);
    assert.equal(commands.includes('aiir.openTreeFile'), true);
});

test('manifest adds AIIR actions to the SCM title bar', () => {
    const scmTitleMenus = manifest.contributes.menus['scm/title'];
    const commands = scmTitleMenus.map(entry => entry.command);
    const generateEntry = scmTitleMenus.find(entry => entry.command === 'aiir.generatePreferred');
    const readinessEntry = scmTitleMenus.find(entry => entry.command === 'aiir.readinessCheck');
    const autoEntry = scmTitleMenus.find(entry => entry.command === 'aiir.enableAutoReceipting');

    assert.equal(commands.includes('aiir.generatePreferred'), true);
    assert.equal(commands.includes('aiir.readinessCheck'), true);
    assert.equal(commands.includes('aiir.enableAutoReceipting'), true);
    assert.equal(commands.includes('aiir.controlPanel'), false);
    assert.match(generateEntry.when, /aiir\.headReceiptMissing/);
    assert.match(generateEntry.when, /aiir\.cliAvailable/);
    assert.match(readinessEntry.when, /!aiir\.cliAvailable/);
    assert.match(autoEntry.when, /aiir\.activeAIToolDetected/);
    assert.match(autoEntry.when, /aiir\.cliAvailable/);
    assert.match(autoEntry.when, /aiir\.autoReceiptingManaged/);
});

test('manifest contributes the receipt summary copy command for everyday workflow use', () => {
    const defaultGenerateCommand = manifest.contributes.commands.find(entry => entry.command === 'aiir.generatePreferred');
    assert.ok(defaultGenerateCommand);
    assert.equal(defaultGenerateCommand.title, 'AIIR: Record Commit Activity');

    const lowLevelGenerateCommand = manifest.contributes.commands.find(entry => entry.command === 'aiir.generateReceipt');
    assert.ok(lowLevelGenerateCommand);
    assert.equal(lowLevelGenerateCommand.title, 'AIIR: Generate Receipt');

    const installCliCommand = manifest.contributes.commands.find(entry => entry.command === 'aiir.installCliNow');
    assert.ok(installCliCommand);
    assert.equal(installCliCommand.title, 'AIIR: Install CLI');

    const installSigstoreCommand = manifest.contributes.commands.find(entry => entry.command === 'aiir.installSigstoreSupport');
    assert.ok(installSigstoreCommand);
    assert.equal(installSigstoreCommand.title, 'AIIR: Install Sigstore Support');

    const readinessCommand = manifest.contributes.commands.find(entry => entry.command === 'aiir.readinessCheck');
    assert.ok(readinessCommand);
    assert.equal(readinessCommand.title, 'AIIR: Commit Status');

    const copyCommand = manifest.contributes.commands.find(entry => entry.command === 'aiir.copyReceiptSummary');
    assert.ok(copyCommand);
    assert.equal(copyCommand.title, 'AIIR: Copy Receipt Summary');

    const previewCommand = manifest.contributes.commands.find(entry => entry.command === 'aiir.previewReceiptSummary');
    assert.ok(previewCommand);
    assert.equal(previewCommand.title, 'AIIR: Preview Receipt Summary');

    const reportBugCommand = manifest.contributes.commands.find(entry => entry.command === 'aiir.reportBug');
    assert.ok(reportBugCommand);
    assert.equal(reportBugCommand.title, 'AIIR: Report a Bug');

    const when = getCommandPaletteWhen('aiir.copyReceiptSummary');
    assert.equal(when, 'workspaceFolderCount > 0');

    const verifyAllWhen = getCommandPaletteWhen('aiir.verifyAll');
    assert.equal(verifyAllWhen, 'workspaceFolderCount > 0');

    const defaultGenerateWhen = getCommandPaletteWhen('aiir.generatePreferred');
    assert.equal(defaultGenerateWhen, 'workspaceFolderCount > 0');

    const lowLevelGenerateWhen = getCommandPaletteWhen('aiir.generateReceipt');
    assert.equal(lowLevelGenerateWhen, 'false');

    const installCliWhen = getCommandPaletteWhen('aiir.installCliNow');
    assert.equal(installCliWhen, undefined);

    const installSigstoreWhen = getCommandPaletteWhen('aiir.installSigstoreSupport');
    assert.equal(installSigstoreWhen, 'workspaceFolderCount > 0');

    const copyInstallWhen = getCommandPaletteWhen('aiir.copyCliInstallCommand');
    assert.equal(copyInstallWhen, 'false');

    const openInstallTerminalWhen = getCommandPaletteWhen('aiir.openCliInstallTerminal');
    assert.equal(openInstallTerminalWhen, 'false');

    const initializeWhen = getCommandPaletteWhen('aiir.initializeRepo');
    assert.equal(initializeWhen, 'workspaceFolderCount > 0');

    const repairWhen = getCommandPaletteWhen('aiir.repairReceipt');
    assert.equal(repairWhen, 'false');

    const disableAutoWhen = getCommandPaletteWhen('aiir.disableAutoReceipting');
    assert.equal(disableAutoWhen, 'false');

    const healthWhen = getCommandPaletteWhen('aiir.healthCheck');
    assert.equal(healthWhen, 'workspaceFolderCount > 0');

    const viewReceiptWhen = getCommandPaletteWhen('aiir.viewReceipt');
    assert.equal(viewReceiptWhen, 'false');

    const provableWhen = getCommandPaletteWhen('aiir.generateWithProvenance');
    assert.equal(provableWhen, 'workspaceFolderCount > 0 && aiir.showAdvancedCommands');

    const previewWhen = getCommandPaletteWhen('aiir.previewReceiptSummary');
    assert.equal(previewWhen, 'false');

    const verifySelectionWhen = getCommandPaletteWhen('aiir.verifySelection');
    assert.equal(verifySelectionWhen, 'false');

    const verifyCborWhen = getCommandPaletteWhen('aiir.verifyCbor');
    assert.equal(verifyCborWhen, 'false');

    const verifySigstoreWhen = getCommandPaletteWhen('aiir.verifySigstore');
    assert.equal(verifySigstoreWhen, 'false');

    const controlPanelWhen = getCommandPaletteWhen('aiir.controlPanel');
    assert.equal(controlPanelWhen, 'workspaceFolderCount > 0 && aiir.showAdvancedCommands');

    const bugReportWhen = getCommandPaletteWhen('aiir.reportBug');
    assert.equal(bugReportWhen, undefined);
});

test('manifest contributes install-helper commands for first-run CLI setup', () => {
    const installCliNow = manifest.contributes.commands.find(entry => entry.command === 'aiir.installCliNow');
    const installSigstoreSupport = manifest.contributes.commands.find(entry => entry.command === 'aiir.installSigstoreSupport');
    const copyInstallCommand = manifest.contributes.commands.find(entry => entry.command === 'aiir.copyCliInstallCommand');
    const openInstallTerminal = manifest.contributes.commands.find(entry => entry.command === 'aiir.openCliInstallTerminal');

    assert.ok(installCliNow);
    assert.equal(installCliNow.title, 'AIIR: Install CLI');
    assert.ok(installSigstoreSupport);
    assert.equal(installSigstoreSupport.title, 'AIIR: Install Sigstore Support');
    assert.ok(copyInstallCommand);
    assert.equal(copyInstallCommand.title, 'AIIR: Copy CLI Install Command');
    assert.ok(openInstallTerminal);
    assert.equal(openInstallTerminal.title, 'AIIR: Open CLI Install Terminal');
    assert.equal(getCommandPaletteWhen('aiir.installCliNow'), undefined);
    assert.equal(getCommandPaletteWhen('aiir.installSigstoreSupport'), 'workspaceFolderCount > 0');
    assert.equal(getCommandPaletteWhen('aiir.copyCliInstallCommand'), 'false');
    assert.equal(getCommandPaletteWhen('aiir.openCliInstallTerminal'), 'false');
});

test('manifest keeps the AI edit tracking label tool-agnostic', () => {
    const toggleListener = manifest.contributes.commands.find(entry => entry.command === 'aiir.toggleListener');

    assert.ok(toggleListener);
    assert.equal(toggleListener.title, 'AIIR: Toggle AI Edit Tracking');
    assert.equal(getConfigurationProperty('aiir.listener.excludePatterns').description.includes('Copilot listener'), false);
});

test('manifest does not contribute duplicate commands', () => {
    const commandIds = manifest.contributes.commands.map(entry => entry.command);
    assert.equal(new Set(commandIds).size, commandIds.length);
});

test('manifest keeps activation events required for packaging', () => {
    assert.equal(Array.isArray(manifest.activationEvents), true);
    assert.equal(manifest.activationEvents.length >= 1, true);
    assert.equal(manifest.activationEvents.includes('onLanguage:json'), false);
    assert.equal(manifest.activationEvents.includes('workspaceContains:**/.aiir/**'), true);
    assert.equal(manifest.activationEvents.includes('onChatParticipant:aiir.chat'), true, 'expected onChatParticipant activation event');
});

test('manifest contributes a getting started walkthrough', () => {
    assert.equal(Array.isArray(manifest.contributes.walkthroughs), true);
    const walkthrough = manifest.contributes.walkthroughs.find(entry => entry.id === 'aiirGettingStarted');

    assert.ok(walkthrough, 'expected aiirGettingStarted walkthrough');
    assert.equal(walkthrough.steps.length, 5);
    assert.match(JSON.stringify(walkthrough.steps), /aiir\.readinessCheck/);
    assert.match(JSON.stringify(walkthrough.steps), /aiir\.generatePreferred/);
    assert.match(JSON.stringify(walkthrough.steps), /aiir\.copyReceiptSummary/);
    assert.match(JSON.stringify(walkthrough.steps), /aiir\.verifyAll/);
    assert.match(JSON.stringify(walkthrough.steps), /aiir\.enableAutoReceipting/);
    assert.match(JSON.stringify(walkthrough.steps), /copilotChat/, 'expected Copilot Chat walkthrough step');
});

test('viewsWelcome keeps receipt explorer onboarding local-first and uses valid command links', () => {
    const welcomeEntries = manifest.contributes.viewsWelcome.filter(entry => entry.view === 'aiir.receiptExplorer');
    assert.equal(welcomeEntries.length, 1);

    const entry = welcomeEntries[0];

    assert.equal(entry.when, undefined);
    assert.doesNotMatch(entry.contents, /Hub Status/);
    assert.doesNotMatch(entry.contents, /Manage Repositories/);
    assert.match(entry.contents, /Open commit status/);
    assert.match(entry.contents, /Open getting started/);
    assert.match(entry.contents, /Install CLI/);
    assert.doesNotMatch(entry.contents, /Copy install command/);
    assert.doesNotMatch(entry.contents, /command:aiir\.[^)\n]*"/);
});

test('manifest contributes compliance workflow commands', () => {
    const signingGuide = manifest.contributes.commands.find(entry => entry.command === 'aiir.openSigningGuide');
    assert.ok(signingGuide);
    assert.equal(signingGuide.title, 'AIIR: Sigstore Signing Guide');

    const switchRepository = manifest.contributes.commands.find(entry => entry.command === 'aiir.switchRepository');
    assert.ok(switchRepository);
    assert.equal(switchRepository.title, 'AIIR: Switch Repository');

    const reviewReceipt = manifest.contributes.commands.find(entry => entry.command === 'aiir.reviewReceipt');
    assert.ok(reviewReceipt);
    assert.equal(reviewReceipt.title, 'AIIR: Review Commit');

    const viewReviewHistory = manifest.contributes.commands.find(entry => entry.command === 'aiir.viewReviewHistory');
    assert.ok(viewReviewHistory);
    assert.equal(viewReviewHistory.title, 'AIIR: View Review History');

    const recordException = manifest.contributes.commands.find(entry => entry.command === 'aiir.recordException');
    assert.ok(recordException);
    assert.equal(recordException.title, 'AIIR: Record Compliance Exception');

    const exportEvidence = manifest.contributes.commands.find(entry => entry.command === 'aiir.exportEvidencePack');
    assert.ok(exportEvidence);
    assert.equal(exportEvidence.title, 'AIIR: Export Evidence Pack');

    const purgeQueue = manifest.contributes.commands.find(entry => entry.command === 'aiir.purgeProvenanceQueue');
    assert.ok(purgeQueue);
    assert.equal(purgeQueue.title, 'AIIR: Purge Provenance Queue');
});

test('compliance settings default to safe off-by-default values', () => {
    assert.equal(getConfigurationProperty('aiir.regulatedMode').default, false);
    assert.equal(getConfigurationProperty('aiir.injectTrailers').default, false);
    assert.equal(getConfigurationProperty('aiir.lockPreset').default, '');
    assert.equal(getConfigurationProperty('aiir.provenanceRetainPrompts').default, false);
    assert.equal(getConfigurationProperty('aiir.provenanceRetentionDays').default, 0);
});

test('recordException command palette is gated on regulatedMode', () => {
    const when = getCommandPaletteWhen('aiir.recordException');
    assert.equal(when, 'workspaceFolderCount > 0 && aiir.regulatedMode && aiir.showAdvancedCommands');
});

test('purgeProvenanceQueue command palette is gated on showAdvancedCommands', () => {
    const when = getCommandPaletteWhen('aiir.purgeProvenanceQueue');
    assert.equal(when, 'workspaceFolderCount > 0 && aiir.showAdvancedCommands');
});

test('shared-repository and compliance exports stay behind Hub capabilities', () => {
    const manageRepositoriesWhen = getCommandPaletteWhen('aiir.manageRepositories');
    assert.equal(manageRepositoriesWhen, 'workspaceFolderCount > 0 && aiir.canUseSharedRepositories && aiir.showAdvancedCommands');

    const switchRepositoryWhen = getCommandPaletteWhen('aiir.switchRepository');
    assert.equal(switchRepositoryWhen, 'workspaceFolderCount > 1 && aiir.multipleAccessibleRepositories');

    const exportEvidencePackWhen = getCommandPaletteWhen('aiir.exportEvidencePack');
    assert.equal(exportEvidencePackWhen, 'workspaceFolderCount > 0 && aiir.canUseCompliance && aiir.showAdvancedCommands');

    const receiptExplorerTitleMenus = manifest.contributes.menus['view/title'];
    const generateMissingReceiptsTitleEntry = receiptExplorerTitleMenus.find(entry => entry.command === 'aiir.generateMissingReceipts');
    const manageRepositoriesTitleEntry = receiptExplorerTitleMenus.find(entry => entry.command === 'aiir.manageRepositories');
    const receiptSwitchRepositoryTitleEntry = receiptExplorerTitleMenus.find(entry => entry.command === 'aiir.switchRepository' && entry.when.includes('view == aiir.receiptExplorer'));
    const homeSwitchRepositoryTitleEntry = receiptExplorerTitleMenus.find(entry => entry.command === 'aiir.switchRepository' && entry.when.includes('view == aiir.homeView'));
    const commitSwitchRepositoryTitleEntry = receiptExplorerTitleMenus.find(entry => entry.command === 'aiir.switchRepository' && entry.when.includes('view == aiir.commitExplorer'));
    assert.ok(generateMissingReceiptsTitleEntry);
    assert.equal(generateMissingReceiptsTitleEntry.when, 'view == aiir.commitExplorer && aiir.showAdvancedCommands');
    assert.ok(manageRepositoriesTitleEntry);
    assert.equal(manageRepositoriesTitleEntry.when, 'view == aiir.receiptExplorer && aiir.canUseSharedRepositories && aiir.showAdvancedCommands');
    assert.ok(receiptSwitchRepositoryTitleEntry);
    assert.equal(receiptSwitchRepositoryTitleEntry.when, 'view == aiir.receiptExplorer && aiir.multipleAccessibleRepositories');
    assert.ok(homeSwitchRepositoryTitleEntry);
    assert.equal(homeSwitchRepositoryTitleEntry.when, 'view == aiir.homeView && aiir.multipleAccessibleRepositories');
    assert.ok(commitSwitchRepositoryTitleEntry);
    assert.equal(commitSwitchRepositoryTitleEntry.when, 'view == aiir.commitExplorer && aiir.multipleAccessibleRepositories');

    const scmTitleMenus = manifest.contributes.menus['scm/title'];
    const scmSwitchRepositoryEntry = scmTitleMenus.find(entry => entry.command === 'aiir.switchRepository');
    assert.ok(scmSwitchRepositoryEntry);
    assert.equal(scmSwitchRepositoryEntry.when, 'scmProvider == git && aiir.multipleAccessibleRepositories');
});

test('reviewReceipt appears in receipt explorer context menu', () => {
    const contextEntries = manifest.contributes.menus['view/item/context'];
    const reviewEntry = contextEntries.find(entry => entry.command === 'aiir.reviewReceipt');
    assert.ok(reviewEntry, 'expected reviewReceipt in view/item/context menu');
    assert.match(reviewEntry.when, /receipt-/);
    assert.match(reviewEntry.when, /aiir\.showAdvancedCommands/);
});

// ── Gap 1: Chat participant ──────────────────────────────────────────

test('manifest contributes an @aiir chat participant with slash commands', () => {
    const participants = manifest.contributes.chatParticipants;
    assert.ok(Array.isArray(participants), 'expected chatParticipants array');
    assert.equal(participants.length, 1);

    const aiir = participants[0];
    assert.equal(aiir.id, 'aiir.chat');
    assert.equal(aiir.name, 'aiir');
    assert.equal(aiir.fullName, 'AIIR');
    assert.equal(aiir.isSticky, false);

    const commandNames = aiir.commands.map(c => c.name);
    assert.deepEqual(commandNames, ['receipt', 'verify', 'stats', 'explain', 'policy']);
});

// ── Gap 2: Language model tools ──────────────────────────────────────

test('manifest contributes language model tools for Copilot Chat agentic use', () => {
    const tools = manifest.contributes.languageModelTools;
    assert.ok(Array.isArray(tools), 'expected languageModelTools array');
    assert.equal(tools.length, 5);

    const toolNames = tools.map(t => t.name);
    assert.deepEqual(toolNames, [
        'aiir_receipt',
        'aiir_verify',
        'aiir_stats',
        'aiir_explain',
        'aiir_policy_check',
    ]);

    for (const tool of tools) {
        assert.ok(tool.displayName, `expected displayName on ${tool.name}`);
        assert.ok(tool.modelDescription, `expected modelDescription on ${tool.name}`);
        assert.ok(tool.tags && tool.tags.length > 0, `expected tags on ${tool.name}`);
        assert.ok(tool.inputSchema, `expected inputSchema on ${tool.name}`);
        assert.equal(tool.inputSchema.type, 'object');
    }
});

// ── Gap 3: Engine version ────────────────────────────────────────────

test('manifest requires VS Code 1.95+ for chat participant and language model tool APIs', () => {
    const engine = manifest.engines.vscode;
    const match = engine.match(/\^(\d+)\.(\d+)/);
    assert.ok(match, 'expected semver engine constraint');
    const major = parseInt(match[1], 10);
    const minor = parseInt(match[2], 10);
    assert.ok(major >= 1 && minor >= 95, `expected engine >= 1.95, got ${major}.${minor}`);
});

// ── Gap 4: AI category and companion packaging ───────────────────────

test('manifest includes AI category for marketplace discovery', () => {
    assert.ok(manifest.categories.includes('AI'), 'expected AI in categories');
    assert.ok(manifest.categories.includes('SCM Providers'), 'expected SCM Providers preserved');
});

test('manifest uses extensionPack for the optional github.copilot-chat companion', () => {
    assert.ok(Array.isArray(manifest.extensionPack), 'expected extensionPack array');
    assert.ok(manifest.extensionPack.includes('github.copilot-chat'), 'expected copilot-chat in extensionPack');
    assert.ok(
        !Array.isArray(manifest.extensionDependencies) || !manifest.extensionDependencies.includes('github.copilot-chat'),
        'expected copilot-chat to stay optional for the core workflow'
    );
});

// ── Gap 7: Chat participant detection ────────────────────────────────

test('manifest declares chatParticipantDetection for organic discoverability', () => {
    const detection = manifest.chatParticipantDetection;
    assert.ok(detection, 'expected chatParticipantDetection object');
    assert.ok(Array.isArray(detection.participants), 'expected participants array');

    const aiir = detection.participants.find(p => p.id === 'aiir.chat');
    assert.ok(aiir, 'expected aiir.chat participant detection entry');
    assert.ok(Array.isArray(aiir.keywords), 'expected keywords array');
    assert.ok(aiir.keywords.includes('aiir'), 'expected aiir in keywords');
    assert.ok(aiir.keywords.includes('receipt'), 'expected receipt in keywords');
});

// ── Workspace Trust ──────────────────────────────────────────────────

test('manifest declares workspace trust capabilities for enterprise deployments', () => {
    assert.ok(manifest.capabilities, 'expected capabilities block');
    const untrusted = manifest.capabilities.untrustedWorkspaces;
    assert.ok(untrusted, 'expected untrustedWorkspaces capability');
    assert.equal(untrusted.supported, 'limited', 'expected limited support in untrusted workspaces');
    assert.ok(untrusted.description, 'expected description for untrusted workspace behaviour');

    const virtual = manifest.capabilities.virtualWorkspaces;
    assert.ok(virtual, 'expected virtualWorkspaces capability');
    assert.equal(virtual.supported, false, 'expected no support for virtual workspaces');
});

// ── AI Blame command ─────────────────────────────────────────────────

test('manifest declares toggleAIBlame command', () => {
    const commands = manifest.contributes.commands;
    const blame = commands.find(c => c.command === 'aiir.toggleAIBlame');
    assert.ok(blame, 'expected aiir.toggleAIBlame command');
    assert.match(blame.title, /blame/i, 'expected blame in title');
});
