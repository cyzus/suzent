import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { Message, ChatConfig, ConfigOptions, Chat, ChatSummary } from '../types/api';

interface ChatContextValue {
  messages: Message[];
  config: ChatConfig;
  setConfig: (c: ChatConfig | ((prev: ChatConfig) => ChatConfig)) => void;
  addMessage: (m: Message) => void;
  updateAssistantStreaming: (delta: string) => void;
  backendConfig: ConfigOptions | null;
  newAssistantMessage: () => void;
  resetChat: () => void;
  shouldResetNext: boolean;
  consumeResetFlag: () => void;
  setIsStreaming: (streaming: boolean) => void;
  
  // New chat management functionality
  currentChatId: string | null;
  chats: ChatSummary[];
  loadingChats: boolean;
  createNewChat: () => Promise<string | null>;
  loadChat: (chatId: string) => Promise<void>;
  saveCurrentChat: (skipRefresh?: boolean) => Promise<void>;
  finalSave: () => Promise<void>;
  forceSaveNow: () => Promise<void>;
  deleteChat: (chatId: string) => Promise<void>;
  refreshChatList: () => Promise<void>;
}

const ChatContext = createContext<ChatContextValue | null>(null);

const defaultConfig: ChatConfig = {
  model: '',
  agent: '',
  tools: [],
  mcp_urls: [] // new optional field
};

