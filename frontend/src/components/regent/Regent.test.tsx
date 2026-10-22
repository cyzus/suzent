import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { FocalAgentStatus } from '../../lib/focalAgent';
import type { Task } from '../../types/api';
import { RegentHeaderDetailsView, RegentIdentity } from './RegentHeader';
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
  it('reads as Suzent Regent, with the cube set beside the name instead of in the row', () => {
    const html = renderToStaticMarkup(<RegentIdentity state="waiting" />);
    expect(text(html)).toBe('chatList.focal.brand chatList.focal.name');
    expect(html).toContain('class="absolute left-0 "');
    expect(html).toContain('data-regent-state="waiting"');
  });
});

describe('RegentHeaderDetailsView', () => {
  const render = (
    tasks: Task[] | null,
    extra: Partial<React.ComponentProps<typeof RegentHeaderDetailsView>> = {}
  ): string =>
    renderToStaticMarkup(
      <RegentHeaderDetailsView
        state="idle"
        kanban={tasks && { tasks, goals: [] }}
        wakeups={[]}
        onOpenChat={() => {}}
        {...extra}
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

  it('says all clear, with its role, when nothing waits or stalls', () => {
    const plain = text(render([]));
    expect(plain).toBe('chatList.focal.role chatList.focal.allClear');
  });

  it('lists what needs the user before what stalled, each opening its session', () => {
    const html = render(tasks);
    const plain = text(html);
    expect(plain.indexOf('Choose a direction')).toBeLessThan(plain.indexOf('Idle work'));
    expect(plain).toContain('regentHeader.needsYou');
    expect(plain).toContain('regentHeader.stalled');
    expect(html.match(/<button/g)).toHaveLength(2);
  });

  it('shows working, the wake-up count, and the board link only while the board is closed', () => {
    const plain = text(
      render([], {
        state: 'working',
        wakeups: [
          {
            id: 1,
            name: 'Weekly update',
            kind: 'reminder',
            schedule: 'once',
            scheduleKind: 'once',
            nextRunAt: null,
          },
        ],
        onOpenBoard: () => {},
      })
    );
    expect(plain).toContain('chatList.focal.working');
    expect(plain).toContain('regentHeader.wakeups:1');
    expect(plain).toContain('regentHeader.board');
    expect(text(render([]))).not.toContain('regentHeader.board');
  });

  it('lines its content up under the name it was measured against', () => {
    expect(render([], { inset: 120 })).toContain('padding-left:120px');
  });
});
