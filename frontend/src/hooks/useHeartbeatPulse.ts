import { useChatCoreStore } from './useChatStore';
import { useHeartbeatRunning } from './useHeartbeatRunning';
import { useI18n } from '../i18n';

const HEARTBEAT_HEALTHY_WINDOW_MS = 90_000; // 90s — runner ticks every 1 min

export type EkgMode = 'fast' | 'active' | 'slow' | 'flat';

export interface HeartbeatPulse {
  enabled: boolean;
  inFlightForChat: boolean;
  failure: string | null;
  ekg: EkgMode;
  heartClass: string;
  text: string;
}

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

/** The current chat's heartbeat as the pixel heart and EKG line show it. */
export function useHeartbeatPulse(): HeartbeatPulse {
  const { currentChatId, config } = useChatCoreStore();
  const { t } = useI18n();
  const { inFlight, inFlightChatId, lastPingAt, statusError } = useHeartbeatRunning();
  const chatStatus = useHeartbeatRunning((s) =>
    currentChatId ? s.chatStatus[currentChatId] : undefined
  );
  const enabled = !!(currentChatId && config?.heartbeat_enabled);
  const inFlightForChat = enabled && inFlight && inFlightChatId === currentChatId;

  // This chat's own last failure, kept until a check-in succeeds again. The
  // runner-wide error named whichever chat failed last and vanished on restart.
  const failure = currentChatId ? (chatStatus?.last_error ?? null) : statusError;
  const lastPingMs = lastPingAt ? new Date(lastPingAt).getTime() : 0;
  const fresh = enabled && lastPingMs > 0 && Date.now() - lastPingMs <= HEARTBEAT_HEALTHY_WINDOW_MS;
  const relative = formatRelativeTime(lastPingAt);

  const base = { enabled, inFlightForChat, failure };
  if (!enabled) return { ...base, ekg: 'flat', heartClass: '', text: t('chatWindow.heartbeatOff') };
  if (inFlightForChat)
    return {
      ...base,
      ekg: 'fast',
      heartClass: 'pixel-heart-beat-fast',
      text: t('chatWindow.heartbeatRunning'),
    };
  if (failure)
    return { ...base, ekg: 'slow', heartClass: '', text: t('chatWindow.heartbeatFailed') };
  if (fresh)
    return {
      ...base,
      ekg: 'active',
      heartClass: 'pixel-heart-beat',
      text: t('chatWindow.heartbeatHealthy'),
    };
  if (relative)
    return {
      ...base,
      ekg: 'slow',
      heartClass: '',
      text: t('chatWindow.heartbeatLastRun', { time: relative }),
    };
  return { ...base, ekg: 'slow', heartClass: '', text: t('chatWindow.heartbeatEnabled') };
}
