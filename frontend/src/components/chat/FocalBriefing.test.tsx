import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { FocalBriefing } from './FocalBriefing';
import type { Task } from '../../types/api';

vi.mock('../../i18n', () => ({
  useI18n: () => ({
    t: (key: string, values?: Record<string, number | string>) =>
      values ? `${key}:${JSON.stringify(values)}` : key,
  }),
}));

const task = (id: number, status: Task['status'], extra: Partial<Task> = {}): Task => ({
  id,
  projectId: 'p',
  title: `Task ${id}`,
  description: '',
  status,
  blockedBy: [],
  blocks: [],
  ...extra,
});
const render = (tasks: Task[] | null): string =>
  renderToStaticMarkup(
    <FocalBriefing kanban={tasks && { tasks, goals: [] }} onOpenChat={() => {}} />
  );
const text = (html: string): string => html.replace(/<[^>]+>/g, ' ').replace(/&quot;/g, '"');

describe('Focal conversation opening', () => {
  it('greets without requiring project telemetry', () => {
    for (const tasks of [null, []]) {
      const html = render(tasks);
      expect(html).toContain('focalBriefing.greeting');
      expect(html).toContain('focalBriefing.invitation');
      expect(html).not.toContain('<details');
      expect(html).not.toContain('<dl');
    }
  });

  it('keeps only actionable follow-ups behind a closed disclosure', () => {
    const html = render([
      task(1, 'blocked', {
        chatId: 'a',
        chatTitle: 'Design',
        waitingKind: 'user',
        waitingReason: 'Choose a direction',
      }),
      task(2, 'in_progress', { chatId: 'b', chatTitle: 'Background work', chatRunning: true }),
      task(3, 'pending', { chatId: 'c', chatTitle: 'Idle work' }),
    ]);
    expect(html).toContain('<details');
    expect(html).not.toMatch(/<details[^>]*open/);
    expect(text(html)).toContain('Choose a direction');
    expect(text(html)).not.toContain('Background work');
    expect(text(html)).not.toContain('Idle work');
  });
});
