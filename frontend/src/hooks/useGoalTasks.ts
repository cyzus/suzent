import React, { createContext, useCallback, useContext, useRef, useState } from 'react';
import type { Goal, Task } from '../types/api';
import { getApiBase } from '../lib/api';
import { subscribeToBusPayloads } from './useEventBus';

export interface KanbanData {
  goals: Goal[];
  tasks: Task[];
}

interface GoalTasksContextValue {
  // Chat-scoped (plan tab)
  goal: Goal | null;
  tasks: Task[];
  /** The chat id the current goal/tasks belong to (null until first load).
   *  Consumers use this to tell "data for the chat I'm in" from stale data
   *  mid-switch, without relying on load-timing heuristics. */
  goalChatId: string | null;
  refresh: (projectId?: string | null, chatId?: string | null) => Promise<void>;
  goalAction: (action: 'pause' | 'resume' | 'clear') => Promise<void>;
  // Project-scoped (kanban tab)
  kanban: KanbanData | null;
  refreshKanban: (projectId?: string | null) => Promise<void>;
  // Human-operated mutations
  updateTask: (taskId: number, updates: { status?: string; title?: string; description?: string }) => Promise<void>;
  createTask: (projectId: string, title: string, status?: string) => Promise<void>;
  deleteTask: (taskId: number) => Promise<void>;
}

const GoalTasksContext = createContext<GoalTasksContextValue | null>(null);

export const GoalTasksProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [goal, setGoal] = useState<Goal | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [goalChatId, setGoalChatId] = useState<string | null>(null);
  const [kanban, setKanban] = useState<KanbanData | null>(null);

  const currentProjectIdRef = useRef<string | null>(null);
  const currentChatIdRef = useRef<string | null>(null);
  const currentKanbanProjectIdRef = useRef<string | null>(null);
  const refreshRef = useRef<GoalTasksContextValue['refresh'] | null>(null);
  const refreshKanbanRef = useRef<GoalTasksContextValue['refreshKanban'] | null>(null);

  const refresh = useCallback(async (projectId?: string | null, chatId?: string | null) => {
    if (projectId !== undefined) currentProjectIdRef.current = projectId ?? null;
    if (chatId !== undefined) currentChatIdRef.current = chatId ?? null;
    const pid = currentProjectIdRef.current;
    const cid = currentChatIdRef.current;
    if (!pid || !cid) { setGoal(null); setTasks([]); setGoalChatId(cid ?? null); return; }
    try {
      const [goalRes, tasksRes] = await Promise.all([
        fetch(`${getApiBase()}/project/goal?project_id=${pid}&chat_id=${cid}`),
        fetch(`${getApiBase()}/project/tasks?project_id=${pid}&chat_id=${cid}`),
      ]);
      if (goalRes.ok) setGoal(await goalRes.json());
      if (tasksRes.ok) setTasks(await tasksRes.json());
      // Stamp which chat this data belongs to (guard against out-of-order
      // responses: only stamp if the request's chat is still the current one).
      if (currentChatIdRef.current === cid) setGoalChatId(cid);
    } catch (err) {
      console.warn('Failed to fetch goal/tasks:', err);
    }
  }, []);

  const goalAction = useCallback(async (action: 'pause' | 'resume' | 'clear') => {
    const pid = currentProjectIdRef.current;
    const cid = currentChatIdRef.current;
    if (!pid || !cid) return;
    try {
      const res = await fetch(`${getApiBase()}/project/goal/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: pid, chat_id: cid, action }),
      });
      if (res.ok) {
        const updated = await res.json();
        setGoal(updated && updated.id ? (updated as Goal) : null);
      }
    } catch (err) {
      console.warn('Failed to update goal:', err);
    }
  }, []);

  const refreshKanban = useCallback(async (projectId?: string | null) => {
    if (projectId !== undefined) currentKanbanProjectIdRef.current = projectId ?? null;
    const pid = currentKanbanProjectIdRef.current;
    if (!pid) { setKanban(null); return; }
    try {
      const res = await fetch(`${getApiBase()}/project/kanban?project_id=${pid}`);
      if (res.ok) setKanban(await res.json());
    } catch (err) {
      console.warn('Failed to fetch project kanban:', err);
    }
  }, []);

  React.useEffect(() => {
    refreshRef.current = refresh;
  }, [refresh]);

  React.useEffect(() => {
    refreshKanbanRef.current = refreshKanban;
  }, [refreshKanban]);

  React.useEffect(() => {
    return subscribeToBusPayloads((payload) => {
      if (payload?.event !== 'goal_tasks_changed') return;

      const projectId = typeof payload.project_id === 'string' ? payload.project_id : null;
      const chatId = typeof payload.chat_id === 'string' ? payload.chat_id : null;
      if (!projectId) return;

      if (projectId === currentProjectIdRef.current && chatId === currentChatIdRef.current) {
        refreshRef.current?.();
      }
      if (projectId === currentKanbanProjectIdRef.current) {
        refreshKanbanRef.current?.();
      }
    });
  }, []);

  const updateTask = useCallback(async (
    taskId: number,
    updates: { status?: string; title?: string; description?: string },
  ) => {
    try {
      const res = await fetch(`${getApiBase()}/project/tasks/${taskId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });
      if (res.ok) {
        const updated: Task = await res.json();
        // Optimistically update kanban state
        setKanban(prev => {
          if (!prev) return prev;
          return { ...prev, tasks: prev.tasks.map(t => t.id === taskId ? updated : t) };
        });
        // Also update chat-scoped tasks if relevant
        setTasks(prev => prev.map(t => t.id === taskId ? updated : t));
      }
    } catch (err) {
      console.warn('Failed to update task:', err);
    }
  }, []);

  const createTask = useCallback(async (projectId: string, title: string, status = 'pending') => {
    try {
      const res = await fetch(`${getApiBase()}/project/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, title, status }),
      });
      if (res.ok) {
        // Refresh the full kanban after creation
        await refreshKanban(projectId);
      }
    } catch (err) {
      console.warn('Failed to create task:', err);
    }
  }, [refreshKanban]);

  const deleteTask = useCallback(async (taskId: number) => {
    try {
      const res = await fetch(`${getApiBase()}/project/tasks/${taskId}`, { method: 'DELETE' });
      if (res.ok) {
        setKanban(prev => prev ? { ...prev, tasks: prev.tasks.filter(t => t.id !== taskId) } : prev);
        setTasks(prev => prev.filter(t => t.id !== taskId));
      }
    } catch (err) {
      console.warn('Failed to delete task:', err);
    }
  }, []);

  const contextValue = React.useMemo(
    () => ({ goal, tasks, goalChatId, refresh, goalAction, kanban, refreshKanban, updateTask, createTask, deleteTask }),
    [goal, tasks, goalChatId, refresh, goalAction, kanban, refreshKanban, updateTask, createTask, deleteTask],
  );

  return React.createElement(GoalTasksContext.Provider, { value: contextValue }, children);
};

export function useGoalTasks() {
  const ctx = useContext(GoalTasksContext);
  if (!ctx) throw new Error('useGoalTasks must be used within GoalTasksProvider');
  return ctx;
}
