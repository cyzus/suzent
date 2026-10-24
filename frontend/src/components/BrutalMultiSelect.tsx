import React, { useState, useRef, useEffect, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../i18n';

interface Option {
  value: string;
  label: string;
  description?: string;
}

interface BrutalMultiSelectProps {
  disabled?: boolean;
  value: string[];
  onChange: (value: string[]) => void;
  options: (string | Option)[];
  label?: string;
  placeholder?: string;
  dropUp?: boolean;
  className?: string;
  dropdownClassName?: string;
  variant?: 'dropdown' | 'list';
  emptyMessage?: string;
  emptyAction?: React.ReactNode;
}

export const BrutalMultiSelect: React.FC<BrutalMultiSelectProps> = ({
  disabled = false,
  value = [],
  onChange,
  options,
  label,
  placeholder,
  dropUp = false,
  className = '',
  dropdownClassName = '',
  variant = 'dropdown',
  emptyMessage,
  emptyAction,
}) => {
  const { t } = useI18n();
  const effectivePlaceholder = placeholder ?? t('multiSelect.placeholder');
  const effectiveEmptyMessage = emptyMessage ?? t('multiSelect.emptyMessage');
  const [isOpen, setIsOpen] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState<{
    top: number;
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

  // Auto-flip determination
  const [effectiveDropUp, setEffectiveDropUp] = useState(dropUp);

  // Calculate dropdown position
  const updatePosition = React.useCallback(() => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      // Estimate height (max 240px)
      const ESTIMATED_HEIGHT = 240;
      const dropdownHeight = Math.min(
        normalizedOptions.length * 40 + (normalizedOptions.length === 0 ? 50 : 0),
        ESTIMATED_HEIGHT
      );

      const spaceAbove = rect.top;
      const spaceBelow = window.innerHeight - rect.bottom;

      let shouldDropUp = dropUp;

      // Auto-flip logic
      if (dropUp && spaceAbove < dropdownHeight && spaceBelow > dropdownHeight) {
        shouldDropUp = false;
      } else if (!dropUp && spaceBelow < dropdownHeight && spaceAbove > dropdownHeight) {
        shouldDropUp = true;
      }

      setEffectiveDropUp(shouldDropUp);

      if (shouldDropUp) {
        setDropdownPosition({
          top: rect.top - dropdownHeight - 4, // Simple approximation, but we'll use auto/bottom in styles
          left: rect.left,
          width: rect.width,
        });
      } else {
        setDropdownPosition({
          top: rect.bottom + 4,
          left: rect.left,
          width: rect.width,
        });
      }
    }
  }, [dropUp, normalizedOptions.length]);

  useLayoutEffect(() => {
    if (isOpen && variant === 'dropdown') {
      updatePosition();

      window.addEventListener('resize', updatePosition);
      window.addEventListener('scroll', updatePosition, true);

      return () => {
        window.removeEventListener('resize', updatePosition);
        window.removeEventListener('scroll', updatePosition, true);
      };
    }
  }, [isOpen, variant, updatePosition]);

  // Close on click outside (only for dropdown)
  useEffect(() => {
    if (variant !== 'dropdown') return;
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      const isOutsideContainer = containerRef.current && !containerRef.current.contains(target);
      const isOutsideDropdown = dropdownRef.current && !dropdownRef.current.contains(target);

      if (isOutsideContainer && isOutsideDropdown) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [variant, isOpen]);

  const handleToggle = (val: string) => {
    if (disabled) return;
    const newValue = value.includes(val) ? value.filter((v) => v !== val) : [...value, val];
    onChange(newValue);
  };

  if (variant === 'list') {
    return (
      <div className={`space-y-2 ${className}`}>
        {label && (
          <label className="block font-bold tracking-wide text-brutal-black dark:text-zinc-200 uppercase mb-1 text-xs">
            {label}
          </label>
        )}
        <div
          className={`flex flex-col gap-2 w-full bg-neutral-50 dark:bg-zinc-900 border-2 border-brutal-black p-2 max-h-60 overflow-y-auto scrollbar-thin ${dropdownClassName}`}
        >
          {normalizedOptions.length === 0 && (
            <div className="text-center py-8 text-neutral-500 font-bold uppercase text-xs">
              {effectiveEmptyMessage}
              {emptyAction && <div className="mt-2">{emptyAction}</div>}
            </div>
          )}
          {normalizedOptions.map((option) => {
            const active = value.includes(option.value);
            return (
              <button
                key={option.value}
                type="button"
                disabled={disabled}
                aria-pressed={active}
                onClick={() => handleToggle(option.value)}
                className={`flex items-center gap-3 px-3 py-2 border-2 text-xs font-bold uppercase transition-all duration-100 w-full min-w-0 text-left group disabled:cursor-not-allowed disabled:opacity-50 ${
                  active
                    ? 'bg-brutal-green text-brutal-black dark:bg-emerald-400/10 dark:text-emerald-200 dark:border-emerald-400/30 border-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] translate-x-[-1px] translate-y-[-1px]'
                    : 'border-brutal-black text-brutal-black dark:text-white bg-white dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700 brutal-btn shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
                }`}
              >
                <div
                  className={`w-4 h-4 shrink-0 border-2 border-brutal-black flex items-center justify-center transition-colors ${active ? 'bg-brutal-black' : 'bg-white dark:bg-zinc-900'}`}
                >
                  {active && (
                    <svg
                      className="w-3 h-3 text-white"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={4}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </div>
                <span className="min-w-0 flex-1">
                  <span className="block truncate" title={option.value}>
                    {option.label}
                  </span>
                  {option.description && (
                    <span className="block mt-1 text-[10px] font-normal normal-case text-neutral-500 dark:text-neutral-400 break-all">
                      {option.description}
                    </span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  const selectedCount = value.length;
  const displayLabel =
    selectedCount === 0
      ? effectivePlaceholder
      : selectedCount === 1
        ? normalizedOptions.find((o) => o.value === value[0])?.label || value[0]
        : `${selectedCount} ITEMS SELECTED`;

  const dropdown =
    isOpen &&
    !disabled &&
    dropdownPosition &&
    createPortal(
      <div
        ref={dropdownRef}
        className={`fixed z-[9999] bg-white dark:bg-zinc-800 dark:text-zinc-200 border-3 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] max-h-60 overflow-y-auto overflow-x-hidden animate-brutal-drop scrollbar-thin ${dropdownClassName}`}
        style={{
          top: effectiveDropUp ? 'auto' : dropdownPosition.top,
          bottom: effectiveDropUp
            ? window.innerHeight - dropdownPosition.top - (buttonRef.current?.offsetHeight ?? 0) - 8
            : 'auto', // Approx bottom positioning
          left: dropdownPosition.left,
          width: dropdownPosition.width,
        }}
      >
        {normalizedOptions.length === 0 && (
          <div className="p-3 text-xs text-neutral-500 font-bold uppercase text-center">
            {effectiveEmptyMessage}
          </div>
        )}
        {normalizedOptions.map((option) => {
          const isSelected = value.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => handleToggle(option.value)}
              className={`w-full text-left px-3 py-2 font-bold text-xs uppercase transition-colors border-b-2 border-neutral-100 last:border-0 flex items-center gap-2 hover:bg-neutral-50 dark:border-white/10 dark:hover:bg-zinc-700`}
            >
              <div
                className={`w-4 h-4 border-2 border-brutal-black flex items-center justify-center transition-colors ${isSelected ? 'bg-brutal-green' : 'bg-white dark:bg-zinc-900 dark:border-white/20'}`}
              >
                {isSelected && (
                  <svg
                    className="w-3 h-3 text-brutal-black"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={4}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </div>
              <span
                className={`flex-1 ${isSelected ? 'text-brutal-black dark:text-zinc-100' : 'text-neutral-600 dark:text-zinc-300'}`}
              >
                {option.label}
              </span>
            </button>
          );
        })}
      </div>,
      document.body
    );

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      {label && (
        <label className="block font-bold tracking-wide text-brutal-black dark:text-zinc-200 uppercase mb-1 text-xs">
          {label}
        </label>
      )}

      <button
        ref={buttonRef}
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full bg-white dark:bg-zinc-800 dark:text-zinc-200 border-3 border-brutal-black px-3 py-2 font-bold text-sm text-left flex items-center justify-between transition-all duration-200 hover:bg-brutal-yellow dark:hover:bg-zinc-700 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 ${isOpen ? 'shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] translate-x-[1px] translate-y-[1px]' : 'shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] brutal-btn'}`}
      >
        <span className="truncate">{displayLabel}</span>
        <svg
          className={`w-4 h-4 transition-transform duration-200 ${isOpen ? (effectiveDropUp ? 'rotate-0' : 'rotate-180') : effectiveDropUp ? 'rotate-180' : 'rotate-0'}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth={3}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {dropdown}
    </div>
  );
};
