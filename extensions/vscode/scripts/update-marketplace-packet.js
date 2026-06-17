const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const PACKAGE_JSON_PATH = path.join(ROOT, 'package.json');
const RELEASE_DIR = path.join(ROOT, 'docs', 'release');
const SUBMISSION_PATH = path.join(RELEASE_DIR, 'MARKETPLACE_SUBMISSION.md');
const EXECUTION_SHEET_PATH = path.join(RELEASE_DIR, 'MARKETPLACE_EXECUTION_SHEET.md');

function buildScreenshots(data) {
    const coverageView = data.sidebarViews.find(view => view === 'Coverage') || 'Coverage';
    const statusView = data.sidebarViews.find(view => view === 'Status') || 'Status';
    const receiptsView = data.sidebarViews.find(view => view === 'Receipts') || 'Receipts';

    return [
        {
            asset: '01-home-view.png',
            title: 'Coverage View',
            caption: 'Show the core record loop in one place: repository coverage, receipt state, and the next trusted action.',
            goal: 'show the current AIIR sidebar model and the main coverage state',
            mustInclude: `activity bar icon, \`${coverageView}\`, \`${statusView}\`, \`${receiptsView}\`, the primary next action, and \`${data.commandTitles.generatePreferredLabel}\` visible in the workflow`,
            targetSurface: `\`${coverageView}\` tree view`,
            requiredState: 'Single repository open; receipts present or setup state intentionally chosen',
            evidence: `Manifest and \`${coverageView}\` contribution confirm the primary view exists`,
            captureStatus: 'Ready with validation',
            notes: 'Capture the actual coverage tree, not older mockups.'
        },
        {
            asset: '02-setup-and-readiness.png',
            title: 'Setup and Readiness',
            caption: 'Show a blocked repository resolving cleanly through one local-first recovery path.',
            goal: 'show first-run clarity and remembered-action recovery',
            mustInclude: `\`${data.commandTitles.readinessCheckLabel}\`, local-only posture copy, CLI guidance, and \`Continue What You Started\` when available`,
            targetSurface: `\`${data.commandTitles.readinessCheck}\``,
            requiredState: 'Prefer pending-action recovery visible',
            evidence: '`readiness_panel.ts` confirms `Continue What You Started` exists when pending action is present',
            captureStatus: 'Ready with setup',
            notes: 'Best captured after triggering a blocked action, then opening setup.'
        },
        {
            asset: '03-receipt-explorer-and-viewer.png',
            title: 'Receipts View and Viewer',
            caption: 'Inspect the receipt, verify active-tool capture or deterministic provenance, and share proof from the same workflow.',
            goal: 'show the inspection and sharing loop plus the source-capture story',
            mustInclude: `grouped receipt items plus the receipt viewer with \`${data.commandTitles.copyReceiptSummaryLabel}\`, \`Preview Receipt Summary\`, and a visible AI or provenance summary`,
            targetSurface: `\`${receiptsView}\` + viewer`,
            requiredState: 'Repo with receipts; open one receipt',
            evidence: 'Manifest and viewer code confirm explorer plus viewer actions',
            captureStatus: 'Ready',
            notes: 'Use one valid receipt and one human-readable commit subject.'
        }
    ];
}

function buildFeatureHighlights(data) {
    const coverageView = data.sidebarViews.find(view => view === 'Coverage') || 'Coverage';
    const statusView = data.sidebarViews.find(view => view === 'Status') || 'Status';

    return [
        `Run \`${data.commandTitles.generatePreferredLabel}\` from the editor or SCM title bar, then inspect or share the result without leaving VS Code.`,
        'Capture active AI tools only, instead of treating installed-but-idle extensions as used.',
        `Use \`${data.commandTitles.generateWithProvenanceLabel}\` when you want deterministic editor provenance attached to the receipt.`,
        'Verify existing AIIR receipts directly in the editor with diagnostics, CodeLens, and a commit-centered receipts view.',
        `Use \`${data.commandTitles.walkthroughLabel}\`, \`${data.commandTitles.readinessCheckLabel}\`, and remembered-action recovery so setup stays in the same flow as recording the commit.`,
        `Keep the default shell focused on \`${statusView}\`, \`${coverageView}\`, and receipts, with a local-only posture on by default.`,
        `Report issues directly from VS Code through the public \`${data.commandTitles.reportBug}\` flow.`
    ];
}

