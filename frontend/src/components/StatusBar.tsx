import React, { useEffect, useRef, useState } from 'react';
import { useStatusStore, StatusType } from '../hooks/useStatusStore';
import { useChatCoreStore, useChatStore } from '../hooks/useChatStore';
import { useI18n } from '../i18n';
import { useHeartbeatRunning } from '../hooks/useHeartbeatRunning';
import { useSubAgentStatus } from '../hooks/useSubAgentStatus';
import { useContextUsageStore, type ContextUsage } from '../hooks/useContextUsageStore';
import { useCompact } from '../hooks/useCompact';
import { useDreamStatus } from '../hooks/useDreamStatus';
import { enableHeartbeat, disableHeartbeat, setHeartbeatInterval, fetchHeartbeatMd, saveHeartbeatMd } from '../lib/api';
import { BrutalOnOff } from './BrutalOnOff';

const getStatusStyles = (type: StatusType) => {
  switch (type) {
    case 'error':
      return 'bg-brutal-red text-white';
    case 'success':
      return 'bg-brutal-green text-brutal-black';
    case 'warning':
      return 'bg-brutal-yellow text-brutal-black';
    case 'info':
      return 'bg-brutal-blue text-white';
    case 'idle':
    default:
      return 'bg-neutral-200 dark:bg-zinc-800 text-neutral-500 dark:text-neutral-400';
  }
};

const getStatusIcon = (type: StatusType) => {
  switch (type) {
    case 'error': return '!';
    case 'success': return '✓';
    case 'warning': return '⚠';
    case 'info': return 'i';
    case 'idle': return '•';
    default: return '';
  }
};

const HEARTBEAT_HEALTHY_WINDOW_MS = 90_000; // 90s — runner ticks every 1 min

function formatRelativeTime(iso: string | null): string | null {
  if (!iso) return null;
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return null;
  const deltaMs = Date.now() - ts;
  if (deltaMs < 0) return null;
  const deltaSec = Math.floor(deltaMs / 1000);
  if (deltaSec < 10) return 'just now';
  if (deltaSec < 60) return `${deltaSec}s ago`;
  const deltaMin = Math.floor(deltaSec / 60);
  if (deltaMin < 60) return `${deltaMin}m ago`;
  const deltaHours = Math.floor(deltaMin / 60);
  if (deltaHours < 24) return `${deltaHours}h ago`;
  return `${Math.floor(deltaHours / 24)}d ago`;
}

const HEARTBEAT_INTERVAL_PRESETS = [5, 15, 30, 60, 120] as const;

const SECTION_LABEL = 'text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400';
const PILL_BUTTON = 'px-1.5 py-0.5 border border-brutal-black dark:border-neutral-400 text-[10px] font-bold uppercase tracking-wider transition-colors';
const PILL_BUTTON_IDLE = 'bg-white text-brutal-black hover:bg-neutral-100 dark:bg-zinc-800 dark:text-white dark:hover:bg-zinc-700';
const PILL_BUTTON_ACTIVE = 'bg-brutal-black text-white border-brutal-black dark:bg-neutral-200 dark:text-brutal-black';
const POPOVER_PANEL = 'absolute top-6 right-0 rounded border-2 border-brutal-black dark:border-neutral-500 bg-white dark:bg-zinc-900 shadow-lg text-[11px] text-neutral-700 dark:text-neutral-300 p-2.5 z-50';

function useStatusHoverPopover() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const closeTimerRef = useRef<number | null>(null);

  const clearCloseTimer = () => {
    if (closeTimerRef.current != null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };

  const openPopover = () => {
    clearCloseTimer();
    setOpen(true);
  };

  const closePopover = () => {
    clearCloseTimer();
    setOpen(false);
  };

  const closePopoverWithDelay = () => {
    clearCloseTimer();
    closeTimerRef.current = window.setTimeout(() => {
      setOpen(false);
      closeTimerRef.current = null;
    }, 150);
  };

  const handleBlur = (event: React.FocusEvent<HTMLDivElement>) => {
    const nextTarget = event.relatedTarget;
    if (nextTarget instanceof Node && rootRef.current?.contains(nextTarget)) {
      return;
    }
    closePopoverWithDelay();
  };

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        closePopover();
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closePopover();
      }
    };

    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  useEffect(() => {
    return () => clearCloseTimer();
  }, []);

  return {
    handleBlur,
    open,
    openPopover,
    rootRef,
    closePopoverWithDelay,
  };
}

