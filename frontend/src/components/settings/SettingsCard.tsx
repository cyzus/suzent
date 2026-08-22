import React from 'react';
import { BrutalButton } from '../BrutalButton';

type IconTone = 'blue' | 'green' | 'yellow' | 'black' | 'neutral';

const ICON_TONE: Record<IconTone, string> = {
  blue: 'bg-brutal-blue text-white',
  green: 'bg-brutal-green text-brutal-black',
  yellow: 'bg-brutal-yellow text-brutal-black',
  black: 'bg-brutal-black text-white',
  neutral: 'bg-neutral-400 text-white',
};

interface SectionCardHeaderProps {
  /** Heroicon-style svg path(s) rendered inside the icon tile. */
  icon?: React.ReactNode;
  iconTone?: IconTone;
  title: string;
  description?: React.ReactNode;
  /** Controls aligned to the right of the header (badge, toggle, button…). */
  actions?: React.ReactNode;
  className?: string;
}

/**
 * Standard header for a section card: optional icon tile + title + description,
 * with an optional right-aligned actions slot. Replaces the hand-rolled
 * `flex items-start gap-4` header blocks that drifted across tabs.
 */
export function SectionCardHeader({
  icon,
  iconTone = 'blue',
  title,
  description,
  actions,
  className = '',
}: SectionCardHeaderProps): React.ReactElement {
  return (
    <div className={`mb-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between ${className}`}>
      <div className="flex min-w-0 items-start gap-3">
        {icon && (
          <div
            className={`flex h-9 w-9 shrink-0 items-center justify-center border-2 border-brutal-black shadow-brutal-sm ${ICON_TONE[iconTone]}`}
          >
            {icon}
          </div>
        )}
        <div className="min-w-0">
          <h3 className="text-base font-black uppercase leading-tight sm:text-lg">{title}</h3>
          {description && (
            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-neutral-600 dark:text-neutral-400 sm:text-sm">{description}</p>
          )}
        </div>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">{actions}</div>}
    </div>
  );
}

interface GridCardProps {
  /** Main heading shown in the header strip. */
  title: React.ReactNode;
  /** Optional secondary line under the title. */
  subtitle?: React.ReactNode;
  /** When provided, shows a status dot (filled green when true, hollow when false). */
  active?: boolean;
  /** Custom controls aligned to the right of the header strip (overrides the status dot). */
  headerRight?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}

/**
 * Grid card with a colored header strip and the standard surface shadow. Used by
 * the equally-sized cards laid out in responsive grids (model roles, social
 * platforms) where each tile reads as a discrete unit.
 */
export function GridCard({
  title,
  subtitle,
  active,
  headerRight,
  className = '',
  children,
}: GridCardProps): React.ReactElement {
  return (
    <div
      className={`flex flex-col border-2 border-brutal-black bg-white shadow-brutal-sm dark:bg-zinc-800 dark:text-white ${className}`}
    >
      <div className="flex items-center justify-between gap-3 border-b-2 border-brutal-black bg-neutral-50 p-3 dark:bg-zinc-900">
        <div className="min-w-0">
          <div className="truncate text-base font-black uppercase tracking-wide">{title}</div>
          {subtitle && (
            <div className="text-xs text-neutral-500 dark:text-neutral-400 normal-case font-normal mt-0.5">
              {subtitle}
            </div>
          )}
        </div>
        {headerRight ?? (
          active !== undefined && (
            <div
              className={`w-4 h-4 rounded-full border-2 border-brutal-black flex-shrink-0 ${active ? 'bg-brutal-green' : 'bg-transparent'}`}
            />
          )
        )}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  );
}

interface SettingsCardProps {
  className?: string;
  children: React.ReactNode;
}

/**
 * Standard full-width section card. One border/shadow/padding convention shared
 * by every settings tab (matches the Usage/Appearance cards).
 */
export function SettingsCard({ className = '', children }: SettingsCardProps): React.ReactElement {
  return (
    <div
      className={`border-2 border-brutal-black bg-white p-3 shadow-brutal-sm dark:bg-zinc-800 dark:text-white sm:p-4 ${className}`}
    >
      {children}
    </div>
  );
}

interface SettingsPageProps {
  className?: string;
  children: React.ReactNode;
}

/** Consistent vertical rhythm and bottom breathing room for every settings tab. */
export function SettingsPage({ className = '', children }: SettingsPageProps): React.ReactElement {
  return <div className={`space-y-4 pb-3 ${className}`}>{children}</div>;
}

interface CollapsibleSettingsCardProps extends Omit<SectionCardHeaderProps, 'actions'> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  openLabel: string;
  closeLabel: string;
  children: React.ReactNode;
}

