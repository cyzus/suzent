import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { Message, ChatConfig, ConfigOptions } from '../types/api';

interface ChatContextValue {
  messages: Message[];
  config: ChatConfig;
  setConfig: (c: ChatConfig | ((prev: ChatConfig) => ChatConfig)) => void;
  addMessage: (m: Message) => void;
  updateAssistantStreaming: (delta: string) => void;
  backendConfig: ConfigOptions | null;
  newAssistantMessage: () => void;
  resetChat: () => void;
  shouldResetNext: boolean; // new
  consumeResetFlag: () => void; // new
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
  const [shouldResetNext, setShouldResetNext] = useState(false); // new

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

  const addMessage = (m: Message) => setMessages(prev => [...prev, m]);

  const updateAssistantStreaming = (delta: string) => {
    setMessages(prev => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== 'assistant') {
        return [...prev, { role: 'assistant', content: delta }];
      }
      const updated = [...prev];
      updated[updated.length - 1] = { ...last, content: last.content + delta };
      return updated;
    });
  };

  const newAssistantMessage = () => {
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);
  };

  const resetChat = () => { setMessages([]); setShouldResetNext(true); };
  const consumeResetFlag = () => setShouldResetNext(false);

  return (
    <ChatContext.Provider value={{ messages, config, setConfig: optimizedSetConfig, addMessage, updateAssistantStreaming, backendConfig, newAssistantMessage, resetChat, shouldResetNext, consumeResetFlag }}>
      {children}
    </ChatContext.Provider>
  );
};

export const useChatStore = () => {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChatStore must be used within ChatProvider');
  return ctx;
};
