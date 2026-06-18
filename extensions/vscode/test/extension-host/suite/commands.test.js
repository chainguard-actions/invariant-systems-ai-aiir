const assert = require('node:assert/strict');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const vscode = require('vscode');

const { setLanguageModelBridgeForTests } = require('../../../out/language_model_bridge.js');

function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitFor(assertion, message, timeoutMs = 5000, intervalMs = 100) {
    const deadline = Date.now() + timeoutMs;
    let lastError;

    while (Date.now() < deadline) {
        try {
            const result = await assertion();
            if (result) {
                return;
            }
            lastError = new Error(message);
        } catch (error) {
            lastError = error;
        }

        await delay(intervalMs);
    }

    throw lastError || new Error(message);
}

const fixtureWorkspacePath = path.resolve(__dirname, '..', '..', 'fixtures', 'sample-workspace');
const fakeCliScriptPath = path.resolve(__dirname, '..', '..', 'fixtures', 'fake-aiir-cli.js');

async function closeAllEditors() {
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    await delay(150);
}

async function activateExtension() {
    const extension = vscode.extensions.getExtension('invariant-systems.aiir');
    assert.ok(extension, 'expected the AIIR extension to be available in the extension host');

    await extension.activate();
}

function getWorkspaceFolder() {
    const folder = vscode.workspace.workspaceFolders?.[0];
    assert.ok(folder, 'expected a workspace folder for extension-host tests');
    return folder;
}

async function removeWorkspaceAiirState() {
    const aiirDir = path.join(fixtureWorkspacePath, '.aiir');
    for (let attempt = 0; attempt < 10; attempt += 1) {
        try {
            await fsp.rm(aiirDir, { recursive: true, force: true });
            return;
        } catch (error) {
            if (error && error.code !== 'ENOTEMPTY' && error.code !== 'EBUSY') {
                throw error;
            }
            await delay(250);
        }
    }

    await fsp.rm(aiirDir, { recursive: true, force: true });
}

async function updateWorkspaceFoldersWithRetry(start, deleteCount, ...workspaceFoldersToAdd) {
    for (let attempt = 0; attempt < 10; attempt += 1) {
        const updated = vscode.workspace.updateWorkspaceFolders(start, deleteCount, ...workspaceFoldersToAdd);
        if (updated) {
            await delay(500);
            return;
        }

        await delay(250);
    }

    assert.fail('expected workspace folder update to succeed');
}

async function removeAdditionalWorkspaceFolders() {
    const folders = vscode.workspace.workspaceFolders ?? [];
    if (folders.length <= 1) {
        return;
    }

    await updateWorkspaceFoldersWithRetry(1, folders.length - 1);
}

async function withAdditionalWorkspaceFolder(name, callback) {
    const root = await fsp.mkdtemp(path.join(os.tmpdir(), 'aiir-vscode-workspace-'));
    const folderPath = path.join(root, name);
    await fsp.mkdir(folderPath, { recursive: true });
    await fsp.writeFile(path.join(folderPath, 'README.md'), `# ${name}\n`, 'utf8');

    await updateWorkspaceFoldersWithRetry(
        vscode.workspace.workspaceFolders?.length ?? 0,
        0,
        { uri: vscode.Uri.file(folderPath), name },
    );

    const folder = (vscode.workspace.workspaceFolders ?? []).find(candidate => candidate.uri.fsPath === folderPath);
    assert.ok(folder, 'expected additional workspace folder to be available');

    try {
        await callback(folder);
    } finally {
        const folders = vscode.workspace.workspaceFolders ?? [];
        const index = folders.findIndex(candidate => candidate.uri.fsPath === folderPath);
        if (index >= 0) {
            await updateWorkspaceFoldersWithRetry(index, 1);
        }
        await fsp.rm(root, { recursive: true, force: true });
    }
}

async function createFakeCliHarness() {
    const root = await fsp.mkdtemp(path.join(os.tmpdir(), 'aiir-vscode-fake-cli-'));
    const wrapperPath = process.platform === 'win32'
        ? path.join(root, 'aiir-test.cmd')
        : path.join(root, 'aiir-test');
    const logPath = path.join(root, 'invocations.jsonl');
    const wrapper = process.platform === 'win32'
        ? `@echo off\r\n"${process.execPath}" "${fakeCliScriptPath}" %*\r\n`
        : `#!/bin/sh\nexec "${process.execPath}" "${fakeCliScriptPath}" "$@"\n`;

    await fsp.writeFile(wrapperPath, wrapper, 'utf8');
    if (process.platform !== 'win32') {
        await fsp.chmod(wrapperPath, 0o755);
    }

    return { root, wrapperPath, logPath };
}

async function readFakeCliLog(logPath) {
    try {
        const raw = await fsp.readFile(logPath, 'utf8');
        return raw
            .split(/\r?\n/)
            .map(line => line.trim())
            .filter(Boolean)
            .map(line => JSON.parse(line));
    } catch (error) {
        if (error && error.code === 'ENOENT') {
            return [];
        }
        throw error;
    }
}

