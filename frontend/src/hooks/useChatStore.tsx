import React, { createContext, useContext, useState, useEffect, useCallback, useRef, useMemo } from 'react';
import type { Message, ChatConfig, ConfigOptions, Chat, ChatSummary, ChatKindCounts } from '../types/api';
import { getApiBase } from '../lib/api';
import { stripDenyApprovalPolicies } from '../lib/approvalPolicy';
import { shouldKeepLocalAssistantContent } from '../lib/chatSyncGuards';
import { useContextUsageStore } from './useContextUsageStore';
import { useProjects } from './useProjects';

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function userMessageFingerprint(message: Message): string {
  const files = (message.files ?? [])
    .map(file => `${file.filename}:${file.path}:${file.mime_type}:${file.size}`)
    .sort()
    .join('|');
  const images = (message.images ?? [])
    .map(image => `${image.filename}:${image.mime_type}`)
    .sort()
    .join('|');
  return JSON.stringify({
    content: (message.content ?? '').trim(),
    files,
    images,
  });
}

function countUserMessageFingerprint(messages: Message[], fingerprint: string): number {
  return messages.reduce((count, message) => (
    message.role === 'user' && userMessageFingerprint(message) === fingerprint
      ? count + 1
      : count
  ), 0);
}

function shouldKeepOptimisticUserMessage(localMessages: Message[], serverMessages: Message[]): boolean {
  const lastLocal = localMessages[localMessages.length - 1];
  if (!lastLocal || lastLocal.role !== 'user') return false;

  const fingerprint = userMessageFingerprint(lastLocal);
  const localCount = countUserMessageFingerprint(localMessages, fingerprint);
  const serverCount = countUserMessageFingerprint(serverMessages, fingerprint);
  // Hold while the local store has more copies of this message than the server
  // (the optimistic append(s) the backend hasn't logged yet). Using >= 1 (not
  // === 1) keeps BOTH bubbles visible when the same text is sent twice in a row,
  // while still releasing as soon as the server catches up.
  return localCount - serverCount >= 1;
}

interface ChatStreamingContextValue {
  messages: Message[];
  isStreaming: boolean;
  activeStreamingChatId: string | null;
}

interface ChatCoreContextValue {
  config: ChatConfig;
  setConfig: (c: ChatConfig | ((prev: ChatConfig) => ChatConfig)) => void;
  addMessage: (m: Message, chatId?: string | null) => void;
  updateLastUserMessageImages: (images: any[], chatId?: string | null) => void;
  updateAssistantStreaming: (delta: string, chatId?: string | null) => void;
  backendConfig: ConfigOptions | null;
  refreshBackendConfig: () => Promise<void>;
  newAssistantMessage: (chatId?: string | null) => void;
  setStepInfo: (stepInfo: string, chatId?: string | null) => void;
  resetChat: () => void;
  shouldResetNext: boolean;
  consumeResetFlag: () => void;
  setIsStreaming: (streaming: boolean, chatId?: string | null) => void;
  removeEmptyAssistantMessage: (chatId?: string | null) => void;
  currentChatId: string | null;
  chats: ChatSummary[];
  loadingChats: boolean;
  refreshingChats: boolean;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  beginNewChat: () => void;
  createNewChat: () => Promise<string | null>;
  loadChat: (chatId: string, options?: { force?: boolean }) => Promise<void>;
  saveCurrentChat: (skipRefresh?: boolean) => Promise<void>;
  finalSave: (chatId?: string | null) => Promise<void>;
  forceSaveNow: (chatId?: string | null) => Promise<void>;
  deleteChat: (chatId: string, options?: { cascade?: boolean }) => Promise<void>;
  renameChat: (chatId: string, title: string) => Promise<void>;
  chatTotal: number;
  chatKindTotals: ChatKindCounts;
  loadingMoreChats: boolean;
  refreshChatList: (searchQuery?: string, force?: boolean) => Promise<void>;
  refreshChatListSilently: (searchQuery?: string) => Promise<void>;
  loadMoreChats: () => Promise<void>;
  updateChatTitleLocally: (chatId: string, title: string) => void;
  updateMessage: (index: number, update: Partial<Message>, chatId?: string | null) => void;
  truncateMessagesFrom: (fromIndex: number, chatId?: string | null) => void;
  markChatRollbackExpected: (chatId?: string | null) => void;
  setViewSwitcher?: (switcher: (view: 'chat' | 'memory') => void) => void;
  switchToView?: (view: 'chat' | 'memory') => void;
  hideToolCalls: boolean;
  toggleHideToolCalls: () => void;
}

type ChatContextValue = ChatCoreContextValue & ChatStreamingContextValue;

const ChatCoreContext = createContext<ChatCoreContextValue | null>(null);
const ChatStreamingContext = createContext<ChatStreamingContextValue | null>(null);

const emptyChatKindCounts: ChatKindCounts = { you: 0, scheduled: 0, all: 0 };

const defaultConfig: ChatConfig = {
  model: '',
  agent: '',
  tools: [],
  mcp_urls: [],
  mcp_enabled: {},
  sandbox_enabled: true, // Default to true to match backend
  permission_mode: 'default',
};

const UNSAVED_CHAT_KEY = '__unsaved__';
const LAST_CONFIG_KEY = 'suzent_last_config';
const keyForChat = (chatId: string | null) => chatId ?? UNSAVED_CHAT_KEY;

const stripReusableConfig = (config: ChatConfig): ChatConfig => {
  const reusable = { ...config } as Record<string, unknown>;
  [
    'tool_approval_policy',
    'permission_policies',
    'permission_mode',
    'heartbeat_enabled',
    'heartbeat_interval_minutes',
    'heartbeat_instructions',
    'heartbeat_last_run_at',
    'platform',
    'sender_id',
    'target_id',
    'cron_job_id',
    'parent_chat_id',
  ].forEach(key => delete reusable[key]);
  return reusable as unknown as ChatConfig;
};

/** Build a ChatConfig from user preferences and backend defaults. */
const buildConfigFromPreferences = (
  prefs: ConfigOptions['userPreferences'],
  backendDefaults: ConfigOptions
): ChatConfig => ({
  model: prefs?.model || backendDefaults.defaultModel || backendDefaults.models[0] || '',
  agent: prefs?.agent || backendDefaults.agents[0] || '',
  tools: prefs?.tools || backendDefaults.defaultTools || [],
  memory_enabled: prefs?.memory_enabled,
  sandbox_enabled: prefs?.sandbox_enabled ?? backendDefaults.sandboxEnabled ?? true,
  sandbox_volumes: prefs?.sandbox_volumes || [],
  permission_mode: backendDefaults.defaultPermissionMode ?? 'default',
  mcp_urls: [],
  mcp_enabled: {}
});

const hydrateChatConfig = (
  chatConfig: ChatConfig | undefined,
  fallbackConfig: ChatConfig
): ChatConfig => {
  const savedConfig: Partial<ChatConfig> = chatConfig ?? {};
  return {
    ...fallbackConfig,
    ...savedConfig,
    model: savedConfig.model || fallbackConfig.model,
    agent: savedConfig.agent || fallbackConfig.agent,
    tools: savedConfig.tools ?? fallbackConfig.tools,
    memory_enabled: savedConfig.memory_enabled ?? fallbackConfig.memory_enabled,
    sandbox_enabled: savedConfig.sandbox_enabled ?? fallbackConfig.sandbox_enabled,
    sandbox_volumes: savedConfig.sandbox_volumes ?? fallbackConfig.sandbox_volumes,
    mcp_urls: savedConfig.mcp_urls ?? fallbackConfig.mcp_urls,
    mcp_enabled: savedConfig.mcp_enabled ?? fallbackConfig.mcp_enabled,
  };
};

