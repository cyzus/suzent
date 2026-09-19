import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useI18n } from '../../i18n';
import { BrutalButton } from '../BrutalButton';
import { SectionCardHeader, SettingsCard } from './SettingsCard';
import { fetchOpsLogs, type OpsLogTail } from '../../lib/opsApi';
import {
  countByLevel,
  filterServiceLog,
  formatEntry,
  parseServiceLog,
  type LogEntry,
  type LogLevel,
} from '../../lib/serviceLog';

const POLL_MS = 5000;
const LINE_CHOICES = [100, 500, 2000];

/** The thresholds worth offering. The rest of loguru's levels are rarely used. */
const LEVEL_CHOICES: (LogLevel | null)[] = [null, 'DEBUG', 'INFO', 'WARNING', 'ERROR'];

/**
 * Level colours for the dark panel. Severity has to be readable at a glance
 * from across a scrolling wall of DEBUG, so the quiet levels stay grey and
 * only the ones worth stopping at take a colour.
 */
const LEVEL_STYLE: Record<LogLevel, string> = {
  TRACE: 'text-neutral-500',
  DEBUG: 'text-neutral-500',
  INFO: 'text-sky-300',
  SUCCESS: 'text-emerald-300',
  WARNING: 'text-amber-300',
  ERROR: 'text-red-400',
  CRITICAL: 'text-red-300',
};

/** Rows that deserve to be picked out of the wall, not just tinted. */
const ROW_STYLE: Partial<Record<LogLevel, string>> = {
  WARNING: 'bg-amber-400/10',
  ERROR: 'bg-red-500/10',
  CRITICAL: 'bg-red-500/20',
};

interface ServiceLogCardProps {
  /**
   * Stop polling. The console sets this across a self-restart, when the host
   * is expected to be unreachable and a failed read would say nothing new.
   */
  paused?: boolean;
}

function LogRow({ entry }: { entry: LogEntry }): React.ReactElement {
  const level = entry.level;
  return (
    <div className={`flex gap-2 px-2 py-[1px] ${level ? (ROW_STYLE[level] ?? '') : 'bg-white/5'}`}>
      {entry.time && <span className="shrink-0 text-neutral-500">{entry.time}</span>}
      {level && (
        <span className={`w-[4.5rem] shrink-0 font-bold ${LEVEL_STYLE[level]}`}>{level}</span>
      )}
      <div className="min-w-0 flex-1">
        {entry.source && (
          <span className="mr-2 text-cyan-500/80" title={entry.source}>
            {entry.source}
          </span>
        )}
        <span className={`whitespace-pre-wrap break-words ${level ? '' : 'text-neutral-400'}`}>
          {entry.message}
        </span>
        {entry.continuation.length > 0 && (
          <pre className="mt-1 whitespace-pre-wrap break-words border-l-2 border-neutral-700 pl-2 text-neutral-400">
            {entry.continuation.join('\n')}
          </pre>
        )}
      </div>
    </div>
  );
}

/**
 * The tail of the service log.
 *
 * Shared by both shells deliberately: the log answers the same question --
 * what did the server last do -- whether you are looking at the machine in
 * front of you or one across a tunnel, and having it in one place in the
 * console and a path to open by hand on the desktop meant two different
 * answers to it. Both read `/ops/logs`, since even the desktop app talks to
 * the backend over HTTP.
 *
 * The lines are parsed rather than dumped, because the question that brings
 * someone here is almost always "what failed", and a plain dump of two
 * thousand mostly-DEBUG lines answers it slowly.
 */
