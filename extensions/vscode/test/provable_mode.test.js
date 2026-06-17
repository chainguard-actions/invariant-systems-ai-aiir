const test = require('node:test');
const assert = require('node:assert/strict');

const {
    PROVABLE_QUEUE_FILENAME,
    appendProvenanceRecord,
    extractFirstJsonObject,
    parseProvenanceQueue,
    parseStructuredEditPlan,
    purgeConsumedRecords,
    serializeProvenanceQueue,
    sha256Text,
} = require('../out/provable_mode.js');

test('extractFirstJsonObject finds the first valid object inside model chatter', () => {
    const raw = 'Plan follows:\n```json\n{"summary":"Fix lint","operations":[]}\n```\nExtra notes';
    assert.equal(extractFirstJsonObject(raw), '{"summary":"Fix lint","operations":[]}');
});

test('extractFirstJsonObject skips invalid JSON fragments and respects escaped strings', () => {
    const raw = '{"summary": } ignored {"summary":"Brace in string: \\"}\\"","operations":[]}';
    assert.equal(
        extractFirstJsonObject(raw),
        '{"summary":"Brace in string: \\"}\\"","operations":[]}',
    );
});

test('extractFirstJsonObject returns undefined when no JSON object is present', () => {
    assert.equal(extractFirstJsonObject('No structured plan here.'), undefined);
});

test('parseStructuredEditPlan accepts replace-range and create-file operations', () => {
    const plan = parseStructuredEditPlan(JSON.stringify({
        summary: '  Tighten queue handling  ',
        operations: [
            {
                type: 'replace-range',
                path: 'src/extension.ts',
                startLine: 1,
                startCharacter: 0,
                endLine: 1,
                endCharacter: 5,
                rangeText: 'hello',
                text: 'world',
            },
            {
                type: 'create-file',
                path: 'notes.txt',
                text: 'created',
            },
        ],
    }));

    assert.equal(plan.summary, 'Tighten queue handling');
    assert.equal(plan.operations.length, 2);
    assert.deepEqual(plan.operations[0], {
        type: 'replace-range',
        path: 'src/extension.ts',
        startLine: 1,
        startCharacter: 0,
        endLine: 1,
        endCharacter: 5,
        rangeText: 'hello',
        text: 'world',
    });
    assert.deepEqual(plan.operations[1], {
        type: 'create-file',
        path: 'notes.txt',
        text: 'created',
        startLine: undefined,
        startCharacter: undefined,
        endLine: undefined,
        endCharacter: undefined,
        rangeText: undefined,
    });
});

test('parseStructuredEditPlan rejects unsupported operation types', () => {
    assert.throws(
        () => parseStructuredEditPlan(JSON.stringify({
            operations: [{ type: 'delete-file', path: 'src/old.ts', text: '' }],
        })),
        /unsupported type/,
    );
});

test('parseStructuredEditPlan rejects missing JSON and malformed operation payloads', () => {
    assert.throws(() => parseStructuredEditPlan('plain text only'), /No valid JSON object/);
    assert.throws(() => parseStructuredEditPlan(JSON.stringify({ summary: 'oops' })), /operations array/);
    assert.throws(
        () => parseStructuredEditPlan(JSON.stringify({ operations: ['bad'] })),
        /Operation 1 is not an object/,
    );
    assert.throws(
        () => parseStructuredEditPlan(JSON.stringify({ operations: [{ type: 'create-file', path: 123, text: 'x' }] })),
        /missing a valid path/,
    );
    assert.throws(
        () => parseStructuredEditPlan(JSON.stringify({ operations: [{ type: 'create-file', path: '   ', text: 'x' }] })),
        /missing a valid path/,
    );
    assert.throws(
        () => parseStructuredEditPlan(JSON.stringify({ operations: [{ type: 'create-file', path: 'ok.txt', text: 42 }] })),
        /missing replacement text/,
    );
    assert.throws(
        () => parseStructuredEditPlan(JSON.stringify({ operations: [{ type: 'create-file', path: 'ok.txt' }] })),
        /missing replacement text/,
    );
});

test('parseStructuredEditPlan falls back to a generated summary when the summary is blank', () => {
    const plan = parseStructuredEditPlan(JSON.stringify({
        summary: '   ',
        operations: [{ type: 'create-file', path: 'new.txt', text: 'content' }],
    }));

    assert.equal(plan.summary, 'Prepared 1 operation');
});

test('parseStructuredEditPlan falls back to a generated summary when the summary is not a string', () => {
    const plan = parseStructuredEditPlan(JSON.stringify({
        summary: 7,
        operations: [{ type: 'create-file', path: 'new.txt', text: 'content' }],
    }));

    assert.equal(plan.summary, 'Prepared 1 operation');
});

test('parseProvenanceQueue and serializeProvenanceQueue handle empty input', () => {
    assert.deepEqual(parseProvenanceQueue(undefined), []);
    assert.deepEqual(parseProvenanceQueue(''), []);
    assert.equal(serializeProvenanceQueue([]), '');
});

test('parseProvenanceQueue skips malformed JSONL lines and keeps valid records', () => {
    const records = parseProvenanceQueue([
        '{"id":"record-1","sessionId":"session-1","createdAt":"2026-03-14T00:00:00.000Z","repositoryPath":"/workspace/aiir","toolId":"aiir-vscode","mode":"provable","command":"generate","source":"aiir-command","promptKind":"workspace","files":[],"contentHash":"sha256:1","applied":true,"consumed":false}',
        '{not-json}',
        '[]',
        '{"id":"record-2","sessionId":"session-1","createdAt":"2026-03-14T00:01:00.000Z","repositoryPath":"/workspace/aiir","toolId":"aiir-vscode","mode":"provable","command":"fix","source":"aiir-chat","promptKind":"file","files":[],"contentHash":"sha256:2","applied":true,"consumed":false}',
    ].join('\n'));

    assert.deepEqual(records.map(record => record.id), ['record-1', 'record-2']);
});

