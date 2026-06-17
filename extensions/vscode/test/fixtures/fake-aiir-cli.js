#!/usr/bin/env node

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const childProcess = require('node:child_process');

function appendLog(entry) {
    const logPath = process.env.AIIR_FAKE_CLI_LOG;
    if (!logPath) {
        return;
    }

    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.appendFileSync(logPath, `${JSON.stringify(entry)}\n`, 'utf8');
}

function ensureAiirScaffolding(cwd, preset) {
    const aiirDir = path.join(cwd, '.aiir');
    fs.mkdirSync(aiirDir, { recursive: true });
    fs.mkdirSync(path.join(aiirDir, 'receipts'), { recursive: true });

    const files = new Map([
        ['receipts.jsonl', ''],
        ['index.json', '{}\n'],
        ['config.json', '{}\n'],
        ['.gitignore', 'editor_provenance.jsonl\n'],
    ]);

    if (preset) {
        files.set('policy.json', `${JSON.stringify({ preset }, null, 2)}\n`);
    }

    for (const [name, content] of files) {
        const targetPath = path.join(aiirDir, name);
        if (!fs.existsSync(targetPath)) {
            fs.writeFileSync(targetPath, content, 'utf8');
        }
    }
}

function canonicalJson(value) {
    if (value === null || value === undefined) {
        return 'null';
    }

    if (typeof value === 'boolean') {
        return value ? 'true' : 'false';
    }

    if (typeof value === 'number') {
        if (!Number.isFinite(value)) {
            throw new Error('NaN/Infinity not allowed');
        }
        return JSON.stringify(value);
    }

    if (typeof value === 'string') {
        return JSON.stringify(value).replace(/[\u0080-\uffff]/g, (ch) => {
            return '\\u' + ch.charCodeAt(0).toString(16).padStart(4, '0');
        });
    }

    if (Array.isArray(value)) {
        return '[' + value.map(item => canonicalJson(item)).join(',') + ']';
    }

    if (typeof value === 'object') {
        const keys = Object.keys(value).sort();
        const pairs = keys
            .filter((key) => value[key] !== undefined)
            .map((key) => canonicalJson(key) + ':' + canonicalJson(value[key]));
        return '{' + pairs.join(',') + '}';
    }

    throw new Error(`cannot encode type: ${typeof value}`);
}

function getHeadSha(cwd) {
    try {
        return childProcess.execFileSync('git', ['rev-parse', 'HEAD'], { cwd, encoding: 'utf8' }).trim();
    } catch {
        return '0'.repeat(40);
    }
}

function getBranchName(cwd) {
    try {
        return childProcess.execFileSync('git', ['rev-parse', '--abbrev-ref', 'HEAD'], { cwd, encoding: 'utf8' }).trim();
    } catch {
        return null;
    }
}

function getHookPath(cwd) {
    try {
        const hookPath = childProcess.execFileSync('git', ['rev-parse', '--git-path', 'hooks/post-commit'], { cwd, encoding: 'utf8' }).trim();
        return path.isAbsolute(hookPath) ? hookPath : path.join(cwd, hookPath);
    } catch {
        return path.join(cwd, '.git', 'hooks', 'post-commit');
    }
}

function readHookState(cwd) {
    const hookPath = getHookPath(cwd);
    if (!fs.existsSync(hookPath)) {
        return 'missing';
    }
    const hookContents = fs.readFileSync(hookPath, 'utf8');
    return hookContents.includes('# >>> AIIR managed post-commit hook >>>') ? 'managed' : 'custom';
}

function buildDoctorPayload(cwd) {
    const aiirDir = path.join(cwd, '.aiir');
    return {
        cli_available: true,
        cli_version: '0.0.0-test',
        git_available: true,
        branch: getBranchName(cwd),
        head_sha: getHeadSha(cwd),
        aiir_dir_exists: fs.existsSync(aiirDir),
        ledger_exists: fs.existsSync(path.join(aiirDir, 'receipts.jsonl')),
        index_exists: fs.existsSync(path.join(aiirDir, 'index.json')),
        policy_exists: fs.existsSync(path.join(aiirDir, 'policy.json')),
        managed_hook_state: readHookState(cwd),
        head_receipt_status: fs.existsSync(path.join(aiirDir, 'receipts.jsonl')) ? 'present' : 'missing',
        provenance_queue_exists: fs.existsSync(path.join(aiirDir, 'editor_provenance.jsonl')),
    };
}

