/**
 * SubAgentSteerBox — redirect one running sub-agent, in place.
 *
 * Shared by the transcript card and the sidebar panel so a sub-agent can be
 * redirected wherever it is shown: a blocking child from the card its parent is
 * waiting on, a background one from the sidebar that is its only home.
 *
 * The message is injected into the child's live run rather than steering it —
 * steering cancels and replays, which for a blocking child would cancel the
 * coroutine its parent's tool call is awaiting and kill the agent being
 * redirected. Injection lands at the child's next model request instead, so
 * each redirect shows as queued until the run reports having taken it.
 */
import React, { useCallback, useState } from 'react';
import { useI18n } from '../../i18n';
import { sendSubAgentSteer, useSentSteers } from '../../hooks/useSubAgentSteer';

interface SubAgentSteerBoxProps {
  taskId: string;
  /**
   * Whether the sub-agent can still take a message. False hides the input but
   * keeps what was already sent on screen: a redirect delivered moments before
   * the run ended is precisely the one you want to reread afterwards, and it
   * used to disappear along with the box.
   */
  canSend: boolean;
}

export const SubAgentSteerBox: React.FC<SubAgentSteerBoxProps> = ({ taskId, canSend }) => {
  const { t } = useI18n();
  const sent = useSentSteers(taskId);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = useCallback(async () => {
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (await sendSubAgentSteer(taskId, message)) {
        setText('');
      } else {
        setError(t('subAgents.steerFailed'));
      }
    } catch {
      setError(t('subAgents.steerFailed'));
    } finally {
      setBusy(false);
    }
  }, [taskId, text, busy, t]);

  if (!canSend && sent.length === 0) return null;

  return (
    <div className="min-w-0">
      {canSend && (
        <div className="flex items-center gap-1.5">
          <input
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder={t('subAgents.steerPlaceholder')}
            disabled={busy}
            className="flex-1 min-w-0 px-2 py-1 text-[11px] bg-white dark:bg-zinc-900 text-brutal-black dark:text-white border-2 border-neutral-200 dark:border-zinc-600 rounded-sm focus:outline-none focus:border-brutal-black dark:focus:border-white disabled:opacity-50"
          />
          <button
            onClick={() => void send()}
            disabled={busy || !text.trim()}
            className="shrink-0 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide bg-white dark:bg-zinc-900 text-brutal-black dark:text-white border-2 border-brutal-black dark:border-white rounded-sm hover:bg-neutral-100 dark:hover:bg-zinc-800 transition-colors disabled:opacity-40"
          >
            {t('subAgents.steer')}
          </button>
        </div>
      )}
      {error && <div className="mt-1 text-[10px] text-red-600 dark:text-red-400">{error}</div>}
      {/* Sent is not the same as heard: an injected message waits for the
          child's next model request, which cannot happen until whatever tool
          it is running returns. Showing only "queued" left people hunting for
          a message that had in fact arrived, so say what each one is waiting
          on, and keep the text readable rather than truncated to a stub. */}
      {sent.length > 0 && (
        <div className="mt-1.5 space-y-1">
          {sent.map((steer) => (
            <div key={steer.enqueueId} className="flex items-start gap-1.5 min-w-0">
              <span
                className={`shrink-0 mt-[1px] font-mono text-[11px] leading-none ${
                  steer.absorbed
                    ? 'text-neutral-300 dark:text-neutral-600'
                    : 'text-brutal-black dark:text-white'
                }`}
                aria-hidden
              >
                &rarr;
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[11px] text-neutral-600 dark:text-neutral-300 break-words leading-snug">
                  {steer.text}
                </div>
                <div
                  className={`text-[9px] font-mono font-bold uppercase tracking-wide ${
                    steer.absorbed
                      ? 'text-neutral-400 dark:text-neutral-500'
                      : 'text-neutral-500 dark:text-neutral-400'
                  }`}
                >
                  {steer.absorbed
                    ? t('subAgents.steerTaken')
                    : `${t('subAgents.steerQueued')} \u00b7 ${t('subAgents.steerQueuedHint')}`}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
