export interface CanonicalJsonOptions {
    escapeUnicode?: boolean;
    maxDepth?: number;
    rejectNonFiniteNumbers?: boolean;
}

export function canonicalJson(
    value: unknown,
    options: CanonicalJsonOptions = {},
    depth = 0,
): string {
    if (typeof options.maxDepth === 'number' && depth > options.maxDepth) {
        throw new Error(`canonical JSON depth limit exceeded (max ${options.maxDepth})`);
    }

    if (value === null || value === undefined) {
        return 'null';
    }

    if (typeof value === 'boolean') {
        return value ? 'true' : 'false';
    }

    if (typeof value === 'number') {
        if (options.rejectNonFiniteNumbers && !Number.isFinite(value)) {
            throw new Error('NaN/Infinity not allowed');
        }
        return JSON.stringify(value);
    }

    if (typeof value === 'string') {
        const encoded = JSON.stringify(value);
        if (!options.escapeUnicode) {
            return encoded;
        }
        return encoded.replace(/[\u0080-\uffff]/g, (char) => {
            return '\\u' + char.charCodeAt(0).toString(16).padStart(4, '0');
        });
    }

    if (Array.isArray(value)) {
        return '[' + value.map(item => canonicalJson(item, options, depth + 1)).join(',') + ']';
    }

    if (typeof value === 'object') {
        const record = value as Record<string, unknown>;
        const keys = Object.keys(record).sort();
        const pairs = keys
            .filter(key => record[key] !== undefined)
            .map(key => canonicalJson(key, options, depth + 1) + ':' + canonicalJson(record[key], options, depth + 1));
        return '{' + pairs.join(',') + '}';
    }

    throw new Error('cannot encode type: ' + typeof value);
}
