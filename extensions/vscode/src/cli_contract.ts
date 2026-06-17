export type ReviewSelectionValue = 'approve' | 'reject' | 'flag';

const REVIEW_OUTCOME_MAP: Record<ReviewSelectionValue, string> = {
    approve: 'approved',
    reject: 'rejected',
    flag: 'commented',
};

export function buildVerifyReceiptArgs(receiptPath: string, verifySignature = false): string[] {
    const args = ['--verify', receiptPath];
    if (verifySignature) {
        args.push('--verify-signature');
    }
    return args;
}

export function buildGenerateReceiptArgs(options?: { commitSha?: string; includeEditorContext?: boolean }): string[] {
    const args = ['--pretty'];
    if (options?.commitSha) {
        args.push('--commit', options.commitSha);
    }
    return args;
}

export function buildGenerateRangeArgs(rangeSpec: string): string[] {
    return ['--range', rangeSpec, '--pretty'];
}

export function mapReviewOutcomeToCli(outcome: ReviewSelectionValue): string {
    return REVIEW_OUTCOME_MAP[outcome];
}

export function buildReviewReceiptArgs(commitSha: string, outcome: ReviewSelectionValue, comment = ''): string[] {
    const args = ['--review', commitSha, '--review-outcome', mapReviewOutcomeToCli(outcome)];
    const trimmedComment = comment.trim();
    if (trimmedComment) {
        args.push('--review-comment', trimmedComment);
    }
    return args;
}
