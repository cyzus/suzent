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
  chatError: boolean;
  chatLoading: boolean;
  kanbanError: boolean;
  kanbanLoading: boolean;
  refresh: (projectId?: string | null, chatId?: string | null) => Promise<void>;
  goalAction: (action: 'pause' | 'resume' | 'clear') => Promise<void>;
  // Project-scoped task list
  kanban: KanbanData | null;
  refreshKanban: (projectId?: string | null) => Promise<void>;
}

const GoalTasksContext = createContext<GoalTasksContextValue | null>(null);

export const GoalTasksProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState(false);
  const [kanbanLoading, setKanbanLoading] = useState(false);
  const [kanbanError, setKanbanError] = useState(false);
  const chatRequest = useRef(0);
  const boardRequest = useRef(0);
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
    const sequence = ++chatRequest.current;
    const changed =
      (projectId !== undefined && projectId !== currentProjectIdRef.current) ||
      (chatId !== undefined && chatId !== currentChatIdRef.current);
    if (projectId !== undefined) currentProjectIdRef.current = projectId ?? null;
    if (chatId !== undefined) currentChatIdRef.current = chatId ?? null;
    const pid = currentProjectIdRef.current;
    const cid = currentChatIdRef.current;
    setChatError(false);
    if (changed || !pid || !cid) {
      setGoal(null);
      setTasks([]);
      setGoalChatId(null);
    }
    if (!pid || !cid) {
      setChatLoading(false);
      return;
    }
    setChatLoading(true);
    try {
      const query = new URLSearchParams({
        project_id: pid,
        chat_id: cid,
        include_completed: 'true',
        include_cancelled: 'true',
      });
      const signal = AbortSignal.timeout(15000);
      const [goalRes, tasksRes] = await Promise.all([
        fetch(`${getApiBase()}/project/goal?${query}`, { signal }),
        fetch(`${getApiBase()}/project/tasks?${query}`, { signal }),
      ]);
      if (!goalRes.ok || !tasksRes.ok) throw new Error('Task fetch failed');
      const [nextGoal, nextTasks] = await Promise.all([goalRes.json(), tasksRes.json()]);
      if (sequence !== chatRequest.current) return;
      setGoal(nextGoal);
      setTasks(nextTasks);
      setGoalChatId(cid);
    } catch {
      if (sequence === chatRequest.current) setChatError(true);
    } finally {
      if (sequence === chatRequest.current) setChatLoading(false);
    }
  }, []);

  const goalAction = useCallback(async (action: 'pause' | 'resume' | 'clear') => {
    const pid = currentProjectIdRef.current;
    const cid = currentChatIdRef.current;
    if (!pid || !cid) throw new Error('No active conversation');
    const res = await fetch(`${getApiBase()}/project/goal/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: pid, chat_id: cid, action }),
    });
    if (!res.ok) throw new Error('Goal action failed');
    const updated = await res.json();
    if (pid === currentProjectIdRef.current && cid === currentChatIdRef.current) {
      setGoal(updated && updated.id ? updated : null);
    }
  }, []);

  const refreshKanban = useCallback(async (projectId?: string | null) => {
    const sequence = ++boardRequest.current;
    if (projectId !== undefined && projectId !== currentKanbanProjectIdRef.current) setKanban(null);
    if (projectId !== undefined) currentKanbanProjectIdRef.current = projectId ?? null;
    const pid = currentKanbanProjectIdRef.current;
    setKanbanError(false);
    if (!pid) {
      setKanban({ goals: [], tasks: [] });
      setKanbanLoading(false);
      return;
    }
    setKanbanLoading(true);
    try {
      const res = await fetch(
        `${getApiBase()}/project/kanban?${new URLSearchParams({ project_id: pid })}`,
        { signal: AbortSignal.timeout(15000) }
      );
      if (!res.ok) throw new Error('Project task fetch failed');
      const data = await res.json();
      if (sequence === boardRequest.current) setKanban(data);
    } catch {
      if (sequence === boardRequest.current) setKanbanError(true);
    } finally {
      if (sequence === boardRequest.current) setKanbanLoading(false);
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

  const contextValue = React.useMemo(
    () => ({
      goal,
      tasks,
      goalChatId,
      chatError,
      chatLoading,
      kanbanError,
      kanbanLoading,
      refresh,
      goalAction,
      kanban,
      refreshKanban,
    }),
    [
      goal,
      tasks,
      goalChatId,
      chatError,
      chatLoading,
      kanbanError,
      kanbanLoading,
      refresh,
      goalAction,
      kanban,
      refreshKanban,
    ]
  );

  return React.createElement(GoalTasksContext.Provider, { value: contextValue }, children);
};

export function useGoalTasks() {
  const ctx = useContext(GoalTasksContext);
  if (!ctx) throw new Error('useGoalTasks must be used within GoalTasksProvider');
  return ctx;
}
