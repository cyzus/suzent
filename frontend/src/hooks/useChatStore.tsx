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
  createNewChat: () => Promise<void>;
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
        console.log('Fetching backend config...');
        const res = await fetch('/api/config');
        if (res.ok) {
          const data: ConfigOptions = await res.json();
          console.log('Backend config received:', data);
          setBackendConfig(data);
          
          // Manual initialization for testing
          setConfig({
            model: data.models[0] || '',
            agent: data.agents[0] || '',
            tools: []
          });
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

  const createNewChat = async () => {
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
        setShouldResetNext(true);
        await refreshChatList();
      } else {
        console.error('Failed to create chat:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error creating chat:', error);
    }
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
        setShouldResetNext(true);
      } else {
        console.error('Failed to load chat:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error loading chat:', error);
    }
  };

  const saveCurrentChat = useCallback(async (skipRefresh = false) => {
    console.log('saveCurrentChat called with:', { currentChatId, messageCount: messages.length, skipRefresh });
    
    if (!currentChatId) {
      // If no current chat, create a new one
      if (messages.length > 0) {
        const chatTitle = messages[0].role === 'user' 
          ? generateChatTitle(messages[0].content)
          : "New Chat";
        
        console.log('Creating new chat with title:', chatTitle, 'messages:', messages.length);
        
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
            console.log('New chat created:', newChat.id);
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

    console.log('Updating existing chat:', currentChatId, 'with', messages.length, 'messages');
    
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
        console.log('Chat updated successfully');
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

  // Optimized config setter with immediate UI feedback
  const optimizedSetConfig = useCallback((newConfig: ChatConfig | ((prev: ChatConfig) => ChatConfig)) => {
    console.log('optimizedSetConfig called with:', typeof newConfig === 'function' ? 'function' : newConfig);
    
    if (typeof newConfig === 'function') {
      setConfig(prevConfig => {
        const result = newConfig(prevConfig);
        console.log('Function config update - prev:', prevConfig, 'new:', result);
        return result;
      });
    } else {
      console.log('Direct config update to:', newConfig);
      setConfig(newConfig);
    }
  }, []); // Remove config dependency

  // Simple debounced save
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  const debouncedSave = useCallback((delay: number = 1000) => {
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    saveTimeoutRef.current = setTimeout(() => {
      console.log('Debounced save triggered (no refresh)');
      saveCurrentChat(true); // Skip refresh during streaming
    }, delay);
  }, [saveCurrentChat]);

  // Force save function that captures current state at call time
  const forceSaveNow = useCallback(async () => {
    console.log('forceSaveNow called - will capture current state');
    
    // Clear any pending debounced saves
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
      saveTimeoutRef.current = null;
      console.log('forceSaveNow: Cleared pending debounced save');
    }
    
    // Capture state immediately using functional updates
    let capturedChatId: string | null = null;
    let capturedMessages: Message[] = [];
    
    await new Promise<void>((resolve) => {
      setCurrentChatId(currentId => {
        capturedChatId = currentId;
        setMessages(currentMessages => {
          capturedMessages = [...currentMessages]; // Create a copy
          console.log('forceSaveNow: captured state -', {
            chatId: capturedChatId,
            messageCount: capturedMessages.length,
            lastMessageLength: capturedMessages[capturedMessages.length - 1]?.content?.length || 0
          });
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
        
        console.log('forceSaveNow: Creating new chat with title:', chatTitle);
        
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
          console.log('forceSaveNow: New chat created:', newChat.id);
          setCurrentChatId(newChat.id);
          await refreshChatList();
        } else {
          console.error('forceSaveNow: Failed to create chat:', res.status);
        }
      } else if (capturedChatId) {
        // Update existing chat
        console.log('forceSaveNow: Updating existing chat:', capturedChatId);
        
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
          console.log('forceSaveNow: Chat updated successfully');
          // Update local title state if we sent a title update
          if (updateTitle) {
            setCurrentChatTitle(updateTitle);
          }
          await refreshChatList();
        } else {
          console.error('forceSaveNow: Failed to update chat:', res.status);
        }
      }
      console.log('forceSaveNow: Save operation completed');
    } catch (error) {
      console.error('forceSaveNow: Error during save:', error);
    }
  }, [config, currentChatTitle, generateChatTitle, refreshChatList]);

  const finalSave = useCallback(async () => {
    console.log('finalSave: delegating to forceSaveNow');
    return forceSaveNow();
  }, [forceSaveNow]);

  const addMessage = (m: Message) => {
    console.log('Adding message:', m.role, m.content.substring(0, 50) + '...');
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
        console.log('updateAssistantStreaming: adding new assistant message');
        return [...prev, { role: 'assistant', content: norm }];
      }
      const updated = [...prev];
      updated[updated.length - 1] = { ...last, content: last.content + norm };
      const newLength = updated[updated.length - 1].content.length;
      console.log('updateAssistantStreaming: updated message length:', newLength, 'total messages:', updated.length);
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
