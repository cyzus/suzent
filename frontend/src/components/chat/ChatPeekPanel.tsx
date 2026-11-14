import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowsPointingOutIcon, ChevronRightIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { getApiBase } from '../../lib/api';
import { mapServerMessages } from '../../lib/serverMessages';
import { useEventBus } from '../../hooks/useEventBus';
import { useI18n } from '../../i18n';
import type { ChatConfig, ConfigOptions, FileAttachment, Message } from '../../types/api';
import type { VoiceSession } from '../../hooks/useVoiceSession';
import { PeekChatComposer } from './PeekChatComposer';
import type { QueuedMessage } from './QueuedMessages';
import { PanelResizeHandle } from '../PanelResizeHandle';

const WIDTH_KEY = 'suzent.chatPeekWidth';
const MIN_WIDTH_PX = 360;
const DEFAULT_WIDTH_PX = 520;
const POLL_MS = 2000;

function storedWidth(): number {
  try {
    const value = Number(localStorage.getItem(WIDTH_KEY));
    return value >= MIN_WIDTH_PX ? value : DEFAULT_WIDTH_PX;
  } catch {
    return DEFAULT_WIDTH_PX;
  }
}

interface ChatPeekPanelProps {
  chatId: string;
  /** What the breadcrumb leads with: the chat the panel was opened from. */
  parentLabel: string;
  /** Title from the chat list, shown until the chat itself loads. */
  knownTitle?: string;
  maxWidthPx: number;
  onClose: () => void;
  onExpand: (chatId: string) => void;
  renderMessages: (chatId: string, messages: Message[]) => React.ReactNode;
  backendConfig: ConfigOptions | null;
  voice: VoiceSession;
  onImageClick?: (src: string) => void;
  /** This chat's queue, shared with its own composer so it carries over on expand. */
  queue: QueuedMessage[];
  onQueueChange: (update: (queue: QueuedMessage[]) => QueuedMessage[]) => void;
}

/**
 * A chat opened beside the one you are in, so following a hand-off does not
 * mean leaving it. Its composer writes to that chat (redirecting it while it
 * runs); the expand button switches to the chat itself.
 */