export const ChatProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [config, setConfig] = useState<ChatConfig>(defaultConfig);
  const [backendConfig, setBackendConfig] = useState<ConfigOptions | null>(null);
  const [shouldResetNext, setShouldResetNext] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  
  // New chat management state
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [currentChatTitle, setCurrentChatTitle] = useState<string>("New Chat");
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [loadingChats, setLoadingChats] = useState(false);
  
  // Helper function to generate chat title from first message
  const generateChatTitle = (firstMessage: string): string => {
    if (!firstMessage.trim()) return "New Chat";
    const title = firstMessage.trim().split('\n')[0];
    return title.length > 50 ? title.substring(0, 47) + "..." : title;
  };

  // Fetch backend config once
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/config');
        if (res.ok) {
          const data: ConfigOptions = await res.json();
          setBackendConfig(data);
          
          const newConfig = {
            model: data.models[0] || '',
            agent: data.agents[0] || '',
            tools: data.defaultTools || []
          };
          setConfig(newConfig);
        } else {
          console.error('Failed to fetch config:', res.status, res.statusText);
        }
      } catch (error) {
        console.error('Error fetching config:', error);
      }
    })();
  }, []);

  // Load chat list on mount
  useEffect(() => {
    refreshChatList();
  }, []);

  // Chat management functions
  const refreshChatList = async () => {
    setLoadingChats(true);
    try {
      const res = await fetch('/api/chats');
      if (res.ok) {
        const data = await res.json();
        setChats(data.chats || []);
      } else {
        console.error('Failed to fetch chats:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error fetching chats:', error);
    } finally {
      setLoadingChats(false);
    }
  };

  const createNewChat = async (): Promise<string | null> => {
    try {
      // Always create a new chat with empty messages and default title
      const res = await fetch('/api/chats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: "New Chat",
          config,
          messages: []
        })
      });
      
      if (res.ok) {
        const newChat: Chat = await res.json();
        setCurrentChatId(newChat.id);
        setCurrentChatTitle(newChat.title);
        setMessages([]);
        setShouldResetNext(true); // Reset for new chats
        await refreshChatList();
        return newChat.id;
      } else {
        console.error('Failed to create chat:', res.status, res.statusText);
        return null;
      }
    } catch (error) {
      console.error('Error creating chat:', error);
      return null;
    }
    return null;
  };

  const loadChat = async (chatId: string) => {
    try {
      const res = await fetch(`/api/chats/${chatId}`);
      if (res.ok) {
        const chat: Chat = await res.json();
        setCurrentChatId(chat.id);
        setCurrentChatTitle(chat.title);
        setMessages(chat.messages);
        setConfig(chat.config);
        // Don't reset when loading existing chat - we want to preserve agent memory
        setShouldResetNext(false);
      } else {
        console.error('Failed to load chat:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error loading chat:', error);
    }
  };

  const saveCurrentChat = useCallback(async (skipRefresh = false) => {
    if (!currentChatId) {
      // If no current chat, create a new one
      if (messages.length > 0) {
        const chatTitle = messages[0].role === 'user' 
          ? generateChatTitle(messages[0].content)
          : "New Chat";
        
        try {
          const res = await fetch('/api/chats', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              title: chatTitle,
              config,
              messages
            })
          });
          
          if (res.ok) {
            const newChat: Chat = await res.json();
            setCurrentChatId(newChat.id);
            if (!skipRefresh) await refreshChatList();
          } else {
            console.error('Failed to create chat:', res.status, res.statusText);
          }
        } catch (error) {
          console.error('Error saving new chat:', error);
        }
      }
      return;
    }
    
    try {
      // Determine if we should update the title
      let updateTitle = undefined;
      if (messages.length > 0 && messages[0].role === 'user' && currentChatTitle === "New Chat") {
        updateTitle = generateChatTitle(messages[0].content);
      }
      
      const updatePayload: any = {
        config,
        messages
      };
      
      // Include title if we should update it
      if (updateTitle) {
        updatePayload.title = updateTitle;
      }
      
      const res = await fetch(`/api/chats/${currentChatId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatePayload)
      });
      
      if (res.ok) {
        // Update local title state if we sent a title update
        if (updateTitle) {
          setCurrentChatTitle(updateTitle);
        }
        if (!skipRefresh) await refreshChatList();
      } else {
        console.error('Failed to save chat:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error saving chat:', error);
    }
  }, [currentChatId, messages, config, currentChatTitle, refreshChatList]);

  const deleteChat = async (chatId: string) => {
    try {
      const res = await fetch(`/api/chats/${chatId}`, {
        method: 'DELETE'
      });
      
      if (res.ok) {
        if (currentChatId === chatId) {
          setCurrentChatId(null);
          setCurrentChatTitle("New Chat");
          setMessages([]);
          setShouldResetNext(true);
        }
        await refreshChatList();
      } else {
        console.error('Failed to delete chat:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error deleting chat:', error);
    }
  };

  // Optimized config setter
  const optimizedSetConfig = useCallback((newConfig: ChatConfig | ((prev: ChatConfig) => ChatConfig)) => {
    if (typeof newConfig === 'function') {
      setConfig(newConfig);
    } else {
      setConfig(newConfig);
    }
  }, []);

  // Simple debounced save
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  const debouncedSave = useCallback((delay: number = 1000) => {
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    saveTimeoutRef.current = setTimeout(() => {
      saveCurrentChat(true); // Skip refresh during streaming
    }, delay);
  }, [saveCurrentChat]);

  // Auto-save when config changes (debounced)
  useEffect(() => {
    // Only save if we have a current chat and the config has meaningful values
    if (currentChatId && config.model && config.agent) {
      debouncedSave(1500); // Slightly longer delay for config changes
    }
  }, [config, currentChatId, debouncedSave]);

  // Force save function that captures current state at call time
  const forceSaveNow = useCallback(async () => {
    // Clear any pending debounced saves
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
      saveTimeoutRef.current = null;
    }
    
    // Capture state immediately using functional updates
    let capturedChatId: string | null = null;
    let capturedMessages: Message[] = [];
    
    await new Promise<void>((resolve) => {
      setCurrentChatId(currentId => {
        capturedChatId = currentId;
        setMessages(currentMessages => {
          capturedMessages = [...currentMessages]; // Create a copy
          resolve();
          return currentMessages; // Return unchanged
        });
        return currentId; // Return unchanged
      });
    });
    
    // Now save with the captured state
    try {
      if (!capturedChatId && capturedMessages.length > 0) {
        // Create new chat
        const chatTitle = capturedMessages[0].role === 'user' 
          ? generateChatTitle(capturedMessages[0].content)
          : "New Chat";
        
        const res = await fetch('/api/chats', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: chatTitle,
            config,
            messages: capturedMessages
          })
        });
        
        if (res.ok) {
          const newChat: Chat = await res.json();
          setCurrentChatId(newChat.id);
          await refreshChatList();
        } else {
          console.error('Failed to create chat:', res.status);
        }
      } else if (capturedChatId) {
        // Update existing chat
        // Determine if we should update the title (only if it's still "New Chat")
        let updateTitle = undefined;
        if (capturedMessages.length > 0 && capturedMessages[0].role === 'user' && currentChatTitle === "New Chat") {
          updateTitle = generateChatTitle(capturedMessages[0].content);
        }
        
        const updatePayload: any = {
          config,
          messages: capturedMessages
        };
        
        // Only include title if we have a user message to generate it from
        if (updateTitle) {
          updatePayload.title = updateTitle;
        }
        
        const res = await fetch(`/api/chats/${capturedChatId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(updatePayload)
        });
        
        if (res.ok) {
          // Update local title state if we sent a title update
          if (updateTitle) {
            setCurrentChatTitle(updateTitle);
          }
          await refreshChatList();
        } else {
          console.error('Failed to update chat:', res.status);
        }
      }
    } catch (error) {
      console.error('Error during forceSaveNow:', error);
    }
  }, [config, currentChatTitle, generateChatTitle, refreshChatList]);

  const finalSave = useCallback(async () => {
    return forceSaveNow();
  }, [forceSaveNow]);

  const addMessage = (m: Message) => {
    setMessages(prev => [...prev, m]);
    // Auto-save after adding a message (debounced, no refresh)
    debouncedSave(800);
  };

  const updateAssistantStreaming = (delta: string) => {
    // Normalize incoming delta to avoid runs of blank lines or leading/trailing newlines
    const norm = String(delta).replace(/\r\n/g, '\n').replace(/\n{3,}/g, '\n\n').replace(/^\n+/, '').replace(/\n+$/, '');
    setMessages(prev => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== 'assistant') {
        return [...prev, { role: 'assistant', content: norm }];
      }
      const updated = [...prev];
      updated[updated.length - 1] = { ...last, content: last.content + norm };
      return updated;
    });
    // Auto-save during streaming (longer delay, no refresh)
    debouncedSave(2000);
  };

  const newAssistantMessage = () => {
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);
  };

  const resetChat = () => { 
    setMessages([]); 
    setShouldResetNext(true);
    setCurrentChatId(null);
    setCurrentChatTitle("New Chat");
  };
  
  const consumeResetFlag = () => setShouldResetNext(false);

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
      setIsStreaming,
      currentChatId,
      chats,
      loadingChats,
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
