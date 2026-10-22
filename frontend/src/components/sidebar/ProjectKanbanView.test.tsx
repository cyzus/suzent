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

describe('Session-grouped task overview', () => {
  const renderSessions = (tasks: Task[]): string =>
    renderToStaticMarkup(
      <ProjectKanbanView
        groupBy="session"
        kanban={{ tasks, goals: [] }}
        onOpenTask={() => {}}
        onOpenChat={() => {}}
      />
    );
  const sectionFor = (html: string, key: string): string | undefined =>
    [...html.matchAll(/<details([^>]*)>([\s\S]*?)<\/details>/g)].find((section) =>
      section[2].includes(`taskFlow.sessionGroups.${key}`)
    )?.[0];

  it('groups each session with its tasks and blocker under the session status', () => {
    const html = renderSessions([
      task(1, 'in_progress', {
        chatId: 'chat-a',
        chatTitle: 'Redesign site',
        projectSlug: 'web',
        projectName: 'Website',
      }),
      task(2, 'blocked', {
        chatId: 'chat-a',
        chatTitle: 'Redesign site',
        projectSlug: 'web',
        projectName: 'Website',
        waitingKind: 'user',
        waitingReason: 'Pick a palette',
      }),
      task(3, 'in_progress', { chatId: 'chat-b', chatTitle: 'Write docs', chatRunning: true }),
      task(4, 'pending', { chatId: 'chat-c', chatTitle: 'Plan launch' }),
      task(5, 'completed', { chatId: 'chat-d', chatTitle: 'Old release' }),
      task(6, 'cancelled', { chatId: 'chat-e', chatTitle: 'Dropped idea' }),
    ]);
    const attention = sectionFor(html, 'attention')!;
    expect(attention).toContain('>Website<');
    expect(attention).not.toContain('[web]');
    expect(attention).toContain('Redesign site');
    expect(attention).toContain('Task 1');
    expect(attention).toContain('Task 2');
    expect(attention).toContain('Pick a palette');
    expect(sectionFor(html, 'active')).toContain('Write docs');
    expect(sectionFor(html, 'active')).toContain('taskFlow.sessionRunning');
    expect(sectionFor(html, 'stalled')).toContain('Plan launch');
    expect(sectionFor(html, 'stalled')).toContain('taskFlow.sessionIdle');
    const completed = sectionFor(html, 'completed')!;
    expect(completed).toContain('Old release');
    expect(completed.slice(0, completed.indexOf('>'))).not.toContain('open');
    expect(html).not.toContain('Dropped idea');
    expect(html).not.toContain('taskFlow.groups.');
    expect(html.indexOf('Redesign site')).toBeLessThan(html.indexOf('Write docs'));
  });

  it('puts a mostly finished idle session under stalled, open work first and done folded away', () => {
    const html = renderSessions([
      task(1, 'completed', { chatId: 'chat-a', chatTitle: 'Security review' }),
      task(2, 'completed', { chatId: 'chat-a', chatTitle: 'Security review' }),
      task(3, 'pending', { chatId: 'chat-a', chatTitle: 'Security review', title: 'Write up' }),
    ]);
    const stalled = sectionFor(html, 'stalled')!;
    expect(stalled).toContain('Security review');
    expect(stalled).toContain('taskFlow.stalledReason');
    expect(stalled.indexOf('Write up')).toBeLessThan(stalled.indexOf('Task 1'));
    const done = stalled.match(/<details class="group\/done[^"]*">([\s\S]*?)<\/details>/);
    expect(done).not.toBeNull();
    expect(done![1]).toContain('taskFlow.doneCount');
    expect(done![1]).toContain('Task 1');
    expect(done![1]).not.toContain('Write up');
    expect(sectionFor(html, 'waiting')).toBeUndefined();
  });

  it('starts every session folded to its header, reason and task count', () => {
    const html = renderSessions([
      task(1, 'blocked', {
        chatId: 'chat-a',
        chatTitle: 'Landing page',
        waitingKind: 'user',
        waitingReason: 'Pick a palette',
      }),
      task(2, 'completed', { chatId: 'chat-a', chatTitle: 'Landing page' }),
      task(3, 'in_progress', { chatId: 'chat-b', chatTitle: 'Docs', chatRunning: true }),
    ]);
    const cards = [...html.matchAll(/<section aria-label="([^"]+)"[\s\S]*?<\/section>/g)];
    expect(cards.map((card) => card[1])).toEqual(['Landing page', 'Docs']);
    for (const [card] of cards) {
      expect(card).toContain('aria-expanded="false"');
      expect(card).toMatch(/<div id="session-tasks-[^"]+" hidden=""/);
    }
    expect(cards[0][0]).toContain('Pick a palette');
    expect(cards[0][0]).toContain('taskFlow.openCount');
    expect(cards[0][0]).toContain('taskFlow.doneCount');
    expect(cards[1][0]).not.toContain('taskFlow.doneCount');
  });

  it('keeps sessions waiting on a dependency out of stalled', () => {
    const html = renderSessions([
      task(1, 'blocked', {
        chatId: 'chat-a',
        chatTitle: 'Release',
        waitingKind: 'dependency',
        waitingReason: 'CI still running',
      }),
    ]);
    expect(sectionFor(html, 'waiting')).toContain('CI still running');
    expect(sectionFor(html, 'stalled')).toBeUndefined();
  });

  it('keeps tasks without a session together per project', () => {
    const html = renderSessions([task(1, 'pending'), task(2, 'pending')]);
    expect(html.match(/<section aria-label="taskFlow\.unassignedSession"/g)).toHaveLength(1);
  });

  it('ignores session grouping in the conversation checklist', () => {
    const html = renderToStaticMarkup(
      <ProjectKanbanView
        scope="chat"
        groupBy="session"
        kanban={{ tasks: [task(1, 'pending', { chatId: 'chat-a' })], goals: [] }}
        onOpenTask={() => {}}
      />
    );
    expect(html).toContain('<ol');
    expect(html).not.toContain('taskFlow.sessionGroups.');
  });
});