function buildReleaseNotes(data) {
    const shell = data.sidebarViews.map(view => `\`${view}\``).join(' and ');
    return [
        `Keeps the extension focused on the shipped AIIR sidebar: ${shell}.`,
        'Highlights active-tool-only capture and the editor-side source evidence story in public listing copy.',
        `Calls out \`${data.commandTitles.generateWithProvenanceLabel}\` as the path to deterministic editor provenance.`,
        'Adds remembered-action recovery so setup can resume receipt generation, initialization, and automation once the CLI is ready.',
        'Keeps the extension local-only by default while leaving rollout and network-backed surfaces explicitly opt-in.',
        'Adds a public in-product bug-report flow for support and triage.',
        'Uses the same public shield badge as invariantsystems.io for Marketplace and extension branding.'
    ];
}

const LISTING_PRIORITIES = [
    'show a credible local-first proof workflow',
    'show active-tool capture and deterministic provenance as the differentiator',
    'verify receipts inside VS Code',
    'onboard a repository quickly',
    'stay local-only by default without leading with admin surfaces',
    'make support visible with a public bug-report path'
];

function buildScreenshotGuidance(data) {
    const shell = data.sidebarViews.map(view => `\`${view}\``).join(' and ');
    return [
        'Use a repository that already contains AIIR receipts.',
        'Prefer clean, deterministic sample data and public-safe commit subjects.',
        'Keep local-only mode enabled unless a screenshot explicitly demonstrates Hub evaluation.',
        'Show one strong UI surface per screenshot instead of dense multi-panel captures.',
        'Favor calm, legible screenshots that look audit-ready rather than developer-busy.',
        'Keep the branded activity bar icon visible in at least one shot.',
        'Use the public website shield badge as the packaged icon and keep the infinity-eyes plus checkmark-mouth mark visible in screenshots where the icon appears.',
        `Use the current shipped AIIR shell: ${shell}. Do not capture older \`Actions\` or \`Posture\` sidebar layouts.`,
        'Prefer a light VS Code theme for Marketplace readability unless a specific surface is materially clearer in dark mode.',
        'Keep commit subjects, repository names, and paths public-safe and screenshot-ready.',
        'If showing the setup panel, prefer a state where recovery is visible rather than a fully-ready idle state.'
    ];
}

function buildCaptureNotes(data) {
    const shell = data.sidebarViews.map(view => `\`${view}\``).join(' and ');
    return [
        `Capture the current AIIR product shell: ${shell}.`,
        'Do not use older screenshots that show `Actions` or `Posture` as separate sidebar views.',
        'Prefer screenshots with stable, legible repository names and commit subjects over highly active or noisy states.',
        'Prefer a setup-state screenshot where remembered-action recovery is visible.',
        'Prefer a receipt-viewer screenshot where `Copy Receipt Summary`, `Preview Receipt Summary`, and `Open Receipt JSON` are all visible.',
        'Keep repository names, commit subjects, and visible paths public-safe.'
    ];
}

function buildBuildValidation(data) {
    const shell = data.sidebarViews.map(view => `\`${view}\``).join(' and ');
    return [
        'Run `npm run package` from `extensions/vscode` before publishing so the current VSIX is fresh.',
        'Run `npm test` in the same checkout before publishing so manifest, navigation, and onboarding expectations stay aligned.',
        'Run the full adversarial manual release pass in `docs/operations/SMOKE_TEST.md` against the packaged VSIX before judging the candidate release-ready.',
        'Use `docs/operations/UI_SMOKE_THREAT_MODEL.md` when deciding whether a wounded flow is a release blocker or acceptable follow-up.',
        'Record the manual verdicts, friction notes, and saved evidence directly in `docs/release/DEEP_SMOKE_RUN_2026-03-15.md` so the release packet captures more than green automated checks.',
        'The empty-state welcome should start with `Check what\'s ready` and `Open getting started`, with CLI install helpers retained as recovery actions.',
        `The shipped status surfaces should use one compact \`Current repository status\` row plus \`${data.commandTitles.readinessCheckLabel}\` and \`${data.commandTitles.healthCheckLabel}\` actions instead of the older multi-row diagnostic layout.`,
        `\`${data.commandTitles.generatePreferredLabel}\` should remain the primary first-run path, while \`${data.commandTitles.generateWithProvenanceLabel}\` stays the explicit stronger-evidence option.`,
        'The shipped copy should describe the default single-repository posture as workspace-scoped and local-only, with explicit allowlisting framed as a tighter multi-root control.',
        `The packaged shell should keep ${shell} as the only default contributed sidebar views.`,
        'The shipped README and listing copy should continue to position the extension around record, inspect, share, active-tool capture, and optional deterministic provenance.',
        'The VSIX should not ship the extension docs tree; only runtime assets, README, changelog, license, media, and compiled output belong in the package.',
        'A clean-profile install should succeed with `code-insiders --user-data-dir <temp> --extensions-dir <temp> --install-extension aiir-<version>.vsix --force`.',
        'A native clean-profile launch should show the AIIR activity-bar icon and avoid extension crashes; remove workspace-trust and startup-editor noise in the capture profile before judging the first frame.'
    ];
}

