import React, { useLayoutEffect, useRef, useState } from 'react';
import { FullscreenButton } from './FullscreenButton';

interface ExpandedSurfaceCardProps {
  title: string;
  dockedToolbar?: boolean;
  controlAnchor?: DOMRect;
  navigation?: React.ReactNode;
  subtitle?: string;
  actions?: React.ReactNode;
  shrinkDisabled?: boolean;
  onShrink: () => void;
  children: React.ReactNode;
}

export function ExpandedSurfaceCard({
  title,
  dockedToolbar = false,
  controlAnchor,
  navigation,
  subtitle,
  actions,
  shrinkDisabled,
  onShrink,
  children,
}: ExpandedSurfaceCardProps): React.ReactElement {
  const header = useRef<HTMLElement>(null);
  const [padding, setPadding] = useState<React.CSSProperties>();
  useLayoutEffect(() => {
    if (!dockedToolbar || !controlAnchor || !header.current) return;
    const rect = header.current.getBoundingClientRect();
    setPadding({
      paddingRight: Math.max(12, rect.right - controlAnchor.right),
      paddingTop: Math.max(8, controlAnchor.top - rect.top),
    });
    // After a resize, return to the normal edge inset instead of keeping stale coordinates.
    const reset = () => setPadding(undefined);
    window.addEventListener('resize', reset);
    return () => window.removeEventListener('resize', reset);
  }, [dockedToolbar, controlAnchor]);
  const toolbar = (
    <header
      ref={header}
      style={padding}
      className="flex min-w-0 shrink-0 items-start gap-3 border-b-3 border-brutal-black bg-white px-3 py-2 dark:bg-zinc-800"
    >
      <div className="min-w-0 min-h-8 flex-1 flex flex-col justify-center">
        {navigation ?? (
          <h2
            title={title}
            className="truncate font-mono text-xs font-bold uppercase tracking-widest text-brutal-black dark:text-white"
          >
            {title}
          </h2>
        )}
        {subtitle && (
          <p
            title={subtitle}
            className="mt-1 truncate font-mono text-[10px] text-neutral-500 dark:text-neutral-400"
          >
            {subtitle}
          </p>
        )}
      </div>
      {actions}
      <FullscreenButton expanded onClick={onShrink} disabled={shrinkDisabled} />
    </header>
  );
  const cardClass =
    'flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden border-2 border-brutal-black bg-white dark:bg-zinc-900';
  const surroundClass = 'flex min-h-0 flex-1 bg-neutral-100 p-2 sm:p-4 dark:bg-zinc-950';
  if (dockedToolbar)
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        {toolbar}
        <div className={surroundClass}>
          <article className={cardClass}>{children}</article>
        </div>
      </div>
    );
  return (
    <div className={surroundClass}>
      <article className={cardClass}>
        {toolbar}
        {children}
      </article>
    </div>
  );
}
