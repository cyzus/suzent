import React from 'react';
import { ContextMenu } from '../ContextMenu';
import { itemBase, itemDefault, itemDanger } from '../contextMenuStyles';
import {
  ArrowDownTrayIcon,
  ArrowUpTrayIcon,
  ClipboardDocumentIcon,
  FolderOpenIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';

interface FileTreeContextMenuProps {
  anchor: { x: number; y: number };
  isDir: boolean;
  canDelete: boolean;
  onOpen: () => void;
  onReveal: () => void;
  onCopyPath: () => void;
  /** Browser console only. The desktop shell reveals the file locally instead. */
  onDownload?: () => void;
  /** Upload into this folder. Omitted for files and the read-only mounts root. */
  onUpload?: () => void;
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
  onDownload,
  onUpload,
  onDelete,
  onClose,
}) => {
  const { t } = useI18n();

  const runAction = (action: () => void) => {
    action();
    onClose();
  };

  return (
    <ContextMenu anchor={anchor} onClose={onClose} label={t('sandbox.contextMenu.label')}>
      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDefault}`}
        onClick={() => runAction(onOpen)}
      >
        <FolderOpenIcon className="h-4 w-4 stroke-[2.5]" />
        {t(isDir ? 'sandbox.contextMenu.toggleFolder' : 'sandbox.contextMenu.open')}
      </button>
      {onUpload && (
        <button
          type="button"
          role="menuitem"
          className={`${itemBase} ${itemDefault}`}
          onClick={() => runAction(onUpload)}
        >
          <ArrowUpTrayIcon className="h-4 w-4 stroke-[2.5]" />
          {t('sandbox.contextMenu.uploadHere')}
        </button>
      )}
      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDefault}`}
        onClick={() => runAction(onReveal)}
      >
        <FolderOpenIcon className="h-4 w-4 stroke-[2.5]" />
        {t('sandbox.contextMenu.reveal')}
      </button>
      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDefault}`}
        onClick={() => runAction(onCopyPath)}
      >
        <ClipboardDocumentIcon className="h-4 w-4 stroke-[2.5]" />
        {t('sandbox.contextMenu.copyPath')}
      </button>
      {onDownload && (
        <button
          type="button"
          role="menuitem"
          className={`${itemBase} ${itemDefault}`}
          onClick={() => runAction(onDownload)}
        >
          <ArrowDownTrayIcon className="h-4 w-4 stroke-[2.5]" />
          {t('sandbox.contextMenu.download')}
        </button>
      )}
      {canDelete && (
        <>
          <div role="separator" className="my-0.5 h-0.5 bg-brutal-black" />
          <button
            type="button"
            role="menuitem"
            className={`${itemBase} ${itemDanger}`}
            onClick={() => runAction(onDelete)}
          >
            <TrashIcon className="h-4 w-4 stroke-[2.5]" />
            {t('sandbox.contextMenu.delete')}
          </button>
        </>
      )}
    </ContextMenu>
  );
};
