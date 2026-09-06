import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ClipboardDocumentIcon, FolderOpenIcon, TrashIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';

interface FileTreeContextMenuProps {
  anchor: { x: number; y: number };
  isDir: boolean;
  canDelete: boolean;
  onOpen: () => void;
  onReveal: () => void;
  onCopyPath: () => void;
  onDelete: () => void;
  onClose: () => void;
}

export const FileTreeContextMenu: React.FC<FileTreeContextMenuProps> = ({
  anchor,
  isDir,
  canDelete,
  onOpen,
  onReveal,
  onCopyPath,
  onDelete,
  onClose,
}) => {
  const { t } = useI18n();
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);

  useLayoutEffect(() => {
    if (!menuRef.current) return;
    const margin = 8;
    const menuWidth = menuRef.current.offsetWidth || 210;
    const menuHeight = menuRef.current.offsetHeight || 180;
    setPosition({
      left: Math.max(margin, Math.min(anchor.x, window.innerWidth - menuWidth - margin)),
      top: Math.max(margin, Math.min(anchor.y, window.innerHeight - menuHeight - margin)),
    });
    menuRef.current.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
  }, [anchor]);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) onClose();
    };
    const handleContextMenu = (event: MouseEvent) => {
      if (menuRef.current?.contains(event.target as Node)) event.preventDefault();
      else onClose();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    const handleScroll = () => onClose();

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('contextmenu', handleContextMenu);
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('scroll', handleScroll, true);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('contextmenu', handleContextMenu);
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('scroll', handleScroll, true);
    };
  }, [onClose]);

  const itemClass =
    'w-full px-3 py-2 text-left font-mono text-xs font-extrabold uppercase tracking-wider flex items-center gap-2.5 transition-colors';
  const defaultItemClass =
    'text-brutal-black dark:text-white hover:bg-brutal-yellow dark:hover:bg-brutal-yellow dark:hover:text-brutal-black';

  const runAction = (action: () => void) => {
    action();
    onClose();
  };

  return createPortal(
    <div
      ref={menuRef}
      role="menu"
      aria-label={t('sandbox.contextMenu.label')}
      className="fixed z-[9999] min-w-[210px] border-2 border-brutal-black bg-white py-0.5 shadow-[3px_3px_0_0_#000] dark:bg-zinc-800"
      style={{
        left: position?.left ?? -9999,
        top: position?.top ?? -9999,
        visibility: position ? 'visible' : 'hidden',
      }}
      onClick={(event) => event.stopPropagation()}
      onContextMenu={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      <button
        type="button"
        role="menuitem"
        className={`${itemClass} ${defaultItemClass}`}
        onClick={() => runAction(onOpen)}
      >
        <FolderOpenIcon className="h-4 w-4 stroke-[2.5]" />
        {t(isDir ? 'sandbox.contextMenu.toggleFolder' : 'sandbox.contextMenu.open')}
      </button>
      <button
        type="button"
        role="menuitem"
        className={`${itemClass} ${defaultItemClass}`}
        onClick={() => runAction(onReveal)}
      >
        <FolderOpenIcon className="h-4 w-4 stroke-[2.5]" />
        {t('sandbox.contextMenu.reveal')}
      </button>
      <button
        type="button"
        role="menuitem"
        className={`${itemClass} ${defaultItemClass}`}
        onClick={() => runAction(onCopyPath)}
      >
        <ClipboardDocumentIcon className="h-4 w-4 stroke-[2.5]" />
        {t('sandbox.contextMenu.copyPath')}
      </button>
      {canDelete && (
        <>
          <div className="my-0.5 h-0.5 bg-brutal-black" />
          <button
            type="button"
            role="menuitem"
            className={`${itemClass} text-brutal-red hover:bg-brutal-red hover:text-white`}
            onClick={() => runAction(onDelete)}
          >
            <TrashIcon className="h-4 w-4 stroke-[2.5]" />
            {t('sandbox.contextMenu.delete')}
          </button>
        </>
      )}
    </div>,
    document.body
  );
};
