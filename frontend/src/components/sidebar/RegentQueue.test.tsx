import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { RegentQueueView } from './RegentQueue';
import type { ChatStateRow } from '../../lib/chatStates';

vi.mock('../../i18n', () => ({
  useI18n: () => ({
    t: (key: string, values?: Record<string, number>) =>
      values?.count !== undefined ? `${key}:${values.count}` : key,
  }),
}));

const row = (chatId: string, extra: Partial<ChatStateRow> = {}): ChatStateRow => ({
  chatId,
  title: `Chat ${chatId}`,
  projectId: 'p',
  projectName: 'suzent',
  state: 'waiting',
  waitingKind: 'reply',
  waitingReason: null,
  summary: null,
  lastActiveAt: null,
  resolvedAt: null,
  openTasks: 0,
  doneTasks: 0,
  ...extra,
});
const render = (rows: ChatStateRow[]): string =>
  renderToStaticMarkup(<RegentQueueView rows={rows} onOpenChat={() => {}} />);

describe("Regent's sidebar queue", () => {
  it('lists blocked chats before ones waiting on a reply, then running chats', () => {
    const html = render([
      row('a'),
      row('b', { waitingKind: 'approval' }),
      row('c', { state: 'running', waitingKind: null }),
      row('d', { state: 'idle', waitingKind: null }),
    ]);
    expect(html.indexOf('Chat b')).toBeLessThan(html.indexOf('Chat a'));
    expect(html.indexOf('Chat a')).toBeLessThan(html.indexOf('Chat c'));
    expect(html).not.toContain('Chat d');
    expect(html).toContain('chatBoard.reason.approval');
  });

  it('folds a long waiting list behind a show-more row', () => {
    const html = render(['1', '2', '3', '4', '5', '6'].map((id) => row(id)));
    expect(html).toContain('Chat 4');
    expect(html).not.toContain('Chat 5');
    expect(html).toContain('chatList.regentQueue.showMore:2');
  });

  it('says all clear when nothing waits or runs', () => {
    expect(render([row('a', { state: 'idle' })])).toContain('chatBoard.allClear');
  });
});
