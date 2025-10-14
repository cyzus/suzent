import React from 'react';
import type { Plan } from '../../types/api';

interface PlanViewProps {
  plan: Plan | null;
  currentPlan: Plan | null;
  snapshotPlan: Plan | null;
  plans: Plan[];
  selectedPlanKey: string | null;
  onSelectPlan: (planKey: string | null) => void;
  onRefresh: () => void;
}

const getPlanKey = (plan: Plan) => (plan.id != null ? `plan:${plan.id}` : plan.versionKey);
const describePlan = (plan: Plan) => {
  const candidate = plan.title ?? plan.objective;
  const trimmed = typeof candidate === 'string' ? candidate.trim() : '';
  return trimmed.length ? trimmed : 'Untitled plan';
};

const formatTimestamp = (input?: string | null) => {
  if (!input) return '';
  const date = new Date(input);
  if (Number.isNaN(date.getTime())) return input;
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
};

export const PlanView: React.FC<PlanViewProps> = ({ plan, currentPlan, snapshotPlan, plans, selectedPlanKey, onSelectPlan, onRefresh }) => {
  const combinedPlans = React.useMemo(() => {
    const items: Array<{ label: string; plan: Plan; key: string; kind: 'snapshot' | 'current' | 'history' }> = [];
    const seenKeys = new Set<string>();
    if (snapshotPlan) {
      const key = snapshotPlan.versionKey;
      const timestamp = formatTimestamp(snapshotPlan.updatedAt || snapshotPlan.createdAt);
      items.push({
        label: `Live Snapshot • ${describePlan(snapshotPlan)}${timestamp ? ` • ${timestamp}` : ''}`,
        key,
        plan: snapshotPlan,
        kind: 'snapshot',
      });
      seenKeys.add(key);
    }
    if (currentPlan) {
      const key = getPlanKey(currentPlan);
      if (!seenKeys.has(key)) {
      const timestamp = formatTimestamp(currentPlan.updatedAt || currentPlan.createdAt);
      items.push({
        label: `Current • ${describePlan(currentPlan)}${timestamp ? ` • ${timestamp}` : ''}`,
        key,
        plan: currentPlan,
        kind: 'current',
      });
      seenKeys.add(key);
      }
    }
    plans.forEach((entry: Plan, index: number) => {
      const key = getPlanKey(entry);
      if (!seenKeys.has(key)) {
        const timestamp = formatTimestamp(entry.updatedAt || entry.createdAt);
        items.push({
          label: `Plan ${entry.id ?? index + 1} • ${describePlan(entry)}${timestamp ? ` • ${timestamp}` : ''}`,
          key,
          plan: entry,
          kind: 'history',
        });
        seenKeys.add(key);
      }
    });
    return items;
  }, [snapshotPlan, currentPlan, plans]);

  const handleSelectChange = React.useCallback((event: React.ChangeEvent<HTMLSelectElement>) => {
    const value = event.target.value;
    onSelectPlan(value || null);
  }, [onSelectPlan]);

  if (!plan) {
    if (!combinedPlans.length) {
      return <div className="text-xs text-neutral-500">No plan loaded.</div>;
    }
  }

  const completed = plan ? plan.tasks.filter(task => task.status === 'completed').length : 0;
  const totalTasks = plan?.tasks.length ?? 0;
  const progress = totalTasks ? completed / totalTasks : 0;
  const isSnapshot = !!plan?.versionKey && plan.versionKey.startsWith('snapshot:');
  const createdAtLabel = formatTimestamp(plan?.createdAt);
  const updatedAtLabel = formatTimestamp(plan?.updatedAt);
  const activeKey = plan ? (isSnapshot ? plan.versionKey : getPlanKey(plan)) : null;
  const otherPlans = activeKey ? combinedPlans.filter(entry => entry.key !== activeKey) : combinedPlans;

  return (
    <div className="space-y-4 relative z-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-medium text-sm tracking-wide text-neutral-700">Plan Overview</h2>
        <div className="flex items-center gap-2 flex-wrap justify-end w-full sm:w-auto">
          {combinedPlans.length > 1 && (
            <div className="relative w-full min-w-[8rem] sm:w-40">
              <select
                value={selectedPlanKey ?? ''}
                onChange={handleSelectChange}
                className="relative z-20 w-full text-[11px] border border-neutral-200 rounded px-2 py-1 bg-white text-neutral-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-200"
              >
                {combinedPlans.map(item => (
                  <option key={item.key} value={item.key}>{item.label}</option>
                ))}
              </select>
            </div>
          )}
          <button
            onClick={onRefresh}
            className="shrink-0 px-2 py-1 text-[11px] text-brand-600 hover:text-brand-500 transition-colors mt-1 sm:mt-0"
          >
            Refresh
          </button>
        </div>
      </div>

      {plan ? (
        <>
          <div className="text-xs text-neutral-500 space-y-0.5">
            <div>{isSnapshot ? 'Live Snapshot' : plan.id != null ? `Plan #${plan.id}` : 'Plan'}</div>
            {!isSnapshot && plan.versionKey && <div>· Version {plan.versionKey}</div>}
            {createdAtLabel && <div>· Created {createdAtLabel}</div>}
            {updatedAtLabel && <div>· Updated {updatedAtLabel}</div>}
          </div>
          <div className="text-sm font-semibold leading-snug text-neutral-900">{plan.objective}</div>
          <div className="w-full h-2 rounded bg-neutral-200 overflow-hidden relative">
            <div
              className="h-2 bg-gradient-to-r from-brand-600 to-brand-400 transition-[width] duration-500 ease-out will-change-[width]"
              style={{ width: `${progress * 100}%` }}
            />
            <div className="absolute inset-0 pointer-events-none bg-[linear-gradient(120deg,rgba(255,255,255,0)_0%,rgba(255,255,255,.4)_50%,rgba(255,255,255,0)_100%)] bg-[length:200%_100%] animate-[shimmer_2.5s_linear_infinite]" />
          </div>
          <div className="text-[11px] text-neutral-500">{completed}/{totalTasks} tasks completed</div>
          <ul className="space-y-2 text-[11px]">
            {plan.tasks.map(task => {
              const statusIcons: Record<string, string> = { pending: '⚪', in_progress: '🔵', completed: '🟢', failed: '🔴' };
              return (
                <li key={task.id ?? `${getPlanKey(plan)}-${task.number}`} className="bg-white/70 rounded border border-neutral-200 p-2.5">
                  <div className="flex justify-between items-start gap-2">
                    <span className="font-medium text-neutral-800 flex-1">{task.number}. {task.description}</span>
                    <span className="shrink-0 text-xs">{statusIcons[task.status] || '❓'}</span>
                  </div>
                  {task.note && <div className="mt-1 italic text-neutral-500">{task.note}</div>}
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        <div className="text-xs text-neutral-500">Select a version to view details.</div>
      )}

      {otherPlans.length > 0 && (
        <div className="border-t border-neutral-200 pt-3">
          <div className="text-[11px] font-medium uppercase tracking-wide text-neutral-500 mb-2">Other Versions</div>
          <ul className="space-y-1.5 text-[11px]">
            {otherPlans.map(item => {
              const label = item.label;
              const otherPlan = item.plan;
              const otherCompleted = otherPlan.tasks.filter(task => task.status === 'completed').length;
              const summarySource = otherPlan.title ?? otherPlan.objective;
              const objectiveLines = summarySource.split(/\r?\n/).filter(Boolean);
              return (
                <li key={item.key} className="flex items-center justify-between gap-3 rounded border border-neutral-200 bg-white/70 px-2.5 py-1.5">
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-neutral-700 truncate">{label}</div>
                    <div className="text-[10px] text-neutral-500">
                      {objectiveLines.length ? objectiveLines.map((line, idx) => (
                        <span key={idx} className="block truncate">{line}</span>
                      )) : <span className="block truncate">No objective text</span>}
                    </div>
                  </div>
                  <div className="text-[10px] text-neutral-500 whitespace-nowrap mr-2">{otherCompleted}/{otherPlan.tasks.length} tasks</div>
                  <button
                    onClick={() => onSelectPlan(item.key)}
                    className="text-[10px] text-brand-600 hover:text-brand-500 transition-colors"
                  >
                    View
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
};
