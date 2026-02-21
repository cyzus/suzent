import React, { useEffect, useState } from 'react';
import { useChatStore } from '../hooks/useChatStore';
import { ChatSummary } from '../types/api';
import { RobotAvatar } from './chat/RobotAvatar';
import { BrutalDeleteButton } from './BrutalDeleteButton';
import { BrutalDeleteOverlay } from './BrutalDeleteOverlay';
import { useI18n } from '../i18n';

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
  const [viewMode, setViewMode] = useState<'personal' | 'social'>('personal');
  const { t } = useI18n();

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

  // Filter chats based on view mode
  const displayedChats = chats.filter(chat => {
    if (viewMode === 'social') {
      return !!chat.platform;
    }
    return !chat.platform;
  });

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

      {/* Unified Header: Search + Filter + Action */}
      <div className="p-3 border-b-3 border-brutal-black bg-white space-y-3">
        {/* Row 1: Search + New Chat */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={localSearchQuery}
              onChange={(e) => setLocalSearchQuery(e.target.value)}
              placeholder={viewMode === 'social' ? t('chatList.searchSocialPlaceholder').toUpperCase() : t('chatList.searchChatsPlaceholder').toUpperCase()}
              className="w-full px-3 py-2 pl-9 bg-neutral-50 border-2 border-brutal-black font-bold text-xs uppercase placeholder-neutral-400 focus:outline-none focus:bg-white focus:shadow-brutal-sm transition-all"
            />
            <svg
              className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-brutal-black pointer-events-none"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            {localSearchQuery && (
              <button
                onClick={() => setLocalSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-neutral-200 rounded transition-colors"
                title={t('chatList.clearSearch')}
              >
                <svg className="w-3 h-3 text-brutal-black" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {/* New Chat Button (Square, Original Colors) */}
          {viewMode === 'personal' && (
            <button
              onClick={() => {
                beginNewChat();
                if (switchToView) switchToView('chat');
              }}
              className="flex items-center justify-center w-[38px] bg-brutal-black text-white border-2 border-brutal-black shadow-[2px_2px_0_0_#000] hover:bg-brutal-blue hover:text-white hover:translate-y-[1px] hover:translate-x-[1px] hover:shadow-[1px_1px_0_0_#000] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none transition-all flex-shrink-0"
              title={t('chatList.newChat')}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            </button>
          )}
        </div>

        {/* Row 2: Full Width Filter Toggles (Only if Social chats exist OR if already in Social view) */}
        {(chats.some(c => !!c.platform) || viewMode === 'social') && (
          <div className="flex shadow-[2px_2px_0_0_#000]">
            {(['personal', 'social'] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={`flex-1 py-1.5 text-[10px] font-bold uppercase border-2 border-brutal-black transition-all relative ${mode === 'personal' ? 'mr-[-2px]' : ''
                  } ${viewMode === mode
                    ? 'bg-brutal-black text-white z-10'
                    : 'bg-white text-neutral-500 hover:bg-neutral-50 hover:text-brutal-black'
                  }`}
              >
                {mode === 'personal' ? t('chatList.view.desktop') : t('chatList.view.social')}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Chat List */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {displayedChats.length === 0 ? (
          <div className="p-8 text-center">
            <div className="w-16 h-16 mx-auto mb-3">
              <RobotAvatar variant={searchQuery ? "ghost" : "portal"} />
            </div>
            <p className="text-brutal-black text-sm font-bold uppercase">
              {searchQuery ? t('chatList.empty.noResultsTitle') : (viewMode === 'social' ? t('chatList.empty.noSocialTitle') : t('chatList.empty.noChatsTitle'))}
            </p>
            <p className="text-neutral-500 text-xs mt-1">
              {searchQuery ? t('chatList.empty.noResultsDesc') : (viewMode === 'social' ? t('chatList.empty.noSocialDesc') : t('chatList.empty.noChatsDesc'))}
            </p>
          </div>
        ) : (
          <div className="p-3 space-y-3">
            {displayedChats.map((chat: ChatSummary, idx: number) => (
              <div
                key={chat.id}
                onClick={() => {
                  loadChat(chat.id);
                  // Switch back to chat view when loading a chat
                  if (switchToView) {
                    switchToView('chat');
                  }
                }}
                className={`group relative p-3 cursor-pointer transition-all duration-200 animate-brutal-drop ${currentChatId === chat.id
                  ? 'bg-brutal-yellow border-3 border-brutal-black shadow-[2px_2px_0_0_#000] translate-y-[2px]'
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
                  <BrutalDeleteOverlay
                    onConfirm={(e: any) => handleDeleteChat(chat.id, e)}
                    onCancel={handleCancelDelete}
                    isDeleting={deletingChatId === chat.id}
                    title={t('chatList.delete.confirmTitle')}
                    confirmText={t('chatList.delete.confirm')}
                  />
                )}

                <div className="flex items-start justify-between pl-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      {/* Platform Badge */}
                      {chat.platform && (
                        <span className="text-[10px] font-bold uppercase px-1 py-0.5 bg-neutral-200 border border-brutal-black">
                          {chat.platform}
                        </span>
                      )}
                      <h3 className={`font-bold text-sm truncate uppercase ${currentChatId === chat.id ? 'text-brutal-black' : 'text-neutral-800'}`}>
                        {chat.title || t('chatList.untitled')}
                      </h3>
                    </div>

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
                  <div className="ml-2">
                    {deletingChatId === chat.id ? (
                      <div className="w-7 h-7 flex items-center justify-center animate-brutal-blink text-brutal-black font-bold text-xs" title={t('chatList.delete.deleting')}>
                        X
                      </div>
                    ) : (
                      <BrutalDeleteButton
                        onClick={(e) => handleDeleteClick(chat.id, e)}
                        isActive={currentChatId === chat.id}
                        className="opacity-0 group-hover:opacity-100"
                        title={t('chatList.delete.buttonTitle')}
                        disabled={deletingChatId === chat.id}
                      />
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};