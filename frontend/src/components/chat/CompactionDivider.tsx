import React from 'react';
import type { Message } from '../../types/api';
import { useI18n } from '../../i18n';
import { formatTokens } from '../../lib/contextFormat';
import type { CompactionNoticeDetails } from '../../lib/compactionNotices';
import { CompactionCube } from './CompactionCube';

// A pass that finishes sooner (a summary prepared in the background) would
// only flash the animation, so it starts after this long.
const COMPACTION_ANIMATION_DELAY_MS = 500;

function useDelayedFlag(value: boolean, delayMs: number): boolean {
  const [delayed, setDelayed] = React.useState(false);
  React.useEffect(() => {
    if (!value) {
      setDelayed(false);
      return;
    }
    const timer = window.setTimeout(() => setDelayed(true), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return value && delayed;
}

const LinesIcon: React.FC = () => (
  <svg
    viewBox="0 0 16 16"
    aria-hidden="true"
    className="h-3.5 w-3.5 flex-none fill-none stroke-current"
    strokeWidth="1.6"
    strokeLinecap="round"
  >
    <path d="M3 5h10M5 8h6M7 11h2" />
  </svg>
);

const AlertIcon: React.FC = () => (
  <svg
    viewBox="0 0 16 16"
    aria-hidden="true"
    className="h-3.5 w-3.5 flex-none fill-none stroke-current"
    strokeWidth="1.8"
    strokeLinecap="round"
  >
    <path d="M8 4v5M8 11.5v.5" />
  </svg>
);

/** The summary's lines, with its section headings marked; blank lines dropped. */
function summaryLines(summary: string): { heading: boolean; text: string }[] {
  return summary
    .split('\n')
    .filter((line) => line.trim())
    .map((line) => {
      const heading = /^\s*#{1,6}\s+/.test(line);
      return { heading, text: heading ? line.replace(/^\s*#{1,6}\s+/, '') : line };
    });
}

/**
 * A compaction notice drawn as a divider in the conversation: compaction is a
 * boundary in the history, not something anyone said.
 */
export const CompactionDivider: React.FC<{
  message: Message;
  details: CompactionNoticeDetails;
  resolved?: boolean;
}> = ({ message, details, resolved = false }) => {
  const { t, locale } = useI18n();
  const [showSummary, setShowSummary] = React.useState(false);
  const running = details.stage === 'start';
  const failed = details.stage === 'error';
  const animate = useDelayedFlag(running, COMPACTION_ANIMATION_DELAY_MS);

  const time =
    message.timestamp && !Number.isNaN(Date.parse(message.timestamp))
      ? new Date(message.timestamp).toLocaleTimeString(locale, {
          hour: '2-digit',
          minute: '2-digit',
        })
      : null;
  const manual = details.source === 'manual' || details.source === 'command';

  let title: string;
  if (running) title = t('chatMessage.compaction.running');
  else if (failed)
    title = /timed out/i.test(details.detail ?? '')
      ? t('chatMessage.compaction.timedOut')
      : t('chatMessage.compaction.failed');
  else if (details.stage === 'skipped') title = t('chatMessage.compaction.skipped');
  else title = manual ? t('chatMessage.compaction.doneManual') : t('chatMessage.compaction.done');

  const tokens =
    details.stage === 'complete' && details.tokensBefore != null && details.tokensAfter != null
      ? `${formatTokens(details.tokensBefore)} → ${formatTokens(details.tokensAfter)}`
      : null;

  let note: string | null = null;
  if (failed)
    note = resolved ? t('chatMessage.compactionResolved') : t('chatMessage.compaction.preserved');
  else if (details.reason === 'cold_cache')
    note = t('chatMessage.compaction.viaColdCache', {
      minutes: String(Math.max(1, Math.round((details.idleSeconds ?? 0) / 60))),
    });
  else if (details.reason === 'prepared') note = t('chatMessage.compaction.viaPrepared');

  const tone = failed && !resolved ? 'text-brutal-red' : 'text-neutral-500 dark:text-neutral-400';
  const rule = failed && !resolved ? 'bg-brutal-red/50' : 'bg-neutral-200 dark:bg-zinc-700';

  return (
    <div className="w-full max-w-3xl py-1 pl-2 md:pl-6" role="separator" aria-label={title}>
      <div className={`flex items-center gap-3 ${tone}`}>
        <div className={`h-px flex-1 ${rule}`} />
        <span
          className={`inline-flex min-w-0 items-center gap-1.5 text-xs ${running && !animate ? 'animate-pulse' : ''}`}
          title={details.detail ?? undefined}
        >
          {animate ? <CompactionCube size={16} /> : failed ? <AlertIcon /> : <LinesIcon />}
          <span
            className={`font-semibold ${failed && !resolved ? '' : 'text-brutal-black dark:text-neutral-100'}`}
          >
            {title}
          </span>
          {tokens && <span className="font-mono tabular-nums">{tokens}</span>}
          {time && !running && <time dateTime={message.timestamp}>· {time}</time>}
        </span>
        <div className={`h-px flex-1 ${rule}`} />
      </div>
      {(note || details.summary) && (
        <div className="mt-0.5 text-center text-[11.5px] text-neutral-500 dark:text-neutral-400">
          {note}
          {note && details.summary && ' · '}
          {details.summary && (
            <button
              type="button"
              onClick={() => setShowSummary((open) => !open)}
              aria-expanded={showSummary}
              className="underline underline-offset-2 hover:text-brutal-black dark:hover:text-white"
            >
              {showSummary
                ? t('chatMessage.compaction.hideSummary')
                : t('chatMessage.compaction.showSummary')}
            </button>
          )}
        </div>
      )}
      {showSummary && details.summary && (
        <div className="mx-auto mt-2 max-w-2xl space-y-0.5 border-l-2 border-neutral-200 pl-3 text-[12px] leading-relaxed text-neutral-700 dark:border-zinc-700 dark:text-neutral-300">
          {summaryLines(details.summary).map((line, index) =>
            line.heading ? (
              <div
                key={index}
                className="pt-1.5 font-bold text-brutal-black first:pt-0 dark:text-neutral-100"
              >
                {line.text}
              </div>
            ) : (
              <div key={index} className="whitespace-pre-wrap">
                {line.text}
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
};
