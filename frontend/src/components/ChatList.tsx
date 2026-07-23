import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckIcon,
  EllipsisVerticalIcon,
  FolderIcon,
  PencilSquareIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';
import { useChatStore } from '../hooks/useChatStore';
import { useProjects } from '../hooks/useProjects';
import type { ChatKindCounts, ChatSummary, Project } from '../types/api';
import { RobotAvatar } from './chat/RobotAvatar';
import { useI18n } from '../i18n';
import {
  fetchCronJobs,
  fetchHeartbeatStatus,
  getApiBase,
  markChatRead,
  deleteCronJob,
  updateCronJob,
  type CronJob,
  type HeartbeatStatus,
} from '../lib/api';
import { ChatRowMenu } from './ChatRowMenu';
import { ProjectRowMenu } from './ProjectRowMenu';
import { BrutalDialog } from './BrutalDialog';
import { BrutalButton } from './BrutalButton';

const ALL_PROJECTS_FILTER = '__all__';
const AUTOMATION_PREVIEW_LIMIT = 5;
const ORGANIZATION_STORAGE_KEY = 'suzent-chat-organization';
type ChatKind = 'you' | 'subagent' | 'scheduled';
type ChatOrganization = 'projects' | 'list';

const MoreActionsIcon = (): React.ReactElement => (
  <EllipsisVerticalIcon className="h-4 w-4 stroke-[2.5]" />
);

const isCronFailureHandledInChat = (job: CronJob): boolean => {
  if (!job.last_error || !job.chat_updated_at || !job.last_run_finished_at) return false;
  return new Date(job.chat_updated_at).getTime() > new Date(job.last_run_finished_at).getTime();
};

interface ChatListProps {
  onOpenAutomation?: () => void;
}

