import React, { useRef, useState } from 'react';
import { ArrowsPointingOutIcon, ChevronRightIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { useEventBus } from '../../hooks/useEventBus';
import { useI18n } from '../../i18n';
import { PanelResizeHandle } from '../PanelResizeHandle';
import { SidebarToggleIcon } from '../SidebarToggleIcon';

const WIDTH_KEY = 'suzent.chatPeekWidth';
const MIN_WIDTH_PX = 400;
const DEFAULT_WIDTH_PX = 560;

function storedWidth(): number {
  try {
    const value = Number(localStorage.getItem(WIDTH_KEY));
    return value >= MIN_WIDTH_PX ? value : DEFAULT_WIDTH_PX;
  } catch {
    return DEFAULT_WIDTH_PX;
  }
}

/** What the chat inside the panel needs to lay out its own side panel. */
export interface PeekSidebarProps {
  isRightSidebarOpen: boolean;
  onRightSidebarToggle: (isOpen: boolean) => void;
  viewportWidthPx: number;
}

interface ChatPeekPanelProps {
  chatId: string;
  /** What the breadcrumb leads with: the chat the panel was opened from. */
  parentLabel: string;
  title?: string;
  maxWidthPx: number;
  onClose: () => void;
  onExpand: (chatId: string) => void;
  /** The chat itself: a full chat window scoped to `chatId`. */
  renderChat: (chatId: string, sidebar: PeekSidebarProps) => React.ReactNode;
}

/**
 * A chat opened beside the one you are in, so following a hand-off does not
 * mean leaving it. The panel is only the frame -- breadcrumb, expand, close,
 * width; inside is the chat's own window, whose side panel opens over this
 * column.
 */
export const ChatPeekPanel: React.FC<ChatPeekPanelProps> = ({
  chatId,
  parentLabel,
  title,
  maxWidthPx,
  onClose,
  onExpand,
  renderChat,
}) => {
  const { t } = useI18n();
  const { activeStreams, snapshotReady } = useEventBus();
  const running = snapshotReady && activeStreams.has(chatId);
  const [width, setWidth] = useState(storedWidth);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const panelRef = useRef<HTMLElement>(null);

  const changeWidth = (next: number): void => {
    setWidth(next);
    try {
      localStorage.setItem(WIDTH_KEY, String(Math.round(next)));
    } catch {
      /* the width is a convenience */
    }
  };
  const shownWidth = Math.min(width, maxWidthPx);
  const label = title ?? chatId;
  const iconButton =
    'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue dark:text-neutral-500 dark:hover:bg-zinc-800 dark:hover:text-neutral-200';

  return (
    <aside
      ref={panelRef}
      data-testid="chat-peek-panel"
      aria-label={label}
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
          <span className="min-w-0 truncate text-neutral-700 dark:text-neutral-200" title={label}>
            {label}
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
          onClick={() => setSidebarOpen((open) => !open)}
          title={t('chatMessage.dispatch.peekSidebar')}
          aria-label={t('chatMessage.dispatch.peekSidebar')}
          aria-pressed={sidebarOpen}
        >
          <SidebarToggleIcon side="right" open={sidebarOpen} className="h-4 w-4" />
        </button>
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
      <div className="relative flex min-h-0 flex-1">
        {renderChat(chatId, {
          isRightSidebarOpen: sidebarOpen,
          onRightSidebarToggle: setSidebarOpen,
          viewportWidthPx: shownWidth,
        })}
      </div>
    </aside>
  );
};
