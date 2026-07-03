/**
 * A2UIRenderer — recursively renders A2UIComponent trees.
 *
 * Dispatches on component.type and passes onAction down to interactive leaf nodes.
 * Container components (Card, Stack, Columns) recursively render their children.
 */

import React from 'react';
import type { A2UIComponent } from '../../types/a2ui';
import { A2UITextComponent }     from './components/A2UITextComponent';
import { A2UIBadgeComponent }    from './components/A2UIBadgeComponent';
import { A2UIButtonComponent }   from './components/A2UIButtonComponent';
import { A2UITableComponent }    from './components/A2UITableComponent';
import { A2UIFormComponent }     from './components/A2UIFormComponent';
import { A2UIListComponent }     from './components/A2UIListComponent';
import { A2UIProgressComponent } from './components/A2UIProgressComponent';
import { A2UIDividerComponent }  from './components/A2UIDividerComponent';
import { A2UIHtmlComponent }     from './components/A2UIHtmlComponent';

interface Props {
  component: A2UIComponent;
  onAction: (action: string, context: Record<string, unknown>) => void;
  /** Nesting depth of container components. Drives progressively lighter
   *  visual weight so nested cards don't stack identical heavy black bars. */
  depth?: number;
}

const GAP: Record<string, string> = { sm: 'gap-2', md: 'gap-4', lg: 'gap-6' };

// Minimum readable width for a single column before it wraps to its own row.
const COLUMN_MIN_WIDTH_PX = 260;

interface LegacyStackHeaderVertical {
  type: 'stackHeaderVertical';
  children?: A2UIComponent[];
  gap?: 'sm' | 'md' | 'lg';
}

export const A2UIRenderer: React.FC<Props> = ({ component, onAction, depth = 0 }) => {
  const rawType = (component as { type?: string }).type;

  if (rawType === 'stackHeaderVertical') {
    const legacy = component as unknown as LegacyStackHeaderVertical;
    const gapCls = GAP[legacy.gap ?? 'md'] ?? GAP.md;
    const stackChildren = legacy.children ?? [];
    return (
      <div className={`flex flex-col ${gapCls}`}>
        {stackChildren.map((child: A2UIComponent, i: number) => (
          <A2UIRenderer key={i} component={child} onAction={onAction} depth={depth} />
        ))}
      </div>
    );
  }

  switch (component.type) {
    case 'text':
      return <A2UITextComponent component={component} />;

    case 'badge':
      return <A2UIBadgeComponent component={component} />;

    case 'button':
      return <A2UIButtonComponent component={component} onAction={onAction} />;

    case 'table':
      return <A2UITableComponent component={component} />;

    case 'form':
      return <A2UIFormComponent component={component} onAction={onAction} />;

    case 'list':
      return <A2UIListComponent component={component} />;

    case 'progress':
      return <A2UIProgressComponent component={component} />;

    case 'divider':
      return <A2UIDividerComponent />;

    case 'html':
      return <A2UIHtmlComponent component={component} onAction={onAction} />;

    case 'card': {
      const cardChildren = component.children ?? [];
      // Top-level card keeps the full brutalist weight; nested cards step down
      // to a lighter frame + soft header so nesting reads as hierarchy instead
      // of a stack of identical black bars.
      const isTop = depth === 0;
      const frameCls = isTop
        ? 'border-2 border-brutal-black bg-white dark:bg-zinc-900'
        : 'border border-neutral-300 dark:border-zinc-700 bg-white dark:bg-zinc-900';
      const headerCls = isTop
        ? 'bg-brutal-black text-white px-3 py-2 text-sm font-bold leading-snug'
        : 'border-b border-neutral-200 dark:border-zinc-700 bg-neutral-50 dark:bg-zinc-800 text-brutal-black dark:text-neutral-100 px-3 py-1.5 text-xs font-bold uppercase tracking-wide leading-snug';
      return (
        <div className={frameCls}>
          {component.title && <div className={headerCls}>{component.title}</div>}
          <div className="p-3 flex flex-col gap-3">
            {cardChildren.length > 0
              ? cardChildren.map((child, i) => (
                  <A2UIRenderer key={i} component={child} onAction={onAction} depth={depth + 1} />
                ))
              : (
                <span className="text-xs text-neutral-400 dark:text-neutral-500 italic">—</span>
              )
            }
          </div>
        </div>
      );
    }

    case 'stack': {
      const gapCls = GAP[component.gap ?? 'md'] ?? GAP.md;
      const stackChildren = component.children ?? [];
      return (
        <div className={`flex flex-col ${gapCls}`}>
          {stackChildren.map((child, i) => (
            <A2UIRenderer key={i} component={child} onAction={onAction} depth={depth} />
          ))}
        </div>
      );
    }

    case 'columns': {
      const children = component.children ?? [];
      const { ratios } = component;
      // Each column keeps a minimum readable width and grows by its ratio.
      // When the columns can no longer sit side-by-side at that minimum, they
      // wrap to stacked rows (flex-wrap) — so a narrow canvas shows one column
      // per row instead of crushing everything into unreadable slivers.
      const styles: React.CSSProperties[] = children.map((_, i) => ({
        flexGrow: ratios ? (ratios[i] ?? 1) : 1,
        flexShrink: 1,
        flexBasis: `${COLUMN_MIN_WIDTH_PX}px`,
        minWidth: `min(${COLUMN_MIN_WIDTH_PX}px, 100%)`,
      }));
      return (
        <div className="flex flex-wrap gap-4">
          {children.map((child, i) => (
            <div key={i} style={styles[i]}>
              <A2UIRenderer component={child} onAction={onAction} depth={depth} />
            </div>
          ))}
        </div>
      );
    }

    default:
      return (
        <div className="text-xs text-red-500 border border-red-300 px-2 py-1">
          Unknown component type: {(component as A2UIComponent & { type: string }).type}
        </div>
      );
  }
};
