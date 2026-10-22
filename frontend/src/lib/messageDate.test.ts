import { describe, expect, it } from 'vitest';
import { conversationTimeLabel, messageDayLabel } from './chatUtils';

const labels = { today: '今天', yesterday: '昨天' };
const now = new Date(2026, 9, 19, 12);
const stamp = (year: number, month: number, day: number): string =>
  new Date(year, month, day, 9, 30).toISOString();

describe('Conversation dates', () => {
  it('uses local calendar days for today and yesterday', () => {
    expect(messageDayLabel(stamp(2026, 9, 19), 'zh-CN', labels, now)?.label).toBe('今天');
    expect(messageDayLabel(stamp(2026, 9, 18), 'zh-CN', labels, now)?.label).toBe('昨天');
    expect(messageDayLabel(stamp(2026, 8, 30), 'zh-CN', labels, new Date(2026, 9, 1))?.label).toBe(
      '昨天'
    );
  });
  it('localizes older dates and includes the year only when needed', () => {
    expect(messageDayLabel(stamp(2026, 9, 17), 'zh-CN', labels, now)?.label).toBe('10月17日');
    expect(messageDayLabel(stamp(2025, 9, 17), 'en', labels, now)?.label).toBe('October 17, 2025');
  });
  it('skips missing and invalid timestamps', () => {
    expect(messageDayLabel(undefined, 'en', labels, now)).toBeNull();
    expect(messageDayLabel('invalid', 'en', labels, now)).toBeNull();
  });
  it('shares a day key across messages within a local day', () => {
    expect(messageDayLabel(new Date(2026, 9, 19, 1).toISOString(), 'en', labels, now)?.key).toBe(
      messageDayLabel(new Date(2026, 9, 19, 23).toISOString(), 'en', labels, now)?.key
    );
  });
  it('shows one centered timestamp after a gap, not on consecutive messages', () => {
    const first = new Date(2026, 9, 19, 9, 30).toISOString();
    const next = new Date(2026, 9, 19, 9, 32).toISOString();
    const later = new Date(2026, 9, 19, 9, 37).toISOString();
    expect(conversationTimeLabel(first, undefined, 'zh-CN', labels, now)).toBe('今天 09:30');
    expect(conversationTimeLabel(next, first, 'zh-CN', labels, now)).toBeNull();
    expect(conversationTimeLabel(later, next, 'zh-CN', labels, now)).toBe('09:37');
  });
  it('shows the date when crossing midnight even without a long gap', () => {
    const before = new Date(2026, 9, 18, 23, 59).toISOString();
    const after = new Date(2026, 9, 19, 0, 1).toISOString();
    expect(conversationTimeLabel(after, before, 'zh-CN', labels, now)).toContain('今天');
    expect(conversationTimeLabel('invalid', before, 'zh-CN', labels, now)).toBeNull();
  });
});
