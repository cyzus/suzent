import React, { createContext, useCallback, useContext, useRef, useState } from 'react';
import type { Goal, Task } from '../types/api';
import { getApiBase } from '../lib/api';

export interface KanbanData {
  goals: Goal[];
  tasks: Task[];
}

interface GoalTasksContextValue {
  // Chat-scoped (plan tab — only the owning chat's goal/tasks)
  goal: Goal | null;
  tasks: Task[];
  refresh: (projectId?: string | null, chatId?: string | null) => Promise<void>;
  // Project-scoped (kanban tab — all goals/tasks across the project)
  kanban: KanbanData | null;
  refreshKanban: (projectId?: string | null) => Promise<void>;
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

    if (!pid || !cid) {
      setGoal(null);
      setTasks([]);
      return;
    }
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
    if (!pid) {
      setKanban(null);
      return;
    }
    try {
      const res = await fetch(`${getApiBase()}/project/kanban?project_id=${pid}`);
      if (res.ok) setKanban(await res.json());
    } catch (err) {
      console.warn('Failed to fetch project kanban:', err);
    }
  }, []);

  const contextValue = React.useMemo(
    () => ({ goal, tasks, refresh, kanban, refreshKanban }),
    [goal, tasks, refresh, kanban, refreshKanban],
  );

  return React.createElement(GoalTasksContext.Provider, { value: contextValue }, children);
};

export function useGoalTasks() {
  const ctx = useContext(GoalTasksContext);
  if (!ctx) throw new Error('useGoalTasks must be used within GoalTasksProvider');
  return ctx;
}
