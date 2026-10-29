import React, { useState } from 'react';
import { ContextMenu } from './ContextMenu';
import { itemBase, itemDefault, itemDanger } from './contextMenuStyles';
import type { Project } from '../types/api';
import { useI18n } from '../i18n';

interface ChatRowMenuProps {
  /** Screen-space anchor: usually the right-click point or the dots-button rect. */
  anchor: { x: number; y: number } | { rect: DOMRect };
  /** Optional screen-space bounds the menu should stay inside. */
  boundary?: DOMRect | null;
  projects: Project[];
  currentProjectId?: string | null;
  pinned: boolean;
  /** Archived chats offer Unarchive instead of Archive, and cannot be pinned. */
  archived?: boolean;
  /** When more than one chat is selected, the menu acts on all of them. */
  bulkCount?: number;
  initialView?: View;
  onTogglePin: () => void;
  onToggleArchive: () => void;
  onRename: () => void;
  onDelete: () => void;
  onMoveToProject: (projectId: string) => void;
  onClose: () => void;
}

export type View = 'root' | 'move';

/**
 * Floating context menu portalled into document.body. Brutalist styling.
 *
 * "Move to project" replaces the menu contents with a project list rather
 * than opening a submenu — avoids stacked nested popovers.
 */
export const ChatRowMenu: React.FC<ChatRowMenuProps> = ({
  anchor,
  boundary,
  projects,
  currentProjectId,
  pinned,
  archived = false,
  bulkCount = 1,
  initialView = 'root',
  onTogglePin,
  onToggleArchive,
  onRename,
  onDelete,
  onMoveToProject,
  onClose,
}) => {
  const { t } = useI18n();
  const [view, setView] = useState<View>(initialView);

  const isBulk = bulkCount > 1;

  const singleChatItems = (
    <>
      {!archived && (
        <button
          type="button"
          role="menuitem"
          className={`${itemBase} ${itemDefault}`}
          onClick={() => {
            onTogglePin();
            onClose();
          }}
        >
          {t(pinned ? 'chatList.unpinChat' : 'chatList.pinChat')}
        </button>
      )}
      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDefault}`}
        onClick={() => {
          onRename();
          onClose();
        }}
      >
        <svg
          className="w-3.5 h-3.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth={3}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
          />
        </svg>
        {t('chatList.menu.rename')}
      </button>
    </>
  );

  const rootView = (
    <>
      {!isBulk && singleChatItems}

      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDefault}`}
        onClick={() => setView('move')}
      >
        <svg
          className="w-3.5 h-3.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth={3}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 7l9-4 9 4M3 7v10l9 4 9-4V7M3 7l9 4 9-4"
          />
        </svg>
        <span className="flex-1">
          {isBulk
            ? t('chatList.selection.moveCount', { count: bulkCount })
            : t('chatList.menu.moveToProject')}
        </span>
        <svg
          className="w-3 h-3"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth={3}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </button>

      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDefault}`}
        onClick={() => {
          onToggleArchive();
          onClose();
        }}
      >
        <svg
          className="w-3.5 h-3.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth={3}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M4 7h16M5 7v12a1 1 0 001 1h12a1 1 0 001-1V7M3 4h18v3H3zM10 11h4"
          />
        </svg>
        {isBulk
          ? t(archived ? 'chatList.selection.unarchiveCount' : 'chatList.selection.archiveCount', {
              count: bulkCount,
            })
          : t(archived ? 'chatList.unarchiveChat' : 'chatList.archiveChat')}
      </button>

      <div role="separator" className="h-0.5 bg-brutal-black my-0.5" />

      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDanger}`}
        onClick={() => {
          onDelete();
          onClose();
        }}
      >
        <svg
          className="w-3.5 h-3.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth={3}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3"
          />
        </svg>
        {isBulk
          ? t('chatList.selection.deleteCount', { count: bulkCount })
          : t('chatList.menu.delete')}
      </button>
    </>
  );

  const moveView = (
    <>
      {/* Back header */}
      <button
        type="button"
        role="menuitem"
        onClick={() => setView('root')}
        className="w-full text-left px-3 py-2 text-[10px] font-extrabold uppercase tracking-widest flex items-center gap-2 border-b-2 border-brutal-black bg-brutal-yellow text-brutal-black hover:bg-yellow-300 transition-colors"
      >
        <svg
          className="w-3 h-3"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth={3}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        {t('chatList.menu.moveToProject')}
      </button>
      <div className="max-h-60 overflow-y-auto">
        {projects.map((p) => {
          const isCurrent = p.id === currentProjectId;
          return (
            <button
              key={p.id}
              type="button"
              role="menuitem"
              onClick={(e) => {
                e.stopPropagation();
                if (!isCurrent) onMoveToProject(p.id);
                onClose();
              }}
              disabled={isCurrent}
              className={`w-full text-left px-3 py-2 text-xs font-extrabold uppercase tracking-wider flex items-center justify-between gap-2 transition-colors ${
                isCurrent ? 'text-neutral-400 dark:text-neutral-500 cursor-default' : itemDefault
              }`}
            >
              <span className="truncate">{p.name}</span>
              {isCurrent && (
                <span className="text-[9px] font-extrabold tracking-widest">
                  {t('chatList.currentLabel')}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </>
  );

  const menu = (
    <ContextMenu
      anchor={anchor}
      onClose={onClose}
      boundary={boundary}
      viewKey={view}
      onEscape={() => (view === 'move' ? setView('root') : onClose())}
    >
      {view === 'root' ? rootView : moveView}
    </ContextMenu>
  );

  return menu;
};
