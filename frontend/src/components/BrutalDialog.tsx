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
        return 'bg-brutal-black text-white hover:bg-brutal-blue';
      case 'danger':
        return 'bg-brutal-red text-white hover:bg-red-700';
      case 'default':
      default:
        return 'bg-white dark:bg-zinc-700 dark:text-white text-brutal-black hover:bg-brutal-yellow dark:hover:bg-brutal-yellow dark:hover:text-brutal-black';
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
        // Click outside the card dismisses, unless hideClose is set.
        if (e.target === e.currentTarget && !hideClose) onClose();
      }}
      {...(rootDataAttrs || {})}
    >
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? 'brutal-dialog-title' : undefined}
        className="relative w-full max-w-md bg-white dark:bg-zinc-800 border-2 border-brutal-black shadow-[6px_6px_0_0_#000]"
      >
        {/* Header */}
        {(title || !hideClose) && (
          <div className="flex items-start gap-2 px-4 py-3 border-b-2 border-brutal-black">
            {title && (
              <h2
                id="brutal-dialog-title"
                className="flex-1 text-sm font-extrabold uppercase tracking-wider text-brutal-black dark:text-white truncate"
              >
                {title}
              </h2>
            )}
            {!hideClose && (
              <button
                type="button"
                aria-label="Close"
                onClick={onClose}
                className="ml-auto p-1 hover:bg-brutal-black/10 dark:hover:bg-white/10 text-brutal-black dark:text-white"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        )}

        {/* Body */}
        <div className="px-4 py-4 text-sm leading-relaxed text-brutal-black dark:text-white">
          {message}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900">
          {actions.map((action, i) => {
            const isPrimary = i === actions.length - 1;
            return (
              <button
                key={action.label + i}
                type="button"
                data-primary={isPrimary ? 'true' : undefined}
                onClick={() => handleActionClick(action)}
                className={`px-3 py-1.5 border-2 border-brutal-black text-xs font-extrabold uppercase tracking-wider shadow-[2px_2px_0_0_#000] hover:translate-y-[1px] hover:translate-x-[1px] hover:shadow-[1px_1px_0_0_#000] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none transition-all ${toneClass(action.tone)}`}
              >
                {action.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );

  return createPortal(dialog, document.body);
};
