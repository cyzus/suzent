import { describe, expect, it } from 'vitest';
import type { Message } from '../types/api';
import {
  compactionNoticeDetails,
  latestCompaction,
  resolvedCompactionFailures,
} from './compactionNotices';

const notice = (content: string): Message => ({ role: 'notice', content });

describe('historical compaction failures', () => {
  it('reconciles stored legacy notices after reload without live state', () => {
    const messages = [
      notice('Context compaction failed: Compaction timed out. Original history preserved.'),
      { role: 'assistant', content: 'Continuing' } as Message,
      notice('Auto context compaction: 242k -> 10k tokens (506 -> 9 messages)'),
      notice('Compaction timed out. Original history preserved.'),
    ];
    expect([...resolvedCompactionFailures(JSON.parse(JSON.stringify(messages)))]).toEqual([0]);
  });

  it('does not resolve failures for skipped or running attempts or earlier successes', () => {
    expect(
      resolvedCompactionFailures([
        notice('Context compacted'),
        notice('Compaction failed'),
        notice('Auto compaction running...'),
        notice('Context compaction skipped: nothing to compact'),
      ]).size
    ).toBe(0);
  });

  it('uses structured lifecycle metadata regardless of notice wording', () => {
    expect([
      ...resolvedCompactionFailures([
        { ...notice('失败'), metadata: { kind: 'context_compaction', stage: 'error' } },
        { ...notice('成功'), metadata: { kind: 'context_compaction', stage: 'complete' } },
      ]),
    ]).toEqual([0]);
    expect(resolvedCompactionFailures([notice('Context compaction failed: error')]).size).toBe(0);
  });
});

describe('latest compaction', () => {
  it('prefers stored details and skips running and skipped passes', () => {
    const messages: Message[] = [
      notice('Auto context compaction: 150.0k -> 20.0k tokens'),
      { role: 'assistant', content: 'Done' },
      {
        role: 'notice',
        content: 'Auto compaction 90.0k -> 15.0k',
        timestamp: '2026-11-13T00:00:00Z',
        metadata: {
          kind: 'context_compaction',
          stage: 'complete',
          tokens_before: 90_000,
          tokens_after: 15_000,
          reason: 'prepared',
        },
      },
      notice('Auto compaction running...'),
      notice('Compaction skipped: nothing to compact'),
    ];

    const last = latestCompaction(messages);
    expect(last?.timestamp).toBe('2026-11-13T00:00:00Z');
    expect(last?.details).toMatchObject({
      stage: 'complete',
      tokensBefore: 90_000,
      tokensAfter: 15_000,
      reason: 'prepared',
    });
  });

  it('is undefined for ordinary notices', () => {
    expect(compactionNoticeDetails(notice('Images were dropped'))).toBeUndefined();
    expect(latestCompaction([notice('Images were dropped')])).toBeUndefined();
  });
});
