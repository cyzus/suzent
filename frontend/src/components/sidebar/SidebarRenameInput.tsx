import { useEffect, useRef, useState } from 'react';
import type React from 'react';
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';

import { isImeComposing } from '../../lib/ime';

interface SidebarRenameInputProps {
  initialValue: string;
  /** Called with the trimmed name when it is non-empty and differs from `initialValue`. */
  onSave: (name: string) => void;
  /** Called when editing ends without a change to save. */
  onCancel: () => void;
  ariaLabel: string;
  saveLabel: string;
  cancelLabel: string;
  placeholder?: string;
  autoFocus?: boolean;
  className?: string;
}

/**
 * Edits a sidebar row's name in place: Enter, the check button or clicking away saves;
 * Escape or the cross button cancels.
 */
export function SidebarRenameInput({
  initialValue,
  onSave,
  onCancel,
  ariaLabel,
  saveLabel,
  cancelLabel,
  placeholder,
  autoFocus = true,
  className = '',
}: SidebarRenameInputProps): React.ReactElement {
  const [value, setValue] = useState(initialValue);
  const inputRef = useRef<HTMLInputElement>(null);
  // Enter and Escape unmount the input, which fires one more blur; this keeps that blur from saving again.
  const doneRef = useRef(false);

  useEffect(() => {
    if (!autoFocus) return;
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [autoFocus]);

  const finish = (save: boolean): void => {
    if (doneRef.current) return;
    doneRef.current = true;
    const trimmed = value.trim();
    if (save && trimmed && trimmed !== initialValue) onSave(trimmed);
    else onCancel();
  };

  const iconButton =
    'flex h-5 w-5 shrink-0 items-center justify-center rounded-sm text-neutral-500 transition-colors dark:text-neutral-400';
  // Pressing a button would otherwise blur the input first, and blur saves.
  const keepFocus = (event: React.MouseEvent): void => {
    event.preventDefault();
    event.stopPropagation();
  };

  return (
    <span className={`flex min-w-0 flex-1 items-center gap-0.5 ${className}`}>
      <input
        ref={inputRef}
        type="text"
        value={value}
        aria-label={ariaLabel}
        data-sidebar-rename
        placeholder={placeholder}
        spellCheck={false}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          event.stopPropagation();
          if (isImeComposing(event)) return;
          if (event.key === 'Enter') {
            event.preventDefault();
            finish(true);
          } else if (event.key === 'Escape') {
            event.preventDefault();
            finish(false);
          }
        }}
        onBlur={(event) => {
          // A chat that is both pinned and listed renders this editor twice; focus moving
          // between the copies must not end the rename.
          if (
            event.relatedTarget instanceof HTMLElement &&
            'sidebarRename' in event.relatedTarget.dataset
          )
            return;
          finish(true);
        }}
        onClick={(event) => event.stopPropagation()}
        onMouseDown={(event) => event.stopPropagation()}
        onDoubleClick={(event) => event.stopPropagation()}
        onContextMenu={(event) => event.stopPropagation()}
        className="min-w-0 flex-1 rounded-sm border border-neutral-300 bg-white px-1.5 py-0.5 text-xs leading-snug font-medium text-brutal-black outline-none placeholder:text-neutral-400 focus:border-brutal-black dark:border-zinc-500 dark:bg-zinc-900 dark:text-white dark:focus:border-zinc-300"
      />
      <button
        type="button"
        aria-label={saveLabel}
        title={saveLabel}
        onMouseDown={keepFocus}
        onClick={(event) => {
          event.stopPropagation();
          finish(true);
        }}
        className={`${iconButton} hover:bg-brutal-yellow hover:text-brutal-black`}
      >
        <CheckIcon className="h-3.5 w-3.5 stroke-[2.5]" />
      </button>
      <button
        type="button"
        aria-label={cancelLabel}
        title={cancelLabel}
        onMouseDown={keepFocus}
        onClick={(event) => {
          event.stopPropagation();
          finish(false);
        }}
        className={`${iconButton} hover:bg-neutral-200 hover:text-brutal-black dark:hover:bg-zinc-600 dark:hover:text-white`}
      >
        <XMarkIcon className="h-3.5 w-3.5 stroke-[2.5]" />
      </button>
    </span>
  );
}
