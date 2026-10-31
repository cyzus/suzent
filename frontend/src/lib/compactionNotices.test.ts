import { describe, expect, it } from 'vitest';
import type { Message } from '../types/api';
import { resolvedCompactionFailures } from './compactionNotices';

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