export const ChatList: React.FC<ChatListProps> = ({ onOpenAutomation }) => {
  const {
    chats,
    chatTotal,
    loadingChats,
    loadingMoreChats,
    refreshingChats,
    currentChatId,
    searchQuery,
    setSearchQuery,
    loadChat,
    beginNewChat,
    deleteChat,
    renameChat,
    switchToView,
    refreshChatList,
    loadMoreChats,
  } = useChatStore();

  const {
    projects,
    currentProjectId,
    setCurrentProjectId,
    createProject,
    renameProject,
    deleteProject,
    moveChat,
    moveAllChats,
    refresh: refreshProjects,
  } = useProjects();

  const [renamingChatId, setRenamingChatId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState<string>('');
  const [showRefreshIndicator, setShowRefreshIndicator] = useState(false);
  const [localSearchQuery, setLocalSearchQuery] = useState<string>('');
  // Unified menu state: which chat's context menu is open, and where to anchor it.
  // anchor.point is for right-click; anchor.rect is for the dots button.
  const [openMenu, setOpenMenu] = useState<{
    chatId: string;
    anchor: { x: number; y: number } | { rect: DOMRect };
  } | null>(null);

  // Project context menu (kebab on each project row).
  const [projectMenu, setProjectMenu] = useState<{
    projectId: string;
    anchor: { rect: DOMRect };
  } | null>(null);
  const [renamingProjectId, setRenamingProjectId] = useState<string | null>(null);
  const [projectRenameValue, setProjectRenameValue] = useState('');
  const [taskMenu, setTaskMenu] = useState<{
    jobId: number;
    anchor: { rect: DOMRect };
  } | null>(null);
  const [renamingTaskId, setRenamingTaskId] = useState<number | null>(null);
  const [taskRenameValue, setTaskRenameValue] = useState('');
  const [organizationMenuOpen, setOrganizationMenuOpen] = useState(false);
  const organizationMenuRef = useRef<HTMLDivElement | null>(null);
  const [organization, setOrganization] = useState<ChatOrganization>(() => {
    try {
      return localStorage.getItem(ORGANIZATION_STORAGE_KEY) === 'list' ? 'list' : 'projects';
    } catch {
      return 'projects';
    }
  });

  // Dialog state — replaces window.alert / window.confirm so we keep
  // brutalist styling and never get blocked by browser dialog rendering.
  const [dialog, setDialog] = useState<{
    title?: string;
    message: React.ReactNode;
    actions: { label: string; tone?: 'default' | 'primary' | 'danger'; onClick?: () => void | Promise<void>; preventDismiss?: boolean }[];
  } | null>(null);

  // A single expanded project keeps the sidebar compact.
  const [filterId, setFilterId] = useState<string>(ALL_PROJECTS_FILTER);
  const [expandedSubagentParents, setExpandedSubagentParents] = useState<Set<string>>(
    () => new Set(),
  );
  const [creatingProjectInline, setCreatingProjectInline] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const sidebarBoundsRef = useRef<HTMLDivElement | null>(null);
  const [projectChats, setProjectChats] = useState<ChatSummary[]>([]);
  const [projectChatKindTotals, setProjectChatKindTotals] = useState<ChatKindCounts>({ you: 0, scheduled: 0, all: 0 });
  const [projectChatOffset, setProjectChatOffset] = useState(0);
  const [loadingProjectChats, setLoadingProjectChats] = useState(false);
  const [loadingMoreProjectChats, setLoadingMoreProjectChats] = useState(false);
  const [cronJobs, setCronJobs] = useState<CronJob[]>([]);
  const [heartbeatStatus, setHeartbeatStatus] = useState<HeartbeatStatus | null>(null);
  const [loadingAutomation, setLoadingAutomation] = useState(true);

  const { t } = useI18n();

  const refreshAutomation = useCallback(async (): Promise<void> => {
    const [cronResult, heartbeatResult] = await Promise.allSettled([
      fetchCronJobs(),
      fetchHeartbeatStatus(),
    ]);
    if (cronResult.status === 'fulfilled') setCronJobs(cronResult.value);
    if (heartbeatResult.status === 'fulfilled') setHeartbeatStatus(heartbeatResult.value);
    setLoadingAutomation(false);
  }, []);

  useEffect(() => {
    void refreshAutomation();
    const interval = window.setInterval(() => void refreshAutomation(), 30_000);
    return () => window.clearInterval(interval);
  }, [refreshAutomation]);

  useEffect(() => {
    if (!organizationMenuOpen) return;
    const closeMenu = (event: MouseEvent): void => {
      if (!organizationMenuRef.current?.contains(event.target as Node)) {
        setOrganizationMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', closeMenu);
    return () => document.removeEventListener('mousedown', closeMenu);
  }, [organizationMenuOpen]);

  const selectOrganization = (next: ChatOrganization): void => {
    setOrganization(next);
    setOrganizationMenuOpen(false);
    if (next === 'list') setFilterId(ALL_PROJECTS_FILTER);
    try {
      localStorage.setItem(ORGANIZATION_STORAGE_KEY, next);
    } catch {
      // The preference remains active for this session when storage is unavailable.
    }
  };

  const chatsRef = useRef(chats);
  useEffect(() => { chatsRef.current = chats; }, [chats]);
  const projectChatsRef = useRef(projectChats);
  useEffect(() => { projectChatsRef.current = projectChats; }, [projectChats]);
  const initialProjectSelectedRef = useRef(false);

  useEffect(() => {
    if (initialProjectSelectedRef.current || projects.length === 0) return;
    const selectedProjectId = chats.find(chat => chat.id === currentChatId)?.projectId;
    if (selectedProjectId && projects.some(project => project.id === selectedProjectId)) {
      setFilterId(selectedProjectId);
    }
    initialProjectSelectedRef.current = true;
  }, [chats, currentChatId, projects]);

  // Whenever the chat list changes (create / delete / move), the server-side
  // project chat counts may be stale. Refresh them so the dropdown shows
  // accurate numbers without the user having to do anything.
  useEffect(() => {
    void refreshProjects();
  }, [chats.length, refreshProjects]);

  // Keep projectChats in sync with changes to the global chats list while a
  // project filter is active (new chat added, or title/fields updated locally).
  const prevChatsLengthRef = useRef(chats.length);
  useEffect(() => {
    if (filterId === ALL_PROJECTS_FILTER) return;

    const prevLen = prevChatsLengthRef.current;
    prevChatsLengthRef.current = chats.length;

    if (chats.length > prevLen) {
      // A chat was added — prepend it if it belongs to the active project.
      const newest = chats[0];
      if (!newest || newest.projectId !== filterId) return;
      setProjectChats(prev => {
        if (prev.some(c => c.id === newest.id)) return prev;
        return [newest, ...prev];
      });
      setProjectChatKindTotals(prev => ({ ...prev, all: prev.all + 1, you: prev.you + 1 }));
    } else {
      // No length change — propagate any field updates (e.g. auto-title) to projectChats.
      setProjectChats(prev => {
        let changed = false;
        const next = prev.map(pc => {
          const updated = chats.find(c => c.id === pc.id);
          if (updated && updated.title !== pc.title) { changed = true; return { ...pc, title: updated.title }; }
          return pc;
        });
        return changed ? next : prev;
      });
    }
  }, [chats, filterId]);

  const markRead = useCallback((chatId: string) => {
    const chat = chatsRef.current.find(c => c.id === chatId);
    if (!chat) return;
    markChatRead(chatId);
    chat.unreadCount = 0;
  }, []);

  const isUnread = (chat: ChatSummary) => {
    if (chat.id === currentChatId) return false;
    return (chat.unreadCount ?? 0) > 0;
  };

  const unreadMessages = (chat: ChatSummary) => {
    if (!isUnread(chat)) return 0;
    return chat.unreadCount ?? 0;
  };

  useEffect(() => {
    if (currentChatId) markRead(currentChatId);
  }, [currentChatId, chats, markRead]);

  useEffect(() => {
    setLocalSearchQuery(searchQuery);
  }, []);

  useEffect(() => {
    const timeout = setTimeout(() => {
      setSearchQuery(localSearchQuery);
      refreshChatList(localSearchQuery, true);
    }, 300);
    return () => clearTimeout(timeout);
  }, [localSearchQuery]);

  useEffect(() => {
    let timeout: NodeJS.Timeout | null = null;
    if (refreshingChats) {
      timeout = setTimeout(() => setShowRefreshIndicator(true), 250);
    } else {
      setShowRefreshIndicator(false);
    }
    return () => {
      if (timeout) clearTimeout(timeout);
    };
  }, [refreshingChats]);

  const fetchProjectChats = useCallback(async (
    projectId: string,
    options?: { offset?: number; append?: boolean },
  ) => {
    const offset = options?.offset ?? 0;
    const append = !!options?.append;
    if (append) setLoadingMoreProjectChats(true);
    else {
      setLoadingProjectChats(true);
      setProjectChats([]);
      setProjectChatKindTotals({ you: 0, scheduled: 0, all: 0 });
      setProjectChatOffset(0);
    }

    try {
      const params = new URLSearchParams({
        limit: '50',
        offset: String(offset),
        project_id: projectId,
      });

      const res = await fetch(`${getApiBase()}/chats?${params.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      const nextChats: ChatSummary[] = data.chats || [];
      setProjectChatKindTotals(data.kindCounts ?? {
        you: nextChats.filter(chat => (chat.platform || '').toLowerCase() !== 'cron').length,
        scheduled: nextChats.filter(chat => (chat.platform || '').toLowerCase() === 'cron').length,
        all: data.total ?? nextChats.length,
      });
      setProjectChatOffset(offset);
      setProjectChats(prev => {
        if (!append) return nextChats;
        const existingIds = new Set(prev.map(c => c.id));
        const appended = nextChats.filter(c => !existingIds.has(c.id));
        return [...prev, ...appended];
      });
    } catch (error) {
      console.error('Error fetching project chats:', error);
      if (!append) {
        setProjectChats([]);
        setProjectChatKindTotals({ you: 0, scheduled: 0, all: 0 });
        setProjectChatOffset(0);
      }
    } finally {
      if (append) setLoadingMoreProjectChats(false);
      else setLoadingProjectChats(false);
    }
  }, []);

  useEffect(() => {
    if (filterId === ALL_PROJECTS_FILTER) {
      setProjectChats([]);
      setProjectChatKindTotals({ you: 0, scheduled: 0, all: 0 });
      setProjectChatOffset(0);
      return;
    }
    void fetchProjectChats(filterId);
  }, [filterId, fetchProjectChats]);

  const filteredChats = useMemo(() => {
    if (filterId === ALL_PROJECTS_FILTER) return chats;
    return projectChats;
  }, [chats, filterId, projectChats]);

  const getChatKind = (chat: ChatSummary): ChatKind => {
    const platform = (chat.platform || '').toLowerCase();
    if (platform === 'subagent') return 'subagent';
    if (platform === 'cron') return 'scheduled';
    return 'you';
  };

  const subagentsByParent = useMemo(() => {
    const childrenByParent = new Map<string, ChatSummary[]>();
    for (const chat of filteredChats) {
      if (getChatKind(chat) !== 'subagent' || !chat.parentChatId) continue;
      const list = childrenByParent.get(chat.parentChatId) ?? [];
      list.push(chat);
      childrenByParent.set(chat.parentChatId, list);
    }
    return childrenByParent;
  }, [filteredChats]);

  useEffect(() => {
    const selected = filteredChats.find(chat => chat.id === currentChatId);
    if (!selected?.parentChatId) return;
    setExpandedSubagentParents(prev => {
      if (prev.has(selected.parentChatId!)) return prev;
      const next = new Set(prev);
      next.add(selected.parentChatId!);
      return next;
    });
  }, [currentChatId, filteredChats]);

  const toggleSubagentParent = (chatId: string) => {
    setExpandedSubagentParents(prev => {
      const next = new Set(prev);
      if (next.has(chatId)) next.delete(chatId);
      else next.add(chatId);
      return next;
    });
  };

  const visibleChats = useMemo(() => {
    const source = filteredChats;

    const childIds = new Set<string>();
    for (const chat of source) {
      if (getChatKind(chat) === 'subagent' && chat.parentChatId) {
        childIds.add(chat.id);
      }
    }

    const arranged: ChatSummary[] = [];
    for (const chat of source) {
      if (childIds.has(chat.id)) continue;
      arranged.push(chat);
      const childChats = subagentsByParent.get(chat.id);
      if (childChats && expandedSubagentParents.has(chat.id)) {
        arranged.push(...childChats);
      }
    }

    for (const chat of source) {
      if (childIds.has(chat.id) && !arranged.some(item => item.id === chat.id)) {
        const parentId = chat.parentChatId;
        const parentInSource = parentId ? source.some(p => p.id === parentId) : false;
        if (!parentInSource) {
          arranged.push(chat);
        }
      }
    }
    return arranged;
  }, [expandedSubagentParents, filteredChats, subagentsByParent]);

  const handleLoadMore = useCallback(async () => {
    if (filterId === ALL_PROJECTS_FILTER) {
      await loadMoreChats();
      return;
    }
    await fetchProjectChats(filterId, {
      offset: projectChatOffset + 50,
      append: true,
    });
  }, [fetchProjectChats, filterId, loadMoreChats, projectChatOffset]);

  // ── Chat actions ──

  const handleRequestDelete = (chatId: string) => {
    const hasSubagents = (subagentsByParent.get(chatId)?.length ?? 0) > 0;
    const doDelete = async (cascade: boolean) => {
      setProjectChats(prev => {
        const filtered = prev.filter(c => c.id !== chatId);
        return cascade ? filtered.filter(c => c.parentChatId !== chatId) : filtered;
      });
      try { await deleteChat(chatId, { cascade }); } catch { /* ignore */ }
    };

    if (hasSubagents) {
      setDialog({
        title: t('chatList.delete.confirmTitle'),
        message: t('chatList.delete.cascadeMessage'),
        actions: [
          { label: t('common.cancel'), tone: 'default' },
          { label: t('chatList.delete.cascadeNo'), tone: 'default', onClick: () => doDelete(false) },
          { label: t('chatList.delete.cascadeYes'), tone: 'danger', onClick: () => doDelete(true) },
        ],
      });
    } else {
      setDialog({
        title: t('chatList.delete.confirmTitle'),
        message: t('chatList.delete.confirmMessage'),
        actions: [
          { label: t('common.cancel'), tone: 'default' },
          { label: t('chatList.delete.confirm'), tone: 'danger', onClick: () => doDelete(false) },
        ],
      });
    }
  };

  const handleRenameSubmit = async (chatId: string, e: React.FormEvent | React.KeyboardEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const trimmed = renameValue.trim();
    if (trimmed) await renameChat(chatId, trimmed);
    setRenamingChatId(null);
  };

  const handleRenameCancel = (e: React.MouseEvent | React.KeyboardEvent) => {
    e.stopPropagation();
    setRenamingChatId(null);
  };

  const handleTaskRenameSubmit = async (
    job: CronJob,
    event: React.FormEvent,
  ): Promise<void> => {
    event.preventDefault();
    event.stopPropagation();
    const trimmed = taskRenameValue.trim();
    if (trimmed && trimmed !== job.name) {
      await updateCronJob(job.id, { name: trimmed });
      if (job.last_run_at) {
        try {
          await renameChat(`cron-${job.id}`, `Cron: ${trimmed}`);
        } catch {
          // The task may not have created its backing conversation yet.
        }
      }
      await refreshAutomation();
    }
    setRenamingTaskId(null);
  };

  const handleRequestTaskDelete = (job: CronJob): void => {
    const deleteTask = async (): Promise<void> => {
      await deleteCronJob(job.id);
      if (job.last_run_at) {
        try {
          await deleteChat(`cron-${job.id}`);
        } catch {
          // The scheduled task is already removed even if its chat was absent.
        }
      }
      await Promise.all([
        refreshAutomation(),
        refreshChatList(undefined, true),
        refreshProjects(),
      ]);
    };
    setDialog({
      title: t('chatList.automation.deleteTaskTitle', { name: job.name }),
      message: t('chatList.automation.deleteTaskMessage'),
      actions: [
        { label: t('common.cancel') },
        { label: t('chatList.menu.delete'), tone: 'danger', onClick: deleteTask },
      ],
    });
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffInHours = (now.getTime() - date.getTime()) / (1000 * 60 * 60);
    if (diffInHours < 24) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (diffInHours < 24 * 7) {
      return date.toLocaleDateString([], { weekday: 'short' });
    } else {
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }
  };

  // ── Project expansion / creation ──

  const handleSelectFilter = (id: string) => {
    setFilterId(id);
    // Expanding a project also makes it the destination for new chats.
    if (id !== ALL_PROJECTS_FILTER) setCurrentProjectId(id);
    setCreatingProjectInline(false);
  };

  const handleCreateProjectInline = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newProjectName.trim();
    if (!name) return;
    const project = await createProject(name);
    if (project) {
      setCurrentProjectId(project.id);
      setFilterId(project.id);
    }
    setNewProjectName('');
    setCreatingProjectInline(false);
  };

  const formatNextRun = (dateString: string): string => {
    const date = new Date(dateString);
    const now = new Date();
    const sameDay =
      date.getFullYear() === now.getFullYear()
      && date.getMonth() === now.getMonth()
      && date.getDate() === now.getDate();
    return date.toLocaleString([], sameDay
      ? { hour: '2-digit', minute: '2-digit' }
      : { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  // ── Move chat to project ──

  const handleMoveChatToProject = async (chatId: string, projectId: string) => {
    const chat =
      chatsRef.current.find(c => c.id === chatId) ??
      projectChatsRef.current.find(c => c.id === chatId);
    if (!chat || chat.projectId === projectId) return;
    const ok = await moveChat(chatId, projectId, chat.projectId);
    if (ok) {
      await Promise.all([
        refreshChatList(undefined, true),
        refreshProjects(),
        filterId !== ALL_PROJECTS_FILTER ? fetchProjectChats(filterId) : undefined,
      ]);
    }
  };

  // ── Render ──

  const platformLabel = (platform?: string | null) => {
    if (!platform) return null;
    if (platform.toLowerCase() === 'cron') return t('chatList.kind.scheduled');
    return platform.toLowerCase().replace(/^\w/, c => c.toUpperCase());
  };

  const openChatMenu = (
    chatId: string,
    anchor: { x: number; y: number } | { rect: DOMRect },
  ) => {
    setOpenMenu({ chatId, anchor });
  };

  const renderChatRow = (chat: ChatSummary, showProject = false, nested = false) => {
    const unread = unreadMessages(chat);
    const showUnread = currentChatId !== chat.id && unread > 0;
    const chatKind = getChatKind(chat);
    const parentTitle = chat.parentChatId
      ? filteredChats.find(item => item.id === chat.parentChatId)?.title
        ?? chats.find(item => item.id === chat.parentChatId)?.title
      : null;
    const childSubagents = subagentsByParent.get(chat.id) ?? [];
    const hasCollapsedChildren = childSubagents.length > 0;
    const childrenExpanded = expandedSubagentParents.has(chat.id);
    const rowSurface = currentChatId === chat.id
      ? 'bg-yellow-50 dark:bg-zinc-700 border-neutral-200 dark:border-zinc-600 shadow-[inset_3px_0_0_var(--brutal-yellow)]'
      : chat.heartbeatEnabled
        ? 'bg-yellow-50 border-neutral-200 dark:bg-zinc-800 dark:border-zinc-700 shadow-[inset_4px_0_0_var(--brutal-yellow)] hover:bg-yellow-100/70 dark:hover:bg-zinc-700/80'
        : chatKind === 'subagent'
          ? 'bg-neutral-50 border-neutral-200 dark:bg-zinc-800/80 dark:border-zinc-700 hover:bg-neutral-100 dark:hover:bg-zinc-700/80'
          : chatKind === 'scheduled'
            ? 'border-neutral-200 dark:border-zinc-700 hover:bg-neutral-50 dark:hover:bg-zinc-700/80'
            : isUnread(chat)
              ? 'bg-white border-neutral-200 dark:bg-zinc-800 dark:border-zinc-700 shadow-[inset_4px_0_0_#000] dark:shadow-[inset_4px_0_0_var(--brutal-yellow)] hover:bg-neutral-50 dark:hover:bg-zinc-700/80'
              : 'border-neutral-200 dark:border-zinc-700 hover:bg-neutral-50 dark:hover:bg-zinc-700/80 hover:border-neutral-300 dark:hover:border-zinc-600';
    return (
      <div
        key={chat.id}
        onClick={() => {
          if (renamingChatId) return;
          markRead(chat.id);
          loadChat(chat.id);
          if (switchToView) switchToView('chat');
        }}
        onContextMenu={(e) => {
          if (renamingChatId) return;
          e.preventDefault();
          e.stopPropagation();
          openChatMenu(chat.id, { x: e.clientX, y: e.clientY });
        }}
        className={`group relative py-2 transition-all border-b last:border-b-0
          ${chatKind === 'subagent' ? (nested ? 'pl-10 pr-3' : 'pl-8 pr-3.5') : (nested ? 'pl-8 pr-3' : 'px-3.5')}
          ${renamingChatId ? (renamingChatId === chat.id ? 'cursor-default' : 'opacity-50 pointer-events-none') : 'cursor-pointer'}
          ${rowSurface}`}
      >
        {renamingChatId === chat.id && (
          <form
            className="absolute inset-0 z-20 flex items-center gap-1 px-2 bg-white dark:bg-zinc-800 border-2 border-brutal-black dark:border-brutal-yellow"
            onSubmit={(e) => handleRenameSubmit(chat.id, e)}
            onClick={(e) => e.stopPropagation()}
          >
            <input
              autoFocus
              type="text"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Escape') handleRenameCancel(e); }}
              className="flex-1 min-w-0 px-2 py-1 text-xs font-bold bg-neutral-50 dark:bg-zinc-700 dark:text-white border-2 border-brutal-black focus:outline-none"
              placeholder={t('chatList.rename.placeholder')}
            />
            <button type="submit" className="px-2 py-1 text-[10px] font-extrabold uppercase border-2 border-brutal-black bg-brutal-yellow hover:bg-yellow-300 text-brutal-black transition-colors shrink-0">
              {t('chatList.rename.confirm')}
            </button>
            <button type="button" onClick={handleRenameCancel} className="px-2 py-1 text-[10px] font-extrabold uppercase border-2 border-brutal-black bg-white dark:bg-zinc-700 dark:text-white hover:bg-neutral-100 transition-colors shrink-0">
              {t('chatList.rename.cancel')}
            </button>
          </form>
        )}

        <div className="min-w-0 space-y-1 pr-8">
          <div className="flex items-start gap-2 overflow-hidden">
            <h3 className={`font-extrabold text-xs leading-snug truncate flex-1 min-w-0 transition-colors ${currentChatId === chat.id ? 'text-brutal-black dark:text-white' : isUnread(chat) ? 'text-neutral-950 dark:text-white' : 'text-neutral-800 dark:text-neutral-100 group-hover:text-brutal-black dark:group-hover:text-white'}`}>
              {chat.title || t('chatList.untitled')}
            </h3>
            {showUnread && (
              <span className="text-[10px] font-extrabold min-w-[20px] h-5 px-1.5 flex items-center justify-center rounded-sm bg-brutal-yellow text-brutal-black border-2 border-brutal-black leading-none shrink-0 shadow-[1px_1px_0_0_rgba(0,0,0,1)]">
                {unread > 99 ? '99+' : unread}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 overflow-hidden">
            {/* Project chip — always shown so the user knows which workspace */}
            {showProject && chat.projectName && (
              <span
                className={`inline-flex items-center h-5 px-2 text-[10px] font-extrabold uppercase tracking-wide border shrink-0 max-w-[8rem] truncate ${
                  currentChatId === chat.id
                    ? 'bg-white/80 text-brutal-black border-brutal-black dark:bg-zinc-900 dark:text-brutal-yellow dark:border-brutal-yellow'
                    : 'bg-neutral-100 text-neutral-600 border-neutral-300 dark:bg-zinc-700 dark:text-neutral-300 dark:border-zinc-500'
                }`}
                title={chat.projectName}
              >
                {chat.projectName}
              </span>
            )}
            {chat.platform && (
              <span className={`inline-flex items-center h-5 px-2 rounded-sm text-[10px] font-extrabold uppercase tracking-wide border shrink-0 ${currentChatId === chat.id ? 'bg-white/80 text-brutal-black border-brutal-black dark:bg-zinc-900 dark:text-brutal-yellow dark:border-brutal-yellow' : 'bg-neutral-100 text-neutral-700 border-neutral-300 dark:bg-zinc-700 dark:text-neutral-200 dark:border-zinc-500'}`}>
                {platformLabel(chat.platform)}
              </span>
            )}
            {chat.heartbeatEnabled && (
              <span
                className={`shrink-0 flex items-center gap-1 h-5 px-1.5 rounded-sm border text-[9px] font-extrabold uppercase tracking-wide ${currentChatId === chat.id ? 'bg-white/80 text-brutal-black border-brutal-black dark:bg-zinc-900 dark:text-brutal-yellow dark:border-brutal-yellow' : 'bg-brutal-yellow text-brutal-black border-brutal-black transition-all'}`}
                title={t('chatWindow.heartbeatEnabled')}
              >
                <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="square" strokeLinejoin="miter">
                  <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                </svg>
                <span>{t('chatList.labels.heartbeat')}</span>
              </span>
            )}
            {hasCollapsedChildren && (
              <button
                type="button"
                aria-expanded={childrenExpanded}
                onClick={(event) => {
                  event.stopPropagation();
                  toggleSubagentParent(chat.id);
                }}
                className={`inline-flex items-center h-4 px-1.5 border text-[9px] font-extrabold uppercase tracking-wide shrink-0 transition-colors ${
                  childrenExpanded
                    ? 'border-brutal-black bg-brutal-yellow text-brutal-black'
                    : 'border-neutral-300 bg-neutral-100 text-neutral-600 hover:border-brutal-black dark:border-zinc-600 dark:bg-zinc-700 dark:text-neutral-300'
                }`}
              >
                {t('chatList.labels.subagentsCount', { count: childSubagents.length })}
              </button>
            )}
            {chatKind === 'subagent' && parentTitle && (
              <span className="text-[9px] font-bold uppercase text-neutral-400 dark:text-neutral-500 truncate">
                {t('chatList.labels.subagentOf', { name: parentTitle })}
              </span>
            )}
            <span className={`text-[10px] font-bold uppercase ml-auto shrink-0 ${currentChatId === chat.id ? 'text-brutal-black/70 dark:text-brutal-yellow' : 'text-neutral-400 dark:text-neutral-500'}`}>
              {formatDate(chat.updatedAt)}
            </span>
          </div>
        </div>

        {/* Three-dot menu button — appears on hover; right-click anywhere on the row also opens it */}
        <button
          type="button"
          aria-label={t('chatList.menu.title')}
          title={t('chatList.menu.title')}
          onClick={(e) => {
            e.stopPropagation();
            const rect = (e.currentTarget as HTMLButtonElement).getBoundingClientRect();
            openChatMenu(chat.id, { rect });
          }}
          onContextMenu={(e) => {
            if (renamingChatId) return;
            e.preventDefault();
            e.stopPropagation();
            const rect = (e.currentTarget as HTMLButtonElement).getBoundingClientRect();
            openChatMenu(chat.id, { rect });
          }}
          className={`absolute right-2 top-1/2 -translate-y-1/2 p-1.5 transition-opacity flex items-center justify-center text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white hover:bg-neutral-200 dark:hover:bg-zinc-600 ${
            openMenu?.chatId === chat.id
              ? 'opacity-100 bg-neutral-200 dark:bg-zinc-600 text-brutal-black dark:text-white'
              : 'opacity-0 group-hover:opacity-100 focus:opacity-100'
          }`}
        >
          <MoreActionsIcon />
        </button>
      </div>
    );
  };

  const renderListSkeleton = () => (
    <div className="p-4 bg-white dark:bg-zinc-800">
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-16 bg-neutral-300 border-3 border-brutal-black animate-brutal-blink"></div>
        ))}
      </div>
    </div>
  );

  if (loadingChats) {
    return (
      <div className="p-4">
        {renderListSkeleton()}
      </div>
    );
  }

  const filteredTotal = filterId === ALL_PROJECTS_FILTER ? chatTotal : projectChatKindTotals.all;
  const remaining = Math.max(0, filteredTotal - filteredChats.length);
  const isSearching = localSearchQuery.trim().length > 0;
  const visibleCronJobs = [...cronJobs]
    .sort((left, right) => {
      const leftPriority = left.last_error && !isCronFailureHandledInChat(left) ? 0 : left.active ? 1 : 2;
      const rightPriority = right.last_error && !isCronFailureHandledInChat(right) ? 0 : right.active ? 1 : 2;
      if (leftPriority !== rightPriority) return leftPriority - rightPriority;
      const leftNext = left.next_run_at ? new Date(left.next_run_at).getTime() : Number.MAX_SAFE_INTEGER;
      const rightNext = right.next_run_at ? new Date(right.next_run_at).getTime() : Number.MAX_SAFE_INTEGER;
      return leftNext - rightNext;
    })
    .slice(0, AUTOMATION_PREVIEW_LIMIT);
  const heartbeatSessions = heartbeatStatus?.active_sessions ?? [];
  const showAutomation = loadingAutomation || cronJobs.length > 0 || heartbeatSessions.length > 0;

  const openChatById = (chatId: string): void => {
    markRead(chatId);
    loadChat(chatId);
    if (switchToView) switchToView('chat');
  };

  return (
    <div ref={sidebarBoundsRef} className="flex flex-col h-full relative">
      {showRefreshIndicator && (
        <div className="absolute top-0 left-0 right-0 z-20 pointer-events-none">
          <div className="h-1 bg-brutal-blue animate-brutal-blink"></div>
        </div>
      )}

      {/* Header: Search + New Chat */}
      <div className="p-3 bg-white dark:bg-zinc-800 flex-shrink-0 space-y-2.5">
        <div className="flex items-stretch gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={localSearchQuery}
              onChange={(e) => setLocalSearchQuery(e.target.value)}
              placeholder={t('chatList.searchChatsPlaceholder').toUpperCase()}
              className="h-10 w-full px-3 pl-9 bg-neutral-50 dark:bg-zinc-700 dark:text-white dark:placeholder-neutral-500 border-2 border-brutal-black font-bold text-xs uppercase placeholder-neutral-400 focus:outline-none focus:bg-white dark:focus:bg-zinc-600 focus:shadow-[inset_3px_0_0_var(--brutal-yellow)] transition-all"
            />
            <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-brutal-black dark:text-neutral-400 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            {localSearchQuery && (
              <button
                onClick={() => setLocalSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-neutral-200 dark:hover:bg-zinc-600 rounded transition-colors"
                title={t('chatList.clearSearch')}
              >
                <svg className="w-3 h-3 text-brutal-black dark:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
          <BrutalButton
            type="button"
            variant="primary"
            size="icon"
            onClick={() => { beginNewChat(); if (switchToView) switchToView('chat'); }}
            className="!h-10 !w-10 !flex-shrink-0 !p-0"
            title={t('chatList.newChat')}
            aria-label={t('chatList.newChat')}
          >
            <PencilSquareIcon className="h-5 w-5 stroke-[2.4]" />
          </BrutalButton>
        </div>

      </div>

      <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin bg-white dark:bg-zinc-800">
        {isSearching ? (
          <section>
            <div className="flex items-center justify-between px-3 py-2 border-y-2 border-brutal-black bg-white dark:bg-zinc-800">
              <h2 className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-neutral-400 dark:text-neutral-500">
                {t('chatList.sections.searchResults')}
              </h2>
              <span className="text-[10px] font-bold tabular-nums text-neutral-500 dark:text-neutral-400">
                {chatTotal}
              </span>
            </div>
            {chats.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <RobotAvatar variant="ghost" />
                <p className="mt-3 text-xs font-extrabold uppercase text-brutal-black dark:text-white">
                  {t('chatList.empty.noResultsTitle')}
                </p>
                <p className="mt-1 text-[10px] text-neutral-500 dark:text-neutral-400">
                  {t('chatList.empty.noResultsDesc')}
                </p>
              </div>
            ) : (
              <div>{chats.map(chat => renderChatRow(chat, true))}</div>
            )}
            {chatTotal > chats.length && (
              <button
                type="button"
                onClick={() => void loadMoreChats()}
                disabled={loadingMoreChats}
                className="w-full py-3 border-t border-neutral-200 dark:border-zinc-700 text-[10px] font-extrabold uppercase text-neutral-500 hover:bg-neutral-50 hover:text-brutal-black dark:hover:bg-zinc-700 dark:hover:text-white disabled:opacity-50"
              >
                {loadingMoreChats ? t('chatList.loadingMore') : t('chatList.loadMore', { count: chatTotal - chats.length })}
              </button>
            )}
          </section>
        ) : (
          <div className="flex flex-col">
            {showAutomation && (
              <section className="order-2 border-t border-neutral-200 dark:border-zinc-700">
                <div className="flex items-center justify-between px-3 py-1.5">
                  <h2 className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-neutral-400 dark:text-neutral-500">
                    {t('chatList.sections.tasks')}
                  </h2>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[9px] font-bold tabular-nums text-neutral-400 dark:text-neutral-500">
                      {cronJobs.length + heartbeatSessions.length}
                    </span>
                  </div>
                </div>

                {loadingAutomation ? (
                  <div className="border-t border-neutral-200 dark:border-zinc-700">
                    <div className="h-11 border-b border-neutral-200 bg-neutral-100 dark:border-zinc-700 dark:bg-zinc-700 animate-pulse" />
                    <div className="h-11 border-b border-neutral-200 bg-neutral-100 dark:border-zinc-700 dark:bg-zinc-700 animate-pulse" />
                  </div>
                ) : (
                  <div className="border-t border-neutral-200 dark:border-zinc-700">
                    {cronJobs.length > 0 && (
                      <div className="border-b border-neutral-200 bg-white dark:border-zinc-700 dark:bg-zinc-800">
                        <div>
                            {visibleCronJobs.map(job => {
                              const chatId = `cron-${job.id}`;
                              const canOpen = !!job.last_run_at;
                              const failureHandled = isCronFailureHandledInChat(job);
                              const unresolvedError = job.last_error && !failureHandled ? job.last_error : null;
                              const subtitle = !job.active
                                ? unresolvedError
                                  ? `${t('chatList.automation.paused')} · ${unresolvedError}`
                                  : t('chatList.automation.paused')
                                : unresolvedError
                                  ? t('chatList.automation.lastRunFailed', { error: unresolvedError })
                                  : job.next_run_at
                                    ? t('chatList.automation.nextRunAt', { time: formatNextRun(job.next_run_at) })
                                    : t('chatList.automation.active');
                              const latestActivityAt = failureHandled
                                ? job.chat_updated_at
                                : job.last_run_at;
                              return (
                                <div
                                  key={job.id}
                                  onContextMenu={(event) => {
                                    event.preventDefault();
                                    setTaskMenu({ jobId: job.id, anchor: { rect: event.currentTarget.getBoundingClientRect() } });
                                  }}
                                  className={`group/task relative min-h-11 border-b border-neutral-200 transition-colors dark:border-zinc-700 ${
                                    currentChatId === chatId
                                      ? 'bg-yellow-50 shadow-[inset_3px_0_0_var(--brutal-yellow)] dark:bg-zinc-700'
                                      : 'bg-white hover:bg-neutral-50 dark:bg-zinc-800 dark:hover:bg-zinc-700'
                                  }`}
                                >
                                  {renamingTaskId === job.id ? (
                                    <form
                                      className="flex min-h-11 items-center gap-1 px-2"
                                      onSubmit={(event) => void handleTaskRenameSubmit(job, event)}
                                    >
                                      <input
                                        autoFocus
                                        value={taskRenameValue}
                                        onChange={(event) => setTaskRenameValue(event.target.value)}
                                        onKeyDown={(event) => {
                                          if (event.key === 'Escape') setRenamingTaskId(null);
                                        }}
                                        className="min-w-0 flex-1 border-2 border-brutal-black bg-white px-2 py-1 text-xs font-bold focus:outline-none dark:bg-zinc-700 dark:text-white"
                                      />
                                      <button type="submit" className="border-2 border-brutal-black bg-brutal-yellow px-2 py-1 text-[10px] font-extrabold">✓</button>
                                      <button type="button" onClick={() => setRenamingTaskId(null)} className="border-2 border-brutal-black bg-white px-2 py-1 text-[10px] font-extrabold dark:bg-zinc-700 dark:text-white">✕</button>
                                    </form>
                                  ) : (
                                    <>
                                      <button
                                        type="button"
                                        disabled={!canOpen && !onOpenAutomation}
                                        onClick={() => canOpen ? openChatById(chatId) : onOpenAutomation?.()}
                                        title={unresolvedError ?? job.last_result ?? undefined}
                                        className="grid min-h-11 w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-2 bg-transparent px-3.5 py-2 pr-10 text-left disabled:cursor-default"
                                      >
                                        <span className="min-w-0">
                                          <span className="block truncate text-xs font-extrabold leading-tight text-brutal-black dark:text-white">{job.name}</span>
                                          <span className={`block truncate text-[9px] font-bold leading-tight ${unresolvedError ? 'text-red-600 dark:text-red-400' : 'text-neutral-500 dark:text-neutral-400'}`}>
                                            {subtitle}
                                          </span>
                                        </span>
                                        <span className="shrink-0 text-[9px] font-bold uppercase text-neutral-400 dark:text-neutral-500">
                                          {latestActivityAt ? formatDate(latestActivityAt) : t('chatList.automation.notYet')}
                                        </span>
                                      </button>
                                      <button
                                        type="button"
                                        aria-label={t('chatList.menu.title')}
                                        title={t('chatList.menu.title')}
                                        onClick={(event) => {
                                          event.stopPropagation();
                                          setTaskMenu({ jobId: job.id, anchor: { rect: event.currentTarget.getBoundingClientRect() } });
                                        }}
                                        className={`absolute right-1.5 top-1/2 flex -translate-y-1/2 items-center justify-center p-1 text-neutral-500 transition-opacity hover:bg-neutral-200 hover:text-brutal-black dark:text-neutral-400 dark:hover:bg-zinc-600 dark:hover:text-white ${
                                          taskMenu?.jobId === job.id ? 'opacity-100' : 'opacity-0 group-hover/task:opacity-100 focus:opacity-100'
                                        }`}
                                      >
                                        <MoreActionsIcon />
                                      </button>
                                    </>
                                  )}
                                </div>
                              );
                            })}
                          {cronJobs.length > AUTOMATION_PREVIEW_LIMIT && onOpenAutomation && (
                            <button
                              type="button"
                              onClick={onOpenAutomation}
                              className="w-full px-3 py-2.5 text-[9px] font-extrabold uppercase tracking-wide text-brutal-blue border-b border-neutral-200 hover:bg-brutal-yellow hover:text-brutal-black dark:border-zinc-700 dark:text-brutal-yellow"
                            >
                              {t('chatList.automation.viewAllScheduled', { count: cronJobs.length })}
                            </button>
                          )}
                        </div>
                      </div>
                    )}

                    {heartbeatSessions.length > 0 && (
                      <div className="border-b border-neutral-200 bg-white dark:border-zinc-700 dark:bg-zinc-800">
                        <div>
                          {heartbeatSessions.slice(0, AUTOMATION_PREVIEW_LIMIT).map(session => (
                              <button
                                key={session.chat_id}
                                type="button"
                                onClick={() => openChatById(session.chat_id)}
                                className={`w-full min-h-11 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 px-3.5 py-2 text-left border-b border-neutral-200 transition-colors dark:border-zinc-700 ${
                                  currentChatId === session.chat_id
                                    ? 'bg-yellow-50 shadow-[inset_3px_0_0_var(--brutal-yellow)] dark:bg-zinc-700'
                                    : 'bg-white hover:bg-neutral-50 dark:bg-zinc-800 dark:hover:bg-zinc-700'
                                }`}
                              >
                                <span className="min-w-0">
                                  <span className="block text-xs leading-tight font-extrabold truncate text-brutal-black dark:text-white">{session.title}</span>
                                  <span className="block text-[9px] leading-tight font-bold text-neutral-500 dark:text-neutral-400">
                                    {t('chatList.automation.everyMinutes', { minutes: session.interval_minutes })}
                                  </span>
                                </span>
                                <span className="text-[9px] font-extrabold uppercase text-neutral-500 dark:text-neutral-400">
                                  {session.last_run_at ? formatDate(session.last_run_at) : t('chatList.automation.notYet')}
                                </span>
                              </button>
                          ))}
                          {heartbeatSessions.length > AUTOMATION_PREVIEW_LIMIT && (
                            <div className="px-3 py-2.5 text-center text-[9px] font-extrabold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                              {t('chatList.automation.moreHeartbeat', { count: heartbeatSessions.length - AUTOMATION_PREVIEW_LIMIT })}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </section>
            )}

            <section className="relative order-1 border-t-2 border-brutal-black">
              <div ref={organizationMenuRef} className="relative flex items-center justify-between px-3 py-1.5">
                <h2 className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-neutral-400 dark:text-neutral-500">
                  {organization === 'projects' ? t('chatList.sections.projects') : t('chatList.sections.chats')}
                </h2>
                <div className="flex items-center gap-0.5">
                  <button
                    type="button"
                    onClick={() => setOrganizationMenuOpen(value => !value)}
                    className="flex h-6 w-6 items-center justify-center text-neutral-500 hover:bg-neutral-100 hover:text-brutal-black dark:text-neutral-400 dark:hover:bg-zinc-700 dark:hover:text-white"
                    title={t('chatList.organization.title')}
                    aria-label={t('chatList.organization.title')}
                    aria-expanded={organizationMenuOpen}
                  >
                    <MoreActionsIcon />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (organization === 'list') selectOrganization('projects');
                      setCreatingProjectInline(true);
                    }}
                    className="w-6 h-6 flex items-center justify-center text-neutral-500 hover:bg-brutal-yellow hover:text-brutal-black dark:text-neutral-400"
                    title={t('chatList.newProject')}
                    aria-label={t('chatList.newProject')}
                  >
                    <PlusIcon className="w-4 h-4 stroke-[3]" />
                  </button>
                </div>
                {organizationMenuOpen && (
                  <div
                    role="menu"
                    className="absolute right-3 top-8 z-30 min-w-[180px] border-2 border-brutal-black bg-white py-1 shadow-[3px_3px_0_0_#000] dark:bg-zinc-800"
                  >
                    <div className="px-3 py-1.5 text-[9px] font-extrabold uppercase tracking-[0.14em] text-neutral-400 dark:text-neutral-500">
                      {t('chatList.organization.title')}
                    </div>
                    {(['projects', 'list'] as const).map(mode => (
                      <button
                        key={mode}
                        type="button"
                        role="menuitemradio"
                        aria-checked={organization === mode}
                        onClick={() => selectOrganization(mode)}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-bold text-brutal-black hover:bg-brutal-yellow dark:text-white dark:hover:text-brutal-black"
                      >
                        <span className="flex h-4 w-4 items-center justify-center">
                          {organization === mode && <CheckIcon className="h-4 w-4 stroke-[2.5]" />}
                        </span>
                        {mode === 'projects'
                          ? t('chatList.organization.byProject')
                          : t('chatList.organization.singleList')}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {organization === 'projects' ? (
                <>
              {creatingProjectInline && (
                <form onSubmit={handleCreateProjectInline} className="flex items-center gap-1 px-3 pb-2">
                  <input
                    autoFocus
                    type="text"
                    value={newProjectName}
                    onChange={(event) => setNewProjectName(event.target.value)}
                    onKeyDown={(event) => { if (event.key === 'Escape') { setCreatingProjectInline(false); setNewProjectName(''); } }}
                    placeholder={t('chatList.newProjectPlaceholder')}
                    className="flex-1 min-w-0 px-2 py-1.5 text-xs font-bold bg-white dark:bg-zinc-700 dark:text-white border-2 border-brutal-black focus:outline-none"
                  />
                  <button type="submit" className="px-2 py-1.5 text-[10px] font-extrabold border-2 border-brutal-black bg-brutal-yellow">✓</button>
                  <button type="button" onClick={() => { setCreatingProjectInline(false); setNewProjectName(''); }} className="px-2 py-1.5 text-[10px] font-extrabold border-2 border-brutal-black bg-white dark:bg-zinc-700 dark:text-white">✕</button>
                </form>
              )}

              <div>
                {projects.map(project => {
                  const isOpen = filterId === project.id;
                  const isSystem = project.slug === 'default' || project.slug === 'social';
                  const isRenaming = renamingProjectId === project.id;
                  return (
                    <div key={project.id} className="border-t border-neutral-200 dark:border-zinc-700">
                      <div className={`group/proj grid min-h-10 grid-cols-[minmax(0,1fr)_28px] ${isOpen ? 'bg-yellow-50/70 shadow-[inset_3px_0_0_var(--brutal-yellow)] dark:bg-zinc-700' : ''}`}>
                        {isRenaming ? (
                          <form
                            className="col-span-2 flex items-center gap-1 px-2 py-1"
                            onSubmit={async (event) => {
                              event.preventDefault();
                              const trimmed = projectRenameValue.trim();
                              if (trimmed && trimmed !== project.name) await renameProject(project.id, trimmed);
                              setRenamingProjectId(null);
                            }}
                          >
                            <input
                              autoFocus
                              value={projectRenameValue}
                              onChange={(event) => setProjectRenameValue(event.target.value)}
                              onKeyDown={(event) => { if (event.key === 'Escape') setRenamingProjectId(null); }}
                              className="flex-1 min-w-0 px-2 py-1 text-xs font-bold bg-white dark:bg-zinc-700 dark:text-white border-2 border-brutal-black focus:outline-none"
                            />
                            <button type="submit" className="px-2 py-1 text-[10px] font-extrabold border-2 border-brutal-black bg-brutal-yellow">✓</button>
                            <button type="button" onClick={() => setRenamingProjectId(null)} className="px-2 py-1 text-[10px] font-extrabold border-2 border-brutal-black bg-white dark:bg-zinc-700 dark:text-white">✕</button>
                          </form>
                        ) : (
                          <>
                            <button
                              type="button"
                              aria-expanded={isOpen}
                              onClick={() => isOpen ? setFilterId(ALL_PROJECTS_FILTER) : handleSelectFilter(project.id)}
                              className="min-w-0 grid grid-cols-[18px_minmax(0,1fr)_28px] items-center gap-2 pl-3 pr-2 py-1.5 text-left hover:bg-neutral-50 dark:hover:bg-zinc-700"
                            >
                              <FolderIcon className="w-[18px] h-[18px] stroke-[2.2] text-brutal-black dark:text-white" />
                              <span className="min-w-0 truncate text-[11px] font-extrabold text-brutal-black dark:text-white">{project.name}</span>
                              <span className="text-right text-[10px] font-bold tabular-nums text-neutral-500 dark:text-neutral-400">{project.chatCount}</span>
                            </button>
                            {!isSystem && (
                              <button
                                type="button"
                                aria-label={t('chatList.menu.title')}
                                title={t('chatList.menu.title')}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  const rect = event.currentTarget.getBoundingClientRect();
                                  setProjectMenu({ projectId: project.id, anchor: { rect } });
                                }}
                                className={`w-7 flex items-center justify-center hover:bg-neutral-100 dark:hover:bg-zinc-600 ${projectMenu?.projectId === project.id ? 'opacity-100' : 'opacity-0 group-hover/proj:opacity-100 focus:opacity-100'}`}
                              >
                                <MoreActionsIcon />
                              </button>
                            )}
                            {isSystem && <span aria-hidden="true" />}
                          </>
                        )}
                      </div>

                      {isOpen && (
                        <div className="bg-neutral-50/50 dark:bg-zinc-900/20">
                          {loadingProjectChats ? (
                            renderListSkeleton()
                          ) : visibleChats.length === 0 ? (
                            <div className="px-4 py-6 text-center text-[10px] font-bold uppercase text-neutral-400">
                              {t('chatList.empty.noChatsTitle')}
                            </div>
                          ) : (
                            <>
                              {visibleChats
                                .filter(chat => getChatKind(chat) !== 'scheduled')
                                .map(chat => renderChatRow(chat, false, true))}
                              {remaining > 0 && (
                                <button
                                  type="button"
                                  onClick={() => void handleLoadMore()}
                                  disabled={loadingMoreProjectChats}
                                  className="w-full py-2.5 border-t border-neutral-200 dark:border-zinc-700 text-[10px] font-extrabold uppercase text-neutral-500 hover:bg-neutral-50 hover:text-brutal-black dark:hover:bg-zinc-700 dark:hover:text-white disabled:opacity-50"
                                >
                                  {loadingMoreProjectChats ? t('chatList.loadingMore') : t('chatList.loadMore', { count: remaining })}
                                </button>
                              )}
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
                </>
              ) : (
                <div className="border-t border-neutral-200 dark:border-zinc-700">
                  {visibleChats
                    .filter(chat => getChatKind(chat) !== 'scheduled')
                    .map(chat => renderChatRow(chat, true))}
                  {remaining > 0 && (
                    <button
                      type="button"
                      onClick={() => void handleLoadMore()}
                      disabled={loadingMoreChats}
                      className="w-full border-t border-neutral-200 py-2.5 text-[10px] font-extrabold uppercase text-neutral-500 hover:bg-neutral-50 hover:text-brutal-black disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-700 dark:hover:text-white"
                    >
                      {loadingMoreChats ? t('chatList.loadingMore') : t('chatList.loadMore', { count: remaining })}
                    </button>
                  )}
                </div>
              )}
            </section>
          </div>
        )}
      </div>

      {/* Floating row menu (portalled, never clipped) */}
      {openMenu && (() => {
        const chat =
          chatsRef.current.find(c => c.id === openMenu.chatId) ??
          projectChatsRef.current.find(c => c.id === openMenu.chatId);
        if (!chat) return null;
        return (
          <ChatRowMenu
            anchor={openMenu.anchor}
            boundary={sidebarBoundsRef.current?.getBoundingClientRect() ?? null}
            projects={projects}
            currentProjectId={chat.projectId ?? undefined}
            onRename={() => {
              setRenamingChatId(chat.id);
              setRenameValue(chat.title || '');
            }}
            onDelete={() => { setOpenMenu(null); handleRequestDelete(chat.id); }}
            onMoveToProject={(pid) => handleMoveChatToProject(chat.id, pid)}
            onClose={() => setOpenMenu(null)}
          />
        );
      })()}

      {taskMenu && (() => {
        const job = cronJobs.find(item => item.id === taskMenu.jobId);
        if (!job) return null;
        return (
          <ProjectRowMenu
            anchor={taskMenu.anchor}
            boundary={sidebarBoundsRef.current?.getBoundingClientRect() ?? null}
            rootDataAttrs={{ 'data-popover-source': 'task-row' }}
            onRename={() => {
              setTaskRenameValue(job.name);
              setRenamingTaskId(job.id);
            }}
            onDelete={() => handleRequestTaskDelete(job)}
            onClose={() => setTaskMenu(null)}
          />
        );
      })()}

      {/* Modal dialog (replaces window.alert / window.confirm) */}
      <BrutalDialog
        open={dialog !== null}
        title={dialog?.title}
        message={dialog?.message ?? ''}
        actions={dialog?.actions ?? []}
        onClose={() => setDialog(null)}
        rootDataAttrs={{ 'data-popover-source': 'project-filter' }}
      />

      {/* Floating project menu */}
      {projectMenu && (() => {
        const p = projects.find(pr => pr.id === projectMenu.projectId);
        if (!p) return null;
        return (
          <ProjectRowMenu
            anchor={projectMenu.anchor}
            boundary={sidebarBoundsRef.current?.getBoundingClientRect() ?? null}
            rootDataAttrs={{ 'data-popover-source': 'project-filter' }}
            onRename={() => {
              setProjectRenameValue(p.name);
              setRenamingProjectId(p.id);
            }}
            onDelete={() => {
              // Always allow delete. If the project has chats, prompt the user
              // to confirm — chats will be moved to the default project first.
              const fallback = projects.find(pr => pr.slug === 'default');
              const finalizeDelete = async () => {
                const result = await deleteProject(p.id);
                if (!result.success) {
                  setDialog({
                    title: p.name,
                    message: result.error || t('chatList.menu.deleteFailed'),
                    actions: [{ label: t('common.ok'), tone: 'primary' }],
                  });
                  return;
                }
                if (filterId === p.id) setFilterId(ALL_PROJECTS_FILTER);
                await Promise.all([refreshChatList(undefined, true), refreshProjects()]);
              };

              if (p.chatCount === 0) {
                setDialog({
                  title: t('chatList.menu.deleteConfirmTitle', { name: p.name }),
                  message: t('chatList.menu.deleteConfirmEmpty'),
                  actions: [
                    { label: t('common.cancel') },
                    { label: t('chatList.menu.delete'), tone: 'danger', onClick: finalizeDelete },
                  ],
                });
                return;
              }

              if (!fallback) {
                setDialog({
                  title: p.name,
                  message: t('chatList.menu.deleteFailed'),
                  actions: [{ label: t('common.ok'), tone: 'primary' }],
                });
                return;
              }

              setDialog({
                title: t('chatList.menu.deleteConfirmTitle', { name: p.name }),
                message: t('chatList.menu.deleteConfirmWithChats', {
                  count: p.chatCount,
                  target: fallback.name,
                }),
                actions: [
                  { label: t('common.cancel') },
                  {
                    label: t('chatList.menu.delete'),
                    tone: 'danger',
                    onClick: async () => {
                      const moveResult = await moveAllChats(p.id, fallback.id);
                      if (!moveResult.success) {
                        setDialog({
                          title: p.name,
                          message: moveResult.error || t('chatList.menu.deleteFailed'),
                          actions: [{ label: t('common.ok'), tone: 'primary' }],
                        });
                        return;
                      }
                      await finalizeDelete();
                    },
                  },
                ],
              });
            }}
            onClose={() => setProjectMenu(null)}
          />
        );
      })()}
    </div>
  );
};

// Project type imported for completeness; not used here directly.
export type _ProjectMarker = Project;
