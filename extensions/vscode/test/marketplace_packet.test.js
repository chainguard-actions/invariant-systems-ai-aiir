const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const {
    EXECUTION_SHEET_PATH,
    SUBMISSION_PATH,
    generatePacketDocuments
} = require('../scripts/update-marketplace-packet.js');

const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));

function getCommandTitle(commandId) {
    const title = manifest.contributes.commands.find((command) => command.command === commandId)?.title;
    assert.ok(title, `missing command title for ${commandId}`);
    return title;
}

function getCommandLabel(commandId) {
    return getCommandTitle(commandId).replace(/^AIIR:\s*/, '');
}

test('marketplace packet docs stay in sync with the generator', () => {
    const generated = generatePacketDocuments();

    for (const [filePath, expected] of Object.entries(generated)) {
        const actual = fs.readFileSync(filePath, 'utf8');
        assert.equal(actual, `${expected.trim()}\n`, `${filePath} is out of date; run npm run marketplace:sync`);
    }
});

test('marketplace packet generator covers all public release packet files', () => {
    const generated = generatePacketDocuments();
    assert.deepEqual(
        Object.keys(generated).sort(),
        [EXECUTION_SHEET_PATH, SUBMISSION_PATH].sort()
    );
});

test('marketplace packet generator uses manifest command titles in generated docs', () => {
    const generated = generatePacketDocuments();
    const executionSheet = generated[EXECUTION_SHEET_PATH];
    const submission = generated[SUBMISSION_PATH];

    for (const commandId of [
        'aiir.generatePreferred',
        'aiir.generateWithProvenance',
        'aiir.readinessCheck',
        'aiir.copyReceiptSummary',
        'aiir.reportBug',
    ]) {
        const title = getCommandTitle(commandId);
        const label = getCommandLabel(commandId);
        assert.match(
            `${executionSheet}\n${submission}`,
            new RegExp(`(${title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}|${label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`)
        );
    }
});

test('marketplace execution sheet keeps the deep manual smoke gate in generated output', () => {
    const generated = generatePacketDocuments();
    const executionSheet = generated[EXECUTION_SHEET_PATH];

    for (const expected of [
        'Run the full adversarial manual release pass in `docs/operations/SMOKE_TEST.md` against the packaged VSIX before judging the candidate release-ready.',
        'Use `docs/operations/UI_SMOKE_THREAT_MODEL.md` when deciding whether a wounded flow is a release blocker or acceptable follow-up.',
        'Record the manual verdicts, friction notes, and saved evidence directly in `docs/release/DEEP_SMOKE_RUN_2026-03-15.md` so the release packet captures more than green automated checks.',
        'Save the run in `docs/release/DEEP_SMOKE_RUN_2026-03-15.md`, including PASS/WOUNDED/FAIL verdicts, friction notes, and the exact screenshots or notes captured for first paint, empty state, blocked state, and healthy state.',
        '## Manual Release Gate',
    ]) {
        assert.match(executionSheet, new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    }
});

test('marketplace execution sheet includes release versioning and publish verification guidance', () => {
    const generated = generatePacketDocuments();
    const executionSheet = generated[EXECUTION_SHEET_PATH];

    for (const expected of [
        '## Versioning Note',
        'The publish lane now respects the version already declared in `extensions/vscode/package.json`; it no longer rewrites the extension version from the repo release tag.',
        '## Publish Sequence',
        'Confirm the workflow or local publish logs show all of the following in order: extension version read from manifest, `npm ci`, compile, `npm test`, `npm run marketplace:sync`, VSIX package, VSIX upload or publish.',
        '## Post-Publish Verification',
        'Confirm the requirements section reflects `VS Code 1.95 or newer` and the current CLI install path.',
    ]) {
        assert.match(executionSheet, new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    }
});
