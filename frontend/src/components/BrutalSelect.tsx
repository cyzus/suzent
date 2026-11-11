import React, { useState, useRef, useEffect, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../i18n';

interface Option {
  value: string;
  label: string;
  /** Rendered but not selectable — e.g. an agent whose binary isn't installed. */
  disabled?: boolean;
  /** Secondary line under the label, used to explain a disabled option. */
  hint?: string;
  /** Optional section heading; consecutive options sharing one are grouped. */
  group?: string;
}

interface BrutalSelectProps {
  value: string;
  ariaLabel?: string;
  menuAlign?: 'start' | 'end';
  onChange: (value: string) => void;
  options: (string | Option)[];
  label?: string;
  placeholder?: string;
  dropUp?: boolean;
  disabled?: boolean;
  hideChevron?: boolean;
  /** `ghost` drops the border, shadow and fill so the trigger sits inside a toolbar. */
  variant?: 'framed' | 'ghost';
  /** Optional override for the trigger label when a custom display string is needed. */
  selectedLabel?: string;
  /** Keep dropdown open after selecting an option when `onChange` returns `true`. */
  keepOpenOnSelect?: (value: string) => boolean;
  className?: string;
  buttonClassName?: string;
  dropdownClassName?: string;
}

export const BrutalSelect: React.FC<BrutalSelectProps> = ({
  value,
  ariaLabel,
  menuAlign = 'start',
  onChange,
  options,
  label,
  placeholder,
  dropUp = false,
  disabled = false,
  hideChevron = false,
  variant = 'framed',
  selectedLabel,
  keepOpenOnSelect,
  className = '',
  buttonClassName = '',
  dropdownClassName = '',
}) => {
  const { t } = useI18n();
  const effectivePlaceholder = placeholder ?? t('select.placeholder');
  const [isOpen, setIsOpen] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState<{
    top?: number;
    bottom?: number;
    maxHeight: number;
    left: number;
    width: number;
  } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Normalize options to Option objects
  const normalizedOptions: Option[] = options.map((opt) =>
    typeof opt === 'string' ? { value: opt, label: opt } : opt
  );

  const selectedOption = normalizedOptions.find((opt) => opt.value === value);

  // Auto-flip determination
  const [effectiveDropUp, setEffectiveDropUp] = useState(dropUp);

  // Calculate dropdown position
  const updatePosition = React.useCallback(() => {
    const button = buttonRef.current;
    const dropdown = dropdownRef.current;
    if (!button || !dropdown) return;

    const rect = button.getBoundingClientRect();
    dropdown.style.width = `${rect.width}px`;
    const margin = 8;
    const gap = 4;
    const dropdownHeight = Math.min(dropdown.scrollHeight + 6, 240);
    const dropdownWidth = Math.max(rect.width, dropdown.offsetWidth);
    const spaceAbove = Math.max(0, rect.top - gap - margin);
    const spaceBelow = Math.max(0, window.innerHeight - rect.bottom - gap - margin);
    const preferredSpace = dropUp ? spaceAbove : spaceBelow;
    const otherSpace = dropUp ? spaceBelow : spaceAbove;
    const shouldDropUp =
      preferredSpace < dropdownHeight && otherSpace > preferredSpace ? !dropUp : dropUp;

    setEffectiveDropUp(shouldDropUp);
    setDropdownPosition({
      ...(shouldDropUp
        ? { bottom: Math.max(margin, window.innerHeight - rect.top + gap) }
        : { top: Math.max(margin, rect.bottom + gap) }),
      left: Math.max(
        margin,
        Math.min(
          menuAlign === 'end' ? rect.right - dropdownWidth : rect.left,
          window.innerWidth - dropdownWidth - margin
        )
      ),
      width: rect.width,
      maxHeight: Math.min(240, shouldDropUp ? spaceAbove : spaceBelow),
    });
  }, [dropUp, menuAlign]);

  useLayoutEffect(() => {
    if (isOpen) {
      updatePosition();

      window.addEventListener('resize', updatePosition);
      window.addEventListener('scroll', updatePosition, true); // Capture scroll on any element

      return () => {
        window.removeEventListener('resize', updatePosition);
        window.removeEventListener('scroll', updatePosition, true);
      };
    }
  }, [isOpen, options, updatePosition]);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      const isOutsideContainer = containerRef.current && !containerRef.current.contains(target);
      const isOutsideDropdown = dropdownRef.current && !dropdownRef.current.contains(target);

      if (isOutsideContainer && isOutsideDropdown) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const dropdown =
    isOpen &&
    createPortal(
      <div
        ref={dropdownRef}
        className={`fixed z-[9999] bg-white dark:bg-zinc-800 border-3 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] max-h-60 overflow-x-hidden overflow-y-auto scrollbar-thin animate-brutal-drop ${dropdownClassName}`}
        style={{
          top: dropdownPosition?.top,
          bottom: dropdownPosition?.bottom,
          left: dropdownPosition?.left ?? 0,
          width: dropdownPosition?.width ?? buttonRef.current?.getBoundingClientRect().width,
          maxHeight: dropdownPosition?.maxHeight ?? 240,
          maxWidth: 'calc(100vw - 16px)',
          visibility: dropdownPosition ? undefined : 'hidden',
        }}
      >
        {normalizedOptions.map((option, optionIndex) => {
          const previousGroup =
            optionIndex > 0 ? normalizedOptions[optionIndex - 1].group : undefined;
          const showGroupHeader = !!option.group && option.group !== previousGroup;
          return (
            <React.Fragment key={option.value}>
              {showGroupHeader && (
                <div className="px-3 pt-2 pb-1 text-[10px] font-mono font-bold uppercase tracking-widest text-neutral-500 dark:text-neutral-400 bg-neutral-50 dark:bg-zinc-900 border-b-2 border-neutral-100 dark:border-zinc-700">
                  {option.group}
                </div>
              )}
              <button
                type="button"
                disabled={option.disabled}
                onClick={() => {
                  if (option.disabled) return;
                  onChange(option.value);
                  if (!keepOpenOnSelect?.(option.value)) {
                    setIsOpen(false);
                  }
                }}
                className={`group w-full text-left px-3 py-2 font-bold text-sm uppercase transition-colors border-b-2 border-neutral-100 dark:border-zinc-700 last:border-0 ${
                  option.disabled
                    ? 'bg-white dark:bg-zinc-800 text-neutral-400 dark:text-neutral-600 cursor-not-allowed'
                    : value === option.value
                      ? 'bg-brutal-black text-white dark:bg-brutal-yellow dark:text-brutal-black'
                      : 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-brutal-yellow dark:hover:bg-zinc-700'
                }`}
              >
                {option.label}
                {option.hint && (
                  <span
                    className={`block normal-case font-normal text-[10px] leading-tight mt-0.5 ${
                      option.disabled
                        ? 'text-neutral-500 dark:text-neutral-500'
                        : value === option.value
                          ? 'text-neutral-300 dark:text-neutral-700'
                          : 'text-neutral-500 dark:text-neutral-400 group-hover:text-neutral-700 dark:group-hover:text-neutral-300'
                    }`}
                  >
                    {option.hint}
                  </span>
                )}
              </button>
            </React.Fragment>
          );
        })}
      </div>,
      document.body
    );

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      {label && (
        <label className="block font-bold tracking-wide text-brutal-black dark:text-white uppercase mb-1 text-xs">
          {label}
        </label>
      )}

      <button
        ref={buttonRef}
        type="button"
        aria-label={ariaLabel}
        aria-expanded={isOpen}
        disabled={disabled}
        onClick={() => {
          if (!disabled) setIsOpen(!isOpen);
        }}
        className={`w-full dark:text-white px-3 py-2 font-bold text-sm text-left flex items-center justify-between transition-all duration-200 focus:outline-none disabled:cursor-not-allowed disabled:opacity-40 ${
          variant === 'ghost'
            ? 'bg-transparent'
            : `bg-white dark:bg-zinc-800 border-3 border-brutal-black hover:bg-brutal-yellow dark:hover:bg-zinc-700 disabled:hover:bg-white dark:disabled:hover:bg-zinc-800 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] ${isOpen ? 'translate-x-[1px] translate-y-[1px]' : 'brutal-btn'}`
        } ${buttonClassName}`}
      >
        <span className="truncate">
          {selectedLabel ?? (selectedOption ? selectedOption.label : effectivePlaceholder)}
        </span>
        {!hideChevron && (
          <svg
            className={`w-4 h-4 transition-transform duration-200 ${isOpen ? (effectiveDropUp ? 'rotate-0' : 'rotate-180') : effectiveDropUp ? 'rotate-180' : 'rotate-0'}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            strokeWidth={3}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>

      {dropdown}
    </div>
  );
};
