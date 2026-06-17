import { type ReceiptData } from './receipt_verifier';

export interface ReceiptEditorProvenanceRecordFile {
    path?: string;
    beforeHash?: string;
    afterHash?: string;
}

export interface ReceiptEditorProvenanceRecord {
    id?: string;
    command?: string;
    source?: string;
    promptKind?: string;
    sessionId?: string;
    createdAt?: string;
    baseCommitSha?: string;
    modelVendor?: string;
    modelFamily?: string;
    files?: ReceiptEditorProvenanceRecordFile[];
}

export interface ReceiptEditorProvenance {
    mode?: string;
    toolId?: string;
    records?: ReceiptEditorProvenanceRecord[];
}

export interface ReceiptToolContextEntry {
    tool?: string;
    extension_id?: string;
    feature?: string;
    evidence_level?: string;
    evidence?: string[];
    tool_version?: string;
}

export function isAIAuthored(receipt: ReceiptData): boolean {
    return receipt.ai_attestation?.is_ai_authored ?? false;
}

export function signalCount(receipt: ReceiptData): number {
    return receipt.ai_attestation?.signal_count ?? receipt.ai_attestation?.signals_detected?.length ?? 0;
}

export function authorshipClass(receipt: ReceiptData): string {
    return receipt.ai_attestation?.authorship_class || (isAIAuthored(receipt) ? 'ai_assisted' : 'human');
}

export function getAgentAttestation(receipt: ReceiptData): Record<string, string> | undefined {
    const candidate = receipt.extensions?.agent_attestation;
    if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
        return undefined;
    }

    return candidate as Record<string, string>;
}

export function getEditorProvenance(receipt: ReceiptData): ReceiptEditorProvenance | undefined {
    const candidate = receipt.extensions?.editor_provenance;
    if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
        return undefined;
    }

    return candidate as ReceiptEditorProvenance;
}

export function getToolContext(receipt: ReceiptData): ReceiptToolContextEntry[] {
    const candidate = receipt.extensions?.tool_context;
    if (!Array.isArray(candidate)) {
        return [];
    }

    return candidate.filter(entry => !!entry && typeof entry === 'object' && !Array.isArray(entry)) as ReceiptToolContextEntry[];
}

export function getToolContextSummary(receipt: ReceiptData): string {
    const contexts = getToolContext(receipt);
    if (contexts.length === 0) {
        return 'No companion tool context recorded';
    }

    return contexts.map(context => {
        const label = context.tool || context.extension_id || 'unknown tool';
        const detail = context.evidence_level || context.feature || 'context';
        return `${label} (${detail})`;
    }).join(', ');
}

export function getEditorProvenanceSummary(receipt: ReceiptData): string {
    const editor = getEditorProvenance(receipt);
    const firstRecord = editor?.records?.[0];
    if (!editor || !firstRecord) {
        return 'No deterministic editor provenance';
    }

    const command = firstRecord.command || 'generate';
    const fileCount = firstRecord.files?.length || 0;
    const model = [firstRecord.modelVendor, firstRecord.modelFamily].filter(Boolean).join(' ');
    const suffix = model ? ` via ${model}` : '';
    return `${command} across ${fileCount} file${fileCount === 1 ? '' : 's'}${suffix}`;
}

export function getAttestedSystemSummary(receipt: ReceiptData): string {
    const editor = getEditorProvenance(receipt);
    const firstRecord = editor?.records?.[0];
    const agent = getAgentAttestation(receipt);
    const toolId = editor?.toolId || agent?.tool_id;
    const editorModel = [firstRecord?.modelVendor, firstRecord?.modelFamily]
        .filter(Boolean)
        .join(' ');
    const model = editorModel || agent?.model_class || '';

    if (toolId && model) {
        return `${toolId} via ${model}`;
    }
    if (toolId) {
        return toolId;
    }
    if (model) {
        return model;
    }
    return 'No explicit tool attested';
}

export function hasEditorProvenance(receipt: ReceiptData): boolean {
    return !!getEditorProvenance(receipt)?.records?.length;
}

export function hasAIInvolvement(receipt: ReceiptData): boolean {
    return isAIAuthored(receipt) || !!getAgentAttestation(receipt)?.tool_id;
}

export function getAIInvolvementSummary(receipt: ReceiptData): string {
    const agent = getAgentAttestation(receipt);
    const tool = agent?.tool_id;
    const confidence = agent?.confidence;

    if (isAIAuthored(receipt) && tool) {
        return `Yes — detected and declared via ${tool}${confidence ? ` (${confidence})` : ''}`;
    }
    if (isAIAuthored(receipt)) {
        return 'Yes — detected from commit signals';
    }
    if (tool) {
        return `Yes — declared via ${tool}${confidence ? ` (${confidence})` : ''}`;
    }
    return 'No';
}

export function getAISignalsSummary(receipt: ReceiptData): string {
    const signals = receipt.ai_attestation?.signals_detected || [];
    if (signals.length === 0) {
        return 'No commit signals detected';
    }

    return `${signals.length} signal${signals.length === 1 ? '' : 's'} detected`;
}
