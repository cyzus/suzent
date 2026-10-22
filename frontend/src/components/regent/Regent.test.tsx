import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { FocalAgentStatus } from '../../lib/focalAgent';
import type { Task } from '../../types/api';
import { RegentIdentity, RegentPinned } from './RegentHeader';
import { RegentCube } from './RegentCube';
import { RegentMark } from './RegentMark';
import { regentState } from './regentState';

vi.mock('../../i18n', () => ({
  useI18n: () => ({
    t: (key: string, values?: Record<string, number>) =>
      values?.count !== undefined ? `${key}:${values.count}` : key,
  }),
}));

const status = (extra: Partial<FocalAgentStatus> = {}): FocalAgentStatus => ({
  chatId: 'focal-suzent',
  title: 'Regent',
  waiting: 0,
  autoRun: 0,
  running: false,
  ...extra,
});
const task = (id: number, extra: Partial<Task>): Task => ({
  id,
  projectId: 'p',
  title: `Task ${id}`,
  description: '',
  status: 'pending',
  blockedBy: [],
  blocks: [],
  ...extra,
});
const text = (html: string): string =>
  html
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

describe('regentState', () => {
  it('is working while Regent runs, even with things waiting', () => {
    expect(regentState(status({ running: true, waiting: 2 }))).toBe('working');
    expect(regentState(status({ waiting: 2 }))).toBe('waiting');
    expect(regentState(status())).toBe('idle');
    expect(regentState(null)).toBe('idle');
  });
});

describe('Regent marks', () => {
  it('sizes the flat mark by its head, with the circlet rising above the slot', () => {
    const html = renderToStaticMarkup(<RegentMark size={24} state="waiting" />);
    expect(html).toContain('data-regent-state="waiting"');
    expect(html).toContain('width="24"');
    expect(html).toContain('margin-top:-9.6px');
    expect(html).toContain('regent-gem');
  });

  it('gives the cube the same state hooks and its circlet', () => {
    const html = renderToStaticMarkup(<RegentCube size={52} state="working" />);
    expect(html).toContain('data-regent-state="working"');
    expect(html.match(/regent-cube-band/g)).toHaveLength(32);
    expect(html).toContain('regent-cube-gem');
  });
});

describe('RegentIdentity', () => {
  it('reads as Suzent Regent with its role, leaving counts to the pinned bar', () => {
    const html = text(
      renderToStaticMarkup(<RegentIdentity status={status({ waiting: 1, stalled: 1 })} />)
    );
    expect(html).toBe('chatList.focal.brand chatList.focal.name chatList.focal.role');
  });

  it('works while Regent runs, or while it answers in this chat before the next poll', () => {
    for (const html of [
      renderToStaticMarkup(<RegentIdentity status={status({ running: true })} />),
      renderToStaticMarkup(<RegentIdentity status={status()} working />),
    ]) {
      expect(text(html)).toContain('chatList.focal.working');
      expect(html).toContain('data-regent-state="working"');
    }
  });
});

describe('RegentPinned', () => {
  const render = (tasks: Task[] | null, onOpenBoard?: () => void): string =>
    renderToStaticMarkup(
      <RegentPinned
        kanban={tasks && { tasks, goals: [] }}
        onOpenChat={() => {}}
        onOpenBoard={onOpenBoard}
      />
    );
  const tasks = [
    task(1, { chatId: 'b', chatTitle: 'Idle work', projectName: 'Docs' }),
    task(2, {
      status: 'blocked',
      chatId: 'a',
      chatTitle: 'Design',
      waitingKind: 'user',
      waitingReason: 'Choose a direction',
    }),
  ];

  it('is not there when nothing waits on the user or has stalled', () => {
    expect(render([])).toBe('');
    expect(render(null)).toBe('');
  });

  it('counts what waits and what stalled, and leads with the most pressing item', () => {
    const plain = text(render(tasks));
    expect(plain).toContain('chatList.focal.waitingCount:1 · chatList.focal.stalledCount:1');
    expect(plain).toContain('Choose a direction');
    expect(plain).not.toContain('Idle work');
  });

  it('offers the board only while it is closed', () => {
    expect(text(render(tasks, () => {}))).toContain('chatList.focal.openBoard');
    expect(text(render(tasks))).not.toContain('chatList.focal.openBoard');
  });
});
