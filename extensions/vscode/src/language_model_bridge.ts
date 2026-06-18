import * as vscode from 'vscode';

export const LANGUAGE_MODEL_RESPONSE_TIMEOUT_MS = 30_000;
export const LANGUAGE_MODEL_RESPONSE_MAX_CHARS = 100_000;

export interface BridgedLanguageModelResponse {
    text: AsyncIterable<string>;
}

export interface BridgedLanguageModel {
    vendor?: string;
    family?: string;
    sendRequest(
        messages: readonly unknown[],
        options: unknown,
        token: vscode.CancellationToken,
    ): Thenable<BridgedLanguageModelResponse>;
}

export interface LanguageModelBridge {
    hasSupport(): boolean;
    selectChatModel(): Promise<BridgedLanguageModel | undefined>;
    createUserMessage(content: string): unknown;
    collectResponseText(response: BridgedLanguageModelResponse): Promise<string>;
}

interface LanguageModelResponseLimits {
    timeoutMs?: number;
    maxChars?: number;
}

function createLanguageModelTimeoutError(timeoutMs: number): Error {
    return new Error(`Language model response timed out after ${timeoutMs}ms`);
}

async function closeResponseIterator(iterator: AsyncIterator<string>): Promise<void> {
    if (typeof iterator.return !== 'function') {
        return;
    }

    try {
        await iterator.return();
    } catch {
        // Ignore iterator cleanup failures.
    }
}

export async function collectResponseTextWithinLimits(
    response: BridgedLanguageModelResponse,
    limits?: LanguageModelResponseLimits,
): Promise<string> {
    const timeoutMs = limits?.timeoutMs ?? LANGUAGE_MODEL_RESPONSE_TIMEOUT_MS;
    const maxChars = limits?.maxChars ?? LANGUAGE_MODEL_RESPONSE_MAX_CHARS;
    const iterator = response.text[Symbol.asyncIterator]();
    const deadline = Date.now() + timeoutMs;
    let text = '';

    try {
        for (; ;) {
            const remainingMs = deadline - Date.now();
            if (remainingMs <= 0) {
                throw createLanguageModelTimeoutError(timeoutMs);
            }

            let timeoutHandle: NodeJS.Timeout | undefined;
            const result = await Promise.race([
                iterator.next(),
                new Promise<IteratorResult<string>>((_, reject) => {
                    timeoutHandle = setTimeout(() => reject(createLanguageModelTimeoutError(timeoutMs)), remainingMs);
                }),
            ]).finally(() => {
                if (timeoutHandle) {
                    clearTimeout(timeoutHandle);
                }
            });

            if (result.done) {
                return text;
            }

            text += String(result.value);
            if (text.length > maxChars) {
                throw new Error(`Language model response exceeded ${maxChars} characters`);
            }
        }
    } finally {
        await closeResponseIterator(iterator);
    }
}

function createDefaultLanguageModelBridge(): LanguageModelBridge {
    return {
        hasSupport(): boolean {
            const api = (vscode as typeof vscode & { lm?: { selectChatModels?: unknown } }).lm;
            return typeof api?.selectChatModels === 'function';
        },
        async selectChatModel(): Promise<BridgedLanguageModel | undefined> {
            const api = (vscode as typeof vscode & { lm?: { selectChatModels?: (selector?: unknown) => Thenable<vscode.LanguageModelChat[]> } }).lm;
            if (!api?.selectChatModels) {
                return undefined;
            }
            let models = await api.selectChatModels({ vendor: 'copilot' });
            if (models.length === 0) {
                models = await api.selectChatModels();
            }
            return models[0] as BridgedLanguageModel | undefined;
        },
        createUserMessage(content: string): unknown {
            return vscode.LanguageModelChatMessage.User(content);
        },
        async collectResponseText(response: BridgedLanguageModelResponse): Promise<string> {
            return collectResponseTextWithinLimits(response);
        },
    };
}

let activeLanguageModelBridge = createDefaultLanguageModelBridge();

export function hasLanguageModelSupport(): boolean {
    return activeLanguageModelBridge.hasSupport();
}

export async function selectProvableChatModel(): Promise<BridgedLanguageModel | undefined> {
    return activeLanguageModelBridge.selectChatModel();
}

export function createProvableUserMessage(content: string): unknown {
    return activeLanguageModelBridge.createUserMessage(content);
}

export async function collectChatResponseText(response: BridgedLanguageModelResponse): Promise<string> {
    return activeLanguageModelBridge.collectResponseText(response);
}

export function setLanguageModelBridgeForTests(bridge?: LanguageModelBridge): void {
    activeLanguageModelBridge = bridge ?? createDefaultLanguageModelBridge();
}