function installManagedHook(cwd) {
    const hookPath = getHookPath(cwd);
    fs.mkdirSync(path.dirname(hookPath), { recursive: true });
    const existing = fs.existsSync(hookPath) ? fs.readFileSync(hookPath, 'utf8') : '';
    const managedBlock = [
        '# >>> AIIR managed post-commit hook >>>',
        '# Managed by AIIR CLI.',
        'aiir --pretty >/dev/null 2>&1 || aiir --pretty',
        '# <<< AIIR managed post-commit hook <<<',
    ].join('\n');

    let status = 'installed';
    let next = '#!/bin/sh\n\n' + managedBlock + '\n';
    if (existing.includes('# >>> AIIR managed post-commit hook >>>') && existing.includes('# <<< AIIR managed post-commit hook <<<')) {
        status = 'updated';
        next = existing.replace(/# >>> AIIR managed post-commit hook >>>[\s\S]*?# <<< AIIR managed post-commit hook <<</m, managedBlock);
    }

    fs.writeFileSync(hookPath, next, 'utf8');
    return { action: 'install_hook', status, hook_path: hookPath, managed_hook_state: 'managed' };
}

function removeManagedHook(cwd) {
    const hookPath = getHookPath(cwd);
    if (!fs.existsSync(hookPath)) {
        return { action: 'remove_hook', status: 'absent', hook_path: hookPath, managed_hook_state: 'missing' };
    }

    const existing = fs.readFileSync(hookPath, 'utf8');
    if (!existing.includes('# >>> AIIR managed post-commit hook >>>') || !existing.includes('# <<< AIIR managed post-commit hook <<<')) {
        return { action: 'remove_hook', status: 'absent', hook_path: hookPath, managed_hook_state: 'custom' };
    }

    const stripped = existing
        .replace(/\n?# >>> AIIR managed post-commit hook >>>[\s\S]*?# <<< AIIR managed post-commit hook <<<\n?/m, '\n')
        .replace(/\n{3,}/g, '\n\n')
        .trim();

    if (!stripped || stripped === '#!/bin/sh') {
        fs.rmSync(hookPath, { force: true });
    } else {
        fs.writeFileSync(hookPath, `${stripped}\n`, 'utf8');
    }

    return { action: 'remove_hook', status: 'removed', hook_path: hookPath, managed_hook_state: 'missing' };
}

function buildReceipt(cwd, commitSha = getHeadSha(cwd)) {
    const core = {
        type: 'aiir.commit_receipt',
        schema: 'aiir/commit_receipt@v1',
        version: '0.1.0',
        commit: {
            sha: commitSha,
            subject: 'Test receipt',
        },
        ai_attestation: {
            is_ai_authored: true,
            authorship_class: 'ai-assisted',
            signals_detected: ['editor_provenance'],
        },
        provenance: {
            generator: 'aiir-test-fixture',
            tool: 'fake-cli',
        },
    };

    const digest = crypto.createHash('sha256').update(canonicalJson(core), 'utf8').digest('hex');
    return {
        ...core,
        receipt_id: `g1-${digest.slice(0, 32)}`,
        content_hash: `sha256:${digest}`,
        timestamp: '2026-03-14T00:00:00Z',
    };
}

function persistReceipt(cwd, commitSha) {
    ensureAiirScaffolding(cwd);

    const receipt = buildReceipt(cwd, commitSha);
    const receiptsDir = path.join(cwd, '.aiir', 'receipts');
    const ledgerPath = path.join(cwd, '.aiir', 'receipts.jsonl');
    const commitShort = receipt.commit.sha.slice(0, 12);
    const hashShort = receipt.content_hash.replace(/[^a-fA-F0-9]/g, '').slice(0, 16);
    const artifactPath = path.join(receiptsDir, `receipt_${commitShort}_${hashShort}.json`);

    fs.appendFileSync(ledgerPath, `${JSON.stringify(receipt)}\n`, 'utf8');
    fs.writeFileSync(artifactPath, `${JSON.stringify(receipt, null, 2)}\n`, 'utf8');

    return receipt;
}

const args = process.argv.slice(2);
appendLog({ args, cwd: process.cwd() });

if (args.includes('--version')) {
    process.stdout.write('aiir 0.0.0-test\n');
    process.exit(0);
}

if (args.includes('--init')) {
    const policyIndex = args.indexOf('--policy');
    const preset = policyIndex >= 0 ? args[policyIndex + 1] : undefined;
    ensureAiirScaffolding(process.cwd(), preset);
    process.stdout.write('initialized test scaffolding\n');
    process.exit(0);
}

if (args[0] === '--policy-init') {
    ensureAiirScaffolding(process.cwd(), args[1]);
    process.stdout.write('initialized test policy\n');
    process.exit(0);
}

if (args[0] === '--review') {
    const outcomeIndex = args.indexOf('--review-outcome');
    const commentIndex = args.indexOf('--review-comment');
    const reviewOutcome = outcomeIndex >= 0 ? args[outcomeIndex + 1] : 'approved';
    const reviewComment = commentIndex >= 0 ? args[commentIndex + 1] : undefined;

    ensureAiirScaffolding(process.cwd());
    const ledgerPath = path.join(process.cwd(), '.aiir', 'receipts.jsonl');
    const reviewRecord = {
        type: 'aiir.review_receipt',
        review_outcome: reviewOutcome,
        review_comment: reviewComment,
        reviewed_commit: args[1] || 'HEAD',
    };
    fs.appendFileSync(ledgerPath, `${JSON.stringify(reviewRecord)}\n`, 'utf8');
    process.stdout.write('recorded test review\n');
    process.exit(0);
}

if (args[0] === '--doctor') {
    process.stdout.write(`${JSON.stringify(buildDoctorPayload(process.cwd()), null, 2)}\n`);
    process.exit(0);
}

if (args[0] === '--install-hook') {
    const payload = installManagedHook(process.cwd());
    process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
    process.exit(0);
}

if (args[0] === '--remove-hook') {
    const payload = removeManagedHook(process.cwd());
    process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
    process.exit(0);
}

if (args.includes('--pretty')) {
    const commitIndex = args.indexOf('--commit');
    const commitSha = commitIndex >= 0 ? args[commitIndex + 1] : undefined;
    const receipt = persistReceipt(process.cwd(), commitSha);
    process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
    process.exit(0);
}

process.stderr.write(`unsupported fake aiir command: ${args.join(' ')}\n`);
process.exit(1);
