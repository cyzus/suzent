import React from 'react';
import type { A2UITable } from '../../../types/a2ui';
import { MarkdownRenderer } from '../../chat/MarkdownRenderer';

interface Props { component: A2UITable; }

export const A2UITableComponent: React.FC<Props> = ({ component }) => {
  const { columns = [], rows = [] } = component;
  return (
    <div className="overflow-x-auto border border-brutal-black scrollbar-thin scrollbar-track-neutral-200 dark:scrollbar-track-zinc-700 scrollbar-thumb-brutal-black">
      <table className="w-max min-w-full text-sm border-collapse">
        <thead>
          <tr className="bg-neutral-800 dark:bg-zinc-950 text-white">
            {columns.map(col => (
              <th
                key={col.key}
                style={col.width ? { width: col.width } : undefined}
                className="px-3 py-2 text-left font-bold text-xs uppercase tracking-wide border-r border-neutral-600 last:border-r-0 whitespace-nowrap"
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className="border-t border-neutral-200 dark:border-zinc-700 odd:bg-white even:bg-neutral-50 dark:odd:bg-zinc-900 dark:even:bg-zinc-800"
            >
              {columns.map(col => (
                <td
                  key={col.key}
                  className="px-3 py-2 border-r border-neutral-200 dark:border-zinc-700 last:border-r-0 text-brutal-black dark:text-neutral-200 whitespace-nowrap align-top"
                >
                  <span className="[&>p]:inline [&>p]:m-0">
                    <MarkdownRenderer content={String(row[col.key] ?? '')} />
                  </span>
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td
                colSpan={columns.length}
                className="px-3 py-4 text-center text-neutral-400 italic text-xs"
              >
                No data
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
};
