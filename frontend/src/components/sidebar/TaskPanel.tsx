import React, { useEffect, useRef, useState } from 'react';
import type { Goal, Task } from '../../types/api';
import { useGoalTasks, type KanbanData } from '../../hooks/useGoalTasks';
import { useI18n } from '../../i18n';
import { ProjectKanbanView } from './ProjectKanbanView';
import { BrutalSegmentedTabs } from '../BrutalSegmentedTabs';
import { GoalSummary } from './GoalSummary';

interface TaskPanelProps {
  navigationError?: string | null;
  onDismissError?: () => void;
  goal: Goal | null;
  tasks: Task[];
  kanban: KanbanData | null;
  projectName?: string | null;
  chatTitles?: Record<string, string>;
  onOpenTask?: (task: Task) => Promise<boolean>;
  onResult?: (task: Task) => Promise<boolean>;
  onOpenChat?: (chatId: string) => void;
}

export function TaskPanel({
  navigationError,
  onDismissError,
  goal,
  tasks,
  kanban,
  projectName,
  chatTitles,
  onOpenTask,
  onResult,
  onOpenChat,
}: TaskPanelProps): React.ReactElement {
  const { t } = useI18n();
  const { chatLoading, chatError, kanbanError, kanbanLoading, refresh, refreshKanban } =
    useGoalTasks();
  const [scope, setScope] = useState<'chat' | 'project'>('chat');
  const chatScope = scope === 'chat';
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [pendingTaskId, setPendingTaskId] = useState<number | null>(null);
  const opening = useRef(false);
  const openTask = async (task: Task, result = false): Promise<void> => {
    if (opening.current) return;
    opening.current = true;
    setPendingTaskId(task.id);
    try {
      const opened = await (result ? onResult?.(task) : onOpenTask?.(task));
      if (opened) setSelectedTaskId(task.id);
    } finally {
      opening.current = false;
      setPendingTaskId(null);
    }
  };
  const panelRef = useRef<HTMLDivElement>(null);
  const [narrow, setNarrow] = useState(true);
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const observer = new ResizeObserver(([entry]) => setNarrow(entry.contentRect.width <= 480));
    observer.observe(panel);
    return () => observer.disconnect();
  }, []);
  return (
    <div
      ref={panelRef}
      className="task-panel h-full min-h-0"
      style={{ containerType: 'inline-size' }}
    >
      <ProjectKanbanView
        narrow={narrow}
        selectedTaskId={selectedTaskId}
        pendingTaskId={pendingTaskId}
        projectName={projectName}
        kanban={
          chatScope
            ? chatLoading && tasks.length === 0 && !goal
              ? null
              : { goals: [], tasks }
            : kanban
        }
        chatTitles={chatTitles}
        loading={chatScope ? chatLoading && tasks.length === 0 && !goal : kanbanLoading && !kanban}
        error={chatScope ? chatError : kanbanError}
        onRetry={() => void (chatScope ? refresh() : refreshKanban())}
        onOpenTask={(task) => void openTask(task)}
        onResult={(task) => void openTask(task, true)}
        onOpenChat={onOpenChat}
        summary={
          chatScope && goal && goal.status !== 'cancelled' ? (
            <GoalSummary key={goal.id} goal={goal} tasks={tasks} />
          ) : undefined
        }
        headerControls={
          <div className="space-y-2">
            <div role="group" aria-label={t('taskFlow.scope')}>
              <BrutalSegmentedTabs
                tabs={[
                  { id: 'chat' as const, label: t('taskFlow.currentChat') },
                  { id: 'project' as const, label: t('taskFlow.entireProject') },
                ]}
                value={scope}
                onChange={(value) => {
                  setScope(value);
                  onDismissError?.();
                }}
                className="w-fit max-w-full"
                tabClassName="px-3 py-1.5 text-xs font-bold"
              />
            </div>
            {navigationError && (
              <p role="status" className="text-xs text-neutral-600 dark:text-zinc-300">
                {navigationError}
              </p>
            )}
          </div>
        }
      />
    </div>
  );
}
