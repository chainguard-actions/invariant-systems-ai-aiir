const os = require('node:os');
const path = require('node:path');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const { runTests } = require('@vscode/test-electron');

function resolveLocalCodeExecutable(extensionRoot) {
    const envPath = process.env.CODE_INSIDERS_BIN || process.env.VSCODE_EXECUTABLE_PATH;
    if (envPath && fs.existsSync(envPath)) {
        return envPath;
    }

    const cachedPath = path.join(extensionRoot, '.vscode-test', 'vscode-linux-x64-insiders', 'code-insiders');
    if (fs.existsSync(cachedPath)) {
        return cachedPath;
    }

    return undefined;
}

async function main() {
    const extensionDevelopmentPath = path.resolve(__dirname, '..', '..');
    const extensionTestsPath = path.resolve(__dirname, 'suite', 'index.js');
    const fixtureWorkspacePath = path.resolve(__dirname, '..', 'fixtures', 'sample-workspace');
    const vscodeExecutablePath = resolveLocalCodeExecutable(extensionDevelopmentPath);
    const profileRoot = await fsp.mkdtemp(path.join(os.tmpdir(), 'aiir-vscode-test-'));
    const userDataDir = path.join(profileRoot, 'user-data');
    const extensionsDir = path.join(profileRoot, 'extensions');
    const workspaceFilePath = path.join(profileRoot, 'aiir-extension-host.code-workspace');

    await fsp.mkdir(userDataDir, { recursive: true });
    await fsp.mkdir(extensionsDir, { recursive: true });
    await fsp.writeFile(
        workspaceFilePath,
        JSON.stringify({ folders: [{ path: fixtureWorkspacePath }] }, null, 2) + '\n',
        'utf8',
    );

    try {
        const options = {
            extensionDevelopmentPath,
            extensionTestsPath,
            launchArgs: [
                workspaceFilePath,
                '--disable-extensions',
                '--new-window',
                `--user-data-dir=${userDataDir}`,
                `--extensions-dir=${extensionsDir}`,
            ],
        };

        if (vscodeExecutablePath) {
            options.vscodeExecutablePath = vscodeExecutablePath;
        } else {
            options.version = 'insiders';
        }

        await runTests(options);
    } finally {
        await fsp.rm(profileRoot, { recursive: true, force: true });
    }
}

main().catch(error => {
    console.error(error);
    process.exit(1);
});
