import { describe, expect, it, beforeEach } from 'vitest';
import { useContextUsageStore, type ContextUsage } from './useContextUsageStore';

const FULL: ContextUsage = {
  input_tokens: 100,
  output_tokens: 20,
  total_tokens: 120,
  context_tokens: 5000,
  cache_write_tokens: 3,
  cache_read_tokens: 4,
  requests: 2,
  details: { reasoning_tokens: 9 },
};

describe('useContextUsageStore', () => {
  beforeEach(() => {
    useContextUsageStore.setState({ usage: null, usageByChatId: {}, compaction: null });
  });

  it('merges a mid-run context size without blanking the last run counters', () => {
    const store = useContextUsageStore.getState();
    store.setUsageForChat('c1', FULL);
    store.mergeUsageForChat('c1', { context_tokens: 6400 });

    const usage = useContextUsageStore.getState().getUsageForChat('c1')!;
    expect(usage.context_tokens).toBe(6400);
    expect(usage.input_tokens).toBe(100);
    expect(usage.requests).toBe(2);
    expect(useContextUsageStore.getState().usage).toEqual(usage);
  });

  it('applies counters once the run reports them', () => {
    const store = useContextUsageStore.getState();
    store.setUsageForChat('c1', FULL);
    store.mergeUsageForChat('c1', { context_tokens: 6400, input_tokens: 900, requests: 5 });

    const usage = useContextUsageStore.getState().getUsageForChat('c1')!;
    expect(usage.input_tokens).toBe(900);
    expect(usage.requests).toBe(5);
    expect(usage.output_tokens).toBe(20);
  });

  it('does not seed one chat from another chat usage', () => {
    const store = useContextUsageStore.getState();
    store.setUsageForChat('c1', FULL);
    store.mergeUsageForChat('c2', { context_tokens: 42 });

    const other = useContextUsageStore.getState().getUsageForChat('c2')!;
    expect(other.context_tokens).toBe(42);
    expect(other.input_tokens).toBe(0);
    expect(other.requests).toBe(0);
  });

  it('tracks a compaction pass so the panel can animate it', () => {
    const store = useContextUsageStore.getState();
    store.setCompaction({
      active: true,
      stage: 'start',
      source: 'auto_midrun',
      label: 'Compaction running...',
    });
    expect(useContextUsageStore.getState().compaction?.active).toBe(true);

    store.setCompaction({
      active: false,
      stage: 'complete',
      source: 'auto_midrun',
      label: 'Compaction 120k -> 40k',
    });
    expect(useContextUsageStore.getState().compaction?.active).toBe(false);

    store.clearCompaction();
    expect(useContextUsageStore.getState().compaction).toBeNull();
  });
});
