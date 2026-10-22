import React, { useCallback, useState } from 'react';
import { useI18n } from '../../i18n';
import { useChatStates, refreshChatStates } from '../../hooks/useChatStates';
import {
  CHAT_STATES,
  chatProjects,
  setChatResolved,
  type ChatState,
  type ChatStateRow,
} from '../../lib/chatStates';
import { relativeTime } from '../../lib/chatUtils';
import { BrutalSelect } from '../BrutalSelect';
import { BoardRowMenu, type BoardRowMenuItem } from './BoardRowMenu';

const ALL_PROJECTS = '__all__';

const DOT: Record<ChatState, string> = {
  waiting: 'bg-brutal-yellow',
  running: 'bg-brutal-blue animate-brutal-blink',
  idle: 'bg-white dark:bg-zinc-700',
  resolved: 'bg-brutal-green',
};

const BADGE: Record<ChatState, string> = {
  waiting: 'bg-brutal-yellow text-brutal-black',
  running: 'bg-brutal-blue text-white',
  idle: 'bg-white text-brutal-black',
  resolved: 'bg-brutal-green text-brutal-black',
};

interface ChatStatusBoardProps {
  projectFilter: string;
  onProjectFilter: (projectId: string) => void;
  onOpenChat?: (chatId: string) => void;
}

/**
 * Regent's board: every recent project chat by where it stands for the user.
 * Tasks stay inside each chat; the board only says who has the next move.
 */
