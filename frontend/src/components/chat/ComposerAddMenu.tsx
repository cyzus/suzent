import React from 'react';
import { createPortal } from 'react-dom';
import {
  AtSymbolIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
  FolderIcon,
  PaperClipIcon,
  PlusIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { isImeComposing } from '../../lib/ime';
import { pickHostDirectory } from '../../lib/hostPathPicker';
import { readFolderHistory, rememberFolders, type RecentFolder } from '../../lib/folderHistory';

interface ComposerAddMenuProps {
  onAttachFiles: () => void;
  onSlashCommand: () => void;
  /** Slash commands only parse at the start of the message. */
  slashCommandDisabled?: boolean;
  onMention: () => void;
  /** Omit to hide the working-directory entry (the Focal Agent has none). */
  folders?: {
    activeVolumes: string[];
    onMount: (paths: string[]) => void;
    onRemoveVolume: (index: number) => void;
  };
  disabled?: boolean;
}

type MenuView = 'root' | 'folders';

interface MenuPosition {
  left: number;
  top?: number;
  bottom?: number;
  maxHeight: number;
}

const GAP = 8;
const EDGE = 8;

const hostPathOf = (volume: string): string =>
  volume.substring(0, volume.lastIndexOf(':')) || volume;

const baseNameOf = (path: string): string => path.split(/[\\/]/).filter(Boolean).pop() ?? path;

const ITEM_CLASS =
  'w-full flex items-center gap-2.5 px-3 py-2 text-left text-sm font-medium text-brutal-black dark:text-white hover:bg-brutal-yellow/40 dark:hover:bg-zinc-700 focus:outline-none focus-visible:bg-brutal-yellow/40 disabled:opacity-40 disabled:hover:bg-transparent disabled:cursor-not-allowed';
const SECTION_LABEL_CLASS =
  'px-3 pt-2 pb-1 text-[11px] font-bold text-neutral-500 dark:text-neutral-400';

export const ComposerAddMenu: React.FC<ComposerAddMenuProps> = ({
  onAttachFiles,
  onSlashCommand,
  slashCommandDisabled = false,
  onMention,
  folders,
  disabled = false,
}) => {
  const { t } = useI18n();
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [view, setView] = React.useState<MenuView>('root');
  const [history, setHistory] = React.useState<RecentFolder[]>([]);
  const containerRef = React.useRef<HTMLDivElement>(null);
  const menuRef = React.useRef<HTMLDivElement>(null);
  const [position, setPosition] = React.useState<MenuPosition | null>(null);

  const activeVolumes = folders?.activeVolumes ?? [];
  const activePaths = activeVolumes.map(hostPathOf);
  const folderSummary =
    activePaths.length === 0
      ? null
      : activePaths.length === 1
        ? baseNameOf(activePaths[0])
        : `${baseNameOf(activePaths[0])} +${activePaths.length - 1}`;
  const recentFolders = history.filter((item) => !activePaths.includes(item.path));

  const closeMenu = React.useCallback(() => {
    setMenuOpen(false);
    setView('root');
  }, []);

  React.useEffect(() => {
    if (!menuOpen) return;
    const onMouseDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!containerRef.current?.contains(target) && !menuRef.current?.contains(target)) {
        closeMenu();
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (isImeComposing(event) || event.key !== 'Escape') return;
      if (view === 'folders') setView('root');
      else closeMenu();
    };
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [closeMenu, menuOpen, view]);

  React.useEffect(() => {
    if (disabled) closeMenu();
  }, [closeMenu, disabled]);

  // Fixed and portaled so a tall menu never extends the page: on the start
  // page the composer sits mid-screen and a menu in the flow would push it up.
  React.useLayoutEffect(() => {
    if (!menuOpen) {
      setPosition(null);
      return;
    }
    const place = () => {
      // Anchor to the whole composer box so the menu never covers the text
      // the user is typing.
      const container = containerRef.current;
      const anchor = (container?.closest('form') ?? container)?.getBoundingClientRect();
      const menu = menuRef.current;
      if (!anchor || !menu) return;
      const height = menu.scrollHeight;
      const spaceAbove = anchor.top - GAP - EDGE;
      const spaceBelow = window.innerHeight - anchor.bottom - GAP - EDGE;
      // Upward even on the start page: opening down lands on the composer's
      // footer and shadow, which reads as a cluttered overlap.
      const up = spaceAbove >= height || spaceAbove >= spaceBelow;
      const width = menu.offsetWidth;
      setPosition({
        left: Math.max(EDGE, Math.min(anchor.left, window.innerWidth - width - EDGE)),
        top: up ? undefined : anchor.bottom + GAP,
        bottom: up ? window.innerHeight - anchor.top + GAP : undefined,
        maxHeight: Math.max(0, up ? spaceAbove : spaceBelow),
      });
    };
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [menuOpen, view, history, activeVolumes.length]);

  const openFolders = () => {
    setHistory(readFolderHistory());
    setView('folders');
  };

  const runAndClose = (action: () => void) => () => {
    closeMenu();
    action();
  };

  const mountFolders = (paths: string[]) => {
    if (!folders || paths.length === 0) return;
    setHistory((prev) => rememberFolders(paths, prev));
    folders.onMount(paths);
  };

  const pickFolder = async () => {
    try {
      const selected = await pickHostDirectory({ multiple: true });
      if (!selected) return;
      mountFolders(Array.isArray(selected) ? selected : [selected]);
    } catch (err) {
      console.error('Failed to pick a host folder', err);
    }
  };

  const rootView = (
    <>
      <button
        type="button"
        role="menuitem"
        className={ITEM_CLASS}
        onClick={runAndClose(onAttachFiles)}
      >
        <PaperClipIcon className="w-4 h-4 shrink-0" />
        <span className="min-w-0 flex-1 truncate">{t('chatInput.attachFilesShort')}</span>
      </button>
      {folders && (
        <button
          type="button"
          role="menuitem"
          aria-haspopup="menu"
          className={ITEM_CLASS}
          onClick={openFolders}
        >
          <FolderIcon className="w-4 h-4 shrink-0" />
          <span className="min-w-0 flex-1 truncate">{t('folderContext.context')}</span>
          {folderSummary && (
            <span className="max-w-[40%] truncate text-xs text-neutral-500 dark:text-neutral-400">
              {folderSummary}
            </span>
          )}
          <ChevronRightIcon className="w-3.5 h-3.5 shrink-0 stroke-2 text-neutral-400" />
        </button>
      )}
      <div className="my-1 border-t border-neutral-200 dark:border-zinc-700" />
      <button
        type="button"
        role="menuitem"
        className={ITEM_CLASS}
        disabled={slashCommandDisabled}
        title={slashCommandDisabled ? t('chatInput.slashCommandsNeedEmpty') : undefined}
        onClick={runAndClose(onSlashCommand)}
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="w-4 h-4 shrink-0"
        >
          <rect x="3.75" y="3.75" width="16.5" height="16.5" rx="2.25" />
          <path d="M14.25 7.5l-4.5 9" />
        </svg>
        <span className="min-w-0 flex-1 truncate">{t('chatInput.slashCommands')}</span>
      </button>
      <button type="button" role="menuitem" className={ITEM_CLASS} onClick={runAndClose(onMention)}>
        <AtSymbolIcon className="w-4 h-4 shrink-0" />
        <span className="min-w-0 flex-1 truncate">{t('chatInput.mentionMenuItem')}</span>
      </button>
    </>
  );

  const foldersView = folders && (
    <>
      <button
        type="button"
        className={`${ITEM_CLASS} font-bold`}
        onClick={() => setView('root')}
        aria-label={t('chatInput.addMenuBack')}
      >
        <ChevronLeftIcon className="w-4 h-4 shrink-0 stroke-2" />
        <span className="min-w-0 flex-1 truncate">{t('folderContext.context')}</span>
      </button>
      <div className="my-1 border-t border-neutral-200 dark:border-zinc-700" />
      <div className="max-h-72 overflow-y-auto">
        <div className={SECTION_LABEL_CLASS}>{t('folderContext.activeContexts')}</div>
        {activePaths.length === 0 ? (
          <div className="px-3 py-1.5 text-xs text-neutral-500 dark:text-neutral-400">
            {t('folderContext.noFoldersMounted')}
          </div>
        ) : (
          activePaths.map((path, index) => (
            <div key={`${path}-${index}`} className="flex items-center gap-2.5 pl-3 pr-1.5 py-1">
              <FolderIcon className="w-4 h-4 shrink-0 text-brutal-black dark:text-white" />
              <div className="min-w-0 flex-1" title={path}>
                <div className="truncate text-sm font-medium text-brutal-black dark:text-white">
                  {baseNameOf(path)}
                </div>
                <div className="truncate font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
                  {path}
                </div>
              </div>
              <button
                type="button"
                onClick={() => folders.onRemoveVolume(index)}
                className="w-7 h-7 shrink-0 flex items-center justify-center text-neutral-500 dark:text-neutral-400 hover:bg-brutal-red hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
                title={`${t('folderContext.remove')}: ${baseNameOf(path)}`}
                aria-label={`${t('folderContext.remove')}: ${baseNameOf(path)}`}
              >
                <XMarkIcon className="w-4 h-4" strokeWidth={2.5} />
              </button>
            </div>
          ))
        )}
        {recentFolders.length > 0 && (
          <>
            <div className={SECTION_LABEL_CLASS}>{t('folderContext.recentFolders')}</div>
            {recentFolders.map((item) => (
              <button
                key={item.path}
                type="button"
                role="menuitem"
                className={`${ITEM_CLASS} !py-1.5`}
                onClick={() => mountFolders([item.path])}
                title={item.path}
              >
                <ClockIcon className="w-4 h-4 shrink-0 text-neutral-400" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{baseNameOf(item.path)}</span>
                  <span className="block truncate font-mono text-[10px] font-normal text-neutral-500 dark:text-neutral-400">
                    {item.path}
                  </span>
                </span>
              </button>
            ))}
          </>
        )}
      </div>
      <div className="my-1 border-t border-neutral-200 dark:border-zinc-700" />
      <button
        type="button"
        role="menuitem"
        className={ITEM_CLASS}
        onClick={() => void pickFolder()}
      >
        <PlusIcon className="w-4 h-4 shrink-0 stroke-2" />
        <span className="min-w-0 flex-1 truncate">{t('folderContext.chooseDifferent')}</span>
      </button>
    </>
  );

  return (
    <div ref={containerRef} className="relative shrink-0 flex items-center gap-1 min-w-0">
      <button
        type="button"
        onClick={() => (menuOpen ? closeMenu() : setMenuOpen(true))}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        aria-label={t('chatInput.addMenu')}
        title={t('chatInput.addMenu')}
        className="w-9 h-9 shrink-0 flex items-center justify-center bg-transparent text-brutal-black dark:text-white hover:bg-neutral-200 dark:hover:bg-zinc-700 transition-colors disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
      >
        <PlusIcon
          className={`w-5 h-5 stroke-2 transition-transform duration-150 ${menuOpen ? 'rotate-45' : ''}`}
        />
      </button>
      {folderSummary && (
        <button
          type="button"
          onClick={() => {
            if (menuOpen && view === 'folders') {
              closeMenu();
              return;
            }
            openFolders();
            setMenuOpen(true);
          }}
          disabled={disabled}
          aria-haspopup="menu"
          title={activePaths.join('\n')}
          className="h-7 min-w-0 max-w-[10rem] flex items-center gap-1 px-1.5 text-xs font-medium text-neutral-600 dark:text-neutral-300 hover:bg-neutral-200 hover:text-brutal-black dark:hover:bg-zinc-700 dark:hover:text-white transition-colors disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
        >
          <FolderIcon className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">{folderSummary}</span>
        </button>
      )}

      {menuOpen &&
        createPortal(
          <div
            ref={menuRef}
            role="menu"
            style={{
              left: position?.left ?? 0,
              top: position ? position.top : 0,
              bottom: position?.bottom,
              maxHeight: position?.maxHeight,
              visibility: position ? 'visible' : 'hidden',
            }}
            className={`fixed z-[9999] ${view === 'folders' ? 'w-80' : 'w-60'} max-w-[calc(100vw-32px)] overflow-y-auto bg-white dark:bg-zinc-800 border-3 border-brutal-black shadow-brutal-overlay py-1.5 animate-brutal-drop`}
          >
            {view === 'folders' ? foldersView : rootView}
          </div>,
          document.body
        )}
    </div>
  );
};
