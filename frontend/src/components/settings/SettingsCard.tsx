import React from 'react';

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
}: SectionCardHeaderProps): React.ReactElement {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div className="flex items-start gap-4 min-w-0">
        {icon && (
          <div
            className={`w-12 h-12 border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-brutal-sm ${ICON_TONE[iconTone]}`}
          >
            {icon}
          </div>
        )}
        <div className="min-w-0">
          <h3 className="text-xl font-bold uppercase">{title}</h3>
          {description && (
            <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{description}</p>
          )}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
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
 * Heavier grid card with a colored header strip and bold drop shadow. Used by
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
      className={`bg-white dark:bg-zinc-800 dark:text-white border-3 border-brutal-black shadow-brutal-xl flex flex-col ${className}`}
    >
      <div className="p-4 bg-neutral-50 dark:bg-zinc-900 border-b-3 border-brutal-black flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="font-black uppercase text-lg tracking-wide truncate">{title}</div>
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
      className={`border-3 border-brutal-black bg-white dark:bg-zinc-800 dark:text-white shadow-brutal p-6 ${className}`}
    >
      {children}
    </div>
  );
}