function buildResolvedProductAnswers(data) {
    return [
        `Keep \`${data.sidebarViews[1] || 'Status'}\` as the public state view name for this release.`,
        'Keep `Coverage` repository-scoped first in Marketplace capture so the listing shows one repository state rather than a workspace aggregate.',
        'Lead the public listing with record, inspect, and share surfaces instead of rollout or admin pages.',
        'Treat unsigned-but-valid receipts as healthy only in the default local workflow; stricter regulated capture should be shown intentionally as a different state.',
        'Keep browser handoff plus refresh as the public Hub pattern; no release asset should imply a deep-link return path that is not required by the current implementation.'
    ];
}

function buildPreCaptureSetup(data) {
    return [
        'Build and install the current VSIX from `extensions/vscode`.',
        'Use a clean VS Code profile so stale settings and hidden internal surfaces do not leak into screenshots.',
        'In the capture profile, disable the workspace-trust prompt or pre-trust the repository before taking screenshots; otherwise the first frame is blocked by VS Code chrome instead of AIIR.',
        'Set `workbench.startupEditor` to `none` in the capture profile so the default VS Code welcome/editor surface does not displace the first AIIR shot.',
        'Open one public-safe repository with deterministic sample data and at least one valid receipt.',
        'Leave `aiir.strictLocalOnly` enabled for the main Marketplace set.'
    ];
}

function buildExecutionSteps(data) {
    return [
        'Capture `Coverage` first with the normal local workflow state you want to present.',
        'Trigger a resumable setup path, then capture `Setup and Readiness` while `Continue What You Started` is visible.',
        'Open a receipt from `Receipts` and capture the explorer plus viewer in one frame, making active-tool capture or deterministic provenance visible.'
    ];
}

function buildVersioningNote() {
    return [
        'The extension can be versioned independently in principle because it has its own `extensions/vscode/package.json`.',
        'The publish lane now respects the version already declared in `extensions/vscode/package.json`; it no longer rewrites the extension version from the repo release tag.',
        'Repo release tags still trigger the GitHub Actions publish workflow, but the Marketplace version comes from the extension manifest, not the tag name.'
    ];
}

function buildPublishSequence() {
    return [
        'Land the extension changes through a PR branch. Do not publish from a local dirty tree.',
        'Bump the extension version in `extensions/vscode/package.json` and `extensions/vscode/package-lock.json` before release packaging.',
        'After merge, publish through the next repo release tag or a deliberate sidecar publish run; in both cases the VSIX and Marketplace version come from the extension manifest.',
        'Confirm the workflow or local publish logs show all of the following in order: extension version read from manifest, `npm ci`, compile, `npm test`, `npm run marketplace:sync`, VSIX package, VSIX upload or publish.',
        'If `VSCE_PAT` is missing, treat the run as incomplete even if the VSIX was attached to GitHub Release.'
    ];
}

function buildPostPublishVerification() {
    return [
        'Open the Marketplace listing and confirm the visible version matches `extensions/vscode/package.json`.',
        'Confirm the listing body reflects the current README story: record, inspect, share; active-tool capture; deterministic provenance; local-only defaults.',
        'Confirm the requirements section reflects `VS Code 1.95 or newer` and the current CLI install path.',
        'Confirm the GitHub release has the matching `.vsix` attached.',
        'If Open VSX publish was enabled, confirm the same version appears there as well.',
        'Record the publish timestamp and verification result in `docs/release/DEEP_SMOKE_RUN_2026-03-15.md` so the release packet captures when the public listing actually caught up.'
    ];
}

