import React, { createContext, useContext, useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Message, ChatConfig, ConfigOptions, Chat, ChatSummary } from '../types/api';
import { getApiBase } from '../lib/api';

interface ChatContextValue {
  messages: Message[];
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
  isStreaming: boolean;
  activeStreamingChatId: string | null;
  removeEmptyAssistantMessage: (chatId?: string | null) => void;
  currentChatId: string | null;
  chats: ChatSummary[];
  loadingChats: boolean;
  refreshingChats: boolean;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  beginNewChat: () => void;
  createNewChat: () => Promise<string | null>;
  loadChat: (chatId: string) => Promise<void>;
  saveCurrentChat: (skipRefresh?: boolean) => Promise<void>;
  finalSave: (chatId?: string | null) => Promise<void>;
  forceSaveNow: (chatId?: string | null) => Promise<void>;
  deleteChat: (chatId: string) => Promise<void>;
  refreshChatList: (searchQuery?: string) => Promise<void>;
  setViewSwitcher?: (switcher: (view: 'chat' | 'memory') => void) => void;
  switchToView?: (view: 'chat' | 'memory') => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

const defaultConfig: ChatConfig = {
  model: '',
  agent: '',
  tools: [],
  mcp_urls: [],
  mcp_enabled: {},
  sandbox_enabled: true // Default to true to match backend
};

const UNSAVED_CHAT_KEY = '__unsaved__';
const LAST_CONFIG_KEY = 'suzent_last_config';
const keyForChat = (chatId: string | null) => chatId ?? UNSAVED_CHAT_KEY;

/** Build a ChatConfig from user preferences and backend defaults. */
const buildConfigFromPreferences = (
  prefs: ConfigOptions['userPreferences'],
  backendDefaults: ConfigOptions
): ChatConfig => ({
  model: prefs?.model || backendDefaults.models[0] || '',
  agent: prefs?.agent || backendDefaults.agents[0] || '',
  tools: prefs?.tools || backendDefaults.defaultTools || [],
  memory_enabled: prefs?.memory_enabled,
  sandbox_enabled: prefs?.sandbox_enabled ?? backendDefaults.sandboxEnabled ?? true,
  sandbox_volumes: prefs?.sandbox_volumes || [],
  mcp_urls: [],
  mcp_enabled: {}
});

/** Extract the preference fields we track for dirty-checking. */
const extractSavedPreferences = (prefs: ConfigOptions['userPreferences']) => ({
  model: prefs?.model ?? '',
  agent: prefs?.agent ?? '',
  tools: prefs?.tools ?? [],
  memory_enabled: prefs?.memory_enabled,
  sandbox_enabled: prefs?.sandbox_enabled,
  sandbox_volumes: prefs?.sandbox_volumes
});

const configsEqual = (a?: ChatConfig | null, b?: ChatConfig | null): boolean => {
  if (a === b) return true;
  if (!a || !b) return false;
  const arrayEqual = (lhs?: string[], rhs?: string[]) => {
    const l = lhs ?? [];
    const r = rhs ?? [];
    if (l.length !== r.length) return false;
    return l.every((value, index) => value === r[index]);
  };
  const mcpUrlsEqual = (lhs?: string[] | { [key: string]: string }, rhs?: string[] | { [key: string]: string }) => {
    if (lhs === rhs) return true;
    if (!lhs || !rhs) return false;

    // Check if both are arrays
    const isLeftArray = Array.isArray(lhs);
    const isRightArray = Array.isArray(rhs);

    if (isLeftArray && isRightArray) {
      return arrayEqual(lhs as string[], rhs as string[]);
    }

    // Check if both are objects (records)
    if (!isLeftArray && !isRightArray) {
      const l = lhs as { [key: string]: string };
      const r = rhs as { [key: string]: string };
      const lKeys = Object.keys(l).sort();
      const rKeys = Object.keys(r).sort();

      if (!arrayEqual(lKeys, rKeys)) return false;
      return lKeys.every(key => l[key] === r[key]);
    }

    // Mismatched types
    return false;
  };

  return (
    a.model === b.model &&
    a.agent === b.agent &&
    arrayEqual(a.tools, b.tools) &&
    mcpUrlsEqual(a.mcp_urls, b.mcp_urls)
  );
};

export const ChatProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [messagesByChat, setMessagesByChat] = useState<Record<string, Message[]>>({
    [UNSAVED_CHAT_KEY]: []
  });
  const [configByChat, setConfigByChat] = useState<Record<string, ChatConfig>>({
    [UNSAVED_CHAT_KEY]: defaultConfig
  });
  const [config, setConfigState] = useState<ChatConfig>(defaultConfig);
  const [backendConfig, setBackendConfig] = useState<ConfigOptions | null>(null);
  const [shouldResetNext, setShouldResetNext] = useState(false);
  const [isStreaming, setIsStreamingState] = useState(false);
  const [activeStreamingChatId, setActiveStreamingChatId] = useState<string | null>(null);
  const activeStreamingChatIdRef = useRef<string | null>(null); // Ref for synchronous access
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [currentChatTitle, setCurrentChatTitle] = useState<string>('New Chat');
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [loadingChats, setLoadingChats] = useState(false);
  const [refreshingChats, setRefreshingChats] = useState(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const chatsLoadedRef = useRef(false);
  const chatCreationPromiseRef = useRef<Promise<string | null> | null>(null);
  const saveTimeoutsRef = useRef<Record<string, NodeJS.Timeout>>({});
  const messagesByChatRef = useRef(messagesByChat);
  const configByChatRef = useRef(configByChat);
  const viewSwitcherRef = useRef<((view: 'chat' | 'memory') => void) | null>(null);
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
            return parsed;
          }
        }
      }
    } catch (e) {
      console.warn('Failed to load last config from localStorage:', e);
    }

    // Fallback to backend defaults
    if (backendConfig) {
      return {
        model: backendConfig.models[0] || '',
        agent: backendConfig.agents[0] || '',
        tools: backendConfig.defaultTools || [],
        sandbox_enabled: backendConfig.sandboxEnabled ?? true,
        mcp_urls: [],
        mcp_enabled: {}
      };
    }
    return defaultConfig;
  }, [backendConfig]);

  const beginNewChat = useCallback(() => {
    const fallbackConfig = computeDefaultConfig();
    setCurrentChatId(null);
    setCurrentChatTitle('New Chat');
    setShouldResetNext(true);
    setMessagesByChat(prev => ({ ...prev, [UNSAVED_CHAT_KEY]: [] }));
    setConfigByChat(prev => ({ ...prev, [UNSAVED_CHAT_KEY]: fallbackConfig }));
    setConfigState(fallbackConfig);
  }, [computeDefaultConfig]);

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
            lastMessage: next.length ? next[next.length - 1].content.slice(0, 100) : undefined,
            updatedAt: new Date().toISOString()
          };
          return updated;
        });
      }

      return { ...prev, [key]: next };
    });
  }, []); // No dependencies needed since we use ref

  const messages = useMemo(() => getMessagesForChat(currentChatId), [getMessagesForChat, currentChatId]);

  // Helper to generate chat title from first message
  const generateChatTitle = useCallback((firstMessage: string): string => {
    if (!firstMessage.trim()) return 'New Chat';
    const title = firstMessage.trim().split('\n')[0];
    return title.length > 50 ? `${title.substring(0, 47)}...` : title;
  }, []);

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
    fetchConfigWithRetry();
  }, [fetchConfigWithRetry]);

  const refreshChatList = useCallback(async (search?: string, attempt = 1, maxAttempts = 5) => {
    const isFirstLoad = !chatsLoadedRef.current;
    if (isFirstLoad) {
      setLoadingChats(true);
    } else {
      setRefreshingChats(true);
    }
    const currentMessages = currentChatId ? getMessagesForChat(currentChatId) : null;
    try {
      const searchParam = search !== undefined ? search : searchQuery;
      // Use getApiBase() to ensure dynamic port resolution
      const apiBase = getApiBase();
      const url = searchParam ? `${apiBase}/chats?search=${encodeURIComponent(searchParam)}` : `${apiBase}/chats`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        const serverList: ChatSummary[] = data.chats || [];

        // Merge server list with local state, preserving local updates
        setChats(prev => {
          const merged = serverList.map(serverChat => {
            const localChat = prev.find(c => c.id === serverChat.id);
            // If we have local state with more messages, keep the local version
            if (localChat && localChat.messageCount > serverChat.messageCount) {
              return localChat;
            }
            // Otherwise use server version
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
        setTimeout(() => refreshChatList(search, attempt + 1, maxAttempts), delay);
        return; // Don't clear loading state yet
      } else {
        console.error('Failed to fetch chats:', res.status, res.statusText);
      }
    } catch (error) {
      if (isFirstLoad && attempt < maxAttempts) {
        // Network error on first load, retry with exponential backoff
        const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000);
        console.log(`Error fetching chat list, retrying in ${delay}ms... (attempt ${attempt}/${maxAttempts})`);
        setTimeout(() => refreshChatList(search, attempt + 1, maxAttempts), delay);
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
      if (!isFirstLoad) {
        setRefreshingChats(false);
      }
    }
  }, [currentChatId, currentChatTitle, getMessagesForChat, searchQuery]);

  // Load chat list on mount (and when refreshChatList reference changes)
  useEffect(() => {
    refreshChatList();
  }, [refreshChatList]);

  const saveChatById = useCallback(async (chatId: string | null, skipRefresh = false) => {
    const key = keyForChat(chatId);
    // Use refs to get current state, not stale closure
    const chatMessages = messagesByChatRef.current[key] ?? [];
    const chatConfig = configByChatRef.current[key] ?? config;

    if (!chatId) {
      if (chatMessages.length === 0) return;
      const chatTitle = chatMessages[0].role === 'user' ? generateChatTitle(chatMessages[0].content) : 'New Chat';
      try {
        const res = await fetch(`${getApiBase()}/chats`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: chatTitle, config: chatConfig, messages: chatMessages })
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
      let updateTitle: string | undefined;
      let baselineTitle: string = 'New Chat';
      if (chatMessages.length > 0 && chatMessages[0].role === 'user') {
        const existingSummary = chats.find(c => c.id === chatId);
        baselineTitle = existingSummary ? existingSummary.title : (currentChatId === chatId ? currentChatTitle : 'New Chat');
        if (baselineTitle === 'New Chat') {
          updateTitle = generateChatTitle(chatMessages[0].content);
        }
      }

      const payload: any = { config: chatConfig, messages: chatMessages };
      if (updateTitle) payload.title = updateTitle;

      const res = await fetch(`${getApiBase()}/chats/${chatId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        if (updateTitle) {
          setChats(prev => prev.map(chat => chat.id === chatId ? { ...chat, title: updateTitle } : chat));
          if (currentChatId === chatId) {
            setCurrentChatTitle(updateTitle);
          }
        }
        if (!skipRefresh) await refreshChatList();
      } else {
        console.error('Failed to save chat:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error saving chat:', error);
    }
  }, [chats, config, currentChatId, currentChatTitle, generateChatTitle, refreshChatList]);
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

    // Save to localStorage to remember for next new chat
    try {
      localStorage.setItem(LAST_CONFIG_KEY, JSON.stringify(resolved));
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
    const prefsChanged = !lastSaved ||
      lastSaved.model !== newPrefs.model ||
      lastSaved.agent !== newPrefs.agent ||
      lastSaved.memory_enabled !== newPrefs.memory_enabled ||
      lastSaved.sandbox_enabled !== newPrefs.sandbox_enabled ||
      JSON.stringify(lastSaved.tools) !== JSON.stringify(newPrefs.tools) ||
      JSON.stringify(lastSaved.sandbox_volumes) !== JSON.stringify(newPrefs.sandbox_volumes);

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
              lastMessage: chatMessages[chatMessages.length - 1].content.slice(0, 100),
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

      const firstUserMessage = chatMessages.find(msg => msg.role === 'user');
      const chatTitle = firstUserMessage ? generateChatTitle(firstUserMessage.content) : 'New Chat';

      try {
        const res = await fetch(`${getApiBase()}/chats`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: chatTitle,
            config: effectiveConfig,
            messages: chatMessages
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

        const summary: ChatSummary = {
          id: newChat.id,
          title: newChat.title,
          createdAt: newChat.createdAt,
          updatedAt: newChat.updatedAt,
          messageCount: chatMessages.length,
          lastMessage: chatMessages.length ? chatMessages[chatMessages.length - 1].content.slice(0, 100) : undefined
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
  }, [currentChatId, messagesByChat, configByChat, computeDefaultConfig, generateChatTitle, refreshChatList, clearScheduledSave]);

  const loadChat = useCallback(async (chatId: string) => {
    // Clear any pending saves for the previous chat before switching
    if (currentChatId && currentChatId !== chatId) {
      clearScheduledSave(currentChatId);
    }

    const key = keyForChat(chatId);
    setCurrentChatId(chatId);
    setShouldResetNext(false);

    const summary = chats.find(c => c.id === chatId);
    if (summary) {
      setCurrentChatTitle(summary.title);
    }

    const cachedConfig = configByChat[key];
    if (cachedConfig) {
      setConfigState(cachedConfig);
      // Save to localStorage to remember for next new chat
      try {
        localStorage.setItem(LAST_CONFIG_KEY, JSON.stringify(cachedConfig));
      } catch (e) {
        console.warn('Failed to save config to localStorage:', e);
      }
    }

    try {
      const res = await fetch(`${getApiBase()}/chats/${chatId}`);
      if (res.ok) {
        const chat: Chat = await res.json();
        setCurrentChatTitle(chat.title);
        setConfigByChat(prev => ({ ...prev, [key]: chat.config }));
        setConfigState(chat.config);
        // Save to localStorage to remember for next new chat
        try {
          localStorage.setItem(LAST_CONFIG_KEY, JSON.stringify(chat.config));
        } catch (e) {
          console.warn('Failed to save config to localStorage:', e);
        }
        setMessagesByChat(prev => {
          const existing = prev[key] ?? [];
          const serverMessages = chat.messages ?? [];
          if (existing.length >= serverMessages.length) {
            return prev;
          }
          return { ...prev, [key]: serverMessages };
        });
        setShouldResetNext(false);
      } else {
        console.error('Failed to load chat:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error loading chat:', error);
    }
  }, [chats, configByChat, currentChatId, clearScheduledSave]);

  const deleteChat = useCallback(async (chatId: string) => {
    try {
      const res = await fetch(`${getApiBase()}/chats/${chatId}`, { method: 'DELETE' });
      if (res.ok) {
        const key = keyForChat(chatId);
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
        if (currentChatId === chatId) {
          beginNewChat();
        }
        await refreshChatList();
      } else {
        console.error('Failed to delete chat:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error deleting chat:', error);
    }
  }, [beginNewChat, currentChatId, refreshChatList]);

  return (
    <ChatContext.Provider value={{
      messages,
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
      isStreaming,
      activeStreamingChatId,
      removeEmptyAssistantMessage,
      currentChatId,
      chats,
      loadingChats,
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
      refreshChatList,
      setViewSwitcher,
      switchToView
    }}>
      {children}
    </ChatContext.Provider>
  );
};

export const useChatStore = () => {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChatStore must be used within ChatProvider');
  return ctx;
};
