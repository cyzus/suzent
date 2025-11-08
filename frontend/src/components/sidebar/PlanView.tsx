import React from 'react';
import type { Plan } from '../../types/api';

interface PlanViewProps {
  plan: Plan | null;
  currentPlan: Plan | null;
  snapshotPlan: Plan | null;
  plans: Plan[];
  selectedPlanKey: string | null;
  onSelectPlan: (planKey: string | null) => void;
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

export const PlanView: React.FC<PlanViewProps> = ({ plan, currentPlan, snapshotPlan, plans, selectedPlanKey, onSelectPlan }) => {
  const [isNewPlan, setIsNewPlan] = React.useState(false);
  const prevPlanKeyRef = React.useRef<string | null>(null);

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

  // Detect when plan changes to trigger animations
  React.useEffect(() => {
    const currentKey = plan ? (plan.versionKey?.startsWith('snapshot:') ? plan.versionKey : getPlanKey(plan)) : null;
    if (currentKey && currentKey !== prevPlanKeyRef.current) {
      setIsNewPlan(true);
      const timer = setTimeout(() => setIsNewPlan(false), 600);
      prevPlanKeyRef.current = currentKey;
      return () => clearTimeout(timer);
    }
    prevPlanKeyRef.current = currentKey;
  }, [plan]);

  const handleSelectChange = React.useCallback((event: React.ChangeEvent<HTMLSelectElement>) => {
    const value = event.target.value;
    onSelectPlan(value || null);
  }, [onSelectPlan]);

  if (!plan) {
    if (!combinedPlans.length) {
      return <div className="text-xs text-brutal-black font-bold uppercase">No plan loaded.</div>;
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
        <h2 className="font-brutal text-sm tracking-tight text-brutal-black uppercase">Plan Overview</h2>
        <div className="flex items-center gap-2 flex-wrap justify-end w-full sm:w-auto">
          {combinedPlans.length > 1 && (
            <div className="relative w-full min-w-[8rem] sm:w-40">
              <select
                value={selectedPlanKey ?? ''}
                onChange={handleSelectChange}
                className="relative z-20 w-full text-xs border-3 border-brutal-black px-2 py-1.5 bg-brutal-white text-brutal-black font-bold uppercase hover:bg-neutral-100 focus:outline-none"
              >
                {combinedPlans.map(item => (
                  <option key={item.key} value={item.key}>{item.label}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {plan ? (
        <>
          <div className={`text-[10px] text-brutal-black font-bold uppercase space-y-0.5 ${isNewPlan ? 'animate-brutal-slide' : ''}`}>
            <div>{isSnapshot ? 'LIVE SNAPSHOT' : plan.id != null ? `PLAN #${plan.id}` : 'PLAN'}</div>
            {!isSnapshot && plan.versionKey && <div>· VERSION {plan.versionKey}</div>}
            {createdAtLabel && <div>· CREATED {createdAtLabel}</div>}
            {updatedAtLabel && <div>· UPDATED {updatedAtLabel}</div>}
          </div>
          <div className={`text-sm font-medium leading-snug text-brutal-black ${isNewPlan ? 'animate-brutal-drop' : ''}`}>
            {plan.objective}
          </div>
          <div className="w-full h-2 bg-neutral-200 border-2 border-brutal-black overflow-hidden relative">
            <div
              className="h-full bg-brutal-blue transition-all duration-300 linear will-change-[width]"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
          <div className={`text-[10px] text-brutal-black font-bold uppercase ${isNewPlan ? 'animate-brutal-slide' : ''}`}>
            {completed}/{totalTasks} tasks completed
          </div>
          <ul className="space-y-2 text-[11px]">
            {plan.tasks.map((task, index) => {
              const statusColors: Record<string, string> = {
                pending: 'bg-neutral-200',
                in_progress: 'bg-brutal-blue',
                completed: 'bg-brutal-green',
                failed: 'bg-brutal-red'
              };
              const animationDelay = isNewPlan ? `${index * 50}ms` : '0ms';
              const bgColor = statusColors[task.status] || 'bg-neutral-200';
              return (
                <li
                  key={task.id ?? `${getPlanKey(plan)}-${task.number}`}
                  className={`${bgColor} border-3 border-brutal-black p-2.5 ${isNewPlan ? 'animate-brutal-drop' : ''}`}
                  style={{ animationDelay }}
                >
                  <div className="flex justify-between items-start gap-2">
                    <span className="font-medium text-brutal-black flex-1 text-sm leading-snug">{task.number}. {task.description}</span>
                    <span className={`shrink-0 text-[9px] font-bold text-brutal-black px-1.5 py-0.5 bg-brutal-black/10 border border-brutal-black ${task.status === 'in_progress' ? 'animate-brutal-blink' : ''}`}>
                      {task.status.toUpperCase()}
                    </span>
                  </div>
                  {task.note && <div className="mt-2 text-brutal-black text-xs font-medium italic opacity-70 border-l-2 border-brutal-black pl-2">{task.note}</div>}
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        <div className="text-xs text-brutal-black font-bold uppercase">Select a version to view details.</div>
      )}

      {otherPlans.length > 0 && (
        <div className="border-t-3 border-brutal-black pt-3 mt-2">
          <div className="text-[10px] font-bold uppercase tracking-wide text-brutal-black mb-2">Other Versions</div>
          <ul className="space-y-1.5 text-[11px]">
            {otherPlans.map((item, idx) => {
              const label = item.label;
              const otherPlan = item.plan;
              const otherCompleted = otherPlan.tasks.filter(task => task.status === 'completed').length;
              const summarySource = otherPlan.title ?? otherPlan.objective;
              const objectiveLines = summarySource.split(/\r?\n/).filter(Boolean);
              return (
                <li
                  key={item.key}
                  className="flex items-center justify-between gap-3 border-3 border-brutal-black bg-brutal-white px-2.5 py-2"
                >
                  <div className="flex-1 min-w-0">
                    <div className="font-bold text-brutal-black truncate text-[11px]">{label}</div>
                    <div className="text-xs text-brutal-black mt-0.5">
                      {objectiveLines.length ? objectiveLines.map((line, idx) => (
                        <span key={idx} className="block truncate">{line}</span>
                      )) : <span className="block truncate">No objective text</span>}
                    </div>
                  </div>
                  <div className="text-xs text-brutal-black font-bold whitespace-nowrap mr-2">{otherCompleted}/{otherPlan.tasks.length}</div>
                  <button
                    onClick={() => onSelectPlan(item.key)}
                    className="text-[11px] bg-brutal-yellow border-2 border-brutal-black px-2 py-1 font-bold uppercase text-brutal-black"
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
