import { describe, expect, it } from 'vitest';
import { canResolve, countStates, withResolved, type ChatStateRow } from './chatStates';
import { formatRelativeTime } from './chatUtils';

const row = (extra: Partial<ChatStateRow>): ChatStateRow => ({
  chatId: 'c',
  title: 'Chat',
  projectId: 'p',
  projectName: 'Project',
  state: 'waiting',
  waitingKind: null,
  waitingReason: null,
  summary: null,
  lastActiveAt: null,
  resolvedAt: null,
  openTasks: 0,
  doneTasks: 0,
  ...extra,
});

describe('resolving a chat', () => {
  it('waits for an open question or approval to be answered first', () => {
    expect(canResolve(row({ waitingKind: 'question' }))).toBe(false);
    expect(canResolve(row({ waitingKind: 'approval' }))).toBe(false);
    expect(canResolve(row({ waitingKind: 'reply' }))).toBe(true);
    expect(canResolve(row({ waitingKind: 'task' }))).toBe(true);
    expect(canResolve(row({ state: 'idle' }))).toBe(true);
  });
});

describe('formatRelativeTime', () => {
  const ago = (ms: number): string => new Date(Date.now() - ms).toISOString();

  it('speaks the interface language', () => {
    expect(formatRelativeTime(ago(3 * 3_600_000), 'en')).toMatch(/^3 ?h.* ago$/);
    expect(formatRelativeTime(ago(2 * 86_400_000), 'zh-CN')).toContain('前');
    expect(formatRelativeTime(ago(1000), 'en')).toBe('now');
  });

  it('is empty for nothing, nonsense or the future', () => {
    expect(formatRelativeTime(null, 'en')).toBe('');
    expect(formatRelativeTime('soon', 'en')).toBe('');
    expect(formatRelativeTime(new Date(Date.now() + 60_000).toISOString(), 'en')).toBe('');
  });
});

describe('showing a resolve before it saves', () => {
  const now = new Date('2026-10-31T00:00:00Z');

  it('clears the wait when resolving and starts idle when reopening', () => {
    const resolved = withResolved(row({ waitingKind: 'reply', waitingReason: 'Pick' }), true, now);
    expect(resolved).toMatchObject({
      state: 'resolved',
      waitingKind: null,
      waitingReason: null,
      resolvedAt: now.toISOString(),
    });
    expect(withResolved(resolved, false, now)).toMatchObject({ state: 'idle', resolvedAt: null });
  });

  it('counts rows by state', () => {
    expect(countStates([row({}), row({ state: 'idle' }), row({ state: 'waiting' })])).toEqual({
      waiting: 2,
      running: 0,
      idle: 1,
      resolved: 0,
    });
  });
});