/** A compact summary row that reveals infrequently used creation forms. */
export function CollapsibleSettingsCard({
  open,
  onOpenChange,
  openLabel,
  closeLabel,
  children,
  ...headerProps
}: CollapsibleSettingsCardProps): React.ReactElement {
  return (
    <SettingsCard>
      <SectionCardHeader
        {...headerProps}
        className={open ? headerProps.className : '!mb-0'}
        actions={
          <BrutalButton
            type="button"
            variant={open ? 'default' : 'primary'}
            size="xs"
            aria-expanded={open}
            onClick={() => onOpenChange(!open)}
          >
            <span aria-hidden="true">{open ? '−' : '+'}</span>
            {open ? closeLabel : openLabel}
          </BrutalButton>
        }
      />
      {open && children}
    </SettingsCard>
  );
}

interface SettingsGridProps {
  density?: 'compact' | 'comfortable';
  className?: string;
  children: React.ReactNode;
}

/** Container-driven card grid that adapts to the settings pane, not the window. */
export function SettingsGrid({
  density = 'comfortable',
  className = '',
  children,
}: SettingsGridProps): React.ReactElement {
  const columns = density === 'compact'
    ? 'grid-cols-[repeat(auto-fit,minmax(min(100%,19rem),1fr))]'
    : 'grid-cols-[repeat(auto-fit,minmax(min(100%,23rem),1fr))]';

  return <div className={`grid items-start gap-4 ${columns} ${className}`}>{children}</div>;
}

type BadgeTone = 'green' | 'blue' | 'amber' | 'red' | 'neutral';

const BADGE_TONE: Record<BadgeTone, string> = {
  green: 'bg-brutal-green text-brutal-black',
  blue: 'bg-brutal-blue text-white',
  amber: 'bg-amber-400 text-brutal-black',
  red: 'bg-brutal-red text-white',
  neutral: 'bg-neutral-100 dark:bg-zinc-700 text-brutal-black dark:text-white',
};

interface BadgeProps {
  tone?: BadgeTone;
  icon?: React.ReactNode;
  title?: string;
  className?: string;
  children: React.ReactNode;
}

/**
 * Small status pill with the shared brutalist border. Replaces the hand-rolled
 * `<span className="px-2 py-1 border-2 border-brutal-black text-[10px]…">`
 * badges that were duplicated across the sync UI (connected, signed-in, lock).
 */
export function Badge({ tone = 'neutral', icon, title, className = '', children }: BadgeProps): React.ReactElement {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 px-2 py-1 border-2 border-brutal-black text-[10px] font-bold uppercase ${BADGE_TONE[tone]} ${className}`}
    >
      {icon}
      {children}
    </span>
  );
}

interface SettingsListActionProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: 'blue' | 'red' | 'neutral';
  active?: boolean;
}

/**
 * Standard soft action button for list items (edit, remove, test, etc).
 */
export function SettingsListAction({ tone = 'neutral', active, className = '', children, ...props }: SettingsListActionProps): React.ReactElement {
  let colorClasses = '';
  if (active) {
    colorClasses = 'bg-brutal-black text-white border-brutal-black dark:bg-white dark:text-black dark:border-white';
  } else if (tone === 'blue') {
    colorClasses = 'border-brutal-black/20 dark:border-white/10 bg-transparent text-neutral-500 dark:text-neutral-400 hover:border-brutal-blue hover:text-brutal-blue dark:hover:border-blue-400 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20';
  } else if (tone === 'red') {
    colorClasses = 'border-brutal-black/20 dark:border-white/10 bg-transparent text-neutral-500 dark:text-neutral-400 hover:border-brutal-red hover:text-brutal-red dark:hover:border-red-400 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20';
  } else {
    colorClasses = 'border-brutal-black/20 dark:border-white/10 bg-transparent text-neutral-500 dark:text-neutral-400 hover:border-brutal-black hover:text-brutal-black dark:hover:border-white dark:hover:text-white hover:bg-neutral-100 dark:hover:bg-zinc-800';
  }

  return (
    <button
      className={`px-3 py-1 border text-[11px] font-bold uppercase transition-colors disabled:opacity-50 rounded-sm ${colorClasses} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

interface SettingsListItemProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * Common wrapper for list items in settings (MCP servers, Cron Jobs).
 * Applies the standard surface border, shadow, and subtle textured background.
 */
export function SettingsListItem({ children, className = '' }: SettingsListItemProps): React.ReactElement {
  return (
    <div className={`group relative overflow-hidden border-2 border-brutal-black bg-neutral-50 shadow-brutal-sm dark:bg-zinc-900 ${className}`}>
      <div className="absolute inset-0 opacity-[0.03] bg-[radial-gradient(#000_2px,transparent_2px)] [background-size:16px_16px] pointer-events-none" />
      <div className="relative z-10 w-full h-full flex flex-col">
        {children}
      </div>
    </div>
  );
}
