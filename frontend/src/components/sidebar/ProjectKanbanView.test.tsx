import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ProjectKanbanView } from './ProjectKanbanView';
import type { Task } from '../../types/api';

vi.mock('../../i18n', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string, values?: Record<string, string>) => values?.titles ?? key,
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
const render = (tasks: Task[]): string =>
  renderToStaticMarkup(<ProjectKanbanView kanban={{ tasks, goals: [] }} onOpenTask={() => {}} />);

describe('Project task overview', () => {
  it('renders conversation tasks as an ordered checklist with visible completed steps', () => {
    const html = renderToStaticMarkup(
      <ProjectKanbanView
        scope="chat"
        kanban={{
          goals: [],
          tasks: [
            task(3, 'pending'),
            task(1, 'completed'),
            task(2, 'in_progress'),
            task(4, 'cancelled'),
          ],
        }}
        onOpenTask={() => {}}
      />
    );
    expect(html).toContain('<ol');
    expect(html).toContain('line-through');
    expect(html).toContain('task.status.completed');
    expect(html).toContain('task.status.inprogress');
    expect(html.indexOf('Task 1')).toBeLessThan(html.indexOf('Task 2'));
    expect(html.indexOf('Task 2')).toBeLessThan(html.indexOf('Task 3'));
    expect(html).not.toContain('Task 4');
    expect(html).not.toContain('<details');
    expect(html).not.toContain('taskFlow.groups.');
    expect(html).not.toContain('type="checkbox"');
  });
  it.each(['chat', 'project'] as const)(
    'uses the selected %s scope for empty-state copy',
    (scope) => {
      const html = renderToStaticMarkup(
        <ProjectKanbanView scope={scope} kanban={{ tasks: [], goals: [] }} onOpenTask={() => {}} />
      );
      expect(html).toContain(scope === 'chat' ? 'taskFlow.chatEmpty' : 'taskFlow.projectEmpty');
      expect(html).not.toContain(scope === 'chat' ? 'taskFlow.projectEmpty' : 'taskFlow.chatEmpty');
    }
  );
  it('does not confuse an absent project with an active request', () => {
    const html = renderToStaticMarkup(<ProjectKanbanView kanban={null} onOpenTask={() => {}} />);
    expect(html).toContain('taskFlow.projectEmpty');
    expect(html).not.toContain('taskFlow.loading');
  });
  it('shows loading only for an active request and offers retry on failure', () => {
    const props = { kanban: null, onOpenTask: () => {} };
    const loading = renderToStaticMarkup(<ProjectKanbanView {...props} loading />);
    expect(loading).toContain('taskFlow.loading');
    expect(loading).not.toContain('taskFlow.projectEmpty');
    const failed = renderToStaticMarkup(<ProjectKanbanView {...props} error onRetry={() => {}} />);
    expect(failed).toContain('taskFlow.loadError');
    expect(failed).toContain('taskFlow.retry');
    expect(failed).not.toContain('taskFlow.loading');
  });
  it('keeps the selected task identifiable while preventing repeated navigation', () => {
    const html = renderToStaticMarkup(
      <ProjectKanbanView
        kanban={{ tasks: [task(1, 'in_progress', { chatId: 'chat-1' })], goals: [] }}
        selectedTaskId={1}
        pendingTaskId={1}
        onOpenTask={() => {}}
      />
    );
    expect(html).toContain('aria-current="true"');
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain('disabled=""');
  });
  it('does not offer navigation or execution for tasks without a conversation', () => {
    const html = render([task(1, 'pending'), task(2, 'blocked')]);
    const rows = [...html.matchAll(/<article[^>]*>([\s\S]*?)<\/article>/g)];
    expect(rows).toHaveLength(2);
    for (const row of rows) expect(row[1]).not.toContain('<button');
    expect(html).not.toContain('taskFlow.start');
  });
  it('prioritizes user attention and hides cancelled tasks, with completed collapsed', () => {
    const html = render([
      task(1, 'pending'),
      task(2, 'in_progress'),
      task(3, 'blocked', { waitingKind: 'user' }),
      task(4, 'cancelled'),
      task(5, 'completed'),
    ]);
    expect(html.indexOf('Task 3')).toBeLessThan(html.indexOf('Task 2'));
    expect(html.indexOf('Task 2')).toBeLessThan(html.indexOf('Task 1'));
    expect(html).not.toContain('Task 4');
    const sections = [...html.matchAll(/<details([^>]*)>([\s\S]*?)<\/details>/g)];
    const completed = sections.find((section) => section[2].includes('taskFlow.groups.completed'));
    expect(completed).toBeDefined();
    expect(completed![1]).not.toContain('open');
    expect(sections.find((section) => section[2].includes('taskFlow.groups.active'))![1]).toContain(
      'open'
    );
    expect(html).not.toContain('taskFlow.board');
  });
  it('shows a single actionable empty state instead of empty columns', () => {
    const html = render([]);
    expect(html).toContain('taskFlow.projectEmpty');
    expect(html).not.toContain('taskFlow.groups.pending');
  });
  it('shows dependency titles, progress and conversation links without an output action', () => {
    const html = render([
      task(1, 'pending', { title: 'Collect sources' }),
      task(2, 'blocked', {
        blockedBy: [1],
        waitingReason: 'Waiting for research',
        nextAction: 'Check sources',
      }),
      task(3, 'completed', {
        chatId: 'chat-1',
        resultSummary: 'Report is ready',
        resultPath: '/workspace/report.md',
      }),
    ]);
    expect(html).toContain('Collect sources');
    expect(html).toContain('Waiting for research');
    expect(html).toContain('Report is ready');
    expect(html).toContain('taskFlow.openChat');
    expect(html).not.toContain('taskFlow.viewResult');
  });
});
