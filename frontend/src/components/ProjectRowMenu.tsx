import React from 'react';
import { ContextMenu } from './ContextMenu';
import { itemBase, itemDefault, itemDanger } from './contextMenuStyles';
import { useI18n } from '../i18n';

interface ProjectRowMenuProps {
  anchor: { x: number; y: number } | { rect: DOMRect };
  /** Optional screen-space bounds the menu should stay inside. */
  boundary?: DOMRect | null;
  /** Extra data-* attributes stamped on the floating panel (e.g. for outside-click whitelisting). */
  rootDataAttrs?: Record<string, string>;
  /** Omitted for rows that have no settings (e.g. scheduled tasks). */
  onSettings?: () => void;
  /** Omitted for system projects, which can't be renamed or deleted. */
  onRename?: () => void;
  onDelete?: () => void;
  onClose: () => void;
}

/**
 * Brutalist context menu for a project row inside the filter dropdown.
 * Portalled into document.body so it never gets clipped by the dropdown.
 */
export const ProjectRowMenu: React.FC<ProjectRowMenuProps> = ({
  anchor,
  boundary,
  rootDataAttrs,
  onSettings,
  onRename,
  onDelete,
  onClose,
}) => {
  const { t } = useI18n();

  const menu = (
    <ContextMenu
      anchor={anchor}
      onClose={onClose}
      boundary={boundary}
      rootDataAttrs={rootDataAttrs}
    >
      {onSettings && (
        <button
          type="button"
          role="menuitem"
          className={`${itemBase} ${itemDefault}`}
          onClick={() => {
            onSettings();
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
              d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75"
            />
          </svg>
          {t('chatList.menu.settings')}
        </button>
      )}

      {onRename && (
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
      )}

      {onDelete && (
        <>
          <div role="separator" className="h-0.5 bg-brutal-black my-0.5" />

          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onDelete();
              onClose();
            }}
            className={`${itemBase} ${itemDanger}`}
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
            {t('chatList.menu.delete')}
          </button>
        </>
      )}
    </ContextMenu>
  );

  return menu;
};
