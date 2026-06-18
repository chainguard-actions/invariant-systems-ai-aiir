export interface ReceiptReviewInfo {
    outcome: 'approve' | 'reject' | 'flag' | 'unknown';
    comment?: string;
    reviewer?: string;
    timestamp?: string;
    commitSha?: string;
}

interface JsonRecordLike {
    [key: string]: unknown;
}

function asRecord(value: unknown): JsonRecordLike | undefined {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return undefined;
    }

    return value as JsonRecordLike;
}

function readFirstString(record: JsonRecordLike, keys: string[]): string | undefined {
    for (const key of keys) {
        const value = record[key];
        if (typeof value === 'string') {
            const trimmed = value.trim();
            if (trimmed) {
                return trimmed;
            }
        }
    }

    return undefined;
}

export function getReceiptReviewInfo(value: unknown): ReceiptReviewInfo | undefined {
    const record = asRecord(value);
    if (!record) {
        return undefined;
    }

    const rawOutcome = readFirstString(record, ['review_outcome', 'reviewOutcome']);
    if (!rawOutcome) {
        return undefined;
    }

    const normalized = rawOutcome.toLowerCase();
    const outcome = normalized === 'approve' || normalized === 'approved'
        ? 'approve'
        : normalized === 'reject' || normalized === 'rejected'
            ? 'reject'
            : normalized === 'flag' || normalized === 'flagged'
                ? 'flag'
                : 'unknown';

    return {
        outcome,
        comment: readFirstString(record, ['review_comment', 'comment']),
        reviewer: readFirstString(record, ['reviewer', 'reviewer_name', 'reviewed_by', 'actor']),
        timestamp: readFirstString(record, ['reviewed_at', 'timestamp']),
        commitSha: readFirstString(record, ['commit_sha', 'sha']),
    };
}

export function getReceiptReviewStatusLabel(review: ReceiptReviewInfo | undefined, reviewExpected: boolean): string {
    if (!review) {
        return reviewExpected ? 'Pending review' : 'No review recorded';
    }

    switch (review.outcome) {
        case 'approve':
            return 'Approved';
        case 'reject':
            return 'Rejected';
        case 'flag':
            return 'Flagged';
        default:
            return 'Review recorded';
    }
}

export function getReceiptReviewStatusSummary(review: ReceiptReviewInfo | undefined, reviewExpected: boolean): string | undefined {
    if (!review && !reviewExpected) {
        return undefined;
    }

    return getReceiptReviewStatusLabel(review, reviewExpected);
}
