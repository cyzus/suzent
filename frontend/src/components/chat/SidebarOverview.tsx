import React from 'react';
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline';
import type { TabId } from './RightSidebar';
import { isImeComposing } from '../../lib/ime';

export interface OverviewSection {
  id: TabId;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  label: string;
  summary?: React.ReactNode;
  detail?: React.ReactNode;
  preview?: React.ReactNode;
  activityClass?: string;
  body: React.ReactNode;
  /** False when the section has no full panel to open. */
  fullView?: boolean;
}

interface SidebarOverviewProps {
  sections: OverviewSection[];
  expanded: ReadonlySet<TabId>;
  onToggle: (tabId: TabId) => void;
  onOpenFull: (tabId: TabId) => void;
  openFullLabel: string;
  emptyLabel: string;
}

export function SidebarOverview({
  sections,
  expanded,
  onToggle,
  onOpenFull,
  openFullLabel,
  emptyLabel,
}: SidebarOverviewProps): React.ReactElement {
  if (sections.length === 0) {
    return <p className="px-5 py-4 text-xs text-neutral-400 dark:text-neutral-500">{emptyLabel}</p>;
  }
  return (
    <div className="flex flex-col gap-0.5 px-2 py-3">
      {sections.map((section) => {
        const Icon = section.icon;
        const isExpanded = expanded.has(section.id);
        return (
          <section key={section.id}>
            <button
              type="button"
              onClick={() => onToggle(section.id)}
              aria-expanded={isExpanded}
              className="group w-full text-left rounded-md px-3 py-2.5 transition-colors hover:bg-neutral-100 dark:hover:bg-zinc-800"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="flex min-w-0 items-center gap-1.5 text-sm text-neutral-700 dark:text-neutral-200">
                  <Icon className="h-4 w-4 shrink-0 text-neutral-500 dark:text-neutral-400" />
                  <span className="truncate">{section.label}</span>
                  {section.activityClass && (
                    <span
                      className={`h-1.5 w-1.5 shrink-0 rounded-full ${section.activityClass}`}
                    />
                  )}
                  <ChevronRightIcon
                    className={`h-3 w-3 shrink-0 text-neutral-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                  />
                </span>
                {section.summary !== undefined && (
                  <span className="shrink-0 font-mono text-[11px] text-neutral-400 dark:text-neutral-500">
                    {section.summary}
                  </span>
                )}
              </div>
              {section.detail && <div className="pl-[1.375rem]">{section.detail}</div>}
              {!isExpanded && section.preview && (
                <div className="pl-[1.375rem]">{section.preview}</div>
              )}
            </button>
            {isExpanded && (
              <div className="pb-2 pl-[2.125rem] pr-3">
                {section.body}
                {section.fullView !== false && (
                  <button
                    type="button"
                    onClick={() => onOpenFull(section.id)}
                    className="mt-1.5 inline-flex items-center gap-0.5 text-xs text-neutral-400 hover:text-brutal-black dark:hover:text-white"
                  >
                    {openFullLabel}
                    <ChevronRightIcon className="h-3 w-3" />
                  </button>
                )}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

interface OverviewListProps<T> {
  items: T[];
  empty: string;
  getKey: (item: T) => React.Key;
  renderMarker: (item: T) => React.ReactNode;
  renderLabel: (item: T) => React.ReactNode;
  muted?: (item: T) => boolean;
  onSelect?: (item: T) => void;
  /** Let long labels run to a second line instead of cutting them at one. */
  wrap?: boolean;
}

export function OverviewList<T>({
  items,
  empty,
  getKey,
  renderMarker,
  renderLabel,
  muted,
  onSelect,
  wrap = false,
}: OverviewListProps<T>): React.ReactElement {
  if (items.length === 0) {
    return <p className="py-1 text-xs text-neutral-400 dark:text-neutral-500">{empty}</p>;
  }
  return (
    <ul className="space-y-0.5">
      {items.map((item) => {
        const content = (
          <>
            <span className="flex h-4 w-3 shrink-0 items-center justify-center">
              {renderMarker(item)}
            </span>
            <span
              className={`min-w-0 flex-1 ${wrap ? 'line-clamp-2 break-words' : 'truncate'} ${
                muted?.(item)
                  ? 'text-neutral-400 dark:text-neutral-500'
                  : 'text-neutral-600 dark:text-neutral-300'
              }`}
            >
              {renderLabel(item)}
            </span>
          </>
        );
        return (
          <li key={getKey(item)}>
            {onSelect ? (
              <button
                type="button"
                onClick={() => onSelect(item)}
                className={`flex w-full ${wrap ? 'items-start' : 'items-center'} gap-2 rounded px-1 py-1 text-left text-xs hover:bg-neutral-100 dark:hover:bg-zinc-800`}
              >
                {content}
              </button>
            ) : (
              <div
                className={`flex ${wrap ? 'items-start' : 'items-center'} gap-2 px-1 py-1 text-xs`}
              >
                {content}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function OverviewBackBar({
  label,
  onBack,
}: {
  label: string;
  onBack: () => void;
}): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onBack}
      className="flex shrink-0 items-center gap-1 px-3 py-2 text-xs text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white"
    >
      <ChevronLeftIcon className="h-3.5 w-3.5" />
      {label}
    </button>
  );
}

interface PlanProgressProps {
  statuses: string[];
  caption?: string;
}

export function PlanProgress({ statuses, caption }: PlanProgressProps): React.ReactElement {
  return (
    <>
      <div className="mt-2 flex gap-0.5">
        {statuses.map((status, index) => (
          <span
            key={index}
            className={`h-1.5 flex-1 rounded-full ${
              status === 'completed'
                ? 'bg-brutal-green'
                : status === 'in_progress'
                  ? 'bg-brutal-yellow'
                  : 'bg-neutral-300 dark:bg-zinc-600'
            }`}
          />
        ))}
      </div>
      {caption && (
        <div className="mt-1.5 truncate text-xs text-neutral-500 dark:text-neutral-400">
          {caption}
        </div>
      )}
    </>
  );
}

export interface HeaderMenuItem {
  id: TabId;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  label: string;
  activityClass?: string;
}

export function HeaderMoreMenu({
  items,
  label,
  icon: Icon,
  onSelect,
}: {
  items: HeaderMenuItem[];
  label: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  onSelect: (tabId: TabId) => void;
}): React.ReactElement {
  const [open, setOpen] = React.useState(false);
  const rootRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent): void => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent): void => {
      if (isImeComposing(event)) return;
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const hasActivity = items.some((item) => item.activityClass);
  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        title={label}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        className={`relative flex h-7 w-7 items-center justify-center rounded transition-colors ${
          open
            ? 'bg-neutral-200 text-brutal-black dark:bg-zinc-700 dark:text-white'
            : 'text-neutral-500 hover:bg-neutral-100 hover:text-brutal-black dark:text-neutral-400 dark:hover:bg-zinc-700 dark:hover:text-white'
        }`}
      >
        <Icon className="h-4 w-4" />
        {hasActivity && !open && (
          <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full border border-brutal-black bg-brutal-yellow" />
        )}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-1 min-w-[10rem] rounded-md border border-neutral-200 bg-white py-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-800"
        >
          {items.map((item) => {
            const ItemIcon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  onSelect(item.id);
                }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-zinc-700"
              >
                <ItemIcon className="h-4 w-4 shrink-0 text-neutral-500 dark:text-neutral-400" />
                <span className="flex-1">{item.label}</span>
                {item.activityClass && (
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${item.activityClass}`} />
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
