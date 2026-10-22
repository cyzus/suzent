import React from 'react';
import { useI18n } from '../../i18n';
import { focalRequestText } from '../../lib/focalAgent';
import { SystemTriggeredMessage } from './StatusMessages';
import { UserMessage } from './UserMessage';

/**
 * A message the running turn took in partway through, shown where it landed.
 *
 * Another agent's message reaches a busy chat this way rather than as a new
 * turn. Regent relays the user's requests, so its messages read as the user's.
 */
export function IncomingMessage({
  text,
  chatId,
}: {
  text: string;
  chatId?: string;
}): React.ReactElement | null {
  const { t } = useI18n();
  const request = focalRequestText(text);
  if (request) {
    return (
      <div className="my-3 flex w-full flex-col items-end">
        <span className="mb-1 pr-1 text-[10px] font-medium text-neutral-400 dark:text-neutral-500">
          {t('chatMessage.sentByRegent')}
        </span>
        <UserMessage message={{ role: 'user', content: request }} chatId={chatId} />
      </div>
    );
  }
  if (!text.trim()) return null;
  return <SystemTriggeredMessage message={{ role: 'system_triggered', content: text }} />;
}
