import React, { useEffect, useRef, useState } from 'react';
import { useStatusStore, StatusType } from '../hooks/useStatusStore';
import { useChatCoreStore, useChatStore } from '../hooks/useChatStore';
import { useI18n } from '../i18n';
import { useHeartbeatRunning } from '../hooks/useHeartbeatRunning';
import { useSubAgentStatus } from '../hooks/useSubAgentStatus';
import { useContextUsageStore, type ContextUsage } from '../hooks/useContextUsageStore';
import { useCompact } from '../hooks/useCompact';
import { subscribeToBusPayloads } from '../hooks/useEventBus';

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

function HeartbeatWidget() {
  const { currentChatId, config } = useChatCoreStore();
  const { t } = useI18n();
  const { inFlight, inFlightChatId, loopRunning, lastPingAt, statusError } = useHeartbeatRunning();

  const enabled = !!(currentChatId && config?.heartbeat_enabled);
  const inFlightForChat = enabled && inFlight && inFlightChatId === currentChatId;

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
    <div className={`flex items-center gap-1 flex-shrink-0 ml-3 ${!enabled ? 'opacity-40' : ''}`} title={loopRunning ? undefined : 'Heartbeat loop stopped'}>
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
  const { compactNotice, setCompactNotice, clearCompactNotice } = useContextUsageStore();
  const { currentChatId, isStreaming } = useChatStore();
  const { setStatus } = useStatusStore();
  const { compact, progress } = useCompact();
  const [hovered, setHovered] = useState(false);
  const hintTimerRef = useRef<number | null>(null);
  const hoverCloseTimerRef = useRef<number | null>(null);

  const total = usage.total_tokens ?? 0;
  const pct = Math.min(100, (total / limit) * 100);
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
  const clearHoverCloseTimer = () => {
    if (hoverCloseTimerRef.current != null) {
      window.clearTimeout(hoverCloseTimerRef.current);
      hoverCloseTimerRef.current = null;
    }
  };
  const openHover = () => {
    clearHoverCloseTimer();
    setHovered(true);
  };
  const closeHoverWithDelay = () => {
    clearHoverCloseTimer();
    hoverCloseTimerRef.current = window.setTimeout(() => {
      setHovered(false);
      hoverCloseTimerRef.current = null;
    }, 150);
  };
  const pushCompactHint = (msg: string) => {
    setCompactNotice(msg);
  };
  useEffect(() => {
    return () => clearHintTimer();
  }, []);
  useEffect(() => {
    return () => clearHoverCloseTimer();
  }, []);
  useEffect(() => {
    if (!compactNotice) return;
    clearHintTimer();
    hintTimerRef.current = window.setTimeout(() => {
      clearCompactNotice();
      hintTimerRef.current = null;
    }, 10_000);
  }, [compactNotice, clearCompactNotice]);
  useEffect(() => {
    if (!currentChatId) return;

    const unsub = subscribeToBusPayloads((payload) => {
      if (!payload || payload.event !== 'auto_compaction') return;
      if (payload.chat_id !== currentChatId) return;

      if (payload.stage === 'start') {
        setCompactNotice('Auto compacting...');
        return;
      }

      if (payload.stage === 'skipped') {
        setCompactNotice('Auto compaction skipped');
        return;
      }

      const before = Number(payload.tokens_before ?? 0);
      const after = Number(payload.tokens_after ?? 0);
      const fmtCompact = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`);
      const label = before > 0 && after >= 0
        ? `Auto compacted ${fmtCompact(before)} -> ${fmtCompact(after)}`
        : 'Auto compacted context';

      setCompactNotice(label);
    });

    return unsub;
  }, [currentChatId, setCompactNotice]);

  const compactStageLabel: Record<string, string> = {
    loading: 'Compacting...',
    analyzing: 'Compaction analyzing...',
    summarizing: 'Compaction summarizing...',
    saving: 'Compaction saving...',
  };

  const handleManualCompact = async () => {
    if (!currentChatId || isStreaming || compacting) return;

    setCompactNotice('Compacting...');
    setStatus('Compacting context...', 'info', 5000);

    const result = await compact(currentChatId);
    if (result.error) {
      pushCompactHint('Compaction failed');
      setStatus(`Compaction failed: ${result.error}`, 'error', 6000);
      return;
    }

    if (result.skipped) {
      pushCompactHint('Compaction skipped');
      setStatus(result.reason || 'Compaction skipped', 'warning', 5000);
      return;
    }

    pushCompactHint('Context compacted');
    setStatus('Context compacted', 'success', 5000);
  };

  const canManualCompact = !!currentChatId && !isStreaming && !compacting;
  const compactLabel = compacting ? (compactStageLabel[progress.stage] || 'Compacting...') : compactNotice;

  return (
    <div
      className="relative flex items-center gap-1.5 flex-shrink-0 ml-3 cursor-default"
      onMouseEnter={openHover}
      onMouseLeave={closeHoverWithDelay}
    >
      <div className="w-12 h-1.5 rounded-full bg-neutral-300 dark:bg-zinc-600 overflow-hidden">
        <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="hidden md:inline text-[10px] font-bold uppercase tracking-wider">
        {fmt(total)}
      </span>
      {compactRecommended && !compacting && (
        <span className="hidden md:inline text-[9px] font-bold uppercase tracking-wider text-brutal-red" title="Context usage is high, consider compacting.">
          Compact?
        </span>
      )}

      {hovered && (
        <div
          className="absolute top-6 right-0 w-56 rounded border-2 border-brutal-black dark:border-neutral-500 bg-white dark:bg-zinc-900 shadow-lg font-mono text-[11px] text-neutral-700 dark:text-neutral-300 p-2.5 space-y-1.5 z-50 normal-case tracking-normal font-normal"
          onMouseEnter={openHover}
          onMouseLeave={closeHoverWithDelay}
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
              <span>{fmt(total)} / {fmt(limit)}</span>
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

export const StatusBar: React.FC = () => {
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
      <HeartbeatWidget />
    </div>
  );
};
