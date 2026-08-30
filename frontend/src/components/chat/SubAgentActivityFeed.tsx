/**
 * SubAgentActivityFeed — the newest few things a sub-agent has done.
 *
 * Shown inside a blocking `agent` call's card, where the parent's turn is
 * suspended and the transcript would otherwise sit empty until the child
 * returns. Reuses the transcript's own tool summaries, so a call reads "Run —
 * npm test" here exactly as it would anywhere else, rather than as a bare tool
 * name that says nothing about what the wait is for.
 */
import React from 'react';
import { useI18n } from '../../i18n';
import { getToolSummary, toolLabel } from './toolSummary';
import type { SubAgentActivity } from '../../hooks/useSubAgentActivity';

/**
 * Arguments arrive as a stream of JSON fragments, so most of the time a call is
 * running its args do not parse yet. Null simply means "no detail to show".
 */
function parseArgs(args: string): Record<string, unknown> | null {
  if (!args) return null;
  try {
    const parsed: unknown = JSON.parse(args);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

export const SubAgentActivityFeed: React.FC<{ activity: SubAgentActivity }> = ({ activity }) => {
  const { t } = useI18n();
  const { entries, phase } = activity;

  if (entries.length === 0 && !phase) return null;

  return (
    <div className="min-w-0">
      <div className="text-[10px] font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase tracking-wide mb-0.5">
        {t('subAgents.activity')}
      </div>
      <div className="space-y-0.5">
        {entries.map((entry) => {
          const parsed = parseArgs(entry.args);
          const summary = entry.toolName
            ? getToolSummary(entry.toolName, parsed, t, entry.done ? 'past' : 'active')
            : null;
          const verb = summary?.verb ?? toolLabel(entry.toolName);
          return (
            <div
              key={entry.toolCallId}
              className="flex items-center gap-1.5 text-[11px] min-w-0"
              title={summary?.title ?? undefined}
            >
              <span
                className={`shrink-0 w-1.5 h-1.5 rounded-full ${
                  entry.done
                    ? 'bg-neutral-300 dark:bg-zinc-600'
                    : 'bg-brutal-black dark:bg-white animate-pulse'
                }`}
              />
              <span
                className={`shrink-0 font-mono ${
                  entry.done
                    ? 'text-neutral-400 dark:text-neutral-500'
                    : 'text-neutral-700 dark:text-neutral-200'
                }`}
              >
                {verb}
              </span>
              {summary?.detail && (
                <span className="truncate min-w-0 font-mono text-neutral-400 dark:text-neutral-500">
                  {summary.detail}
                </span>
              )}
            </div>
          );
        })}

        {/* Between tool calls the child is still working. Without this a long
            stretch of reasoning is indistinguishable from a stall. */}
        {phase && (
          <div className="flex items-center gap-1.5 text-[11px] min-w-0">
            <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-brutal-black dark:bg-white animate-pulse" />
            <span className="font-mono text-neutral-500 dark:text-neutral-400 italic">
              {phase === 'thinking' ? t('subAgents.thinking') : t('subAgents.responding')}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
