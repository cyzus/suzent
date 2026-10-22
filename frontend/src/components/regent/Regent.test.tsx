import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { FocalAgentStatus, FocalWakeup } from '../../lib/focalAgent';
import type { Task } from '../../types/api';
import { RegentIdentity } from './RegentHeader';
import { RegentCube } from './RegentCube';
import { RegentMark } from './RegentMark';
import { RegentPanelView } from './RegentPanel';
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
  it('reads as Suzent Regent on one line, so the header keeps its height', () => {
    const html = renderToStaticMarkup(<RegentIdentity status={status({ waiting: 1 })} />);
    expect(text(html)).toBe('chatList.focal.brand chatList.focal.name');
    expect(html).toContain('title="chatList.focal.role"');
    expect(html).toContain('data-regent-state="waiting"');
  });

  it('works while Regent runs, or while it answers in this chat before the next poll', () => {
    for (const html of [
      renderToStaticMarkup(<RegentIdentity status={status({ running: true })} />),
      renderToStaticMarkup(<RegentIdentity status={status()} working />),
    ]) {
      expect(html).toContain('title="chatList.focal.working"');
      expect(html).toContain('data-regent-state="working"');
    }
  });
});

describe('RegentPanelView', () => {
  const render = (
    tasks: Task[] | null,
    wakeups: FocalWakeup[] | null = [],
    value: FocalAgentStatus | null = status()
  ): string =>
    renderToStaticMarkup(
      <RegentPanelView
        status={value}
        kanban={tasks && { tasks, goals: [] }}
        wakeups={wakeups}
        onOpenChat={() => {}}
        board={<div>full-board</div>}
      />
    );

  it('shows only Regent and its schedule when all is clear, with the board one click away', () => {
    const plain = text(render([]));
    expect(plain).toContain('chatList.focal.allClear');
    expect(plain).toContain('regentPanel.wakeups');
    expect(plain).toContain('focalTools.noWakeups');
    expect(plain).toContain('regentPanel.fullBoard');
    expect(plain).not.toContain('regentPanel.needsYou');
    expect(plain).not.toContain('full-board');
  });

  it('stacks what needs the user, what runs and what stalled, each row opening its session', () => {
    const html = render([
      task(1, { chatId: 'b', chatTitle: 'Idle work', projectName: 'Docs' }),
      task(2, {
        status: 'blocked',
        chatId: 'a',
        chatTitle: 'Design',
        waitingKind: 'user',
        waitingReason: 'Choose a direction',
      }),
      task(3, { status: 'in_progress', chatId: 'c', chatTitle: 'Deploy', chatRunning: true }),
    ]);
    const plain = text(html);
    const order = ['regentPanel.needsYou', 'regentPanel.running', 'regentPanel.stalled'].map(
      (title) => plain.indexOf(title)
    );
    expect(order.every((at) => at >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(plain).toContain('Choose a direction');
    expect(plain).toContain('chatList.focal.waitingCount:1 · chatList.focal.stalledCount:1');
    expect(html.match(/<button type="button" class="flex w-full/g)).toHaveLength(3);
  });

  it('lists Regent’s own wake-ups', () => {
    const plain = text(
      render(
        [],
        [
          {
            id: 1,
            name: 'Weekly update',
            kind: 'reminder',
            schedule: 'once',
            scheduleKind: 'once',
            nextRunAt: null,
          },
        ]
      )
    );
    expect(plain).toContain('focalTools.reminder');
    expect(plain).toContain('Weekly update');
  });
});
