import React from 'react';
import type { A2UIList } from '../../../types/a2ui';
import { MarkdownRenderer } from '../../chat/MarkdownRenderer';

interface Props { component: A2UIList; }

export const A2UIListComponent: React.FC<Props> = ({ component }) => {
  const Tag = component.ordered ? 'ol' : 'ul';
  return (
    <Tag className={`text-sm text-brutal-black dark:text-neutral-200 pl-5 space-y-1 ${component.ordered ? 'list-decimal' : 'list-disc'}`}>
      {(component.items ?? []).map((item, i) => (
        <li key={i}>
          <span className="[&>p]:inline [&>p]:m-0">
            <MarkdownRenderer content={item} />
          </span>
        </li>
      ))}
    </Tag>
  );
};
