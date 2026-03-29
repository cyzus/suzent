import React from 'react';
import { useStatusStore, StatusType } from '../hooks/useStatusStore';
import { useChatCoreStore } from '../hooks/useChatStore';
import { useI18n } from '../i18n';
import { useHeartbeatRunning } from '../hooks/useHeartbeatRunning';

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
      {/* Right: persistent heartbeat widget */}
      <HeartbeatWidget />
    </div>
  );
};