function buildManualReleaseGate() {
    return [
        'Execute the full manual matrix in `docs/operations/SMOKE_TEST.md` against the packaged VSIX, not the source checkout alone.',
        'Judge each phase with the release-layer failure classes in `docs/operations/UI_SMOKE_THREAT_MODEL.md` so `WOUNDED` does not get flattened into `PASS`.',
        'Save the run in `docs/release/DEEP_SMOKE_RUN_2026-03-15.md`, including PASS/WOUNDED/FAIL verdicts, friction notes, and the exact screenshots or notes captured for first paint, empty state, blocked state, and healthy state.',
    ];
}

function buildWhatIsSolid(data) {
    const shell = data.sidebarViews.map(view => `\`${view}\``).join(' and ');
    return [
        `The shipped manifest, README copy, and release docs all agree on the AIIR shell: ${shell}.`,
        'The public story is now anchored on active-tool capture and deterministic provenance instead of generic operator surface area.',
        'The setup screenshot is well-supported by current code because `readiness_panel.ts` renders `Continue What You Started` when a pending action exists.',
        'The receipt-viewer screenshot is well-supported by current code because the viewer exposes `Copy Receipt Summary`, `Preview Receipt Summary`, and `Open Receipt JSON`.',
        'The public listing narrative is aligned with the current local-first UX simplification instead of the older multi-surface onboarding story.'
    ];
}

function buildNeedsCare(data) {
    return [
        'The coverage shot should follow the actual built tree contents rather than older checklists that assume fixed group labels.',
        'The public listing can drift back into operator language if screenshots or captions start foregrounding rollout, policy, or Hub surfaces.',
        'The setup and readiness screenshot depends on a transient state; if the repository is already fully healthy, the strongest first-run capture disappears.',
        'A truly clean profile does not land on AIIR by itself. Even after removing trust and startup walkthrough noise, Explorer remains the selected container on first paint, so capture still needs an explicit switch into the AIIR activity-bar container.'
    ];
}

function buildRiskAssessment(data) {
    return [
        'Highest documentation risk: older coverage or status screenshot checklists can over-prescribe UI details that are not guaranteed by the current state-driven providers.',
        'Highest operational risk: drifting back into admin-surface captures and losing the high-conversion record, inspect, and share story.',
        'Remaining validation gap: native clean launch is validated, but final Marketplace screenshots still require one manual or scripted switch into the AIIR container before capture.',
        'Lowest risk asset: the receipts plus viewer shot, because both surfaces are explicit, stable, and directly backed by current code.'
    ];
}

function buildGoNoGo(data) {
    return [
        'Go for `Coverage`, `Setup and Readiness`, and `Receipts + Viewer` from the default local-only build.',
        'No-go on leading the public listing with control, rollout, or Hub surfaces when the goal is high-conversion onboarding.',
        'No-go on using older screenshot instructions as literal UI truth where they conflict with the built extension.',
        'Go on packaging and local validation for the current artifact, but treat final screenshot quality as a release-grade asset rather than a documentation afterthought.'
    ];
}

function loadManifest() {
    return JSON.parse(fs.readFileSync(PACKAGE_JSON_PATH, 'utf8'));
}

function requireCommandTitle(commands, commandId) {
    const title = commands.find(command => command.command === commandId)?.title;
    if (!title) {
        throw new Error(`Required command title missing from package.json: ${commandId}`);
    }
    return title;
}

function stripAiirPrefix(title) {
    return title.replace(/^AIIR:\s*/, '');
}

function buildMarketplaceNarrative() {
    return {
        shortDescription: 'Local-first AI integrity receipts for git commits with active tool context.',
        overview: 'AIIR brings AI integrity receipts into VS Code so teams can record the current commit, inspect what was captured, and share proof without leaving the editor. The extension carries active AI tool context into receipts, can attach deterministic editor provenance for stronger source evidence, starts local-first, and keeps setup and recovery inside the same workflow.'
    };
}

