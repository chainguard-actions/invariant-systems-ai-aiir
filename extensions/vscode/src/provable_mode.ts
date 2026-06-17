import crypto = require('crypto');
import { canonicalJson } from './canonical_json';

export const PROVABLE_QUEUE_FILENAME = 'editor_provenance.jsonl';

export interface StructuredEditOperation {
    type: 'replace-range' | 'create-file';
    path: string;
    startLine?: number;
    startCharacter?: number;
    endLine?: number;
    endCharacter?: number;
    rangeText?: string;
    text: string;
}

export interface StructuredEditPlan {
    summary: string;
    operations: StructuredEditOperation[];
}

export interface ProvenanceFileRecord {
    path: string;
    beforeHash: string;
    afterHash: string;
}

export interface ProvenanceEditRecord {
    id: string;
    sessionId: string;
    createdAt: string;
    repositoryPath: string;
    branch?: string;
    baseCommitSha?: string;
    toolId: 'aiir-vscode';
    mode: 'provable';
    command: 'generate' | 'refactor' | 'fix' | 'passive-capture';
    modelVendor?: string;
    modelFamily?: string;
    source: 'aiir-command' | 'aiir-chat' | 'passive-capture';
    promptKind: 'selection' | 'file' | 'workspace' | 'auto';
    files: ProvenanceFileRecord[];
    contentHash: string;
    previousRecordHash?: string;
    applied: boolean;
    consumed: boolean;
}

interface StructuredEditPlanCandidate {
    summary?: unknown;
    operations?: unknown;
}

export function sha256Text(value: string): string {
    return `sha256:${crypto.createHash('sha256').update(value, 'utf8').digest('hex')}`;
}

function computeRecordHash(record: Omit<ProvenanceEditRecord, 'contentHash'>): string {
    return sha256Text(canonicalJson(record));
}

export function extractFirstJsonObject(raw: string): string | undefined {
    for (let start = 0; start < raw.length; start += 1) {
        if (raw[start] !== '{') {
            continue;
        }
        let depth = 0;
        let inString = false;
        let escaping = false;
        for (let index = start; index < raw.length; index += 1) {
            const current = raw[index];
            if (escaping) {
                escaping = false;
                continue;
            }
            if (current === '\\') {
                escaping = true;
                continue;
            }
            if (current === '"') {
                inString = !inString;
                continue;
            }
            if (inString) {
                continue;
            }
            if (current === '{') {
                depth += 1;
            } else if (current === '}') {
                depth -= 1;
                if (depth === 0) {
                    const candidate = raw.slice(start, index + 1);
                    try {
                        JSON.parse(candidate);
                        return candidate;
                    } catch {
                        break;
                    }
                }
            }
        }
    }
    return undefined;
}

export function parseStructuredEditPlan(raw: string): StructuredEditPlan {
    const extracted = extractFirstJsonObject(raw);
    if (!extracted) {
        throw new Error('No valid JSON object was found in the model response.');
    }
    const parsed = JSON.parse(extracted) as StructuredEditPlanCandidate;
    if (!Array.isArray(parsed.operations)) {
        throw new Error('The model response did not include an operations array.');
    }
    const operations = parsed.operations.map((operation, index) => {
        if (!operation || typeof operation !== 'object') {
            throw new Error(`Operation ${index + 1} is not an object.`);
        }
        const record = operation as Record<string, unknown>;
        const type = record.type;
        const path = record.path;
        const text = record.text;
        if (type !== 'replace-range' && type !== 'create-file') {
            throw new Error(`Operation ${index + 1} uses an unsupported type.`);
        }
        if (typeof path !== 'string') {
            throw new Error(`Operation ${index + 1} is missing a valid path.`);
        }
        if (path.trim() === '') {
            throw new Error(`Operation ${index + 1} is missing a valid path.`);
        }
        if (typeof text !== 'string') {
            throw new Error(`Operation ${index + 1} is missing replacement text.`);
        }
        return {
            type,
            path,
            text,
            startLine: typeof record.startLine === 'number' ? record.startLine : undefined,
            startCharacter: typeof record.startCharacter === 'number' ? record.startCharacter : undefined,
            endLine: typeof record.endLine === 'number' ? record.endLine : undefined,
            endCharacter: typeof record.endCharacter === 'number' ? record.endCharacter : undefined,
            rangeText: typeof record.rangeText === 'string' ? record.rangeText : undefined,
        } satisfies StructuredEditOperation;
    });
    let summary = `Prepared ${operations.length} operation${operations.length === 1 ? '' : 's'}`;
    if (typeof parsed.summary === 'string') {
        const trimmedSummary = parsed.summary.trim();
        if (trimmedSummary !== '') {
            summary = trimmedSummary;
        }
    }
    return { summary, operations };
}

export function parseProvenanceQueue(raw: string | undefined): ProvenanceEditRecord[] {
    if (!raw) {
        return [];
    }
    const records: ProvenanceEditRecord[] = [];
    for (const line of raw.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (trimmed.length === 0) {
            continue;
        }
        try {
            const parsed = JSON.parse(trimmed);
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                records.push(parsed as ProvenanceEditRecord);
            }
        } catch {
            continue;
        }
    }
    return records;
}

export function serializeProvenanceQueue(records: ProvenanceEditRecord[]): string {
    if (records.length === 0) {
        return '';
    }
    return records.map(record => JSON.stringify(record)).join('\n') + '\n';
}

export function appendProvenanceRecord(
    existingRaw: string | undefined,
    record: Omit<ProvenanceEditRecord, 'contentHash' | 'previousRecordHash'>,
): { record: ProvenanceEditRecord; serialized: string } {
    const existing = parseProvenanceQueue(existingRaw);
    const previousRecordHash = existing.length > 0 ? existing[existing.length - 1].contentHash : undefined;
    const nextRecordBase = {
        ...record,
        previousRecordHash,
    };
    const nextRecord: ProvenanceEditRecord = {
        ...nextRecordBase,
        contentHash: computeRecordHash(nextRecordBase),
    };
    return {
        record: nextRecord,
        serialized: serializeProvenanceQueue([...existing, nextRecord]),
    };
}

export function purgeConsumedRecords(raw: string | undefined, retentionDays: number): string {
    const records = parseProvenanceQueue(raw);
    if (retentionDays <= 0) {
        return raw ?? '';
    }
    if (records.length === 0) {
        return raw ?? '';
    }
    const cutoff = Date.now() - retentionDays * 86_400_000;
    const kept = records.filter(r => !r.consumed || new Date(r.createdAt).getTime() >= cutoff);
    return serializeProvenanceQueue(kept);
}
