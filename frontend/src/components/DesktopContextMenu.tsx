import React, { useEffect, useState } from 'react';
import { ContextMenu } from './ContextMenu';
import { itemBase, itemDefault } from './contextMenuStyles';
import { useI18n } from '../i18n';

interface MenuState {
  x: number;
  y: number;
  target: HTMLElement;
  editable: boolean;
  text: string;
  range: Range | null;
  start: number | null;
  end: number | null;
}

export function DesktopContextMenu({
  onSettings,
}: {
  onSettings: () => void;
}): React.ReactElement | null {
  const { t } = useI18n();
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const open = (event: MouseEvent): void => {
      if (event.defaultPrevented || !(event.target instanceof HTMLElement)) return;
      event.preventDefault();
      const target =
        event.target.closest<HTMLElement>('input, textarea, [contenteditable="true"]') ??
        event.target;
      const field =
        target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement ? target : null;
      const selection = window.getSelection();
      setError(false);
      setMenu({
        x: event.clientX,
        y: event.clientY,
        target,
        editable: field ? !field.readOnly && !field.disabled : target.isContentEditable,
        text: field
          ? field.value.slice(field.selectionStart ?? 0, field.selectionEnd ?? 0)
          : (selection?.toString() ?? ''),
        range: selection?.rangeCount ? selection.getRangeAt(0).cloneRange() : null,
        start: field?.selectionStart ?? null,
        end: field?.selectionEnd ?? null,
      });
    };
    document.addEventListener('contextmenu', open);
    return () => document.removeEventListener('contextmenu', open);
  }, []);
  if (!menu) return null;
  const restore = (): void => {
    menu.target.focus({ preventScroll: true });
    if (
      (menu.target instanceof HTMLInputElement || menu.target instanceof HTMLTextAreaElement) &&
      menu.start !== null
    ) {
      menu.target.setSelectionRange(menu.start, menu.end);
    } else if (menu.range) {
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(menu.range);
    }
  };
  const run = async (action: string): Promise<void> => {
    try {
      if (action === 'copy' || action === 'cut') await navigator.clipboard.writeText(menu.text);
      if (action === 'paste') {
        const text = await navigator.clipboard.readText();
        restore();
        if (!document.execCommand('insertText', false, text)) throw new Error('paste');
      } else if (action === 'cut' || action === 'selectAll') {
        restore();
        if (!document.execCommand(action === 'cut' ? 'delete' : 'selectAll'))
          throw new Error(action);
      } else if (action === 'settings') onSettings();
      else if (action === 'reload') window.location.reload();
      setMenu(null);
    } catch {
      setError(true);
    }
  };
  const actions = menu.editable
    ? ['cut', 'copy', 'paste', 'selectAll']
    : menu.text
      ? ['copy', 'selectAll']
      : ['settings', 'reload'];
  return (
    <ContextMenu anchor={menu} onClose={() => setMenu(null)} label={t('desktopMenu.label')}>
      {actions.map((action) => (
        <button
          key={action}
          type="button"
          role="menuitem"
          disabled={(action === 'copy' || action === 'cut') && !menu.text}
          className={`${itemBase} ${itemDefault}`}
          onClick={() => void run(action)}
        >
          {t(`desktopMenu.${action}`)}
        </button>
      ))}
      {error && (
        <p role="alert" className="px-3 py-2 text-xs text-brutal-red">
          {t('desktopMenu.failed')}
        </p>
      )}
    </ContextMenu>
  );
}
