import React, { useEffect, useState, useRef, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { CheckIcon, ClockIcon, FolderIcon, PlusIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { pickHostDirectory } from '../../lib/hostPathPicker';
import { useI18n } from '../../i18n';

interface RecentFolder {
  path: string;
  timestamp: number;
}

interface FolderContextPickerProps {
  onMount: (paths: string[]) => void;
  activeVolumes?: string[];
  /** Host paths to show as active, in place of parsing `activeVolumes`. */
  activeFolders?: string[];
  onRemoveVolume?: (index: number) => void;
  /** Folders already used in the current project, listed above recent ones. */
  projectFolders?: string[];
  /** Pick one folder at a time (e.g. a working directory) instead of mounting several. */
  multiple?: boolean;
  activeTitle?: string;
  emptyActiveText?: string;
  disabled?: boolean;
  dropUp?: boolean;
  buttonLabel?: string;
  /**
   * Replaces the toolbar look of the trigger: it then shows only its icon and
   * label, styled by this class.
   */
  buttonClassName?: string;
  buttonIcon?: typeof FolderIcon;
}

const HISTORY_KEY = 'suzent_folder_history';
const MAX_HISTORY = 5;

export const FolderContextPicker: React.FC<FolderContextPickerProps> = ({
  onMount,
  activeVolumes = [],
  activeFolders,
  onRemoveVolume,
  projectFolders = [],
  multiple = true,
  activeTitle,
  emptyActiveText,
  disabled = false,
  dropUp = true,
  buttonLabel,
  buttonClassName,
  buttonIcon: ButtonIcon = FolderIcon,
}) => {
  const { t } = useI18n();
  const [history, setHistory] = useState<RecentFolder[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState<{
    top: number;
    left: number;
    width: number;
    maxHeight: number;
  } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(HISTORY_KEY);
      if (saved) {
        setHistory(JSON.parse(saved));
      }
    } catch (e) {
      console.error('Failed to load folder history', e);
    }
  }, []);

  const addToHistory = (paths: string[]) => {
    const now = Date.now();
    const newItems = paths.map((p) => ({ path: p, timestamp: now }));

    setHistory((prev) => {
      const combined = [...newItems, ...prev];
      const unique = combined.filter(
        (item, index, self) => index === self.findIndex((t) => t.path === item.path)
      );
      const trimmed = unique.slice(0, MAX_HISTORY);

      localStorage.setItem(HISTORY_KEY, JSON.stringify(trimmed));
      return trimmed;
    });
  };

  const handleNativePick = async () => {
    try {
      const selected = await pickHostDirectory({ multiple });

      if (!selected) return;
      const paths = Array.isArray(selected) ? selected : [selected];
      if (paths.length === 0) return;

      addToHistory(paths);
      onMount(paths);
      setIsOpen(false);
    } catch (err) {
      console.error('Failed to pick a host folder', err);
    }
  };

  const activePaths =
    activeFolders ?? activeVolumes.map((volume) => volume.substring(0, volume.lastIndexOf(':')));

  const handleRecentClick = (path: string) => {
    const existingIndex = activePaths.indexOf(path);
    if (existingIndex !== -1) {
      onRemoveVolume?.(existingIndex);
    } else {
      addToHistory([path]);
      onMount([path]);
      if (!multiple) setIsOpen(false);
    }
  };

  // Calculate active count for badge
  const activeCount = activePaths.length;

  const getDynamicLabel = (): string | null => {
    if (!activePaths.length) return null;
    return activePaths[0].split(/[\\/]/).filter(Boolean).pop() ?? activePaths[0];
  };

  const dynamicLabel = getDynamicLabel();
  const inactiveProjectFolders = projectFolders.filter((path) => !activePaths.includes(path));
  const inactiveHistory = history.filter(
    (item) => !activePaths.includes(item.path) && !projectFolders.includes(item.path)
  );

  const [effectiveDropUp, setEffectiveDropUp] = useState(dropUp);

  // Calculate dropdown position
  const updatePosition = React.useCallback(() => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      // Clamp the width too: on a viewport narrower than the panel, a fixed
      // 336 would make the `left` clamp below unsatisfiable.
      const width = Math.min(336, Math.max(0, window.innerWidth - 32));
      const height = 420;
      const left = Math.max(16, Math.min(rect.left, window.innerWidth - width - 16));

      const spaceAbove = rect.top;
      const spaceBelow = window.innerHeight - rect.bottom;

      let shouldDropUp = dropUp;

      // Auto-flip logic
      if (dropUp && spaceAbove < height && spaceBelow > height) {
        shouldDropUp = false;
      } else if (!dropUp && spaceBelow < height && spaceAbove > height) {
        shouldDropUp = true;
      } else if (spaceAbove < height && spaceBelow < height) {
        // Neither side fits the full panel (e.g. opened from a centered
        // dialog): use the roomier side and shrink the panel to fit it.
        shouldDropUp = spaceAbove > spaceBelow;
      }

      setEffectiveDropUp(shouldDropUp);
      const maxHeight = Math.min(height, (shouldDropUp ? spaceAbove : spaceBelow) - 16);

      if (shouldDropUp) {
        setDropdownPosition({
          top: rect.top - 4,
          left,
          width,
          maxHeight,
        });
      } else {
        setDropdownPosition({
          top: rect.bottom + 4,
          left,
          width,
          maxHeight,
        });
      }
    }
  }, [dropUp]);

  useLayoutEffect(() => {
    if (isOpen) {
      updatePosition();

      window.addEventListener('resize', updatePosition);
      window.addEventListener('scroll', updatePosition, true);

      return () => {
        window.removeEventListener('resize', updatePosition);
        window.removeEventListener('scroll', updatePosition, true);
      };
    }
  }, [isOpen, updatePosition]);

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

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const renderFolderList = (paths: string[], Icon: typeof FolderIcon) => (
    <div className="border-y border-neutral-200 dark:border-zinc-700 divide-y divide-neutral-200 dark:divide-zinc-700">
      {paths.map((path) => (
        <button
          type="button"
          key={path}
          onClick={() => handleRecentClick(path)}
          className="group w-full text-left px-1 py-2 flex items-center gap-2.5 text-xs text-brutal-black dark:text-white transition-colors hover:bg-brutal-yellow/40 dark:hover:bg-zinc-700 focus:outline-none focus-visible:bg-brutal-yellow/40"
        >
          <Icon className="w-4 h-4 text-neutral-400 group-hover:text-brutal-black dark:group-hover:text-white shrink-0" />
          <div className="min-w-0 flex-1">
            <div className="truncate font-bold">{path.split(/[/\\]/).pop()}</div>
            <div
              className="truncate text-[10px] font-mono text-neutral-500 dark:text-neutral-400"
              title={path}
            >
              {path}
            </div>
          </div>
          <PlusIcon className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
        </button>
      ))}
    </div>
  );

  const dropdown =
    isOpen &&
    dropdownPosition &&
    createPortal(
      <div
        ref={dropdownRef}
        role="dialog"
        aria-label={t('folderContext.context')}
        className="fixed z-[9999] bg-white dark:bg-zinc-800 border-2 border-brutal-black shadow-[3px_3px_0_0_#000] focus:outline-none flex flex-col max-h-[420px] overflow-y-auto scrollbar-thin animate-brutal-drop"
        style={{
          top: effectiveDropUp ? 'auto' : dropdownPosition.top,
          bottom: effectiveDropUp ? window.innerHeight - dropdownPosition.top : 'auto',
          left: dropdownPosition.left,
          // `left` above is clamped against exactly this width, so the width
          // has to be applied for that clamp to mean anything. Without it the
          // panel sizes to its content and stretches to fit the longest host
          // path, running off the right edge. A definite width is also what
          // lets the `truncate` on those paths take effect.
          width: dropdownPosition.width,
          maxHeight: dropdownPosition.maxHeight,
        }}
      >
        <div className="px-3 py-2.5 border-b-2 border-brutal-black bg-neutral-100 dark:bg-zinc-900">
          <div className="flex justify-between items-center gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <FolderIcon className="w-4 h-4 shrink-0 text-brutal-black dark:text-white" />
              <span className="text-xs font-black uppercase tracking-wide text-brutal-black dark:text-white">
                {activeTitle ?? t('folderContext.activeContexts')}
              </span>
            </div>
            <span
              className={`min-w-6 h-6 px-1.5 inline-flex items-center justify-center border-2 border-brutal-black text-[10px] font-black ${activeCount > 0 ? 'bg-brutal-green text-brutal-black' : 'bg-white dark:bg-zinc-800 dark:text-white'}`}
            >
              {activeCount}
            </span>
          </div>

          {activeCount === 0 ? (
            <div className="text-xs text-neutral-500 dark:text-neutral-400 py-2">
              {emptyActiveText ?? t('folderContext.noFoldersMounted')}
            </div>
          ) : (
            <div className="mt-2 border-2 border-brutal-black bg-white dark:bg-zinc-800 divide-y-2 divide-brutal-black">
              {activePaths.map((hostPath, idx) => {
                const folderName = hostPath.split(/[/\\]/).pop() || hostPath;

                return (
                  <div key={`${hostPath}-${idx}`} className="flex items-center gap-2 px-2.5 py-2">
                    <div className="w-6 h-6 bg-brutal-green border-2 border-brutal-black flex items-center justify-center shrink-0">
                      <CheckIcon className="w-3.5 h-3.5 text-brutal-black" strokeWidth={3} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-bold truncate text-brutal-black dark:text-white">
                        {folderName}
                      </div>
                      <div
                        className="text-[10px] text-neutral-500 dark:text-neutral-400 truncate font-mono"
                        title={hostPath}
                      >
                        {hostPath}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => onRemoveVolume?.(idx)}
                      className="w-7 h-7 shrink-0 flex items-center justify-center border-0 text-neutral-500 dark:text-neutral-400 hover:bg-brutal-red hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
                      title={`${t('folderContext.remove')}: ${folderName}`}
                      aria-label={`${t('folderContext.remove')}: ${folderName}`}
                    >
                      <XMarkIcon className="w-4 h-4" strokeWidth={2.5} />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {inactiveProjectFolders.length > 0 && (
          <div className="px-3 py-2.5 border-b-2 border-brutal-black bg-white dark:bg-zinc-800">
            <div className="text-[10px] font-black uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mb-1.5">
              {t('folderContext.projectFolders')}
            </div>
            {renderFolderList(inactiveProjectFolders, FolderIcon)}
          </div>
        )}

        <div className="px-3 py-2.5 border-b-2 border-brutal-black bg-white dark:bg-zinc-800">
          <div className="text-[10px] font-black uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mb-1.5">
            {t('folderContext.recentFolders')}
          </div>
          {inactiveHistory.length === 0 ? (
            <div className="text-xs text-neutral-500 dark:text-neutral-400 py-1">
              {history.length > 0
                ? t('folderContext.allRecentFoldersMounted')
                : t('folderContext.noRecentFolders')}
            </div>
          ) : (
            renderFolderList(
              inactiveHistory.map((item) => item.path),
              ClockIcon
            )
          )}
        </div>

        <div className="p-2 bg-neutral-100 dark:bg-zinc-900">
          <button
            type="button"
            onClick={handleNativePick}
            className="w-full flex items-center justify-center gap-2 px-3 py-2.5 text-xs font-black uppercase transition-colors border-2 border-brutal-black bg-brutal-yellow text-brutal-black hover:bg-yellow-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
          >
            <PlusIcon className="w-4 h-4" />
            {t('folderContext.chooseDifferent')}
          </button>
        </div>
      </div>,
      document.body
    );

  return (
    <div className="relative min-w-0 shrink text-left" ref={containerRef}>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        className={
          buttonClassName ??
          `
                    flex items-center gap-1.5 px-2 h-9 w-full min-w-0 border-0 shadow-none transition-colors disabled:opacity-50 disabled:cursor-not-allowed group text-xs font-bold uppercase focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue
                    bg-transparent text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700
                `
        }
      >
        <ButtonIcon className="w-4 h-4 shrink-0" />
        {buttonClassName ? (
          <span className="truncate min-w-0">{buttonLabel}</span>
        ) : (
          <>
            <span className="hidden sm:inline truncate min-w-0">
              {buttonLabel || dynamicLabel || t('folderContext.context')}
            </span>
            {activeCount > 1 && (
              <span className="min-w-5 h-5 px-1 inline-flex items-center justify-center bg-white/80 border border-brutal-black text-[9px] leading-none">
                {activeCount}
              </span>
            )}
            <svg
              className={`w-3.5 h-3.5 shrink-0 text-neutral-400 dark:text-neutral-500 transition-transform duration-200 ${isOpen ? (effectiveDropUp ? 'rotate-0' : 'rotate-180') : effectiveDropUp ? 'rotate-180' : 'rotate-0'}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2}
              aria-hidden="true"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </>
        )}
      </button>
      {dropdown}
    </div>
  );
};
