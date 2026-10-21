import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { FocalAgentCardView } from './FocalAgentCard';
import type { FocalAgentStatus } from '../lib/focalAgent';

vi.mock('../i18n', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string, values?: Record<string, number>) =>
      values?.count !== undefined ? `${key}:${values.count}` : key,
  }),
}));

const status = (extra: Partial<FocalAgentStatus> = {}): FocalAgentStatus => ({
  chatId: 'focal-suzent',
  title: 'SUZENT',
  waiting: 0,
  autoRun: 0,
  running: false,
  ...extra,
});
const render = (value: FocalAgentStatus | null, active = false): string =>
  renderToStaticMarkup(<FocalAgentCardView status={value} active={active} onOpen={() => {}} />);
const text = (html: string): string => html.replace(/<[^>]+>/g, ' ');

describe('SUZENT contact card', () => {
  it('reads like a contact: name, role and an online presence dot', () => {
    const html = render(status());
    expect(html).toContain('chatList.focal.name');
    expect(html).toContain('chatList.focal.role');
    expect(html).toContain('bg-emerald-500');
    expect(text(html)).not.toContain('chatList.focal.allClear');
    expect(html).toContain('aria-label="chatList.focal.allClear"');
  });

  it('spells out what is waiting, stalled and auto-running', () => {
    const html = render(status({ waiting: 1, stalled: 2, autoRun: 3 }));
    expect(text(html)).toContain(
      'chatList.focal.waitingCount:1 · chatList.focal.stalledCount:2 · chatList.focal.autoRunCount:3'
    );
    expect(html).toContain('title="chatList.focal.waitingBadge:1"');
  });

  it('shows when SUZENT itself is working', () => {
    const html = render(status({ running: true, autoRun: 2 }));
    expect(text(html)).toContain('chatList.focal.working · chatList.focal.autoRunCount:2');
    expect(html).toContain('bg-brutal-blue animate-pulse');
    expect(html).not.toContain('bg-emerald-500');
  });

  it('shows a new message with its unread count and time', () => {
    const at = new Date();
    at.setHours(9, 5, 0, 0);
    const html = render(
      status({
        unread: 2,
        waiting: 1,
        lastMessage: 'Deploy needs your approval.',
        lastMessageAt: at.toISOString(),
      })
    );
    expect(text(html)).toContain('Deploy needs your approval.');
    expect(text(html)).toContain('09:05');
    expect(text(html)).toMatch(/>?\s2\s/);
    expect(html).not.toContain('chatList.focal.waitingCount');
  });

  it('drops the new-message state once SUZENT is open', () => {
    const html = render(status({ unread: 2, lastMessage: 'Deploy needs your approval.' }), true);
    expect(html).toContain('aria-current="page"');
    expect(html).not.toContain('Deploy needs your approval.');
  });

  it('keeps the entry usable before its status arrives', () => {
    const html = render(null);
    expect(html).toContain('chatList.focal.name');
    expect(text(html)).not.toContain('chatList.focal.allClear');
    expect(html).toContain('aria-label="chatList.focal.allClear"');
  });
});
