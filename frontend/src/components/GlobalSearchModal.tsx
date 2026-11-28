import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChatBubbleLeftRightIcon,
  CircleStackIcon,
  ClockIcon,
  CodeBracketIcon,
  DocumentTextIcon,
  FolderIcon,
  PhotoIcon,
  PlusCircleIcon,
  RectangleStackIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { useI18n } from '../i18n';
import { useChatStore } from '../hooks/useChatStore';
import { useProjects } from '../hooks/useProjects';
import {
  adoptAcpSession,
  type CronJob,
  discoverAcpSessions,
  fetchCronJobs,
  getApiBase,
} from '../lib/api';
import { memoryApi } from '../lib/memoryApi';
import { resourcePaths } from '../lib/resourceAPI.generated';
import { isImeComposing } from '../lib/ime';
import type { ChatSummary, DiscoveredExternalSession, Project } from '../types/api';
import type { ArchivalMemory } from '../types/memory';
import { AcpAgentIcon } from './AcpAgentIcon';
import { formatAcpAgentName } from './chat/AssistantMessage';

export type GlobalSearchTab =
  'all' | 'artifacts' | 'chats' | 'external' | 'memory' | 'projects' | 'scheduled';

const TABS: GlobalSearchTab[] = [
  'all',
  'artifacts',
  'chats',
  'external',
  'memory',
  'projects',
  'scheduled',
];

interface IndexedArtifactRow {
  path: string;
  name: string;
  kind: string;
  project_id: string;
  chat_id: string | null;
  chat_title: string | null;
  serve_chat_id: string | null;
  modified: number;
  size: number;
}

interface SearchListItem {
  key: string;
  group:
    'recent' | 'chats' | 'external' | 'artifacts' | 'memory' | 'projects' | 'scheduled' | 'actions';
  title: string;
  subtitle?: string;
  badge?: string;
  icon: React.ReactNode;
  onSelect: () => void | Promise<void>;
}

interface GlobalSearchModalProps {
  open: boolean;
  onClose: () => void;
  onOpenChat: (chatId: string) => void;
  onNewChat: () => void;
  onOpenView: (view: 'chat' | 'mailbox' | 'memory' | 'skills' | 'artifacts') => void;
  onOpenAutomation: () => void;
}

