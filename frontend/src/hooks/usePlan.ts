import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { Plan, PlanHistoryResponse, PlanTaskStatus } from '../types/api';

interface PlanContextValue {
  plan: Plan | null;
  currentPlan: Plan | null;
  snapshotPlan: Plan | null;
  history: Plan[];
  selectedVersion: string | null;
  selectVersion: (versionKey: string | null) => void;
  refresh: (chatId?: string | null) => Promise<void>;
  applySnapshot: (snapshot: Partial<Plan> & { objective?: string; tasks?: Array<Partial<Plan['tasks'][number]>> } | null) => void;
}

const PlanContext = createContext<PlanContextValue | null>(null);

export const PlanProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [planResponse, setPlanResponse] = useState<PlanHistoryResponse | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const [snapshotPlan, setSnapshotPlan] = useState<Plan | null>(null);

  const refresh = useCallback(async (chatId?: string | null) => {
    if (!chatId) {
      // No chat selected, clear plan state
      setPlanResponse(null);
      setSelectedVersion(null);
      setSnapshotPlan(null);
      return;
    }

    try {
      console.log(`Fetching plan for chat_id: ${chatId}`);
      const res = await fetch(`/api/plan?chat_id=${chatId}`);
      console.log(`Plan fetch response: ${res.status}`);
      if (res.ok) {
        const data: PlanHistoryResponse = await res.json();
        console.log('Plan data received:', data);
        setPlanResponse(data);
        if (data.current) {
          setSnapshotPlan(null);
        }
        const defaultVersion = data.current?.versionKey ?? data.history[0]?.versionKey ?? null;
        setSelectedVersion(defaultVersion);
      } else if (res.status === 400 || res.status === 404) {
        console.log('No plan found for this chat');
        setPlanResponse({ current: null, history: [] });
        setSelectedVersion(null);
        setSnapshotPlan(null);
      } else {
        console.warn(`Plan fetch failed with status ${res.status}`);
        setPlanResponse(null);
        setSelectedVersion(null);
      }
    } catch (error) {
      console.warn('Failed to fetch plan:', error);
      setPlanResponse(null);
      setSelectedVersion(null);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const history = planResponse?.history ?? [];
  const currentPlanFromResponse = planResponse?.current ?? null;

  const allCandidates = useMemo(() => {
    const entries: Plan[] = [];
    if (snapshotPlan) entries.push(snapshotPlan);
    if (currentPlanFromResponse) entries.push(currentPlanFromResponse);
    if (history.length) entries.push(...history);
    return entries;
  }, [snapshotPlan, currentPlanFromResponse, history]);

  const plan = useMemo(() => {
    if (!selectedVersion) {
      return snapshotPlan ?? currentPlanFromResponse ?? history[0] ?? null;
    }
    return allCandidates.find(candidate => candidate.versionKey === selectedVersion) ?? snapshotPlan ?? currentPlanFromResponse ?? history[0] ?? null;
  }, [selectedVersion, snapshotPlan, currentPlanFromResponse, history, allCandidates]);

  const currentPlan = currentPlanFromResponse ?? snapshotPlan;

  const applySnapshot = useCallback((snapshot: Partial<Plan> & { objective?: string; tasks?: Array<Partial<Plan['tasks'][number]>> } | null) => {
    if (!snapshot || (!snapshot.objective && !Array.isArray(snapshot.tasks))) {
      setSnapshotPlan(null);
      return;
    }

    const tasks = Array.isArray(snapshot.tasks) ? snapshot.tasks.map((task, index) => {
      const rawStatus = typeof task?.status === 'string' ? task.status : undefined;
      const validStatus: PlanTaskStatus = rawStatus === 'pending' || rawStatus === 'in_progress' || rawStatus === 'completed' || rawStatus === 'failed'
        ? rawStatus
        : 'pending';
      const number = typeof task?.number === 'number' ? task.number : index + 1;
      return {
        id: task?.id,
        number,
        description: String(task?.description ?? '').trim(),
        status: validStatus,
        note: task?.note ?? undefined,
        createdAt: task?.createdAt,
        updatedAt: task?.updatedAt,
      };
    }) : [];

    const versionKey = snapshot.versionKey ?? `snapshot:${Date.now()}`;
    const timestamp = snapshot.updatedAt ?? snapshot.createdAt ?? new Date().toISOString();
    setSnapshotPlan({
      id: snapshot.id,
      chatId: snapshot.chatId ?? null,
      objective: snapshot.objective ?? 'Plan',
      tasks,
      createdAt: snapshot.createdAt ?? timestamp,
      updatedAt: snapshot.updatedAt ?? timestamp,
      versionKey,
    });
    setSelectedVersion(prev => (prev === null || prev.startsWith('snapshot:')) ? versionKey : prev);
  }, []);

  const contextValue: PlanContextValue = useMemo(() => ({
    plan,
    currentPlan,
    snapshotPlan,
    history,
    selectedVersion,
    selectVersion: setSelectedVersion,
    refresh,
    applySnapshot,
  }), [plan, currentPlan, snapshotPlan, history, selectedVersion, refresh, applySnapshot]);

  return React.createElement(PlanContext.Provider, { value: contextValue }, children);
};

export function usePlan() {
  const ctx = useContext(PlanContext);
  if (!ctx) throw new Error('usePlan must be used within PlanProvider');
  return ctx;
}
