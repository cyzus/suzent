import { useEffect, useRef, useState } from 'react';
import type React from 'react';

import { isImeComposing } from '../../lib/ime';

interface SidebarRenameInputProps {
  initialValue: string;
  /** Called with the trimmed name when it is non-empty and differs from `initialValue`. */
  onSave: (name: string) => void;
  /** Called when editing ends without a change to save. */
  onCancel: () => void;
  ariaLabel: string;
  placeholder?: string;
  autoFocus?: boolean;
  className?: string;
}

/**
 * Edits a sidebar row's name in place: Enter or clicking away saves, Escape cancels.
 */
export function SidebarRenameInput({
  initialValue,
  onSave,
  onCancel,
  ariaLabel,
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

  return (
    <input
      ref={inputRef}
      type="text"
      value={value}
      aria-label={ariaLabel}
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
      onBlur={() => finish(true)}
      onClick={(event) => event.stopPropagation()}
      onMouseDown={(event) => event.stopPropagation()}
      onDoubleClick={(event) => event.stopPropagation()}
      onContextMenu={(event) => event.stopPropagation()}
      className={`min-w-0 flex-1 rounded-sm border border-neutral-300 bg-white px-1.5 py-0.5 text-xs leading-snug font-medium text-brutal-black outline-none placeholder:text-neutral-400 focus:border-brutal-black dark:border-zinc-500 dark:bg-zinc-900 dark:text-white dark:focus:border-zinc-300 ${className}`}
    />
  );
}
