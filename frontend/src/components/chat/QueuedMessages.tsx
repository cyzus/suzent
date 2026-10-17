/**
 * QueuedMessages — messages waiting for the running turn to end.
 *
 * Enter redirects the agent mid-turn; Cmd/Ctrl+Enter holds the message here
 * instead, and each one is sent as its own turn in order. Any of them can
 * still be sent now as a redirect, or dropped.
 */
import React from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import type { FileMentionSelection } from '../ChatInputPanel';

export interface QueuedMessage {
  id: string;
  text: string;
  fileMentions: FileMentionSelection[];
  files: File[];
}

interface QueuedMessagesProps {
  items: QueuedMessage[];
  onSteer: (id: string) => void;
  onRemove: (id: string) => void;
  onClear: () => void;
}

const ACTION_CLASS =
  'shrink-0 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-neutral-500 dark:text-neutral-400 hover:text-brutal-black dark:hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue';

export const QueuedMessages: React.FC<QueuedMessagesProps> = ({
  items,
  onSteer,
  onRemove,
  onClear,
}) => {
  const { t } = useI18n();

  return (
    <div className="px-1 flex flex-col gap-1" role="list" aria-label={t('chatInput.queuedLabel')}>
      <div className="flex items-center justify-between gap-2 px-1">
        <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          {t('chatInput.queuedCount', { count: items.length })}
        </span>
        {items.length > 1 && (
          <button type="button" onClick={onClear} className={ACTION_CLASS}>
            {t('chatInput.cancelAllQueued')}
          </button>
        )}
      </div>
      {items.map((item) => (
        <div
          key={item.id}
          role="listitem"
          className="flex items-start gap-2 min-w-0 px-2 py-1 bg-white dark:bg-zinc-800 border-2 border-dashed border-neutral-300 dark:border-zinc-600"
        >
          <span className="shrink-0 font-mono text-xs leading-5 text-neutral-400" aria-hidden>
            &rarr;
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-sm leading-5 text-neutral-700 dark:text-neutral-200 whitespace-pre-wrap break-words line-clamp-3">
              {item.text}
            </div>
            {item.files.length > 0 && (
              <div className="text-[10px] font-mono text-neutral-500 dark:text-neutral-400 truncate">
                {item.files.map((file) => file.name).join(', ')}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => onSteer(item.id)}
            className="shrink-0 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide border-2 border-brutal-black bg-brutal-yellow hover:bg-yellow-300 text-brutal-black focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
            title={t('chatInput.steerQueuedHint')}
          >
            {t('chatInput.steerQueued')}
          </button>
          <button
            type="button"
            onClick={() => onRemove(item.id)}
            className="shrink-0 p-0.5 text-neutral-400 hover:text-brutal-black dark:hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
            title={t('chatInput.removeQueued')}
            aria-label={t('chatInput.removeQueued')}
          >
            <XMarkIcon className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  );
};
