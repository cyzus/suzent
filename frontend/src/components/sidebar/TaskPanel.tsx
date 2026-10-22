import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { Goal, Task } from '../../types/api';
import { useGoalTasks, type KanbanData } from '../../hooks/useGoalTasks';
import { useI18n } from '../../i18n';
import { ProjectKanbanView } from './ProjectKanbanView';
import { BrutalSegmentedTabs } from '../BrutalSegmentedTabs';
import { BrutalSelect } from '../BrutalSelect';
import { GoalSummary } from './GoalSummary';
import { readFocalProjectFilter, writeFocalProjectFilter } from '../../lib/focalAgent';
import {
  ALL_PROJECTS,
  filterKanbanByProject,
  projectOptions,
  type StatusChange,
} from '../../lib/sessionGroups';
import { setTaskStatus } from '../../lib/api';

interface TaskPanelProps {
  navigationError?: string | null;
  onDismissError?: () => void;
  goal: Goal | null;
  tasks: Task[];
  kanban: KanbanData | null;
  projectName?: string | null;
  chatTitles?: Record<string, string>;
  onOpenTask?: (task: Task) => Promise<boolean>;
  onOpenChat?: (chatId: string) => void;
  /** On the Focal Agent chat the board spans every project, grouped by session. */
  focal?: boolean;
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
  onOpenChat,
  focal = false,
}: TaskPanelProps): React.ReactElement {
  const { t } = useI18n();
  const { chatLoading, chatError, kanbanError, kanbanLoading, refresh, refreshKanban } =
    useGoalTasks();
  const [scope, setScope] = useState<'chat' | 'project'>(focal ? 'project' : 'chat');
  useEffect(() => {
    setScope(focal ? 'project' : 'chat');
  }, [focal]);
  const chatScope = scope === 'chat';
  const [projectFilter, setProjectFilter] = useState<string>(
    () => readFocalProjectFilter() ?? ALL_PROJECTS
  );
  const projects = useMemo(() => (focal ? projectOptions(kanban) : []), [focal, kanban]);
  // A remembered project that has since emptied out or been archived falls back to all.
  const activeProject = projects.find((project) => project.id === projectFilter);
  const effectiveFilter = activeProject ? activeProject.id : ALL_PROJECTS;
  const chooseProject = (projectId: string): void => {
    setProjectFilter(projectId);
    writeFocalProjectFilter(projectId);
  };
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [pendingTaskId, setPendingTaskId] = useState<number | null>(null);
  const opening = useRef(false);
  const openTask = async (task: Task): Promise<void> => {
    if (opening.current) return;
    opening.current = true;
    setPendingTaskId(task.id);
    try {
      const opened = await onOpenTask?.(task);
      if (opened) setSelectedTaskId(task.id);
    } finally {
      opening.current = false;
      setPendingTaskId(null);
    }
  };
  const setTaskStatuses = async (changes: StatusChange[]): Promise<void> => {
    try {
      await Promise.all(changes.map(({ task, status }) => setTaskStatus(task.id, status)));
    } finally {
      void refreshKanban();
    }
  };
  return (
    <div className="task-panel h-full min-h-0" style={{ containerType: 'inline-size' }}>
      <ProjectKanbanView
        scope={scope}
        groupBy={focal ? 'session' : 'status'}
        selectedTaskId={selectedTaskId}
        pendingTaskId={pendingTaskId}
        projectName={focal ? (activeProject?.label ?? t('taskFlow.allProjects')) : projectName}
        kanban={
          chatScope
            ? chatLoading && tasks.length === 0 && !goal
              ? null
              : { goals: [], tasks }
            : focal
              ? filterKanbanByProject(kanban, effectiveFilter)
              : kanban
        }
        chatTitles={chatTitles}
        loading={chatScope ? chatLoading && tasks.length === 0 && !goal : kanbanLoading && !kanban}
        error={chatScope ? chatError : kanbanError}
        onRetry={() => void (chatScope ? refresh() : refreshKanban())}
        onOpenTask={(task) => void openTask(task)}
        onOpenChat={onOpenChat}
        onSetTaskStatus={focal ? setTaskStatuses : undefined}
        summary={
          chatScope && goal && goal.status !== 'cancelled' ? (
            <GoalSummary key={goal.id} goal={goal} tasks={tasks} />
          ) : undefined
        }
        headerControls={
          <div className="space-y-2">
            {focal ? (
              projects.length > 1 && (
                <BrutalSelect
                  label={t('taskFlow.projectFilter')}
                  value={effectiveFilter}
                  onChange={chooseProject}
                  options={[
                    { value: ALL_PROJECTS, label: t('taskFlow.allProjects') },
                    ...projects.map((project) => ({ value: project.id, label: project.label })),
                  ]}
                  className="w-full"
                />
              )
            ) : (
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
            )}
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
