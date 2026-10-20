import React from 'react';
import { RobotAvatar } from './RobotAvatar';
import { useI18n } from '../../i18n';
import type { KanbanData } from '../../hooks/useGoalTasks';
import { buildSessions, sessionGroupKey } from '../../lib/sessionGroups';

interface FocalBriefingProps {
  kanban: KanbanData | null;
  onOpenChat: (chatId: string) => void;
}

export function FocalBriefing({ kanban, onOpenChat }: FocalBriefingProps): React.ReactElement {
  const { t } = useI18n();
  const waiting = kanban
    ? buildSessions(kanban.tasks, {}).filter((session) => sessionGroupKey(session) === 'attention')
    : [];

  return (
    <div className="w-full max-w-2xl mb-6 text-left text-brutal-black dark:text-white">
      <div className="flex items-start gap-3">
        <span className="block w-10 h-10 shrink-0" aria-hidden="true">
          <RobotAvatar variant="idle" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="mb-2 font-mono text-xs font-bold text-neutral-500 dark:text-neutral-400">
            {t('chatList.focal.name')}
          </p>
          <h1 className="text-2xl font-bold tracking-tight">{t('focalBriefing.greeting')}</h1>
          <p className="mt-2 text-sm leading-relaxed text-neutral-600 dark:text-neutral-300">
            {t('focalBriefing.invitation')}
          </p>
          {waiting.length > 0 && (
            <details className="mt-4 text-xs text-neutral-500 dark:text-neutral-400">
              <summary className="cursor-pointer leading-relaxed focus-visible:outline focus-visible:outline-2 focus-visible:outline-current">
                {t('focalBriefing.followUp')}
              </summary>
              <ul className="mt-2 pl-3 border-l border-neutral-200 dark:border-zinc-700 max-h-56 overflow-auto space-y-3">
                {waiting.map((session) => (
                  <li key={session.key} className="break-words">
                    {session.chatId ? (
                      <button type="button" onClick={() => onOpenChat(session.chatId!)}>
                        {session.title || t('taskFlow.unassignedSession')}
                        <span aria-hidden="true"> ↗</span>
                      </button>
                    ) : (
                      <span>{session.title || t('taskFlow.unassignedSession')}</span>
                    )}
                    {session.blocker?.waitingReason && (
                      <p className="mt-1 leading-relaxed">{session.blocker.waitingReason}</p>
                    )}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