function HeartbeatWidget() {
  const { currentChatId, config, setConfig } = useChatCoreStore();
  const { t } = useI18n();
  const { inFlight, inFlightChatId, lastPingAt, statusError } = useHeartbeatRunning();
  const chatStatus = useHeartbeatRunning(s => currentChatId ? s.chatStatus[currentChatId] : undefined);
  const [toggling, setToggling] = useState(false);
  const { handleBlur, open, openPopover, rootRef, closePopoverWithDelay } = useStatusHoverPopover();

  // heartbeat.md instructions editor
  const [showText, setShowText] = useState(false);
  const [mdDraft, setMdDraft] = useState('');
  const [mdLoading, setMdLoading] = useState(false);
  const [mdSaving, setMdSaving] = useState(false);
  // Track which chat the current draft was loaded for, so we don't clobber edits.
  const loadedForChatRef = useRef<string | null>(null);

  const enabled = !!(currentChatId && config?.heartbeat_enabled);
  const inFlightForChat = enabled && inFlight && inFlightChatId === currentChatId;
  const intervalMinutes = config?.heartbeat_interval_minutes || 30;

  useEffect(() => {
    if (!open) {
      // Allow the next open to reseed the draft from the latest polled status.
      loadedForChatRef.current = null;
    }
  }, [open]);

  const handleToggle = async () => {
    if (!currentChatId || toggling) return;
    const newEnabled = !enabled;
    setToggling(true);
    setConfig(prev => ({ ...prev, heartbeat_enabled: newEnabled }));
    try {
      if (newEnabled) {
        await enableHeartbeat(currentChatId);
      } else {
        await disableHeartbeat(currentChatId);
      }
    } catch {
      setConfig(prev => ({ ...prev, heartbeat_enabled: !newEnabled }));
    } finally {
      setToggling(false);
    }
  };

  const handleSetInterval = async (mins: number) => {
    if (!currentChatId || mins < 1) return;
    const prevMins = intervalMinutes;
    setConfig(prev => ({ ...prev, heartbeat_interval_minutes: mins }));
    try {
      await setHeartbeatInterval(mins, currentChatId);
    } catch {
      setConfig(prev => ({ ...prev, heartbeat_interval_minutes: prevMins }));
    }
  };

  // Seed the editor when the popover opens for a chat. The instructions are
  // already polled into the heartbeat store (chatStatus.heartbeat_instructions),
  // so prefer that; fall back to a direct fetch if the poll hasn't arrived yet.
  useEffect(() => {
    if (!open || !currentChatId) return;
    // Don't reseed the same chat (preserves in-progress edits across re-renders).
    if (loadedForChatRef.current === currentChatId) return;

    const polled = chatStatus?.heartbeat_instructions;
    if (polled != null) {
      setMdDraft(polled);
      loadedForChatRef.current = currentChatId;
      if (polled.trim()) setShowText(true);
      return;
    }

    let cancelled = false;
    setMdLoading(true);
    fetchHeartbeatMd(currentChatId)
      .then(({ content }) => {
        if (cancelled) return;
        setMdDraft(content || '');
        loadedForChatRef.current = currentChatId;
        if (content?.trim()) setShowText(true);
      })
      .catch(() => { if (!cancelled) setMdDraft(''); })
      .finally(() => { if (!cancelled) setMdLoading(false); });
    return () => { cancelled = true; };
  }, [open, currentChatId, chatStatus?.heartbeat_instructions]);

  const handleSaveText = async () => {
    if (!currentChatId || mdSaving) return;
    setMdSaving(true);
    try {
      await saveHeartbeatMd(mdDraft, currentChatId);
      setConfig(prev => ({ ...prev, heartbeat_instructions: mdDraft }));
      // Keep the polled store in sync so the editor doesn't revert on reopen.
      const prevStatus = chatStatus;
      if (prevStatus) {
        useHeartbeatRunning.getState().setChatStatus(currentChatId, {
          ...prevStatus,
          heartbeat_instructions: mdDraft,
        });
      }
    } catch {
      // best effort
    } finally {
      setMdSaving(false);
    }
  };

  const lastPingMs = lastPingAt ? new Date(lastPingAt).getTime() : 0;
  const fresh = enabled && lastPingMs > 0 && (Date.now() - lastPingMs) <= HEARTBEAT_HEALTHY_WINDOW_MS;
  const relative = formatRelativeTime(lastPingAt);

  type EkgMode = 'fast' | 'active' | 'slow' | 'flat';
  let ekg: EkgMode;
  let heartClass: string;
  let text: string;

  if (!enabled) {
    ekg = 'flat'; heartClass = ''; text = t('chatWindow.heartbeatOff');
  } else if (inFlightForChat) {
    ekg = 'fast'; heartClass = 'pixel-heart-beat-fast'; text = t('chatWindow.heartbeatRunning');
  } else if (statusError) {
    ekg = 'slow'; heartClass = ''; text = statusError.slice(0, 32);
  } else if (fresh) {
    ekg = 'active'; heartClass = 'pixel-heart-beat'; text = t('chatWindow.heartbeatHealthy');
  } else if (relative) {
    ekg = 'slow'; heartClass = ''; text = t('chatWindow.heartbeatLastRun', { time: relative });
  } else {
    ekg = 'slow'; heartClass = ''; text = t('chatWindow.heartbeatEnabled');
  }

  const ekgClass = ekg === 'fast'
    ? 'ekg-active-wave [animation-duration:1.5s]'
    : ekg === 'active'
    ? 'ekg-active-wave [animation-duration:3s]'
    : ekg === 'slow'
    ? 'ekg-active-wave [animation-duration:6s] opacity-50'
    : 'ekg-flatline';
  const ekgPath = ekg !== 'flat'
    ? "M 0 25 L 10 25 L 14 30 L 22 5 L 28 45 L 34 25 L 100 25"
    : "M 0 25 L 100 25";

  return (
    <div
      ref={rootRef}
      className="relative flex-shrink-0 ml-3"
      onBlur={handleBlur}
      onMouseEnter={currentChatId ? openPopover : undefined}
      onMouseLeave={closePopoverWithDelay}
    >
      <button
        type="button"
        onFocus={currentChatId ? openPopover : undefined}
        disabled={!currentChatId}
        className={`flex items-center gap-1 transition-opacity hover:opacity-80 disabled:cursor-default ${!enabled ? 'opacity-40' : ''}`}
        title={t('chatWindow.heartbeatConfigure')}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <svg
          className={`w-3 h-3 flex-shrink-0 ${heartClass}`}
          viewBox="0 0 24 24"
          fill="currentColor"
          aria-hidden="true"
        >
          <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
        </svg>
        <div className="hidden md:block w-8 h-3 flex-shrink-0">
          <svg viewBox="0 0 100 50" preserveAspectRatio="none" className="w-full h-full">
            <path
              className={ekgClass}
              pathLength="100"
              fill="none"
              stroke="currentColor"
              strokeWidth="6"
              d={ekgPath}
            />
          </svg>
        </div>
        <span className="hidden md:inline text-[10px] font-bold uppercase tracking-wider">{text}</span>
      </button>

      {open && (
        <div
          role="dialog"
          className={`${POPOVER_PANEL} w-60 space-y-2`}
        >
          {/* On/off */}
          <div className="flex items-center justify-between gap-3">
            <span className={SECTION_LABEL}>{t('chatWindow.heartbeatLabel')}</span>
            <BrutalOnOff size="sm" checked={enabled} onChange={handleToggle} disabled={toggling} />
          </div>

          {/* Interval */}
          <div className={`border-t border-neutral-100 dark:border-zinc-800 pt-2 ${enabled ? '' : 'opacity-50 pointer-events-none'}`}>
            <div className={SECTION_LABEL}>{t('chatWindow.heartbeatInterval')}</div>
            <div className="flex flex-wrap gap-1 mt-1.5">
              {HEARTBEAT_INTERVAL_PRESETS.map(mins => (
                <button
                  key={mins}
                  type="button"
                  onClick={() => handleSetInterval(mins)}
                  className={`${PILL_BUTTON} min-w-12 text-center ${intervalMinutes === mins ? PILL_BUTTON_ACTIVE : PILL_BUTTON_IDLE}`}
                >
                  {mins >= 60 ? t('chatWindow.heartbeatHours', { hours: mins / 60 }) : t('chatWindow.heartbeatMinutes', { minutes: mins })}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 mt-1.5">
              <input
                type="number"
                min={1}
                value={intervalMinutes}
                onChange={e => setConfig(prev => ({ ...prev, heartbeat_interval_minutes: parseInt(e.target.value, 10) || 1 }))}
                onBlur={e => handleSetInterval(parseInt(e.target.value, 10) || 1)}
                className="w-14 bg-white dark:bg-zinc-800 border border-brutal-black dark:border-neutral-400 px-1.5 py-0.5 font-mono text-[11px] focus:outline-none dark:text-white"
              />
              <span className="text-neutral-500 dark:text-neutral-400">{t('chatWindow.heartbeatMinutesUnit')}</span>
            </div>
          </div>

          {/* heartbeat.md instructions */}
          <div className="border-t border-neutral-100 dark:border-zinc-800 pt-2">
            <button
              type="button"
              onClick={() => setShowText(s => !s)}
              className={`flex items-center justify-between w-full ${SECTION_LABEL} hover:text-neutral-900 dark:hover:text-neutral-100 transition-colors`}
            >
              <span>{t('chatWindow.heartbeatInstructions')}</span>
              <svg className={`w-3 h-3 transition-transform ${showText ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {showText && (
              <div className="mt-1.5">
                {mdLoading ? (
                  <div className="text-neutral-400 py-1.5">{t('common.loading')}</div>
                ) : (
                  <>
                    <textarea
                      value={mdDraft}
                      onChange={e => setMdDraft(e.target.value)}
                      rows={5}
                      placeholder={t('chatWindow.heartbeatInstructionsPlaceholder')}
                      className="w-full bg-white dark:bg-zinc-800 border border-brutal-black dark:border-neutral-400 px-1.5 py-1 font-mono text-[11px] leading-relaxed resize-y focus:outline-none dark:text-white dark:placeholder-neutral-500"
                    />
                    <div className="flex justify-end mt-1.5">
                      <button
                        type="button"
                        onClick={handleSaveText}
                        disabled={mdSaving}
                        className={`${PILL_BUTTON} bg-brutal-green text-brutal-black border-brutal-black disabled:opacity-40 disabled:cursor-not-allowed`}
                      >
                        {mdSaving ? t('common.saving') : t('common.save')}
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ContextWidget() {
  const { usage } = useContextUsageStore();
  const { backendConfig } = useChatCoreStore();

  if (!usage || !backendConfig?.maxContextTokens) return null;

  return (
    <ContextWidgetBody usage={usage} limit={backendConfig.maxContextTokens} />
  );
}

function ContextWidgetBody({ usage, limit }: { usage: ContextUsage; limit: number; }) {
  const { compactNotice, setCompactNotice, clearCompactNotice, setUsageForChat } = useContextUsageStore();
  const { currentChatId, isStreaming } = useChatStore();
  const { setStatus } = useStatusStore();
  const { compact, progress } = useCompact();
  const { handleBlur, open, openPopover, rootRef, closePopoverWithDelay } = useStatusHoverPopover();
  const hintTimerRef = useRef<number | null>(null);

  const contextTokens = usage.context_tokens ?? usage.total_tokens ?? 0;
  const pct = Math.min(100, (contextTokens / limit) * 100);
  const barColor = pct >= 80 ? 'bg-brutal-red' : pct >= 60 ? 'bg-brutal-yellow' : 'bg-neutral-400 dark:bg-neutral-500';

  const inputTokens = usage.input_tokens ?? 0;
  const outputTokens = usage.output_tokens ?? 0;
  const cacheRead = usage.cache_read_tokens ?? 0;
  const cacheWrite = usage.cache_write_tokens ?? 0;
  const details = usage.details ?? {};
  const extraDetails = Object.entries(details).filter(([, v]) => Number(v) > 0) as Array<[string, number]>;
  const compactRecommended = pct >= 80;
  const compacting = ['loading', 'analyzing', 'summarizing', 'saving'].includes(progress.stage);

  const fmt = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`;
  const clearHintTimer = () => {
    if (hintTimerRef.current != null) {
      window.clearTimeout(hintTimerRef.current);
      hintTimerRef.current = null;
    }
  };
  useEffect(() => {
    return () => clearHintTimer();
  }, []);
  useEffect(() => {
    if (!compactNotice) return;
    clearHintTimer();
    hintTimerRef.current = window.setTimeout(() => {
      clearCompactNotice();
      hintTimerRef.current = null;
    }, 10_000);
  }, [compactNotice, clearCompactNotice]);
  const compactStageLabel: Record<string, string> = {
    loading: 'Compacting...',
    analyzing: 'Compaction analyzing...',
    summarizing: 'Compaction summarizing...',
    saving: 'Compaction saving...',
  };

  const handleManualCompact = async () => {
    if (!currentChatId || isStreaming || compacting) return;

    setStatus('Compacting context...', 'info', 5000);

    const result = await compact(currentChatId);
    if (result.error) {
      setStatus(`Compaction failed: ${result.error}`, 'error', 6000);
      return;
    }

    if (result.skipped) {
      setStatus(result.reason || 'Compaction skipped', 'warning', 5000);
      return;
    }

    // Provider-reported usage isn't touched by /compact, so the panel stays stale
    // until the next turn. Apply the freshly recomputed post-compaction totals now.
    if (result.usage && currentChatId) {
      setUsageForChat(currentChatId, result.usage);
    }

    setStatus('Context compacted', 'success', 5000);
  };

  const canManualCompact = !!currentChatId && !isStreaming && !compacting;
  const compactLabel = compacting ? (compactStageLabel[progress.stage] || 'Compacting...') : compactNotice;

  return (
    <div
      ref={rootRef}
      className="relative flex-shrink-0 ml-3"
      onBlur={handleBlur}
      onMouseEnter={openPopover}
      onMouseLeave={closePopoverWithDelay}
    >
      <button
        type="button"
        onFocus={openPopover}
        className="flex items-center gap-1.5 transition-opacity hover:opacity-80"
        title="Context usage"
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <div className="w-12 h-1.5 rounded-full bg-neutral-300 dark:bg-zinc-600 overflow-hidden">
          <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${pct}%` }} />
        </div>
        <span className="hidden md:inline text-[10px] font-bold uppercase tracking-wider">
          {fmt(contextTokens)}
        </span>
        {compactRecommended && !compacting && (
          <span className="hidden md:inline text-[9px] font-bold uppercase tracking-wider text-brutal-red">
            Compact?
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          className={`${POPOVER_PANEL} w-56 space-y-1.5 font-mono normal-case tracking-normal font-normal`}
        >
          <div className="flex items-center justify-between mb-1">
            <div className="font-bold text-neutral-900 dark:text-neutral-100 uppercase tracking-wider text-[10px]">Context Window</div>
            <button
              type="button"
              onClick={handleManualCompact}
              disabled={!canManualCompact}
              className="px-1.5 py-0.5 border border-brutal-black dark:border-neutral-400 text-[9px] font-bold uppercase tracking-wider bg-white dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed"
              title={canManualCompact ? 'Compact context now' : 'Compaction unavailable while streaming'}
            >
              {compacting ? '...' : 'Compact'}
            </button>
          </div>
          {compactLabel && (
            <div className={`px-1.5 py-1 border rounded text-[10px] font-bold ${progress.stage === 'error' ? 'border-brutal-red text-brutal-red' : 'border-neutral-300 dark:border-zinc-700 text-neutral-600 dark:text-neutral-300'}`}>
              {compactLabel}
            </div>
          )}

          {/* Total bar */}
          <div className="space-y-0.5">
            <div className="flex justify-between">
              <span className="text-neutral-500 dark:text-neutral-400">Total</span>
              <span>{fmt(contextTokens)} / {fmt(limit)}</span>
            </div>
            <div className="w-full h-1 rounded-full bg-neutral-100 dark:bg-zinc-800">
              <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${pct}%` }} />
            </div>
          </div>

          {/* Input / Output */}
          <div className="border-t border-neutral-100 dark:border-zinc-800 pt-1.5 space-y-1">
            <div className="flex justify-between">
              <span>Input</span>
              <span>{fmt(inputTokens)}</span>
            </div>
            <div className="flex justify-between">
              <span>Output</span>
              <span>{fmt(outputTokens)}</span>
            </div>
          </div>

          {/* Cache */}
          {(cacheRead > 0 || cacheWrite > 0) && (
            <div className="border-t border-neutral-100 dark:border-zinc-800 pt-1.5 space-y-1">
              <div className="text-neutral-400 dark:text-neutral-500 text-[10px] uppercase tracking-wide mb-0.5">Cache</div>
              {cacheRead > 0 && (
                <div className="flex justify-between">
                  <span>Cache Read</span>
                  <span className="text-green-600 dark:text-green-400">{fmt(cacheRead)}</span>
                </div>
              )}
              {cacheWrite > 0 && (
                <div className="flex justify-between">
                  <span>Cache Write</span>
                  <span className="text-blue-500 dark:text-blue-400">{fmt(cacheWrite)}</span>
                </div>
              )}
            </div>
          )}

          {/* Extra details from model */}
          {extraDetails.length > 0 && (
            <div className="border-t border-neutral-100 dark:border-zinc-800 pt-1.5 space-y-1">
              <div className="text-neutral-400 dark:text-neutral-500 text-[10px] uppercase tracking-wide mb-0.5">Details</div>
              {extraDetails.map(([key, val]) => (
                <div key={key} className="flex justify-between">
                  <span className="text-neutral-500 dark:text-neutral-400 truncate mr-2">{key.replace(/_/g, ' ')}</span>
                  <span className="flex-shrink-0">{fmt(Number(val))}</span>
                </div>
              ))}
            </div>
          )}

          {usage.requests > 1 && (
            <div className="border-t border-neutral-100 dark:border-zinc-800 pt-1.5">
              <div className="flex justify-between text-neutral-500 dark:text-neutral-400">
                <span>API Requests</span>
                <span>{usage.requests}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SubAgentWidget() {
  const { activeTasks } = useSubAgentStatus();
  if (activeTasks.length === 0) return null;

  return (
    <div className="flex items-center gap-1.5 flex-shrink-0 ml-3 brutal-running-mono !shadow-none dark:!shadow-none px-1.5 py-0.5 border-2 border-brutal-black dark:border-white text-brutal-black dark:text-white font-bold" title={`${activeTasks.length} sub-agent(s) running`}>
      <span className="text-[10px]">🤖</span>
      <span className="hidden md:inline text-[9px] font-bold uppercase tracking-wider">
        {activeTasks.length} sub-agent{activeTasks.length > 1 ? 's' : ''} running
      </span>
    </div>
  );
}

function DreamWidget({ onOpenMemorySettings }: { onOpenMemorySettings?: () => void }) {
  const { status, loading, error } = useDreamStatus();
  const { t } = useI18n();

  if (loading && !status) return null;
  if (!status?.active) return null;

  const pending = status.pending_count ?? 0;
  const failed = !!error || status.last_result?.advanced === false;
  const running = status.running;

  const label = running
    ? status.phase === 'finalizing'
      ? t('settings.memoryConfig.dreamStatus.finalizing')
      : t('settings.memoryConfig.dreamStatus.running')
    : failed
    ? t('settings.memoryConfig.statusBarNeedsReview')
    : pending > 0
    ? t('settings.memoryConfig.statusBarPending', { count: String(pending) })
    : t('settings.memoryConfig.statusBarIdle');

  const badgeClass = running
    ? 'bg-brutal-blue text-white animate-pulse border-2 border-brutal-black dark:border-neutral-500'
    : failed
    ? 'bg-brutal-red text-white border-2 border-brutal-black dark:border-neutral-500'
    : pending > 0
    ? 'bg-brutal-yellow text-brutal-black border-2 border-brutal-black dark:border-neutral-500'
    : 'bg-neutral-200 dark:bg-zinc-700 text-neutral-600 dark:text-neutral-300';

  const title = error || status.reason || (status.watermark
    ? t('settings.memoryConfig.statusBarWatermark', { watermark: status.watermark })
    : t('settings.memoryConfig.dreamTitle'));

  return (
    <button
      type="button"
      onClick={onOpenMemorySettings}
      className={`flex items-center gap-1.5 flex-shrink-0 ml-3 px-1.5 py-0.5 font-bold uppercase tracking-wider ${badgeClass}`}
      title={title}
    >
      <span className="text-[10px]" aria-hidden="true">{running ? '◐' : failed ? '!' : '◌'}</span>
      <span className="hidden md:inline text-[9px]">{label}</span>
    </button>
  );
}

interface StatusBarProps {
  onOpenMemorySettings?: () => void;
}

export const StatusBar: React.FC<StatusBarProps> = ({ onOpenMemorySettings }) => {
  const { message, type } = useStatusStore();

  return (
    <div className={`
      w-full h-7 flex items-center px-4 md:px-6
      border-b-3 border-brutal-black
      font-mono text-[10px] md:text-xs font-bold uppercase tracking-wider
      transition-colors duration-200
      ${getStatusStyles(type)}
    `}>
      {/* Left: transient toast area */}
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <span className="flex-shrink-0 w-4 text-center">{getStatusIcon(type)}</span>
        <span className="truncate">{message}</span>
        <span className="hidden md:inline opacity-50 flex-shrink-0">
          {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </span>
      </div>
      {/* Right: context usage + sub-agent indicator + heartbeat */}
      <ContextWidget />
      <SubAgentWidget />
      <DreamWidget onOpenMemorySettings={onOpenMemorySettings} />
      <HeartbeatWidget />
    </div>
  );
};
