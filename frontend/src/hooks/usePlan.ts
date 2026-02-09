import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { Plan, PlanPhaseStatus } from '../types/api';
import { getApiBase } from '../lib/api';

const getPlanKey = (plan: Plan) => (plan.id != null ? `plan:${plan.id}` : plan.versionKey);

interface PlanContextValue {
  plan: Plan | null;
  plans: Plan[];
  currentPlan: Plan | null;
  snapshotPlan: Plan | null;
  selectedPlanKey: string | null;
  selectPlan: (planKey: string | null) => void;
  refresh: (chatId?: string | null) => Promise<void>;
  applySnapshot: (snapshot: Partial<Plan> & { objective?: string; phases?: Array<Partial<Plan['phases'][number]>> } | null) => void;
}

const PlanContext = createContext<PlanContextValue | null>(null);

export const PlanProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedPlanKey, setSelectedPlanKey] = useState<string | null>(null);
  const [snapshotPlan, setSnapshotPlan] = useState<Plan | null>(null);

  const refresh = useCallback(async (chatId?: string | null) => {
    if (!chatId) {
      setPlans([]);
      setSelectedPlanKey(null);
      setSnapshotPlan(null);
      return;
    }

    try {
      const res = await fetch(`${getApiBase()}/plans?chat_id=${chatId}`);
      if (res.ok) {
        const data: Plan[] = await res.json();
        setPlans(data);

        const snapshotMatchesPersisted = Boolean(
          snapshotPlan &&
          data.some(planEntry => {
            if (snapshotPlan.id != null && planEntry.id === snapshotPlan.id) return true;
            if (snapshotPlan.versionKey && snapshotPlan.versionKey === getPlanKey(planEntry)) return true;
            return false;
          }),
        );

        const effectiveSnapshot = snapshotMatchesPersisted ? null : snapshotPlan;
        if (snapshotMatchesPersisted) {
          setSnapshotPlan(null);
        }

        const availableKeys = new Set<string>();
        data.forEach(planEntry => availableKeys.add(getPlanKey(planEntry)));
        if (effectiveSnapshot?.versionKey) availableKeys.add(effectiveSnapshot.versionKey);

        setSelectedPlanKey(prev => {
          if (prev && availableKeys.has(prev)) return prev;
          if (effectiveSnapshot?.versionKey) return effectiveSnapshot.versionKey;
          const firstPlan = data[0];
          return firstPlan ? getPlanKey(firstPlan) : null;
        });
      } else if (res.status === 400 || res.status === 404) {
        setPlans([]);
        setSelectedPlanKey(null);
        setSnapshotPlan(null);
      } else {
        console.warn(`Plan fetch failed with status ${res.status}`);
        setPlans([]);
        setSelectedPlanKey(null);
      }
    } catch (error) {
      console.warn('Failed to fetch plan:', error);
      setPlans([]);
      setSelectedPlanKey(null);
    }
  }, [snapshotPlan]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const sortedPlans = useMemo(() => {
    return [...plans].sort((a, b) => {
      const aTime = new Date(a.updatedAt ?? a.createdAt ?? 0).getTime();
      const bTime = new Date(b.updatedAt ?? b.createdAt ?? 0).getTime();
      return bTime - aTime;
    });
  }, [plans]);

  const currentPlan = sortedPlans[0] ?? null;

  const plan = useMemo(() => {
    if (selectedPlanKey) {
      if (snapshotPlan && snapshotPlan.versionKey === selectedPlanKey) return snapshotPlan;
      const matched = sortedPlans.find(entry => getPlanKey(entry) === selectedPlanKey);
      if (matched) return matched;
    }
    if (snapshotPlan) return snapshotPlan;
    return currentPlan ?? null;
  }, [selectedPlanKey, snapshotPlan, sortedPlans, currentPlan]);

  const applySnapshot = useCallback(
    (snapshot: Partial<Plan> & { objective?: string; phases?: Array<Partial<Plan['phases'][number]>> } | null) => {
      if (!snapshot || (!snapshot.objective && !Array.isArray(snapshot.phases))) {
        setSnapshotPlan(null);
        return;
      }

      const phases = Array.isArray(snapshot.phases)
        ? snapshot.phases.map((phase, index) => {
          const rawStatus = typeof phase?.status === 'string' ? phase.status : undefined;
          const validStatus: PlanPhaseStatus =
            rawStatus === 'pending' || rawStatus === 'in_progress' || rawStatus === 'completed'
              ? rawStatus
              : 'pending';
          const number = typeof phase?.number === 'number' ? phase.number : index + 1;
          return {
            id: phase?.id,
            number,
            title: String(phase?.title ?? phase?.description ?? '').trim(),
            description: String(phase?.description ?? '').trim(),
            status: validStatus,
            note: phase?.note ?? undefined,
            capabilities: phase?.capabilities,
            createdAt: phase?.createdAt,
            updatedAt: phase?.updatedAt,
          };
        })
        : [];

      const versionKey = snapshot.versionKey ?? `snapshot:${Date.now()}`;
      const timestamp = snapshot.updatedAt ?? snapshot.createdAt ?? new Date().toISOString();
      setSnapshotPlan({
        id: snapshot.id,
        chatId: snapshot.chatId ?? null,
        objective: snapshot.objective ?? 'Plan',
        phases,
        createdAt: snapshot.createdAt ?? timestamp,
        updatedAt: snapshot.updatedAt ?? timestamp,
        versionKey,
      });
      // Automatically switch to the new snapshot
      setSelectedPlanKey(versionKey);
    },
    [],
  );

  const contextValue: PlanContextValue = useMemo(
    () => ({
      plan,
      plans: sortedPlans,
      currentPlan,
      snapshotPlan,
      selectedPlanKey,
      selectPlan: setSelectedPlanKey,
      refresh,
      applySnapshot,
    }),
    [plan, sortedPlans, currentPlan, snapshotPlan, selectedPlanKey, refresh, applySnapshot],
  );

  return React.createElement(PlanContext.Provider, { value: contextValue }, children);
};

export function usePlan() {
  const ctx = useContext(PlanContext);
  if (!ctx) throw new Error('usePlan must be used within PlanProvider');
  return ctx;
}
