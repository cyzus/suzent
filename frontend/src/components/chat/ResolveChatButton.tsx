import React, { useState } from 'react';
import { CheckIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { refreshChatStates, useChatStates } from '../../hooks/useChatStates';
import { setChatResolved } from '../../lib/chatStates';

/**
 * Resolve the open chat, or reopen it, from its header. Shown only for chats
 * the board tracks, so Regent, sub-agents and chat apps never carry it.
 */
export function ResolveChatButton({ chatId }: { chatId: string }): React.ReactElement | null {
  const { t } = useI18n();
  const { states } = useChatStates();
  const [saving, setSaving] = useState(false);
  const row = states?.chats.find((item) => item.chatId === chatId);
  if (!row) return null;
  const resolved = row.state === 'resolved';
  const label = resolved ? t('chatBoard.reopen') : t('chatBoard.resolve');
  return (
    <button
      type="button"
      disabled={saving}
      aria-pressed={resolved}
      aria-label={label}
      title={label}
      onClick={() => {
        setSaving(true);
        setChatResolved(chatId, !resolved)
          .then(() => refreshChatStates())
          .catch(() => {})
          .finally(() => setSaving(false));
      }}
      className={`inline-flex h-6 w-6 shrink-0 items-center justify-center self-center border-2 border-brutal-black transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue disabled:opacity-60 ${resolved ? 'bg-brutal-green text-brutal-black' : 'bg-white text-neutral-500 hover:bg-brutal-green hover:text-brutal-black dark:bg-zinc-700 dark:text-neutral-300'}`}
    >
      <CheckIcon className="h-3.5 w-3.5 stroke-[3]" aria-hidden="true" />
    </button>
  );
}
