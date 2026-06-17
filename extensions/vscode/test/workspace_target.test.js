const test = require('node:test');
const assert = require('node:assert/strict');

const {
    filterWorkspaceFolderTargets,
    isPathInside,
    isWorkspaceIsolationBlockingAccess,
    matchesWorkspaceFolderSelector,
    resolvePreferredWorkspaceFolderTarget,
    resolveWorkspaceFolderTarget,
} = require('../out/workspace_target.js');

test('isPathInside matches files inside a workspace root', () => {
    assert.equal(isPathInside('/workspace/aiir', '/workspace/aiir/src/extension.ts'), true);
    assert.equal(isPathInside('/workspace/aiir', '/workspace/aiir'), true);
    assert.equal(isPathInside('/workspace/aiir', '/workspace/site/index.html'), false);
    assert.equal(isPathInside('/workspace/aiir/', '/workspace/aiir/src/index.ts'), true);
    assert.equal(isPathInside('C:\\workspace\\aiir', 'C:\\workspace\\aiir\\src\\extension.ts'), true);
});

test('isPathInside rejects sibling prefix tricks and normalizes Windows drive casing', () => {
    assert.equal(isPathInside('/workspace/aiir', '/workspace/aiir-other/src/index.ts'), false);
    assert.equal(isPathInside('C:\\Workspace\\AIIR', 'c:\\workspace\\aiir\\src\\extension.ts'), true);
    assert.equal(isPathInside('C:\\workspace\\aiir', 'C:\\workspace\\aiir-other\\src\\extension.ts'), false);
});

test('resolveWorkspaceFolderTarget returns the deepest matching folder', () => {
    const folders = [
        { fsPath: '/workspace', value: 'root' },
        { fsPath: '/workspace/aiir', value: 'aiir' },
    ];

    assert.equal(resolveWorkspaceFolderTarget(folders, '/workspace/aiir/extensions/vscode/src/extension.ts'), 'aiir');
});

test('resolveWorkspaceFolderTarget preserves falsey folder values', () => {
    const folders = [{ fsPath: '/workspace/aiir', value: 0 }];

    assert.equal(resolveWorkspaceFolderTarget(folders, '/workspace/aiir/extensions/vscode/src/extension.ts'), 0);
});

test('resolveWorkspaceFolderTarget returns the only folder when workspace is single-root', () => {
    const folders = [{ fsPath: '/workspace/aiir', value: 'aiir' }];

    assert.equal(resolveWorkspaceFolderTarget(folders), 'aiir');
    assert.equal(resolveWorkspaceFolderTarget(folders, '/workspace/elsewhere/file.txt'), 'aiir');
});

test('resolveWorkspaceFolderTarget leaves multi-root selection unresolved without context', () => {
    const folders = [
        { fsPath: '/workspace/aiir', value: 'aiir' },
        { fsPath: '/workspace/site', value: 'site' },
    ];

    assert.equal(resolveWorkspaceFolderTarget(folders), undefined);
});

test('resolvePreferredWorkspaceFolderTarget falls back to the preferred repository when no direct context exists', () => {
    const folders = [
        { fsPath: '/workspace/aiir', value: 'aiir' },
        { fsPath: '/workspace/site', value: 'site' },
    ];

    assert.equal(resolvePreferredWorkspaceFolderTarget(folders, undefined, '/workspace/site/docs.html'), 'site');
});

test('resolvePreferredWorkspaceFolderTarget picks the deepest preferred folder match', () => {
    const folders = [
        { fsPath: '/workspace', value: 'root' },
        { fsPath: '/workspace/site', value: 'site' },
    ];

    assert.equal(resolvePreferredWorkspaceFolderTarget(folders, undefined, '/workspace/site/docs/page.html'), 'site');
});

test('resolvePreferredWorkspaceFolderTarget prefers the direct target over the preferred path', () => {
    const folders = [
        { fsPath: '/workspace/aiir', value: 'aiir' },
        { fsPath: '/workspace/site', value: 'site' },
    ];

    assert.equal(
        resolvePreferredWorkspaceFolderTarget(
            folders,
            '/workspace/aiir/extensions/vscode/src/extension.ts',
            '/workspace/site/docs.html',
        ),
        'aiir',
    );
});