function getManifestData() {
    const manifest = loadManifest();
    const commands = manifest.contributes.commands || [];
    const activitybar = manifest.contributes.viewsContainers?.activitybar || [];
    const sidebarViews = (manifest.contributes.views?.aiir || []).map(view => view.name);
    const configuration = manifest.contributes.configuration?.properties || {};
    const marketplaceNarrative = buildMarketplaceNarrative();

    return {
        version: manifest.version,
        shortDescription: marketplaceNarrative.shortDescription,
        overview: marketplaceNarrative.overview,
        supportLink: manifest.bugs?.url || '',
        activityBarTitle: activitybar.find(container => container.id === 'aiir')?.title || 'AIIR Receipts',
        sidebarViews,
        strictLocalOnly: configuration['aiir.strictLocalOnly']?.default,
        showAdvancedCommands: configuration['aiir.showAdvancedCommands']?.default,
        commandTitles: {
            generatePreferred: requireCommandTitle(commands, 'aiir.generatePreferred'),
            generatePreferredLabel: stripAiirPrefix(requireCommandTitle(commands, 'aiir.generatePreferred')),
            generateWithProvenance: requireCommandTitle(commands, 'aiir.generateWithProvenance'),
            generateWithProvenanceLabel: stripAiirPrefix(requireCommandTitle(commands, 'aiir.generateWithProvenance')),
            copyReceiptSummary: requireCommandTitle(commands, 'aiir.copyReceiptSummary'),
            copyReceiptSummaryLabel: stripAiirPrefix(requireCommandTitle(commands, 'aiir.copyReceiptSummary')),
            reportBug: requireCommandTitle(commands, 'aiir.reportBug'),
            readinessCheck: requireCommandTitle(commands, 'aiir.readinessCheck'),
            readinessCheckLabel: stripAiirPrefix(requireCommandTitle(commands, 'aiir.readinessCheck')),
            securityPosture: requireCommandTitle(commands, 'aiir.securityPosture'),
            securityPostureLabel: stripAiirPrefix(requireCommandTitle(commands, 'aiir.securityPosture')),
            deploymentPresets: requireCommandTitle(commands, 'aiir.rolloutPresets'),
            deploymentPresetsLabel: stripAiirPrefix(requireCommandTitle(commands, 'aiir.rolloutPresets')),
            controlPanel: requireCommandTitle(commands, 'aiir.controlPanel'),
            controlPanelLabel: stripAiirPrefix(requireCommandTitle(commands, 'aiir.controlPanel')),
            healthCheckLabel: stripAiirPrefix(requireCommandTitle(commands, 'aiir.healthCheck')),
            walkthroughLabel: stripAiirPrefix(requireCommandTitle(commands, 'aiir.openWalkthrough')),
            hubPlans: requireCommandTitle(commands, 'aiir.hubBilling'),
            hubPlansLabel: stripAiirPrefix(requireCommandTitle(commands, 'aiir.hubBilling'))
        }
    };
}

function renderBulletList(items) {
    return items.map(item => `- ${item}`).join('\n');
}

function renderNumberedList(items) {
    return items.map((item, index) => `${index + 1}. ${item}`).join('\n');
}

function renderScreenshotOrder(screenshots) {
    return screenshots.map((shot, index) => `${index + 1}. \`${shot.title}\`\n   Caption: ${shot.caption}`).join('\n\n');
}

function renderScreenshotChecklist(screenshots) {
    return screenshots.map((shot, index) => `${index + 1}. \`${shot.asset}\`\n   Goal: ${shot.goal}.\n   Must include: ${shot.mustInclude}.`).join('\n\n');
}

function renderCaptureMatrix(screenshots) {
    const header = '| Asset | Target surface | Required state | Current evidence in code | Capture status | Notes |';
    const divider = '|---|---|---|---|---|---|';
    const rows = screenshots.map(shot => `| \`${shot.asset}\` | ${shot.targetSurface} | ${shot.requiredState} | ${shot.evidence} | ${shot.captureStatus} | ${shot.notes} |`);
    return [header, divider, ...rows].join('\n');
}

function renderGeneratedBanner() {
    return '<!-- Generated by scripts/update-marketplace-packet.js. Run npm run marketplace:sync. -->';
}

function renderSubmission(data) {
    const screenshots = buildScreenshots(data);
    const featureHighlights = buildFeatureHighlights(data);
    const releaseNotes = buildReleaseNotes(data);
    const captureNotes = buildCaptureNotes(data);
    return `${renderGeneratedBanner()}\n# AIIR VS Code Marketplace Submission\n\nUse this file as the publisher-ready copy bundle for the VS Code Marketplace listing.\n\nFor capture sequencing, blockers, and current-surface validation notes, use \`MARKETPLACE_EXECUTION_SHEET.md\`.\n\nThis file also serves as the screenshot order and listing plan for the current public Marketplace submission.\n\n## Short Description\n\n${data.shortDescription}\n\n## Overview\n\n${data.overview}\n\n## Feature Highlights\n\n${renderBulletList(featureHighlights)}\n\n## Screenshot Order And Captions\n\n${renderScreenshotOrder(screenshots)}\n\n## Screenshot Capture Notes\n\n${renderBulletList(captureNotes)}\n\n## Release Notes Bullets\n\n${renderBulletList(releaseNotes)}\n\n## Support Link\n\n- Public issues: \`${data.supportLink}\`\n- In-product support: \`${data.commandTitles.reportBug}\`\n\n## Branding Note\n\n- The packaged Marketplace icon uses the public invariantsystems.io shield badge.\n- The activity bar icon uses the same shield, infinity-eyes, and checkmark-mouth mark in a monochrome small-size variant.\n- Keep that public badge visible anywhere iconography appears in screenshots or release collateral.\n`;
}

