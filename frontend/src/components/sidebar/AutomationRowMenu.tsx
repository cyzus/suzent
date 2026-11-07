import React from 'react';
import { ContextMenu } from '../ContextMenu';
import { itemBase, itemDefault, itemDanger } from '../contextMenuStyles';
import { useI18n } from '../../i18n';

interface ScheduledTaskMenuProps {
  anchor: { x: number; y: number } | { rect: DOMRect };
  boundary?: DOMRect | null;
  active: boolean;
  runDisabled: boolean;
  onToggleActive: () => void;
  onRunNow: () => void;
  onRename: () => void;
  onDelete: () => void;
  onClose: () => void;
}

/** Sidebar menu for one scheduled task. Delete stays last and is confirmed by the caller. */
export function ScheduledTaskMenu({
  anchor,
  boundary,
  active,
  runDisabled,
  onToggleActive,
  onRunNow,
  onRename,
  onDelete,
  onClose,
}: ScheduledTaskMenuProps): React.ReactElement {
  const { t } = useI18n();
  const run = (action: () => void) => {
    action();
    onClose();
  };

  return (
    <ContextMenu
      anchor={anchor}
      onClose={onClose}
      boundary={boundary}
      label={t('chatList.menu.title')}
    >
      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDefault}`}
        onClick={() => run(onToggleActive)}
      >
        {t(active ? 'chatList.automation.pause' : 'chatList.automation.resume')}
      </button>
      <button
        type="button"
        role="menuitem"
        disabled={runDisabled}
        className={`${itemBase} ${itemDefault}`}
        onClick={() => {
          if (runDisabled) return;
          run(onRunNow);
        }}
      >
        {t('chatList.automation.runNow')}
      </button>
      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDefault}`}
        onClick={() => run(onRename)}
      >
        {t('chatList.menu.rename')}
      </button>
      <div role="separator" className="my-0.5 h-0.5 bg-brutal-black" />
      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDanger}`}
        onClick={() => run(onDelete)}
      >
        {t('chatList.menu.delete')}
      </button>
    </ContextMenu>
  );
}

interface HeartbeatRowMenuProps {
  anchor: { x: number; y: number } | { rect: DOMRect };
  boundary?: DOMRect | null;
  runDisabled: boolean;
  onOpen: () => void;
  onDisable: () => void;
  onRunNow: () => void;
  onClose: () => void;
}

/** Sidebar menu for one heartbeat session. Turning it off does not delete the chat. */
export function HeartbeatRowMenu({
  anchor,
  boundary,
  runDisabled,
  onOpen,
  onDisable,
  onRunNow,
  onClose,
}: HeartbeatRowMenuProps): React.ReactElement {
  const { t } = useI18n();
  const run = (action: () => void) => {
    action();
    onClose();
  };

  return (
    <ContextMenu
      anchor={anchor}
      onClose={onClose}
      boundary={boundary}
      label={t('chatList.menu.title')}
    >
      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDefault}`}
        onClick={() => run(onOpen)}
      >
        {t('chatBoard.menu.open')}
      </button>
      <button
        type="button"
        role="menuitem"
        disabled={runDisabled}
        className={`${itemBase} ${itemDefault}`}
        onClick={() => {
          if (runDisabled) return;
          run(onRunNow);
        }}
      >
        {t('chatList.automation.runHeartbeat')}
      </button>
      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDefault}`}
        onClick={() => run(onDisable)}
      >
        {t('chatList.automation.disableHeartbeat')}
      </button>
    </ContextMenu>
  );
}
