import React, { useState } from 'react';
import type { Task, TaskStatus } from '../../types/api';
import type { KanbanData } from '../../hooks/useGoalTasks';
import { useGoalTasks } from '../../hooks/useGoalTasks';
import { useI18n } from '../../i18n';
import { BrutalButton } from '../BrutalButton';

interface ProjectKanbanViewProps {
  projectName?: string | null;
  projectId?: string | null;
  kanban: KanbanData | null;
  /** Map of chatId → chat title for assignee chip lookup */
  chatTitles?: Record<string, string>;
}

const STATUS_CYCLE: TaskStatus[] = ['pending', 'in_progress', 'completed'];
const NEXT_STATUS: Record<string, TaskStatus> = {
  pending: 'in_progress',
  in_progress: 'completed',
  completed: 'pending',
  blocked: 'in_progress',
  cancelled: 'pending',
};

const COLUMNS: { id: TaskStatus | 'blocked'; label: string }[] = [
  { id: 'pending',     label: 'Todo'   },
  { id: 'in_progress', label: 'Active' },
  { id: 'completed',   label: 'Done'   },
];

const DOT_PATTERNS = ['●', '○', '◆', '◇'] as const;
function dotPattern(chatId: string | null | undefined): string {
  if (!chatId) return '□';
  let h = 0;
  for (let i = 0; i < chatId.length; i++) h = (h * 31 + chatId.charCodeAt(i)) >>> 0;
  return DOT_PATTERNS[h % DOT_PATTERNS.length];
}

interface AssigneeChipProps {
  chatId: string | null | undefined;
  chatTitle?: string;
}

const AssigneeChip: React.FC<AssigneeChipProps> = ({ chatId, chatTitle }) => {
  const short = chatId ? chatId.slice(0, 8) : null;
  const title = chatTitle || (chatId ? `${short}…` : 'human');
  const pattern = dotPattern(chatId);

  return (
    <span className="inline-flex items-center gap-1 border-2 border-brutal-black bg-white dark:bg-zinc-800 pl-1 pr-2 py-0.5 max-w-[140px]">
      <span className="text-[10px] font-black text-brutal-black dark:text-white shrink-0 leading-none">{pattern}</span>
      <span className="text-[8px] font-black text-brutal-black dark:text-white truncate font-mono">{title}</span>
      {chatId && (
        <span className="text-[7px] font-mono text-neutral-400 dark:text-zinc-500 shrink-0">{short}</span>
      )}
    </span>
  );
};

interface AddCardFormProps {
  onAdd: (title: string) => void;
  onCancel: () => void;
}

const AddCardForm: React.FC<AddCardFormProps> = ({ onAdd, onCancel }) => {
  const [value, setValue] = useState('');
  return (
    <div className="border-2 border-brutal-black bg-white dark:bg-zinc-800 p-2 shadow-[2px_2px_0_0_#000]">
      <input
        autoFocus
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && value.trim()) onAdd(value.trim());
          if (e.key === 'Escape') onCancel();
        }}
        placeholder="Task title…"
        className="w-full border-2 border-brutal-black px-2 py-1 text-xs font-bold font-mono bg-white dark:bg-zinc-700 dark:text-white outline-none mb-2"
      />
      <div className="flex gap-1">
        <BrutalButton variant="dark" size="sm" onClick={() => value.trim() && onAdd(value.trim())}>
          Add
        </BrutalButton>
        <BrutalButton size="sm" onClick={onCancel}>
          Cancel
        </BrutalButton>
      </div>
    </div>
  );
};

interface KanbanCardProps {
  task: Task;
  chatTitle?: string;
  onStatusCycle: () => void;
  onDelete: () => void;
}

const KanbanCard: React.FC<KanbanCardProps> = ({ task, chatTitle, onStatusCycle, onDelete }) => {
  const [hovered, setHovered] = useState(false);
  const isActive = task.status === 'in_progress';
  const isDone = task.status === 'completed';
  const isBlocked = task.status === 'blocked';

  return (
    <div
      className={[
        'border-2 border-brutal-black bg-white dark:bg-zinc-800 p-2 relative',
        isActive ? 'shadow-[3px_3px_0_0_#000]' : '',
        isBlocked ? 'bg-brutal-yellow/10 dark:bg-zinc-800' : '',
        isDone ? 'opacity-50' : '',
      ].join(' ')}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {hovered && (
        <div className="absolute top-1.5 right-1.5 flex gap-1 z-10">
          <BrutalButton
            size="icon"
            onClick={onStatusCycle}
            title={`Move to ${NEXT_STATUS[task.status]}`}
            className="px-1.5 py-0.5 text-[9px] leading-none"
          >
            {isDone ? '↺' : '→'}
          </BrutalButton>
          <BrutalButton
            size="icon"
            onClick={onDelete}
            title="Delete"
            className="px-1.5 py-0.5 text-[9px] leading-none"
          >
            ✕
          </BrutalButton>
        </div>
      )}

      <div className="text-[7px] font-mono font-black opacity-25 mb-1">#{task.id}</div>
      <div className={`text-xs font-black leading-snug text-brutal-black dark:text-white mb-2 ${hovered ? 'pr-10' : ''} ${isDone ? 'line-through' : ''}`}>
        {isActive && task.activeForm ? task.activeForm : task.title}
      </div>
      <div className="flex items-center justify-between gap-1 flex-wrap">
        <AssigneeChip chatId={task.assignee} chatTitle={chatTitle} />
        {isBlocked && task.blockedBy.length > 0 && (
          <span className="text-[7px] font-black border border-brutal-black bg-brutal-yellow px-1 py-0.5 text-brutal-black">
            blocked by {task.blockedBy.map(b => `#${b}`).join(', ')}
          </span>
        )}
      </div>
    </div>
  );
};

