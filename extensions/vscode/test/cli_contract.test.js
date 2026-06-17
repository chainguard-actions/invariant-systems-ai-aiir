const test = require('node:test');
const assert = require('node:assert/strict');

const {
    buildGenerateReceiptArgs,
    buildReviewReceiptArgs,
    buildVerifyReceiptArgs,
    mapReviewOutcomeToCli,
} = require('../out/cli_contract.js');

test('buildVerifyReceiptArgs uses the public --verify flag contract', () => {
    assert.deepEqual(buildVerifyReceiptArgs('/tmp/receipt.json'), ['--verify', '/tmp/receipt.json']);
    assert.deepEqual(
        buildVerifyReceiptArgs('/tmp/receipt.json', true),
        ['--verify', '/tmp/receipt.json', '--verify-signature'],
    );
});

test('mapReviewOutcomeToCli maps extension choices to CLI outcomes', () => {
    assert.equal(mapReviewOutcomeToCli('approve'), 'approved');
    assert.equal(mapReviewOutcomeToCli('reject'), 'rejected');
    assert.equal(mapReviewOutcomeToCli('flag'), 'commented');
});

test('buildGenerateReceiptArgs supports exact commit regeneration', () => {
    assert.deepEqual(buildGenerateReceiptArgs(), ['--pretty']);
    assert.deepEqual(
        buildGenerateReceiptArgs({ commitSha: 'abc1234' }),
        ['--pretty', '--commit', 'abc1234'],
    );
});

test('buildReviewReceiptArgs trims comments and uses CLI outcome values', () => {
    assert.deepEqual(
        buildReviewReceiptArgs('abc1234', 'flag', ' needs follow-up '),
        ['--review', 'abc1234', '--review-outcome', 'commented', '--review-comment', 'needs follow-up'],
    );
});