test('resolvePreferredWorkspaceFolderTarget preserves falsey preferred folder values', () => {
    const folders = [
        { fsPath: '/workspace/aiir', value: 'aiir' },
        { fsPath: '/workspace/site', value: 0 },
    ];

    assert.equal(resolvePreferredWorkspaceFolderTarget(folders, undefined, '/workspace/site/docs.html'), 0);
});

test('resolvePreferredWorkspaceFolderTarget falls back to the only folder when preferred path does not match', () => {
    const folders = [{ fsPath: '/workspace/aiir', value: 'aiir' }];

    assert.equal(resolvePreferredWorkspaceFolderTarget(folders, undefined, '/workspace/site/docs.html'), 'aiir');
});

test('resolvePreferredWorkspaceFolderTarget stays unresolved in multi-root workspaces without direct or preferred context', () => {
    const folders = [
        { fsPath: '/workspace/aiir', value: 'aiir' },
        { fsPath: '/workspace/site', value: 'site' },
    ];

    assert.equal(resolvePreferredWorkspaceFolderTarget(folders), undefined);
});

test('filterWorkspaceFolderTargets allows a single-root workspace without an allowlist', () => {
    const folders = [{ name: 'aiir', fsPath: '/workspace/aiir', value: 'aiir' }];

    assert.deepEqual(filterWorkspaceFolderTargets(folders, [], true).map(folder => folder.value), ['aiir']);
});

test('filterWorkspaceFolderTargets blocks multi-root discovery without an allowlist when isolation is enabled', () => {
    const folders = [
        { name: 'aiir', fsPath: '/workspace/aiir', value: 'aiir' },
        { name: 'site', fsPath: '/workspace/site', value: 'site' },
    ];

    assert.deepEqual(filterWorkspaceFolderTargets(folders, [], true), []);
});

test('filterWorkspaceFolderTargets allows all folders when isolation is disabled', () => {
    const folders = [
        { name: 'aiir', fsPath: '/workspace/aiir', value: 'aiir' },
        { name: 'site', fsPath: '/workspace/site', value: 'site' },
    ];

    assert.deepEqual(filterWorkspaceFolderTargets(folders, [], false).map(folder => folder.value), ['aiir', 'site']);
});

test('filterWorkspaceFolderTargets matches allowlist entries by folder name and path', () => {
    const folders = [
        { name: 'aiir', fsPath: '/workspace/aiir', value: 'aiir' },
        { name: 'site', fsPath: '/workspace/site', value: 'site' },
    ];

    assert.deepEqual(
        filterWorkspaceFolderTargets(folders, ['site', '/workspace/aiir'], true).map(folder => folder.value),
        ['aiir', 'site'],
    );
});

test('matchesWorkspaceFolderSelector matches by exact folder name and rejects blanks', () => {
    assert.equal(matchesWorkspaceFolderSelector({ name: 'aiir', fsPath: '/workspace/aiir', value: 'aiir' }, 'aiir'), true);
    assert.equal(matchesWorkspaceFolderSelector({ name: 'aiir', fsPath: '/workspace/aiir', value: 'aiir' }, '   '), false);
});

test('filterWorkspaceFolderTargets ignores blank selectors and matches unnamed folders by normalized path', () => {
    const folders = [
        { fsPath: '/workspace/aiir/', value: 'aiir' },
        { fsPath: '/workspace/site', value: 'site' },
    ];

    assert.deepEqual(
        filterWorkspaceFolderTargets(folders, ['   ', '/workspace/aiir'], true).map(folder => folder.value),
        ['aiir'],
    );
});

test('isWorkspaceIsolationBlockingAccess reports multi-root lockout without an allowlist', () => {
    assert.equal(isWorkspaceIsolationBlockingAccess(2, [], true), true);
    assert.equal(isWorkspaceIsolationBlockingAccess(1, [], true), false);
    assert.equal(isWorkspaceIsolationBlockingAccess(2, ['aiir'], true), false);
    assert.equal(isWorkspaceIsolationBlockingAccess(2, ['   '], true), true);
    assert.equal(isWorkspaceIsolationBlockingAccess(2, [], false), false);
});
