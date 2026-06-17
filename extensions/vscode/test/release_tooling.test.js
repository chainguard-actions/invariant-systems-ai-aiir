const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const extensionRoot = path.join(__dirname, '..');

function read(relativePath) {
    return fs.readFileSync(path.join(extensionRoot, relativePath), 'utf8');
}

test('deep smoke prep script derives the VSIX path from package.json', () => {
    const script = read('scripts/prepare-deep-smoke.sh');

    assert.match(script, /NODE_BIN="\$\{NODE_BIN:-\$\(command -v node \|\| true\)\}"/);
    assert.match(script, /require_bin "\$NODE_BIN" "node"/);
    assert.match(script, /bash "\$ROOT\/scripts\/materialize-deep-smoke-fixtures\.sh"/);
    assert.match(script, /PACKAGE_VERSION="\$\(\$NODE_BIN -p "require\(process\.argv\[1\]\)\.version" "\$ROOT\/package\.json"\)"/);
    assert.match(script, /VSIX_PATH="\$ROOT\/aiir-\$PACKAGE_VERSION\.vsix"/);
    assert.match(script, /Package version:\n\s+\$PACKAGE_VERSION/);
    assert.match(script, /VSIX artifact:\n\s+\$VSIX_PATH/);
    assert.match(script, /HEALTHY_DIR="\$FIXTURE_ROOT\/healthy"/);
    assert.match(script, /cp -R "\$FIXTURE_ROOT\/initialized-empty" "\$HEALTHY_DIR"/);
    assert.match(script, /"\$CLI_BIN" --pretty --output \.aiir\/receipts >/);
    assert.match(script, /cat "\$HEALTHY_RECEIPT_JSON" > "\$HEALTHY_DIR\/.aiir\/receipts\.jsonl"/);
    assert.match(script, /Healthy repo: \$HEALTHY_DIR/);
    assert.doesNotMatch(script, /aiir-0\.3\.1\.vsix/);
});

test('release docs avoid pinning the deep smoke VSIX to one old version', () => {
    const blockingChecklist = read('docs/release/BLOCKING_DEEP_SMOKE_CHECKLIST.md');
    const datedReport = read('docs/release/DEEP_SMOKE_RUN_2026-03-15.md');
    const adminGuide = read('docs/operations/ADMIN_DEPLOYMENT.md');
    const launcher = read('scripts/launch-deep-smoke.sh');

    assert.doesNotMatch(blockingChecklist, /\/home\/kaleidos\/Desktop\/invariant-systems-public\/aiir\/extensions\/vscode\/aiir-0\.3\.1\.vsix/);
    assert.match(datedReport, /aiir-0\.3\.1\.vsix/);
    assert.match(adminGuide, /aiir-<version>\.vsix/);
    assert.doesNotMatch(adminGuide, /aiir-0\.3\.0\.vsix/);
    assert.match(launcher, /HEALTHY_DIR="\$FIXTURE_ROOT\/healthy"/);
    assert.doesNotMatch(launcher, /Desktop\/invariant-systems-public\/aiir/);
});
