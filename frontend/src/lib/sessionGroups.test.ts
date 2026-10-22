import { describe, expect, it } from 'vitest';
import {
  ALL_PROJECTS,
  boardActionChanges,
  filterKanbanByProject,
  projectOptions,
} from './sessionGroups';
import type { Goal, Task } from '../types/api';

const task = (id: number, projectId: string, extra: Partial<Task> = {}): Task => ({
  id,
  projectId,
  title: `Task ${id}`,
  description: '',
  status: 'pending',
  blockedBy: [],
  blocks: [],
  ...extra,
});
const goal = (id: number, projectId: string): Goal =>
  ({ id, projectId, objective: `Goal ${id}`, status: 'active' }) as Goal;

describe('all-projects board filter', () => {
  const kanban = {
    goals: [goal(1, 'p-web'), goal(2, 'p-ops')],
    tasks: [
      task(1, 'p-web', { projectName: 'Website' }),
      task(2, 'p-ops', { projectName: 'Ops' }),
      task(3, 'p-web', { projectName: 'Website' }),
      task(4, 'p-old', { projectName: 'Old', status: 'cancelled' }),
    ],
  };

  it('offers each project with live tasks once, sorted by name', () => {
    expect(projectOptions(kanban)).toEqual([
      { id: 'p-ops', label: 'Ops' },
      { id: 'p-web', label: 'Website' },
    ]);
    expect(projectOptions(null)).toEqual([]);
  });

  it('narrows goals and tasks to one project, or leaves the board whole', () => {
    const web = filterKanbanByProject(kanban, 'p-web')!;
    expect(web.tasks.map((item) => item.id)).toEqual([1, 3]);
    expect(web.goals.map((item) => item.id)).toEqual([1]);
    expect(filterKanbanByProject(kanban, ALL_PROJECTS)).toBe(kanban);
  });
});

describe('board row actions', () => {
  const tasks = [
    task(1, 'p', { status: 'blocked', waitingKind: 'user' }),
    task(2, 'p', { status: 'in_progress' }),
    task(3, 'p', { status: 'completed' }),
  ];
  const changes = (action: Parameters<typeof boardActionChanges>[1]) =>
    boardActionChanges(tasks, action).map(({ task, status }) => [task.id, status]);

  it('resumes only waiting tasks, back to pending', () => {
    expect(changes('resume')).toEqual([[1, 'pending']]);
  });

  it('marks done or cancels every open task and leaves finished ones alone', () => {
    expect(changes('complete')).toEqual([
      [1, 'completed'],
      [2, 'completed'],
    ]);
    expect(changes('cancel')).toEqual([
      [1, 'cancelled'],
      [2, 'cancelled'],
    ]);
  });

  it('reopens finished tasks', () => {
    expect(changes('reopen')).toEqual([[3, 'pending']]);
  });

  it('offers nothing a task could not use', () => {
    expect(boardActionChanges([task(4, 'p', { status: 'completed' })], 'resume')).toEqual([]);
  });
});