/** Extract the preference fields we track for dirty-checking. */
const extractSavedPreferences = (prefs: ConfigOptions['userPreferences']) => ({
  model: prefs?.model ?? '',
  agent: prefs?.agent ?? '',
  tools: prefs?.tools ?? [],
  memory_enabled: prefs?.memory_enabled,
  sandbox_enabled: prefs?.sandbox_enabled,
  sandbox_volumes: prefs?.sandbox_volumes ?? [],
});

const configsEqual = (a?: ChatConfig | null, b?: ChatConfig | null): boolean => {
  if (a === b) return true;
  if (!a || !b) return false;
  const arrayEqual = (left?: string[], right?: string[]) => {
    const l = left ?? [];
    const r = right ?? [];
    if (l.length !== r.length) return false;
    return l.every((value, index) => value === r[index]);
  };
  const mcpUrlsEqual = (left?: string[] | Record<string, string>, right?: string[] | Record<string, string>) => {
    if (left === right) return true;
    if (!left || !right) return false;

    // Check if both are arrays
    const isLeftArray = Array.isArray(left);
    const isRightArray = Array.isArray(right);

    if (isLeftArray && isRightArray) {
      return arrayEqual(left as string[], right as string[]);
    }

    // Check if both are objects (records)
    if (!isLeftArray && !isRightArray) {
      const l = left as Record<string, string>;
      const r = right as Record<string, string>;
      const lKeys = Object.keys(l).sort();
      const rKeys = Object.keys(r).sort();

      if (!arrayEqual(lKeys, rKeys)) return false;
      return lKeys.every(key => l[key] === r[key]);
    }

    // Mismatched types
    return false;
  };

  const recordEqual = (
    left?: Record<string, unknown>,
    right?: Record<string, unknown>
  ) => {
    if (left === right) return true;
    const l = left ?? {};
    const r = right ?? {};
    const lKeys = Object.keys(l).sort();
    const rKeys = Object.keys(r).sort();
    if (!arrayEqual(lKeys, rKeys)) return false;
    return lKeys.every(key => l[key] === r[key]);
  };

  return (
    a.model === b.model &&
    a.agent === b.agent &&
    arrayEqual(a.tools, b.tools) &&
    mcpUrlsEqual(a.mcp_urls, b.mcp_urls) &&
    // Chat-scoped fields that affect a turn must be compared too, otherwise a
    // mid-chat change (e.g. mounting a folder via the working-dir picker) is
    // treated as a no-op and never persisted to the chat's config — leaving the
    // backend with stale sandbox_volumes / permissions for the next turn.
    a.sandbox_enabled === b.sandbox_enabled &&
    arrayEqual(a.sandbox_volumes, b.sandbox_volumes) &&
    a.memory_enabled === b.memory_enabled &&
    a.permission_mode === b.permission_mode &&
    recordEqual(a.mcp_enabled, b.mcp_enabled) &&
    recordEqual(a.tool_approval_policy, b.tool_approval_policy)
  );
};

const arraysEqual = (a?: string[], b?: string[]): boolean => {
  const l = a ?? [];
  const r = b ?? [];
  if (l.length !== r.length) return false;
  return l.every((v, i) => v === r[i]);
};

interface SavedPreferences {
  model?: string;
  agent?: string;
  tools?: string[];
  memory_enabled?: boolean;
  sandbox_enabled?: boolean;
  sandbox_volumes?: string[];
}

const preferencesEqual = (a: SavedPreferences | null, b: SavedPreferences | null): boolean => {
  if (a === b) return true;
  if (!a || !b) return false;
  return (
    a.model === b.model &&
    a.agent === b.agent &&
    arraysEqual(a.tools, b.tools) &&
    a.memory_enabled === b.memory_enabled &&
    a.sandbox_enabled === b.sandbox_enabled &&
    arraysEqual(a.sandbox_volumes, b.sandbox_volumes)
  );
};