test('appendProvenanceRecord chains previous record hashes and serializes JSONL', () => {
    const first = appendProvenanceRecord(undefined, {
        id: 'record-1',
        sessionId: 'session-1',
        createdAt: '2026-03-14T00:00:00.000Z',
        repositoryPath: '/workspace/aiir',
        toolId: 'aiir-vscode',
        mode: 'provable',
        command: 'generate',
        source: 'aiir-command',
        promptKind: 'workspace',
        files: [{ path: 'src/app.ts', beforeHash: 'sha256:1', afterHash: 'sha256:2' }],
        applied: true,
        consumed: false,
    });

    const second = appendProvenanceRecord(first.serialized, {
        id: 'record-2',
        sessionId: 'session-1',
        createdAt: '2026-03-14T00:01:00.000Z',
        repositoryPath: '/workspace/aiir',
        toolId: 'aiir-vscode',
        mode: 'provable',
        command: 'fix',
        source: 'aiir-chat',
        promptKind: 'file',
        files: [{ path: 'src/app.ts', beforeHash: 'sha256:2', afterHash: 'sha256:3' }],
        applied: true,
        consumed: false,
    });

    const records = parseProvenanceQueue(second.serialized);
    assert.equal(records.length, 2);
    assert.equal(records[0].previousRecordHash, undefined);
    assert.equal(records[1].previousRecordHash, records[0].contentHash);
    assert.equal(records[0].contentHash.startsWith('sha256:'), true);
    assert.equal(serializeProvenanceQueue(records).endsWith('\n'), true);
});

test('appendProvenanceRecord canonicalizes null metadata fields deterministically', () => {
    const result = appendProvenanceRecord(undefined, {
        id: 'record-null-metadata',
        sessionId: 'session-1',
        createdAt: '2026-03-14T00:00:00.000Z',
        repositoryPath: '/workspace/aiir',
        branch: null,
        baseCommitSha: null,
        toolId: 'aiir-vscode',
        mode: 'provable',
        command: 'generate',
        modelVendor: null,
        modelFamily: null,
        source: 'aiir-command',
        promptKind: 'workspace',
        files: [{ path: 'src/app.ts', beforeHash: 'sha256:1', afterHash: 'sha256:2' }],
        applied: true,
        consumed: false,
    });

    const [record] = parseProvenanceQueue(result.serialized);
    assert.equal(record.branch, null);
    assert.equal(record.baseCommitSha, null);
    assert.equal(record.modelVendor, null);
    assert.equal(record.modelFamily, null);
    assert.equal(record.contentHash.startsWith('sha256:'), true);
});

test('purgeConsumedRecords removes only stale consumed records', () => {
    const raw = serializeProvenanceQueue([
        {
            id: 'old-consumed',
            sessionId: 'session-1',
            createdAt: '2026-03-01T00:00:00.000Z',
            repositoryPath: '/workspace/aiir',
            toolId: 'aiir-vscode',
            mode: 'provable',
            command: 'generate',
            source: 'aiir-command',
            promptKind: 'workspace',
            files: [],
            contentHash: sha256Text('old-consumed'),
            applied: true,
            consumed: true,
        },
        {
            id: 'fresh-consumed',
            sessionId: 'session-1',
            createdAt: new Date().toISOString(),
            repositoryPath: '/workspace/aiir',
            toolId: 'aiir-vscode',
            mode: 'provable',
            command: 'generate',
            source: 'aiir-command',
            promptKind: 'workspace',
            files: [],
            contentHash: sha256Text('fresh-consumed'),
            applied: true,
            consumed: true,
        },
        {
            id: 'active',
            sessionId: 'session-1',
            createdAt: '2026-03-01T00:00:00.000Z',
            repositoryPath: '/workspace/aiir',
            toolId: 'aiir-vscode',
            mode: 'provable',
            command: 'passive-capture',
            source: 'passive-capture',
            promptKind: 'auto',
            files: [],
            contentHash: sha256Text('active'),
            applied: true,
            consumed: false,
        },
    ]);

    const remaining = parseProvenanceQueue(purgeConsumedRecords(raw, 7));
    assert.deepEqual(remaining.map(record => record.id), ['fresh-consumed', 'active']);
    assert.equal(PROVABLE_QUEUE_FILENAME, 'editor_provenance.jsonl');
});

test('purgeConsumedRecords returns the original content for non-positive retention or empty queues', () => {
    assert.equal(purgeConsumedRecords('', 7), '');

    const raw = serializeProvenanceQueue([
        {
            id: 'kept',
            sessionId: 'session-1',
            createdAt: '2026-03-01T00:00:00.000Z',
            repositoryPath: '/workspace/aiir',
            toolId: 'aiir-vscode',
            mode: 'provable',
            command: 'generate',
            source: 'aiir-command',
            promptKind: 'workspace',
            files: [],
            contentHash: sha256Text('kept'),
            applied: true,
            consumed: true,
        },
    ]);

    assert.equal(purgeConsumedRecords(raw, 0), raw);
    assert.equal(purgeConsumedRecords(raw, -1), raw);
});
