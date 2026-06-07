import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

export interface BrutalDialogAction {
  label: string;
  /** Button visual tone. */
  tone?: 'default' | 'primary' | 'danger';
  /** Triggers this action's onClick, then dismisses unless preventDismiss = true. */
  onClick?: () => void | Promise<void>;
  preventDismiss?: boolean;
}

interface BrutalDialogProps {
  open: boolean;
  title?: string;
  /** Plain text or a React node (e.g. for inline emphasis). */
  message: React.ReactNode;
  /**
   * Buttons rendered in the footer, left → right. Convention: cancel-style
   * action first, primary action last.
   */
  actions: BrutalDialogAction[];
  /** Called when the user presses Esc or clicks the backdrop / X. */
  onClose: () => void;
  /** Hide the close ✕ button. Useful for required confirmations. */
  hideClose?: boolean;
  /** Extra data-* attributes stamped on the dialog root (e.g. for outside-click whitelisting). */
  rootDataAttrs?: Record<string, string>;
}

/**
 * Brutalist modal dialog — fixed-position card with hard shadow, centered
 * behind a dimmed scrim. Use for confirmations, errors, and any prompt that
 * needs the user's attention. Replaces window.alert / window.confirm.
 */
export const BrutalDialog: React.FC<BrutalDialogProps> = ({
  open,
  title,
  message,
  actions,
  onClose,
  hideClose,
  rootDataAttrs,
}) => {
  const cardRef = useRef<HTMLDivElement | null>(null);

  // Dismiss on Escape; trap focus to the dialog.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    // Move focus to the first button so the user can immediately Enter / Tab.
    const t = setTimeout(() => {
      cardRef.current?.querySelector<HTMLButtonElement>('button[data-primary="true"]')?.focus()
        ?? cardRef.current?.querySelector<HTMLButtonElement>('button')?.focus();
    }, 0);
    return () => {
      document.removeEventListener('keydown', onKey);
      clearTimeout(t);
    };
  }, [open, onClose]);

  if (!open) return null;

  const toneClass = (tone: BrutalDialogAction['tone']) => {
    switch (tone) {
      case 'primary':
        return 'bg-brutal-black text-white hover:bg-neutral-800 dark:bg-brutal-yellow dark:text-brutal-black dark:hover:bg-yellow-300';
      case 'danger':
        return 'bg-brutal-red text-white hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-500';
      case 'default':
      default:
        return 'bg-white text-brutal-black hover:bg-neutral-100 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700';
    }
  };

  const handleActionClick = async (action: BrutalDialogAction) => {
    try {
      await action.onClick?.();
    } finally {
      if (!action.preventDismiss) onClose();
    }
  };

  const dialog = (
    <div
      className="fixed inset-0 z-[9998] flex items-center justify-center p-4 animate-brutal-drop"
      style={{ backgroundColor: 'rgba(0,0,0,0.4)' }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !hideClose) onClose();
      }}
      {...(rootDataAttrs || {})}
    >
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? 'brutal-dialog-title' : undefined}
        className="relative w-full max-w-sm bg-white dark:bg-zinc-900 border-2 border-brutal-black dark:border-zinc-500 shadow-[5px_5px_0_0_#000] dark:shadow-[5px_5px_0_0_rgba(255,255,255,0.15)]"
      >
        {/* Header */}
        {(title || !hideClose) && (
          <div className="flex items-center gap-2 px-4 py-3 border-b-2 border-brutal-black dark:border-zinc-500">
            {title && (
              <h2
                id="brutal-dialog-title"
                className="flex-1 text-sm font-extrabold uppercase tracking-wider text-brutal-black dark:text-white"
              >
                {title}
              </h2>
            )}
            {!hideClose && (
              <button
                type="button"
                aria-label="Close"
                onClick={onClose}
                className="ml-auto p-1 text-brutal-black dark:text-white hover:bg-brutal-black/10 dark:hover:bg-white/10 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        )}

        {/* Body */}
        <div className="px-4 py-4 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">
          {message}
        </div>

        {/* Actions — cancel leftmost, destructive rightmost */}
        <div className="flex items-stretch border-t-2 border-brutal-black dark:border-zinc-500">
          {actions.map((action, i) => (
            <button
              key={action.label + i}
              type="button"
              data-primary={action.tone === 'primary' || action.tone === 'danger' ? 'true' : undefined}
              onClick={() => handleActionClick(action)}
              className={`flex-1 py-3 text-xs font-bold uppercase tracking-wide transition-colors ${i > 0 ? 'border-l-2 border-brutal-black dark:border-zinc-500' : ''} ${toneClass(action.tone)}`}
            >
              {action.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );

  return createPortal(dialog, document.body);
};
