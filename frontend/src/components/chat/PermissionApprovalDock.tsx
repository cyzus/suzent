import React from 'react';
import { ShieldCheckIcon } from '@heroicons/react/24/outline';
import { BrutalSelect } from '../BrutalSelect';
import { useI18n } from '../../i18n';
import type { AGUIPart, ApprovalRememberScope, PermissionAction } from '../../types/agui';
import { isImeComposing } from '../../lib/ime';
import { normalizeToolName } from './toolSummary';

interface PermissionApprovalDockProps {
  parts: AGUIPart[];
  onDecision: (
    approvalId: string,
    toolCallId: string,
    approved: boolean,
    remember?: ApprovalRememberScope,
    toolName?: string,
    actionId?: string,
    feedback?: string
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
  source?: string;
  confidence?: 'low' | 'medium' | 'high' | number | null;
  reviewerModel?: string | null;
  riskCategories: string[];
}

function parseArgs(raw: string | undefined): Record<string, unknown> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return { input: raw };
  }
}

export function getPendingApprovals(parts: AGUIPart[]): PendingApproval[] {
  return parts.flatMap((part) => {
    if (
      part.type !== 'tool' ||
      part.state !== 'approval-requested' ||
      !part.approvalId ||
      !part.toolCallId ||
      !part.permission
    ) {
      return [];
    }
    return [
      {
        approvalId: part.approvalId,
        toolCallId: part.toolCallId,
        toolName: part.toolName || 'unknown',
        args: parseArgs(part.args),
        actions: part.permission.actions || [],
        reason: part.permission.reason,
        risk: part.permission.risk,
        source: part.permissionDecision?.source || part.permission.source,
        confidence:
          part.permissionDecision?.confidence ??
          (typeof part.permission.metadata?.confidence === 'number' ||
          part.permission.metadata?.confidence === 'low' ||
          part.permission.metadata?.confidence === 'medium' ||
          part.permission.metadata?.confidence === 'high'
            ? part.permission.metadata.confidence
            : null),
        reviewerModel:
          part.permissionDecision?.reviewerModel ??
          (typeof part.permission.metadata?.reviewer_model === 'string'
            ? part.permission.metadata.reviewer_model
            : null),
        riskCategories:
          part.permissionDecision?.riskCategories ??
          (Array.isArray(part.permission.metadata?.risk_categories)
            ? part.permission.metadata.risk_categories.filter(
                (item): item is string => typeof item === 'string'
              )
            : []),
      },
    ];
  });
}

function getActionDisplayOrder(actions: PermissionAction[]): PermissionAction[] {
  const once = actions.filter((action) => action.behavior === 'allow' && action.scope === 'once');
  const persistent = actions.filter(
    (action) => action.behavior === 'allow' && action.scope !== 'once'
  );
  const deny = actions.filter((action) => action.behavior === 'deny');
  return [...once, ...persistent, ...deny];
}

/** A server enum value the locale table does not know yet reads as itself. */
function labelOr(t: (key: string) => string, key: string, fallback: string): string {
  const label = t(key);
  return label === key ? fallback : label;
}

interface RiskTone {
  panel: string;
  chip: string;
}

function riskToneFor(risk: string | undefined): RiskTone {
  switch (risk) {
    case 'high':
    case 'critical':
      return {
        panel: 'border-red-600 bg-red-50 dark:border-red-400 dark:bg-red-950/30',
        chip: 'text-red-700 dark:text-red-400',
      };
    case 'medium':
      return {
        panel: 'border-amber-500 bg-amber-50 dark:border-amber-400 dark:bg-amber-950/25',
        chip: 'text-neutral-500 dark:text-neutral-400',
      };
    default:
      return {
        panel: 'border-neutral-400 bg-neutral-50 dark:border-zinc-500 dark:bg-zinc-800/60',
        chip: 'border-neutral-500 bg-white text-neutral-700 dark:border-zinc-500 dark:bg-zinc-900 dark:text-neutral-200',
      };
  }
}

interface ActionCommand {
  command: string;
  isPrefix: boolean;
}

function getActionCommand(action: PermissionAction): ActionCommand | null {
  for (const update of action.permissionUpdates ?? []) {
    if (update.type !== 'add_rule') continue;
    const matcher = update.payload.matcher;
    if (!matcher || typeof matcher !== 'object' || Array.isArray(matcher)) continue;

    const matcherRecord = matcher as Record<string, unknown>;
    if (matcherRecord.type === 'exact_input') {
      const value = matcherRecord.value;
      if (!value || typeof value !== 'object' || Array.isArray(value)) continue;
      const command = (value as Record<string, unknown>).command;
      if (typeof command === 'string' && command.trim()) {
        return { command: command.trim(), isPrefix: false };
      }
    } else if (matcherRecord.type === 'command_prefix') {
      const value = matcherRecord.value;
      if (typeof value === 'string' && value.trim()) {
        return { command: value.trim(), isPrefix: true };
      }
    }
  }
  return null;
}