export const GlobalSearchModal: React.FC<GlobalSearchModalProps> = ({
  open,
  onClose,
  onOpenChat,
  onNewChat,
  onOpenView,
  onOpenAutomation,
}) => {
  const { t } = useI18n();
  const { chats, refreshChatList } = useChatStore();
  const { projects, setCurrentProjectId } = useProjects();

  const [query, setQuery] = useState('');
  const [activeTab, setActiveTab] = useState<GlobalSearchTab>('all');
  const [activeIndex, setActiveIndex] = useState(0);
  const [adoptingId, setAdoptingId] = useState<string | null>(null);

  const [searchedChats, setSearchedChats] = useState<ChatSummary[]>([]);
  const [externalSessions, setExternalSessions] = useState<DiscoveredExternalSession[]>([]);
  const [artifacts, setArtifacts] = useState<IndexedArtifactRow[]>([]);
  const [memories, setMemories] = useState<ArchivalMemory[]>([]);
  const [cronJobs, setCronJobs] = useState<CronJob[]>([]);

  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Focus input & load initial data when modal opens
  useEffect(() => {
    if (!open) return;
    setQuery('');
    setActiveTab('all');
    setActiveIndex(0);
    setTimeout(() => inputRef.current?.focus(), 10);

    // Fetch artifacts snapshot
    let cancelled = false;
    fetch(`${getApiBase()}/artifacts`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data && Array.isArray(data.items)) {
          setArtifacts(data.items);
        }
      })
      .catch(() => {});

    // Fetch scheduled tasks
    fetchCronJobs()
      .then((jobs) => {
        if (!cancelled) setCronJobs(jobs);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [open]);

  // Debounced live search when query changes
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const trimmed = query.trim();
    const timer = setTimeout(() => {
      // 1. Search chats from backend without mutating sidebar store
      if (trimmed) {
        fetch(
          `${getApiBase()}${resourcePaths.chats()}?limit=20&search=${encodeURIComponent(trimmed)}`
        )
          .then((res) => (res.ok ? res.json() : null))
          .then((data) => {
            if (!cancelled && data && Array.isArray(data.chats)) {
              setSearchedChats(data.chats);
            }
          })
          .catch(() => {});
      } else {
        setSearchedChats([]);
      }

      // 2. Discover external CLI sessions filtered by query
      discoverAcpSessions({ query: trimmed || undefined })
        .then((res) => {
          if (!cancelled) setExternalSessions(res.sessions);
        })
        .catch(() => {});

      // 3. Search archival memories
      memoryApi
        .searchArchivalMemory(trimmed, 'default-user', 12, 0)
        .then((res) => {
          if (!cancelled) setMemories(res.memories || []);
        })
        .catch(() => {});
    }, 180);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [open, query]);

  const handleAdoptExternal = useCallback(
    async (ext: DiscoveredExternalSession) => {
      if (adoptingId) return;
      setAdoptingId(ext.session_id);
      try {
        const res = await adoptAcpSession({
          agentId: ext.agent_id,
          sessionId: ext.session_id,
          cwd: ext.cwd,
          title: ext.title,
          updatedAt: ext.updated_at,
          mtime: ext.mtime,
        });
        await refreshChatList(undefined, true);
        onClose();
        onOpenChat(res.chat_id);
      } catch {
        // Ignore transient adopt error
      } finally {
        setAdoptingId(null);
      }
    },
    [adoptingId, onClose, onOpenChat, refreshChatList]
  );

  const items = useMemo<SearchListItem[]>(() => {
    const q = query.trim().toLowerCase();
    const result: SearchListItem[] = [];

    const chatSource = q ? searchedChats : chats;
    const filteredChats = chatSource.slice(0, activeTab === 'chats' ? 20 : q ? 6 : 5);

    const filteredExternal = externalSessions.slice(0, activeTab === 'external' ? 20 : q ? 5 : 3);

    const filteredArtifacts = artifacts
      .filter(
        (a) =>
          !q ||
          a.name.toLowerCase().includes(q) ||
          (a.chat_title || '').toLowerCase().includes(q) ||
          a.path.toLowerCase().includes(q)
      )
      .slice(0, activeTab === 'artifacts' ? 20 : q ? 5 : 2);

    const filteredMemories = memories.slice(0, activeTab === 'memory' ? 20 : q ? 4 : 0);

    const filteredProjects = projects
      .filter(
        (p: Project) =>
          !q ||
          p.name.toLowerCase().includes(q) ||
          (p.workingDirectory || '').toLowerCase().includes(q)
      )
      .slice(0, activeTab === 'projects' ? 20 : q ? 4 : 2);

    const filteredScheduled = cronJobs
      .filter(
        (j) => !q || j.name.toLowerCase().includes(q) || (j.prompt || '').toLowerCase().includes(q)
      )
      .slice(0, activeTab === 'scheduled' ? 20 : q ? 4 : 0);

    const makeChatItem = (c: ChatSummary, group: SearchListItem['group']): SearchListItem => ({
      key: `chat:${c.id}`,
      group,
      title: c.title || t('chatList.untitled'),
      subtitle: c.projectName || undefined,
      badge: c.acpAgentId ? formatAcpAgentName(c.acpAgentId) : undefined,
      icon: c.acpAgentId ? (
        <AcpAgentIcon id={c.acpAgentId} className="h-4 w-4 shrink-0" />
      ) : (
        <CodeBracketIcon className="h-4 w-4 shrink-0 text-neutral-500 dark:text-neutral-400" />
      ),
      onSelect: () => {
        onClose();
        onOpenChat(c.id);
      },
    });

    const makeExternalItem = (
      ext: DiscoveredExternalSession,
      group: SearchListItem['group']
    ): SearchListItem => {
      const folder = ext.cwd
        ? ext.cwd
            .replace(/[\\/]+$/, '')
            .split(/[\\/]/)
            .pop() || ext.cwd
        : '';
      const busy = adoptingId === ext.session_id;
      return {
        key: `ext:${ext.agent_id}:${ext.session_id}`,
        group,
        title: ext.title,
        subtitle: [formatAcpAgentName(ext.agent_id), folder].filter(Boolean).join(' · '),
        badge: busy
          ? t('newChat.acp.adopting')
          : `${t('newChat.acp.adoptAction')} · ${ext.session_id.slice(0, 7)}`,
        icon: <AcpAgentIcon id={ext.agent_id} className="h-4 w-4 shrink-0" />,
        onSelect: () => handleAdoptExternal(ext),
      };
    };

    const makeArtifactItem = (
      a: IndexedArtifactRow,
      group: SearchListItem['group']
    ): SearchListItem => ({
      key: `artifact:${a.project_id}:${a.path}`,
      group,
      title: a.name,
      subtitle: a.chat_title || undefined,
      badge: a.kind.toUpperCase(),
      icon:
        a.kind === 'image' ? (
          <PhotoIcon className="h-4 w-4 shrink-0 text-blue-500" />
        ) : (
          <DocumentTextIcon className="h-4 w-4 shrink-0 text-blue-500" />
        ),
      onSelect: () => {
        onClose();
        if (a.chat_id) {
          onOpenChat(a.chat_id);
        } else {
          onOpenView('artifacts');
        }
      },
    });

    const makeProjectItem = (p: Project, group: SearchListItem['group']): SearchListItem => ({
      key: `project:${p.id}`,
      group,
      title: p.name,
      subtitle: p.workingDirectory || undefined,
      icon: <FolderIcon className="h-4 w-4 shrink-0 text-pink-500 dark:text-pink-400" />,
      onSelect: () => {
        setCurrentProjectId(p.id);
        onClose();
        onNewChat();
      },
    });

    const makeMemoryItem = (m: ArchivalMemory, group: SearchListItem['group']): SearchListItem => ({
      key: `memory:${m.id}`,
      group,
      title: m.content.replace(/\s+/g, ' ').slice(0, 90),
      subtitle: String(m.metadata?.category || m.metadata?.kind || '') || undefined,
      icon: <CircleStackIcon className="h-4 w-4 shrink-0 text-amber-500 dark:text-amber-400" />,
      onSelect: () => {
        onClose();
        onOpenView('memory');
      },
    });

    const makeScheduledItem = (j: CronJob, group: SearchListItem['group']): SearchListItem => ({
      key: `cron:${j.id}`,
      group,
      title: j.name,
      subtitle: j.cron_expr || undefined,
      badge: j.active ? t('chatList.automation.active') : t('chatList.automation.paused'),
      icon: <ClockIcon className="h-4 w-4 shrink-0 text-neutral-500 dark:text-neutral-400" />,
      onSelect: () => {
        onClose();
        if (j.chat_id) {
          onOpenChat(j.chat_id);
        } else {
          onOpenAutomation();
        }
      },
    });

    // When query is empty and tab is 'all', show mixed "Recent" + "External CLI" + "Actions" like Claude Code
    if (activeTab === 'all' && !q) {
      filteredChats.forEach((c) => result.push(makeChatItem(c, 'recent')));
      filteredProjects.forEach((p) => result.push(makeProjectItem(p, 'recent')));
      filteredArtifacts.forEach((a) => result.push(makeArtifactItem(a, 'recent')));
      filteredExternal.forEach((e) => result.push(makeExternalItem(e, 'external')));
    } else {
      if (activeTab === 'all' || activeTab === 'chats') {
        filteredChats.forEach((c) => result.push(makeChatItem(c, 'chats')));
      }
      if (activeTab === 'all' || activeTab === 'external') {
        filteredExternal.forEach((e) => result.push(makeExternalItem(e, 'external')));
      }
      if (activeTab === 'all' || activeTab === 'artifacts') {
        filteredArtifacts.forEach((a) => result.push(makeArtifactItem(a, 'artifacts')));
      }
      if (activeTab === 'all' || activeTab === 'memory') {
        filteredMemories.forEach((m) => result.push(makeMemoryItem(m, 'memory')));
      }
      if (activeTab === 'all' || activeTab === 'projects') {
        filteredProjects.forEach((p) => result.push(makeProjectItem(p, 'projects')));
      }
      if (activeTab === 'all' || activeTab === 'scheduled') {
        filteredScheduled.forEach((j) => result.push(makeScheduledItem(j, 'scheduled')));
      }
    }

    // Bottom quick actions section
    if (activeTab === 'all' && !q) {
      result.push({
        key: 'action:new-chat',
        group: 'actions',
        title: t('chatList.globalSearch.actions.newChat'),
        icon: (
          <PlusCircleIcon className="h-4 w-4 shrink-0 text-neutral-500 dark:text-neutral-400" />
        ),
        onSelect: () => {
          onClose();
          onNewChat();
        },
      });
      result.push({
        key: 'action:open-artifacts',
        group: 'actions',
        title: t('chatList.globalSearch.actions.openArtifacts'),
        icon: (
          <RectangleStackIcon className="h-4 w-4 shrink-0 text-neutral-500 dark:text-neutral-400" />
        ),
        onSelect: () => {
          onClose();
          onOpenView('artifacts');
        },
      });
      result.push({
        key: 'action:open-memory',
        group: 'actions',
        title: t('chatList.globalSearch.actions.openMemory'),
        icon: (
          <CircleStackIcon className="h-4 w-4 shrink-0 text-neutral-500 dark:text-neutral-400" />
        ),
        onSelect: () => {
          onClose();
          onOpenView('memory');
        },
      });
    }

    return result;
  }, [
    activeTab,
    adoptingId,
    artifacts,
    chats,
    cronJobs,
    externalSessions,
    handleAdoptExternal,
    memories,
    onClose,
    onNewChat,
    onOpenAutomation,
    onOpenChat,
    onOpenView,
    projects,
    query,
    searchedChats,
    setCurrentProjectId,
    t,
  ]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query, activeTab]);

  // Keep active row scrolled into view
  useEffect(() => {
    const container = listRef.current;
    if (!container) return;
    const row = container.querySelector<HTMLElement>(`[data-search-idx="${activeIndex}"]`);
    row?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (isImeComposing(e)) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (items.length > 0) {
        setActiveIndex((prev) => (prev + 1) % items.length);
      }
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (items.length > 0) {
        setActiveIndex((prev) => (prev - 1 + items.length) % items.length);
      }
      return;
    }
    if (
      e.key === 'Tab' ||
      (e.key === 'ArrowRight' && !query) ||
      (e.key === 'ArrowLeft' && !query)
    ) {
      e.preventDefault();
      const dir = e.key === 'ArrowLeft' || (e.key === 'Tab' && e.shiftKey) ? -1 : 1;
      const idx = TABS.indexOf(activeTab);
      const next = TABS[(idx + dir + TABS.length) % TABS.length];
      setActiveTab(next);
      return;
    }
    if (e.key === 'Enter' && items[activeIndex]) {
      e.preventDefault();
      void items[activeIndex].onSelect();
    }
  };

  if (!open) return null;

  // Group items in display order while preserving flat index for keyboard nav
  const groupedSections: {
    group: SearchListItem['group'];
    entries: { item: SearchListItem; flatIdx: number }[];
  }[] = [];
  items.forEach((item, flatIdx) => {
    const last = groupedSections[groupedSections.length - 1];
    if (!last || last.group !== item.group) {
      groupedSections.push({ group: item.group, entries: [{ item, flatIdx }] });
    } else {
      last.entries.push({ item, flatIdx });
    }
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/35 backdrop-blur-[1px] pt-[10vh] px-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('chatList.search')}
        onKeyDown={handleKeyDown}
        className="w-full max-w-[660px] flex flex-col bg-white dark:bg-zinc-900 border-2 border-brutal-black dark:border-zinc-600 shadow-brutal-lg overflow-hidden"
      >
        {/* Top search input + close button */}
        <div className="px-4 pt-3.5 pb-2.5 border-b border-neutral-200 dark:border-zinc-800">
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('chatList.globalSearch.placeholder')}
              className="flex-1 bg-transparent text-sm font-medium text-brutal-black dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:outline-none"
            />
            {query && (
              <button
                type="button"
                onClick={() => {
                  setQuery('');
                  inputRef.current?.focus();
                }}
                className="px-1.5 py-0.5 text-[10px] font-bold uppercase text-neutral-400 hover:text-brutal-black dark:hover:text-white"
              >
                {t('chatList.clearSearch')}
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              aria-label={t('chatList.globalSearch.footer.close')}
              className="p-1 text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white hover:bg-neutral-100 dark:hover:bg-zinc-800 transition-colors"
            >
              <XMarkIcon className="h-4 w-4 stroke-[2.2]" />
            </button>
          </div>

          {/* Category filter pills (Claude Code style) */}
          <div className="mt-3 flex items-center gap-1.5 overflow-x-auto no-scrollbar">
            {TABS.map((tab) => {
              const selected = activeTab === tab;
              return (
                <button
                  key={tab}
                  type="button"
                  onClick={() => {
                    setActiveTab(tab);
                    inputRef.current?.focus();
                  }}
                  className={`px-2.5 py-1 text-xs font-bold transition-colors shrink-0 ${
                    selected
                      ? 'bg-neutral-200/90 text-brutal-black dark:bg-zinc-700 dark:text-white'
                      : 'text-neutral-600 hover:bg-neutral-100 hover:text-brutal-black dark:text-neutral-400 dark:hover:bg-zinc-800 dark:hover:text-white'
                  }`}
                >
                  {t(`chatList.globalSearch.tabs.${tab}`)}
                </button>
              );
            })}
          </div>
        </div>

        {/* Scrollable results body */}
        <div
          ref={listRef}
          className="max-h-[58vh] min-h-[260px] overflow-y-auto px-2 py-2 space-y-3 scrollbar-thin"
        >
          {groupedSections.length === 0 ? (
            <div className="py-16 text-center text-xs font-semibold text-neutral-400 dark:text-neutral-500">
              <ChatBubbleLeftRightIcon className="h-6 w-6 mx-auto mb-2 opacity-50" />
              {t('chatList.globalSearch.empty')}
            </div>
          ) : (
            groupedSections.map((section) => (
              <div key={section.group}>
                <div className="px-2.5 pb-1 text-[11px] font-semibold text-neutral-400 dark:text-neutral-500">
                  {t(`chatList.globalSearch.groups.${section.group}`)}
                </div>
                <div className="space-y-0.5">
                  {section.entries.map(({ item, flatIdx }) => {
                    const active = flatIdx === activeIndex;
                    return (
                      <button
                        key={item.key}
                        type="button"
                        data-search-idx={flatIdx}
                        onMouseEnter={() => setActiveIndex(flatIdx)}
                        onClick={() => void item.onSelect()}
                        className={`w-full flex items-center gap-2.5 px-2.5 py-2 text-left transition-colors ${
                          active
                            ? 'bg-neutral-200/75 dark:bg-zinc-800 text-brutal-black dark:text-white'
                            : 'text-neutral-700 dark:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-zinc-800/60'
                        }`}
                      >
                        <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                          {item.icon}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-[13px] font-medium">
                          {item.title}
                          {item.subtitle && (
                            <span className="ml-1.5 text-xs font-normal text-neutral-400 dark:text-neutral-500">
                              · {item.subtitle}
                            </span>
                          )}
                        </span>
                        {item.badge && (
                          <span className="shrink-0 text-[11px] font-mono text-neutral-400 dark:text-neutral-500">
                            {item.badge}
                          </span>
                        )}
                        {active && (
                          <span
                            aria-hidden="true"
                            className="shrink-0 text-xs font-mono text-neutral-500 dark:text-neutral-400"
                          >
                            ↵
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Bottom keyboard shortcut bar */}
        <div className="flex items-center justify-between px-4 py-2 border-t border-neutral-200 dark:border-zinc-800 bg-neutral-50/70 dark:bg-zinc-900/90 text-[11px] text-neutral-500 dark:text-neutral-400">
          <div className="flex items-center gap-4">
            <span className="inline-flex items-center gap-1.5">
              <span>{t('chatList.globalSearch.footer.close')}</span>
              <kbd className="px-1.5 py-0.5 text-[10px] font-mono bg-neutral-200/80 dark:bg-zinc-800 border border-neutral-300 dark:border-zinc-700">
                Esc
              </kbd>
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span>{t('chatList.globalSearch.footer.switchTab')}</span>
              <kbd className="px-1 py-0.5 text-[10px] font-mono bg-neutral-200/80 dark:bg-zinc-800 border border-neutral-300 dark:border-zinc-700">
                ←
              </kbd>
              <kbd className="px-1 py-0.5 text-[10px] font-mono bg-neutral-200/80 dark:bg-zinc-800 border border-neutral-300 dark:border-zinc-700">
                →
              </kbd>
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span>{t('chatList.globalSearch.footer.navigate')}</span>
              <kbd className="px-1 py-0.5 text-[10px] font-mono bg-neutral-200/80 dark:bg-zinc-800 border border-neutral-300 dark:border-zinc-700">
                ↑
              </kbd>
              <kbd className="px-1 py-0.5 text-[10px] font-mono bg-neutral-200/80 dark:bg-zinc-800 border border-neutral-300 dark:border-zinc-700">
                ↓
              </kbd>
            </span>
          </div>
          <span className="inline-flex items-center gap-1.5">
            <span>{t('chatList.globalSearch.footer.select')}</span>
            <kbd className="px-1.5 py-0.5 text-[10px] font-mono bg-neutral-200/80 dark:bg-zinc-800 border border-neutral-300 dark:border-zinc-700">
              ↵
            </kbd>
          </span>
        </div>
      </div>
    </div>
  );
};