export const ProjectKanbanView: React.FC<ProjectKanbanViewProps> = ({
  projectName,
  projectId,
  kanban,
  chatTitles = {},
}) => {
  const { t } = useI18n();
  const { updateTask, createTask, deleteTask } = useGoalTasks();
  const [addingIn, setAddingIn] = useState<string | null>(null);

  if (!kanban) {
    return (
      <div className="flex items-center justify-center h-full text-[10px] font-black uppercase tracking-widest font-mono text-brutal-black dark:text-white opacity-25">
        {t('projectBoard.noTasks')}
      </div>
    );
  }

  const { goals, tasks } = kanban;

  const colTasks: Record<string, Task[]> = {
    pending: tasks.filter(t => t.status === 'pending' || t.status === 'blocked'),
    in_progress: tasks.filter(t => t.status === 'in_progress'),
    completed: tasks.filter(t => t.status === 'completed'),
  };

  const handleStatusCycle = async (task: Task) => {
    await updateTask(task.id, { status: NEXT_STATUS[task.status] });
  };

  const handleAdd = async (colId: string, title: string) => {
    if (!projectId) return;
    const status = colId === 'in_progress' ? 'in_progress' : colId === 'completed' ? 'completed' : 'pending';
    await createTask(projectId, title, status);
    setAddingIn(null);
  };

  return (
    <div className="flex flex-col h-full min-h-0">

      {/* ── Header ── */}
      <div className="shrink-0 bg-brutal-black text-white px-3 py-2 border-b-3 border-brutal-black">
        <div className="text-[9px] font-black uppercase tracking-widest opacity-50">{t('projectBoard.title')}</div>
        {projectName && (
          <div className="text-base font-black tracking-tight uppercase leading-tight">{projectName}</div>
        )}
      </div>

      {/* ── Goal chips ── */}
      {goals.length > 0 && (
        <div className="shrink-0 border-b-2 border-brutal-black bg-white dark:bg-zinc-800 px-3 py-2 flex flex-wrap gap-1.5">
          {goals.map(goal => (
            <span key={goal.id} className="inline-flex items-center gap-1.5 border-2 border-brutal-black bg-white dark:bg-zinc-700 px-2 py-0.5 shadow-[2px_2px_0_0_#000]">
              <span className="text-[9px] font-black text-brutal-black dark:text-white">◆</span>
              <span className="text-[9px] font-black text-brutal-black dark:text-white truncate max-w-[140px]">{goal.objective}</span>
            </span>
          ))}
        </div>
      )}

      {/* ── Kanban columns ── */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        {COLUMNS.map((col, colIdx) => {
          const colItems = colTasks[col.id] || [];
          return (
            <div
              key={col.id}
              className={`flex flex-col flex-1 overflow-hidden ${colIdx < COLUMNS.length - 1 ? 'border-r-2 border-brutal-black' : ''}`}
            >
              {/* Column header */}
              <div className="shrink-0 px-2 py-1.5 border-b-2 border-brutal-black bg-white dark:bg-zinc-800 flex items-center justify-between">
                <span className="text-[9px] font-black uppercase tracking-widest text-brutal-black dark:text-white">
                  {col.label}
                </span>
                <div className="flex items-center gap-1">
                  <span className={`text-[9px] font-black font-mono px-1.5 border-2 border-brutal-black ${col.id === 'completed' ? 'bg-brutal-green text-brutal-black' : 'bg-white dark:bg-zinc-700 text-brutal-black dark:text-white'}`}>
                    {colItems.length}
                  </span>
                  <BrutalButton
                    size="icon"
                    onClick={() => setAddingIn(addingIn === col.id ? null : col.id)}
                    title="Add task"
                    className="px-1 py-0.5 text-[9px] leading-none"
                  >
                    ＋
                  </BrutalButton>
                </div>
              </div>

              {/* Cards */}
              <div className="flex-1 overflow-y-auto scrollbar-thin scrollbar-track-neutral-200 dark:scrollbar-track-zinc-700 scrollbar-thumb-brutal-black bg-neutral-100 dark:bg-zinc-900 p-1.5 flex flex-col gap-1.5">
                {colItems.map(task => (
                  <KanbanCard
                    key={task.id}
                    task={task}
                    chatTitle={task.assignee ? chatTitles[task.assignee] : undefined}
                    onStatusCycle={() => handleStatusCycle(task)}
                    onDelete={() => deleteTask(task.id)}
                  />
                ))}

                {addingIn === col.id && (
                  <AddCardForm
                    onAdd={title => handleAdd(col.id, title)}
                    onCancel={() => setAddingIn(null)}
                  />
                )}

                {colItems.length === 0 && addingIn !== col.id && (
                  <BrutalButton
                    variant="ghost"
                    size="sm"
                    onClick={() => setAddingIn(col.id)}
                    className="border-dashed w-full justify-center py-2 opacity-20 hover:opacity-60"
                  >
                    ＋ Add task
                  </BrutalButton>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
