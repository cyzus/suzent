import React, { useEffect, useState } from 'react';
import { useChatStore } from '../hooks/useChatStore';
import { ChatSummary } from '../types/api';

export const ChatList: React.FC = () => {
  const { 
    chats, 
    loadingChats, 
    refreshingChats,
    currentChatId, 
    loadChat, 
    beginNewChat,
    deleteChat 
  } = useChatStore();
  
  const [deletingChatId, setDeletingChatId] = useState<string | null>(null);
  const [showRefreshIndicator, setShowRefreshIndicator] = useState(false);

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

  const handleDeleteChat = async (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent chat selection when deleting
    
    if (window.confirm('Are you sure you want to delete this chat?')) {
      setDeletingChatId(chatId);
      try {
        await deleteChat(chatId);
      } catch (error) {
        console.error('Error deleting chat:', error);
      } finally {
        setDeletingChatId(null);
      }
    }
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

  if (loadingChats) {
    return (
      <div className="p-4">
        <div className="animate-pulse space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-16 bg-neutral-200 rounded-lg"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* New Chat Button */}
      <div className="p-4 border-b border-neutral-200 flex items-center justify-between gap-3">
        <button
          onClick={beginNewChat}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-brand-600 hover:bg-brand-500 text-white rounded-lg font-medium transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Chat
        </button>
        {showRefreshIndicator && (
          <div className="flex items-center text-[11px] text-neutral-400 gap-2 whitespace-nowrap transition-opacity duration-150">
            <span className="w-3 h-3 rounded-full border-2 border-neutral-300 border-t-brand-500 animate-spin" aria-hidden="true"></span>
            Updating…
            <span className="sr-only">Refreshing chat list</span>
          </div>
        )}
      </div>

      {/* Chat List */}
      <div className="flex-1 overflow-y-auto">
        {chats.length === 0 ? (
          <div className="p-4 text-center text-neutral-500 text-sm">
            No chats yet. Start a new conversation!
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {chats.map((chat: ChatSummary) => (
              <div
                key={chat.id}
                onClick={() => loadChat(chat.id)}
                className={`group relative p-3 rounded-lg cursor-pointer transition-all ${
                  currentChatId === chat.id
                    ? 'bg-brand-50 border border-brand-200'
                    : 'bg-neutral-50 hover:bg-neutral-100 border border-transparent'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <h3 className={`font-medium text-sm truncate ${
                      currentChatId === chat.id ? 'text-brand-900' : 'text-neutral-900'
                    }`}>
                      {chat.title}
                    </h3>
                    
                    {chat.lastMessage && (
                      <p className="text-xs text-neutral-500 mt-1 line-clamp-2">
                        {chat.lastMessage}
                      </p>
                    )}
                    
                    <div className="flex items-center justify-between mt-2">
                      <span className="text-xs text-neutral-400">
                        {chat.messageCount} message{chat.messageCount !== 1 ? 's' : ''}
                      </span>
                      <span className="text-xs text-neutral-400">
                        {formatDate(chat.updatedAt)}
                      </span>
                    </div>
                  </div>

                  {/* Delete Button */}
                  <button
                    onClick={(e) => handleDeleteChat(chat.id, e)}
                    disabled={deletingChatId === chat.id}
                    className="opacity-0 group-hover:opacity-100 ml-2 p-1 rounded text-neutral-400 hover:text-red-500 hover:bg-red-50 transition-all"
                    title="Delete chat"
                  >
                    {deletingChatId === chat.id ? (
                      <div className="w-4 h-4 animate-spin rounded-full border-2 border-neutral-300 border-t-red-500"></div>
                    ) : (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};