export const ChatProvider: React.FC<{ children: React.ReactNode; enabled?: boolean }> = ({
  children,
  enabled = true,
}) => {
  // Read the user's currently-selected project so newly-created chats land there.
  // Must be wrapped in ProjectProvider (see App.tsx).
  const { currentProjectId, projects } = useProjects();
  const currentProjectIdRef = useRef<string | null>(currentProjectId);
  useEffect(() => { currentProjectIdRef.current = currentProjectId; }, [currentProjectId]);
  const [messagesByChat, setMessagesByChat] = useState<Record<string, Message[]>>({
    [UNSAVED_CHAT_KEY]: []
  });
  const [configByChat, setConfigByChat] = useState<Record<string, ChatConfig>>({
    [UNSAVED_CHAT_KEY]: defaultConfig
  });
  const [config, setConfigState] = useState<ChatConfig>(defaultConfig);
  const [backendConfig, setBackendConfig] = useState<ConfigOptions | null>(null);
  const [backendConfigError, setBackendConfigError] = useState<string | null>(null);
  const [shouldResetNext, setShouldResetNext] = useState(false);
  const [isStreaming, setIsStreamingState] = useState(false);
  const [activeStreamingChatId, setActiveStreamingChatId] = useState<string | null>(null);
  const activeStreamingChatIdRef = useRef<string | null>(null); // Ref for synchronous access
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [currentChatTitle, setCurrentChatTitle] = useState<string>('New Chat');
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [chatTotal, setChatTotal] = useState<number>(0);
  const [chatKindTotals, setChatKindTotals] = useState<ChatKindCounts>(emptyChatKindCounts);
  const [chatOffset, setChatOffset] = useState<number>(0);
  const chatOffsetRef = useRef<number>(0);
  // Keep refs in sync so refresh callbacks always see the latest offset values
  useEffect(() => { chatOffsetRef.current = chatOffset; }, [chatOffset]);
  const [loadingChats, setLoadingChats] = useState(false);
  const [loadingMoreChats, setLoadingMoreChats] = useState(false);
  const [refreshingChats, setRefreshingChats] = useState(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const chatsLoadedRef = useRef(false);
  const refreshInFlightRef = useRef(false);
  const lastRefreshAtRef = useRef(0);
  const searchRequestIdRef = useRef(0);
  const chatCreationPromiseRef = useRef<Promise<string | null> | null>(null);
  const saveTimeoutsRef = useRef<Record<string, NodeJS.Timeout>>({});
  const rollbackExpectedChatIdsRef = useRef<Set<string>>(new Set());
  const messagesByChatRef = useRef(messagesByChat);
  const configByChatRef = useRef(configByChat);
  const viewSwitcherRef = useRef<((view: 'chat' | 'memory') => void) | null>(null);
  const [hideToolCalls, setHideToolCalls] = useState(() => {
    try {
      const stored = localStorage.getItem('suzent_hide_tool_calls');
      return stored === null ? true : stored === 'true';
    } catch {
      return true;
    }
  });
  const toggleHideToolCalls = useCallback(() => {
    setHideToolCalls(prev => {
      const next = !prev;
      try { localStorage.setItem('suzent_hide_tool_calls', String(next)); } catch { }
      return next;
    });
  }, []);
  const lastSavedPreferencesRef = useRef<{ model: string, agent: string, tools: string[], memory_enabled?: boolean, sandbox_enabled?: boolean, sandbox_volumes?: string[] } | null>(null);

  // Keep refs in sync with state
  useEffect(() => {
    messagesByChatRef.current = messagesByChat;
  }, [messagesByChat]);

  useEffect(() => {
    configByChatRef.current = configByChat;
  }, [configByChat]);

  const setViewSwitcher = useCallback((switcher: (view: 'chat' | 'memory') => void) => {
    viewSwitcherRef.current = switcher;
  }, []);

  const switchToView = useCallback((view: 'chat' | 'memory') => {
    if (viewSwitcherRef.current) {
      viewSwitcherRef.current(view);
    }
  }, []);

  const getMessagesForChat = useCallback((chatId: string | null) => {
    const key = keyForChat(chatId);
    return messagesByChat[key] ?? [];
  }, [messagesByChat]);

  const computeDefaultConfig = useCallback((): ChatConfig => {
    // First priority: user preferences from backend database
    if (backendConfig && backendConfig.userPreferences) {
      const prefs = backendConfig.userPreferences;
      lastSavedPreferencesRef.current = extractSavedPreferences(prefs);
      return buildConfigFromPreferences(prefs, backendConfig);
    }

    // Second priority: load last used config from localStorage
    try {
      const saved = localStorage.getItem(LAST_CONFIG_KEY);
      if (saved) {
        const parsed: ChatConfig = JSON.parse(saved);
        // Validate that the saved config is compatible with current backend options
        if (backendConfig) {
          const isModelValid = backendConfig.models.includes(parsed.model);
          const isAgentValid = backendConfig.agents.includes(parsed.agent);
          if (isModelValid && isAgentValid) {
            // Ensure chat-scoped state is never inherited from localStorage.
            return {
              ...stripReusableConfig(parsed),
              permission_mode: backendConfig.defaultPermissionMode ?? 'default',
            };
          }
        }
      }
    } catch (e) {
      console.warn('Failed to load last config from localStorage:', e);
    }

    // Fallback to backend defaults
    if (backendConfig) {
      return {
        model: backendConfig.defaultModel || backendConfig.models[0] || '',
        agent: backendConfig.agents[0] || '',
        tools: backendConfig.defaultTools || [],
        sandbox_enabled: backendConfig.sandboxEnabled ?? true,
        permission_mode: backendConfig.defaultPermissionMode ?? 'default',
        mcp_urls: [],
        mcp_enabled: {}
      };
    }
    return defaultConfig;
  }, [backendConfig]);

  const beginNewChat = useCallback(() => {
    const defaultConfig = computeDefaultConfig();
    const fallbackConfig = {
      ...defaultConfig,
      permission_mode: config.permission_mode ?? defaultConfig.permission_mode,
    };
    setCurrentChatId(null);
    setCurrentChatTitle('New Chat');
    setShouldResetNext(true);
    setMessagesByChat(prev => ({ ...prev, [UNSAVED_CHAT_KEY]: [] }));
    setConfigByChat(prev => ({ ...prev, [UNSAVED_CHAT_KEY]: fallbackConfig }));
    setConfigState(fallbackConfig);
  }, [computeDefaultConfig, config.permission_mode]);

  const setMessagesForChat = useCallback((chatId: string | null, updater: Message[] | ((prev: Message[]) => Message[])) => {
    const key = keyForChat(chatId);
    setMessagesByChat(prev => {
      const previous = prev[key] ?? [];
      const next = typeof updater === 'function' ? (updater as (prev: Message[]) => Message[])(previous) : updater;
      if (next === previous) return prev;

      // Only update sidebar summary if we're not actively streaming for this chat
      // This prevents constant re-renders during streaming
      // Use ref for synchronous access to avoid timing issues with state updates
      if (chatId && chatId !== activeStreamingChatIdRef.current) {
        setChats(current => {
          const index = current.findIndex(c => c.id === chatId);
          if (index === -1) return current;
          const updated = [...current];
          const summary = updated[index];
          updated[index] = {
            ...summary,
            messageCount: next.length,
            lastMessage: next.length ? next[next.length - 1].content.replace(/<details\b[^>]*>[\s\S]*?<\/details>/gi, '').replace(/<[^>]+>/g, '').trim().slice(0, 100) : undefined,
            updatedAt: new Date().toISOString()
          };
          return updated;
        });
      }

      return { ...prev, [key]: next };
    });
  }, []); // No dependencies needed since we use ref

  const messages = useMemo(() => getMessagesForChat(currentChatId), [getMessagesForChat, currentChatId]);

  // Fetch backend config with retry logic
  const fetchConfigWithRetry = useCallback(async (attempt = 1, maxAttempts = 5) => {
    try {
      const res = await fetch(`${getApiBase()}/config`);
      if (res.ok) {
        const data: ConfigOptions = await res.json();

        setBackendConfig(data);
        // Align memory user id with backend-provided userId if present
        try {
          if (data.userId) {
            // Lazy import to avoid circulars; memory hook standalone
            const { useMemory } = await import('./useMemory');
            useMemory.getState().setUserId(data.userId);
          }
        } catch (e) {
          console.warn('Failed to set memory userId from backend config:', e);
        }

        // Build initial config from user preferences or backend defaults
        const firstConfig: ChatConfig = buildConfigFromPreferences(
          data.userPreferences,
          data
        );

        // Track saved preferences to avoid re-saving on initial load
        if (data.userPreferences) {
          lastSavedPreferencesRef.current = extractSavedPreferences(data.userPreferences);
        }

        setConfigState(firstConfig);
        setConfigByChat(prev => ({ ...prev, [UNSAVED_CHAT_KEY]: firstConfig }));
      } else if (attempt < maxAttempts) {
        // Backend not ready, retry with exponential backoff
        const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000);
        console.log(`Backend not ready (${res.status}), retrying in ${delay}ms... (attempt ${attempt}/${maxAttempts})`);
        setTimeout(() => fetchConfigWithRetry(attempt + 1, maxAttempts), delay);
      } else {
        console.error('Failed to fetch config after', maxAttempts, 'attempts:', res.status, res.statusText);
      }
    } catch (error) {
      if (attempt < maxAttempts) {
        // Network error, retry with exponential backoff
        const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000);
        console.log(`Error fetching config, retrying in ${delay}ms... (attempt ${attempt}/${maxAttempts})`);
        setTimeout(() => fetchConfigWithRetry(attempt + 1, maxAttempts), delay);
      } else {
        console.error('Error fetching config after', maxAttempts, 'attempts:', error);
      }
    }
  }, []);

  const refreshBackendConfig = useCallback(async () => {
    await fetchConfigWithRetry();
  }, [fetchConfigWithRetry]);

  // Fetch backend config once on mount
  useEffect(() => {
    if (!enabled) return;
    fetchConfigWithRetry();
  }, [enabled, fetchConfigWithRetry]);

  const refreshChatListInternal = useCallback(async (
    search?: string,
    options?: { silent?: boolean; force?: boolean },
    attempt = 1,
    maxAttempts = 5,
  ) => {
    const silent = !!options?.silent;
    const force = !!options?.force;
    const isFirstLoad = !chatsLoadedRef.current;

    // Deduplicate overlapping non-initial refreshes to reduce repeated /chats traffic.
    // Skip throttle when force=true (e.g. search queries must always go through).
    // Do NOT update lastRefreshAtRef for forced requests so background consistency
    // refreshes (e.g. after deleteChat) are not accidentally suppressed.
    let requestId = 0;
    if (!isFirstLoad && !force) {
      const now = Date.now();
      if (refreshInFlightRef.current) return;
      if (now - lastRefreshAtRef.current < 3500) return;
      refreshInFlightRef.current = true;
      lastRefreshAtRef.current = now;
    } else if (!isFirstLoad && force) {
      // Assign a monotonically increasing ID; only apply the response if it's still latest.
      searchRequestIdRef.current += 1;
      requestId = searchRequestIdRef.current;
      // Reset offsets so the fetch covers only the first page for the new query
      chatOffsetRef.current = 0;
      setChatOffset(0);
    }

    if (isFirstLoad) {
      setLoadingChats(true);
    } else if (!silent) {
      setRefreshingChats(true);
    }
    const currentMessages = currentChatId ? getMessagesForChat(currentChatId) : null;
    try {
      const searchParam = search !== undefined ? search : searchQuery;
      const apiBase = getApiBase();
      // Re-fetch enough rows to cover what the user has already loaded via "load more"
      const limit = chatOffsetRef.current + 50;
      let url = `${apiBase}/chats?limit=${limit}`;
      if (searchParam) url += `&search=${encodeURIComponent(searchParam)}`;
      const res = await fetch(url);
      if (res.ok) {
        // Discard stale forced-search responses that arrived out of order.
        if (force && requestId !== searchRequestIdRef.current) return;

        const data = await res.json();
        const serverList: ChatSummary[] = data.chats || [];
        setChatTotal(data.total ?? serverList.length);
        setChatKindTotals(data.kindCounts ?? {
          you: serverList.filter(chat => (chat.platform || '').toLowerCase() !== 'cron').length,
          scheduled: serverList.filter(chat => (chat.platform || '').toLowerCase() === 'cron').length,
          all: data.total ?? serverList.length,
        });

        // Merge server list with local state, preserving local updates
        setChats(prev => {
          const merged = serverList.map(serverChat => {
            const localChat = prev.find(c => c.id === serverChat.id);
            if (localChat && localChat.messageCount > serverChat.messageCount) {
              return localChat;
            }
            return serverChat;
          });
          return merged;
        });

        if (currentChatId) {
          const summary = serverList.find(c => c.id === currentChatId);
          if (summary && summary.title && summary.title !== currentChatTitle) {
            const localCount = currentMessages?.length ?? 0;
            if (summary.messageCount >= localCount) {
              setCurrentChatTitle(summary.title);
            }
          }
        }

        // Success - mark as loaded
        if (isFirstLoad) {
          chatsLoadedRef.current = true;
        }
      } else if (isFirstLoad && attempt < maxAttempts) {
        // Backend not ready on first load, retry with exponential backoff
        const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000);
        console.log(`Backend not ready for chat list (${res.status}), retrying in ${delay}ms... (attempt ${attempt}/${maxAttempts})`);
        setTimeout(() => refreshChatListInternal(search, options, attempt + 1, maxAttempts), delay);
        return; // Don't clear loading state yet
      } else {
        console.error('Failed to fetch chats:', res.status, res.statusText);
      }
    } catch (error) {
      if (isFirstLoad && attempt < maxAttempts) {
        // Network error on first load, retry with exponential backoff
        const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000);
        console.log(`Error fetching chat list, retrying in ${delay}ms... (attempt ${attempt}/${maxAttempts})`);
        setTimeout(() => refreshChatListInternal(search, options, attempt + 1, maxAttempts), delay);
        return; // Don't clear loading state yet
      } else {
        console.error('Error fetching chats:', error);
      }
    } finally {
      // Clear loading state if we're done (success or final failure)
      if (isFirstLoad) {
        // Clear loading if we succeeded OR if this was the final attempt
        if (chatsLoadedRef.current || attempt >= maxAttempts) {
          setLoadingChats(false);
          if (!chatsLoadedRef.current) {
            chatsLoadedRef.current = true; // Mark as attempted even if failed
          }
        }
      }
      if (!isFirstLoad && !silent) {
        setRefreshingChats(false);
      }
      if (!isFirstLoad) {
        refreshInFlightRef.current = false;
      }
    }
  }, [currentChatId, currentChatTitle, getMessagesForChat, searchQuery]);

  const refreshChatList = useCallback(async (search?: string, force?: boolean) => {
    await refreshChatListInternal(search, { silent: false, force });
  }, [refreshChatListInternal]);

  const refreshChatListSilently = useCallback(async (search?: string) => {
    await refreshChatListInternal(search, { silent: true });
  }, [refreshChatListInternal]);

  const loadMoreChats = useCallback(async () => {
    if (loadingMoreChats) return;
    setLoadingMoreChats(true);
    try {
      const apiBase = getApiBase();
      const nextOffset = chatOffset + 50;
      const searchParam = searchQuery;
      let url = `${apiBase}/chats?limit=50&offset=${nextOffset}`;
      if (searchParam) url += `&search=${encodeURIComponent(searchParam)}`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        const newChats: ChatSummary[] = data.chats || [];
        if (data.total != null) setChatTotal(data.total);
        if (data.kindCounts) setChatKindTotals(data.kindCounts);
        setChatOffset(nextOffset);
        setChats(prev => {
          const existingIds = new Set(prev.map(c => c.id));
          const appended = newChats.filter(c => !existingIds.has(c.id));
          return [...prev, ...appended];
        });
      }
    } catch (error) {
      console.error('Error loading more chats:', error);
    } finally {
      setLoadingMoreChats(false);
    }
  }, [chatOffset, loadingMoreChats, searchQuery]);

  const updateChatTitleLocally = useCallback((chatId: string, title: string) => {
    setChats(prev => prev.map(c => c.id === chatId ? { ...c, title } : c));
    if (chatId === currentChatId) setCurrentChatTitle(title);
  }, [currentChatId]);

  // Load chat list on mount (and when refreshChatList reference changes)
  useEffect(() => {
    if (!enabled) return;
    refreshChatList();
  }, [enabled, refreshChatList]);

  const saveChatById = useCallback(async (chatId: string | null, skipRefresh = false) => {
    const key = keyForChat(chatId);
    // Use refs to get current state, not stale closure
    const chatMessages = messagesByChatRef.current[key] ?? [];
    const chatConfig = configByChatRef.current[key] ?? config;

    if (!chatId) {
      if (chatMessages.length === 0) return;
      const chatTitle = 'New Chat';
      try {
        const res = await fetch(`${getApiBase()}/chats`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: chatTitle, config: stripDenyApprovalPolicies(chatConfig), messages: chatMessages })
        });
        if (res.ok) {
          const newChat: Chat = await res.json();
          const newKey = keyForChat(newChat.id);
          setMessagesByChat(prev => {
            const next = { ...prev };
            delete next[key];
            next[newKey] = chatMessages;
            return next;
          });
          setConfigByChat(prev => {
            const next = { ...prev };
            delete next[key];
            next[newKey] = chatConfig;
            return next;
          });
          setCurrentChatId(newChat.id);
          setCurrentChatTitle(newChat.title);
          if (!skipRefresh) await refreshChatList();
        } else {
          console.error('Failed to create chat:', res.status, res.statusText);
        }
      } catch (error) {
        console.error('Error saving new chat:', error);
      }
      return;
    }

    try {
      const payload: any = { config: stripDenyApprovalPolicies(chatConfig) };

      const res = await fetch(`${getApiBase()}/chats/${chatId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        if (!skipRefresh) await refreshChatList();
      } else {
        console.error('Failed to save chat:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error saving chat:', error);
    }
  }, [chats, config, currentChatId, currentChatTitle, refreshChatList]);
  // Note: messagesByChat and configByChat removed from deps - using refs instead

  const saveCurrentChat = useCallback(async (skipRefresh = false) => {
    await saveChatById(currentChatId, skipRefresh);
  }, [currentChatId, saveChatById]);

  const clearScheduledSave = useCallback((chatId: string | null) => {
    const key = keyForChat(chatId);
    const registry = saveTimeoutsRef.current;
    if (registry[key]) {
      clearTimeout(registry[key]);
      delete registry[key];
    }
  }, []);

  const scheduleSave = useCallback((chatId: string | null, delay: number) => {
    const key = keyForChat(chatId);
    const registry = saveTimeoutsRef.current;
    if (registry[key]) {
      clearTimeout(registry[key]);
    }
    registry[key] = setTimeout(() => {
      saveChatById(chatId, true).catch(error => {
        console.error('Error during scheduled save:', error);
      });
    }, delay);
  }, [saveChatById]);

  const forceSaveNow = useCallback(async (chatId?: string | null) => {
    const targetChatId = chatId ?? currentChatId;
    clearScheduledSave(targetChatId);
    await saveChatById(targetChatId, false);
  }, [clearScheduledSave, currentChatId, saveChatById]);

  const finalSave = useCallback(async (chatId?: string | null) => {
    await forceSaveNow(chatId);
  }, [forceSaveNow]);

  const optimizedSetConfig = useCallback((nextConfig: ChatConfig | ((prev: ChatConfig) => ChatConfig)) => {
    const resolved = typeof nextConfig === 'function' ? (nextConfig as (prev: ChatConfig) => ChatConfig)(config) : nextConfig;
    const key = keyForChat(currentChatId);
    const previousConfig = configByChat[key];
    setConfigState(resolved);
    setConfigByChat(prevConfigs => ({ ...prevConfigs, [key]: resolved }));

    // Save reusable preferences for the next new chat without chat-scoped state.
    try {
      localStorage.setItem(LAST_CONFIG_KEY, JSON.stringify(stripReusableConfig(resolved)));
    } catch (e) {
      console.warn('Failed to save config to localStorage:', e);
    }

    // Check if preferences actually changed before saving to backend
    const newPrefs = {
      model: resolved.model,
      agent: resolved.agent,
      tools: resolved.tools,
      memory_enabled: resolved.memory_enabled,
      sandbox_enabled: resolved.sandbox_enabled,
      sandbox_volumes: resolved.sandbox_volumes
    };

    const lastSaved = lastSavedPreferencesRef.current;
    const prefsChanged = !preferencesEqual(lastSaved, newPrefs);

    if (prefsChanged) {
      // Save preferences to backend database (async, don't await)
      import('../lib/api').then(({ saveUserPreferences }) => {
        saveUserPreferences(newPrefs).then(() => {
          // Update ref after successful save
          lastSavedPreferencesRef.current = newPrefs;

          // Also update the local backendConfig state so that subsequent calls to 
          // computeDefaultConfig() (e.g. when starting a new chat) use the updated preferences
          setBackendConfig(prev => {
            if (!prev) return prev;
            return {
              ...prev,
              userPreferences: {
                ...(prev.userPreferences || {
                  model: '',
                  agent: '',
                  tools: [],
                  memory_enabled: false
                }),
                ...newPrefs,
                memory_enabled: !!newPrefs.memory_enabled // Ensure boolean for required field
              }
            };
          });
        }).catch(err => {
          console.warn('Failed to save preferences to backend:', err);
        });
      });
    }

    if (currentChatId && !configsEqual(previousConfig, resolved)) {
      scheduleSave(currentChatId, 1500);
    }
  }, [config, currentChatId, configByChat, scheduleSave]);

  const addMessage = useCallback((message: Message, chatId: string | null = currentChatId) => {
    setMessagesForChat(chatId, prev => [...prev, message]);
    scheduleSave(chatId, 800);
  }, [currentChatId, scheduleSave, setMessagesForChat]);

  const updateLastUserMessageImages = useCallback((images: any[], chatId: string | null = currentChatId) => {
    setMessagesForChat(chatId, prev => {
      if (!prev.length) {
        return prev;
      }

      // Find the last user message (search backward)
      let userMessageIndex = -1;
      for (let i = prev.length - 1; i >= 0; i--) {
        if (prev[i].role === 'user') {
          userMessageIndex = i;
          break;
        }
      }

      if (userMessageIndex === -1) {
        return prev;
      }

      const updated = [...prev];
      updated[userMessageIndex] = { ...updated[userMessageIndex], images };
      return updated;
    });
    scheduleSave(chatId, 800);
  }, [currentChatId, scheduleSave, setMessagesForChat]);

  const updateAssistantStreaming = useCallback((delta: string, chatId: string | null = currentChatId) => {
    // Preserve leading/trailing newlines so streamed code stays line-accurate
    const norm = String(delta)
      .replace(/\r\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n');

    setMessagesForChat(chatId, prev => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== 'assistant') {
        return [...prev, { role: 'assistant', content: norm }];
      }
      const updated = [...prev];
      updated[updated.length - 1] = { ...last, content: last.content + norm };
      return updated;
    });
    scheduleSave(chatId, 2000);
  }, [currentChatId, scheduleSave, setMessagesForChat]);

  const newAssistantMessage = useCallback((chatId: string | null = currentChatId) => {
    setMessagesForChat(chatId, prev => [...prev, { role: 'assistant', content: '' }]);
  }, [currentChatId, setMessagesForChat]);

  const setStepInfo = useCallback((stepInfo: string, chatId: string | null = currentChatId) => {
    setMessagesForChat(chatId, prev => {
      if (!prev.length) return prev;
      const last = prev[prev.length - 1];
      if (last.role === 'assistant') {
        const updated = [...prev];
        updated[updated.length - 1] = { ...last, stepInfo };
        return updated;
      }
      return prev;
    });
  }, [currentChatId, setMessagesForChat]);

  const removeEmptyAssistantMessage = useCallback((chatId: string | null = currentChatId) => {
    setMessagesForChat(chatId, prev => {
      if (!prev.length) return prev;
      const last = prev[prev.length - 1];
      if (last.role === 'assistant' && !last.content.trim()) {
        return prev.slice(0, -1);
      }
      return prev;
    });
  }, [currentChatId, setMessagesForChat]);

  const resetChat = useCallback(() => {
    const key = keyForChat(currentChatId);
    const fallbackConfig = computeDefaultConfig();
    setMessagesByChat(prev => ({ ...prev, [key]: [] }));
    setConfigByChat(prev => ({ ...prev, [key]: fallbackConfig }));
    setConfigState(fallbackConfig);
    setShouldResetNext(true);
    setCurrentChatId(null);
    setCurrentChatTitle('New Chat');
  }, [computeDefaultConfig, currentChatId]);

  const consumeResetFlag = useCallback(() => {
    setShouldResetNext(false);
  }, []);

  const updateMessage = useCallback((index: number, update: Partial<Message>, chatId: string | null = currentChatId) => {
    setMessagesForChat(chatId, prev => {
      if (index < 0 || index >= prev.length) return prev;
      const updated = [...prev];
      updated[index] = { ...updated[index], ...update };
      return updated;
    });
    scheduleSave(chatId, 800);
  }, [currentChatId, scheduleSave, setMessagesForChat]);

  // Remove all messages at or after `fromIndex`. Used by retry to strip the
  // last assistant response before re-streaming.
  const truncateMessagesFrom = useCallback((fromIndex: number, chatId: string | null = currentChatId) => {
    setMessagesForChat(chatId, prev => {
      if (fromIndex <= 0) return [];
      return prev.slice(0, fromIndex);
    });
  }, [currentChatId, setMessagesForChat]);

  const markChatRollbackExpected = useCallback((chatId: string | null = currentChatId) => {
    if (!chatId) return;
    rollbackExpectedChatIdsRef.current.add(chatId);
  }, [currentChatId]);

  const setStreamingState = useCallback((streaming: boolean, chatId?: string | null) => {
    setIsStreamingState(streaming);
    const targetChatId = chatId ?? currentChatId;

    // Update ref synchronously for immediate access
    if (streaming) {
      activeStreamingChatIdRef.current = targetChatId;
    } else {
      activeStreamingChatIdRef.current = null;
    }

    setActiveStreamingChatId(prev => {
      if (streaming) {
        return targetChatId;
      }
      // When streaming stops, update the sidebar summary for this chat
      if (!streaming && targetChatId) {
        const key = keyForChat(targetChatId);
        const chatMessages = messagesByChatRef.current[key] ?? [];
        if (chatMessages.length > 0) {
          setChats(current => {
            const index = current.findIndex(c => c.id === targetChatId);
            if (index === -1) return current;
            const updated = [...current];
            const summary = updated[index];
            updated[index] = {
              ...summary,
              messageCount: chatMessages.length,
              lastMessage: chatMessages[chatMessages.length - 1].content.replace(/<details\b[^>]*>[\s\S]*?<\/details>/gi, '').replace(/<[^>]+>/g, '').trim().slice(0, 100),
              updatedAt: new Date().toISOString()
            };
            return updated;
          });
        }
      }
      if (chatId && prev && prev !== chatId) {
        return prev;
      }
      return null;
    });
  }, [currentChatId]);

  const createNewChat = useCallback(async (): Promise<string | null> => {
    if (currentChatId) {
      return currentChatId;
    }
    if (chatCreationPromiseRef.current) {
      return chatCreationPromiseRef.current;
    }

    // Cancel any pending saves for the unsaved chat
    clearScheduledSave(null);

    const promise = (async () => {
      const unsavedKey = UNSAVED_CHAT_KEY;
      const chatMessages = messagesByChat[unsavedKey] ?? [];
      const baseConfig = configByChat[unsavedKey] ?? computeDefaultConfig();
      const effectiveConfig: ChatConfig = {
        ...baseConfig,
        tools: [...(baseConfig.tools || [])],
        mcp_urls: Array.isArray(baseConfig.mcp_urls)
          ? [...baseConfig.mcp_urls]
          : { ...(baseConfig.mcp_urls || {}) }
      };

      const chatTitle = 'New Chat';

      try {
        const projectId = currentProjectIdRef.current;
        const res = await fetch(`${getApiBase()}/chats`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: chatTitle,
            config: effectiveConfig,
            messages: chatMessages,
            project_id: projectId || undefined,
          })
        });

        if (!res.ok) {
          console.error('Failed to create chat:', res.status, res.statusText);
          return null;
        }

        const newChat: Chat = await res.json();
        const newKey = keyForChat(newChat.id);

        setCurrentChatId(newChat.id);
        setCurrentChatTitle(newChat.title);
        setMessagesByChat(prev => {
          const next = { ...prev };
          delete next[UNSAVED_CHAT_KEY];
          next[newKey] = chatMessages;
          return next;
        });
        setConfigState(effectiveConfig);
        setConfigByChat(prev => {
          const next = { ...prev };
          delete next[UNSAVED_CHAT_KEY];
          next[newKey] = effectiveConfig;
          return next;
        });
        setShouldResetNext(false);

        const createdProjectId = projectId || undefined;
        const createdProject = createdProjectId ? projects.find(p => p.id === createdProjectId) : undefined;
        const summary: ChatSummary = {
          id: newChat.id,
          title: newChat.title,
          createdAt: newChat.createdAt,
          updatedAt: newChat.updatedAt,
          messageCount: chatMessages.length,
          lastMessage: chatMessages.length ? chatMessages[chatMessages.length - 1].content.slice(0, 100) : undefined,
          projectId: createdProjectId ?? null,
          projectName: createdProject?.name ?? null,
          projectSlug: createdProject?.slug ?? null,
        };

        setChats(prev => {
          const existingIndex = prev.findIndex(c => c.id === newChat.id);
          if (existingIndex !== -1) {
            const updated = [...prev];
            updated[existingIndex] = summary;
            return updated;
          }
          return [summary, ...prev];
        });

        return newChat.id;
      } catch (error) {
        console.error('Error creating chat:', error);
        return null;
      } finally {
        // Refresh will happen after save completes, no need to refresh here
      }
    })();

    chatCreationPromiseRef.current = promise;
    const result = await promise;
    chatCreationPromiseRef.current = null;
    return result;
  }, [currentChatId, messagesByChat, configByChat, computeDefaultConfig, refreshChatListInternal, clearScheduledSave]);

  const loadChat = useCallback(async (chatId: string, options?: { force?: boolean }) => {
    const force = !!options?.force;
    // Clear any pending saves for the previous chat before switching
    if (currentChatId && currentChatId !== chatId) {
      clearScheduledSave(currentChatId);
    }

    const key = keyForChat(chatId);
    const cachedMessages = messagesByChatRef.current[key];
    setCurrentChatId(chatId);
    setShouldResetNext(false);

    const summary = chats.find(c => c.id === chatId);
    if (summary) {
      setCurrentChatTitle(summary.title);
    }

    const cachedConfig = configByChat[key];
    if (cachedConfig) {
      setConfigState(cachedConfig);
      // Save reusable preferences for the next new chat without chat-scoped state.
      try {
        localStorage.setItem(LAST_CONFIG_KEY, JSON.stringify(stripReusableConfig(cachedConfig)));
      } catch (e) {
        console.warn('Failed to save config to localStorage:', e);
      }
    }

    if (!force && cachedMessages) {
      return;
    }

    try {
      const res = await fetch(`${getApiBase()}/chats/${chatId}`);
      if (res.ok) {
        const chat: Chat = await res.json();
        setCurrentChatTitle(chat.title);

        if (chat.contextUsage || chat.contextTokens) {
          const contextUsageStore = useContextUsageStore.getState();
          const existingUsage = contextUsageStore.getUsageForChat(chatId);
          const serverUsage = chat.contextUsage;
          const contextTokens = serverUsage?.context_tokens ?? chat.contextTokens ?? existingUsage?.context_tokens ?? 0;
          contextUsageStore.setUsageForChat(chatId, {
            input_tokens: serverUsage?.input_tokens ?? existingUsage?.input_tokens ?? contextTokens,
            output_tokens: serverUsage?.output_tokens ?? existingUsage?.output_tokens ?? 0,
            total_tokens: serverUsage?.total_tokens ?? existingUsage?.total_tokens ?? contextTokens,
            context_tokens: contextTokens,
            cache_write_tokens: serverUsage?.cache_write_tokens ?? existingUsage?.cache_write_tokens ?? 0,
            cache_read_tokens: serverUsage?.cache_read_tokens ?? existingUsage?.cache_read_tokens ?? 0,
            requests: serverUsage?.requests ?? existingUsage?.requests ?? 0,
            details: serverUsage?.details ?? existingUsage?.details,
          });
        }
        const loadedConfig = hydrateChatConfig(
          stripDenyApprovalPolicies(chat.config),
          computeDefaultConfig(),
        );
        setConfigByChat(prev => ({ ...prev, [key]: loadedConfig }));
        setConfigState(loadedConfig);
        // Save reusable preferences for the next new chat without chat-scoped state.
        try {
          localStorage.setItem(LAST_CONFIG_KEY, JSON.stringify(stripReusableConfig(loadedConfig)));
        } catch (e) {
          console.warn('Failed to save config to localStorage:', e);
        }
        setMessagesByChat(prev => {
          const rollbackExpected = rollbackExpectedChatIdsRef.current.has(chatId);
          // 100% Backend Authored: backend is ALWAYS the source of truth for ALL chats.
          // Map backend JSON (which includes strict tool_calls arrays and 'tool' roles)
          // into the legacy HTML `<details>` string blocks that the UI parser expects.
          const serverMessages: any[] = chat.messages || [];
          const mappedMessages: Message[] = [];
          
          let currentAssistant: Partial<Message> | null = null;
          // True while the currentAssistant had tool_calls but hasn't yet received
          // a follow-up assistant message (the final-text continuation of that turn).
          // Reset to false once the continuation arrives so the NEXT assistant is a
          // new independent bubble (e.g. a wakeup turn).
          let awaitingToolContinuation = false;

          for (const msg of serverMessages) {
            if (msg.role === 'user') {
              // Empty user rows are tool-resume continuations (system-reminder injected
              // by the backend, then stripped to empty). Drop them — they don't represent
              // a real turn and must not flush the assistant buffer or act as boundaries.
              if (!(msg.content || '').trim() && !(msg.images?.length) && !(msg.files?.length)) {
                continue;
              }
              if (currentAssistant) { mappedMessages.push(currentAssistant as Message); currentAssistant = null; }
              awaitingToolContinuation = false;
              mappedMessages.push(msg);
            } else if (msg.role === 'system_triggered' || msg.role === 'trigger') {
              // 'trigger' is the legacy name; normalize to 'system_triggered' so the
              // rest of the render pipeline only needs to handle one role.
              if (currentAssistant) { mappedMessages.push(currentAssistant as Message); currentAssistant = null; }
              awaitingToolContinuation = false;
              mappedMessages.push({ ...msg, role: 'system_triggered' } as Message);
            } else if (msg.role === 'assistant') {
              if (!currentAssistant) {
                currentAssistant = { ...msg, content: msg.content || '' };
                awaitingToolContinuation = false;
              } else if (awaitingToolContinuation) {
                // This assistant message is the final-text continuation of the
                // preceding tool-call turn — merge it into the same bubble.
                if (msg.content) {
                  currentAssistant.content = (currentAssistant.content ? currentAssistant.content + '\n\n' : '') + msg.content;
                }
                if (Array.isArray(msg.parts) && msg.parts.length > 0) {
                  currentAssistant.parts = [
                    ...((currentAssistant.parts as any[] | undefined) || []),
                    ...msg.parts,
                  ];
                }
                awaitingToolContinuation = false;
              } else {
                // Independent assistant turn (e.g. wakeup) — new bubble.
                mappedMessages.push(currentAssistant as Message);
                currentAssistant = { ...msg, content: msg.content || '' };
                awaitingToolContinuation = false;
              }
              if (msg.tool_calls && Array.isArray(msg.tool_calls)) {
                msg.tool_calls.forEach((tc: any) => {
                  const args = escapeHtml(typeof tc.function.arguments === 'string' ? tc.function.arguments : JSON.stringify(tc.function.arguments));
                  const stateAttr = tc.state === 'approval-requested' ? ' data-approval-state="pending"' : '';
                  const idAttr = tc.id ? ` data-approval-id="${escapeHtml(tc.id)}"` : '';
                  currentAssistant!.content += `\n<details data-tool-call-id="${escapeHtml(tc.id ?? '')}"${idAttr}${stateAttr}><summary>🔧 ${escapeHtml(tc.function.name)}</summary>\n<pre><code class="language-json">${args}</code></pre>\n</details>\n`;
                });
                awaitingToolContinuation = true;
              }
            } else if (msg.role === 'tool') {
              if (!currentAssistant) {
                currentAssistant = { role: 'assistant', content: '' };
              }
              currentAssistant.content += `\n<details data-tool-call-id="${escapeHtml(msg.tool_call_id ?? '')}"><summary>📦 ${escapeHtml(msg.name ?? '')}</summary>\n<pre><code class="language-text">${escapeHtml(msg.content ?? '')}</code></pre>\n</details>\n`;
              awaitingToolContinuation = true;
            } else {
              if (currentAssistant) { mappedMessages.push(currentAssistant as Message); currentAssistant = null; }
              awaitingToolContinuation = false;
              mappedMessages.push(msg);
            }
          }
          if (currentAssistant) { mappedMessages.push(currentAssistant as Message); }

          // Prevent UI flicker: if local store has more messages (e.g. optimistic append right after stream),
          // don't let stale backend DB state overwrite it. Wait until DB catches up.
          const existing = prev[key] || [];
          if (rollbackExpected && existing.length > 0 && mappedMessages.length > existing.length) {
            return prev;
          }
          // Guard (edit flow): an edit optimistically replaces the last user
          // message with new text, then the backend rolls history back and
          // replays it via /retry-edit. Until that replay re-persists the edited
          // message, the server snapshot still carries the ORIGINAL text. Keep the
          // optimistic local state — and crucially preserve the rollback flag — so
          // a sync arriving mid-rollback can't revert the bubble to the old text.
          if (rollbackExpected) {
            const lastLocalUser = [...existing].reverse().find((m: Message) => m.role === 'user');
            const lastServerUser = [...mappedMessages].reverse().find((m: Message) => m.role === 'user');
            if (
              lastLocalUser &&
              typeof lastLocalUser.content === 'string' &&
              lastLocalUser.content.trim() &&
              (!lastServerUser ||
                (typeof lastServerUser.content === 'string' &&
                  lastServerUser.content.trim() !== lastLocalUser.content.trim()))
            ) {
              return prev;
            }
          }
          if (existing.length > mappedMessages.length && !rollbackExpected) {
            return prev;
          }
          // Guard: a force reload can arrive after the frontend optimistically
          // appended the user's message but before the backend display log has
          // caught up. Keep the local user bubble visible while the agent stream
          // continues, then let the next fresh server snapshot replace it.
          if (!rollbackExpected && shouldKeepOptimisticUserMessage(existing, mappedMessages)) {
            return prev;
          }
          // Guard: keep optimistic local content when server is still mid-postprocess.
          // Covers both equal-count and server-has-more cases: if local last assistant has
          // real text and server last assistant is tool-only (intermediate), backend hasn't
          // finished writing the final reply yet.
          if (!rollbackExpected && shouldKeepLocalAssistantContent(existing, mappedMessages)) {
            return prev;
          }
          // Guard against replacing locally-resolved content with a stale pending-approval
          // DB state. This race occurs when loadChat is called immediately after a resume
          // stream ends but before the backend persists the final resolved state.
          // Compare the LAST assistant message on each side — this avoids false negatives
          // when earlier history messages happen to contain pending state from old sessions.
          const msgHasPendingApproval = (m: Message) => {
            if (typeof m.content === 'string' && m.content.includes('data-approval-state="pending"')) return true;
            if (Array.isArray((m as any).parts)) {
              return (m as any).parts.some((p: any) => p.type === 'tool' && p.state === 'approval-requested');
            }
            return false;
          };
          const serverHasPendingApproval = mappedMessages.some(msgHasPendingApproval);
          const lastLocalAssistant = existing.length > 0
            ? [...existing].reverse().find((m: Message) => m.role === 'assistant')
            : undefined;
          const localLastAssistantHasNoPending = lastLocalAssistant != null && !msgHasPendingApproval(lastLocalAssistant);
          if (!rollbackExpected && serverHasPendingApproval && localLastAssistantHasNoPending) {
            return prev;
          }
          // Guard: local has completed tool outputs (📦) that the server hasn't persisted yet.
          // Count output blocks — if local has more, server is still catching up.
          const countOutputs = (msgs: Message[]) => msgs.reduce(
            (n, m) => n + (typeof m.content === 'string' ? (m.content.match(/<summary>📦/g) ?? []).length : 0), 0
          );
          if (!rollbackExpected && existing.length > 0 && countOutputs(existing) > countOutputs(mappedMessages)) {
            return prev;
          }

          // Guard: prevent stale backend snapshots from replacing richer local assistant
          // content with a shorter/empty variant when counts are otherwise equal.
          const getLastAssistant = (msgs: Message[]) =>
            msgs.length > 0 ? [...msgs].reverse().find((m: Message) => m.role === 'assistant') : undefined;
          const localLastAssistant = getLastAssistant(existing);
          const serverLastAssistant = getLastAssistant(mappedMessages);
          if (!rollbackExpected && localLastAssistant && serverLastAssistant) {
            const localContent = typeof localLastAssistant.content === 'string' ? localLastAssistant.content.trim() : '';
            const serverContent = typeof serverLastAssistant.content === 'string' ? serverLastAssistant.content.trim() : '';

            // If server regresses to much shorter content while structure counts are equal,
            // keep optimistic local data until the backend catches up.
            if (
              localContent.length > 0 &&
              serverContent.length > 0 &&
              existing.length === mappedMessages.length &&
              countOutputs(existing) === countOutputs(mappedMessages) &&
              serverContent.length + 40 < localContent.length
            ) {
              return prev;
            }

            if (
              localContent.length > 0 &&
              serverContent.length === 0 &&
              existing.length === mappedMessages.length
            ) {
              return prev;
            }
          }
          rollbackExpectedChatIdsRef.current.delete(chatId);
          return { ...prev, [key]: mappedMessages };
        });
        setShouldResetNext(false);
      } else {
        console.error('Failed to load chat:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error loading chat:', error);
    }
  }, [chats, configByChat, currentChatId, clearScheduledSave]);

  const deleteChat = useCallback(async (chatId: string, { cascade = false }: { cascade?: boolean } = {}) => {
    const key = keyForChat(chatId);
    const deletedSummary = chats.find(c => c.id === chatId);
    const deletedIndex = chats.findIndex(c => c.id === chatId);
    const deletedMessages = messagesByChatRef.current[key];
    const deletedConfig = configByChatRef.current[key];
    const wasCurrent = currentChatId === chatId;

    // Optimistic UI: remove immediately so delete feels instant.
    // When cascading, also remove subagent children from the local chats list.
    setChats(prev => {
      if (!cascade) return prev.filter(c => c.id !== chatId);
      return prev.filter(c => {
        if (c.id === chatId) return false;
        const config = (c as any).config;
        const parentId = (c as any).parentChatId;
        return !(parentId === chatId);
      });
    });
    setMessagesByChat(prev => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    setConfigByChat(prev => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    if (wasCurrent) {
      beginNewChat();
    }

    try {
      const url = cascade
        ? `${getApiBase()}/chats/${chatId}?cascade=true`
        : `${getApiBase()}/chats/${chatId}`;
      const res = await fetch(url, { method: 'DELETE' });
      if (!res.ok) {
        throw new Error(`Failed to delete chat: ${res.status} ${res.statusText}`);
      }

      // Background consistency sync (non-blocking).
      void refreshChatListSilently();
    } catch (error) {
      console.error('Error deleting chat:', error);

      // Roll back optimistic removal if delete fails.
      if (deletedSummary) {
        setChats(prev => {
          if (prev.some(c => c.id === deletedSummary.id)) return prev;
          const next = [...prev];
          const idx = deletedIndex >= 0 ? Math.min(deletedIndex, next.length) : next.length;
          next.splice(idx, 0, deletedSummary);
          return next;
        });
      }
      if (deletedMessages) {
        setMessagesByChat(prev => ({ ...prev, [key]: deletedMessages }));
      }
      if (deletedConfig) {
        setConfigByChat(prev => ({ ...prev, [key]: deletedConfig }));
      }
      if (wasCurrent) {
        // Try to restore the previously selected chat after rollback.
        try { await loadChat(chatId, { force: true }); } catch { /* ignore */ }
      }
    }
  }, [beginNewChat, chats, currentChatId, loadChat, refreshChatListSilently]);

  const renameChat = useCallback(async (chatId: string, title: string) => {
    const prev = chats.find(c => c.id === chatId);
    updateChatTitleLocally(chatId, title);
    try {
      const res = await fetch(`${getApiBase()}/chats/${chatId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      });
      if (!res.ok) throw new Error(`Failed to rename chat: ${res.status}`);
    } catch (error) {
      console.error('Error renaming chat:', error);
      if (prev) updateChatTitleLocally(chatId, prev.title ?? '');
    }
  }, [chats, updateChatTitleLocally]);

  const coreValue = useMemo<ChatCoreContextValue>(() => ({
      config,
      setConfig: optimizedSetConfig,
      addMessage,
      updateLastUserMessageImages,
      updateAssistantStreaming,
      backendConfig,
      refreshBackendConfig,
      newAssistantMessage,
      setStepInfo,
      resetChat,
      shouldResetNext,
      consumeResetFlag,
      setIsStreaming: setStreamingState,
      removeEmptyAssistantMessage,
      currentChatId,
      chats,
      chatTotal,
      chatKindTotals,
      loadingChats,
      loadingMoreChats,
      refreshingChats,
      searchQuery,
      setSearchQuery,
      beginNewChat,
      createNewChat,
      loadChat,
      saveCurrentChat,
      finalSave,
      forceSaveNow,
      deleteChat,
      renameChat,
      refreshChatList,
      refreshChatListSilently,
      loadMoreChats,
      updateChatTitleLocally,
      updateMessage,
      truncateMessagesFrom,
      markChatRollbackExpected,
      setViewSwitcher,
      switchToView,
      hideToolCalls,
      toggleHideToolCalls
  }), [
    config,
    optimizedSetConfig,
    addMessage,
    updateLastUserMessageImages,
    updateAssistantStreaming,
    backendConfig,
    refreshBackendConfig,
    newAssistantMessage,
    setStepInfo,
    resetChat,
    shouldResetNext,
    consumeResetFlag,
    setStreamingState,
    removeEmptyAssistantMessage,
    currentChatId,
    chats,
    chatTotal,
    chatKindTotals,
    loadingChats,
    loadingMoreChats,
    refreshingChats,
    searchQuery,
    setSearchQuery,
    beginNewChat,
    createNewChat,
    loadChat,
    saveCurrentChat,
    finalSave,
    forceSaveNow,
    deleteChat,
    renameChat,
    refreshChatList,
    refreshChatListSilently,
    loadMoreChats,
    updateChatTitleLocally,
    updateMessage,
    truncateMessagesFrom,
    markChatRollbackExpected,
    setViewSwitcher,
    switchToView,
    hideToolCalls,
    toggleHideToolCalls,
  ]);

  const streamingValue = useMemo<ChatStreamingContextValue>(() => ({
    messages,
    isStreaming,
    activeStreamingChatId,
  }), [messages, isStreaming, activeStreamingChatId]);

  return (
    <ChatCoreContext.Provider value={coreValue}>
      <ChatStreamingContext.Provider value={streamingValue}>
        {children}
      </ChatStreamingContext.Provider>
    </ChatCoreContext.Provider>
  );
};

export const useChatCoreStore = () => {
  const ctx = useContext(ChatCoreContext);
  if (!ctx) throw new Error('useChatCoreStore must be used within ChatProvider');
  return ctx;
};

export const useChatStreamingStore = () => {
  const ctx = useContext(ChatStreamingContext);
  if (!ctx) throw new Error('useChatStreamingStore must be used within ChatProvider');
  return ctx;
};

export const useChatStore = (): ChatContextValue => {
  const core = useChatCoreStore();
  const streaming = useChatStreamingStore();
  return useMemo(() => ({ ...core, ...streaming }), [core, streaming]);
};
