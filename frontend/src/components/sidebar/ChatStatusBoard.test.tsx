import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { ChatStateRow, ChatStates } from '../../lib/chatStates';

let states: ChatStates | null = null;

vi.mock('../../i18n', () => ({
  useI18n: () => ({
    t: (key: string, values?: Record<string, number>) =>
      values?.count !== undefined ? `${key}:${values.count}` : key,
  }),
}));
vi.mock('../../hooks/useChatStates', () => ({
  useChatStates: () => ({ states, failed: false }),
  refreshChatStates: () => Promise.resolve(),
}));

const { ChatStatusBoard } = await import('./ChatStatusBoard');

const row = (title: string, extra: Partial<ChatStateRow> = {}): ChatStateRow => ({
  chatId: title.toLowerCase().replace(/\s+/g, '-'),
  title,
  projectId: 'p-web',
  projectName: 'Website',
  state: 'idle',
  waitingKind: null,
  waitingReason: null,
  summary: null,
  lastActiveAt: null,
  resolvedAt: null,
  openTasks: 0,
  doneTasks: 0,
  ...extra,
});

const render = (rows: ChatStateRow[], projectFilter = '__all__'): string => {
  states = { chats: rows, counts: { waiting: 0, running: 0, idle: 0, resolved: 0 } };
  return renderToStaticMarkup(
    <ChatStatusBoard
      projectFilter={projectFilter}
      onProjectFilter={() => {}}
      onOpenChat={() => {}}
    />
  );
};

const sections = (html: string): { label: string; open: boolean; body: string }[] =>
  [...html.matchAll(/<details([^>]*)>([\s\S]*?)<\/details>/g)].map((match) => ({
    label: match[2].match(/chatBoard\.groups\.(\w+)/)![1],
    open: match[1].includes(' open'),
    body: match[2],
  }));

describe("Regent's chat board", () => {
  it('groups chats as waiting, running, idle, then resolved folded away', () => {
    const html = render([
      row('Docs', { state: 'resolved' }),
      row('Release', { state: 'running' }),
      row('Palette', { state: 'waiting', waitingKind: 'reply', waitingReason: 'Pick one' }),
      row('Notes', { summary: 'Draft is up' }),
    ]);
    const groups = sections(html);
    expect(groups.map((group) => group.label)).toEqual(['waiting', 'running', 'idle', 'resolved']);
    expect(groups.map((group) => group.open)).toEqual([true, true, true, false]);
    expect(groups[0].body).toContain('chatBoard.reason.reply');
    expect(groups[0].body).toContain('Pick one');
    expect(groups[2].body).toContain('Draft is up');
    expect(html).toContain('chatBoard.waitingSummary:1');
  });

  it('shows no task lists, only where each chat stands', () => {
    const html = render([row('Plan', { openTasks: 3, doneTasks: 2 })]);
    expect(html).not.toContain('taskFlow.openCount');
    expect(html).not.toContain('aria-expanded');
  });

  it('narrows to a project, and falls back to all when the remembered one is gone', () => {
    const rows = [row('Site'), row('Deploy', { projectId: 'p-ops', projectName: 'Ops' })];
    expect(render(rows, 'p-ops')).not.toContain('>Site<');
    expect(render(rows, 'p-gone')).toContain('>Site<');
    expect(render([row('Site')])).not.toContain('taskFlow.projectFilter');
  });

  it('says so when nothing waits on the user', () => {
    expect(render([row('Notes')])).toContain('chatBoard.allClear');
    expect(render([])).toContain('chatBoard.empty');
  });
});
