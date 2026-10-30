import React, { useEffect, useRef, useState } from 'react';
import { useChatCoreStore } from '../hooks/useChatStore';
import { useI18n } from '../i18n';
import { useHeartbeatRunning } from '../hooks/useHeartbeatRunning';
import { useHeartbeatToggle } from '../hooks/useHeartbeatToggle';
import { useHeartbeatPulse } from '../hooks/useHeartbeatPulse';
import { useSubAgentStatus } from '../hooks/useSubAgentStatus';
import { useDreamStatus } from '../hooks/useDreamStatus';
import { useEventBus } from '../hooks/useEventBus';
import {
  fetchHeartbeatMd,
  fetchServiceRuntimeStatus,
  saveHeartbeatMd,
  setHeartbeatInterval,
  type ServiceRuntimeStatus,
} from '../lib/api';
import { BrutalOnOff } from './BrutalOnOff';
import { HeartbeatPulse } from './HeartbeatPulse';
import { InformationPopover } from './InformationPopover';
import { isImeComposing } from '../lib/ime';
import { FOCAL_CHAT_ID } from '../lib/focalAgent';
import { LiveRegentIdentity } from './regent/RegentHeader';
import { RegentMark } from './regent/RegentMark';
import { ResolveChatButton } from './chat/ResolveChatButton';
import { forgetRegentReturnUnless, useOpenedFromRegent } from '../lib/regentReturn';
import { hoverText } from '../lib/hoverText';

const SERVICE_STATUS_POLL_MS = 8_000;

const HEARTBEAT_INTERVAL_PRESETS = [5, 15, 30, 60, 120] as const;

const SECTION_LABEL =
  'text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400';
const PILL_BUTTON =
  'px-1.5 py-0.5 border border-brutal-black dark:border-neutral-400 text-[10px] font-bold uppercase tracking-wider transition-colors';
const PILL_BUTTON_IDLE =
  'bg-white text-brutal-black hover:bg-neutral-100 dark:bg-zinc-800 dark:text-white dark:hover:bg-zinc-700';
