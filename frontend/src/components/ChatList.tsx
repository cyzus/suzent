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
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
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
      <div className="p-4 border-b-3 border-brutal-black flex items-center justify-between gap-3">
        <button
          onClick={beginNewChat}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-brutal-blue border-3 border-brutal-black shadow-brutal hover:shadow-brutal-lg active:shadow-none text-white font-bold uppercase"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          New Chat
        </button>
      </div>

      {/* Chat List */}
      <div className="flex-1 overflow-y-auto">
        {chats.length === 0 ? (
          <div className="p-4 text-center text-brutal-black text-sm font-bold uppercase">
            No chats yet. Start a new conversation!
          </div>
        ) : (
          <div className="p-2 space-y-2">
            {chats.map((chat: ChatSummary, idx: number) => (
              <div
                key={chat.id}
                onClick={() => loadChat(chat.id)}
                className={`group relative p-3 cursor-pointer active:animate-brutal-shake animate-brutal-slide ${
                  currentChatId === chat.id
                    ? 'bg-brutal-yellow border-3 border-brutal-black shadow-brutal'
                    : 'bg-brutal-white hover:bg-neutral-100 border-3 border-brutal-black hover:shadow-brutal-sm'
                }`}
                style={{ animationDelay: `${idx * 30}ms` }}
              >
                {/* Inline delete confirmation overlay */}
                {confirmDeleteId === chat.id && (
                  <div className="absolute inset-0 bg-brutal-red border-3 border-brutal-black flex flex-col items-center justify-center gap-2 z-10 p-2 animate-brutal-pop">
                    <span className="text-sm font-bold text-brutal-white uppercase animate-brutal-glitch">Delete this chat?</span>
                    <div className="flex gap-2">
                      <button
                        onClick={(e) => handleDeleteChat(chat.id, e)}
                        disabled={deletingChatId === chat.id}
                        className="px-3 py-1.5 bg-brutal-black border-2 border-brutal-white text-white text-xs font-bold uppercase disabled:opacity-50"
                      >
                        {deletingChatId === chat.id ? 'Deleting...' : 'Delete'}
                      </button>
                      <button
                        onClick={handleCancelDelete}
                        className="px-3 py-1.5 bg-brutal-white border-2 border-brutal-black text-brutal-black text-xs font-bold uppercase"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-bold text-sm truncate text-brutal-black uppercase">
                      {chat.title}
                    </h3>

                    {chat.lastMessage && (
                      <p className="text-xs mt-1 line-clamp-2 text-brutal-black">
                        {chat.lastMessage}
                      </p>
                    )}

                    <div className="flex items-center justify-between mt-2">
                      <span className="text-xs font-mono font-bold text-brutal-black">
                        {chat.messageCount} MSG{chat.messageCount !== 1 ? 'S' : ''}
                      </span>
                      <span className="text-xs font-mono font-bold text-brutal-black">
                        {formatDate(chat.updatedAt)}
                      </span>
                    </div>
                  </div>

                  {/* Delete Button */}
                  <button
                    onClick={(e) => handleDeleteClick(chat.id, e)}
                    disabled={deletingChatId === chat.id}
                    className="opacity-0 group-hover:opacity-100 ml-2 p-1.5 bg-brutal-red border-2 border-brutal-black hover:shadow-brutal-sm transition-opacity duration-75"
                    title="Delete chat"
                  >
                    {deletingChatId === chat.id ? (
                      <div className="w-4 h-4 animate-brutal-blink text-brutal-white font-bold text-xs">X</div>
                    ) : (
                      <svg className="w-4 h-4 text-brutal-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
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