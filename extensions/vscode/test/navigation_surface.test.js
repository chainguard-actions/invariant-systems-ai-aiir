const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const extensionSourcePath = path.join(__dirname, '..', 'src', 'extension.ts');
const homeStateSourcePath = path.join(__dirname, '..', 'src', 'home_state.ts');
const cliContractSourcePath = path.join(__dirname, '..', 'src', 'cli_contract.ts');
const languageModelBridgeSourcePath = path.join(__dirname, '..', 'src', 'language_model_bridge.ts');
const repositorySetupStateSourcePath = path.join(__dirname, '..', 'src', 'repository_setup_state.ts');
const srcDir = path.join(__dirname, '..', 'src');
const extensionSource = Array.from(new Set([
    ...fs.readdirSync(srcDir)
        .filter(name => name.endsWith('.ts'))
        .map(name => path.join(srcDir, name)),
    extensionSourcePath,
    homeStateSourcePath,
    cliContractSourcePath,
    languageModelBridgeSourcePath,
    repositorySetupStateSourcePath,
]))
    .map(filePath => fs.readFileSync(filePath, 'utf8'))
    .join('\n');

function expectSource(pattern, message) {
    assert.match(extensionSource, pattern, message);
}

test('extension registers the simplified AIIR sidebar views', () => {
    expectSource(/createTreeView\('aiir\.homeView'/, 'expected home tree view registration');
    expectSource(/createTreeView\('aiir\.receiptExplorer'/, 'expected receipt explorer sidebar view');
});

test('home sidebar is a native tree view with trust state items', () => {
    expectSource(/class HomeProvider implements vscode\.TreeDataProvider<vscode\.TreeItem>/, 'expected native tree data provider');
    expectSource(/getChildren\(element\?: vscode\.TreeItem\)/, 'expected tree data children method');
    expectSource(/getTreeItem\(element: vscode\.TreeItem\)/, 'expected tree item accessor');
    expectSource(/onDidChangeTreeData/, 'expected tree data change event for refresh');
    expectSource(/export type HomeState = 'no-workspace' \| 'access-blocked' \| 'cli-missing' \| 'not-initialized' \| 'ready-no-receipts' \| 'head-missing' \| 'regulated-incomplete' \| 'healthy' \| 'failing'/, 'expected explicit home states');
    expectSource(/resolveHomeState\(/, 'expected extracted home state resolver');
    expectSource(/Open a folder to get started/, 'expected no-repo state');
    expectSource(/Repository hidden by workspace policy/, 'expected blocked-access home title');
    expectSource(/This commit needs the AIIR CLI/, 'expected CLI-missing state');
    expectSource(/commandId: 'aiir\.installCliNow'/, 'expected missing-CLI state to surface one-click install');
    expectSource(/This commit needs repository setup/, 'expected repo initialization state');
    expectSource(/This commit is ready to record/, 'expected ready-without-receipts state');
    expectSource(/Latest commit needs a record/, 'expected head-missing state to drive current-commit coverage');
    expectSource(/Current commit activity is recorded/, 'expected healthy steady state');
    expectSource(/commandId: 'aiir\.generatePreferred'/, 'expected smart default generate action');
    expectSource(/Check Receipts/, 'expected check receipts action');
    expectSource(/Open Folder/, 'expected open folder action for no-repo state');
    expectSource(/Current repository status/, 'expected home tree to summarize repository state in one compact row');
    expectSource(/Green means ready, yellow means usable but incomplete, and red means blocked or broken\./, 'expected home summary tooltip to explain the dot semantics');
    expectSource(/function getHomeHealthDots\(/, 'expected extracted health-dot builder for the home tree');
    expectSource(/label: 'Repo'/, 'expected repo health dot');
    expectSource(/label: 'This Commit'/, 'expected current-commit health dot');
    expectSource(/label: 'Proof'/, 'expected proof health dot');
    expectSource(/label: 'Auto'/, 'expected automation health dot');
    expectSource(/new vscode\.ThemeIcon\('circle-filled', new vscode\.ThemeColor\(/, 'expected color-coded dot icons for home health items');
    expectSource(/stateLabel: 'needs record'/, 'expected record dot to call out missing commit coverage');
    expectSource(/stateLabel: 'needs repair'/, 'expected verify dot to call out invalid receipts');
    expectSource(/stateLabel: 'manual'/, 'expected auto dot to distinguish manual mode from managed automation');
    expectSource(/Commit Status/, 'expected home tree to expose commit status action');
    expectSource(/Health Check/, 'expected home tree to expose health check action');
});

test('cli install uses a managed user-local path instead of failing system pip defaults', () => {
    expectSource(/function getManagedCliInstallDir\(\)/, 'expected managed CLI install directory helper');
    expectSource(/function getManagedCliPath\(\)/, 'expected managed CLI executable helper');
    expectSource(/function getManagedPipPath\(\)/, 'expected managed CLI pip helper');
    expectSource(/function getConfiguredCliPathSetting\(\): string/, 'expected helper for the raw CLI path setting');
    expectSource(/return fs\.existsSync\(managedCliPath\) \? managedCliPath : configured;/, 'expected CLI path to fall back to a managed local install');
    expectSource(/python3 -m venv/, 'expected Linux and macOS install guidance to use a dedicated venv');
    expectSource(/registerCommand\('aiir\.installCliNow'/, 'expected one-click install command registration');
    expectSource(/async function installSigstoreSupport\(output: vscode\.OutputChannel\): Promise<string>/, 'expected one-click Sigstore setup helper');
    expectSource(/registerCommand\('aiir\.installSigstoreSupport'/, 'expected Sigstore setup command registration');
    expectSource(/aiir\[sigstore\]/, 'expected Sigstore setup to install optional signing dependencies');
    expectSource(/await updateAiirSetting\('cliPath', cliPath\);/, 'expected successful install to persist the managed CLI path');
});

test('hubBaseUrl is persisted at global scope to match its trusted (global-only) read', () => {
    // Security: getTrustedHubBaseUrlSetting reads hubBaseUrl only from global
    // scope, so the write must target global too or Connect-to-Hub can never
    // persist (and a workspace value must never be trusted).
    expectSource(/getTrustedHubBaseUrlSetting/, 'expected a global-only trusted hubBaseUrl reader');
    expectSource(/key === 'cliPath' \|\| key === 'hubBaseUrl'/, 'expected hubBaseUrl writes to use global ConfigurationTarget like cliPath');
});

test('default generation prefers provenance and falls back safely', () => {
    expectSource(/type GenerateCommandId = 'aiir\.generatePreferred'/, 'expected shared generate command id type');
    expectSource(/function canUseProvenanceGeneration\(/, 'expected provenance eligibility helper');
    expectSource(/return isPathInside\(folder\.uri\.fsPath, editor\.document\.uri\.fsPath\);/, 'expected provenance eligibility to check whether the active editor lives inside the selected repository');
    expectSource(/registerCommand\('aiir\.generatePreferred'/, 'expected smart default generate command registration');
    expectSource(/if \(!await deps\.isRepositoryInitialized\(folder\)\) \{[\s\S]*await vscode\.commands\.executeCommand\('aiir\.initializeRepo', folder\.uri\);[\s\S]*return;[\s\S]*\}/, 'expected smart generate to auto-initialize missing repo scaffolding before recording');
    expectSource(/canUseProvenanceGeneration\(folder\) \? 'aiir\.generateWithProvenance' : 'aiir\.generateReceipt'/, 'expected smart generate routing');
});

test('home does not treat a missing HEAD receipt as fully covered', () => {
    expectSource(/if \(input\.receiptsExist && !input\.headCovered && input\.cliAvailable && input\.repoInitialized\) \{[\s\S]*return 'head-missing';[\s\S]*\}/, 'expected a dedicated head-missing state when historical receipts exist but HEAD is uncovered');
    expectSource(/case 'head-missing':[\s\S]*label: 'Record Commit Activity'/, 'expected head-missing state to prioritize the default record action');
    expectSource(/case 'head-missing':[\s\S]*headline: 'Latest commit needs a record'/, 'expected head-missing card headline');
    expectSource(/case 'head-missing':[\s\S]*return 'generate';/, 'expected head-missing state to stay on the generate trust vertex');
});

test('home renders directly from trust state without intermediate layers', () => {
    expectSource(/this\.cachedState = await getResolvedTrustState\(this\.explorer\);/, 'expected refresh to call getResolvedTrustState directly');
    expectSource(/const card = trustState\.primaryCard;/, 'expected tree items to read the primary card from trust state');
    expectSource(/const cachedRecord = explorer\.getReceiptByUri\(candidate\);/, 'expected cached receipt fallback for receipt actions');
    expectSource(/getReceiptByUri\(uri: vscode\.Uri, folder\?: vscode\.WorkspaceFolder\)/, 'expected explorer lookup by receipt URI');
});

test('home refreshes on editor change without manual folder tracking', () => {
    expectSource(/vscode\.window\.onDidChangeActiveTextEditor\(async editor => \{[\s\S]*await homeProvider\.refresh\(\);/s, 'expected Home to refresh when the active editor changes');
    expectSource(/this\.cachedState = await getResolvedTrustState\(this\.explorer\);/, 'expected refresh to delegate folder resolution entirely to getResolvedTrustState');
});

test('home retargets to the active repository and reacts to .aiir scaffolding changes', () => {
    expectSource(/vscode\.window\.onDidChangeActiveTextEditor\(async editor => \{[\s\S]*rememberWorkspaceFolder\(editor \? vscode\.workspace\.getWorkspaceFolder\(editor\.document\.uri\) : undefined\);[\s\S]*await homeProvider\.refresh\(\);/s, 'expected Home to remember the active editor repository before refreshing');
    expectSource(/aiirStateWatcher = vscode\.workspace\.createFileSystemWatcher\(new vscode\.RelativePattern\(folder, '\.aiir\/\*\*'\)\)/, 'expected watcher coverage for .aiir scaffolding changes');
    expectSource(/createReceiptWatcher\(explorer, statusBar, diagnosticCollection, updateSidebarChrome, async \(\) => \{[\s\S]*await homeProvider\.refresh\(\);/s, 'expected receipt watcher to refresh the Home tree when repo state changes');
});

test('local receipt generation can declare a model hint', () => {
    expectSource(/function getAgentModelHint\(\): string/, 'expected agent model hint helper');
    expectSource(/args\.push\('--agent-model', modelHint\);/, 'expected model hints to flow into local receipt generation');
    expectSource(/const active = detectEditorAITools\(\)\.filter\(t => t\.isActive\);/, 'expected agent attestation to use only active AI tools');
    expectSource(/args\.push\('--agent-context', 'ide:active'\);/, 'expected agent context to describe active tools only');
    expectSource(/function buildToolContextArgs\(\): string\[\]/, 'expected companion tool-context CLI arg helper');
    expectSource(/getExtension\('eamodio\.gitlens'\)/, 'expected GitLens companion extension detection');
    expectSource(/feature: 'companion_extension'/, 'expected GitLens to be recorded as companion context rather than agent authorship');
    expectSource(/'--tool-context', JSON\.stringify\(toolContext\)/, 'expected GitLens companion context to be serialized into CLI args');
});

test('provable mode registers an explicit AIIR-owned generation command', () => {
    expectSource(/registerCommand\('aiir\.generateWithProvenance'/, 'expected provable-mode command registration');
    expectSource(/buildEditorProvenanceArgs\(\)/, 'expected receipt generation to include editor provenance args');
    expectSource(/Commit these changes, then record a proof or rely on managed auto-receipting/, 'expected provable-mode post-apply guidance');
    expectSource(/vscode\.LanguageModelChatMessage\.User\(/, 'expected provable mode to use the public language model API');
    expectSource(/if \(!isPathInside\(folder\.uri\.fsPath, editor\.document\.uri\.fsPath\)\) \{[\s\S]*The active editor is not inside the selected repository\./, 'expected provable mode to treat the repository as the containment root');
    expectSource(/if \(!isPathInside\(folder\.uri\.fsPath, absolutePath\)\) \{[\s\S]*Operation path escapes the workspace/, 'expected provable edits to validate create-file paths against the workspace root');
});

test('managed auto-receipting carries queued editor provenance into receipt generation', () => {
    expectSource(/const allArgs = \[\.\.\.args, \.\.\.buildEditorProvenanceArgs\(\), \.\.\.agentArgs, \.\.\.toolContextArgs, \.\.\.trailerArgs\];/, 'expected managed hook generation to include editor provenance and companion tool context');
    expectSource(/AIIR provable mode needs the active file saved before it can hash and queue deterministic edits/, 'expected provable mode to guard hashing on saved content');
    expectSource(/editor_provenance\.jsonl/, 'expected provable queue infrastructure to be referenced in extension code');
});

test('receipt viewer surfaces companion tool context separately from agent attestation', () => {
    expectSource(/getToolContext\(/, 'expected receipt metadata helper for companion tool context');
    expectSource(/getToolContextSummary\(/, 'expected receipt metadata summary for companion tool context');
    expectSource(/Companion Tool Context/, 'expected receipt viewer block for companion tool context');
    expectSource(/key === 'agent_attestation' \|\| key === 'sigstore' \|\| key === 'editor_provenance' \|\| key === 'tool_context'/, 'expected viewer to avoid rendering tool_context twice');
});

test('passive provenance captures file changes when AI tools are active', () => {
    expectSource(/async function capturePassiveProvenance\(document: vscode\.TextDocument\)/, 'expected passive provenance capture function');
    expectSource(/registerCommand\('aiir\.configureProvenanceQueue'/, 'expected provenance queue configuration command');
    expectSource(/function seedContentTrackerForFolder\(folder: vscode\.WorkspaceFolder\): void \{/, 'expected provenance queue setup to seed tracked file hashes for open documents');
    expectSource(/if \(!isPathInside\(folder\.uri\.fsPath, document\.uri\.fsPath\)\) \{[\s\S]*continue;/, 'expected provenance seeding to keep the workspace folder as the containment root');
    expectSource(/const activeTool = detectEditorAITools\(\)\.find\(t => t\.isActive\)/, 'expected passive capture to check for active AI tools');
    expectSource(/command: 'passive-capture'/, 'expected passive-capture command type');
    expectSource(/source: 'passive-capture'/, 'expected passive-capture source type');
    expectSource(/onDidSaveTextDocument\(async document =>/, 'expected save listener for passive provenance');
    expectSource(/onDidOpenTextDocument\(document =>/, 'expected open listener for content tracking');
    expectSource(/contentTracker\.set\(document\.uri\.fsPath, sha256Text\(document\.getText\(\)\)\)/, 'expected content hash tracking on open');
    expectSource(/const selectedFolder = this\.cachedFolder \|\| getDefaultWorkspaceFolderCandidate\(\);/, 'expected Home passive provenance indicator to use the selected workspace folder');
    expectSource(/config\.get<boolean>\('listener\.enabled', false\)/, 'expected passive listener to stay off until explicitly enabled');
});

test('initialization applies safe workspace settings and direct policy-file access', () => {
    expectSource(/async function applySafeWorkspaceSettings\(/, 'expected safe workspace settings helper');
    expectSource(/Initialize \$\{accessibleFolders.length\} repositories with the standard safe workspace policy/, 'expected multi-root safe initialization scope');
    expectSource(/async function ensureWorkspaceBaselinePolicy\(/, 'expected baseline workspace policy helper');
    expectSource(/async function createOrEnsureWorkspacePolicy\(/, 'expected shared workspace policy creation helper');
    expectSource(/await runCommand\(getCliPath\(\), args, folder\.uri\.fsPath, output\);[\s\S]*await ensureProvableQueueInfrastructure\(folder, \{ allowCreateAiir: false, promptOnCreateAiir: false \}\);/s, 'expected initialization to configure provenance queue support immediately after init');
    expectSource(/--policy-init/, 'expected policy-only CLI path for initialized repositories');
    expectSource(/async function getWorkspacePolicyState\(/, 'expected policy workspace target reader');
    expectSource(/const starterReceipts: Array<\{ folder: vscode\.WorkspaceFolder; receipt\?: ReceiptRecord \}> = \[\];/, 'expected initialization to track starter receipts');
    expectSource(/await generateReceiptForFolder\(folder\);/, 'expected initialization to generate starter receipts');
    expectSource(/registerCommand\('aiir\.createWorkspacePolicy'/, 'expected create workspace policy command');
    expectSource(/registerCommand\('aiir\.openPolicyFile'/, 'expected open policy file command');
    expectSource(/registerCommand\('aiir\.editPolicyTargets'/, 'expected edit policy targets command');
    expectSource(/registerCommand\('aiir\.toggleCurrentPolicyTarget'/, 'expected current policy target toggle command');
    expectSource(/showQuickPick\([\s\S]*canPickMany: true[\s\S]*Select the repositories that should stay enabled in this workspace policy/s, 'expected multi-select policy target editor');
    expectSource(/Open Policy File/, 'expected policy file link in advanced settings');
    expectSource(/Create Policy File/, 'expected create policy file affordance in setup surfaces');
    expectSource(/Open Workspace Settings JSON/, 'expected settings-file affordance in setup surfaces');
    expectSource(/Edit Workspace Targets/, 'expected policy target edit link in advanced settings');
    expectSource(/Enabled and disabled repositories currently recorded in the repo-local AIIR policy file/, 'expected advanced settings workspace target list');
});

test('home stays focused on the core loop without intermediate snapshot layers', () => {
    expectSource(/async function hasAiirGitHubActionWorkflow\(/, 'expected GitHub Action detection helper');
    expectSource(/const card = trustState\.primaryCard;/, 'expected Home tree to read the primary card directly from trust state');
    expectSource(/cachedState\?: ResolvedTrustState;/, 'expected Home to cache trust state for tree rendering');
    expectSource(/cachedFolder\?: vscode\.WorkspaceFolder;/, 'expected Home to cache the resolved folder for consistent tree items');
    expectSource(/async refresh\(target\?: vscode\.Uri\)/, 'expected Home refresh to accept an optional target URI');
    expectSource(/receiptTreeView\.onDidChangeSelection\(async event => \{[\s\S]*homeProvider\.getCurrentFolderPath\(\) === folder\.uri\.fsPath[\s\S]*await homeProvider\.refresh\(folder\.uri\);/s, 'expected receipt explorer selection to retarget Home only when the repository changes');
    expectSource(/registerCommand\('aiir\.viewReceipt'[\s\S]*await homeProvider\.refresh\(record\.uri\);/s, 'expected opening a receipt to retarget Home to the receipt repository');
});

test('rollout presets include public guidance for CI signing without changing local defaults', () => {
    expectSource(/id: 'ci-sign-when-supported'/, 'expected CI signing guidance preset');
    expectSource(/title: 'CI Signing When Supported'/, 'expected CI signing preset title');
    expectSource(/actionLabel: 'Open Guidance'/, 'expected guidance-first action label');
    expectSource(/This preset does not change local workspace settings/, 'expected non-mutating preset note');
    expectSource(/preset\.id === 'ci-sign-when-supported'/, 'expected special handling for CI signing guidance');
    expectSource(/Copy CI Command/, 'expected CI signing guidance action');
    expectSource(/aiir --sign --in-toto --output \.receipts\//, 'expected copied CI signing command example');
});

test('advanced workflow commands remain available via command palette', () => {
    expectSource(/registerCommand\('aiir\.controlPanel'/, 'expected advanced tools command registration');
    expectSource(/registerCommand\('aiir\.securityPosture'/, 'expected security posture command registration');
    expectSource(/registerCommand\('aiir\.rolloutPresets'/, 'expected deployment presets command registration');
    expectSource(/registerCommand\('aiir\.advancedSettings'/, 'expected advanced settings command registration');
    expectSource(/registerCommand\('aiir\.createWorkspacePolicy'/, 'expected create policy command registration');
    expectSource(/registerCommand\('aiir\.reportBug'/, 'expected bug report command registration');
    expectSource(/registerCommand\('aiir\.openWalkthrough'/, 'expected walkthrough command registration');
});

test('hub access is normalized into entitlement states and hosted signup handoff', () => {
    expectSource(/export type HubEntitlementState =/, 'expected shared Hub entitlement state model');
    expectSource(/\['tenant', 'tier'\]/, 'expected Hub state resolution to use the canonical Foundation session tier field');
    expectSource(/\['tenant', 'enabled'\]/, 'expected Hub state resolution to use the canonical Foundation tenant enabled flag');
    expectSource(/\['onboarding_complete'\]/, 'expected Hub state resolution to use the canonical onboarding completion flag');
    expectSource(/onboardingStatus === 'ready'/, 'expected Hub state resolution to treat canonical onboarding ready as active entitlement');
    expectSource(/if \(typeof entry === 'boolean' && entry\) \{[\s\S]*tokens\.add\(key\.trim\(\)\.toLowerCase\(\)\);/s, 'expected token collection to treat only truthy boolean keys as evidence');
    expectSource(/setContext', 'aiir\.hubState', resolvedHub\.entitlementState\)/, 'expected normalized Hub state context key');
    expectSource(/setContext', 'aiir\.canRemoteSync', resolvedHub\.capabilities\.remoteReceiptSync\)/, 'expected Hub capability context key for remote sync');
    expectSource(/registerCommand\('aiir\.openHostedHubSignup'/, 'expected hosted Hub signup command');
    expectSource(/await vscode\.env\.openExternal\(vscode\.Uri\.parse\(getHostedHubSignupUrl\(\)\)\);/, 'expected browser handoff for hosted signup');
});

test('home sidebar surfaces normalized Hub state without displacing the local-first loop', () => {
    expectSource(/private cachedHubState\?: ResolvedHubState;/, 'expected Home to cache resolved Hub state');
    expectSource(/this\.cachedHubState = await this\.resolveHubState\(\);/, 'expected Home refresh to resolve Hub state');
    expectSource(/const hubState = this\.cachedHubState;/, 'expected Home tree to keep normalized Hub state available during render');
    expectSource(/const hubItem = new vscode\.TreeItem\(`Hub: \$\{hubState\.stateLabel\}`/, 'expected Home tree to expose Hub state directly');
    expectSource(/hubItem\.command = \{ command: hubState\.primaryActionCommandId, title: hubState\.primaryActionLabel \};/, 'expected Home Hub row to route through the normalized primary action');
});

test('pending-action recovery includes direct CLI install helpers', () => {
    expectSource(/'Install CLI',\s*'Copy Install Command',\s*'Open Terminal'/, 'expected pending-action recovery to offer one-click install before copy and terminal fallbacks');
    expectSource(/Copy Install Command/, 'expected copy install option in recovery flow');
    expectSource(/Open Terminal/, 'expected open terminal option in recovery flow');
    expectSource(/async function copyCliInstallCommand\(\): Promise<void>/, 'expected copy install helper');
    expectSource(/async function installCliNow\(output: vscode\.OutputChannel\): Promise<string>/, 'expected one-click CLI install helper');
    expectSource(/async function openCliInstallTerminal\(\): Promise<void>/, 'expected terminal install helper');
    expectSource(/vscode\.window\.onDidChangeWindowState\(async state => \{[\s\S]*getPendingAction\(\)/s, 'expected pending action refresh on focus');
    expectSource(/vscode\.window\.onDidCloseTerminal\(async \(\) => \{[\s\S]*getPendingAction\(\)/s, 'expected pending action refresh after terminal closes');
});

test('advanced commands stay opt-in while the default path stays single-seat and core-loop focused', () => {
    expectSource(/function getShowAdvancedCommands\(\): boolean/, 'expected advanced command visibility helper');
    expectSource(/setContext', 'aiir\.showAdvancedCommands', getShowAdvancedCommands\(\)/, 'expected advanced command context key');
    expectSource(/Open Getting Started/, 'expected walkthrough-first onboarding copy instead of advanced tooling');
    expectSource(/Install CLI/, 'expected one-click install path in onboarding surfaces');
    expectSource(/Configure Provenance/, 'expected readiness flow to offer provenance configuration before generation when queue support is missing');
    expectSource(/Generate With Provenance/, 'expected first-run surfaces to keep deterministic generation as a secondary advanced path');
});

test('extension exposes a public bug-report flow', () => {
    expectSource(/function getBugReportUrl\(extensionVersion: string\): string \{/, 'expected bug report URL helper');
    expectSource(/issues\/new\?/, 'expected GitHub issue creation URL');
    expectSource(/registerCommand\('aiir\.reportBug'/, 'expected report bug command registration');
    expectSource(/vscode\.env\.openExternal\(vscode\.Uri\.parse\(getBugReportUrl\(/, 'expected report bug command to open the issue flow');
});

test('webview command bridge handles clicks even when inline command wiring is skipped', () => {
    expectSource(/const fallbackTarget = !target && event\.target instanceof Element \? event\.target\.closest\('\[onclick\]'\) : null;/, 'expected click handler fallback for panels whose inline command wiring did not run');
    expectSource(/const inlineCommand = datasetCommand \? undefined : parseInlineCommand\(commandTarget\.getAttribute\('onclick'\)\);/, 'expected inline onclick parsing fallback when data attributes are missing');
    expectSource(/} else if \(inlineCommand\?\.args\) \{[\s\S]*args = inlineCommand\.args;/, 'expected parsed inline arguments to flow into command execution');
});

test('receipt explorer groups recent commits into action-oriented sections and compact empty repos', () => {
    expectSource(/RECEIPT_RECENT_LIMIT/, 'expected recent receipt cap constant');
    expectSource(/buildRecentList/, 'expected flat recent list builder');
    expectSource(/function getActiveReceiptRecords\(records: ReceiptRecord\[\]\): ReceiptRecord\[\]/, 'expected helper that keeps the newest receipt per commit active');
    expectSource(/const activeRecords = getActiveReceiptRecords\(records\);[\s\S]*const sorted = \[\.\.\.activeRecords\]\.sort\(compareReceipts\);/s, 'expected explorer sections to render from active per-commit receipts');
    expectSource(/function getActiveReceiptForCommit\(records: ReceiptRecord\[\], commitSha: string\): ReceiptRecord \| undefined/, 'expected commit lookups to resolve the active receipt for that commit');
    expectSource(/return \[\.\.\.getActiveReceiptRecords\(this\.getReceipts\(folder\)\)\]\.sort\(compareReceiptFreshness\)\[0\];/, 'expected latest receipt lookup to prefer freshest active receipts over historical failures');
    expectSource(/buildEmptyRepositoryItems/, 'expected empty repository handling in explorer');
    expectSource(/Set up receipts/, 'expected single setup action for empty repos');
    expectSource(/Needs Attention/, 'expected attention-first receipt section');
    expectSource(/Current Commit/, 'expected current commit section');
    expectSource(/Recent History|Compliant/, 'expected compliant or history section');
    expectSource(/earlier commit/, 'expected earlier history link for overflow');
    expectSource(/getCurrentBranchName/, 'expected local git branch enrichment');
    expectSource(/new ReceiptActionItem\('Open Pretty Receipt',/, 'expected explicit pretty receipt action');
    expectSource(/new ReceiptActionItem\('Repair Failed Receipt', 'Choose the lowest-friction recovery path for this invalid receipt'/, 'expected invalid receipts to expose repair directly in the explorer');
    expectSource(/new ReceiptActionItem\('Open Receipt JSON',/, 'expected explicit raw receipt action');
    expectSource(/new ReceiptActionItem\('Copy Markdown Summary', 'Copy a PR-ready Markdown receipt summary', 'copy', 'aiir\.copyReceiptSummary'/, 'expected explicit markdown receipt summary copy action');
    expectSource(/new ReceiptActionItem\('Browse Attested Diffs', 'Open the pretty receipt viewer and scroll through all recorded attested file updates'/, 'expected editor diff section to link to a full attested diff browser');
    expectSource(/class ReceiptFileItem/, 'expected clickable changed file nodes');
});

test('commit explorer renders explicit recovery states instead of going blank', () => {
    expectSource(/class CommitPlaceholderItem extends vscode\.TreeItem/, 'expected a dedicated commit explorer placeholder item');
    expectSource(/if \(!this\.folderPath\) \{[\s\S]*return buildNoRepositoryItems\(\);[\s\S]*\}/, 'expected commit explorer to render a no-repository state when no target folder is available');
    expectSource(/if \(this\.commits\.length === 0\) \{[\s\S]*return buildNoCommitItems\(\);[\s\S]*\}/, 'expected commit explorer to render a no-commit state instead of an empty tree');
    expectSource(/Open a folder to start using AIIR/, 'expected explicit no-workspace copy in commit explorer');
    expectSource(/No repository available for commit coverage/, 'expected explicit no-repository copy in commit explorer');
    expectSource(/No recent commits yet/, 'expected explicit no-commit copy in commit explorer');
    expectSource(/Make the first commit, then generate a receipt to cover it\./, 'expected no-commit guidance to explain the next step');
    expectSource(/new CommitActionItem\('Open Folder', 'vscode\.openFolder', \[\], 'folder-opened'\)/, 'expected no-workspace recovery to offer opening a folder');
    expectSource(/new CommitActionItem\('Check Status', 'aiir\.readinessCheck', \[\], 'checklist'\)/, 'expected commit explorer recovery to link to commit status');
    expectSource(/new CommitActionItem\('Open Getting Started', 'aiir\.openWalkthrough', \[\], 'milestone'\)/, 'expected commit explorer recovery to link to the walkthrough');
    expectSource(/parts\.push\('covered'\)/, 'expected covered commit rows to lead with a clear coverage label');
    expectSource(/parts\.push\('needs repair'\)/, 'expected failing commit rows to lead with repair language');
    expectSource(/parts\.push\('needs receipt'\)/, 'expected uncovered commit rows to lead with receipt language');
    expectSource(/return 'Needs receipt — coverage gap';/, 'expected receipt status rows to use action-led gap wording');
    expectSource(/return `Needs repair: \$\{overlay\.errorSummary \?\? 'verification error'\}`;/, 'expected receipt status rows to use action-led repair wording');
    expectSource(/return `Coverage \$\{stats\.coveredCommits\}\/\$\{stats\.totalCommits\} commits`;/, 'expected coverage footer to read as a coverage summary');
});

test('readiness copy distinguishes blocked access, missing repositories, and missing initialization', () => {
    expectSource(/Workspace policy is hiding this repository from AIIR\./, 'expected readiness panel to call out policy-blocked access directly');
    expectSource(/Open a git repository to check commit status\./, 'expected readiness panel to distinguish missing git repo from missing initialization');
    expectSource(/No usable git repository detected in the current target/, 'expected readiness checklist to describe missing repository state clearly');
    expectSource(/The repository is open and the CLI is ready, but local AIIR scaffolding is missing\./, 'expected Home card to distinguish open-but-uninitialized repositories');
    expectSource(/This commit is ready to record\./, 'expected readiness panel to keep first-run guidance focused on recording the first commit');
    expectSource(/Add the repo policy file later if you want repo-local access defaults\./, 'expected readiness panel to demote repo policy creation from the main path');
    expectSource(/Check Commit Status/, 'expected readiness panel hero to center on current commit status');
    expectSource(/Advanced Setup Details/, 'expected detailed setup mechanics to sit behind the advanced section');
});

test('status bar uses action-led compliance language', () => {
    expectSource(/AIIR: Record needed/, 'expected head-missing status bar text');
    expectSource(/AIIR: Verify weaker evidence/, 'expected regulated warning status bar text');
    expectSource(/AIIR: Current commit recorded/, 'expected healthy status bar text');
    expectSource(/AIIR: Ready to record/, 'expected first-receipt status bar text');
    expectSource(/AIIR: Verify needs repair/, 'expected failing status bar text to stay action-led');
    expectSource(/\*\*Health\*\*/, 'expected status bar tooltip to summarize the shared health model');
    expectSource(/\| Check \| State \| Next step \|/, 'expected status bar tooltip health table');
});

test('failed receipts expose a guided repair flow instead of a dead-end message', () => {
    expectSource(/registerCommand\('aiir\.repairReceipt'/, 'expected failed receipt repair command registration');
    expectSource(/registerCommand\('aiir\.generateReceiptForCommit'/, 'expected exact-commit regeneration command registration');
    expectSource(/buildReceiptRepairPlan\(/, 'expected extracted repair planning helper');
    expectSource(/getReceiptFailureExplanation\(/, 'expected failure explanation helper for invalid receipts');
    expectSource(/AIIR: Repair Failed Receipt/, 'expected guided repair quick pick title');
    expectSource(/primaryRepairLabel/, 'expected receipt viewer repair action to reuse the repair plan label');
    expectSource(/Replace this failed receipt with a fresh proof for the same commit|This failed receipt points at an older commit/, 'expected recovery copy to guide exact-commit regeneration');
    expectSource(/Generate Receipt For \$\{receiptShaShort\}|Re-Record Receipt For \$\{receiptShaShort\}/, 'expected repair actions to show the target commit directly in the label');
    expectSource(/Open Coverage Check \(\$\{receiptShaShort\}\)|Open Receipt JSON \(\$\{receiptShaShort\}\)/, 'expected secondary repair actions to carry the target commit label');
});

test('pretty receipt viewer exposes a scrollable attested diff browser', () => {
    expectSource(/<h2>Attested Diffs<\/h2>/, 'expected attested diff section in the receipt viewer');
    expectSource(/max-height: 360px;/, 'expected attested diff list to be scrollable');
    expectSource(/Scroll through recorded deterministic file updates/, 'expected attested diff viewer guidance');
});

test('editor diff file nodes open a dedicated attested diff history panel', () => {
    expectSource(/import \{ getAttestedDiffPanelHtml \} from '\.\/attested_diff_panel';/, 'expected dedicated attested diff panel helper');
    expectSource(/command: 'aiir\.viewAttestedDiffFile'/, 'expected editor diff file nodes to open the dedicated panel');
    expectSource(/registerCommand\('aiir\.viewAttestedDiffFile'/, 'expected attested diff file panel command registration');
    expectSource(/'aiir\.attestedDiffViewer'/, 'expected dedicated attested diff webview id');
    expectSource(/Open Tracked File/, 'expected attested diff panel to preserve direct file access');
    expectSource(/Attested Update History/, 'expected dedicated attested diff history section');
    expectSource(/Open Latest Recoverable Diff/, 'expected panel to expose a latest recoverable diff action');
    expectSource(/Open Recoverable Diff/, 'expected per-event recoverable diff action');
    expectSource(/Compare is available when hashes match recoverable base, receipt, or workspace snapshots/, 'expected panel to explain recoverable comparison limits');
    expectSource(/Diff titles name the exact matched sources when compare is available/, 'expected panel to explain recoverable diff labeling');
    expectSource(/registerCommand\('aiir\.openAttestedDiffComparison'/, 'expected recoverable diff command registration');
    expectSource(/vscode\.diff/, 'expected recoverable comparisons to open a side-by-side diff');
    expectSource(/getRecoverableSnapshotMatchLabel\(/, 'expected shared matched-source label helper');
    expectSource(/Recoverable diff opened using \$\{beforeLabel\} and \$\{afterLabel\}\./, 'expected compare flow to announce the matched snapshot sources');
    expectSource(/getFileContentFromCommit\(/, 'expected recoverable comparisons to read git snapshots');
    expectSource(/resolveRecoverableAttestedDiff\(/, 'expected shared recoverable diff resolution helper');
});

test('receipt discovery covers .aiir/receipts subdirectory', () => {
    expectSource(/'\*\*\/\.aiir\/receipts\/\*\.json'/, 'expected discovery pattern for .aiir/receipts/*.json');
    expectSource(/async function loadReceiptRecordsFromLedger\(folder: vscode\.WorkspaceFolder\): Promise<ReceiptRecord\[]>/, 'expected ledger-backed receipt loader');
    expectSource(/loadReceiptRecordsFromLedger\(folder\)[\s\S]*nextRecords\.set\(getReceiptRecordKey\(record\), record\);/s, 'expected receipt refresh to prefer ledger-backed records when artifact files are stale');
});

test('receipt explorer only shows repos with ledgers and offers manage link', () => {
    expectSource(/hasLedger/, 'expected ledger detection in repository view state');
    expectSource(/resolveRepositoryViewState\(/, 'expected shared repository state resolver');
    expectSource(/pathExists\(path\.join\(aiirDir, 'receipts\.jsonl'\)\)/, 'expected ledger existence check in shared resolver');
    expectSource(/function shouldShowRepository\(state: RepositorySetupState \| undefined\)/, 'expected named repository visibility predicate');
    expectSource(/state\.hasReceipts \|\| state\.hasLedger \|\| state\.aiirDirExists/, 'expected widened repository filtering for initialized repos');
    expectSource(/registerCommand\('aiir\.manageRepositories'/, 'expected manage repositories command registration');
    expectSource(/canPickMany: true/, 'expected multi-select quick pick for repo management');
    expectSource(/if \(getShowAdvancedCommands\(\)\) \{[\s\S]*new ReceiptActionItem\(\s*'Manage Repositories'/, 'expected manage repositories action in explorer tree only when advanced mode is enabled');
    expectSource(/const manageRepositoriesDetail = unconfiguredCount > 0/, 'expected manage repositories action detail to stay visible even when all folders are active');
    expectSource(/:\s*`\$\{repositoryPaths\.length\} workspace folder\$\{repositoryPaths\.length === 1 \? '' : 's'\} active in this workspace`;/, 'expected always-visible manage repositories summary for fully active workspaces');
    expectSource(/registerCommand\('aiir\.switchRepository'/, 'expected switch repository command registration');
    expectSource(/setContext', 'aiir\.multipleAccessibleRepositories', accessibleFolders\.length > 1\)/, 'expected repository switcher context key');
    expectSource(/Choose the repository AIIR should focus on/, 'expected switch repository quick-pick guidance');
});

test('webviews enforce CSP, nonce-bearing scripts, bounded commands, and a command allowlist', () => {
    expectSource(/const COMMAND_TIMEOUT_MS = 30_000;/, 'expected bounded child-process timeout constant');
    expectSource(/const REQUEST_TIMEOUT_MS = 30_000;/, 'expected bounded network timeout constant');
    expectSource(/LANGUAGE_MODEL_RESPONSE_TIMEOUT_MS = 30_000;/, 'expected bounded language-model timeout constant');
    expectSource(/LANGUAGE_MODEL_RESPONSE_MAX_CHARS = 100_000;/, 'expected bounded language-model response size constant');
    expectSource(/const WEBVIEW_ALLOWED_COMMANDS = new Set\(\[/, 'expected explicit webview command allowlist');
    expectSource(/Blocked unexpected webview command/, 'expected unexpected webview commands to be blocked');
    expectSource(/Webview command \$\{payload\.command\} failed/, 'expected webview command failures to be surfaced in the AIIR output channel');
    expectSource(/const controller = new AbortController\(\);/, 'expected Hub request helper to create an abort controller');
    expectSource(/Request timed out after \$\{REQUEST_TIMEOUT_MS\}ms/, 'expected timed-out requests to return a clear bounded error');
    expectSource(/Language model response timed out after \$\{timeoutMs\}ms/, 'expected bounded language-model timeout error');
    expectSource(/Language model response exceeded \$\{maxChars\} characters/, 'expected bounded language-model size error');
    expectSource(/function finalizeScriptedWebviewHtml\(/, 'expected scripted webview CSP helper');
    expectSource(/function finalizeStaticWebviewHtml\(/, 'expected static webview CSP helper');
    expectSource(/<meta http-equiv="Content-Security-Policy"/, 'expected injected CSP meta tag');
    expectSource(/<script nonce="\$\{WEBVIEW_NONCE_TOKEN\}">/, 'expected nonce-bearing webview scripts');
    expectSource(/JSON\.stringify\(arg\)\.replace\(\/"\/g, '&quot;'\)/, 'expected rendered panel command args to HTML-escape double quotes for onclick attributes');
    assert.doesNotMatch(extensionSource, /onclick="cmd\('[^']+',\s*'[^']*'/, 'expected webview onclick handlers to avoid legacy single-quoted argument literals that break parser rewiring');
    expectSource(/function wirePanelCommands\(\) \{[\s\S]*querySelectorAll\('\[onclick\]'\)[\s\S]*getPanelCommand\(element\);/s, 'expected webview buttons to be normalized through the shared command helper');
    expectSource(/function getPanelCommand\(element\) \{[\s\S]*parseInlineCommand\(element\.getAttribute\('onclick'\)\)[\s\S]*removeAttribute\('onclick'\);/s, 'expected the shared command helper to lazily rebind inline handlers for CSP compatibility');
    expectSource(/document\.addEventListener\('click', event => \{[\s\S]*closest\('\[data-aiir-command\], \[onclick\]'\)[\s\S]*cmd\(panelCommand\.command, \.\.\.panelCommand\.args\);/s, 'expected webview command dispatch to use delegated click handling with inline-command fallback');
    expectSource(/execFileBounded\(/, 'expected bounded command helper usage');
});

test('provable-mode writes are serialized and preset-locked settings are enforced', () => {
    expectSource(/const provenanceQueueMutations = new Map/, 'expected a shared provenance queue mutation lock map');
    expectSource(/async function runWithProvenanceQueueLock</, 'expected a queue lock helper for provenance writes');
    expectSource(/await runWithProvenanceQueueLock\(queuePath, async \(\) => \{/, 'expected provenance append paths to run under the queue lock');
    expectSource(/const receiptGenerationMutations = new Map/, 'expected a shared receipt generation lock map');
    expectSource(/async function runWithReceiptGenerationLock</, 'expected a folder-scoped lock helper for receipt generation');
    expectSource(/return await deps\.runWithReceiptGenerationLock\(folder\.uri\.fsPath, deps\.output, async \(\) => \{/, 'expected receipt generation to run under the folder-scoped lock');
    expectSource(/Receipt generation already in progress for \$\{path\.basename\(folderPath\)\}\. Waiting for the active run to finish\./, 'expected queued receipt generation to log a clear wait message');
    expectSource(/async function enforceLockedPresetSettings\(/, 'expected locked preset enforcement helper');
    expectSource(/Clear \$\{LOCK_PRESET_SETTING\} to change it/, 'expected locked preset mutations to explain how to unlock');
    expectSource(/Reverted \$\{revertedKeys\.join\(', '\)\} because they are locked by preset/, 'expected locked preset config changes to be restored with a warning');
});

test('manage repositories applies both additions and removals', () => {
    expectSource(/placeHolder: 'Select repositories to keep active in this workspace'/, 'expected repository manager to describe active workspace selection instead of enable-only behavior');
    expectSource(/picked: shouldShowRepository\(repositoryState\)/, 'expected repository manager selection state to match visible active repositories');
    expectSource(/const selectedPaths = new Set\(selected\.map\(item => item\.folder\.uri\.fsPath\)\);/, 'expected repository manager to compare current and selected repository sets');
    expectSource(/const newlyDisabled = items\.filter\(item => !selectedPaths\.has\(item\.folder\.uri\.fsPath\) && item\.picked\);/, 'expected repository manager to detect removals');
    expectSource(/if \(newlyEnabled\.length === 0 && newlyDisabled\.length === 0\) \{[\s\S]*Repository selection unchanged/s, 'expected repository manager to handle unchanged selections explicitly');
    expectSource(/Removed \$\{names\} from the active workspace repository list\./, 'expected repository manager success message to acknowledge removals');
});

test('setup helpers keep empty-repo actions and checklist ordering stable', () => {
    expectSource(/export const SETUP_PRIORITY_CHAIN: readonly SetupPriorityKey\[\] = \[/, 'expected shared setup-priority chain constant');
    expectSource(/export function isRepositoryFullyReady\(state: RepositorySetupState \| undefined\): boolean \{[\s\S]*state\.aiirDirExists && state\.hasLedger && state\.cliAvailable && state\.policyExists;/, 'expected fully-ready predicate to require policy configuration');
    expectSource(/const checklist = input\.sortChecklist\(\[/, 'expected readiness checklist ordering to use the shared helper');
    expectSource(/label: 'Repository open'/, 'expected readiness checklist to start with repository-open language');
    expectSource(/label: 'Commit activity recorded'/, 'expected readiness checklist to focus on whether commits are already covered');
    expectSource(/: !isRepositoryFullyReady\(state\)[\s\S]*\? 'Continue status check'[\s\S]*: 'Open commit status';/, 'expected empty repositories to keep commit status as the non-mutating follow-up');
});

test('receipt generation closes with view, copy, and automation next steps', () => {
    expectSource(/registerCommand\('aiir\.generatePreferred'/, 'expected smart default generate command registration');
    expectSource(/registerCommand\('aiir\.copyReceiptSummary'/, 'expected copy receipt summary command registration');
    expectSource(/registerCommand\('aiir\.previewReceiptSummary'/, 'expected preview receipt summary command registration');
    expectSource(/\['Copy Summary', 'View Proof'\]/, 'expected post-generate next-step actions');
    expectSource(/if \(hookKind !== 'managed'\) \{[\s\S]*actions\.push\('Turn On Auto Next Time'\);/, 'expected post-generate automation upsell when hook is not managed');
    expectSource(/AIIR: Current commit recorded in \$\{folder\.name\}/, 'expected post-generate success copy to center the current commit');
    expectSource(/AIIR: Commit \$\{commitSha\.slice\(0, 8\)\} recorded in \$\{folder\.name\}/, 'expected exact-commit regeneration success copy to stay commit-specific');
    expectSource(/buildReceiptClipboardSummary\(/, 'expected receipt clipboard summary formatter');
    expectSource(/## AIIR PR Summary/, 'expected markdown receipt summary heading');
    expectSource(/### Snapshot/, 'expected PR-ready summary snapshot section');
    expectSource(/### AI Evidence/, 'expected PR-ready summary AI evidence section');
    expectSource(/- AI signals: \$\{getAISignalsSummary\(receipt\)\}/, 'expected AI signals in markdown receipt summary');
});

test('setup can remember and resume the user intent once the CLI is ready', () => {
    expectSource(/const PENDING_ACTION_KEY = 'aiir\.pendingAction\.v1';/, 'expected persisted pending action key');
    expectSource(/interface PendingAction \{/, 'expected pending action model');
    expectSource(/interface PendingActionContinuationOptions \{/, 'expected pending action continuation options');
    expectSource(/const maybeContinuePendingAction = async \(options\?: PendingActionContinuationOptions\): Promise<boolean> => \{/, 'expected pending action continuation helper');
    expectSource(/AIIR: Setup is ready\. Continue to \$\{pending\.label\}\?/, 'expected continuation prompt after setup');
    expectSource(/const shouldPrompt = options\?\.prompt !== false;/, 'expected pending action helper to support silent continuation after setup actions');
    expectSource(/await maybeContinuePendingAction\(\{ prompt: false \}\);/, 'expected explicit setup commands to silently resume the pending action');
    expectSource(/AIIR: \$\{action\.label\} needs the AIIR CLI first\./, 'expected guided setup handoff instead of ENOENT dead end');
    expectSource(/function getReadinessHtml\([\s\S]*view: ReadinessViewModel,[\s\S]*pendingAction\?: ReadinessPendingActionViewModel,[\s\S]*options\?: \{ showAdvanced\?: boolean \},?[\s\S]*\)/, 'expected readiness panel support for pending actions');
    expectSource(/Continue What You Started/, 'expected readiness panel section for resumed user intent');
    expectSource(/cmd\('aiir\.continuePendingAction'\)/, 'expected readiness panel continue button wiring');
    expectSource(/Install CLI and Continue/, 'expected pending action recovery to offer install-and-continue');
    expectSource(/Initialize Repository and Continue/, 'expected pending record flow to offer initialize-and-continue');
    expectSource(/commandId: 'aiir\.generatePreferred'[\s\S]*folderPath: folder\.uri\.fsPath/s, 'expected smart default generate intent capture');
    expectSource(/commandId: 'aiir\.generateReceipt'[,\s\S]*folderPath: folder\.uri\.fsPath/s, 'expected generate receipt intent capture');
    expectSource(/commandId: 'aiir\.initializeRepo'[,\s\S]*folderPath: unavailableFolder\.uri\.fsPath/s, 'expected initialize repository intent capture');
    expectSource(/commandId: 'aiir\.enableAutoReceipting'[,\s\S]*folderPath: folder\.uri\.fsPath/s, 'expected auto-receipting intent capture');
});

test('initialize repo retargets Home to the initialized repository before refreshing', () => {
    expectSource(/for \(const folder of targetFolders\) \{[\s\S]*await initializeWorkspaceFolder\(folder, output, 'balanced', baselineFolders\);[\s\S]*await generateReceiptForFolder\(folder\);[\s\S]*\}/s, 'expected initialize flow over explicit target folders and generate starter receipts');
    expectSource(/if \(targetFolders\.length > 0\) \{[\s\S]*rememberWorkspaceFolder\(targetFolders\[0\]\);[\s\S]*\}/s, 'expected initialize flow to retarget Home to the initialized repository');
    expectSource(/const starterReceipt = starterReceipts\.find\(entry => entry\.folder\.uri\.fsPath === targetFolders\[0\]\?\.uri\.fsPath\)\?\.receipt;/, 'expected initialize flow to surface the starter receipt for the primary repository');
});

test('blocked actions steer users to recovery surfaces instead of dead-end errors', () => {
    expectSource(/async function showWorkspaceAccessRecovery\(/, 'expected workspace recovery helper');
    expectSource(/'Open Advanced Settings',\s*'Open Security Posture'/, 'expected isolation recovery actions');
    expectSource(/A workspace is open, but AIIR could not find a usable repository folder/, 'expected open-workspace recovery message when no usable repo is detected');
    expectSource(/async function showNetworkAccessRecovery\(/, 'expected network recovery helper');
    expectSource(/'Open Advanced Settings',\s*'Open Public Pricing'/, 'expected network recovery actions');
    expectSource(/type RequiredHubCapability = 'remoteReceiptSync' \| 'sharedRepositories' \| 'policyManagement' \| 'complianceExports';/, 'expected explicit Hub capability gates for blocked-action recovery');
    expectSource(/async function showHubCapabilityRecovery\(/, 'expected Hub capability recovery helper');
    expectSource(/const requirementLabel = requirement === 'connection'[\s\S]*'an active Hub connection'[\s\S]*getHubCapabilityLabel\(requirement\)/s, 'expected Hub recovery copy to derive the missing connection or capability label');
    expectSource(/return 'remote receipt sync';/, 'expected Hub capability labels to include remote receipt sync');
    expectSource(/return 'compliance exports';/, 'expected Hub capability labels to include compliance exports');
    expectSource(/resolved\.primaryActionLabel[\s\S]*resolved\.primaryActionCommandId/s, 'expected Hub recovery to route through normalized Hub next actions');
    expectSource(/await deps\.showWorkspaceAccessRecovery\('generate receipts'\)/, 'expected generate receipt recovery routing');
    expectSource(/await showWorkspaceAccessRecovery\('use the control panel'\)/, 'expected control panel recovery routing');
    expectSource(/await showNetworkAccessRecovery\('connect to Hub'\)/, 'expected connect hub recovery routing');
    expectSource(/await showNetworkAccessRecovery\('open the Hub dashboard'\)/, 'expected hub dashboard recovery routing');
    expectSource(/await showHubCapabilityRecovery\(options\.action, 'connection', resolved\);/, 'expected Hub config helper to recover through state-aware connection guidance');
    expectSource(/await showHubCapabilityRecovery\(options\.action, options\.requiredCapability, resolved\);/, 'expected Hub config helper to recover through state-aware capability guidance');
    expectSource(/requiredCapability: 'remoteReceiptSync'/, 'expected remote-sync Hub actions to declare their capability requirement');
    expectSource(/requiredCapability: 'complianceExports'/, 'expected evidence-pack Hub action to declare its compliance capability requirement');
    expectSource(/const accessButton = view\.networkAllowed[\s\S]*Open Advanced Settings/s, 'expected Hub billing page to offer settings instead of a dead disabled request button');
});

test('control panel quick actions adapt to repo readiness instead of staying unconditional', () => {
    expectSource(/const generateAction = !health\.cliAvailable[\s\S]*Open Commit Status[\s\S]*Initialize Repo[\s\S]*Generate/s, 'expected receipt quick action to switch between status, initialization, and generation');
    expectSource(/const verifyAllDisabled = stats\.total === 0;/, 'expected verify-all button disable state when no receipts exist');
    expectSource(/const fixActionDisabled = stats\.invalid === 0;/, 'expected fix action disable state when no failed receipts exist');
    expectSource(/const repoAction = !health\.aiirDirExists[\s\S]*Initialize Repo[\s\S]*!health\.policyExists[\s\S]*Create Policy File[\s\S]*Open Policy File/s, 'expected repo quick action to switch between initialization, policy creation, and policy opening');
    expectSource(/const autoReceiptAction = !health\.cliAvailable[\s\S]*Disable Auto-Receipting[\s\S]*Enable Auto-Receipting/s, 'expected auto-receipting quick action to adapt to current hook state');
    expectSource(/<h2>Core Workflow<\/h2>/, 'expected control panel to foreground the core workflow');
    expectSource(/Use setup when prerequisites are missing, generate for the current work, verify the repository receipts, and jump directly into the latest failure/, 'expected control panel to describe the narrowed default path');
    expectSource(/Fix Latest Failure/, 'expected control panel quick actions to expose a single fix entry point');
    expectSource(/\$\{showAdvanced \? `<section>[\s\S]*<h2>Pages<\/h2>/s, 'expected control panel operator pages to stay behind advanced mode');
    expectSource(/button:disabled \{ opacity: 0\.45; cursor: not-allowed; \}/, 'expected control panel disabled button styling');
});

test('health check guides users toward the right next step for the current repo state', () => {
    expectSource(/const nextAction = !health\.cliAvailable[\s\S]*Open Commit Status[\s\S]*Initialize Repository[\s\S]*Generate[\s\S]*Enable Auto-Receipting[\s\S]*Review Coverage/s, 'expected health check next-step decision tree');
    expectSource(/<h2>Recommended Next Step<\/h2>/, 'expected health check next-step section');
    expectSource(/Local provenance is the default VS Code path\. Use Sigstore signing in CI or release workflows/, 'expected health-check workflow-boundary guidance');
    expectSource(/Review Settings/, 'expected health check next-step settings fallback');
    expectSource(/Review Coverage/, 'expected polished coverage review label');
    expectSource(/Review Plans/, 'expected polished plans review label');
    expectSource(/Review Security/, 'expected polished security review label');
    expectSource(/Review Presets/, 'expected polished preset review label');
});

test('receipt viewer exposes markdown copy and preview actions', () => {
    expectSource(/createWebviewPanel\([\s\S]*enableScripts: true/s, 'expected receipt viewer scripts enabled for viewer actions');
    expectSource(/renderViewerCommandAttributes\('aiir\.copyReceiptSummary'\)/, 'expected copy markdown button in receipt viewer to use CSP-safe command attributes');
    expectSource(/renderViewerCommandAttributes\('aiir\.previewReceiptSummary'\)/, 'expected preview markdown button in receipt viewer to use CSP-safe command attributes');
    expectSource(/function serializeViewerCommandArg\(value: unknown\): unknown \{[\s\S]*value instanceof vscode\.Uri[\s\S]*return value\.toString\(\);/s, 'expected receipt viewer to serialize VS Code URIs before posting webview commands');
    expectSource(/renderCommandAttributes\(command, args\.map\(serializeViewerCommandArg\)\)/, 'expected receipt viewer buttons to bypass inline onclick parsing');
    expectSource(/if \(message\?\.command === 'aiir\.openReceiptSource'\) \{[\s\S]*record\.uri/s, 'expected receipt viewer to open the JSON source for the current record');
    expectSource(/markdown\.showPreviewToSide/, 'expected markdown preview command wiring');
    expectSource(/<h2>Outcome<\/h2>/, 'expected receipt viewer outcome section heading');
    expectSource(/<h2>Evidence<\/h2>/, 'expected receipt viewer evidence section heading');
    expectSource(/<h2>AI Summary<\/h2>/, 'expected receipt viewer AI summary section heading');
    expectSource(/<h2>Exceptions<\/h2>/, 'expected receipt viewer exceptions section heading');
    expectSource(/<h2>Files<\/h2>/, 'expected receipt viewer files section heading');
    expectSource(/<h2>Raw JSON<\/h2>/, 'expected receipt viewer raw JSON section heading');
    expectSource(/Review Commit|Repair Receipt/, 'expected receipt viewer to prioritize a decision-first primary action');
    expectSource(/<h2>Fix This Receipt<\/h2>/, 'expected invalid receipt viewer to surface a direct fix section');
    expectSource(/Recommended Next Step/, 'expected invalid receipt viewer to frame the recovery flow around the primary action');
    expectSource(/What Happens Next/, 'expected invalid receipt viewer to explain the recovery sequence');
    expectSource(/primaryRepairLabel/, 'expected invalid receipt viewer to derive the repair button label from the repair plan');
    expectSource(/primaryRepairDescription/, 'expected invalid receipt viewer to surface the primary repair description inline');
    expectSource(/renderViewerCommandAttributes\(repairPlan\.primaryAction\.command, repairPlan\.primaryAction\.args\)/, 'expected invalid receipt viewer primary action to run the repair plan directly through CSP-safe command attributes');
    expectSource(/More Repair Options/, 'expected invalid receipt viewer to keep advanced recovery choices behind a secondary action');
    expectSource(/Open Receipt JSON \(\$\{shaShort\}\)/, 'expected invalid receipt viewer to keep direct receipt inspection commit-specific');
    expectSource(/Refresh Receipts/, 'expected invalid receipt viewer to keep refresh available');
    expectSource(/What AIIR changes:[\s\S]*records a fresh proof instead of editing this JSON in place/s, 'expected invalid receipt viewer to explain the content-addressed repair boundary');
    expectSource(/This receipt failed integrity checks|This receipt file is malformed|This receipt did not pass local verification/, 'expected invalid receipt viewer to explain the failure class clearly');
});

test('receipt viewer and tree surface deterministic editor provenance', () => {
    expectSource(/function getEditorProvenance\(/, 'expected editor provenance helper');
    expectSource(/function getEditorProvenanceSummary\(/, 'expected editor provenance summary helper');
    expectSource(/function getAttestedSystemSummary\(/, 'expected attested system helper');
    expectSource(/\['Evidence Tier', escapeHtml\(EVIDENCE_TIER_LABELS\[evidenceTier\]\)\]/, 'expected viewer evidence tier summary row');
    expectSource(/\['Attested Tool', escapeHtml\(getAttestedSystemSummary\(r\)\)\]/, 'expected viewer attested tool row');
    expectSource(/\['Editor Provenance', escapeHtml\(getEditorProvenanceSummary\(r\)\)\]/, 'expected viewer summary row for deterministic editor provenance');
    expectSource(/Provable evidence present, but unsigned for stricter workflow\.|Receipt valid, but stronger evidence is still missing\./, 'expected viewer decision summary to explain evidence gaps clearly');
    expectSource(/new ReceiptSubsectionItem\(record, 'editor-diffs', 'Editor Diffs'/, 'expected explicit editor diff subsection in the receipt tree');
    expectSource(/type ProvenanceCategoryKind = 'intent' \| 'chat' \| 'commit';/, 'expected editor provenance categories to keep metadata only after editor diffs move out');
    expectSource(/class EditorDiffFileItem extends vscode\.TreeItem/, 'expected dedicated expandable editor diff file node');
    expectSource(/new EditorDiffFileItem\(element\.record, filePath, fileUri, events\)/, 'expected editor diffs to create expandable per-file nodes');
    expectSource(/new ReceiptDetailItem\('Recorded Updates', String\(element\.events\.length\), 'history'\)/, 'expected per-file editor diff summary details');
    expectSource(/new ReceiptDetailItem\(`Update \$\{index \+ 1\}`/, 'expected recent provenance updates listed under each editor diff file');
    expectSource(/<strong>Deterministic editor provenance<\/strong>/, 'expected receipt viewer provenance callout');
    expectSource(/Generate With Provenance Next Time/, 'expected heuristic upgrade action in receipt viewer');
    expectSource(/Heuristic only/, 'expected viewer to distinguish heuristic-only receipts from deterministic provenance');
    expectSource(/Record Exception/, 'expected receipt viewer exceptions section to surface the exception action');
});

test('status bar and watchers keep pace with git state changes', () => {
    expectSource(/export interface ResolvedTrustState/, 'expected shared resolved trust state model');
    expectSource(/async function getResolvedTrustState\(/, 'expected shared trust-state gatherer');
    expectSource(/async refresh\(explorer: ReceiptExplorerProvider\)/, 'expected repository-aware status bar refresh');
    expectSource(/function createGitStateWatcher\(/, 'expected git state watcher');
    expectSource(/new vscode\.RelativePattern\(gitDir, pattern\)/, 'expected git watcher patterns rooted in the git dir');
    expectSource(/onDidChangeWorkspaceFolders\(async \(\) => \{[\s\S]*await recreateGitWatcher\(\)/, 'expected watcher recreation when workspace folders change');
});

test('ambient nudges cover active AI tool usage on new unreceipted HEAD commits', () => {
    expectSource(/activeAITool\?: string;/, 'expected shared trust state to track active AI tools');
    expectSource(/cliAvailable: boolean;/, 'expected shared trust state to track CLI availability');
    expectSource(/getRepositoryState\(folder\)/, 'expected trust-state gatherer to read shared repository state');
    expectSource(/activeAITool: repositoryState\?\.activeAIToolName/, 'expected trust-state gatherer to capture the active AI tool from shared repository state');
    expectSource(/const maybeShowMissingReceiptNudge = async \(\) => \{/, 'expected one-time missing receipt nudge helper');
    expectSource(/trustState\.headReceiptStatus !== 'missing' \|\| trustState\.hookKind === 'managed' \|\| !trustState\.activeAITool/, 'expected missing-receipt nudge guardrails');
    expectSource(/looks active and HEAD is missing a receipt/, 'expected active AI tool nudge copy');
    expectSource(/vscode\.commands\.executeCommand\('aiir\.generatePreferred'\)/, 'expected nudge to use the smart default generate command');
    expectSource(/setContext', 'aiir\.headReceiptMissing'/, 'expected SCM ambient context for missing HEAD coverage');
    expectSource(/setContext', 'aiir\.activeAIToolDetected'/, 'expected SCM ambient context for active AI tools');
    expectSource(/setContext', 'aiir\.autoReceiptingManaged'/, 'expected SCM ambient context for managed auto-receipting');
    expectSource(/setContext', 'aiir\.cliAvailable'/, 'expected SCM ambient context for CLI availability');
});



test('webview navigation bar hides advanced pages by default and keeps the active admin page reachable', () => {
    expectSource(/\{ id: 'readiness', label: 'Status', command: 'aiir\.readinessCheck'/, 'expected status nav button');
    expectSource(/\{ id: 'summary', label: 'Summary', command: 'aiir\.showSummary'/, 'expected summary nav button');
    expectSource(/\{ id: 'health', label: 'Health', command: 'aiir\.healthCheck'/, 'expected health nav button');
    expectSource(/const showAdvanced = options\?\.showAdvanced \?\? false;/, 'expected nav visibility to be driven by advanced mode');
    expectSource(/\{ id: 'control', label: 'Advanced', command: 'aiir\.controlPanel', visible: showAdvanced \|\| active === 'control' \}/, 'expected advanced page nav button to stay hidden until advanced mode is enabled or the page is already open');
    expectSource(/\{ id: 'billing', label: 'Plans', command: 'aiir\.hubBilling', visible: true \}/, 'expected plans page nav button to stay visible');
    expectSource(/\{ id: 'security', label: 'Security', command: 'aiir\.securityPosture', visible: showAdvanced \|\| active === 'security' \}/, 'expected security page nav button to stay hidden until advanced mode is enabled or the page is already open');
    expectSource(/\{ id: 'presets', label: 'Presets', command: 'aiir\.rolloutPresets', visible: showAdvanced \|\| active === 'presets' \}/, 'expected presets page nav button to stay hidden until advanced mode is enabled or the page is already open');
    expectSource(/\{ id: 'settings', label: 'Settings', command: 'aiir\.advancedSettings', visible: showAdvanced \|\| active === 'settings' \}/, 'expected settings page nav button to stay hidden until advanced mode is enabled or the page is already open');
});

test('getting started walkthrough and onboarding commands stay wired', () => {
    expectSource(/registerCommand\('aiir\.readinessCheck', openReadinessPanel\)/, 'expected readiness command registration');
    expectSource(/registerCommand\('aiir\.openWalkthrough'/, 'expected walkthrough command registration');
    expectSource(/workbench\.action\.openWalkthrough/, 'expected VS Code walkthrough command wiring');
});

test('receipt explorer keeps human-first labels and direct open behavior', () => {
    expectSource(/super\(\s*getReceiptSubject\(receipt\),\s*vscode\.TreeItemCollapsibleState\.Collapsed/s, 'expected receipt rows to use commit subjects as primary labels');
    expectSource(/this\.description = getReceiptListDescription\(record\);/, 'expected receipt rows to use status-rich secondary text');
    expectSource(/const parts = \[commitShort, EVIDENCE_TIER_SHORT_LABELS\[tier\], formatReceiptTimestamp\(receipt\.timestamp\)\];/, 'expected per-commit evidence tier in receipt row description');
    expectSource(/hasAIInvolvement\(receipt\)/, 'expected AI badge in receipt row description');
    expectSource(/getRepositoryHeadBadge/, 'expected HEAD status badge on repository items');
    expectSource(/new ReceiptActionItem\('Open Pretty Receipt',/, 'expected pretty receipt opening to be an explicit nested action');
});

test('summary panel pushes provenance and signing upgrades from evidence-tier totals', () => {
    expectSource(/const showSummaryCmd = vscode\.commands\.registerCommand\('aiir\.showSummary', async \(target\?: unknown\) => \{/, 'expected summary command to accept a target from webviews');
    expectSource(/getSummaryHtml\(stats, aiPercent, folderStats, folder\?\.uri\.toString\(\)\)/, 'expected summary panel rendering to carry the selected repository target');
    expectSource(/function getSummaryHtml\([\s\S]*targetUri\?: string/s, 'expected summary HTML helper to accept an optional command target');
    expectSource(/getPanelNavHtml\('summary', \{ networkAllowed: isNetworkAllowed\(\), hubVisible: isHubEnabled\(\), commandTarget: targetUri, showAdvanced: getShowAdvancedCommands\(\) \}\)/, 'expected summary navigation to preserve repository context');
    expectSource(/renderCommandCall\('aiir\.generatePreferred', targetArgs\)/, 'expected summary generate action to stay bound to the selected repository');
    expectSource(/renderCommandCall\('aiir\.generateWithProvenance', targetArgs\)/, 'expected summary provenance action to stay bound to the selected repository');
    expectSource(/<strong>Core Workflow<\/strong>/, 'expected summary panel to foreground the default workflow actions');
    expectSource(/set up the repository, generate receipts for current work, verify what exists, and jump straight into the latest failure/, 'expected summary panel to describe the narrowed default path');
    expectSource(/renderCommandCall\('aiir\.fixLatestFailedReceipt', targetArgs\)/, 'expected summary panel fix action to target the latest failed receipt in scope');
    expectSource(/<h2 style="margin-top:28px;">Evidence Tiers<\/h2>/, 'expected summary evidence-tier section');
    expectSource(/heuristic receipt.*need a stronger next step/i, 'expected heuristic upgrade callout in summary panel');
    expectSource(/Generate With Provenance/, 'expected provenance upgrade action in summary panel');
    expectSource(/Open Signing Guide/, 'expected signing upgrade action in summary panel');
});

test('fix latest failed receipt opens the newest invalid receipt in scope', () => {
    expectSource(/const fixLatestFailedReceiptCmd = vscode\.commands\.registerCommand\('aiir\.fixLatestFailedReceipt', async \(target\?: unknown\) => \{/, 'expected helper command registration for focused failure repair');
    expectSource(/explorer\.getRecentReceipts\(50, folder\)\.find\(record => !record\.result\.valid\)/, 'expected fix helper to choose the newest invalid receipt for the selected scope');
    expectSource(/AIIR: No failed receipts need repair right now\./, 'expected fix helper to explain when there is nothing to repair');
    expectSource(/executeCommand\('aiir\.viewReceipt', failedRecord\.uri\)/, 'expected fix helper to open the guided receipt repair viewer');
    expectSource(/fixLatestFailedReceiptCmd/, 'expected fix helper wired into subscriptions');
});

test('verify all refreshes Home after refreshing the receipt explorer', () => {
    expectSource(/const verifyAllCmd = vscode\.commands\.registerCommand\('aiir\.verifyAll', async \(\) => \{[\s\S]*await explorer\.refresh\(\);[\s\S]*await homeProvider\.refresh\(\);[\s\S]*const stats = explorer\.getStats\(\);/s, 'expected verify-all to refresh Home after the receipt explorer so summary state does not stay stale');
});

test('receipt UI distinguishes AI involvement from heuristic AI authorship', () => {
    expectSource(/function getAIInvolvementSummary\(/, 'expected AI involvement helper');
    expectSource(/function getAISignalsSummary\(/, 'expected AI signals helper');
    expectSource(/\['AI Involvement', aiField\]/, 'expected viewer summary row for AI involvement');
    expectSource(/\['AI Signals Detected', aiSignalsField\]/, 'expected viewer summary row for AI signal detection');
    expectSource(/new ReceiptDetailItem\('AI Involvement', getAIInvolvementSummary\(r\), 'hubot'\)/, 'expected tree overview to separate AI involvement from AI authorship');
});

test('MCP server auto-configuration connects the extension to Copilot Chat', () => {
    // Command registration
    expectSource(/registerCommand\('aiir\.configureMcpServer'/, 'expected MCP configuration command registration');
    expectSource(/configureMcpServerCmd/, 'expected command wired into subscriptions');

    // MCP config generation writes .vscode/mcp.json with aiir server entry
    expectSource(/\.vscode.*mcp\.json/, 'expected .vscode/mcp.json path construction');
    expectSource(/aiir-mcp-server/, 'expected MCP server command name');
    expectSource(/servers.*aiir.*serverConfig/, 'expected server config merged into mcp.json');
    expectSource(/createDirectory\(vscodeDirUri\)/, 'expected .vscode directory creation');

    // Already-configured detection with MCP status on health check
    expectSource(/mcpConfigured/, 'expected MCP configured status in health check result');
    expectSource(/servers\?\.aiir/, 'expected MCP config detection via mcp.json parsing');

    // Control Panel surfaces MCP status
    expectSource(/Copilot Chat connected.*MCP not configured/, 'expected MCP badge in control panel hero');
    expectSource(/Reconfigure.*Connect to Copilot Chat/, 'expected MCP page card with state-aware label');
    expectSource(/MCP Server.*configured/, 'expected MCP status in health grid');

    // Derives MCP server path from custom CLI path when set
    expectSource(/cliPath !== 'aiir'/, 'expected custom CLI path detection for MCP server derivation');

    // Post-config offers to open Copilot Chat
    expectSource(/Open Copilot Chat[\s\S]*Open mcp\.json/, 'expected post-config action choices');
    expectSource(/workbench\.action\.chat\.open/, 'expected Copilot Chat opening command');
});

test('home state includes regulated-incomplete for repos that do not meet the evidence bar', () => {
    expectSource(/export type HomeState = [^;]*'regulated-incomplete'/, 'expected regulated-incomplete home state');
    expectSource(/export type TrustVertex = [^;]*'regulated'/, 'expected regulated trust vertex');
    expectSource(/regulatedMode\?: boolean/, 'expected regulatedMode input field on trust state');
    expectSource(/case 'regulated-incomplete':[\s\S]*return 'regulated';/, 'expected regulated-incomplete to map to regulated trust vertex');
    expectSource(/regulated mode requires stronger evidence/, 'expected regulated-incomplete guidance copy');
});

test('signing promotion surfaces unsigned receipt warnings and a signing guide', () => {
    expectSource(/No signed receipts detected/, 'expected signing callout when no sigstore receipts exist');
    expectSource(/Unsigned receipt/, 'expected unsigned receipt warning in receipt viewer');
    expectSource(/function getSigningGuideHtml\(\)/, 'expected signing guide HTML generator');
    expectSource(/Why sign\?/, 'expected signing guide rationale callout');
    expectSource(/AIIR: Install Sigstore Support/, 'expected signing guide to mention the managed Sigstore setup command');
    expectSource(/registerCommand\('aiir\.openSigningGuide'/, 'expected signing guide command registration');
    expectSource(/Install Sigstore Support',\s*'Open Signing Guide'/, 'expected Sigstore verification recovery actions');
});

test('review attestation commands are registered and wired', () => {
    expectSource(/registerCommand\('aiir\.reviewReceipt'/, 'expected review receipt command registration');
    expectSource(/registerCommand\('aiir\.viewReviewHistory'/, 'expected view review history command registration');
    expectSource(/function getReceiptReviewInfo\(/, 'expected review metadata parsing helper');
    expectSource(/Review Status/, 'expected receipt UI to surface review status');
    expectSource(/Review This Commit/, 'expected receipt UI to expose direct review action');
    expectSource(/View Review History/, 'expected receipt UI to expose review history action');
    expectSource(/function getReviewHistoryHtml\(/, 'expected review history HTML generator');
    expectSource(/--review-outcome/, 'expected CLI review outcome flag in review command');
    expectSource(/--review-comment/, 'expected CLI review comment flag in review command');
});

test('compliance exception recording is gated on regulated mode', () => {
    expectSource(/registerCommand\('aiir\.recordException'/, 'expected record exception command registration');
    expectSource(/coverage-gap/, 'expected coverage-gap exception type');
    expectSource(/unsigned-receipt/, 'expected unsigned-receipt exception type');
    expectSource(/missing-review/, 'expected missing-review exception type');
    expectSource(/vsExt\.exceptions/, 'expected exceptions written to policy file');
});

test('evidence pack export bundles health check and policy data', () => {
    expectSource(/registerCommand\('aiir\.exportEvidencePack'/, 'expected export evidence pack command registration');
    expectSource(/aiir-evidence-pack/, 'expected evidence pack filename pattern');
    expectSource(/pack\.exceptions = exceptions;/, 'expected evidence pack to include recorded exceptions');
    expectSource(/pack\.reviewSummary = \{/, 'expected evidence pack to include review summary counts');
    expectSource(/pack\.reviews = reviews;/, 'expected evidence pack to include review attestations');
});

test('trailer injection is configurable through managed hook args', () => {
    expectSource(/injectTrailers/, 'expected trailer injection setting reference');
    expectSource(/--trailer/, 'expected --trailer flag in managed hook args');
    expectSource(/Trailer Injection/, 'expected trailer injection status in health check');
});

test('health check surfaces compliance posture section', () => {
    expectSource(/Compliance Posture/, 'expected compliance posture section heading');
    expectSource(/Lock Preset/, 'expected lock preset display in compliance posture');
    expectSource(/regulatedMode/, 'expected regulated mode field in health check result');
    expectSource(/lockPreset/, 'expected lock preset field in health check result');
    expectSource(/trailerInjection/, 'expected trailer injection field in health check result');
});

test('provenance queue purge command is registered', () => {
    expectSource(/registerCommand\('aiir\.purgeProvenanceQueue'/, 'expected purge provenance queue command registration');
});

// ── Gap 1: @aiir chat participant ────────────────────────────────────

test('chat participant is registered for Copilot Chat', () => {
    expectSource(/import \{ registerChatParticipant/, 'expected chat participant import');
    expectSource(/registerChatParticipant\(context, copilotIntegrationDeps\)/, 'expected chat participant registration in activate');
    expectSource(/createChatParticipant\('aiir\.chat'/, 'expected chat participant creation with aiir.chat id');
    expectSource(/request\.command/, 'expected chat participant to dispatch on slash commands');
    expectSource(/case 'receipt':/, 'expected receipt slash command handler');
    expectSource(/case 'verify':/, 'expected verify slash command handler');
    expectSource(/case 'stats':/, 'expected stats slash command handler');
    expectSource(/case 'explain':/, 'expected explain slash command handler');
    expectSource(/case 'policy':/, 'expected policy slash command handler');
    expectSource(/participant\.iconPath/, 'expected chat participant icon');
});

// ── Gap 2: Language model tools ──────────────────────────────────────

test('language model tools are registered for Copilot agentic mode', () => {
    expectSource(/import \{ registerLanguageModelTools/, 'expected language model tools import');
    expectSource(/registerLanguageModelTools\(context, copilotIntegrationDeps\)/, 'expected language model tools registration in activate');
    expectSource(/lm\.registerTool\('aiir_receipt'/, 'expected aiir_receipt tool registration');
    expectSource(/lm\.registerTool\('aiir_verify'/, 'expected aiir_verify tool registration');
    expectSource(/lm\.registerTool\('aiir_stats'/, 'expected aiir_stats tool registration');
    expectSource(/lm\.registerTool\('aiir_explain'/, 'expected aiir_explain tool registration');
    expectSource(/lm\.registerTool\('aiir_policy_check'/, 'expected aiir_policy_check tool registration');
    expectSource(/class ReceiptTool implements vscode\.LanguageModelTool/, 'expected ReceiptTool class');
    expectSource(/class VerifyTool implements vscode\.LanguageModelTool/, 'expected VerifyTool class');
    expectSource(/new vscode\.LanguageModelToolResult/, 'expected tools to return LanguageModelToolResult');
});

// ── Gap integration: shared deps ─────────────────────────────────────

test('chat participant and language model tools share workspace resolution deps', () => {
    expectSource(/copilotIntegrationDeps: ChatParticipantDeps & LanguageModelToolDeps/, 'expected shared deps type');
    expectSource(/copilotIntegrationDeps[\s\S]*getCliPath/, 'expected shared deps wired with getCliPath');
    expectSource(/copilotIntegrationDeps[\s\S]*isCliAvailable/, 'expected shared deps wired with isCliAvailable');
    expectSource(/copilotIntegrationDeps[\s\S]*resolveWorkspaceFolder/, 'expected shared deps wired with resolveWorkspaceFolder');
});

// ── AI Blame decorations ─────────────────────────────────────────────

test('AI blame decorations module is wired into extension activation', () => {
    expectSource(/registerAIBlameDecorations\(context/, 'expected AI blame registration call');
    expectSource(/invalidateReceiptIndex/, 'expected receipt index invalidation on ledger change');
});

test('AI blame decorations implement git blame cross-reference with receipts', () => {
    const blameSource = fs.readFileSync(path.join(__dirname, '..', 'src', 'ai_blame_decorations.ts'), 'utf-8');
    const expectBlame = (pattern, msg) => assert.match(blameSource, pattern, msg);

    expectBlame(/blame.*--porcelain/, 'expected porcelain git blame call');
    expectBlame(/createTextEditorDecorationType/, 'expected decoration type creation');
    expectBlame(/setDecorations/, 'expected decoration application');
    expectBlame(/getReceiptSummary/, 'expected AI blame to use canonical receipt summary lookup');
    expectBlame(/lineAt\(endLineNumber\)\.range\.end\.character/, 'expected full-line blame decoration ranges');
    expectBlame(/registerCommand\('aiir\.toggleAIBlame'/, 'expected toggle command registration');
    expectBlame(/onDidChangeActiveTextEditor/, 'expected editor change listener');
});