const PILL_BUTTON_ACTIVE =
  'bg-brutal-black text-white border-brutal-black dark:bg-neutral-200 dark:text-brutal-black';
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
      if (isImeComposing(event)) return;
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
  const pulse = useHeartbeatPulse();
  const chatStatus = useHeartbeatRunning((s) =>
    currentChatId ? s.chatStatus[currentChatId] : undefined
  );
  const { enabled, toggling, toggle: handleToggle } = useHeartbeatToggle();
  const { handleBlur, open, openPopover, rootRef, closePopoverWithDelay } = useStatusHoverPopover();

  // heartbeat.md instructions editor
  const [showText, setShowText] = useState(false);
  const [mdDraft, setMdDraft] = useState('');
  const [mdLoading, setMdLoading] = useState(false);
  const [mdSaving, setMdSaving] = useState(false);
  // Track which chat the current draft was loaded for, so we don't clobber edits.
  const loadedForChatRef = useRef<string | null>(null);

  const intervalMinutes = config?.heartbeat_interval_minutes || 30;

  useEffect(() => {
    if (!open) {
      // Allow the next open to reseed the draft from the latest polled status.
      loadedForChatRef.current = null;
    }
  }, [open]);

  const handleSetInterval = async (mins: number) => {
    if (!currentChatId || mins < 1) return;
    const prevMins = intervalMinutes;
    setConfig((prev) => ({ ...prev, heartbeat_interval_minutes: mins }));
    try {
      await setHeartbeatInterval(mins, currentChatId);
    } catch {
      setConfig((prev) => ({ ...prev, heartbeat_interval_minutes: prevMins }));
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
      .catch(() => {
        if (!cancelled) setMdDraft('');
      })
      .finally(() => {
        if (!cancelled) setMdLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, currentChatId, chatStatus?.heartbeat_instructions]);

  const handleSaveText = async () => {
    if (!currentChatId || mdSaving) return;
    setMdSaving(true);
    try {
      await saveHeartbeatMd(mdDraft, currentChatId);
      setConfig((prev) => ({ ...prev, heartbeat_instructions: mdDraft }));
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

  const { failure, inFlightForChat, text } = pulse;

  // Off is the default; the overview's environment section is where it gets turned on.
  if (!enabled && !open) return null;

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
        <HeartbeatPulse pulse={pulse} lineClassName="hidden md:block" />
        {/* Spelled out only when it needs attention: running, or failing. */}
        <span
          className={`${(failure && enabled) || inFlightForChat ? 'hidden md:inline' : 'sr-only'} text-[10px] font-bold uppercase tracking-wider ${failure && enabled && !inFlightForChat ? 'text-red-600 dark:text-red-400' : ''}`}
          title={enabled ? hoverText(failure) : undefined}
        >
          {text}
        </span>
      </button>

      {open && (
        <InformationPopover role="dialog" className="absolute top-6 right-0 z-50 w-60 space-y-2">
          {/* On/off */}
          <div className="flex items-center justify-between gap-3">
            <span className={SECTION_LABEL}>{t('chatWindow.heartbeatLabel')}</span>
            <BrutalOnOff size="sm" checked={enabled} onChange={handleToggle} disabled={toggling} />
          </div>

          {/* Interval */}
          <div
            className={`border-t border-neutral-100 dark:border-zinc-800 pt-2 ${enabled ? '' : 'opacity-50 pointer-events-none'}`}
          >
            <div className={SECTION_LABEL}>{t('chatWindow.heartbeatInterval')}</div>
            <div className="flex flex-wrap gap-1 mt-1.5">
              {HEARTBEAT_INTERVAL_PRESETS.map((mins) => (
                <button
                  key={mins}
                  type="button"
                  onClick={() => handleSetInterval(mins)}
                  className={`${PILL_BUTTON} min-w-12 text-center ${intervalMinutes === mins ? PILL_BUTTON_ACTIVE : PILL_BUTTON_IDLE}`}
                >
                  {mins >= 60
                    ? t('chatWindow.heartbeatHours', { hours: mins / 60 })
                    : t('chatWindow.heartbeatMinutes', { minutes: mins })}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 mt-1.5">
              <input
                type="number"
                min={1}
                value={intervalMinutes}
                onChange={(e) =>
                  setConfig((prev) => ({
                    ...prev,
                    heartbeat_interval_minutes: parseInt(e.target.value, 10) || 1,
                  }))
                }
                onBlur={(e) => handleSetInterval(parseInt(e.target.value, 10) || 1)}
                className="w-14 bg-white dark:bg-zinc-800 border border-brutal-black dark:border-neutral-400 px-1.5 py-0.5 font-mono text-[11px] focus:outline-none dark:text-white"
              />
              <span className="text-neutral-500 dark:text-neutral-400">
                {t('chatWindow.heartbeatMinutesUnit')}
              </span>
            </div>
          </div>

          {/* heartbeat.md instructions */}
          <div className="border-t border-neutral-100 dark:border-zinc-800 pt-2">
            <button
              type="button"
              onClick={() => setShowText((s) => !s)}
              className={`flex items-center justify-between w-full ${SECTION_LABEL} hover:text-neutral-900 dark:hover:text-neutral-100 transition-colors`}
            >
              <span>{t('chatWindow.heartbeatInstructions')}</span>
              <svg
                className={`w-3 h-3 transition-transform ${showText ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                strokeWidth={3}
              >
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
                      onChange={(e) => setMdDraft(e.target.value)}
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
        </InformationPopover>
      )}
    </div>
  );
}

function SubAgentWidget() {
  const { t } = useI18n();
  const { activeTasks } = useSubAgentStatus();
  if (activeTasks.length === 0) return null;

  return (
    <div
      className="flex items-center gap-1.5 flex-shrink-0 ml-3 brutal-running-mono !shadow-none dark:!shadow-none px-1.5 py-0.5 border-2 border-brutal-black dark:border-white text-brutal-black dark:text-white font-bold"
      title={t('backgroundTasks.running', { count: activeTasks.length })}
    >
      <span className="text-[10px]">🤖</span>
      <span className="hidden md:inline text-[9px] font-bold uppercase tracking-wider">
        {t('backgroundTasks.running', { count: activeTasks.length })}
      </span>
    </div>
  );
}

function DreamWidget({ onOpenMemorySettings }: { onOpenMemorySettings?: () => void }) {
  const { status, loading, error } = useDreamStatus();
  const { memoryChats } = useEventBus();
  const extracting = memoryChats.size > 0;
  const { t } = useI18n();
  const { handleBlur, open, openPopover, rootRef, closePopoverWithDelay } = useStatusHoverPopover();

  if (!extracting && ((loading && !status) || !status?.active)) return null;

  const pending = status?.pending_count ?? 0;
  const failed = !!error || status?.last_result?.advanced === false;
  const running = extracting || !!status?.running;
  // Idle memory is shown in the overview's memory section, not the header.
  if (!running && !failed && pending === 0 && !open) return null;

  const label = extracting
    ? t('backgroundTasks.memoryProcessing')
    : running
      ? status?.phase === 'finalizing'
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
        : 'text-neutral-600 dark:text-neutral-300';

  const title =
    error ||
    (status?.active && status.reason) ||
    (status?.watermark
      ? t('settings.memoryConfig.statusBarWatermark', { watermark: status?.watermark })
      : t('settings.memoryConfig.dreamTitle'));

  return (
    <div
      ref={rootRef}
      className="relative ml-3 flex-shrink-0"
      onBlur={handleBlur}
      onMouseEnter={openPopover}
      onMouseLeave={closePopoverWithDelay}
    >
      <button
        type="button"
        onClick={openPopover}
        onFocus={openPopover}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={label}
        className={`flex items-center gap-1.5 px-1.5 py-0.5 font-bold uppercase tracking-wider ${badgeClass}`}
        title={title}
      >
        <span className="text-[10px]" aria-hidden="true">
          {running ? '◐' : failed ? '!' : '◌'}
        </span>
        <span className="hidden md:inline text-[9px]">{label}</span>
      </button>
      {open && (
        <InformationPopover
          role="dialog"
          aria-label={t('settings.memoryConfig.dreamTitle')}
          className="absolute top-full right-0 z-50 w-64 space-y-2"
        >
          <div className="font-bold" role="status">
            {label}
          </div>
          {status?.active && (
            <div>{t('settings.memoryConfig.statusBarPending', { count: String(pending) })}</div>
          )}
          {status?.active && status.watermark && (
            <div>
              {t('settings.memoryConfig.statusBarWatermark', { watermark: status.watermark })}
            </div>
          )}
          {(error || (status?.active && status.reason)) && (
            <div role={error ? 'alert' : undefined} className="break-words">
              {error || status?.reason}
            </div>
          )}
          {onOpenMemorySettings && (
            <button
              type="button"
              onClick={onOpenMemorySettings}
              className="underline hover:no-underline"
            >
              {t('settings.memoryConfig.openMemorySettings')}
            </button>
          )}
        </InformationPopover>
      )}
    </div>
  );
}

function BackendServiceWidget() {
  const { t } = useI18n();
  const [service, setService] = useState<ServiceRuntimeStatus | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let active = true;

    const refresh = async () => {
      try {
        const next = await fetchServiceRuntimeStatus();
        if (!active) return;
        setService(next);
        setUnavailable(false);
      } catch {
        if (!active) return;
        setUnavailable(true);
      }
    };

    refresh();
    const interval = window.setInterval(refresh, SERVICE_STATUS_POLL_MS);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  const state = unavailable
    ? 'offline'
    : service?.ready
      ? 'online'
      : service
        ? 'starting'
        : 'checking';
  const label =
    state === 'online'
      ? t('status.backgroundOnline')
      : state === 'starting'
        ? t('status.backgroundStarting')
        : state === 'offline'
          ? t('status.backgroundOffline')
          : t('status.backgroundChecking');
  const dotClass =
    state === 'online'
      ? 'bg-brutal-green'
      : state === 'offline'
        ? 'bg-brutal-red'
        : 'bg-brutal-yellow animate-pulse';
  const details =
    service && !unavailable
      ? t('status.backgroundDetails', {
          scheduler: service.schedulerRunning ? t('common.on') : t('common.off'),
          heartbeat: service.heartbeatRunning ? t('common.on') : t('common.off'),
          channels: String(service.channelsConfigured),
        })
      : label;

  return (
    <div
      className="flex min-w-0 items-center gap-2 text-neutral-500 dark:text-neutral-400"
      title={details}
    >
      <span
        className={`h-2.5 w-2.5 flex-shrink-0 border border-brutal-black dark:border-neutral-300 ${dotClass}`}
        aria-hidden="true"
      />
      <span className={state === 'online' ? 'sr-only' : 'hidden truncate lg:inline'}>{label}</span>
    </div>
  );
}

function ActiveChatTitle() {
  const { currentChatId, chats } = useChatCoreStore();
  const activeTitle = currentChatId
    ? chats.find((chat) => chat.id === currentChatId)?.title.trim()
    : null;

  if (!activeTitle) return null;

  return (
    <div
      className="flex h-5 max-w-full min-w-0 items-center gap-2 border border-neutral-400/80 bg-white/70 px-2.5 text-neutral-700 shadow-[2px_2px_0_rgba(0,0,0,0.12)] dark:border-neutral-600 dark:bg-zinc-900/80 dark:text-neutral-200 dark:shadow-[2px_2px_0_rgba(255,255,255,0.08)]"
      title={activeTitle}
    >
      <span
        className="relative flex h-3 w-3 flex-shrink-0 items-center justify-center border border-current/50"
        aria-hidden="true"
      >
        <span className="h-1 w-1 bg-current" />
      </span>
      <span className="truncate text-[11px] font-semibold normal-case tracking-normal" dir="auto">
        {activeTitle}
      </span>
    </div>
  );
}

/**
 * Who the header is about: Regent as a contact, or a chat with its project.
 * Returns null on a new, unsaved chat, where the header keeps the brand title.
 */
export function ConversationIdentity(): React.ReactElement | null {
  const { t } = useI18n();
  const { currentChatId, chats, loadChat } = useChatCoreStore();
  const openedFromRegent = useOpenedFromRegent();
  useEffect(() => {
    forgetRegentReturnUnless(currentChatId);
  }, [currentChatId]);
  if (!currentChatId) return null;
  if (currentChatId === FOCAL_CHAT_ID) return <LiveRegentIdentity />;
  const chat = chats.find((item) => item.id === currentChatId);
  const title = chat?.title?.trim();
  const backToRegent = openedFromRegent === currentChatId && (
    <span className="flex shrink-0 items-center gap-1.5 self-center">
      <button
        type="button"
        onClick={() => void loadChat(FOCAL_CHAT_ID)}
        title={t('chatList.focal.back')}
        aria-label={t('chatList.focal.back')}
        className="regent-back -ml-1 inline-flex items-center gap-1.5 px-1 py-0.5 text-sm font-bold text-neutral-500 transition-colors hover:bg-brutal-yellow hover:text-brutal-black dark:text-neutral-400 dark:hover:text-brutal-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue"
      >
        <RegentMark size={14} />
        <span className="hidden sm:inline">{t('chatList.focal.name')}</span>
      </button>
      <span aria-hidden="true" className="text-sm text-neutral-300 dark:text-zinc-600">
        /
      </span>
    </span>
  );
  if (!title) return backToRegent || null;
  return (
    <div className="flex min-w-0 items-baseline gap-2">
      {backToRegent}
      <span
        className="truncate text-sm font-extrabold text-brutal-black dark:text-white"
        dir="auto"
        title={title}
      >
        {title}
      </span>
      {chat?.projectName && (
        <span className="hidden shrink-0 truncate font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 sm:inline dark:text-neutral-400">
          {chat.projectName}
        </span>
      )}
      {openedFromRegent === currentChatId && <ResolveChatButton chatId={currentChatId} />}
    </div>
  );
}

interface StatusBarProps {
  onOpenMemorySettings?: () => void;
  showActiveChatTitle?: boolean;
  /** Render just the status marks, to sit inside the app header. */
  inline?: boolean;
}

export const StatusBar: React.FC<StatusBarProps> = ({
  onOpenMemorySettings,
  showActiveChatTitle = false,
  inline = false,
}) => {
  if (inline) {
    return (
      <div className="hidden sm:flex min-w-0 items-center font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
        <BackendServiceWidget />
        <DreamWidget onOpenMemorySettings={onOpenMemorySettings} />
        <HeartbeatWidget />
      </div>
    );
  }
  return (
    <div
      className={`
      w-full h-8 flex items-center px-3 md:px-5
      border-b-3 border-brutal-black
      font-mono text-[10px] md:text-xs font-bold uppercase tracking-wider
      transition-colors duration-200
      bg-neutral-200 dark:bg-zinc-800 text-neutral-500 dark:text-neutral-400
    `}
    >
      {/* Left: service followed by the selected conversation. */}
      <div className="flex min-w-0 flex-1 items-center gap-4 pr-4">
        <div className="flex min-w-0 flex-shrink-0 items-center gap-2.5">
          <BackendServiceWidget />
        </div>

        <div className="flex min-w-0 flex-1 justify-start overflow-hidden">
          {showActiveChatTitle && <ActiveChatTitle />}
        </div>
      </div>

      {/* Right: context usage + sub-agent indicator + heartbeat */}
      <div className="flex flex-shrink-0 items-center justify-end">
        <SubAgentWidget />
        <DreamWidget onOpenMemorySettings={onOpenMemorySettings} />
        <HeartbeatWidget />
      </div>
    </div>
  );
};
