import * as crypto from 'crypto';
import { canonicalJson as sharedCanonicalJson } from './canonical_json';

const CORE_KEYS = new Set(['type', 'schema', 'version', 'commit', 'ai_attestation', 'provenance']);
const MAX_DEPTH = 64;
const VERSION_RE = /^[0-9]+\.[0-9]+\.[0-9]+([.+-][0-9a-zA-Z.+-]*)?$/;
const VALID_GRANULARITIES = new Set(['session', 'forward-pass', 'token']);

function pythonRepr(value: unknown): string {
    if (typeof value === 'string') {
        return `'${value.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;
    }
    if (value === null || value === undefined) {
        return 'None';
    }
    if (typeof value === 'boolean') {
        return value ? 'True' : 'False';
    }
    return String(value);
}

export interface VerifyResult {
    valid: boolean;
    errors: string[];
}

export interface ReceiptData {
    type?: string;
    schema?: string;
    version?: string;
    receipt_id?: string;
    content_hash?: string;
    timestamp?: string;
    commit?: {
        sha?: string;
        tree_sha?: string;
        parent_shas?: string[];
        author?: { name?: string; email?: string };
        committer?: { name?: string; email?: string };
        subject?: string;
        message_hash?: string;
        diff_hash?: string;
        files_changed?: number;
        files?: string[];
    };
    ai_attestation?: {
        is_ai_authored?: boolean;
        is_bot_authored?: boolean;
        authorship_class?: string;
        signals_detected?: string[];
        bot_signals_detected?: string[];
        detection_method?: string;
        ai_authored?: boolean;
        signals?: Array<{ type?: string; source?: string; value?: string }>;
        signal_count?: number;
    };
    provenance?: {
        generator?: string;
        repository?: string;
        tool?: string;
    };
    extensions?: Record<string, unknown>;
    [key: string]: unknown;
}

export function canonicalJson(obj: unknown, depth = 0): string {
    return sharedCanonicalJson(obj, {
        escapeUnicode: true,
        maxDepth: MAX_DEPTH,
        rejectNonFiniteNumbers: true,
    }, depth);
}

export function sha256(value: string): string {
    return crypto.createHash('sha256').update(value, 'utf-8').digest('hex');
}

function timingSafeStringEqual(expected: string, actual: unknown): boolean {
    if (typeof actual !== 'string') {
        return false;
    }

    const expectedDigest = crypto.createHash('sha256')
        .update(String(Buffer.byteLength(expected, 'utf8')))
        .update(':')
        .update(expected, 'utf8')
        .digest();
    const actualDigest = crypto.createHash('sha256')
        .update(String(Buffer.byteLength(actual, 'utf8')))
        .update(':')
        .update(actual, 'utf8')
        .digest();

    return crypto.timingSafeEqual(expectedDigest, actualDigest);
}

function isInferenceReceipt(record: Record<string, unknown>): boolean {
    if (record.type === 'aiir.commit_receipt') {
        return false;
    }
    return ['model_fingerprint', 'sampling_params', 'tokens', 'granularity']
        .every(key => key in record);
}

function verifyInferenceReceipt(record: Record<string, unknown>): VerifyResult {
    const modelFingerprint = record.model_fingerprint;
    if (typeof modelFingerprint !== 'string' || modelFingerprint.length === 0) {
        return { valid: false, errors: ['missing or invalid model_fingerprint'] };
    }

    const samplingParams = record.sampling_params;
    if (samplingParams === null || typeof samplingParams !== 'object' || Array.isArray(samplingParams)) {
        return { valid: false, errors: ['missing or invalid sampling_params'] };
    }

    const tokens = record.tokens;
    if (!Array.isArray(tokens)) {
        return { valid: false, errors: ['missing or invalid tokens'] };
    }

    const granularity = record.granularity;
    if (typeof granularity !== 'string' || !VALID_GRANULARITIES.has(granularity)) {
        return {
            valid: false,
            errors: [`invalid granularity: ${pythonRepr(granularity)} (expected one of ['forward-pass', 'session', 'token'])`],
        };
    }

    const storedHash = typeof record.hash === 'string'
        ? record.hash
        : typeof record.receipt_hash === 'string'
            ? record.receipt_hash
            : '';
    if (!storedHash) {
        return { valid: false, errors: ["missing hash (expected 'hash' or 'receipt_hash' field)"] };
    }

    const payload = canonicalJson({
        granularity,
        model_fingerprint: modelFingerprint,
        sampling_params: samplingParams,
        tokens,
    });
    const expectedHash = sha256(payload);

    if (!timingSafeStringEqual(expectedHash, storedHash)) {
        return { valid: false, errors: ['hash mismatch — receipt content does not match stored hash'] };
    }

    return { valid: true, errors: [] };
}

export function verify(receipt: unknown): VerifyResult {
    if (receipt === null || typeof receipt !== 'object' || Array.isArray(receipt)) {
        return { valid: false, errors: ['receipt is not a dict'] };
    }

    const record = receipt as Record<string, unknown>;

    if (isInferenceReceipt(record)) {
        return verifyInferenceReceipt(record);
    }

    const errors: string[] = [];

    if (record.type !== 'aiir.commit_receipt') {
        errors.push(`unknown receipt type: ${pythonRepr(record.type)}`);
    }

    const schema = typeof record.schema === 'undefined' ? '' : record.schema;
    if (typeof schema !== 'string' || !schema.startsWith('aiir/')) {
        errors.push(`unknown schema: ${pythonRepr(schema)}`);
    }

    if (typeof record.version !== 'string' || !VERSION_RE.test(record.version)) {
        errors.push(`invalid version format: ${pythonRepr(record.version)}`);
    }

    if (errors.length > 0) {
        return { valid: false, errors };
    }

    const core: Record<string, unknown> = {};
    for (const key of Object.keys(record)) {
        if (CORE_KEYS.has(key)) {
            core[key] = record[key];
        }
    }

    const coreJson = canonicalJson(core);
    const hash = sha256(coreJson);
    const expectedHash = 'sha256:' + hash;
    const expectedId = 'g1-' + hash.slice(0, 32);

    const integrityErrors: string[] = [];
    if (!timingSafeStringEqual(expectedHash, record.content_hash)) {
        integrityErrors.push('content hash mismatch');
    }
    if (!timingSafeStringEqual(expectedId, record.receipt_id)) {
        integrityErrors.push('receipt_id mismatch');
    }

    return { valid: integrityErrors.length === 0, errors: integrityErrors };
}
