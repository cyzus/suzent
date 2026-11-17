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
  /** `compact` lists options in small, single-line, normal-case rows. */
  menuSize?: 'default' | 'compact';
  /** Let the menu grow wider than its trigger, up to the viewport. */
  menuMinWidth?: number;
  /** Allow clicking section group headers to collapse or expand their options. */
  collapsibleGroups?: boolean;
  /** Optional localStorage key to remember expanded/collapsed group states. */
  collapsibleGroupsStorageKey?: string;
  /** Show a quick filter input at the top of the dropdown menu. */
  searchable?: boolean;
  searchPlaceholder?: string;
  emptySearchMessage?: string;
  /** Optional refresh callback rendered in the dropdown header. */
  onRefresh?: () => void | Promise<void>;
  refreshing?: boolean;
  refreshTitle?: string;
  /** Optional star/favorite support for options. */
  starredValues?: ReadonlySet<string>;
  onToggleStar?: (value: string, starred: boolean) => void | Promise<void>;
  canStarOption?: (value: string) => boolean;
  starLabel?: string;
  unstarLabel?: string;
  /** Called whenever the dropdown opens or closes. */
  onOpenChange?: (open: boolean) => void;
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
  menuSize = 'default',
  menuMinWidth = 0,
  collapsibleGroups = false,
  collapsibleGroupsStorageKey,
  searchable = false,
  searchPlaceholder,
  emptySearchMessage,
  onRefresh,
  refreshing = false,
  refreshTitle,
  starredValues,
  onToggleStar,
  canStarOption,
  starLabel,
  unstarLabel,
  onOpenChange,
}) => {
  const compact = menuSize === 'compact';
  const { t } = useI18n();
  const effectivePlaceholder = placeholder ?? t('select.placeholder');
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchCollapsedGroups, setSearchCollapsedGroups] = useState<Set<string>>(new Set());
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => {
    if (!collapsibleGroups || !collapsibleGroupsStorageKey) return new Set();
    try {
      const raw = localStorage.getItem(collapsibleGroupsStorageKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) return new Set(parsed.filter((x) => typeof x === 'string'));
      }
    } catch {
      // Ignore storage errors
    }
    return new Set();
  });
  const initializedCollapseRef = useRef(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
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

  // Initialize default collapsed groups when no stored state exists: keep the
  // currently selected option's group expanded and collapse other groups when
  // there are multiple groups.
  useEffect(() => {
    if (!collapsibleGroups || initializedCollapseRef.current) return;
    const allGroups = Array.from(
      new Set(normalizedOptions.map((o) => o.group).filter((g): g is string => !!g))
    );
    if (allGroups.length === 0) return;
    initializedCollapseRef.current = true;

    if (collapsibleGroupsStorageKey) {
      try {
        if (localStorage.getItem(collapsibleGroupsStorageKey) !== null) {
          // Ensure selected option's group is open when first loaded
          if (selectedOption?.group) {
            setCollapsedGroups((prev) => {
              if (!prev.has(selectedOption.group!)) return prev;
              const next = new Set(prev);
              next.delete(selectedOption.group!);
              return next;
            });
          }
          return;
        }
      } catch {
        // Ignore storage errors
      }
    }

    if (allGroups.length > 1 && selectedOption?.group) {
      setCollapsedGroups(new Set(allGroups.filter((g) => g !== selectedOption.group)));
    }
  }, [collapsibleGroups, collapsibleGroupsStorageKey, normalizedOptions, selectedOption?.group]);

  const trimmedQuery = searchQuery.trim().toLowerCase();

  // Reset search-specific manual collapses whenever the query text changes so
  // new search hits start expanded, while still allowing the user to collapse
  // any group in the search results.
  useEffect(() => {
    setSearchCollapsedGroups(new Set());
  }, [trimmedQuery]);

  const toggleGroupCollapse = (groupName: string) => {
    if (trimmedQuery) {
      setSearchCollapsedGroups((prev) => {
        const next = new Set(prev);
        if (next.has(groupName)) {
          next.delete(groupName);
        } else {
          next.add(groupName);
        }
        return next;
      });
      return;
    }
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupName)) {
        next.delete(groupName);
      } else {
        next.add(groupName);
      }
      if (collapsibleGroupsStorageKey) {
        try {
          localStorage.setItem(collapsibleGroupsStorageKey, JSON.stringify([...next]));
        } catch {
          // Ignore storage errors
        }
      }
      return next;
    });
  };

  const filteredOptions = trimmedQuery
    ? normalizedOptions.filter((opt) =>
        `${opt.label} ${opt.value} ${opt.group ?? ''}`.toLowerCase().includes(trimmedQuery)
      )
    : normalizedOptions;

  // Auto-flip determination
  const [effectiveDropUp, setEffectiveDropUp] = useState(dropUp);

  const hasToolbar = searchable || !!onRefresh;
  const maxDropdownHeight = compact || hasToolbar || collapsibleGroups ? 340 : 240;

  // Calculate dropdown position
  const updatePosition = React.useCallback(() => {
    const button = buttonRef.current;
    const dropdown = dropdownRef.current;
    if (!button || !dropdown) return;

    const rect = button.getBoundingClientRect();
    const menuWidth = Math.min(Math.max(rect.width, menuMinWidth), window.innerWidth - 16);
    dropdown.style.width = `${menuWidth}px`;
    const margin = 8;
    const gap = 4;
    const dropdownHeight = Math.min(dropdown.scrollHeight + 6, maxDropdownHeight);
    const dropdownWidth = Math.max(menuWidth, dropdown.offsetWidth);
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
      width: menuWidth,
      maxHeight: Math.min(maxDropdownHeight, shouldDropUp ? spaceAbove : spaceBelow),
    });
  }, [dropUp, menuAlign, menuMinWidth, maxDropdownHeight]);

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
  }, [isOpen, options, collapsedGroups, searchCollapsedGroups, searchQuery, updatePosition]);

  const setOpenState = React.useCallback(
    (next: boolean) => {
      setIsOpen((prev) => {
        if (prev !== next) {
          onOpenChange?.(next);
          if (!next) {
            setSearchQuery('');
          } else if (selectedOption?.group && collapsibleGroups) {
            // Ensure active selection's group is visible when opening
            setCollapsedGroups((curr) => {
              if (!curr.has(selectedOption.group!)) return curr;
              const updated = new Set(curr);
              updated.delete(selectedOption.group!);
              return updated;
            });
          }
        }
        return next;
      });
    },
    [collapsibleGroups, onOpenChange, selectedOption?.group]
  );

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      const isOutsideContainer = containerRef.current && !containerRef.current.contains(target);
      const isOutsideDropdown = dropdownRef.current && !dropdownRef.current.contains(target);

      if (isOutsideContainer && isOutsideDropdown) {
        setOpenState(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [setOpenState]);

  // Count how many items belong to each group in the filtered list
  const groupCounts = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const opt of filteredOptions) {
      if (opt.group) {
        counts.set(opt.group, (counts.get(opt.group) ?? 0) + 1);
      }
    }
    return counts;
  }, [filteredOptions]);

  const dropdown =
    isOpen &&
    createPortal(
      <div
        ref={dropdownRef}
        className={`fixed z-[9999] bg-white dark:bg-zinc-800 border-3 border-brutal-black shadow-brutal-overlay flex flex-col overflow-hidden animate-brutal-drop ${dropdownClassName}`}
        style={{
          top: dropdownPosition?.top,
          bottom: dropdownPosition?.bottom,
          left: dropdownPosition?.left ?? 0,
          width: dropdownPosition?.width ?? buttonRef.current?.getBoundingClientRect().width,
          maxHeight: dropdownPosition?.maxHeight ?? maxDropdownHeight,
          maxWidth: 'calc(100vw - 16px)',
          visibility: dropdownPosition ? undefined : 'hidden',
        }}
      >
        {hasToolbar && (
          <div className="flex items-center gap-1.5 px-2 py-1.5 border-b-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 shrink-0">
            {searchable && (
              <input
                ref={searchInputRef}
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') {
                    if (searchQuery) {
                      e.stopPropagation();
                      setSearchQuery('');
                    } else {
                      setOpenState(false);
                    }
                  }
                }}
                placeholder={searchPlaceholder ?? t('chatInput.searchModelsPlaceholder')}
                aria-label={searchPlaceholder ?? t('chatInput.searchModelsPlaceholder')}
                className="flex-1 min-w-0 bg-white dark:bg-zinc-800 border-2 border-brutal-black dark:border-zinc-600 px-2 py-1 font-mono text-xs text-brutal-black dark:text-white placeholder:text-neutral-400 focus:outline-none focus:border-brutal-blue"
              />
            )}
            {onRefresh && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  void onRefresh();
                }}
                disabled={refreshing}
                title={
                  refreshing
                    ? (refreshTitle ?? t('chatInput.refreshingModels'))
                    : (refreshTitle ?? t('chatInput.refreshModels'))
                }
                aria-label={
                  refreshing
                    ? (refreshTitle ?? t('chatInput.refreshingModels'))
                    : (refreshTitle ?? t('chatInput.refreshModels'))
                }
                className="w-7 h-7 shrink-0 inline-flex items-center justify-center border-2 border-brutal-black dark:border-zinc-600 bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-brutal-yellow dark:hover:bg-zinc-700 disabled:opacity-50 transition-colors"
              >
                <svg
                  className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`}
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M13.5 8A5.5 5.5 0 1 1 8 2.5c1.8 0 3.4.87 4.4 2.2"
                  />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 2v3h-3" />
                </svg>
              </button>
            )}
          </div>
        )}
        <div className="overflow-x-hidden overflow-y-auto scrollbar-thin flex-1 min-h-0">
          {filteredOptions.length === 0 && (
            <div className="px-3 py-3 text-xs font-mono text-neutral-500 dark:text-neutral-400 text-center">
              {emptySearchMessage ?? t('chatInput.noModelsMatch')}
            </div>
          )}
          {filteredOptions.map((option, optionIndex) => {
            const previousGroup =
              optionIndex > 0 ? filteredOptions[optionIndex - 1].group : undefined;
            const showGroupHeader = !!option.group && option.group !== previousGroup;
            const isGroupCollapsed =
              collapsibleGroups &&
              !!option.group &&
              (trimmedQuery
                ? searchCollapsedGroups.has(option.group)
                : collapsedGroups.has(option.group));
            const starAllowed =
              !!onToggleStar &&
              !option.disabled &&
              (canStarOption ? canStarOption(option.value) : true);
            const isStarred = starAllowed && !!starredValues?.has(option.value);

            return (
              <React.Fragment key={`${option.group ?? ''}:${option.value}`}>
                {showGroupHeader &&
                  (collapsibleGroups ? (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleGroupCollapse(option.group!);
                      }}
                      aria-expanded={!isGroupCollapsed}
                      className={`w-full flex items-center justify-between gap-2 font-mono font-bold uppercase tracking-widest text-neutral-600 dark:text-neutral-300 bg-neutral-100 dark:bg-zinc-900 hover:bg-neutral-200 dark:hover:bg-zinc-950 transition-colors cursor-pointer select-none ${
                        compact
                          ? 'px-2.5 py-1.5 text-[9px] border-b border-neutral-200 dark:border-zinc-700'
                          : 'px-3 py-1.5 text-[10px] border-b-2 border-neutral-200 dark:border-zinc-700'
                      }`}
                    >
                      <span className="flex items-center gap-1.5 min-w-0 truncate">
                        <span
                          className="inline-block w-2.5 text-center text-[9px]"
                          aria-hidden="true"
                        >
                          {isGroupCollapsed ? '▸' : '▾'}
                        </span>
                        <span className="truncate">{option.group}</span>
                      </span>
                      <span className="text-[9px] font-mono font-normal text-neutral-400 dark:text-neutral-500 shrink-0">
                        {groupCounts.get(option.group!) ?? 0}
                      </span>
                    </button>
                  ) : (
                    <div
                      className={`font-mono font-bold uppercase tracking-widest text-neutral-500 dark:text-neutral-400 bg-neutral-50 dark:bg-zinc-900 ${
                        compact
                          ? 'px-2.5 pt-2 pb-1 text-[9px] border-b border-neutral-200 dark:border-zinc-700'
                          : 'px-3 pt-2 pb-1 text-[10px] border-b-2 border-neutral-100 dark:border-zinc-700'
                      }`}
                    >
                      {option.group}
                    </div>
                  ))}
                {!isGroupCollapsed && (
                  <div
                    className={`group flex items-stretch w-full transition-colors last:border-0 ${
                      compact
                        ? 'border-b border-neutral-100 dark:border-zinc-700/60'
                        : 'border-b-2 border-neutral-100 dark:border-zinc-700'
                    } ${
                      option.disabled
                        ? 'bg-white dark:bg-zinc-800 text-neutral-400 dark:text-neutral-600 cursor-not-allowed'
                        : value === option.value
                          ? 'bg-brutal-black text-white dark:bg-brutal-yellow dark:text-brutal-black'
                          : 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-brutal-yellow dark:hover:bg-zinc-700'
                    }`}
                  >
                    <button
                      type="button"
                      disabled={option.disabled}
                      onClick={() => {
                        if (option.disabled) return;
                        onChange(option.value);
                        if (!keepOpenOnSelect?.(option.value)) {
                          setOpenState(false);
                        }
                      }}
                      title={compact ? option.label : undefined}
                      className={`flex-1 min-w-0 text-left ${
                        compact
                          ? 'px-2.5 py-1.5 font-mono text-[11px]'
                          : 'px-3 py-2 font-bold text-sm uppercase'
                      }`}
                    >
                      <span className="block truncate">{option.label}</span>
                      {option.hint && (
                        <span
                          className={`block normal-case font-normal text-[10px] leading-tight mt-0.5 ${
                            compact ? 'truncate' : ''
                          } ${
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
                    {starAllowed && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          void onToggleStar?.(option.value, !isStarred);
                        }}
                        title={
                          isStarred
                            ? (unstarLabel ?? t('chatInput.unstarModel'))
                            : (starLabel ?? t('chatInput.starModel'))
                        }
                        aria-label={
                          isStarred
                            ? (unstarLabel ?? t('chatInput.unstarModel'))
                            : (starLabel ?? t('chatInput.starModel'))
                        }
                        aria-pressed={isStarred}
                        className={`px-2.5 shrink-0 inline-flex items-center justify-center text-xs transition-opacity ${
                          isStarred
                            ? value === option.value
                              ? 'text-brutal-yellow dark:text-brutal-black opacity-100'
                              : 'text-amber-500 dark:text-amber-400 opacity-100'
                            : 'opacity-30 group-hover:opacity-90 hover:!opacity-100'
                        }`}
                      >
                        {isStarred ? '★' : '☆'}
                      </button>
                    )}
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
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
          if (!disabled) setOpenState(!isOpen);
        }}
        className={`w-full dark:text-white px-3 py-2 font-bold text-sm text-left flex items-center justify-between transition-all duration-200 focus:outline-none disabled:cursor-not-allowed disabled:opacity-40 ${
          variant === 'ghost'
            ? 'bg-transparent'
            : `bg-white dark:bg-zinc-800 border-3 border-brutal-black hover:bg-brutal-yellow dark:hover:bg-zinc-700 disabled:hover:bg-white dark:disabled:hover:bg-zinc-800 shadow-brutal-sm ${isOpen ? 'translate-x-[1px] translate-y-[1px]' : 'brutal-btn'}`
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