async function withFakeCliHarness(callback) {
    const harness = await createFakeCliHarness();
    process.env.AIIR_FAKE_CLI_LOG = harness.logPath;
    await vscode.workspace.getConfiguration('aiir').update('cliPath', harness.wrapperPath, vscode.ConfigurationTarget.Global);

    try {
        await callback(harness);
    } finally {
        await fsp.rm(harness.root, { recursive: true, force: true });
    }
}

async function openCommandAndExpectTab(commandId, expectedLabel) {
    await closeAllEditors();
    await vscode.commands.executeCommand(commandId);
    await delay(250);

    const labels = vscode.window.tabGroups.all.flatMap(group => group.tabs.map(tab => tab.label));
    assert.equal(labels.includes(expectedLabel), true, `expected tab '${expectedLabel}' after ${commandId}`);
}

describe('AIIR extension-host smoke', () => {
    before(async () => {
        await activateExtension();
    });

    afterEach(async () => {
        await closeAllEditors();
        await removeWorkspaceAiirState();
        await removeAdditionalWorkspaceFolders();
        delete process.env.AIIR_FAKE_CLI_LOG;
        setLanguageModelBridgeForTests();
        await vscode.workspace.getConfiguration('aiir').update('cliPath', undefined, vscode.ConfigurationTarget.Global);
        await vscode.workspace.getConfiguration('aiir').update('lockPreset', undefined, vscode.ConfigurationTarget.Workspace);
        await vscode.workspace.getConfiguration('aiir').update('strictLocalOnly', undefined, vscode.ConfigurationTarget.Workspace);
        await vscode.workspace.getConfiguration('aiir').update('enableHubFeatures', undefined, vscode.ConfigurationTarget.Workspace);
        await vscode.workspace.getConfiguration('aiir').update('enforceWorkspaceIsolation', undefined, vscode.ConfigurationTarget.Workspace);
        await vscode.workspace.getConfiguration('aiir').update('allowedWorkspaceFolders', undefined, vscode.ConfigurationTarget.Workspace);
    });

    it('registers the onboarding and operator commands', async () => {
        const commands = await vscode.commands.getCommands(true);

        for (const commandId of [
            'aiir.generatePreferred',
            'aiir.generateReceiptForCommit',
            'aiir.installCliNow',
            'aiir.installSigstoreSupport',
            'aiir.readinessCheck',
            'aiir.healthCheck',
            'aiir.securityPosture',
            'aiir.rolloutPresets',
            'aiir.advancedSettings',
            'aiir.hubBilling',
            'aiir.openWalkthrough',
            'aiir.switchRepository',
        ]) {
            assert.equal(commands.includes(commandId), true, `expected command ${commandId}`);
        }
    });

    it('opens the setup and operator webviews without throwing', async () => {
        await openCommandAndExpectTab('aiir.readinessCheck', 'AIIR Commit Status');
        await openCommandAndExpectTab('aiir.healthCheck', 'AIIR Health Check');
        await openCommandAndExpectTab('aiir.securityPosture', 'AIIR Security Posture');
        await openCommandAndExpectTab('aiir.rolloutPresets', 'AIIR Deployment Presets');
        await openCommandAndExpectTab('aiir.advancedSettings', 'AIIR Advanced Settings');
        await openCommandAndExpectTab('aiir.hubBilling', 'AIIR Hub Plans and Access');
    });

    it('opens the contributed walkthrough command', async () => {
        await closeAllEditors();
        await vscode.commands.executeCommand('aiir.openWalkthrough');
        await delay(500);

        const commands = await vscode.commands.getCommands(true);
        assert.equal(commands.includes('aiir.openWalkthrough'), true);
    });

    it('uses the public doctor contract when opening health check through the configured CLI path', async () => {
        const folder = getWorkspaceFolder();

        await withFakeCliHarness(async (harness) => {
            await closeAllEditors();
            await vscode.commands.executeCommand('aiir.healthCheck', folder.uri);
            await delay(500);

            const log = await readFakeCliLog(harness.logPath);
            const doctorCall = log.find(entry => Array.isArray(entry.args) && entry.args[0] === '--doctor');
            assert.ok(doctorCall, 'expected doctor CLI invocation for health check');
            assert.deepEqual(doctorCall.args, ['--doctor', '--json']);
            assert.equal(doctorCall.cwd, folder.uri.fsPath, 'expected doctor to run in the workspace folder');

            const labels = vscode.window.tabGroups.all.flatMap(group => group.tabs.map(tab => tab.label));
            assert.equal(labels.includes('AIIR Health Check'), true, 'expected health check panel after doctor invocation');
        });
    });

    it('guides the CI signing preset without changing local settings', async () => {
        const originalShowInformationMessage = vscode.window.showInformationMessage;
        let guidancePromptSeen = false;

        try {
            vscode.window.showInformationMessage = async (message, ...items) => {
                const text = String(message);
                if (items.includes('Copy CI Command')) {
                    guidancePromptSeen = true;
                    assert.match(
                        text,
                        /Keep local generation provenance-first in VS Code\. Use Sigstore signing in CI or release workflows/,
                    );
                    return 'Copy CI Command';
                }

                assert.match(text, /Copied a CI signing command example/);
                return undefined;
            };

            await vscode.env.clipboard.writeText('');
            await vscode.commands.executeCommand('aiir.applyPreset', 'ci-sign-when-supported');
            await delay(250);

            const clipboard = await vscode.env.clipboard.readText();
            assert.equal(guidancePromptSeen, true, 'expected the signing guidance prompt');
            assert.equal(clipboard, 'aiir --sign --in-toto --output .receipts/');
        } finally {
            vscode.window.showInformationMessage = originalShowInformationMessage;
        }
    });

    it('initializes the repository through the configured CLI path', async () => {
        const folder = getWorkspaceFolder();
        const originalShowInformationMessage = vscode.window.showInformationMessage;

        try {
            await withFakeCliHarness(async (harness) => {
                vscode.window.showInformationMessage = async () => undefined;

                await vscode.commands.executeCommand('aiir.initializeRepo', folder.uri);
                await waitFor(async () => {
                    const log = await readFakeCliLog(harness.logPath);
                    return log.some(entry => entry.args.includes('--pretty'));
                }, 'expected starter receipt generation');

                const log = await readFakeCliLog(harness.logPath);
                assert.equal(log.some(entry => entry.args.includes('--version')), true, 'expected CLI availability probe');
                assert.equal(log.some(entry => entry.args.includes('--init')), true, 'expected CLI init invocation');
                assert.equal(log.some(entry => entry.args.includes('--pretty')), true, 'expected starter receipt generation');

                const aiirDir = path.join(folder.uri.fsPath, '.aiir');
                const queuePath = path.join(aiirDir, 'editor_provenance.jsonl');
                const ignorePath = path.join(aiirDir, '.gitignore');
                const policyPath = path.join(aiirDir, 'policy.json');
                const ledgerPath = path.join(aiirDir, 'receipts.jsonl');

                await waitFor(async () => fs.existsSync(ledgerPath) && fs.readFileSync(ledgerPath, 'utf8').includes('"type":"aiir.commit_receipt"'), 'expected starter receipt in ledger');

                assert.equal(fs.existsSync(aiirDir), true, 'expected .aiir directory after initialization');
                assert.equal(fs.existsSync(queuePath), true, 'expected provable queue file after initialization');
                assert.equal(fs.readFileSync(ignorePath, 'utf8').includes('editor_provenance.jsonl'), true, 'expected queue ignore entry');
                assert.equal(fs.existsSync(policyPath), true, 'expected repo-local policy file after initialization');
                assert.match(fs.readFileSync(ledgerPath, 'utf8'), /"type":"aiir\.commit_receipt"/, 'expected starter receipt in ledger');

                const aiirConfig = vscode.workspace.getConfiguration('aiir');
                assert.equal(aiirConfig.get('strictLocalOnly'), true, 'expected safe local-only default');
                assert.equal(aiirConfig.get('enforceWorkspaceIsolation'), true, 'expected safe isolation default');
                assert.deepEqual(aiirConfig.get('allowedWorkspaceFolders'), [folder.uri.fsPath], 'expected initialized repo allowlisted in workspace settings');
            });
        } finally {
            vscode.window.showInformationMessage = originalShowInformationMessage;
        }
    });

    it('reviews a commit through the configured CLI path with mapped outcome values', async () => {
        const folder = getWorkspaceFolder();
        const originalShowQuickPick = vscode.window.showQuickPick;
        const originalShowInputBox = vscode.window.showInputBox;

        try {
            await withFakeCliHarness(async (harness) => {
                let quickPickCall = 0;
                vscode.window.showQuickPick = async (items) => {
                    quickPickCall += 1;
                    assert.ok(Array.isArray(items), 'expected quick pick items');

                    if (quickPickCall === 1) {
                        const flagOption = items.find(item => item.value === 'flag');
                        assert.ok(flagOption, 'expected review flag option');
                        return flagOption;
                    }

                    throw new Error(`unexpected quick pick call ${quickPickCall}`);
                };

                vscode.window.showInputBox = async (options) => {
                    assert.match(String(options?.prompt || ''), /Reason for flag/);
                    return 'Needs deeper follow-up';
                };

                await vscode.commands.executeCommand('aiir.reviewReceipt', { sha: 'abc12345deadbeef' });
                const ledgerPath = path.join(folder.uri.fsPath, '.aiir', 'receipts.jsonl');
                await waitFor(async () => fs.existsSync(ledgerPath) && fs.readFileSync(ledgerPath, 'utf8').includes('"review_outcome":"commented"'), 'expected review record in ledger');

                const log = await readFakeCliLog(harness.logPath);
                const reviewCall = log.find(entry => Array.isArray(entry.args) && entry.args[0] === '--review');
                assert.ok(reviewCall, 'expected review CLI invocation');
                assert.equal(reviewCall.cwd, folder.uri.fsPath, 'expected configured CLI path to run in the workspace folder');
                assert.deepEqual(
                    reviewCall.args,
                    ['--review', 'abc12345deadbeef', '--review-outcome', 'commented', '--review-comment', 'Needs deeper follow-up'],
                );

                const ledger = fs.readFileSync(ledgerPath, 'utf8');
                assert.match(ledger, /"review_outcome":"commented"/);
                assert.match(ledger, /"review_comment":"Needs deeper follow-up"/);
            });
        } finally {
            vscode.window.showQuickPick = originalShowQuickPick;
            vscode.window.showInputBox = originalShowInputBox;
        }
    });

    it('generates a receipt through the configured CLI path', async () => {
        const folder = getWorkspaceFolder();
        const originalShowInformationMessage = vscode.window.showInformationMessage;
        const infoMessages = [];

        try {
            await withFakeCliHarness(async (harness) => {
                vscode.window.showInformationMessage = async (message, ...items) => {
                    infoMessages.push({ message: String(message), items });
                    return undefined;
                };

                await vscode.commands.executeCommand('aiir.generateReceipt', folder.uri);
                const ledgerPath = path.join(folder.uri.fsPath, '.aiir', 'receipts.jsonl');
                await waitFor(async () => fs.existsSync(ledgerPath) && fs.readFileSync(ledgerPath, 'utf8').includes('"type":"aiir.commit_receipt"'), 'expected receipt generation to write the ledger');

                const log = await readFakeCliLog(harness.logPath);
                const generateCall = log.find(entry => Array.isArray(entry.args) && entry.args.includes('--pretty'));
                assert.ok(generateCall, 'expected receipt generation CLI invocation');
                assert.equal(generateCall.cwd, folder.uri.fsPath, 'expected configured CLI path to run in the workspace folder');
                assert.equal(generateCall.args[0], '--pretty');
                assert.equal(generateCall.args.includes('--editor-provenance'), true, 'expected editor provenance flag');

                const receiptsDir = path.join(folder.uri.fsPath, '.aiir', 'receipts');
                const ledger = fs.readFileSync(ledgerPath, 'utf8');
                assert.match(ledger, /"type":"aiir\.commit_receipt"/);
                assert.match(ledger, /"signals_detected":\["editor_provenance"\]/);

                const artifactFiles = await fsp.readdir(receiptsDir);
                assert.equal(artifactFiles.some(name => name.endsWith('.json')), true, 'expected receipt artifact file');

                assert.equal(
                    infoMessages.some(entry => /Current commit recorded/.test(entry.message)),
                    true,
                    'expected generate receipt success message',
                );
            });
        } finally {
            vscode.window.showInformationMessage = originalShowInformationMessage;
        }
    });

    it('surfaces a PR-ready summary after generation', async () => {
        const folder = getWorkspaceFolder();
        const originalShowInformationMessage = vscode.window.showInformationMessage;

        try {
            await withFakeCliHarness(async () => {
                let copyPromptSeen = false;
                vscode.window.showInformationMessage = async (message, ...items) => {
                    const text = String(message);
                    if (/Current commit recorded/.test(text)) {
                        copyPromptSeen = true;
                        assert.deepEqual(items.slice(0, 2), ['Copy Summary', 'View Proof']);
                        return undefined;
                    }
                    return undefined;
                };

                await vscode.commands.executeCommand('aiir.generateReceipt', folder.uri);
                await delay(900);

                assert.equal(copyPromptSeen, true, 'expected generation success prompt to offer copy summary first');

                const receiptsDir = path.join(folder.uri.fsPath, '.aiir', 'receipts');
                const receiptFile = (await fsp.readdir(receiptsDir)).find(name => name.endsWith('.json'));
                assert.ok(receiptFile, 'expected a generated receipt artifact for summary preview');

                await vscode.commands.executeCommand('aiir.previewReceiptSummary', vscode.Uri.file(path.join(receiptsDir, receiptFile)));
                await delay(500);

                const previewDocument = vscode.workspace.textDocuments.find(document => {
                    if (document.languageId !== 'markdown') {
                        return false;
                    }

                    const text = document.getText();
                    return text.includes('## AIIR PR Summary') && text.includes('### Snapshot');
                });
                assert.ok(previewDocument, 'expected preview summary markdown document to be open');
                const markdown = previewDocument.getText();

                assert.match(markdown, /^## AIIR PR Summary$/m);
                assert.match(markdown, /^### Snapshot$/m);
                assert.match(markdown, /^### AI Evidence$/m);
                assert.match(markdown, new RegExp(`^- Repository: ${folder.name}$`, 'm'));
                assert.match(markdown, /^- Verification: Verified$/m);
            });
        } finally {
            vscode.window.showInformationMessage = originalShowInformationMessage;
        }
    });

    it('regenerates the exact commit referenced by a failed receipt instead of falling back to HEAD', async () => {
        const folder = getWorkspaceFolder();
        const originalShowInformationMessage = vscode.window.showInformationMessage;
        const historicalSha = '1234567890abcdef1234567890abcdef12345678';
        const infoMessages = [];

        try {
            await withFakeCliHarness(async (harness) => {
                vscode.window.showInformationMessage = async (message, ...items) => {
                    infoMessages.push({ message: String(message), items });
                    return undefined;
                };

                await vscode.commands.executeCommand('aiir.generateReceiptForCommit', {
                    record: {
                        receipt: {
                            type: 'aiir.commit_receipt',
                            schema: 'aiir/commit_receipt@v1',
                            version: '0.1.0',
                            commit: {
                                sha: historicalSha,
                                subject: 'Historical test receipt',
                            },
                        },
                        uri: vscode.Uri.file(path.join(folder.uri.fsPath, '.aiir', 'receipts', 'failed-historical.json')),
                        result: {
                            valid: false,
                            errors: ['content hash mismatch'],
                        },
                        artifacts: {
                            cborStatus: 'missing',
                            sigstoreStatus: 'missing',
                        },
                        workspaceFolderName: folder.name,
                        workspaceFolderPath: folder.uri.fsPath,
                    },
                });
                await delay(750);

                const log = await readFakeCliLog(harness.logPath);
                const generateCall = log.find(entry => Array.isArray(entry.args) && entry.args.includes('--pretty') && entry.args.includes('--commit'));
                assert.ok(generateCall, 'expected commit-targeted receipt generation CLI invocation');
                assert.equal(generateCall.cwd, folder.uri.fsPath, 'expected exact-commit generation to run in the workspace folder');
                assert.deepEqual(generateCall.args.slice(0, 3), ['--pretty', '--commit', historicalSha]);
                assert.equal(generateCall.args.includes('--editor-provenance'), false, 'expected historical regeneration to avoid live editor provenance');

                const ledgerPath = path.join(folder.uri.fsPath, '.aiir', 'receipts.jsonl');
                const ledger = fs.readFileSync(ledgerPath, 'utf8');
                assert.match(ledger, new RegExp(`"sha":"${historicalSha}"`), 'expected regenerated historical receipt in the ledger');
                assert.equal(
                    infoMessages.some(entry => /Commit 12345678 recorded/.test(entry.message)),
                    true,
                    'expected commit-specific repair success message',
                );
            });
        } finally {
            vscode.window.showInformationMessage = originalShowInformationMessage;
        }
    });

    it('routes generatePreferred to CLI generation when no active editor qualifies for provenance mode', async () => {
        const folder = getWorkspaceFolder();
        const originalShowInformationMessage = vscode.window.showInformationMessage;
        const infoMessages = [];

        try {
            await withFakeCliHarness(async (harness) => {
                await closeAllEditors();

                vscode.window.showInformationMessage = async () => undefined;
                await vscode.commands.executeCommand('aiir.initializeRepo', folder.uri);
                await delay(900);
                await fsp.writeFile(harness.logPath, '', 'utf8');

                vscode.window.showInformationMessage = async (message, ...items) => {
                    infoMessages.push({ message: String(message), items });
                    return undefined;
                };

                await vscode.commands.executeCommand('aiir.generatePreferred', folder.uri);
                await delay(750);

                const log = await readFakeCliLog(harness.logPath);
                const generateCalls = log.filter(entry => Array.isArray(entry.args) && entry.args.includes('--pretty'));
                assert.equal(generateCalls.length, 1, 'expected a single CLI receipt generation invocation');
                assert.equal(generateCalls[0].cwd, folder.uri.fsPath, 'expected configured CLI path to run in the workspace folder');
                assert.equal(generateCalls[0].args[0], '--pretty');
                assert.equal(generateCalls[0].args.includes('--editor-provenance'), true, 'expected standard receipt generation flags');

                assert.equal(
                    infoMessages.some(entry => /Current commit recorded/.test(entry.message)),
                    true,
                    'expected generatePreferred success message',
                );
            });
        } finally {
            vscode.window.showInformationMessage = originalShowInformationMessage;
        }
    });

    it('auto-initializes the repository when generatePreferred is run on first use', async () => {
        const folder = getWorkspaceFolder();
        const originalShowInformationMessage = vscode.window.showInformationMessage;
        const infoMessages = [];

        try {
            await withFakeCliHarness(async (harness) => {
                await removeWorkspaceAiirState();

                vscode.window.showInformationMessage = async (message, ...items) => {
                    infoMessages.push({ message: String(message), items });
                    return undefined;
                };

                await vscode.commands.executeCommand('aiir.generatePreferred', folder.uri);
                await delay(900);

                const log = await readFakeCliLog(harness.logPath);
                assert.equal(log.some(entry => entry.args.includes('--version')), true, 'expected CLI availability probe');
                assert.equal(log.some(entry => entry.args.includes('--init')), true, 'expected generatePreferred to initialize missing repo scaffolding');

                const generateCalls = log.filter(entry => Array.isArray(entry.args) && entry.args.includes('--pretty'));
                assert.equal(generateCalls.length, 1, 'expected initialization to record a single starter proof');
                assert.equal(generateCalls[0].cwd, folder.uri.fsPath, 'expected starter proof generation in the workspace folder');

                const aiirDir = path.join(folder.uri.fsPath, '.aiir');
                const ledgerPath = path.join(aiirDir, 'receipts.jsonl');
                assert.equal(fs.existsSync(aiirDir), true, 'expected .aiir directory after first-run generatePreferred');
                assert.match(fs.readFileSync(ledgerPath, 'utf8'), /"type":"aiir\.commit_receipt"/, 'expected starter proof in the ledger after auto-init');

                assert.equal(
                    infoMessages.some(entry => /Initialized .* and recorded a starter proof\./.test(entry.message)),
                    true,
                    'expected first-run generatePreferred to surface the initialization success message',
                );
            });
        } finally {
            vscode.window.showInformationMessage = originalShowInformationMessage;
        }
    });

    it('enables auto-receipting through the public install-hook CLI flags', async () => {
        const folder = getWorkspaceFolder();
        const originalShowWarningMessage = vscode.window.showWarningMessage;
        const originalShowInformationMessage = vscode.window.showInformationMessage;
        const infoMessages = [];

        try {
            await withFakeCliHarness(async (harness) => {
                vscode.window.showWarningMessage = async (message, ...items) => {
                    assert.match(String(message), /install or update a post-commit hook/);
                    assert.equal(items.includes('Install Hook'), true);
                    return 'Install Hook';
                };

                vscode.window.showInformationMessage = async (message) => {
                    infoMessages.push(String(message));
                    return undefined;
                };

                await vscode.commands.executeCommand('aiir.enableAutoReceipting', folder.uri);
                await delay(500);

                const log = await readFakeCliLog(harness.logPath);
                const installCall = log.find(entry => Array.isArray(entry.args) && entry.args[0] === '--install-hook');
                assert.ok(installCall, 'expected install-hook CLI invocation');
                assert.deepEqual(installCall.args, ['--install-hook', '--json']);
                assert.equal(installCall.cwd, folder.uri.fsPath, 'expected install-hook to run in the workspace folder');
                assert.equal(infoMessages.some(message => /Auto-receipting/.test(message)), true, 'expected enable success message');
            });
        } finally {
            vscode.window.showWarningMessage = originalShowWarningMessage;
            vscode.window.showInformationMessage = originalShowInformationMessage;
        }
    });

    it('disables auto-receipting through the public remove-hook CLI flags', async () => {
        const folder = getWorkspaceFolder();
        const originalShowInformationMessage = vscode.window.showInformationMessage;
        const originalShowWarningMessage = vscode.window.showWarningMessage;
        const infoMessages = [];
        const warningMessages = [];

        try {
            await withFakeCliHarness(async (harness) => {
                vscode.window.showInformationMessage = async (message) => {
                    infoMessages.push(String(message));
                    return undefined;
                };
                vscode.window.showWarningMessage = async (message) => {
                    warningMessages.push(String(message));
                    return undefined;
                };

                await vscode.commands.executeCommand('aiir.enableAutoReceipting', folder.uri);
                await delay(250);
                await vscode.commands.executeCommand('aiir.disableAutoReceipting', folder.uri);
                await delay(500);

                const log = await readFakeCliLog(harness.logPath);
                const removeCall = log.find(entry => Array.isArray(entry.args) && entry.args[0] === '--remove-hook');
                assert.ok(removeCall, 'expected remove-hook CLI invocation');
                assert.deepEqual(removeCall.args, ['--remove-hook', '--json']);
                assert.equal(removeCall.cwd, folder.uri.fsPath, 'expected remove-hook to run in the workspace folder');
                assert.equal(infoMessages.some(message => /Disabled managed auto-receipting/.test(message)), true, 'expected disable success message');
                assert.equal(warningMessages.some(message => /No managed post-commit hook/.test(message)), false, 'expected managed hook removal, not absent warning');
            });
        } finally {
            vscode.window.showInformationMessage = originalShowInformationMessage;
            vscode.window.showWarningMessage = originalShowWarningMessage;
        }
    });

    it('resumes a pending generate action after CLI availability is restored', async () => {
        const folder = getWorkspaceFolder();
        const originalShowInformationMessage = vscode.window.showInformationMessage;
        const harness = await createFakeCliHarness();
        const infoMessages = [];

        try {
            process.env.AIIR_FAKE_CLI_LOG = harness.logPath;
            await vscode.workspace.getConfiguration('aiir').update('cliPath', harness.wrapperPath, vscode.ConfigurationTarget.Global);
            vscode.window.showInformationMessage = async () => undefined;
            await vscode.commands.executeCommand('aiir.initializeRepo', folder.uri);
            await delay(900);
            await fsp.writeFile(harness.logPath, '', 'utf8');

            await vscode.workspace.getConfiguration('aiir').update('cliPath', path.join(harness.root, 'missing-aiir'), vscode.ConfigurationTarget.Global);

            let setupPromptSeen = false;
            let continuePromptSeen = false;
            vscode.window.showInformationMessage = async (message, ...items) => {
                const text = String(message);
                infoMessages.push({ message: text, items });

                if (items.includes('Install CLI') && /needs the AIIR CLI first/.test(text)) {
                    setupPromptSeen = true;
                    return undefined;
                }

                if (items.includes('Continue') && /Setup is ready\. Continue to Generate\?/.test(text)) {
                    continuePromptSeen = true;
                    return 'Continue';
                }

                if (/Current commit recorded/.test(text)) {
                    return undefined;
                }

                return undefined;
            };

            await vscode.commands.executeCommand('aiir.generatePreferred', folder.uri);
            await delay(400);

            assert.equal(setupPromptSeen, true, 'expected missing CLI guidance prompt');
            assert.deepEqual(await readFakeCliLog(harness.logPath), [], 'expected no fake CLI usage while CLI path is missing');

            await vscode.workspace.getConfiguration('aiir').update('cliPath', harness.wrapperPath, vscode.ConfigurationTarget.Global);

            const terminal = vscode.window.createTerminal('aiir-pending-action-trigger');
            terminal.dispose();

            await waitFor(async () => continuePromptSeen, 'expected continuation prompt after CLI availability returned');
            await waitFor(async () => {
                const entries = await readFakeCliLog(harness.logPath);
                return entries.some(entry => entry.args.includes('--version'))
                    && entries.some(entry => Array.isArray(entry.args) && entry.args.includes('--pretty'));
            }, 'expected pending generate action to resume through CLI generation');
            await waitFor(async () => infoMessages.some(entry => /Current commit recorded/.test(entry.message)), 'expected resumed generate success message');

            const log = await readFakeCliLog(harness.logPath);
            assert.equal(continuePromptSeen, true, 'expected continuation prompt after CLI availability returned');
            assert.equal(log.some(entry => entry.args.includes('--version')), true, 'expected CLI availability probe during pending action resume');

            const generateCall = log.find(entry => Array.isArray(entry.args) && entry.args.includes('--pretty'));
            assert.ok(generateCall, 'expected pending generate action to resume through CLI generation');
            assert.equal(generateCall.cwd, folder.uri.fsPath, 'expected resumed generate action to run in the workspace folder');

            const ledgerPath = path.join(folder.uri.fsPath, '.aiir', 'receipts.jsonl');
            const ledger = fs.readFileSync(ledgerPath, 'utf8');
            assert.match(ledger, /"type":"aiir\.commit_receipt"/);
            assert.equal(infoMessages.some(entry => /Current commit recorded/.test(entry.message)), true, 'expected resumed generate success message');
        } finally {
            delete process.env.AIIR_FAKE_CLI_LOG;
            await fsp.rm(harness.root, { recursive: true, force: true });
            vscode.window.showInformationMessage = originalShowInformationMessage;
        }
    });

    it('switches repository focus for untargeted commands', async () => {
        const originalShowQuickPick = vscode.window.showQuickPick;
        const originalShowInformationMessage = vscode.window.showInformationMessage;

        try {
            await withAdditionalWorkspaceFolder('secondary-repo', async (secondaryFolder) => {
                await withFakeCliHarness(async (harness) => {
                    let switchPromptSeen = false;
                    const infoMessages = [];

                    vscode.window.showQuickPick = async (items, options) => {
                        if (options?.title === 'Switch Repository') {
                            switchPromptSeen = true;
                            const target = items.find(item => item.description === secondaryFolder.uri.fsPath);
                            assert.ok(target, 'expected secondary repository option in switch command');
                            return target;
                        }
                        return items[0];
                    };

                    vscode.window.showInformationMessage = async (message) => {
                        infoMessages.push(String(message));
                        return undefined;
                    };

                    await vscode.commands.executeCommand('aiir.switchRepository');
                    await delay(300);
                    await vscode.commands.executeCommand('aiir.healthCheck');
                    await delay(700);

                    const log = await readFakeCliLog(harness.logPath);
                    const doctorCall = log.find(entry => Array.isArray(entry.args) && entry.args[0] === '--doctor');
                    assert.equal(switchPromptSeen, true, 'expected switch repository quick pick');
                    assert.ok(doctorCall, 'expected health check CLI invocation after switching repositories');
                    assert.equal(doctorCall.cwd, secondaryFolder.uri.fsPath, 'expected untargeted health check to use the switched repository');
                    assert.equal(
                        infoMessages.some(message => message === `AIIR: Focused on ${secondaryFolder.name}`),
                        true,
                        'expected repository switch confirmation message',
                    );
                });
            });
        } finally {
            vscode.window.showQuickPick = originalShowQuickPick;
            vscode.window.showInformationMessage = originalShowInformationMessage;
        }
    });

    it('shows a clear error when generateWithProvenance has no language-model support', async () => {
        const folder = getWorkspaceFolder();
        const originalShowErrorMessage = vscode.window.showErrorMessage;
        const errorMessages = [];

        try {
            await withFakeCliHarness(async (harness) => {
                setLanguageModelBridgeForTests({
                    hasSupport: () => false,
                    selectChatModel: async () => undefined,
                    createUserMessage: (content) => content,
                    collectResponseText: async () => '',
                });
                vscode.window.showErrorMessage = async (message) => {
                    errorMessages.push(String(message));
                    return undefined;
                };

                await vscode.commands.executeCommand('aiir.generateWithProvenance', folder.uri);
                await delay(300);

                const log = await readFakeCliLog(harness.logPath);
                assert.equal(log.some(entry => entry.args.includes('--version')), true, 'expected CLI availability probe for provable command');
                assert.equal(log.some(entry => entry.args.includes('--pretty')), false, 'expected provable command to stop before receipt generation');

                assert.equal(
                    errorMessages.some(message => /requires a VS Code build with language model support/.test(message)),
                    true,
                    'expected missing language-model support error',
                );
            });
        } finally {
            vscode.window.showErrorMessage = originalShowErrorMessage;
        }
    });

    it('runs generateWithProvenance through a bridged chat model and queues provenance', async () => {
        const folder = getWorkspaceFolder();
        const originalShowInformationMessage = vscode.window.showInformationMessage;
        const originalShowInputBox = vscode.window.showInputBox;
        const originalShowErrorMessage = vscode.window.showErrorMessage;
        const activeFileUri = vscode.Uri.joinPath(folder.uri, 'README.md');
        const activeFilePath = activeFileUri.fsPath;
        const createdFilePath = path.join(folder.uri.fsPath, 'provable-generated.txt');
        const infoMessages = [];
        const errorMessages = [];

        try {
            await fsp.rm(createdFilePath, { force: true });

            await withFakeCliHarness(async (harness) => {
                const document = await vscode.workspace.openTextDocument(activeFileUri);
                await vscode.window.showTextDocument(document);
                await delay(200);
                assert.equal(vscode.window.activeTextEditor?.document.uri.fsPath, activeFilePath, 'expected provable-mode test file to be active');

                setLanguageModelBridgeForTests({
                    hasSupport: () => true,
                    selectChatModel: async () => ({
                        vendor: 'copilot',
                        family: 'test-model',
                        sendRequest: async (messages) => {
                            assert.equal(Array.isArray(messages), true, 'expected bridged provable request messages');
                            return {
                                text: (async function* () {
                                    yield JSON.stringify({
                                        summary: 'Create a provenance artifact',
                                        operations: [
                                            {
                                                type: 'create-file',
                                                path: 'provable-generated.txt',
                                                text: 'created by provable mode\n',
                                            },
                                        ],
                                    });
                                }()),
                            };
                        },
                    }),
                    createUserMessage: (content) => ({ role: 'user', content }),
                    collectResponseText: async (response) => {
                        let text = '';
                        for await (const chunk of response.text) {
                            text += chunk;
                        }
                        return text;
                    },
                });

                vscode.window.showInputBox = async (options) => {
                    assert.match(String(options?.prompt || ''), /Describe the code change/);
                    return 'Create a provenance artifact';
                };

                vscode.window.showErrorMessage = async (message) => {
                    errorMessages.push(String(message));
                    return undefined;
                };

                vscode.window.showInformationMessage = async (message, ...items) => {
                    const text = String(message);
                    infoMessages.push({ message: text, items });

                    if (items.includes('Continue') && /needs local \.aiir working state/.test(text)) {
                        return 'Continue';
                    }

                    if (items.includes('Apply Changes') && /Create a provenance artifact/.test(text)) {
                        return 'Apply Changes';
                    }

                    return undefined;
                };

                await vscode.commands.executeCommand('aiir.generateWithProvenance', document.uri);
                await delay(1000);

                assert.deepEqual(errorMessages, [], `unexpected provable-mode errors: ${errorMessages.join(' | ')}`);

                const log = await readFakeCliLog(harness.logPath);
                assert.equal(log.some(entry => entry.args.includes('--version')), true, 'expected CLI availability probe for provable command');
                assert.equal(log.some(entry => entry.args.includes('--pretty')), false, 'expected provable command to avoid direct receipt generation');

                const createdContent = await fsp.readFile(createdFilePath, 'utf8');
                assert.equal(createdContent, 'created by provable mode\n');

                const queuePath = path.join(folder.uri.fsPath, '.aiir', 'editor_provenance.jsonl');
                const queueRaw = await fsp.readFile(queuePath, 'utf8');
                assert.match(queueRaw, /"mode":"provable"/);
                assert.match(queueRaw, /"command":"generate"/);
                assert.match(queueRaw, /"path":"provable-generated\.txt"/);
                assert.match(queueRaw, /"modelVendor":"copilot"/);
                assert.match(queueRaw, /"modelFamily":"test-model"/);

                assert.equal(
                    infoMessages.some(entry => /Changes applied and provable provenance was queued/.test(entry.message)),
                    true,
                    'expected provable-mode completion message',
                );
            });
        } finally {
            await fsp.rm(createdFilePath, { force: true });
            vscode.window.showInformationMessage = originalShowInformationMessage;
            vscode.window.showInputBox = originalShowInputBox;
            vscode.window.showErrorMessage = originalShowErrorMessage;
        }
    });

    it('restores preset-covered settings when lockPreset is active', async () => {
        const config = vscode.workspace.getConfiguration('aiir');
        const originalShowWarningMessage = vscode.window.showWarningMessage;
        const warnings = [];

        try {
            vscode.window.showWarningMessage = async (message) => {
                warnings.push(String(message));
                return undefined;
            };

            await config.update('lockPreset', 'local-public', vscode.ConfigurationTarget.Workspace);
            await delay(300);

            await config.update('strictLocalOnly', false, vscode.ConfigurationTarget.Workspace);
            await delay(500);

            assert.equal(config.get('strictLocalOnly'), true, 'expected strictLocalOnly to be restored by the active lock preset');
            assert.equal(
                warnings.some(message => /locked by preset/.test(message)),
                true,
                'expected a warning explaining the preset-enforced revert',
            );
        } finally {
            vscode.window.showWarningMessage = originalShowWarningMessage;
        }
    });
});