const ApprovalCard: React.FC<{
  approval: PendingApproval;
  onDecision: PermissionApprovalDockProps['onDecision'];
  keyboardActive: boolean;
}> = ({ approval, onDecision, keyboardActive }) => {
  const { t } = useI18n();
  const [feedback, setFeedback] = React.useState('');
  const editingFeedback = feedback.trim().length > 0;
  const [selectedActionId, setSelectedActionId] = React.useState('');
  const feedbackInputRef = React.useRef<HTMLInputElement>(null);
  const displayName = normalizeToolName(approval.toolName).replace(/_/g, ' ');
  const description =
    typeof approval.args.description === 'string' ? approval.args.description.trim() : '';
  const promptAction = description
    ? `${description.charAt(0).toLowerCase()}${description.slice(1)}`
    : t('permissionDock.useTool', { tool: displayName });
  const command =
    typeof approval.args.content === 'string'
      ? approval.args.content
      : typeof approval.args.command === 'string'
        ? approval.args.command
        : '';
  const filePath =
    typeof approval.args.file_path === 'string'
      ? approval.args.file_path
      : typeof approval.args.path === 'string'
        ? approval.args.path
        : '';
  const detail = command || filePath || JSON.stringify(approval.args, null, 2);
  const riskTone = riskToneFor(approval.risk);
  const riskText = approval.risk
    ? t('permissionDock.riskLabel', {
        risk: labelOr(t, `permissionDock.riskLevels.${approval.risk}`, approval.risk),
      })
    : null;
  const orderedActions = React.useMemo(
    () =>
      getActionDisplayOrder(approval.actions).filter(
        (action) =>
          approval.source !== 'auto_classifier' ||
          action.scope === 'once' ||
          action.behavior === 'deny'
      ),
    [approval.actions, approval.source]
  );

  const allowActions = orderedActions.filter((action) => action.behavior === 'allow');
  const selectedAction =
    allowActions.find((action) => action.id === selectedActionId) ?? allowActions[0];
  const cancelFeedback = (): void => {
    setFeedback('');
    requestAnimationFrame(() => feedbackInputRef.current?.focus());
  };

  const submitAction = React.useCallback(
    (action: PermissionAction, actionFeedback?: string) => {
      onDecision(
        approval.approvalId,
        approval.toolCallId,
        action.behavior === 'allow',
        action.scope === 'session' || action.scope === 'global' ? action.scope : null,
        approval.toolName,
        action.id,
        action.behavior === 'deny' ? actionFeedback?.trim() || undefined : undefined
      );
    },
    [approval, onDecision]
  );

  const selectAction = React.useCallback(
    (action: PermissionAction) => {
      submitAction(action);
    },
    [submitAction]
  );

  const rejectAction = orderedActions.find((action) => action.behavior === 'deny');
  React.useEffect(() => {
    if (!keyboardActive || editingFeedback) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (isImeComposing(event)) return;
      const target = event.target as HTMLElement | null;
      const isTyping =
        target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.isContentEditable;
      if (isTyping) return;

      if (event.ctrlKey && event.key === 'Enter') {
        const allowOnce = selectedAction;
        if (allowOnce) {
          event.preventDefault();
          selectAction(allowOnce);
        }
        return;
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [keyboardActive, selectedAction, selectAction, editingFeedback]);

  const actionLabel = (action: PermissionAction): string => {
    if (action.scope === 'once') return t('permissionDock.once');
    const commandRule = getActionCommand(action);
    if (commandRule && !commandRule.isPrefix) {
      return t(
        action.scope === 'session'
          ? 'permissionDock.commandSession'
          : 'permissionDock.commandAlways'
      );
    }
    return action.label;
  };

  return (
    <section className="mx-auto w-full max-w-5xl animate-brutal-drop overflow-hidden rounded-sm border-2 border-brutal-black bg-white font-mono text-brutal-black shadow-[3px_3px_0_0_#000] dark:border-neutral-500 dark:bg-zinc-900 dark:text-white dark:shadow-[3px_3px_0_0_rgba(255,255,255,0.14)]">
      <div className="flex items-start gap-2.5 px-4 pt-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-brutal-yellow text-brutal-black">
          <ShieldCheckIcon className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1 text-[13px] font-medium leading-6">
          {t('permissionDock.title', {
            action: promptAction,
          })}
        </div>
        {/* A described call reads as its description alone ("May I list the
            files?"), so name the tool itself: that is what the user approves. */}
        {description && (
          <span
            className="mt-0.5 max-w-[25%] truncate px-1.5 py-0.5 text-[10px] text-neutral-500 dark:text-neutral-400"
            title={approval.toolName}
          >
            {displayName}
          </span>
        )}
      </div>

      {detail && (
        <pre className="mx-4 mt-3 whitespace-pre-wrap break-words rounded-sm border border-neutral-200 bg-neutral-50 px-3 py-2.5 font-mono text-[12px] leading-5 text-neutral-800 dark:border-zinc-700 dark:bg-zinc-800 dark:text-neutral-200">
          {detail}
        </pre>
      )}

      {approval.reason && (
        // The reason is why the user is being asked at all, so it reads at body
        // size and wraps in full instead of an ellipsised footnote; the risk
        // level tints it so a high-risk call does not look like a routine one.
        <div className="mx-4 mt-3 min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            {riskText && (
              <span className={`shrink-0 text-[11px] font-medium ${riskTone.chip}`}>
                {riskText}
              </span>
            )}
          </div>
          <p className="mt-1.5 whitespace-pre-wrap break-words text-[12px] leading-5 text-neutral-800 dark:text-neutral-100">
            {approval.reason}
          </p>
        </div>
      )}

      <div className="permission-dock-controls mx-4 mb-3 mt-4 border-t border-neutral-200 pt-3 dark:border-zinc-700">
        <div className="permission-dock-persistent flex h-full items-center gap-3">
          {rejectAction && (
            <input
              ref={feedbackInputRef}
              type="text"
              value={feedback}
              aria-label={t('permissionDock.feedback')}
              onChange={(event) => setFeedback(event.target.value)}
              onKeyDown={(event) => {
                if (isImeComposing(event)) return;
                if (event.key === 'Escape') {
                  event.preventDefault();
                  cancelFeedback();
                }
                if (event.key === 'Enter' && feedback.trim()) {
                  event.preventDefault();
                  if (rejectAction) submitAction(rejectAction, feedback);
                }
              }}
              placeholder={t('permissionDock.feedbackPlaceholder')}
              className="h-9 min-w-0 flex-1 border border-brutal-black bg-white px-2.5 text-xs outline-none focus:bg-brutal-yellow/10 focus:ring-2 focus:ring-brutal-yellow dark:border-neutral-500 dark:bg-zinc-800 dark:text-white"
            />
          )}
          <div className="permission-dock-action-slot ml-auto flex shrink-0 justify-end">
            {editingFeedback && rejectAction ? (
              <div
                key="feedback"
                className="permission-dock-transition flex h-full items-center gap-2"
              >
                <button
                  type="button"
                  disabled={!feedback.trim()}
                  onClick={() => submitAction(rejectAction, feedback)}
                  className="h-9 shrink-0 border-2 border-brutal-black bg-brutal-black px-3 text-xs font-bold text-white disabled:opacity-35 dark:border-neutral-300 dark:bg-neutral-200 dark:text-brutal-black"
                >
                  {t('permissionDock.rejectSend')}
                </button>
                <button
                  type="button"
                  onClick={cancelFeedback}
                  aria-label={t('permissionDock.cancelFeedback')}
                  className="h-9 w-9 shrink-0 text-lg text-neutral-500 hover:bg-neutral-100 dark:hover:bg-zinc-800"
                >
                  ×
                </button>
              </div>
            ) : (
              <div
                key="actions"
                className="permission-dock-transition flex h-full flex-wrap items-center justify-end gap-2"
              >
                {rejectAction && (
                  <>
                    <button
                      type="button"
                      onClick={() => selectAction(rejectAction)}
                      className="min-h-9 border-2 border-neutral-300 px-3 py-1.5 text-xs font-bold hover:bg-neutral-100 dark:border-zinc-600 dark:hover:bg-zinc-800"
                    >
                      {t('permissionDock.decline')}
                    </button>
                  </>
                )}{' '}
                {selectedAction && (
                  <div className="flex min-w-0 items-stretch border-2 border-brutal-black bg-brutal-yellow text-brutal-black">
                    <button
                      type="button"
                      onClick={() => selectAction(selectedAction)}
                      className="flex min-h-8 min-w-0 items-center gap-2 px-3 py-1.5 text-xs font-bold hover:bg-black/5"
                    >
                      {selectedAction.scope === 'once'
                        ? t('permissionDock.allow')
                        : actionLabel(selectedAction)}
                      <span className="text-[10px] font-normal opacity-60">
                        {t('permissionDock.ctrlEnter')}
                      </span>
                    </button>
                    {allowActions.length > 1 && (
                      <BrutalSelect
                        value={selectedAction.id}
                        onChange={setSelectedActionId}
                        ariaLabel={t('permissionDock.allowOptions')}
                        menuAlign="end"
                        options={allowActions.map((action) => ({
                          value: action.id,
                          label: actionLabel(action),
                        }))}
                        variant="ghost"
                        dropUp
                        className="w-9 shrink-0 border-l border-brutal-black/30"
                        buttonClassName="!h-full !px-2 !py-1.5 !text-brutal-black [&>span]:sr-only hover:!bg-black/5"
                        dropdownClassName="permission-scope-menu !min-w-64"
                      />
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
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