export function ChatStatusBoard({
  projectFilter,
  onProjectFilter,
  onOpenChat,
}: ChatStatusBoardProps): React.ReactElement {
  const { t } = useI18n();
  const { states, failed } = useChatStates();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({ resolved: true });
  const [menu, setMenu] = useState<{
    anchor: { x: number; y: number };
    title: string;
    items: BoardRowMenuItem[];
  } | null>(null);
  const [actionFailed, setActionFailed] = useState(false);
  const closeMenu = useCallback(() => setMenu(null), []);

  const allRows = states?.chats ?? [];
  const projects = chatProjects(allRows);
  // A remembered project with no chats left on the board falls back to all.
  const filter = projects.some((project) => project.id === projectFilter)
    ? projectFilter
    : ALL_PROJECTS;
  const rows =
    filter === ALL_PROJECTS ? allRows : allRows.filter((row) => row.projectId === filter);
  const waiting = rows.filter((row) => row.state === 'waiting').length;

  const resolve = (row: ChatStateRow, resolved: boolean): void => {
    setActionFailed(false);
    setChatResolved(row.chatId, resolved)
      .then(() => refreshChatStates())
      .catch(() => setActionFailed(true));
  };

  const openMenu = (event: React.MouseEvent, row: ChatStateRow): void => {
    event.preventDefault();
    // A context-menu key press reports no pointer position; anchor to the row.
    const rect = event.currentTarget.getBoundingClientRect();
    const anchor =
      event.clientX || event.clientY
        ? { x: event.clientX, y: event.clientY }
        : { x: rect.left + 16, y: rect.top + 16 };
    const items: BoardRowMenuItem[] = [];
    if (onOpenChat) {
      items.push({
        key: 'open',
        label: t('chatBoard.menu.open'),
        onSelect: () => onOpenChat(row.chatId),
      });
    }
    items.push(
      row.state === 'resolved'
        ? { key: 'reopen', label: t('chatBoard.reopen'), onSelect: () => resolve(row, false) }
        : { key: 'resolve', label: t('chatBoard.resolve'), onSelect: () => resolve(row, true) }
    );
    setMenu({ anchor, title: row.title, items });
  };

  const renderRow = (row: ChatStateRow): React.ReactNode => {
    const reason = row.state === 'waiting' ? (row.waitingReason ?? row.summary) : row.summary;
    const time = relativeTime(row.lastActiveAt);
    return (
      <section
        key={row.chatId}
        aria-label={row.title}
        onContextMenu={(event) => openMenu(event, row)}
        className="flex items-start gap-2.5 border-b border-neutral-200 px-3 py-2.5 last:border-b-0 dark:border-zinc-700"
      >
        <span
          aria-hidden="true"
          className={`mt-1.5 h-2 w-2 shrink-0 border border-brutal-black ${DOT[row.state]}`}
        />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-baseline gap-2">
            {onOpenChat ? (
              <button
                type="button"
                className="min-w-0 flex-1 truncate text-left text-[13px] font-bold leading-snug hover:underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue"
                title={`${row.title} · ${t('chatBoard.menu.open')}`}
                onClick={() => onOpenChat(row.chatId)}
              >
                {row.title}
              </button>
            ) : (
              <h2 className="min-w-0 flex-1 truncate text-[13px] font-bold leading-snug">
                {row.title}
              </h2>
            )}
            {time && (
              <span className="shrink-0 font-mono text-[10px] tabular-nums text-neutral-400 dark:text-zinc-500">
                {time}
              </span>
            )}
          </div>
          <p className="mt-0.5 flex min-w-0 items-center gap-1.5 font-mono text-[10px] text-neutral-500 dark:text-zinc-400">
            {row.projectName && <span className="min-w-0 truncate">{row.projectName}</span>}
            {row.projectName && row.waitingKind && <span aria-hidden="true">·</span>}
            {row.waitingKind && (
              <span className="shrink-0 font-bold uppercase text-brutal-black dark:text-white">
                {t(`chatBoard.reason.${row.waitingKind}`)}
              </span>
            )}
          </p>
          {reason && (
            <p
              className={`mt-1.5 line-clamp-2 text-xs leading-snug ${row.state === 'waiting' ? 'border-l-2 border-brutal-yellow pl-2 text-brutal-black dark:text-white' : 'text-neutral-600 dark:text-zinc-300'}`}
            >
              {reason}
            </p>
          )}
        </div>
      </section>
    );
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-white text-brutal-black dark:bg-zinc-900 dark:text-white">
      <header className="shrink-0 space-y-2 border-b-2 border-brutal-black bg-white px-4 py-3 dark:bg-zinc-800">
        {projects.length > 1 && (
          <BrutalSelect
            label={t('taskFlow.projectFilter')}
            value={filter}
            onChange={onProjectFilter}
            options={[
              { value: ALL_PROJECTS, label: t('taskFlow.allProjects') },
              ...projects.map((project) => ({ value: project.id, label: project.label })),
            ]}
            className="w-full"
          />
        )}
        {states && (
          <p className="font-mono text-[11px] text-neutral-500 dark:text-zinc-400">
            {waiting > 0
              ? t('chatBoard.waitingSummary', { count: waiting })
              : t('chatBoard.allClear')}
          </p>
        )}
      </header>
      <div className="task-scroll min-h-0 flex-1 space-y-5 overflow-auto p-4 [scrollbar-gutter:stable] md:p-6">
        {actionFailed && (
          <p
            role="alert"
            className="border-2 border-brutal-black bg-brutal-red px-3 py-2 text-xs font-bold text-white"
          >
            {t('chatBoard.failed')}
          </p>
        )}
        {failed && !states ? (
          <div role="alert" className="space-y-3 text-sm">
            <p>{t('chatBoard.loadError')}</p>
            <button onClick={() => void refreshChatStates()} className="underline">
              {t('taskFlow.retry')}
            </button>
          </div>
        ) : !states ? (
          <p role="status" className="text-sm text-neutral-500">
            {t('taskFlow.loading')}
          </p>
        ) : rows.length === 0 ? (
          <p className="py-12 text-center text-sm text-neutral-600 dark:text-zinc-300">
            {t('chatBoard.empty')}
          </p>
        ) : (
          CHAT_STATES.map((state) => {
            const group = rows.filter((row) => row.state === state);
            if (group.length === 0) return null;
            return (
              <details
                key={state}
                open={!collapsed[state]}
                onToggle={(event) => {
                  const closed = !event.currentTarget.open;
                  setCollapsed((previous) =>
                    previous[state] === closed ? previous : { ...previous, [state]: closed }
                  );
                }}
                className="group/chat-state"
              >
                <summary className="flex cursor-pointer select-none list-none items-center gap-2 px-1 pb-1.5 font-mono text-[11px] font-bold uppercase tracking-wider text-brutal-black hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue dark:text-white [&::-webkit-details-marker]:hidden">
                  <span
                    aria-hidden="true"
                    className="inline-block text-neutral-400 transition-transform group-open/chat-state:rotate-90"
                  >
                    ▸
                  </span>
                  {t(`chatBoard.groups.${state}`)}
                  <span
                    className={`ml-auto min-w-5 border border-brutal-black px-1 text-center ${BADGE[state]}`}
                  >
                    {group.length}
                  </span>
                </summary>
                <div className="border-2 border-brutal-black bg-white shadow-brutal-sm dark:bg-zinc-800">
                  {group.map(renderRow)}
                </div>
              </details>
            );
          })
        )}
      </div>
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
