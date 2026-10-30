import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import { resolveCatalogText } from '../tools/CapabilityToolPicker';
import {
  cancelFocalWakeup,
  fetchFocalPanel,
  type FocalPanel,
  type FocalWakeup,
} from '../../lib/focalAgent';
import { hoverText } from '../../lib/hoverText';

const PANEL_POLL_MS = 30_000;

/** The Tools tab on the Focal chat: Regent's fixed tools and its own wake-ups. */
export function FocalToolsPanel(): React.ReactElement {
  const [panel, setPanel] = useState<FocalPanel | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [cancelling, setCancelling] = useState<number | null>(null);
  const [cancelError, setCancelError] = useState(false);
  const request = useRef(0);

  const refresh = useCallback(async (): Promise<void> => {
    const sequence = ++request.current;
    try {
      const next = await fetchFocalPanel();
      if (sequence !== request.current) return;
      setPanel(next);
      setLoadError(false);
    } catch {
      if (sequence === request.current) setLoadError(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), PANEL_POLL_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const cancel = async (wakeup: FocalWakeup): Promise<void> => {
    setCancelling(wakeup.id);
    setCancelError(false);
    try {
      await cancelFocalWakeup(wakeup.id);
      await refresh();
    } catch {
      setCancelError(true);
    } finally {
      setCancelling(null);
    }
  };

  return (
    <FocalToolsPanelView
      panel={panel}
      loadError={loadError}
      cancelling={cancelling}
      cancelError={cancelError}
      onRetry={() => void refresh()}
      onCancel={(wakeup) => void cancel(wakeup)}
    />
  );
}

interface FocalToolsPanelViewProps {
  panel: FocalPanel | null;
  loadError: boolean;
  cancelling: number | null;
  cancelError: boolean;
  onRetry: () => void;
  onCancel: (wakeup: FocalWakeup) => void;
}

export function FocalToolsPanelView({
  panel,
  loadError,
  cancelling,
  cancelError,
  onRetry,
  onCancel,
}: FocalToolsPanelViewProps): React.ReactElement {
  const { t, locale } = useI18n();
  const heading = (label: string): React.ReactNode => (
    <h2 className="px-3 pt-3 pb-1.5 text-[10px] font-bold uppercase tracking-widest text-neutral-500 dark:text-neutral-400">
      {label}
    </h2>
  );
  const formatTime = (iso: string): string =>
    new Date(iso).toLocaleString(locale, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });

  if (!panel) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 px-4 text-center text-xs text-neutral-500">
        {loadError ? (
          <>
            <p role="alert">{t('focalTools.loadError')}</p>
            <button type="button" onClick={onRetry} className="font-bold underline">
              {t('focalTools.retry')}
            </button>
          </>
        ) : (
          <p role="status">{t('focalTools.loading')}</p>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0 overflow-y-auto scrollbar-thin">
      <section aria-label={t('focalTools.wakeups')}>
        {heading(t('focalTools.wakeups'))}
        {panel.wakeups.length === 0 ? (
          <p className="px-3 pb-3 text-xs leading-relaxed text-neutral-500 dark:text-neutral-400">
            {t('focalTools.noWakeups')}
          </p>
        ) : (
          <ul className="flex flex-col gap-1.5 px-1.5 pb-3">
            {panel.wakeups.map((wakeup) => (
              <li
                key={wakeup.id}
                className="flex items-start gap-2 border-2 border-brutal-black bg-white dark:bg-zinc-800 px-2.5 py-2 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span
                      className={`shrink-0 border border-brutal-black px-1 font-mono text-[9px] font-bold uppercase ${wakeup.kind === 'reminder' ? 'bg-brutal-yellow text-brutal-black' : 'bg-white text-brutal-black dark:bg-zinc-700 dark:text-white'}`}
                    >
                      {t(`focalTools.${wakeup.kind}`)}
                    </span>
                    <span className="truncate text-xs font-bold" title={wakeup.name}>
                      {wakeup.name}
                    </span>
                  </div>
                  <p className="mt-1 font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
                    {wakeup.nextRunAt
                      ? t('focalTools.nextRun', { time: formatTime(wakeup.nextRunAt) })
                      : t('focalTools.unscheduled')}
                    {wakeup.scheduleKind !== 'once' && ` · ${wakeup.schedule}`}
                  </p>
                  {wakeup.lastError && (
                    <p
                      className="mt-1 text-[10px] font-bold text-red-600 dark:text-red-400 truncate"
                      title={hoverText(wakeup.lastError)}
                    >
                      {t('focalTools.lastRunFailed')}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => onCancel(wakeup)}
                  disabled={cancelling !== null}
                  aria-label={t('focalTools.cancelAria', { name: wakeup.name })}
                  className="shrink-0 border-2 border-brutal-black bg-white px-1.5 py-0.5 text-[10px] font-bold uppercase text-brutal-black hover:bg-neutral-100 disabled:opacity-50 dark:bg-zinc-900 dark:text-white dark:hover:bg-zinc-700"
                >
                  {t('focalTools.cancel')}
                </button>
              </li>
            ))}
          </ul>
        )}
        {cancelError && (
          <p role="alert" className="px-3 pb-3 text-xs text-red-600 dark:text-red-400">
            {t('focalTools.cancelError')}
          </p>
        )}
      </section>

      <section
        aria-label={t('focalTools.tools')}
        className="border-t border-brutal-black/10 dark:border-neutral-700"
      >
        {heading(t('focalTools.tools'))}
        <p className="px-3 pb-2 text-[11px] leading-relaxed text-neutral-500 dark:text-neutral-400">
          {t('focalTools.fixedNote')}
        </p>
        <ul className="flex flex-col gap-1 px-1.5 pb-3">
          {panel.tools.map((tool) => (
            <li
              key={tool.id}
              className="border-2 border-brutal-black bg-neutral-100 dark:bg-zinc-800 px-2.5 py-1.5"
            >
              <p className="text-[11px] font-bold">
                {resolveCatalogText(t, `config.toolCatalog.tools.${tool.id}.name`, tool.name)}
              </p>
              <p className="mt-0.5 text-[10px] leading-snug text-neutral-600 dark:text-neutral-300">
                {resolveCatalogText(
                  t,
                  `config.toolCatalog.tools.${tool.id}.description`,
                  tool.description
                )}
              </p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
