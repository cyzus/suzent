import React from 'react';
import type { Plan } from '../../types/api';

interface PlanViewProps {
  plan: Plan | null;
  currentPlan: Plan | null;
  snapshotPlan: Plan | null;
  history: Plan[];
  selectedVersion: string | null;
  onSelectVersion: (versionKey: string | null) => void;
  onRefresh: () => void;
}

const formatTimestamp = (input?: string | null) => {
  if (!input) return '';
  const date = new Date(input);
  if (Number.isNaN(date.getTime())) return input;
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
};

export const PlanView: React.FC<PlanViewProps> = ({ plan, currentPlan, snapshotPlan, history, selectedVersion, onSelectVersion, onRefresh }) => {
  const combinedPlans = React.useMemo(() => {
    const items: Array<{ label: string; plan: Plan; kind: 'snapshot' | 'current' | 'history' }> = [];
    const seenKeys = new Set<string>();
    if (snapshotPlan) {
      items.push({
        label: `Live Snapshot • ${formatTimestamp(snapshotPlan.updatedAt || snapshotPlan.createdAt)}`,
        plan: snapshotPlan,
        kind: 'snapshot',
      });
      seenKeys.add(snapshotPlan.versionKey);
    }
    if (currentPlan) {
      if (!seenKeys.has(currentPlan.versionKey)) {
        items.push({
          label: `Current • ${formatTimestamp(currentPlan.updatedAt || currentPlan.createdAt)}`,
          plan: currentPlan,
          kind: 'current',
        });
        seenKeys.add(currentPlan.versionKey);
      }
    }
    history.forEach((entry, index) => {
      if (!seenKeys.has(entry.versionKey)) {
        items.push({
          label: `History #${index + 1} • ${formatTimestamp(entry.updatedAt || entry.createdAt)}`,
          plan: entry,
          kind: 'history',
        });
        seenKeys.add(entry.versionKey);
      }
    });
    return items;
  }, [snapshotPlan, currentPlan, history]);

  const handleSelectChange = React.useCallback((event: React.ChangeEvent<HTMLSelectElement>) => {
    const value = event.target.value;
    onSelectVersion(value || null);
  }, [onSelectVersion]);

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
  const otherPlans = plan ? combinedPlans.filter(entry => entry.plan.versionKey !== plan.versionKey) : combinedPlans;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-medium text-sm tracking-wide text-neutral-700">Plan Overview</h2>
        <div className="flex items-center gap-2">
          {combinedPlans.length > 1 && (
            <select
              value={selectedVersion ?? ''}
              onChange={handleSelectChange}
              className="text-[11px] border border-neutral-200 rounded px-2 py-1 bg-white text-neutral-700"
            >
              {combinedPlans.map(item => (
                <option key={item.plan.versionKey} value={item.plan.versionKey}>{item.label}</option>
              ))}
            </select>
          )}
          <button onClick={onRefresh} className="text-[11px] text-brand-600 hover:text-brand-500 transition-colors">Refresh</button>
        </div>
      </div>

      {plan ? (
        <>
          <div className="text-xs text-neutral-500">
            {isSnapshot ? 'Live Snapshot' : `Version ${plan.versionKey}`}
            {createdAtLabel ? ` • Created ${createdAtLabel}` : ''}
            {updatedAtLabel ? ` • Updated ${updatedAtLabel}` : ''}
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
                <li key={task.id ?? `${plan.versionKey}-${task.number}`} className="bg-white/70 rounded border border-neutral-200 p-2.5">
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
              const objectiveLines = otherPlan.objective.split(/\r?\n/).filter(Boolean);
              return (
                <li key={otherPlan.versionKey} className="flex items-center justify-between gap-3 rounded border border-neutral-200 bg-white/70 px-2.5 py-1.5">
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
                    onClick={() => onSelectVersion(otherPlan.versionKey)}
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
