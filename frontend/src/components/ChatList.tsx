import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useChatStore } from '../hooks/useChatStore';
import { ChatSummary } from '../types/api';
import { RobotAvatar } from './chat/RobotAvatar';
import { BrutalDeleteButton } from './BrutalDeleteButton';
import { BrutalDeleteOverlay } from './BrutalDeleteOverlay';
import { useI18n } from '../i18n';
import { markChatRead } from '../lib/api';

export const ChatList: React.FC = () => {
  const {
    chats,
    chatTotal,
    socialChatTotal,
    loadingChats,
    loadingMoreChats,
    refreshingChats,
    currentChatId,
    searchQuery,
    setSearchQuery,
    loadChat,
    beginNewChat,
    deleteChat,
    renameChat,
    switchToView,
    refreshChatList,
    loadMoreChats,
  } = useChatStore();

  const [deletingChatId, setDeletingChatId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [renamingChatId, setRenamingChatId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState<string>('');
  const [showRefreshIndicator, setShowRefreshIndicator] = useState(false);
  const [localSearchQuery, setLocalSearchQuery] = useState<string>('');
  const [viewMode, setViewMode] = useState<'personal' | 'social'>('personal');
  const { t } = useI18n();

  // Keep a ref so markRead always reads the latest chats without going stale.
  const chatsRef = useRef(chats);
  useEffect(() => { chatsRef.current = chats; }, [chats]);

  const markRead = useCallback((chatId: string) => {
    const chat = chatsRef.current.find(c => c.id === chatId);
    if (!chat) return;
    markChatRead(chatId);
    // Optimistically clear the badge without waiting for next list refresh.
    chat.unreadCount = 0;
  }, []);

  const isUnread = (chat: ChatSummary) => {
    if (chat.id === currentChatId) return false;
    return (chat.unreadCount ?? 0) > 0;
  };

  const unreadMessages = (chat: ChatSummary) => {
    if (!isUnread(chat)) return 0;
    return chat.unreadCount ?? 0;
  };

  // Mark current chat read when it becomes active, and re-mark whenever the
  // chat list refreshes (new messages arrive) while the user is viewing it.
  useEffect(() => {
    if (currentChatId) markRead(currentChatId);
  }, [currentChatId, chats, markRead]);

  // Sync local search with global search on mount
  useEffect(() => {
    setLocalSearchQuery(searchQuery);
  }, []);

  // Debounce search — force=true bypasses the 3500ms throttle so every keystroke
  // (after the 300ms debounce) actually fires a new request.
  useEffect(() => {
    const timeout = setTimeout(() => {
      setSearchQuery(localSearchQuery);
      refreshChatList(localSearchQuery, true);
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

  const handleRenameClick = (chat: ChatSummary, e: React.MouseEvent) => {
    e.stopPropagation();
    setRenamingChatId(chat.id);
    setRenameValue(chat.title || '');
  };

  const handleRenameSubmit = async (chatId: string, e: React.FormEvent | React.KeyboardEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const trimmed = renameValue.trim();
    if (trimmed) await renameChat(chatId, trimmed);
    setRenamingChatId(null);
  };

  const handleRenameCancel = (e: React.MouseEvent | React.KeyboardEvent) => {
    e.stopPropagation();
    setRenamingChatId(null);
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

  const socialUnreadCount = chats
    .filter(c => !!c.platform)
    .reduce((sum, c) => sum + unreadMessages(c), 0);

  const platformTone = (platform?: string | null) => {
    switch (platform?.toLowerCase()) {
      case 'telegram':
      case 'cron':
      default:
        return 'bg-neutral-100 text-neutral-700 border-neutral-300 dark:bg-zinc-700 dark:text-neutral-200 dark:border-zinc-500';
    }
  };

  const platformLabel = (platform?: string | null) => {
    if (!platform) return null;
    return platform.toLowerCase().replace(/^\w/, c => c.toUpperCase());
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

      {/* Unified Header: Search + Filter + Action */}
      <div className="p-3 bg-white dark:bg-zinc-800 space-y-3 flex-shrink-0">
        {/* Row 1: Search + New Chat */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={localSearchQuery}
              onChange={(e) => setLocalSearchQuery(e.target.value)}
              placeholder={viewMode === 'social' ? t('chatList.searchSocialPlaceholder').toUpperCase() : t('chatList.searchChatsPlaceholder').toUpperCase()}
              className="w-full px-3 py-2 pl-9 bg-neutral-50 dark:bg-zinc-700 dark:text-white dark:placeholder-neutral-500 border-2 border-brutal-black font-bold text-xs uppercase placeholder-neutral-400 focus:outline-none focus:bg-white dark:focus:bg-zinc-600 focus:shadow-brutal-sm transition-all"
            />
            <svg
              className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-brutal-black dark:text-neutral-400 pointer-events-none"
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
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-neutral-200 dark:hover:bg-zinc-600 rounded transition-colors"
                title={t('chatList.clearSearch')}
              >
                <svg className="w-3 h-3 text-brutal-black dark:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
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
                    ? 'bg-brutal-black text-white dark:bg-brutal-yellow dark:text-brutal-black z-10'
                    : 'bg-white dark:bg-zinc-700 text-neutral-500 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-zinc-600 hover:text-brutal-black dark:hover:text-white'
                  }`}
              >
                <span className="flex items-center justify-center gap-1">
                  {mode === 'personal' ? t('chatList.view.desktop') : t('chatList.view.social')}
                  {mode === 'social' && socialUnreadCount > 0 && (
                    <span className="inline-flex items-center justify-center min-w-[14px] h-[14px] px-0.5 bg-brutal-yellow text-brutal-black dark:bg-brutal-yellow dark:text-brutal-black text-[9px] font-bold leading-none">
                      {socialUnreadCount}
                    </span>
                  )}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Chat List - Scrollable Content */}
      <div className="flex-1 overflow-y-auto scrollbar-thin min-h-0">
        {displayedChats.length === 0 ? (
          <div className="flex flex-col bg-white dark:bg-zinc-800">
            <div className="p-8 text-center">
              <div className="w-16 h-16 mx-auto mb-3">
                <RobotAvatar variant={searchQuery ? "ghost" : "portal"} />
              </div>
              <p className="text-brutal-black dark:text-white text-sm font-bold uppercase">
                {searchQuery ? t('chatList.empty.noResultsTitle') : (viewMode === 'social' ? t('chatList.empty.noSocialTitle') : t('chatList.empty.noChatsTitle'))}
              </p>
              <p className="text-neutral-500 dark:text-neutral-400 text-xs mt-1">
                {searchQuery ? t('chatList.empty.noResultsDesc') : (viewMode === 'social' ? t('chatList.empty.noSocialDesc') : t('chatList.empty.noChatsDesc'))}
              </p>
            </div>
            {/* Load more even when current view is empty (e.g. social tab but chats beyond first page) */}
            {(() => {
              const tabTotal = viewMode === 'social' ? socialChatTotal : chatTotal - socialChatTotal;
              const remaining = Math.max(0, tabTotal - displayedChats.length);
              if (remaining <= 0) return null;
              return (
                <button
                  onClick={() => loadMoreChats(viewMode)}
                  disabled={loadingMoreChats}
                  className="w-full py-2.5 text-[10px] font-bold uppercase border-t-2 border-brutal-black bg-white dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700 text-neutral-500 dark:text-neutral-400 hover:text-brutal-black dark:hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loadingMoreChats
                    ? t('chatList.loadingMore')
                    : t('chatList.loadMore', { count: remaining })}
                </button>
              );
            })()}
          </div>
        ) : (
          <div className="flex flex-col bg-white dark:bg-zinc-800 pt-[3px]">
            {displayedChats.map((chat: ChatSummary, _idx: number) => (
              <div
                key={chat.id}
                onClick={() => {
                  if (confirmDeleteId) return;
                  markRead(chat.id);
                  loadChat(chat.id);
                  // Switch back to chat view when loading a chat
                  if (switchToView) {
                    switchToView('chat');
                  }
                }}
                className={`group relative overflow-hidden px-3.5 py-3 transition-all border-b last:border-b-0 
                  ${confirmDeleteId ? (confirmDeleteId === chat.id ? 'cursor-default' : 'opacity-50 pointer-events-none') : renamingChatId ? (renamingChatId === chat.id ? 'cursor-default' : 'opacity-50 pointer-events-none') : 'cursor-pointer'}
                  ${currentChatId === chat.id
                    ? 'bg-brutal-yellow/95 dark:bg-zinc-700 border-brutal-black dark:border-brutal-yellow z-10'
                    : isUnread(chat)
                      ? 'bg-white border-neutral-200 dark:bg-zinc-800 dark:border-zinc-700 shadow-[inset_4px_0_0_#000] dark:shadow-[inset_4px_0_0_var(--brutal-yellow)] hover:bg-neutral-50 dark:hover:bg-zinc-700/80'
                      : 'border-neutral-200 dark:border-zinc-700 hover:bg-neutral-50 dark:hover:bg-zinc-700/80 hover:border-neutral-300 dark:hover:border-zinc-600'
                  }`}
              >
                {/* Active Indicator Overlay */}
                {currentChatId === chat.id && (
                  <div
                    className="absolute pointer-events-none inset-0 border-2 border-brutal-black dark:border-brutal-yellow transition-all"
                  />
                )}

                {/* Inline delete confirmation overlay */}
                {confirmDeleteId === chat.id && (
                  <BrutalDeleteOverlay
                    onConfirm={(e: any) => handleDeleteChat(chat.id, e)}
                    onCancel={handleCancelDelete}
                    isDeleting={deletingChatId === chat.id}
                    title={t('chatList.delete.confirmTitle')}
                    confirmText={t('chatList.delete.confirm')}
                    layout="horizontal"
                  />
                )}

                {/* Inline rename input overlay */}
                {renamingChatId === chat.id && (
                  <form
                    className="absolute inset-0 z-20 flex items-center gap-1 px-2 bg-white dark:bg-zinc-800 border-2 border-brutal-black dark:border-brutal-yellow"
                    onSubmit={(e) => handleRenameSubmit(chat.id, e)}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <input
                      autoFocus
                      type="text"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Escape') handleRenameCancel(e); }}
                      className="flex-1 min-w-0 px-2 py-1 text-xs font-bold bg-neutral-50 dark:bg-zinc-700 dark:text-white border-2 border-brutal-black focus:outline-none"
                      placeholder={t('chatList.rename.placeholder')}
                    />
                    <button type="submit" className="px-2 py-1 text-[10px] font-extrabold uppercase border-2 border-brutal-black bg-brutal-yellow hover:bg-yellow-300 text-brutal-black transition-colors shrink-0">
                      {t('chatList.rename.confirm')}
                    </button>
                    <button type="button" onClick={handleRenameCancel} className="px-2 py-1 text-[10px] font-extrabold uppercase border-2 border-brutal-black bg-white dark:bg-zinc-700 dark:text-white hover:bg-neutral-100 transition-colors shrink-0">
                      {t('chatList.rename.cancel')}
                    </button>
                  </form>
                )}

                <div className="min-w-0 space-y-1 pr-8">
                  <div className="flex items-start gap-2 overflow-hidden">
                    {/* Title */}
                    <h3 className={`font-extrabold text-sm leading-snug truncate flex-1 min-w-0 transition-colors ${currentChatId === chat.id ? 'text-brutal-black dark:text-white' : isUnread(chat) ? 'text-neutral-950 dark:text-white' : 'text-neutral-800 dark:text-neutral-100 group-hover:text-brutal-black dark:group-hover:text-white'}`}>
                      {chat.title || t('chatList.untitled')}
                    </h3>

                    {/* Unread count badge */}
                    {(() => {
                      const count = currentChatId === chat.id ? 0 : unreadMessages(chat);
                      if (count <= 0) return null;
                      return (
                        <span className="text-[10px] font-extrabold min-w-[20px] h-5 px-1.5 flex items-center justify-center rounded-sm bg-brutal-yellow text-brutal-black border-2 border-brutal-black leading-none shrink-0 shadow-[1px_1px_0_0_rgba(0,0,0,1)]">
                          {count > 99 ? '99+' : count}
                        </span>
                      );
                    })()}
                  </div>

                  <div className="flex items-center gap-2 overflow-hidden">
                    {/* Platform Badge */}
                    {chat.platform && (
                      <span className={`inline-flex items-center h-5 px-2 rounded-sm text-[10px] font-extrabold uppercase tracking-wide border shrink-0 ${currentChatId === chat.id ? 'bg-white/80 text-brutal-black border-brutal-black dark:bg-zinc-900 dark:text-brutal-yellow dark:border-brutal-yellow' : platformTone(chat.platform)}`}>
                        {platformLabel(chat.platform)}
                      </span>
                    )}

                    {/* Heartbeat icon */}
                    {chat.heartbeatEnabled && (
                      <span
                        className={`shrink-0 flex items-center justify-center w-5 h-5 rounded-sm border ${currentChatId === chat.id ? 'bg-white/80 text-brutal-black border-brutal-black dark:bg-zinc-900 dark:text-brutal-yellow dark:border-brutal-yellow' : 'bg-neutral-100 dark:bg-zinc-800 text-neutral-500 dark:text-neutral-300 border-neutral-300 dark:border-zinc-600 group-hover:border-neutral-500 dark:group-hover:border-zinc-500 transition-all'}`}
                        title={t('chatWindow.heartbeatEnabled')}
                      >
                        <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="square" strokeLinejoin="miter">
                          <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                        </svg>
                      </span>
                    )}

                    {/* Date */}
                    <span className={`text-[10px] font-bold uppercase shrink-0 ${currentChatId === chat.id ? 'text-brutal-black/70 dark:text-brutal-yellow' : 'text-neutral-400 dark:text-neutral-500'}`}>
                      {formatDate(chat.updatedAt)}
                    </span>
                  </div>

                  {/* Action Buttons (Absolute Overlay) */}
                  <div className="absolute right-3 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                    {/* Rename button */}
                    <button
                      type="button"
                      onClick={(e) => handleRenameClick(chat, e)}
                      title={t('chatList.rename.buttonTitle')}
                      className={`p-1.5 border-2 border-brutal-black transition-all duration-200 hover:-translate-y-[1px] hover:shadow-brutal-sm active:translate-y-[1px] active:scale-95 active:shadow-none flex items-center justify-center text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white scale-90 ${currentChatId === chat.id ? 'bg-white dark:bg-zinc-600 hover:bg-brutal-yellow dark:hover:bg-brutal-yellow' : 'bg-neutral-100 dark:bg-zinc-700 hover:bg-brutal-yellow dark:hover:bg-brutal-yellow'}`}
                    >
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                      </svg>
                    </button>
                    {deletingChatId === chat.id ? (
                      <div className="w-7 h-7 flex items-center justify-center animate-brutal-blink text-brutal-black font-bold text-xs bg-brutal-red border-2 border-brutal-black shadow-[2px_2px_0_0_rgba(0,0,0,1)]" title={t('chatList.delete.deleting')}>
                        X
                      </div>
                    ) : (
                      <BrutalDeleteButton
                        onClick={(e) => handleDeleteClick(chat.id, e)}
                        isActive={currentChatId === chat.id}
                        className="scale-90"
                        title={t('chatList.delete.buttonTitle')}
                        disabled={deletingChatId === chat.id}
                      />
                    )}
                  </div>
                </div>
              </div>
            ))}
            {/* Load more button — per-tab count */}
            {(() => {
              const tabTotal = viewMode === 'social' ? socialChatTotal : chatTotal - socialChatTotal;
              const remaining = Math.max(0, tabTotal - displayedChats.length);
              if (remaining <= 0) return null;
              return (
                <button
                  onClick={() => loadMoreChats(viewMode)}
                  disabled={loadingMoreChats}
                  className="w-full py-2.5 text-[10px] font-bold uppercase border-t-2 border-brutal-black bg-white dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700 text-neutral-500 dark:text-neutral-400 hover:text-brutal-black dark:hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loadingMoreChats
                    ? t('chatList.loadingMore')
                    : t('chatList.loadMore', { count: remaining })}
                </button>
              );
            })()}
          </div>
        )}
      </div>
    </div>
  );
};
