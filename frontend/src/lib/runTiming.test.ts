import { describe, expect, it } from 'vitest';
import type { Message } from '../types/api';
import { collectRunTimings, recordedWorkedSeconds } from './runTiming';

const first: Message = {
  role: 'assistant',
  content: 'first',
  _streaming_run_id: 'first',
  run_started_at: '2026-10-24T10:00:00Z',
  run_finished_at: '2026-10-24T10:00:30Z',
};
const second: Message = {
  role: 'assistant',
  content: 'second',
  _streaming_run_id: 'second',
  run_started_at: '2026-10-24T10:10:30Z',
  run_finished_at: '2026-10-24T10:10:50Z',
};

describe('run timing', () => {
  it('uses recorded active time instead of overnight question waits', () => {
    const overnight = {
      ...first,
      run_finished_at: '2026-10-24T18:45:00Z',
      run_active_seconds: 12.8,
      parts: [{ type: 'tool' as const, toolName: 'ask_question' }],
    };
    expect(recordedWorkedSeconds([overnight, second])).toBe(32);
    const legacy = { ...overnight, run_active_seconds: undefined };
    expect(recordedWorkedSeconds([legacy, second])).toBeUndefined();
    const merged = { ...legacy, run_timings: collectRunTimings([legacy, second]) };
    expect(recordedWorkedSeconds([merged, second])).toBeUndefined();
  });
  it('adds only the active draft elapsed time to completed runs', () => {
    const draft = { ...second, _streaming_draft: true, run_finished_at: undefined };
    expect(recordedWorkedSeconds([first, draft], Date.parse('2026-10-24T10:10:40Z'))).toBe(40);
    expect(recordedWorkedSeconds([first, draft])).toBe(30);
  });
  it('sums work without counting the ten-minute wait or duplicate runs', () => {
    expect(recordedWorkedSeconds([first, second, first])).toBe(50);
  });

  it('keeps run identities through repeated bubble merges and reloads', () => {
    const merged = { ...first, run_timings: collectRunTimings([first, second]) };
    const reloaded: Message = JSON.parse(JSON.stringify(merged));
    expect(collectRunTimings([reloaded, second])).toHaveLength(2);
    expect(recordedWorkedSeconds([reloaded, second])).toBe(50);
  });

  it('ignores incomplete and invalid runs while retaining real zero durations', () => {
    expect(recordedWorkedSeconds([{ ...first, run_finished_at: undefined }])).toBeUndefined();
    expect(recordedWorkedSeconds([{ ...first, run_finished_at: 'invalid' }])).toBeUndefined();
    expect(recordedWorkedSeconds([{ ...first, run_finished_at: first.run_started_at }])).toBe(0);
  });
});
