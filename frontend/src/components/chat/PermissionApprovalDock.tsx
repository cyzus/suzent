import React from 'react';
import { useI18n } from '../../i18n';
import type {
  AGUIPart,
  ApprovalRememberScope,
  PermissionAction,
} from '../../types/agui';

interface PermissionApprovalDockProps {
  parts: AGUIPart[];
  onDecision: (
    approvalId: string,
    toolCallId: string,
    approved: boolean,
    remember?: ApprovalRememberScope,
    toolName?: string,
    actionId?: string,
    feedback?: string,
  ) => void;
}

interface PendingApproval {
  approvalId: string;
  toolCallId: string;
  toolName: string;
  args: Record<string, unknown>;
  actions: PermissionAction[];
  reason?: string;
  risk?: string;
}

function parseArgs(raw: string | undefined): Record<string, unknown> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {};
  } catch {
    return { input: raw };
  }
}

export function getPendingApprovals(parts: AGUIPart[]): PendingApproval[] {
  return parts.flatMap(part => {
    if (
      part.type !== 'tool'
      || part.state !== 'approval-requested'
      || !part.approvalId
      || !part.toolCallId
      || !part.permission
    ) {
      return [];
    }
    return [{
      approvalId: part.approvalId,
      toolCallId: part.toolCallId,
      toolName: part.toolName || 'unknown',
      args: parseArgs(part.args),
      actions: part.permission.actions || [],
      reason: part.permission.reason,
      risk: part.permission.risk,
    }];
  });
}

function getActionDisplayOrder(actions: PermissionAction[]): PermissionAction[] {
  const once = actions.filter(
    action => action.behavior === 'allow' && action.scope === 'once',
  );
  const persistent = actions.filter(
    action => action.behavior === 'allow' && action.scope !== 'once',
  );
  const deny = actions.filter(action => action.behavior === 'deny');
  return [...once, ...persistent, ...deny];
}

