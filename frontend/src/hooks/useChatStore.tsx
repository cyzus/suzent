import React, { createContext, useContext, useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Message, ChatConfig, ConfigOptions, Chat, ChatSummary } from '../types/api';

interface ChatContextValue {
  messages: Message[];
  config: ChatConfig;
  setConfig: (c: ChatConfig | ((prev: ChatConfig) => ChatConfig)) => void;
  addMessage: (m: Message, chatId?: string | null) => void;
  updateAssistantStreaming: (delta: string, chatId?: string | null) => void;
  backendConfig: ConfigOptions | null;
  newAssistantMessage: (chatId?: string | null) => void;
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
  beginNewChat: () => void;
  createNewChat: () => Promise<string | null>;
  loadChat: (chatId: string) => Promise<void>;
  saveCurrentChat: (skipRefresh?: boolean) => Promise<void>;
  finalSave: (chatId?: string | null) => Promise<void>;
  forceSaveNow: (chatId?: string | null) => Promise<void>;
  deleteChat: (chatId: string) => Promise<void>;
  refreshChatList: () => Promise<void>;
}

const ChatContext = createContext<ChatContextValue | null>(null);

const defaultConfig: ChatConfig = {
  model: '',
  agent: '',
  tools: [],
  mcp_urls: []
};

const UNSAVED_CHAT_KEY = '__unsaved__';
const keyForChat = (chatId: string | null) => chatId ?? UNSAVED_CHAT_KEY;

