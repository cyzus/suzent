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

interface Props {
  component: A2UIComponent;
  onAction: (action: string, context: Record<string, unknown>) => void;
}

const GAP: Record<string, string> = { sm: 'gap-2', md: 'gap-4', lg: 'gap-6' };

export const A2UIRenderer: React.FC<Props> = ({ component, onAction }) => {
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

    case 'card': {
      const cardChildren = component.children ?? [];
      return (
        <div className="border-2 border-brutal-black bg-white dark:bg-zinc-900">
          {component.title && (
            <div className="bg-brutal-black text-white px-3 py-2 text-sm font-bold leading-snug">
              {component.title}
            </div>
          )}
          <div className="p-3 flex flex-col gap-3">
            {cardChildren.length > 0
              ? cardChildren.map((child, i) => (
                  <A2UIRenderer key={i} component={child} onAction={onAction} />
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
            <A2UIRenderer key={i} component={child} onAction={onAction} />
          ))}
        </div>
      );
    }

    case 'columns': {
      const children = component.children ?? [];
      const { ratios } = component;
      const styles: React.CSSProperties[] = ratios
        ? children.map((_, i) => ({ flex: ratios[i] ?? 1 }))
        : children.map(() => ({ flex: 1 }));
      return (
        <div className="flex gap-4">
          {children.map((child, i) => (
            <div key={i} style={styles[i]}>
              <A2UIRenderer component={child} onAction={onAction} />
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
