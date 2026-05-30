import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useChatStore } from '../hooks/useChatStore';
import { useProjects } from '../hooks/useProjects';
import { ChatSummary, Project } from '../types/api';
import { RobotAvatar } from './chat/RobotAvatar';
import { useI18n } from '../i18n';
import { getApiBase, markChatRead } from '../lib/api';
import { ChatRowMenu } from './ChatRowMenu';
import { ProjectRowMenu } from './ProjectRowMenu';
import { BrutalDialog } from './BrutalDialog';

const ALL_PROJECTS_FILTER = '__all__';
type ChatKind = 'you' | 'subagent' | 'scheduled';
type ChatKindFilter = 'you' | 'scheduled' | 'all';

export const ChatList: React.FC = () => {
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

  // Project context menu (kebab inside filter dropdown)
  const [projectMenu, setProjectMenu] = useState<{
    projectId: string;
    anchor: { rect: DOMRect };
  } | null>(null);
  const [renamingProjectId, setRenamingProjectId] = useState<string | null>(null);
  const [projectRenameValue, setProjectRenameValue] = useState('');

  // Dialog state — replaces window.alert / window.confirm so we keep
  // brutalist styling and never get blocked by browser dialog rendering.
  const [dialog, setDialog] = useState<{
    title?: string;
    message: React.ReactNode;
    actions: { label: string; tone?: 'default' | 'primary' | 'danger'; onClick?: () => void | Promise<void>; preventDismiss?: boolean }[];
  } | null>(null);

  // Filter pill state
  const [filterId, setFilterId] = useState<string>(ALL_PROJECTS_FILTER);
  const [kindFilter, setKindFilter] = useState<ChatKindFilter>('you');
  const [expandedSubagentParents, setExpandedSubagentParents] = useState<Set<string>>(
    () => new Set(),
  );
  const [filterMenuOpen, setFilterMenuOpen] = useState(false);
  const [creatingProjectInline, setCreatingProjectInline] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const filterMenuRef = useRef<HTMLDivElement | null>(null);
  const filterPillRef = useRef<HTMLButtonElement | null>(null);
  const sidebarBoundsRef = useRef<HTMLDivElement | null>(null);
  const [projectChats, setProjectChats] = useState<ChatSummary[]>([]);
  const [projectChatTotal, setProjectChatTotal] = useState(0);
  const [projectChatOffset, setProjectChatOffset] = useState(0);
  const [loadingProjectChats, setLoadingProjectChats] = useState(false);
  const [loadingMoreProjectChats, setLoadingMoreProjectChats] = useState(false);

  const { t } = useI18n();

  const chatsRef = useRef(chats);
  useEffect(() => { chatsRef.current = chats; }, [chats]);
  const projectChatsRef = useRef(projectChats);
  useEffect(() => { projectChatsRef.current = projectChats; }, [projectChats]);

  // Whenever the chat list changes (create / delete / move), the server-side
  // project chat counts may be stale. Refresh them so the dropdown shows
  // accurate numbers without the user having to do anything.
  useEffect(() => {
    void refreshProjects();
  }, [chats.length, refreshProjects]);

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

  // Whenever the filter dropdown closes, also dismiss any project-row menu
  // and abandon an inline project rename so we don't leave orphan UI behind.
  useEffect(() => {
    if (filterMenuOpen) return;
    setProjectMenu(null);
    setRenamingProjectId(null);
    setCreatingProjectInline(false);
  }, [filterMenuOpen]);

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
      setProjectChatTotal(0);
      setProjectChatOffset(0);
    }

    try {
      const params = new URLSearchParams({
        limit: '50',
        offset: String(offset),
        project_id: projectId,
      });
      const search = searchQuery.trim();
      if (search) params.set('search', search);

      const res = await fetch(`${getApiBase()}/chats?${params.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      const nextChats: ChatSummary[] = data.chats || [];
      setProjectChatTotal(data.total ?? nextChats.length);
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
        setProjectChatTotal(0);
        setProjectChatOffset(0);
      }
    } finally {
      if (append) setLoadingMoreProjectChats(false);
      else setLoadingProjectChats(false);
    }
  }, [searchQuery]);

  useEffect(() => {
    if (filterId === ALL_PROJECTS_FILTER) {
      setProjectChats([]);
      setProjectChatTotal(0);
      setProjectChatOffset(0);
      return;
    }
    void fetchProjectChats(filterId);
  }, [filterId, fetchProjectChats]);

  // Close filter menu on outside click. Clicks inside the kebab popover or
  // the modal dialog (which live in portals at document.body) are treated as
  // inside, since they were spawned from the dropdown.
  useEffect(() => {
    if (!filterMenuOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Element | null;
      if (!target) return;
      const insidePill = filterPillRef.current?.contains(target);
      const insideMenu = filterMenuRef.current?.contains(target);
      const insidePortal = !!target.closest?.('[data-popover-source="project-filter"]');
      if (insidePill || insideMenu || insidePortal) return;
      setFilterMenuOpen(false);
      setCreatingProjectInline(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [filterMenuOpen]);

  // ── Filter and derived counts ──

  const filterLabel = useMemo(() => {
    if (filterId === ALL_PROJECTS_FILTER) return t('chatList.filter.all');
    return projects.find(p => p.id === filterId)?.name ?? t('chatList.filter.all');
  }, [filterId, projects, t]);

  const filteredChats = useMemo(() => {
    if (filterId === ALL_PROJECTS_FILTER) return chats;
    return projectChats;
  }, [chats, filterId, projectChats]);

  // Total used for the load-more remainder. We approximate: when filtering by
  // project we use that project's chatCount; otherwise the global total.
  const filteredTotal = useMemo(() => {
    if (filterId === ALL_PROJECTS_FILTER) return chatTotal;
    return projectChatTotal;
  }, [filterId, chatTotal, projectChatTotal]);

  const getChatKind = (chat: ChatSummary): ChatKind => {
    const platform = (chat.platform || '').toLowerCase();
    if (platform === 'subagent') return 'subagent';
    if (platform === 'cron') return 'scheduled';
    return 'you';
  };

  const kindCounts = useMemo(() => {
    const counts: Record<ChatKindFilter, number> = {
      you: 0,
      scheduled: 0,
      all: filteredChats.length,
    };
    for (const chat of filteredChats) {
      const kind = getChatKind(chat);
      if (kind === 'scheduled') counts.scheduled += 1;
      else counts.you += 1;
    }
    return counts;
  }, [filteredChats]);

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
    const source = filteredChats.filter(chat => {
      const kind = getChatKind(chat);
      if (kindFilter === 'scheduled') return kind === 'scheduled';
      if (kindFilter === 'you') return kind !== 'scheduled';
      return true;
    });

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
  }, [expandedSubagentParents, filteredChats, kindFilter, subagentsByParent]);

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

  // ── Project filter / creation ──

  const handleSelectFilter = (id: string) => {
    setFilterId(id);
    // If a real project is selected, also set it as the current project so
    // new chats land there.
    if (id !== ALL_PROJECTS_FILTER) setCurrentProjectId(id);
    setFilterMenuOpen(false);
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
    setFilterMenuOpen(false);
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

  const renderChatRow = (chat: ChatSummary) => {
    const unread = unreadMessages(chat);
    const showUnread = currentChatId !== chat.id && unread > 0;
    const chatKind = getChatKind(chat);
    const parentTitle = chat.parentChatId
      ? filteredChats.find(item => item.id === chat.parentChatId)?.title
      : null;
    const childSubagents = subagentsByParent.get(chat.id) ?? [];
    const hasCollapsedChildren = childSubagents.length > 0;
    const childrenExpanded = expandedSubagentParents.has(chat.id);
    const rowSurface = currentChatId === chat.id
      ? 'bg-brutal-yellow/95 dark:bg-zinc-700 border-brutal-black dark:border-brutal-yellow z-10'
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
        className={`group relative py-3 transition-all border-b last:border-b-0
          ${chatKind === 'subagent' ? 'pl-8 pr-3.5' : 'px-3.5'}
          ${renamingChatId ? (renamingChatId === chat.id ? 'cursor-default' : 'opacity-50 pointer-events-none') : 'cursor-pointer'}
          ${rowSurface}`}
      >
        {chatKind === 'subagent' && (
          <div className="absolute left-3 top-0 bottom-0 w-3 border-l-2 border-b-2 border-neutral-300 dark:border-zinc-600 rounded-bl-sm" />
        )}
        {currentChatId === chat.id && (
          <div className="absolute pointer-events-none inset-0 border-2 border-brutal-black dark:border-brutal-yellow transition-all" />
        )}


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
            {hasCollapsedChildren && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleSubagentParent(chat.id);
                }}
                className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center border border-neutral-300 dark:border-zinc-600 bg-white dark:bg-zinc-900 text-neutral-400 dark:text-zinc-500 hover:border-neutral-500 dark:hover:border-zinc-400 hover:text-neutral-600 dark:hover:text-zinc-300 transition-all ${
                  childrenExpanded ? 'rotate-90' : ''
                }`}
                title={t('chatList.labels.subagentsCount', { count: childSubagents.length })}
                aria-label={t('chatList.labels.subagentsCount', { count: childSubagents.length })}
              >
                <svg className="h-2.5 w-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </button>
            )}
            <h3 className={`font-extrabold text-sm leading-snug truncate flex-1 min-w-0 transition-colors ${currentChatId === chat.id ? 'text-brutal-black dark:text-white' : isUnread(chat) ? 'text-neutral-950 dark:text-white' : 'text-neutral-800 dark:text-neutral-100 group-hover:text-brutal-black dark:group-hover:text-white'}`}>
              {chat.title || t('chatList.untitled')}
            </h3>
            {hasCollapsedChildren && (
              <span className="mt-0.5 flex h-4 min-w-[16px] shrink-0 items-center justify-center rounded-full bg-neutral-200 dark:bg-zinc-700 px-1 text-[9px] font-semibold text-neutral-500 dark:text-zinc-400">
                {childSubagents.length}
              </span>
            )}
            {showUnread && (
              <span className="text-[10px] font-extrabold min-w-[20px] h-5 px-1.5 flex items-center justify-center rounded-sm bg-brutal-yellow text-brutal-black border-2 border-brutal-black leading-none shrink-0 shadow-[1px_1px_0_0_rgba(0,0,0,1)]">
                {unread > 99 ? '99+' : unread}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 overflow-hidden">
            {/* Project chip — always shown so the user knows which workspace */}
            {chat.projectName && (
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
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <circle cx="12" cy="5" r="1.6" />
            <circle cx="12" cy="12" r="1.6" />
            <circle cx="12" cy="19" r="1.6" />
          </svg>
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

  const remaining = Math.max(0, filteredTotal - filteredChats.length);

  return (
    <div ref={sidebarBoundsRef} className="flex flex-col h-full relative">
      {showRefreshIndicator && (
        <div className="absolute top-0 left-0 right-0 z-20 pointer-events-none">
          <div className="h-1 bg-brutal-blue animate-brutal-blink"></div>
        </div>
      )}

      {/* Header: Search + New Chat */}
      <div className="p-3 bg-white dark:bg-zinc-800 flex-shrink-0 space-y-2.5">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={localSearchQuery}
              onChange={(e) => setLocalSearchQuery(e.target.value)}
              placeholder={t('chatList.searchChatsPlaceholder').toUpperCase()}
              className="w-full px-3 py-2 pl-9 bg-neutral-50 dark:bg-zinc-700 dark:text-white dark:placeholder-neutral-500 border-2 border-brutal-black font-bold text-xs uppercase placeholder-neutral-400 focus:outline-none focus:bg-white dark:focus:bg-zinc-600 focus:shadow-brutal-sm transition-all"
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
          <button
            onClick={() => { beginNewChat(); if (switchToView) switchToView('chat'); }}
            className="flex items-center justify-center w-[38px] bg-brutal-black text-white border-2 border-brutal-black shadow-[2px_2px_0_0_#000] hover:bg-brutal-blue hover:text-white hover:translate-y-[1px] hover:translate-x-[1px] hover:shadow-[1px_1px_0_0_#000] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none transition-all flex-shrink-0"
            title={t('chatList.newChat')}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
          </button>
        </div>

        {/* Project filter pill */}
        <div className="relative">
          <button
            ref={filterPillRef}
            type="button"
            onClick={() => setFilterMenuOpen(prev => !prev)}
            className="w-full flex items-center gap-2 px-3 py-2 border-2 border-brutal-black bg-white dark:bg-zinc-700 dark:text-white shadow-[2px_2px_0_0_#000] hover:bg-brutal-yellow hover:translate-y-[1px] hover:translate-x-[1px] hover:shadow-[1px_1px_0_0_#000] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none transition-all"
          >
            <span className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 dark:text-neutral-400">
              {t('chatList.filter.in')}
            </span>
            <span className="text-xs font-extrabold uppercase tracking-wider truncate flex-1 text-left">
              {filterLabel}
            </span>
            <svg className={`w-3 h-3 transition-transform shrink-0 ${filterMenuOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {filterMenuOpen && (
            <div
              ref={filterMenuRef}
              className="absolute left-0 right-0 top-full mt-1 z-30 bg-white dark:bg-zinc-800 border-2 border-brutal-black shadow-[3px_3px_0_0_#000] max-h-[60vh] overflow-hidden flex flex-col"
            >
              <div className="overflow-y-auto flex-1">
                <div
                  className={`flex items-stretch border-b border-neutral-200 dark:border-zinc-700 ${
                    filterId === ALL_PROJECTS_FILTER ? 'bg-brutal-yellow text-brutal-black' : 'hover:bg-neutral-100 dark:hover:bg-zinc-700 dark:text-white'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => handleSelectFilter(ALL_PROJECTS_FILTER)}
                    className="flex-1 min-w-0 text-left px-3 py-2 text-xs font-bold flex items-center justify-between gap-2"
                  >
                    <span className="truncate uppercase tracking-wider">{t('chatList.filter.all')}</span>
                    <span className="text-[10px] font-bold tabular-nums opacity-70">{chatTotal}</span>
                  </button>
                  {/* Spacer to align with kebab column on user-project rows */}
                  <span aria-hidden="true" className="px-2 flex items-center shrink-0">
                    <span className="w-4" />
                  </span>
                </div>
                {projects.map(p => {
                  const isSystem = p.slug === 'default' || p.slug === 'social';
                  const isRenaming = renamingProjectId === p.id;
                  const isFiltered = filterId === p.id;
                  return (
                    <div
                      key={p.id}
                      className={`group/proj relative flex items-stretch border-b border-neutral-200 dark:border-zinc-700 last:border-b-0 ${
                        isFiltered ? 'bg-brutal-yellow text-brutal-black' : 'hover:bg-neutral-100 dark:hover:bg-zinc-700 dark:text-white'
                      }`}
                    >
                      {isRenaming ? (
                        <form
                          className="flex-1 flex items-center gap-1 p-1.5"
                          onSubmit={async (e) => {
                            e.preventDefault();
                            const trimmed = projectRenameValue.trim();
                            if (trimmed && trimmed !== p.name) await renameProject(p.id, trimmed);
                            setRenamingProjectId(null);
                          }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <input
                            autoFocus
                            type="text"
                            value={projectRenameValue}
                            onChange={(e) => setProjectRenameValue(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Escape') setRenamingProjectId(null); }}
                            className="flex-1 min-w-0 px-2 py-1 text-xs font-bold bg-white dark:bg-zinc-700 dark:text-white border-2 border-brutal-black focus:outline-none"
                          />
                          <button type="submit" className="px-2 py-1 text-[10px] font-extrabold uppercase border-2 border-brutal-black bg-brutal-yellow hover:bg-yellow-300 text-brutal-black shrink-0">✓</button>
                          <button type="button" onClick={() => setRenamingProjectId(null)} className="px-2 py-1 text-[10px] font-extrabold uppercase border-2 border-brutal-black bg-white dark:bg-zinc-700 dark:text-white shrink-0">✕</button>
                        </form>
                      ) : (
                        <>
                          <button
                            type="button"
                            onClick={() => handleSelectFilter(p.id)}
                            className="flex-1 min-w-0 text-left px-3 py-2 text-xs font-bold flex items-center justify-between gap-2"
                          >
                            <span className="truncate">{p.name}</span>
                            <span className="text-[10px] font-bold tabular-nums opacity-70">{p.chatCount}</span>
                          </button>
                          {!isSystem ? (
                            <button
                              type="button"
                              aria-label={t('chatList.menu.title')}
                              title={t('chatList.menu.title')}
                              onClick={(e) => {
                                e.stopPropagation();
                                const rect = (e.currentTarget as HTMLButtonElement).getBoundingClientRect();
                                setProjectMenu({ projectId: p.id, anchor: { rect } });
                              }}
                              className={`px-2 transition-opacity flex items-center justify-center shrink-0 ${
                                projectMenu?.projectId === p.id
                                  ? 'opacity-100'
                                  : 'opacity-0 group-hover/proj:opacity-100 focus:opacity-100'
                              } hover:bg-black/10`}
                            >
                              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                                <circle cx="12" cy="5" r="1.6" />
                                <circle cx="12" cy="12" r="1.6" />
                                <circle cx="12" cy="19" r="1.6" />
                              </svg>
                            </button>
                          ) : (
                            // Spacer so the chat-count column stays aligned across
                            // rows whether or not a kebab button is rendered.
                            <span aria-hidden="true" className="px-2 flex items-center shrink-0">
                              <span className="w-4" />
                            </span>
                          )}
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
              <div className="border-t-2 border-brutal-black">
                {creatingProjectInline ? (
                  <form onSubmit={handleCreateProjectInline} className="flex items-center gap-1 p-2">
                    <input
                      autoFocus
                      type="text"
                      value={newProjectName}
                      onChange={(e) => setNewProjectName(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Escape') { setCreatingProjectInline(false); setNewProjectName(''); } }}
                      placeholder={t('chatList.newProjectPlaceholder')}
                      className="flex-1 min-w-0 px-2 py-1 text-xs font-bold bg-white dark:bg-zinc-700 dark:text-white border-2 border-brutal-black focus:outline-none"
                    />
                    <button type="submit" className="px-2 py-1 text-[10px] font-extrabold uppercase border-2 border-brutal-black bg-brutal-yellow hover:bg-yellow-300 text-brutal-black shrink-0">✓</button>
                    <button type="button" onClick={() => { setCreatingProjectInline(false); setNewProjectName(''); }} className="px-2 py-1 text-[10px] font-extrabold uppercase border-2 border-brutal-black bg-white dark:bg-zinc-700 dark:text-white shrink-0">✕</button>
                  </form>
                ) : (
                  <button
                    type="button"
                    onClick={() => setCreatingProjectInline(true)}
                    className="w-full text-left px-3 py-2 text-xs font-extrabold uppercase tracking-wider hover:bg-brutal-yellow hover:text-brutal-black text-brutal-blue dark:text-brutal-yellow"
                  >
                    + {t('chatList.newProject')}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Filter context line */}
        <div className="text-[10px] font-bold uppercase tracking-widest text-neutral-400 dark:text-neutral-500 px-0.5">
          {filterId === ALL_PROJECTS_FILTER
            ? t('chatList.filter.recentAll')
            : t('chatList.filter.recentIn', { name: filterLabel })}
        </div>
        <div className="flex items-center gap-1 border-2 border-brutal-black bg-white dark:bg-zinc-700 p-0.5">
          {([
            ['you', t('chatList.kind.you')],
            ['scheduled', t('chatList.kind.scheduled')],
            ['all', t('chatList.kind.all')],
          ] as const).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setKindFilter(id)}
              className={`flex-1 min-w-0 h-6 px-1 text-[9px] font-extrabold uppercase tracking-wide flex items-center justify-center gap-1 transition-colors ${
                kindFilter === id
                  ? 'bg-brutal-yellow text-brutal-black shadow-[inset_0_0_0_2px_#000]'
                  : 'text-neutral-500 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-zinc-600'
              }`}
              title={label}
            >
              <span className="truncate">{label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Chat list */}
      <div className="flex-1 overflow-y-auto scrollbar-thin min-h-0">
        {loadingProjectChats ? (
          renderListSkeleton()
        ) : visibleChats.length === 0 ? (
          <div className="flex flex-col bg-white dark:bg-zinc-800">
            <div className="p-8 text-center">
              <div className="w-16 h-16 mx-auto mb-3">
                <RobotAvatar variant={searchQuery ? 'ghost' : 'portal'} />
              </div>
              <p className="text-brutal-black dark:text-white text-sm font-bold uppercase">
                {searchQuery ? t('chatList.empty.noResultsTitle') : t('chatList.empty.noChatsTitle')}
              </p>
              <p className="text-neutral-500 dark:text-neutral-400 text-xs mt-1">
                {searchQuery ? t('chatList.empty.noResultsDesc') : t('chatList.empty.noChatsDesc')}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex flex-col bg-white dark:bg-zinc-800">
            {visibleChats.map(renderChatRow)}
            {remaining > 0 && (
              <button
                onClick={handleLoadMore}
                disabled={loadingMoreChats || loadingMoreProjectChats}
                className="w-full py-2.5 text-[10px] font-bold uppercase border-t-2 border-brutal-black bg-white dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700 text-neutral-500 dark:text-neutral-400 hover:text-brutal-black dark:hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loadingMoreChats || loadingMoreProjectChats ? t('chatList.loadingMore') : t('chatList.loadMore', { count: remaining })}
              </button>
            )}
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

      {/* Modal dialog (replaces window.alert / window.confirm) */}
      <BrutalDialog
        open={dialog !== null}
        title={dialog?.title}
        message={dialog?.message ?? ''}
        actions={dialog?.actions ?? []}
        onClose={() => setDialog(null)}
        rootDataAttrs={{ 'data-popover-source': 'project-filter' }}
      />

      {/* Floating project menu (kebab inside the filter dropdown) */}
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
