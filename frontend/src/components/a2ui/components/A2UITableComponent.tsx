import React from 'react';
import type { A2UITable } from '../../../types/a2ui';
import { MarkdownRenderer } from '../../chat/MarkdownRenderer';

interface Props { component: A2UITable; }

export const A2UITableComponent: React.FC<Props> = ({ component }) => {
  const { columns = [], rows = [] } = component;
  return (
    <div className="overflow-x-auto border-2 border-brutal-black">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-brutal-black text-white">
            {columns.map(col => (
              <th
                key={col.key}
                style={col.width ? { width: col.width } : undefined}
                className="px-3 py-2 text-left font-bold text-xs uppercase tracking-wide border-r border-neutral-600 last:border-r-0"
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
              className="border-t-2 border-brutal-black odd:bg-white even:bg-neutral-50 dark:odd:bg-zinc-900 dark:even:bg-zinc-800"
            >
              {columns.map(col => (
                <td
                  key={col.key}
                  className="px-3 py-2 border-r-2 border-brutal-black last:border-r-0 text-brutal-black dark:text-neutral-200 break-words"
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
