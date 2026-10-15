import React from 'react';
import type { Task } from '../../types/api';
import { useI18n } from '../../i18n';

interface TaskProgressCardProps {
  task: Task;
  tasks: Task[];
  chatTitle?: string;
  compact?: boolean;
  selected?: boolean;
  opening?: boolean;
  disabled?: boolean;
  onOpen?: (task: Task) => void;
  onResult?: (task: Task) => void;
}

export function TaskProgressCard({
  task,
  tasks,
  chatTitle,
  compact = false,
  selected = false,
  opening = false,
  disabled = false,
  onOpen,
  onResult,
}: TaskProgressCardProps): React.ReactElement {
  const { t, locale } = useI18n();
  const openTask = task.chatId?.trim() ? onOpen : undefined;
  const waiting = task.status === 'blocked';
  const done = task.status === 'completed';
  const statusKey = task.status === 'in_progress' ? 'inprogress' : task.status;
  const dependencies = task.blockedBy.map(
    (id) => tasks.find((item) => item.id === id)?.title ?? `#${id}`
  );
  const detail = done ? task.resultSummary : waiting ? task.waitingReason : task.activeForm;
  const updated = task.updatedAt ? new Date(task.updatedAt) : null;
  if (compact) {
    const summary = [
      detail ||
        (waiting && dependencies.length > 0
          ? t('taskFlow.dependencies', {
              titles: dependencies.join(locale === 'zh-CN' ? '、' : ', '),
            })
          : task.description),
      waiting ? task.nextAction : null,
    ]
      .filter(Boolean)
      .join(' · ');
    return (
      <article
        aria-busy={opening}
        className={`task-row ${selected ? 'bg-brutal-yellow/15 shadow-[inset_3px_0_0_0_#000]' : ''} relative flex items-center gap-3 border-b border-brutal-black/10 dark:border-zinc-700 last:border-b-0 px-4 py-3 sm:px-5 ${openTask ? 'hover:bg-brutal-yellow/10 dark:hover:bg-zinc-800' : ''}`}
      >
        {openTask && (
          <button
            type="button"
            disabled={disabled}
            aria-current={selected ? 'true' : undefined}
            onClick={() => openTask(task)}
            aria-label={`${task.title} · ${t(task.chatId ? 'taskFlow.openChat' : 'taskFlow.start')}`}
            className="absolute inset-0 w-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 focus-visible:outline-offset-[-2px]"
          />
        )}
        <div className="min-w-0 flex-1 pointer-events-none">
          <h3 className="truncate text-sm font-bold" title={task.title}>
            {task.title}
          </h3>
          {summary && (
            <p
              title={summary}
              className="mt-1 truncate text-sm text-neutral-500 dark:text-zinc-400"
            >
              {summary}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-3 text-xs">
          {opening && <span role="status">{t('taskFlow.loading')}</span>}
          {done && task.chatId && task.resultPath && onResult && (
            <button
              type="button"
              disabled={disabled}
              onClick={() => onResult(task)}
              className="relative border-2 border-brutal-black bg-white dark:bg-zinc-800 px-2 py-1 font-mono font-bold shadow-[2px_2px_0_0_#000] hover:bg-brutal-green/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue"
            >
              {t('taskFlow.viewResult')} ↗
            </button>
          )}
          {updated && !Number.isNaN(updated.getTime()) && (
            <time
              className="pointer-events-none font-mono text-neutral-500 dark:text-zinc-400"
              dateTime={task.updatedAt}
              title={updated.toLocaleString(locale)}
            >
              {updated.toLocaleDateString(locale, { month: 'short', day: 'numeric' })}
            </time>
          )}
        </div>
      </article>
    );
  }
  return (
    <article
      aria-busy={opening}
      className={`min-w-0 border-2 border-brutal-black p-3 space-y-2 ${waiting ? 'bg-brutal-yellow/10 dark:bg-zinc-800' : 'bg-white dark:bg-zinc-800'}`}
    >
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span
            className={`inline-flex items-center gap-1.5 font-bold ${waiting ? 'text-amber-800 dark:text-amber-300' : 'text-neutral-600 dark:text-zinc-300'}`}
          >
            <span
              aria-hidden="true"
              className={`h-2 w-2 border border-brutal-black ${waiting ? 'bg-amber-500' : done ? 'bg-green-600' : task.status === 'in_progress' ? 'bg-blue-600' : 'bg-neutral-400'}`}
            />
            {waiting && task.waitingKind
              ? t(`taskFlow.wait.${task.waitingKind}`)
              : t(`task.status.${statusKey}`)}
          </span>
          {updated && !Number.isNaN(updated.getTime()) && (
            <time
              className="ml-auto text-neutral-500 dark:text-zinc-400"
              dateTime={task.updatedAt}
              title={updated.toLocaleString(locale)}
            >
              {updated.toLocaleDateString(locale, { month: 'short', day: 'numeric' })}
            </time>
          )}
        </div>
        {openTask ? (
          <button
            type="button"
            disabled={disabled}
            aria-current={selected ? 'true' : undefined}
            onClick={() => openTask?.(task)}
            className="block text-left text-sm font-bold leading-snug hover:underline focus-visible:outline-offset-4 break-words"
          >
            {task.title}
          </button>
        ) : (
          <h3 className="text-sm font-bold leading-snug break-words">{task.title}</h3>
        )}
        {detail && (
          <p className="text-xs leading-relaxed text-neutral-600 dark:text-zinc-300 break-words whitespace-pre-wrap">
            {detail}
          </p>
        )}
        {waiting && dependencies.length > 0 && (
          <p className="text-xs text-amber-800 dark:text-amber-300">
            {t('taskFlow.dependencies', {
              titles: dependencies.join(locale === 'zh-CN' ? '、' : ', '),
            })}
          </p>
        )}
        {task.nextAction && waiting && (
          <p className="text-xs font-medium">
            {t('taskFlow.nextAction', { action: task.nextAction })}
          </p>
        )}
        {!detail && !waiting && task.description && (
          <p className="text-xs text-neutral-600 dark:text-zinc-300 line-clamp-2">
            {task.description}
          </p>
        )}
      </div>
      {(openTask || (done && task.chatId && task.resultPath && onResult)) && (
        <div className="flex flex-wrap gap-x-4 gap-y-2 pt-1 text-xs">
          {openTask && (
            <button
              type="button"
              disabled={disabled}
              aria-current={selected ? 'true' : undefined}
              onClick={() => openTask?.(task)}
              className="max-w-full text-left break-words font-bold underline underline-offset-4"
            >
              {task.chatId
                ? chatTitle || t('taskFlow.openChat')
                : task.status === 'pending' || waiting
                  ? t('taskFlow.start')
                  : t('taskFlow.discuss')}{' '}
              →
            </button>
          )}
          {done && task.chatId && task.resultPath && onResult && (
            <button
              type="button"
              disabled={disabled}
              onClick={() => onResult(task)}
              className="max-w-full text-left break-words font-bold underline underline-offset-4"
            >
              {t('taskFlow.viewResult')} ↗
            </button>
          )}
        </div>
      )}
    </article>
  );
}
