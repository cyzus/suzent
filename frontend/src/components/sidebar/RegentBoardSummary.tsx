import { useChatStates } from '../../hooks/useChatStates';
import { useI18n } from '../../i18n';
import { CHAT_STATES, type ChatState, type ChatStateRow } from '../../lib/chatStates';
import { OverviewList } from '../chat/SidebarOverview';

const DOT: Record<ChatState, string> = {
  waiting: 'bg-brutal-yellow',
  running: 'bg-brutal-blue',
  idle: 'bg-neutral-300 dark:bg-zinc-600',
  resolved: 'bg-brutal-green',
};

/** Regent's board in one line: how many chats stand where. */
export function RegentBoardCounts(): JSX.Element | null {
  const { t } = useI18n();
  const rows = useChatStates().states?.chats ?? [];
  if (rows.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-neutral-500 dark:text-neutral-400">
      {CHAT_STATES.map((state) => {
        const count = rows.filter((row) => row.state === state).length;
        if (count === 0) return null;
        return (
          <span key={state} className="flex items-center gap-1.5 tabular-nums">
            <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${DOT[state]}`} />
            {t(`chatBoard.groups.${state}`)} {count}
          </span>
        );
      })}
    </div>
  );
}

/** The chats that need the user or are moving; the full board has the rest. */
export function RegentBoardList({
  onOpenChat,
}: {
  onOpenChat: (chatId: string) => void;
}): JSX.Element {
  const { t } = useI18n();
  const rows = useChatStates().states?.chats ?? [];
  const live = [
    ...rows.filter((row) => row.state === 'waiting'),
    ...rows.filter((row) => row.state === 'running'),
  ];
  return (
    <OverviewList<ChatStateRow>
      items={live}
      empty={t('chatBoard.allClear')}
      getKey={(row) => row.chatId}
      renderMarker={(row) => <span className={`h-1.5 w-1.5 rounded-full ${DOT[row.state]}`} />}
      renderLabel={(row) => row.title}
      onSelect={(row) => onOpenChat(row.chatId)}
    />
  );
}

export function RegentWaitingCount(): JSX.Element | null {
  const rows = useChatStates().states?.chats ?? [];
  const waiting = rows.filter((row) => row.state === 'waiting').length;
  return waiting > 0 ? <>{waiting}</> : null;
}
