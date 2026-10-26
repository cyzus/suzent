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
  title: 'Regent',
  waiting: 0,
  running: false,
  ...extra,
});
const render = (value: FocalAgentStatus | null, active = false): string =>
  renderToStaticMarkup(<FocalAgentCardView status={value} active={active} onOpen={() => {}} />);
const text = (html: string): string => html.replace(/<[^>]+>/g, ' ');

describe('Regent contact card', () => {
  it('reads like a pinned contact: its mark, name and an all-clear line', () => {
    const html = render(status());
    expect(html).toContain('chatList.focal.name');
    expect(html).toContain('data-regent-state="idle"');
    expect(text(html)).toContain('chatList.focal.allClear');
    expect(text(html)).not.toContain('chatList.focal.role');
  });

  it('spells out how many chats wait on the user and how many are running', () => {
    const html = render(
      status({ waiting: 1, states: { waiting: 1, running: 3, idle: 2, resolved: 0 } })
    );
    expect(text(html)).toContain('chatList.focal.waitingCount:1 · chatList.focal.runningCount:3');
    expect(html).not.toContain('chatList.focal.waitingBadge');
  });

  it('shows when Regent itself is working', () => {
    const html = render(
      status({ running: true, states: { waiting: 0, running: 2, idle: 0, resolved: 0 } })
    );
    expect(text(html)).toContain('chatList.focal.working · chatList.focal.runningCount:2');
    expect(html).toContain('data-regent-state="working"');
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

  it('drops the new-message state once Regent is open', () => {
    const html = render(status({ unread: 2, lastMessage: 'Deploy needs your approval.' }), true);
    expect(html).toContain('aria-current="page"');
    expect(html).not.toContain('Deploy needs your approval.');
  });

  it('grows into a profile with the cube while Regent is open', () => {
    const html = render(status({ waiting: 1 }), true);
    expect(html).toContain('regent-card-hero');
    expect(html).toContain('regent-cube');
    expect(html).not.toContain('regent-mark');
    expect(text(html)).toContain('chatList.focal.waitingCount:1');
  });

  it('keeps the entry usable before its status arrives', () => {
    const html = render(null);
    expect(html).toContain('chatList.focal.name');
    expect(text(html)).toContain('chatList.focal.allClear');
  });
});
