import React, { useCallback, useEffect, useRef, useState } from 'react';

import { useI18n } from '../../i18n';
import { BrutalButton } from '../BrutalButton';
import { SectionCardHeader, SettingsCard } from './SettingsCard';
import { fetchOpsLogs, type OpsLogTail } from '../../lib/opsApi';

const POLL_MS = 5000;
const LINE_CHOICES = [100, 500, 2000];

interface ServiceLogCardProps {
  /**
   * Stop polling. The console sets this across a self-restart, when the host
   * is expected to be unreachable and a failed read would say nothing new.
   */
  paused?: boolean;
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
 */
export function ServiceLogCard({ paused = false }: ServiceLogCardProps): React.ReactElement {
  const { t } = useI18n();
  const [logs, setLogs] = useState<OpsLogTail | null>(null);
  const [lines, setLines] = useState(LINE_CHOICES[0]);
  const [follow, setFollow] = useState(true);
  const boxRef = useRef<HTMLPreElement | null>(null);

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

  // Pin the view to the newest line while following, the way `tail -f` does.
  useEffect(() => {
    if (follow && boxRef.current) {
      boxRef.current.scrollTop = boxRef.current.scrollHeight;
    }
  }, [logs, follow]);

  return (
    <SettingsCard>
      <SectionCardHeader
        title={t('settings.service.logTitle')}
        description={t('settings.service.logDesc')}
        actions={
          <>
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
          </>
        }
      />

      {logs?.available === false ? (
        <p className="font-mono text-xs text-neutral-500">{t('settings.service.logMissing')}</p>
      ) : (
        <pre
          ref={boxRef}
          aria-label={t('settings.service.logTitle')}
          className="max-h-96 overflow-auto border-2 border-brutal-black bg-brutal-black p-3 font-mono text-xs leading-relaxed text-neutral-200"
        >
          {logs?.lines.join('\n') ?? ''}
        </pre>
      )}

      {logs?.path && (
        <p className="mt-2 break-all font-mono text-[11px] text-neutral-500">{logs.path}</p>
      )}
    </SettingsCard>
  );
}
