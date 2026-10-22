import React, { useEffect, useState } from 'react';
import { CheckIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { refreshChatStates, useChatStates } from '../../hooks/useChatStates';
import {
  canResolve,
  fetchChatState,
  setChatResolved,
  type ChatStateRow,
} from '../../lib/chatStates';

/**
 * Resolve the open chat, or reopen it, from its header. Shown only for chats
 * the board tracks, so Regent, sub-agents and chat apps never carry it. A chat
 * too quiet for the board is looked up on its own.
 */
export function ResolveChatButton({ chatId }: { chatId: string }): React.ReactElement | null {
  const { t } = useI18n();
  const { states } = useChatStates();
  const boardRow = states?.chats.find((item) => item.chatId === chatId) ?? null;
  const [ownRow, setOwnRow] = useState<ChatStateRow | null>(null);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    if (boardRow) return;
    let current = true;
    setOwnRow(null);
    fetchChatState(chatId)
      .then((row) => current && setOwnRow(row))
      .catch(() => {});
    return () => {
      current = false;
    };
    // The board refreshing is what can change a quiet chat's state.
  }, [chatId, boardRow, states]);

  const row = boardRow ?? (ownRow?.chatId === chatId ? ownRow : null);
  if (!row) return null;
  const resolved = row.state === 'resolved';
  const blocked = !resolved && !canResolve(row);
  const label = failed
    ? t('chatBoard.failed')
    : blocked
      ? t('chatBoard.answerFirst')
      : resolved
        ? t('chatBoard.reopen')
        : t('chatBoard.resolve');
  return (
    <button
      type="button"
      disabled={saving || blocked}
      aria-pressed={resolved}
      aria-label={label}
      title={label}
      onClick={() => {
        setSaving(true);
        setFailed(false);
        setChatResolved(chatId, !resolved)
          .then(() => refreshChatStates())
          .catch(() => setFailed(true))
          .finally(() => setSaving(false));
      }}
      className={`inline-flex h-6 w-6 shrink-0 items-center justify-center self-center border-2 border-brutal-black transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue disabled:opacity-60 ${failed ? 'bg-brutal-red text-white' : resolved ? 'bg-brutal-green text-brutal-black' : 'bg-white text-neutral-500 hover:bg-brutal-green hover:text-brutal-black disabled:hover:bg-white dark:bg-zinc-700 dark:text-neutral-300'}`}
    >
      <CheckIcon className="h-3.5 w-3.5 stroke-[3]" aria-hidden="true" />
    </button>
  );
}
