import React from 'react';
import { ContextMenu } from '../ContextMenu';
import { itemBase, itemDefault } from '../contextMenuStyles';
import { useI18n } from '../../i18n';
import { type MessageMenuAction } from './messageMenuActions';

/**
 * Right-click actions for one message. Callers pass only the handlers the
 * hover toolbar already shows, so the menu cannot do more than those buttons.
 */
export function MessageActionMenu({
  anchor,
  actions,
  onClose,
}: {
  anchor: { x: number; y: number };
  actions: MessageMenuAction[];
  onClose: () => void;
}): React.ReactElement {
  const { t } = useI18n();
  return (
    <ContextMenu anchor={anchor} onClose={onClose} label={t('chatMessage.menu')}>
      {actions.map((action) => (
        <button
          key={action.key}
          type="button"
          role="menuitem"
          className={`${itemBase} ${itemDefault}`}
          onClick={() => {
            action.onSelect();
            onClose();
          }}
        >
          {action.label}
        </button>
      ))}
    </ContextMenu>
  );
}
