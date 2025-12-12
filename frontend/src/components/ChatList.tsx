import React, { useEffect, useState } from 'react';
import { useChatStore } from '../hooks/useChatStore';
import { ChatSummary } from '../types/api';

export const ChatList: React.FC = () => {
  const {
    chats,
    loadingChats,
    refreshingChats,
    currentChatId,
    searchQuery,
    setSearchQuery,
    loadChat,
    beginNewChat,
    deleteChat,
    switchToView,
    refreshChatList
  } = useChatStore();
  
  const [deletingChatId, setDeletingChatId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [showRefreshIndicator, setShowRefreshIndicator] = useState(false);
  const [localSearchQuery, setLocalSearchQuery] = useState<string>('');

  // Sync local search with global search on mount
  useEffect(() => {
    setLocalSearchQuery(searchQuery);
  }, []);

  // Debounce search to avoid too many API calls
  useEffect(() => {
    const timeout = setTimeout(() => {
      setSearchQuery(localSearchQuery);
      refreshChatList(localSearchQuery);
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

  const handleDeleteChat = async (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent chat selection when deleting
    
    setDeletingChatId(chatId);
    try {
      await deleteChat(chatId);
      setConfirmDeleteId(null);
    } catch (error) {
      console.error('Error deleting chat:', error);
    } finally {
      setDeletingChatId(null);
    }
  };

  const handleDeleteClick = (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setConfirmDeleteId(chatId);
  };

  const handleCancelDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    setConfirmDeleteId(null);
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
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-16 bg-neutral-300 border-3 border-brutal-black animate-brutal-blink"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full relative">
      {/* Brutalist refresh indicator */}
      {showRefreshIndicator && (
        <div className="absolute top-0 left-0 right-0 z-10 pointer-events-none">
          <div className="h-1 bg-brutal-blue animate-brutal-blink"></div>
        </div>
      )}

      {/* New Chat Button */}
      <div className="p-4 border-b-3 border-brutal-black flex items-center justify-between gap-3 bg-white">
        <button
          onClick={beginNewChat}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-brutal-black border-3 border-brutal-black shadow-brutal hover:bg-brutal-blue hover:text-white hover:shadow-brutal-lg active:translate-x-[2px] active:translate-y-[2px] active:shadow-none text-white font-bold uppercase transition-all"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          New Chat
        </button>
      </div>

      {/* Search Bar */}
      <div className="p-4 border-b-3 border-brutal-black bg-white">
        <div className="relative">
          <input
            type="text"
            value={localSearchQuery}
            onChange={(e) => setLocalSearchQuery(e.target.value)}
            placeholder="SEARCH CHATS..."
            className="w-full px-3 py-2 pl-10 bg-white border-3 border-brutal-black font-bold text-sm uppercase placeholder-neutral-400 focus:outline-none focus:shadow-brutal transition-shadow"
          />
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-brutal-black pointer-events-none"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            strokeWidth={3}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          {localSearchQuery && (
            <button
              onClick={() => setLocalSearchQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-neutral-100 border-2 border-brutal-black transition-colors"
              title="Clear search"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Chat List */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {chats.length === 0 ? (
          <div className="p-8 text-center">
            <div className="w-12 h-12 bg-neutral-200 border-2 border-brutal-black mx-auto mb-3 flex items-center justify-center text-2xl">
              {searchQuery ? '🔍' : '💬'}
            </div>
            <p className="text-brutal-black text-sm font-bold uppercase">
              {searchQuery ? 'No results found' : 'No chats yet'}
            </p>
            <p className="text-neutral-500 text-xs mt-1">
              {searchQuery ? 'Try a different search term' : 'Start a new conversation to begin'}
            </p>
          </div>
        ) : (
          <div className="p-3 space-y-3">
            {chats.map((chat: ChatSummary, idx: number) => (
              <div
                key={chat.id}
                onClick={() => {
                  loadChat(chat.id);
                  // Switch back to chat view when loading a chat
                  if (switchToView) {
                    switchToView('chat');
                  }
                }}
                className={`group relative p-3 cursor-pointer transition-all duration-200 animate-brutal-drop ${
                  currentChatId === chat.id
                    ? 'bg-brutal-yellow border-3 border-brutal-black shadow-brutal translate-x-[-2px] translate-y-[-2px]'
                    : 'bg-white hover:bg-neutral-50 border-3 border-brutal-black hover:shadow-brutal-sm'
                }`}
                style={{ animationDelay: `${idx * 0.05}s` }}
              >
                {/* Active Indicator */}
                {currentChatId === chat.id && (
                  <div className="absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-8 bg-brutal-black"></div>
                )}

                {/* Inline delete confirmation overlay */}
                {confirmDeleteId === chat.id && (
                  <div className="absolute inset-0 bg-brutal-red border-3 border-brutal-black flex flex-col items-center justify-center gap-2 z-10 p-2 animate-brutal-pop">
                    <span className="text-sm font-bold text-brutal-white uppercase animate-brutal-glitch">Delete this chat?</span>
                    <div className="flex gap-2">
                      <button
                        onClick={(e) => handleDeleteChat(chat.id, e)}
                        disabled={deletingChatId === chat.id}
                        className="px-3 py-1.5 bg-brutal-black border-2 border-brutal-white text-white text-xs font-bold uppercase disabled:opacity-50 hover:bg-neutral-800"
                      >
                        {deletingChatId === chat.id ? 'Deleting...' : 'Delete'}
                      </button>
                      <button
                        onClick={handleCancelDelete}
                        className="px-3 py-1.5 bg-brutal-white border-2 border-brutal-black text-brutal-black text-xs font-bold uppercase hover:bg-neutral-100"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                <div className="flex items-start justify-between pl-2">
                  <div className="flex-1 min-w-0">
                    <h3 className={`font-bold text-sm truncate uppercase ${currentChatId === chat.id ? 'text-brutal-black' : 'text-neutral-800'}`}>
                      {chat.title || 'Untitled Chat'}
                    </h3>

                    {chat.lastMessage && (
                      <p className={`text-xs mt-1 line-clamp-2 font-mono ${currentChatId === chat.id ? 'text-brutal-black/80' : 'text-neutral-600'}`}>
                        {chat.lastMessage}
                      </p>
                    )}

                    <div className={`flex items-center justify-between mt-3 pt-2 border-t-2 ${currentChatId === chat.id ? 'border-brutal-black/20' : 'border-neutral-200/50'}`}>
                      <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 border ${currentChatId === chat.id ? 'bg-white text-brutal-black border-brutal-black' : 'bg-neutral-100 text-neutral-500 border-neutral-300'}`}>
                        {chat.messageCount} MSG
                      </span>
                      <span className={`text-[10px] font-bold uppercase ${currentChatId === chat.id ? 'text-brutal-black/60' : 'text-neutral-400'}`}>
                        {formatDate(chat.updatedAt)}
                      </span>
                    </div>
                  </div>

                  {/* Delete Button */}
                  <button
                    onClick={(e) => handleDeleteClick(chat.id, e)}
                    disabled={deletingChatId === chat.id}
                    className={`opacity-0 group-hover:opacity-100 ml-2 p-1.5 border-2 border-brutal-black transition-all duration-200 hover:shadow-[2px_2px_0_0_#000000] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none ${
                      currentChatId === chat.id ? 'bg-white hover:bg-brutal-red hover:text-white' : 'bg-neutral-100 hover:bg-brutal-red hover:text-white'
                    }`}
                    title="Delete chat"
                  >
                    {deletingChatId === chat.id ? (
                      <div className="w-3 h-3 animate-brutal-blink text-brutal-black font-bold text-xs">X</div>
                    ) : (
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round"
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