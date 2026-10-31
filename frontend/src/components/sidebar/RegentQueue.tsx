import React, { useCallback, useState } from 'react';
import { ChevronDownIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { resolveChat, useChatStates } from '../../hooks/useChatStates';
import { canResolve, type ChatStateRow } from '../../lib/chatStates';
import { BoardRowMenu, type BoardRowMenuItem } from './BoardRowMenu';

const WAITING_PREVIEW = 4;
const RUNNING_PREVIEW = 3;

interface RegentQueueProps {
  onOpenChat: (chatId: string) => void;
}

/**
 * What Regent is watching, in the sidebar while its chat is open: the chats
 * waiting on the user first, then the ones still running.
 */
export function RegentQueue({ onOpenChat }: RegentQueueProps): React.ReactElement | null {
  const { states } = useChatStates();
  if (!states) return null;
  return <RegentQueueView rows={states.chats} onOpenChat={onOpenChat} />;
}

interface RegentQueueViewProps extends RegentQueueProps {
  rows: ChatStateRow[];
}

export function RegentQueueView({ rows, onOpenChat }: RegentQueueViewProps): React.ReactElement {
  const { t } = useI18n();
  const [showAllWaiting, setShowAllWaiting] = useState(false);
  const [menu, setMenu] = useState<{
    anchor: { x: number; y: number };
    title: string;
    items: BoardRowMenuItem[];
  } | null>(null);
  const closeMenu = useCallback(() => setMenu(null), []);
  // An open question or approval blocks the chat outright, so it comes first.
  const blocking = (row: ChatStateRow): number =>
    row.waitingKind === 'question' || row.waitingKind === 'approval' ? 0 : 1;
  const waiting = rows
    .filter((row) => row.state === 'waiting')
    .sort((left, right) => blocking(left) - blocking(right));
  const running = rows.filter((row) => row.state === 'running');
  const visibleWaiting = showAllWaiting ? waiting : waiting.slice(0, WAITING_PREVIEW);

  // The same menu as on Regent's board, so a row means the same thing in both places.
  const openMenu = (event: React.MouseEvent, row: ChatStateRow): void => {
    event.preventDefault();
    // A context-menu key press reports no pointer position; anchor to the row.
    const rect = event.currentTarget.getBoundingClientRect();
    const anchor =
      event.clientX || event.clientY
        ? { x: event.clientX, y: event.clientY }
        : { x: rect.left + 16, y: rect.top + 16 };
    const items: BoardRowMenuItem[] = [
      { key: 'open', label: t('chatBoard.menu.open'), onSelect: () => onOpenChat(row.chatId) },
    ];
    if (canResolve(row)) {
      items.push({
        key: 'resolve',
        label: t('chatBoard.resolve'),
        onSelect: () => void resolveChat(row.chatId, true).catch(() => {}),
      });
    }
    setMenu({ anchor, title: row.title, items });
  };

  const renderRow = (row: ChatStateRow): React.ReactNode => {
    const reason = row.state === 'waiting' ? (row.waitingReason ?? row.summary) : row.summary;
    const dot =
      row.state === 'running'
        ? 'bg-brutal-blue animate-pulse'
        : blocking(row) === 0
          ? 'bg-brutal-red'
          : 'bg-brutal-yellow';
    return (
      <li key={row.chatId}>
        <button
          type="button"
          onClick={() => onOpenChat(row.chatId)}
          onContextMenu={(event) => openMenu(event, row)}
          title={reason ?? row.title}
          className="flex w-full items-start gap-2 px-2 py-1.5 text-left transition-colors hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue dark:hover:bg-zinc-700"
        >
          <span
            aria-hidden="true"
            className={`mt-1.5 h-2 w-2 shrink-0 border border-brutal-black ${dot}`}
          />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-medium text-brutal-black dark:text-white">
              {row.title}
            </span>
            <span className="mt-0.5 block truncate text-[10px] text-neutral-500 dark:text-neutral-400">
              {[
                row.projectName,
                row.waitingKind ? t(`chatBoard.reason.${row.waitingKind}`) : reason,
              ]
                .filter(Boolean)
                .join(' · ')}
            </span>
          </span>
        </button>
      </li>
    );
  };

  const heading = (label: string, count: number): React.ReactNode => (
    <h2 className="flex items-center justify-between px-2 pt-2 pb-1 font-mono text-[10px] font-extrabold uppercase tracking-[0.14em] text-neutral-400 dark:text-neutral-500">
      <span>{label}</span>
      <span className="tabular-nums">{count}</span>
    </h2>
  );

  if (waiting.length === 0 && running.length === 0) {
    return (
      <p className="px-3 py-3 text-xs text-neutral-500 dark:text-neutral-400">
        {t('chatBoard.allClear')}
      </p>
    );
  }

  return (
    <div className="px-1.5 pb-1">
      {waiting.length > 0 && (
        <section>
          {heading(t('chatBoard.groups.waiting'), waiting.length)}
          <ul>{visibleWaiting.map(renderRow)}</ul>
          {waiting.length > WAITING_PREVIEW && (
            <button
              type="button"
              aria-expanded={showAllWaiting}
              onClick={() => setShowAllWaiting((value) => !value)}
              className="flex w-full items-center gap-1 px-2 py-1 text-[10px] font-bold text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white"
            >
              {showAllWaiting
                ? t('chatList.regentQueue.showLess')
                : t('chatList.regentQueue.showMore', {
                    count: waiting.length - WAITING_PREVIEW,
                  })}
              <ChevronDownIcon
                className={`h-3 w-3 transition-transform ${showAllWaiting ? 'rotate-180' : ''}`}
                aria-hidden="true"
              />
            </button>
          )}
        </section>
      )}
      {running.length > 0 && (
        <section>
          {heading(t('chatBoard.groups.running'), running.length)}
          <ul>{running.slice(0, RUNNING_PREVIEW).map(renderRow)}</ul>
        </section>
      )}
      {menu && (
        <BoardRowMenu
          anchor={menu.anchor}
          title={menu.title}
          items={menu.items}
          onClose={closeMenu}
        />
      )}
    </div>
  );
}
