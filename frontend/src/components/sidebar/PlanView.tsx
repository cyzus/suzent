import React from 'react';
import type { Plan } from '../../types/api';

interface PlanViewProps {
  plan: Plan | null;
  currentPlan: Plan | null;
  snapshotPlan: Plan | null;
  plans: Plan[];
  selectedPlanKey: string | null;
  onSelectPlan: (planKey: string | null) => void;
  onRefresh?: () => void;
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

  // Single plan enforcement: ignore version history
  const combinedPlans = React.useMemo(() => [], []);

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


  const completed = plan ? plan.phases.filter(phase => phase.status === 'completed').length : 0;
  const totalPhases = plan?.phases.length ?? 0;
  const progress = totalPhases ? completed / totalPhases : 0;
  const isSnapshot = !!plan?.versionKey && plan.versionKey.startsWith('snapshot:');
  const createdAtLabel = formatTimestamp(plan?.createdAt);
  const updatedAtLabel = formatTimestamp(plan?.updatedAt);
  const activeKey = plan ? (isSnapshot ? plan.versionKey : getPlanKey(plan)) : null;

  return (
    <div className="space-y-4 relative z-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-brutal text-sm tracking-tight text-brutal-black uppercase">Plan Overview</h2>
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
          <div className="w-full h-3 bg-white border-3 border-brutal-black overflow-hidden relative shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
            <div
              className="h-full bg-brutal-blue transition-all duration-300 linear will-change-[width]"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
          <div className={`text-[10px] text-brutal-black font-bold uppercase ${isNewPlan ? 'animate-brutal-slide' : ''}`}>
            {completed}/{totalPhases} phases completed
          </div>
          <ul className="space-y-3 text-[11px]">
            {plan.phases.map((phase, index) => {
              const statusColors: Record<string, string> = {
                pending: 'bg-white',
                in_progress: 'bg-brutal-blue text-white',
                completed: 'bg-brutal-green',
              };
              const animationDelay = isNewPlan ? `${index * 50}ms` : '0ms';
              const bgColor = statusColors[phase.status] || 'bg-white';
              const textColor = (phase.status === 'in_progress') ? 'text-white' : 'text-brutal-black';

              return (
                <li
                  key={phase.id ?? `${getPlanKey(plan)}-${phase.number}`}
                  className={`${bgColor} border-3 border-brutal-black p-2.5 shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] transition-transform hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] ${isNewPlan ? 'animate-brutal-drop' : ''}`}
                  style={{ animationDelay }}
                >
                  <div className="flex justify-between items-start gap-2">
                    <div className={`font-bold ${textColor} flex-1 text-sm leading-snug`}>
                      {phase.number}. {phase.title || phase.description}
                      {phase.capabilities && (
                        <div className="flex gap-1 mt-1 flex-wrap">
                          {Array.isArray(phase.capabilities)
                            ? phase.capabilities.map((cap, idx) => (
                              <span key={idx} className="text-[9px] px-1 bg-black/10 rounded">{String(cap)}</span>
                            ))
                            : Object.keys(phase.capabilities).map(cap => (
                              <span key={cap} className="text-[9px] px-1 bg-black/10 rounded">{cap}</span>
                            ))
                          }
                        </div>
                      )}
                    </div>
                    <span className={`shrink-0 text-[9px] font-bold border-2 border-brutal-black px-1.5 py-0.5 bg-white text-brutal-black ${phase.status === 'in_progress' ? 'animate-pulse' : ''}`}>
                      {phase.status.toUpperCase()}
                    </span>
                  </div>
                  {phase.note && <div className={`mt-2 ${textColor} text-xs font-medium italic opacity-80 border-l-2 ${phase.status === 'in_progress' ? 'border-white' : 'border-brutal-black'} pl-2`}>{phase.note}</div>}
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        <div className="text-xs text-brutal-black font-bold uppercase">No plan loaded.</div>
      )}

    </div>
  );
};