const configsEqual = (a?: ChatConfig | null, b?: ChatConfig | null): boolean => {
  if (a === b) return true;
  if (!a || !b) return false;
  const arrayEqual = (left?: string[], right?: string[]) => {
  
    const l = left ?? [];
    const r = right ?? [];
    if (l.length !== r.length) return false;
    return l.every((value, index) => value === r[index]);
  };
  return (
    a.model === b.model &&
    a.agent === b.agent &&
    arrayEqual(a.tools, b.tools) &&
    arrayEqual(a.mcp_urls, b.mcp_urls)
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
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [currentChatTitle, setCurrentChatTitle] = useState<string>('New Chat');
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [loadingChats, setLoadingChats] = useState(false);
  const [refreshingChats, setRefreshingChats] = useState(false);
  const chatsLoadedRef = useRef(false);
  const chatCreationPromiseRef = useRef<Promise<string | null> | null>(null);
  const saveTimeoutsRef = useRef<Record<string, NodeJS.Timeout>>({});
  const messagesByChatRef = useRef(messagesByChat);
  const configByChatRef = useRef(configByChat);

  // Keep refs in sync with state
  useEffect(() => {
    messagesByChatRef.current = messagesByChat;
  }, [messagesByChat]);

  useEffect(() => {
    configByChatRef.current = configByChat;
  }, [configByChat]);

  const getMessagesForChat = useCallback((chatId: string | null) => {
    const key = keyForChat(chatId);
    return messagesByChat[key] ?? [];
  }, [messagesByChat]);

  const computeDefaultConfig = useCallback((): ChatConfig => {
    if (backendConfig) {
      return {
        model: backendConfig.models[0] || '',
        agent: backendConfig.agents[0] || '',
    tools: backendConfig.defaultTools || [],
    mcp_urls: []
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

      console.log('[setMessagesForChat]', {
        chatId,
        key,
        previousCount: previous.length,
        nextCount: next.length,
        allKeys: Object.keys(prev)
      });

      if (chatId) {
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
  }, [setChats]);

  const messages = useMemo(() => getMessagesForChat(currentChatId), [getMessagesForChat, currentChatId]);

  // Helper to generate chat title from first message
  const generateChatTitle = useCallback((firstMessage: string): string => {
    if (!firstMessage.trim()) return 'New Chat';
    const title = firstMessage.trim().split('\n')[0];
    return title.length > 50 ? `${title.substring(0, 47)}...` : title;
  }, []);

  // Fetch backend config once
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/config');
        if (res.ok) {
          const data: ConfigOptions = await res.json();
          setBackendConfig(data);
          const firstConfig: ChatConfig = {
            model: data.models[0] || '',
            agent: data.agents[0] || '',
            tools: data.defaultTools || [],
            mcp_urls: []
          };
          setConfigState(firstConfig);
          setConfigByChat(prev => ({ ...prev, [UNSAVED_CHAT_KEY]: firstConfig }));
        } else {
          console.error('Failed to fetch config:', res.status, res.statusText);
        }
      } catch (error) {
        console.error('Error fetching config:', error);
      }
    })();
  }, []);

  const refreshChatList = useCallback(async () => {
    const isFirstLoad = !chatsLoadedRef.current;
    if (isFirstLoad) {
      setLoadingChats(true);
    } else {
      setRefreshingChats(true);
    }
    const currentMessages = currentChatId ? getMessagesForChat(currentChatId) : null;
    try {
      const res = await fetch('/api/chats');
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
      } else {
        console.error('Failed to fetch chats:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error fetching chats:', error);
    } finally {
      if (isFirstLoad) {
        setLoadingChats(false);
        chatsLoadedRef.current = true;
      }
      setRefreshingChats(false);
    }
  }, [currentChatId, currentChatTitle, getMessagesForChat]);

  // Load chat list on mount (and when refreshChatList reference changes)
  useEffect(() => {
    refreshChatList();
  }, [refreshChatList]);

  const saveChatById = useCallback(async (chatId: string | null, skipRefresh = false) => {
    const key = keyForChat(chatId);
    // Use refs to get current state, not stale closure
    const chatMessages = messagesByChatRef.current[key] ?? [];
    const chatConfig = configByChatRef.current[key] ?? config;

    console.log('[saveChatById] Saving chat:', {
      chatId,
      key,
      messageCount: chatMessages.length,
      skipRefresh,
      allKeys: Object.keys(messagesByChatRef.current),
      messagesInKey: messagesByChatRef.current[key]?.length
    });

    if (!chatId) {
      if (chatMessages.length === 0) return;
      const chatTitle = chatMessages[0].role === 'user' ? generateChatTitle(chatMessages[0].content) : 'New Chat';
      try {
        const res = await fetch('/api/chats', {
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

      console.log('[saveChatById] Updating existing chat:', {
        chatId,
        messageCount: chatMessages.length,
        updateTitle,
        existingTitle: baselineTitle
      });

      const res = await fetch(`/api/chats/${chatId}`, {
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
    if (currentChatId && !configsEqual(previousConfig, resolved)) {
      scheduleSave(currentChatId, 1500);
    }
  }, [config, currentChatId, configByChat, scheduleSave]);

  const addMessage = useCallback((message: Message, chatId: string | null = currentChatId) => {
    setMessagesForChat(chatId, prev => [...prev, message]);
    scheduleSave(chatId, 800);
  }, [currentChatId, scheduleSave, setMessagesForChat]);

  const updateAssistantStreaming = useCallback((delta: string, chatId: string | null = currentChatId) => {
    const norm = String(delta)
      .replace(/\r\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/^\n+/, '')
      .replace(/\n+$/, '');

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
    setActiveStreamingChatId(prev => {
      if (streaming) {
        return chatId ?? currentChatId;
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
        model: baseConfig.model,
        agent: baseConfig.agent,
        tools: [...(baseConfig.tools || [])],
        mcp_urls: [...(baseConfig.mcp_urls || [])]
      };

      const firstUserMessage = chatMessages.find(msg => msg.role === 'user');
      const chatTitle = firstUserMessage ? generateChatTitle(firstUserMessage.content) : 'New Chat';

      console.log('[createNewChat] Creating chat with:', {
        title: chatTitle,
        messageCount: chatMessages.length,
        firstMessage: firstUserMessage?.content
      });

      try {
        const res = await fetch('/api/chats', {
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

        console.log('[createNewChat] Chat created:', {
          id: newChat.id,
          title: newChat.title,
          serverMessageCount: newChat.messages?.length,
          localMessageCount: chatMessages.length
        });

        setCurrentChatId(newChat.id);
        setCurrentChatTitle(newChat.title);
        setMessagesByChat(prev => {
          console.log('[createNewChat] Moving messages:', {
            from: UNSAVED_CHAT_KEY,
            to: newKey,
            messageCount: chatMessages.length,
            prevKeys: Object.keys(prev)
          });
          const next = { ...prev }; 
          delete next[UNSAVED_CHAT_KEY];
          next[newKey] = chatMessages;
          console.log('[createNewChat] After move, keys:', Object.keys(next));
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
        // Don't await - let it refresh in background
        refreshChatList();
      }
    })();

    chatCreationPromiseRef.current = promise;
    const result = await promise;
    chatCreationPromiseRef.current = null;
    return result;
  }, [currentChatId, messagesByChat, configByChat, computeDefaultConfig, generateChatTitle, refreshChatList, clearScheduledSave]);

  const loadChat = useCallback(async (chatId: string) => {
    const key = keyForChat(chatId);
    console.log('[loadChat] Loading chat:', chatId);
    setCurrentChatId(chatId);
    setShouldResetNext(false);

    const summary = chats.find(c => c.id === chatId);
    if (summary) {
      setCurrentChatTitle(summary.title);
    }

    const cachedConfig = configByChat[key];
    if (cachedConfig) {
      setConfigState(cachedConfig);
    }

    try {
      const res = await fetch(`/api/chats/${chatId}`);
      if (res.ok) {
        const chat: Chat = await res.json();
        setCurrentChatTitle(chat.title);
        setConfigByChat(prev => ({ ...prev, [key]: chat.config }));
        setConfigState(chat.config);
        setMessagesByChat(prev => {
          const existing = prev[key] ?? [];
          const serverMessages = chat.messages ?? [];
          console.log('[loadChat] Merging messages:', {
            chatId,
            existingCount: existing.length,
            serverCount: serverMessages.length,
            prevKeys: Object.keys(prev)
          });
          if (existing.length >= serverMessages.length) {
            return prev;
          }
          const next = { ...prev, [key]: serverMessages };
          console.log('[loadChat] After merge, keys:', Object.keys(next));
          return next;
        });
        setShouldResetNext(false);
      } else {
        console.error('Failed to load chat:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error loading chat:', error);
    }
  }, [chats, configByChat]);  const deleteChat = useCallback(async (chatId: string) => {
    try {
      const res = await fetch(`/api/chats/${chatId}`, { method: 'DELETE' });
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
      updateAssistantStreaming,
      backendConfig,
      newAssistantMessage,
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
      beginNewChat,
      createNewChat,
      loadChat,
      saveCurrentChat,
      finalSave,
      forceSaveNow,
      deleteChat,
      refreshChatList
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