export const ChatPeekPanel: React.FC<ChatPeekPanelProps> = ({
  chatId,
  parentLabel,
  knownTitle,
  maxWidthPx,
  onClose,
  onExpand,
  renderMessages,
  backendConfig,
  voice,
  onImageClick,
  queue,
  onQueueChange,
}) => {
  const { t } = useI18n();
  const { activeStreams, snapshotReady } = useEventBus();
  const running = snapshotReady && activeStreams.has(chatId);
  const [messages, setMessages] = useState<Message[] | null>(null);
  const [title, setTitle] = useState<string | undefined>(knownTitle);
  const [failed, setFailed] = useState(false);
  const [config, setConfig] = useState<Partial<ChatConfig> | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [width, setWidth] = useState(storedWidth);
  const panelRef = useRef<HTMLElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  const currentChat = useRef(chatId);
  currentChat.current = chatId;

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${getApiBase()}/chats/${encodeURIComponent(chatId)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const chat = await res.json();
      // A slow read for the previous chat must not land in this one.
      if (currentChat.current !== chatId) return;
      const mapped = mapServerMessages(chat.messages ?? []);
      setMessages(mapped);
      setPending((text) => (text !== null && lastUserText(mapped) === text ? null : text));
      if (chat.title) setTitle(chat.title);
      // The composer seeds from the first read; later reads must not reset its picks.
      setConfig(
        (previous) =>
          previous ?? (chat.config && typeof chat.config === 'object' ? chat.config : {})
      );
      setFailed(false);
    } catch {
      if (currentChat.current === chatId) setFailed(true);
    }
  }, [chatId]);

  useEffect(() => {
    setMessages(null);
    setFailed(false);
    setPending(null);
    setConfig(null);
    setTitle(knownTitle);
    stickToBottom.current = true;
    // The known title only seeds a newly opened chat; a list refresh must not reset it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatId]);

  // Follow a run while it works; a settled chat needs one read.
  useEffect(() => {
    void load();
    if (!running) return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [running, load]);

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages, pending]);

  // A running chat is redirected, as its own composer would; an idle one starts a turn.
  const send = async (
    text: string,
    sendConfig: ChatConfig,
    files?: FileAttachment[]
  ): Promise<boolean> => {
    // A send while the chat runs redirects it, as Enter does in its own composer.
    const res = await fetch(`${getApiBase()}/chat/${running ? 'steer-send' : 'send'}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chat_id: chatId,
        message: text,
        config: sendConfig,
        ...(files?.length ? { files } : {}),
        client_run_token: crypto.randomUUID(),
      }),
    }).catch(() => null);
    if (!res?.ok) return false;
    stickToBottom.current = true;
    setPending(text);
    void load();
    return true;
  };

  const shown =
    messages && pending !== null
      ? [...messages, { role: 'user' as const, content: pending }]
      : messages;

  const changeWidth = (next: number): void => {
    setWidth(next);
    try {
      localStorage.setItem(WIDTH_KEY, String(Math.round(next)));
    } catch {
      /* the width is a convenience */
    }
  };
  const shownWidth = Math.min(width, maxWidthPx);
  const iconButton =
    'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue dark:text-neutral-500 dark:hover:bg-zinc-800 dark:hover:text-neutral-200';

  return (
    <aside
      ref={panelRef}
      data-testid="chat-peek-panel"
      aria-label={title ?? chatId}
      className="chat-peek-panel relative flex h-full min-h-0 shrink-0 flex-col border-l-3 border-brutal-black bg-neutral-50 dark:bg-zinc-900"
      style={{ width: shownWidth }}
    >
      <PanelResizeHandle
        panelRef={panelRef}
        side="right"
        width={shownWidth}
        minWidth={MIN_WIDTH_PX}
        maxWidth={maxWidthPx}
        defaultWidth={DEFAULT_WIDTH_PX}
        onWidthChange={changeWidth}
      />
      <header className="flex h-11 shrink-0 items-center gap-1 border-b border-neutral-200 pl-4 pr-2 dark:border-zinc-800">
        <div className="flex min-w-0 flex-1 items-center gap-1 text-[13px]">
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 text-neutral-400 hover:text-neutral-700 dark:text-neutral-500 dark:hover:text-neutral-200"
          >
            {parentLabel}
          </button>
          <ChevronRightIcon
            className="h-3 w-3 shrink-0 text-neutral-300 dark:text-zinc-600"
            aria-hidden="true"
          />
          <span
            className="min-w-0 truncate text-neutral-700 dark:text-neutral-200"
            title={title ?? chatId}
          >
            {title ?? chatId}
          </span>
          {running && (
            <span
              className="ml-1 h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-brutal-yellow"
              title={t('chatMessage.dispatch.peekRunning')}
              aria-label={t('chatMessage.dispatch.peekRunning')}
            />
          )}
        </div>
        <button
          type="button"
          className={iconButton}
          onClick={() => onExpand(chatId)}
          title={t('chatMessage.dispatch.peekExpand')}
          aria-label={t('chatMessage.dispatch.peekExpand')}
        >
          <ArrowsPointingOutIcon className="h-4 w-4" aria-hidden="true" />
        </button>
        <button
          type="button"
          className={iconButton}
          onClick={onClose}
          title={t('chatMessage.dispatch.peekClose')}
          aria-label={t('chatMessage.dispatch.peekClose')}
        >
          <XMarkIcon className="h-4 w-4" aria-hidden="true" />
        </button>
      </header>
      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
        }}
        className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-4 pb-6 pt-3 scrollbar-thin"
      >
        {messages === null ? (
          <p className="pt-6 text-center text-xs text-neutral-400 dark:text-neutral-500">
            {failed ? t('chatMessage.dispatch.peekError') : t('chatMessage.dispatch.peekLoading')}
          </p>
        ) : (
          renderMessages(chatId, shown ?? [])
        )}
      </div>
      {config && (
        <PeekChatComposer
          key={chatId}
          chatId={chatId}
          savedConfig={config}
          backendConfig={backendConfig}
          voice={voice}
          running={running}
          onSend={send}
          onImageClick={onImageClick}
          queue={queue}
          onQueueChange={onQueueChange}
        />
      )}
    </aside>
  );
};

function lastUserText(messages: Message[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'user') return (messages[i].content ?? '').trim();
  }
  return null;
}
