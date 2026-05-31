import React, { createContext, useCallback, useContext, useRef, useState } from 'react';
import type { Goal, Task } from '../types/api';
import { getApiBase } from '../lib/api';

export interface KanbanData {
  goals: Goal[];
  tasks: Task[];
}

interface GoalTasksContextValue {
  // Chat-scoped (plan tab)
  goal: Goal | null;
  tasks: Task[];
  refresh: (projectId?: string | null, chatId?: string | null) => Promise<void>;
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
  const [kanban, setKanban] = useState<KanbanData | null>(null);

  const currentProjectIdRef = useRef<string | null>(null);
  const currentChatIdRef = useRef<string | null>(null);
  const currentKanbanProjectIdRef = useRef<string | null>(null);

  const refresh = useCallback(async (projectId?: string | null, chatId?: string | null) => {
    if (projectId !== undefined) currentProjectIdRef.current = projectId ?? null;
    if (chatId !== undefined) currentChatIdRef.current = chatId ?? null;
    const pid = currentProjectIdRef.current;
    const cid = currentChatIdRef.current;
    if (!pid || !cid) { setGoal(null); setTasks([]); return; }
    try {
      const [goalRes, tasksRes] = await Promise.all([
        fetch(`${getApiBase()}/project/goal?project_id=${pid}&chat_id=${cid}`),
        fetch(`${getApiBase()}/project/tasks?project_id=${pid}&chat_id=${cid}`),
      ]);
      if (goalRes.ok) setGoal(await goalRes.json());
      if (tasksRes.ok) setTasks(await tasksRes.json());
    } catch (err) {
      console.warn('Failed to fetch goal/tasks:', err);
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
    () => ({ goal, tasks, refresh, kanban, refreshKanban, updateTask, createTask, deleteTask }),
    [goal, tasks, refresh, kanban, refreshKanban, updateTask, createTask, deleteTask],
  );

  return React.createElement(GoalTasksContext.Provider, { value: contextValue }, children);
};

export function useGoalTasks() {
  const ctx = useContext(GoalTasksContext);
  if (!ctx) throw new Error('useGoalTasks must be used within GoalTasksProvider');
  return ctx;
}