const ApprovalCard: React.FC<{
  approval: PendingApproval;
  onDecision: PermissionApprovalDockProps['onDecision'];
  keyboardActive: boolean;
}> = ({ approval, onDecision, keyboardActive }) => {
  const { t } = useI18n();
  const [feedback, setFeedback] = React.useState('');
  const displayName = approval.toolName.replace(/_/g, ' ');
  const description = typeof approval.args.description === 'string'
    ? approval.args.description.trim()
    : '';
  const promptAction = description
    ? `${description.charAt(0).toLowerCase()}${description.slice(1)}`
    : t('permissionDock.useTool', { tool: displayName });
  const command = typeof approval.args.content === 'string'
    ? approval.args.content
    : typeof approval.args.command === 'string'
      ? approval.args.command
      : '';
  const filePath = typeof approval.args.file_path === 'string'
    ? approval.args.file_path
    : typeof approval.args.path === 'string'
      ? approval.args.path
      : '';
  const detail = command || filePath || JSON.stringify(approval.args, null, 2);
  const orderedActions = React.useMemo(
    () => getActionDisplayOrder(approval.actions),
    [approval.actions],
  );

  const submitAction = React.useCallback((
    action: PermissionAction,
    actionFeedback?: string,
  ) => {
    onDecision(
      approval.approvalId,
      approval.toolCallId,
      action.behavior === 'allow',
      action.scope === 'session' || action.scope === 'global'
        ? action.scope
        : null,
      approval.toolName,
      action.id,
      action.behavior === 'deny'
        ? actionFeedback?.trim() || undefined
        : undefined,
    );
  }, [approval, onDecision]);

  const selectAction = React.useCallback((action: PermissionAction) => {
    submitAction(action);
  }, [submitAction]);

  const allowActions = React.useMemo(
    () => orderedActions.filter(action => action.behavior === 'allow'),
    [orderedActions],
  );
  const rejectAction = orderedActions.find(action => action.behavior === 'deny');
  React.useEffect(() => {
    if (!keyboardActive) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isTyping = target?.tagName === 'INPUT'
        || target?.tagName === 'TEXTAREA'
        || target?.isContentEditable;
      if (isTyping) return;

      if (event.ctrlKey && event.key === 'Enter') {
        const allowOnce = allowActions.find(
          action => action.behavior === 'allow' && action.scope === 'once',
        );
        if (allowOnce) {
          event.preventDefault();
          selectAction(allowOnce);
        }
        return;
      }

      if (event.ctrlKey || event.altKey || event.metaKey) return;

      const index = Number(event.key) - 1;
      if (Number.isInteger(index) && allowActions[index]) {
        event.preventDefault();
        selectAction(allowActions[index]);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [allowActions, keyboardActive, selectAction]);

  const shortcutFor = (action: PermissionAction) =>
    allowActions.findIndex(candidate => candidate.id === action.id) + 1;

  const allowLabel = (action: PermissionAction): string => {
    if (action.scope === 'once') return t('permissionDock.yes');
    const actionText = `${action.label.charAt(0).toLowerCase()}${action.label.slice(1)}`;
    return t('permissionDock.yesAnd', { action: actionText });
  };

  return (
    <section className="mx-auto w-full max-w-5xl animate-brutal-drop overflow-hidden border-2 border-brutal-black bg-white font-mono text-brutal-black shadow-[3px_3px_0_0_#000] dark:border-neutral-500 dark:bg-zinc-900 dark:text-white dark:shadow-[3px_3px_0_0_rgba(255,255,255,0.14)]">
      <div className="flex items-start gap-2 px-3 pt-3">
        <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full border border-brutal-black bg-brutal-yellow dark:border-neutral-300" />
        <div className="text-[12px] font-bold leading-5">
          {t('permissionDock.title', {
            action: promptAction,
          })}
        </div>
      </div>

      {detail && (
        <pre
          title={detail}
          className="mx-3 mt-2 max-h-20 overflow-auto whitespace-pre-wrap break-words border border-neutral-300 bg-neutral-100 px-2.5 py-1.5 font-mono text-[11px] leading-4 text-neutral-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-neutral-300"
        >
          {detail}
        </pre>
      )}

      {approval.reason && (
        <div className="mx-3 mt-2 flex min-w-0 items-center gap-2 text-[9px] text-neutral-500 dark:text-neutral-400">
          {approval.risk && (
            <span className="shrink-0 border border-brutal-black bg-brutal-yellow px-1.5 py-px text-[8px] font-bold uppercase tracking-wider text-brutal-black dark:border-neutral-500">
              {approval.risk}
            </span>
          )}
          <span className="truncate" title={approval.reason}>{approval.reason}</span>
        </div>
      )}

      <div className="mx-3 mt-2 overflow-hidden border border-neutral-300 dark:border-zinc-700">
        {allowActions.map(action => (
          <button
            key={action.id}
            type="button"
            onClick={() => selectAction(action)}
            className="group flex min-h-9 w-full items-center gap-2 border-b border-neutral-200 px-2 text-left text-[10px] font-bold transition-colors last:border-b-0 hover:bg-brutal-yellow hover:text-brutal-black dark:border-zinc-700 dark:hover:bg-brutal-yellow dark:hover:text-brutal-black"
          >
            <span className="flex h-5 w-5 shrink-0 items-center justify-center border border-brutal-black bg-white text-[9px] font-bold text-brutal-black shadow-[1px_1px_0_0_#000] dark:border-neutral-500 dark:bg-zinc-800 dark:text-white group-hover:bg-white group-hover:text-brutal-black">
              {shortcutFor(action)}
            </span>
            <span className="min-w-0 flex-1 truncate">
              {allowLabel(action)}
            </span>
            {action.scope === 'once' && (
              <span className="shrink-0 text-[8px] font-normal uppercase tracking-wide text-neutral-400 group-hover:text-brutal-black/60 dark:text-neutral-500">
                {t('permissionDock.ctrlEnter')}
              </span>
            )}
          </button>
        ))}
      </div>

      {rejectAction && (
        <div className="mt-3 flex min-w-0 items-center gap-1.5 border-t-2 border-brutal-black bg-neutral-50 px-3 py-2 dark:border-neutral-500 dark:bg-zinc-950/40">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center border border-brutal-black bg-white text-neutral-500 dark:border-neutral-500 dark:bg-zinc-800 dark:text-neutral-300">
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.862 4.487Z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 7.125 16.875 4.5" />
            </svg>
          </span>
          <input
            type="text"
            value={feedback}
            onChange={event => setFeedback(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter' && feedback.trim()) {
                event.preventDefault();
                submitAction(rejectAction, feedback);
              }
            }}
            placeholder={t('permissionDock.feedbackPlaceholder')}
            className="h-7 min-w-0 flex-1 border border-brutal-black bg-white px-2 text-[10px] text-brutal-black outline-none placeholder:text-neutral-400 focus:bg-brutal-yellow/10 dark:border-neutral-500 dark:bg-zinc-800 dark:text-white dark:placeholder:text-neutral-500"
          />
          <button
            type="button"
            onClick={() => submitAction(rejectAction)}
            className="h-7 shrink-0 border border-brutal-black bg-white px-2 text-[9px] font-bold uppercase tracking-wide text-brutal-black transition-colors hover:bg-brutal-red hover:text-white dark:border-neutral-500 dark:bg-zinc-800 dark:text-white dark:hover:bg-brutal-red"
          >
            {t('permissionDock.skip')}
          </button>
          <button
            type="button"
            disabled={!feedback.trim()}
            onClick={() => submitAction(rejectAction, feedback)}
            className="flex h-7 shrink-0 items-center gap-1 border-2 border-brutal-black bg-brutal-black px-2.5 text-[9px] font-bold uppercase tracking-wide text-white shadow-[2px_2px_0_0_#000] transition-all hover:bg-neutral-800 active:translate-x-[1px] active:translate-y-[1px] active:shadow-none disabled:cursor-not-allowed disabled:opacity-35 dark:border-neutral-300 dark:bg-neutral-200 dark:text-brutal-black dark:shadow-[2px_2px_0_0_rgba(255,255,255,0.18)] dark:hover:bg-white"
          >
            {t('permissionDock.submit')}
            <span className="text-[13px] opacity-60">↵</span>
          </button>
        </div>
      )}
    </section>
  );
};

export const PermissionApprovalDock: React.FC<PermissionApprovalDockProps> = ({
  parts,
  onDecision,
}) => {
  const approvals = React.useMemo(() => getPendingApprovals(parts), [parts]);
  if (approvals.length === 0) return null;

  return (
    <div className="max-h-[46vh] space-y-2 overflow-y-auto overflow-x-hidden pb-1 pr-1">
      {approvals.map((approval, index) => (
        <ApprovalCard
          key={approval.approvalId}
          approval={approval}
          onDecision={onDecision}
          keyboardActive={index === 0}
        />
      ))}
    </div>
  );
};
