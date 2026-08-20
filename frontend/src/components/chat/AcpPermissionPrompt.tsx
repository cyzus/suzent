import React, { useState } from 'react';
import { useI18n } from '../../i18n';
import type { AcpPermissionRequest } from '../../types/agui';
import { resolveAcpPermission } from '../../lib/api';

interface Props {
  request: AcpPermissionRequest;
  /** Streaming is over — the agent is no longer waiting, so hide the actions. */
  stale?: boolean;
}

/**
 * Approval prompt for an external ACP agent's tool call.
 *
 * The agent's subprocess is blocked on this decision, so it is answered against
 * the ACP endpoint directly rather than through the native resume_approvals
 * flow (which resumes a Suzent turn that isn't running here).
 */
export const AcpPermissionPrompt: React.FC<Props> = ({ request, stale }) => {
  const { t } = useI18n();
  const [pending, setPending] = useState(false);
  const [outcome, setOutcome] = useState<'approved' | 'denied' | null>(
    request.resolved ?? null,
  );
  const [error, setError] = useState<string | null>(null);

  const decide = async (approved: boolean, optionId?: string) => {
    setPending(true);
    setError(null);
    try {
      await resolveAcpPermission(request.requestId, approved, optionId);
      setOutcome(approved ? 'approved' : 'denied');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  const allowOptions = request.options.filter(o => o.kind.startsWith('allow'));
  const rejectOptions = request.options.filter(o => o.kind.startsWith('reject'));
  const title = request.toolCall?.title || t('acp.permission.untitled');

  return (
    <div className="my-2 border-2 border-brutal-black dark:border-white bg-white dark:bg-zinc-900 shadow-[3px_3px_0px_#000] dark:shadow-[3px_3px_0px_#fff]">
      <div className="bg-brutal-black dark:bg-white text-white dark:text-brutal-black px-2 py-1 text-[10px] font-mono font-bold uppercase tracking-wider">
        {t('acp.permission.header')}
      </div>
      <div className="p-3 flex flex-col gap-2">
        <div className="font-mono text-sm break-words">{title}</div>
        {request.toolCall?.kind && (
          <div className="text-[10px] font-mono uppercase text-neutral-500">
            {request.toolCall.kind}
          </div>
        )}

        {outcome ? (
          <div className="text-[11px] font-mono font-bold uppercase">
            {outcome === 'approved'
              ? t('acp.permission.approved')
              : t('acp.permission.denied')}
          </div>
        ) : stale ? (
          <div className="text-[11px] font-mono uppercase text-neutral-500">
            {t('acp.permission.expired')}
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {allowOptions.map(option => (
              <button
                key={option.optionId}
                disabled={pending}
                onClick={() => decide(true, option.optionId)}
                className="border-2 border-brutal-black dark:border-white px-2 py-1 text-[11px] font-mono font-bold uppercase hover:bg-brutal-black hover:text-white dark:hover:bg-white dark:hover:text-brutal-black disabled:opacity-50"
              >
                {option.name}
              </button>
            ))}
            {rejectOptions.map(option => (
              <button
                key={option.optionId}
                disabled={pending}
                onClick={() => decide(false, option.optionId)}
                className="border-2 border-neutral-400 px-2 py-1 text-[11px] font-mono uppercase hover:border-brutal-black dark:hover:border-white disabled:opacity-50"
              >
                {option.name}
              </button>
            ))}
          </div>
        )}

        {error && (
          <div className="text-[11px] font-mono text-red-600 break-words">{error}</div>
        )}
      </div>
    </div>
  );
};