export function ServiceLogCard({ paused = false }: ServiceLogCardProps): React.ReactElement {
  const { t } = useI18n();
  const [logs, setLogs] = useState<OpsLogTail | null>(null);
  const [lines, setLines] = useState(LINE_CHOICES[0]);
  const [follow, setFollow] = useState(true);
  const [minLevel, setMinLevel] = useState<LogLevel | null>(null);
  const [query, setQuery] = useState('');
  const [copied, setCopied] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);

  const refresh = useCallback(
    async (signal?: AbortSignal): Promise<void> => {
      try {
        setLogs(await fetchOpsLogs(lines, signal));
      } catch {
        // A failed read leaves the last tail on screen. Whether the host is
        // reachable at all is the surrounding page's question, not this card's.
      }
    },
    [lines]
  );

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    if (!follow) return () => controller.abort();
    const timer = window.setInterval(() => {
      if (!paused) void refresh();
    }, POLL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [refresh, follow, paused]);

  // Parsing 2000 lines on every poll is wasted work when the tail has not
  // moved, which is the common case between two five-second reads.
  const entries = useMemo(() => parseServiceLog(logs?.lines ?? []), [logs]);
  const counts = useMemo(() => countByLevel(entries), [entries]);
  const shown = useMemo(
    () => filterServiceLog(entries, { minLevel, query }),
    [entries, minLevel, query]
  );

  // Pin the view to the newest line while following, the way `tail -f` does.
  useEffect(() => {
    if (follow && boxRef.current) {
      boxRef.current.scrollTop = boxRef.current.scrollHeight;
    }
  }, [shown, follow]);

  const copy = useCallback(async () => {
    const text = shown.map(formatEntry).join('\n');
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be refused; the text is still on screen.
    }
  }, [shown]);

  const problems = counts.ERROR + counts.CRITICAL;

  return (
    <SettingsCard>
      <SectionCardHeader
        title={t('settings.service.logTitle')}
        description={t('settings.service.logDesc')}
        actions={
          <>
            <label className="flex items-center gap-2 text-xs font-bold uppercase">
              {t('settings.service.logLevel')}
              <select
                value={minLevel ?? ''}
                onChange={(event) => setMinLevel((event.target.value || null) as LogLevel | null)}
                className="border-2 border-brutal-black bg-white px-2 py-1 font-mono text-xs dark:bg-zinc-900"
              >
                {LEVEL_CHOICES.map((choice) => (
                  <option key={choice ?? 'all'} value={choice ?? ''}>
                    {choice ?? t('settings.service.logLevelAll')}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-xs font-bold uppercase">
              {t('settings.service.logLines')}
              <select
                value={lines}
                onChange={(event) => setLines(Number(event.target.value))}
                className="border-2 border-brutal-black bg-white px-2 py-1 font-mono text-xs dark:bg-zinc-900"
              >
                {LINE_CHOICES.map((choice) => (
                  <option key={choice} value={choice}>
                    {choice}
                  </option>
                ))}
              </select>
            </label>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t('settings.service.logSearch')}
              aria-label={t('settings.service.logSearch')}
              className="w-40 border-2 border-brutal-black bg-white px-2 py-1 font-mono text-xs dark:bg-zinc-900"
            />
            <BrutalButton
              size="sm"
              isActive={follow}
              onClick={() => setFollow((following) => !following)}
            >
              {t('settings.service.follow')}
            </BrutalButton>
            <BrutalButton size="sm" onClick={() => void refresh()}>
              {t('settings.service.refresh')}
            </BrutalButton>
            <BrutalButton size="sm" onClick={() => void copy()} disabled={shown.length === 0}>
              {copied ? t('settings.service.logCopied') : t('settings.service.logCopy')}
            </BrutalButton>
          </>
        }
      />

      {logs?.available === false ? (
        <p className="font-mono text-xs text-neutral-500">{t('settings.service.logMissing')}</p>
      ) : (
        <div
          ref={boxRef}
          role="log"
          aria-label={t('settings.service.logTitle')}
          className="max-h-96 overflow-auto border-2 border-brutal-black bg-brutal-black py-2 font-mono text-xs leading-relaxed text-neutral-200"
        >
          {shown.length === 0 ? (
            <p className="px-3 py-1 text-neutral-500">
              {entries.length === 0
                ? t('settings.service.logEmpty')
                : t('settings.service.logNoMatch')}
            </p>
          ) : (
            shown.map((entry) => <LogRow key={entry.index} entry={entry} />)
          )}
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 font-mono text-[11px] text-neutral-500">
        <span>
          {t('settings.service.logCounts', { shown: shown.length, total: entries.length })}
          {problems > 0 && (
            <span className="ml-2 font-bold text-red-500">
              {t('settings.service.logProblems', { count: problems })}
            </span>
          )}
        </span>
        {logs?.path && <span className="break-all">{logs.path}</span>}
      </div>
    </SettingsCard>
  );
}
