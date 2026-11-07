import { isImeComposing } from '../../lib/ime';
import { claimContextMenu, prefersNativeContextMenu } from '../../lib/contextMenuClaim';

export interface MessageMenuAction {
  key: string;
  label: string;
  onSelect: () => void;
}

export function copyMessageText(text: string): void {
  const clipboard = navigator.clipboard;
  if (!clipboard) return;
  void clipboard.writeText(text).catch(() => {});
}

/** Open the message menu, or leave the event alone for a link, field, or selection. */
export function openOwnedMenu(
  event: React.MouseEvent | React.KeyboardEvent,
  open: (point: { x: number; y: number }) => void
): void {
  if ('key' in event) {
    if (isImeComposing(event)) return;
    if (event.key !== 'ContextMenu' && !(event.shiftKey && event.key === 'F10')) return;
    if (prefersNativeContextMenu(event.target, window.getSelection(), { button: 2 })) return;
    event.preventDefault();
    event.stopPropagation();
    const rect = event.currentTarget.getBoundingClientRect();
    open({ x: rect.left + 12, y: rect.top + 12 });
    return;
  }
  const native = event.nativeEvent;
  const pointerType =
    'pointerType' in native ? String((native as PointerEvent).pointerType) : undefined;
  if (
    !claimContextMenu(
      {
        target: event.target,
        button: event.button,
        pointerType,
        preventDefault: () => event.preventDefault(),
        stopPropagation: () => event.stopPropagation(),
      },
      window.getSelection()
    )
  ) {
    return;
  }
  const x = event.clientX > 0 || event.clientY > 0 ? event.clientX : 0;
  const y = event.clientY > 0 || event.clientX > 0 ? event.clientY : 0;
  if (x === 0 && y === 0) {
    const rect = event.currentTarget.getBoundingClientRect();
    open({ x: rect.left + 12, y: rect.top + 12 });
    return;
  }
  open({ x, y });
}