function renderExecutionSheet(data) {
    const screenshots = buildScreenshots(data);
    const versioningNote = buildVersioningNote();
    const buildValidation = buildBuildValidation(data);
    const resolvedProductAnswers = buildResolvedProductAnswers(data);
    const preCaptureSetup = buildPreCaptureSetup(data);
    const executionSteps = buildExecutionSteps(data);
    const publishSequence = buildPublishSequence();
    const postPublishVerification = buildPostPublishVerification();
    const manualReleaseGate = buildManualReleaseGate();
    const whatIsSolid = buildWhatIsSolid(data);
    const needsCare = buildNeedsCare(data);
    const riskAssessment = buildRiskAssessment(data);
    const goNoGo = buildGoNoGo(data);
    return `${renderGeneratedBanner()}\n# AIIR VS Code Marketplace Execution Sheet\n\nUse this sheet to run the release capture pass from the current public extension build instead of relying on older plans or memory.\n\n## Release Baseline\n\n- Extension version in \`package.json\`: \`${data.version}\`\n- Current activity-bar container: \`${data.activityBarTitle}\`\n- Current sidebar views: ${data.sidebarViews.map(view => `\`${view}\``).join(', ')}\n- Local-only default: \`aiir.strictLocalOnly = ${String(data.strictLocalOnly)}\`\n- Advanced operator surfaces hidden by default: \`aiir.showAdvancedCommands = ${String(data.showAdvancedCommands)}\`\n\n## Versioning Note\n\n${renderBulletList(versioningNote)}\n\n## Build Validation\n\n${renderBulletList(buildValidation)}\n\n## Resolved Product Answers\n\n${renderBulletList(resolvedProductAnswers)}\n\n## Capture Matrix\n\n${renderCaptureMatrix(screenshots)}\n\n## Required Pre-Capture Setup\n\n${renderNumberedList(preCaptureSetup)}\n\n## Execution Steps\n\n${renderNumberedList(executionSteps)}\n\n## Publish Sequence\n\n${renderNumberedList(publishSequence)}\n\n## Post-Publish Verification\n\n${renderNumberedList(postPublishVerification)}\n\n## Manual Release Gate\n\n${renderBulletList(manualReleaseGate)}\n\n## Deep Analysis\n\n### What is solid\n\n${renderBulletList(whatIsSolid)}\n\n### What needs care\n\n${renderBulletList(needsCare)}\n\n### Risk assessment\n\n${renderBulletList(riskAssessment)}\n\n## Go/No-Go Summary\n\n${renderBulletList(goNoGo)}\n`;
}

function generatePacketDocuments() {
    const data = getManifestData();
    return {
        [SUBMISSION_PATH]: renderSubmission(data),
        [EXECUTION_SHEET_PATH]: renderExecutionSheet(data)
    };
}

function writeDocuments(documents) {
    const updated = [];
    for (const [filePath, content] of Object.entries(documents)) {
        const normalized = `${content.trim()}\n`;
        const previous = fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8') : '';
        if (previous !== normalized) {
            fs.writeFileSync(filePath, normalized, 'utf8');
            updated.push(path.relative(ROOT, filePath));
        }
    }
    return updated;
}

function main() {
    const updated = writeDocuments(generatePacketDocuments());
    if (updated.length === 0) {
        console.log('Marketplace packet already up to date.');
        return;
    }

    for (const file of updated) {
        console.log(`Updated ${file}`);
    }
}

if (require.main === module) {
    main();
}

module.exports = {
    EXECUTION_SHEET_PATH,
    SUBMISSION_PATH,
    generatePacketDocuments,
    getManifestData,
    renderExecutionSheet,
    renderSubmission
};
