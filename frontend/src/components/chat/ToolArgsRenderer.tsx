import React from 'react';
import { useI18n } from '../../i18n';

/**
 * General-purpose tool-argument renderer.
 *
 * Replaces the raw `JSON.stringify(...)` `<pre>` dump that every tool without a
 * dedicated ArgsRenderer used to fall back to. Renders the parsed args as a
 * compact label/value field list: scalar values inline, longer strings and
 * nested objects/arrays on their own line. A heuristically-chosen "primary"
 * field (the search query, shell command, file path, …) is promoted to a
 * prominent chip at the top so the most important input reads at a glance.
 *
 * Falls back to a `<pre>` of the raw text when args aren't a parseable object
 * (so we never lose information the model sent).
 */

interface ToolArgsRendererProps {
  /** Parsed object form of the args, or null if it wasn't a JSON object. */
  parsedArgs: Record<string, unknown> | null;
  /** Raw args string, used as a fallback when parsing produced no object. */
  raw?: string;
}

// Per-tool hint for which field is the headline input, tried before the
// generic key list below. Keeps the chip correct even when a tool also has,
// say, a `query` alongside its real primary field.
const PRIMARY_BY_HINT: Array<{ test: RegExp; keys: string[] }> = [
  { test: /search/, keys: ['query', 'q'] },
  { test: /bash|shell|exec|process/, keys: ['command', 'cmd'] },
  { test: /fetch|browse|webpage|url/, keys: ['url'] },
];

// Generic primary-field preference order, used when no per-tool hint matches.
const PRIMARY_KEYS = ['query', 'q', 'command', 'cmd', 'url', 'path', 'file_path', 'prompt', 'content', 'text'];

function pickPrimaryKey(
  args: Record<string, unknown>,
  toolName?: string,
): string | null {
  const hint = toolName ? PRIMARY_BY_HINT.find(h => h.test.test(toolName)) : undefined;
  const order = hint ? [...hint.keys, ...PRIMARY_KEYS] : PRIMARY_KEYS;
  for (const key of order) {
    if (typeof args[key] === 'string' && (args[key] as string).trim()) {
      return key;
    }
  }
  return null;
}

function humanizeKey(key: string): string {
  return key.replace(/[_-]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function isEmptyValue(value: unknown): boolean {
  return (
    value === null ||
    value === undefined ||
    value === '' ||
    (Array.isArray(value) && value.length === 0)
  );
}

function formatScalar(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return String(value);
}

/** Scalars (string/number/boolean) render inline; everything else gets a block. */
function isScalar(value: unknown): boolean {
  return (
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  );
}

const Field: React.FC<{ name: string; value: unknown }> = ({ name, value }) => {
  const label = (
    <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-neutral-400 dark:text-neutral-500 shrink-0">
      {humanizeKey(name)}
    </span>
  );

  if (isScalar(value)) {
    const text = formatScalar(value);
    const multiline = text.length > 80 || text.includes('\n');
    if (multiline) {
      return (
        <div className="flex flex-col gap-1 min-w-0">
          {label}
          <pre className="font-mono text-[12px] leading-5 text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap break-words m-0">
            {text}
          </pre>
        </div>
      );
    }
    return (
      <div className="flex items-baseline gap-2 min-w-0">
        {label}
        <span className="font-mono text-[12px] text-neutral-700 dark:text-neutral-300 break-words min-w-0">
          {text}
        </span>
      </div>
    );
  }

  // Objects / arrays: pretty-printed block.
  return (
    <div className="flex flex-col gap-1 min-w-0">
      {label}
      <pre className="font-mono text-[12px] leading-5 text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap break-words m-0">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
};

export const ToolArgsRenderer: React.FC<ToolArgsRendererProps & { toolName?: string }> = ({
  parsedArgs,
  raw,
  toolName,
}) => {
  const { t } = useI18n();
  // Not a JSON object (a bare string/number/array, or unparseable): show raw.
  if (!parsedArgs) {
    return (
      <div className="max-h-[220px] overflow-y-auto scrollbar-thin w-full rounded-sm bg-neutral-50/70 dark:bg-zinc-800/40 px-2.5 py-2" style={{ overflowX: 'hidden' }}>
        <pre className="tool-call-pre font-mono text-[12px] leading-5 text-neutral-600 dark:text-neutral-300 w-full m-0">
          {raw ?? ''}
        </pre>
      </div>
    );
  }

  const primaryKey = pickPrimaryKey(parsedArgs, toolName);
  const restKeys = Object.keys(parsedArgs).filter(
    k => k !== primaryKey && !isEmptyValue(parsedArgs[k]),
  );

  const primaryValue = primaryKey ? (parsedArgs[primaryKey] as string) : null;

  return (
    <div className="w-full font-brutal bg-neutral-50/70 dark:bg-zinc-800/40 px-2.5 py-2 space-y-2 min-w-0 overflow-hidden">
      {primaryValue !== null && (
        <div className="flex items-start gap-2 bg-white dark:bg-zinc-800 border-2 border-brutal-black dark:border-zinc-500 px-2.5 py-1.5 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] min-w-0">
          <svg className="w-3.5 h-3.5 mt-0.5 stroke-[2.5] shrink-0 text-brutal-black dark:text-neutral-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <span className="font-mono text-[12.5px] font-bold text-brutal-black dark:text-neutral-100 break-words min-w-0 leading-snug">
            {primaryValue}
          </span>
        </div>
      )}

      {restKeys.length > 0 && (
        <div className="space-y-1.5">
          {restKeys.map(key => (
            <Field key={key} name={key} value={parsedArgs[key]} />
          ))}
        </div>
      )}

      {primaryValue === null && restKeys.length === 0 && (
        <span className="text-[11px] font-mono text-neutral-400 dark:text-neutral-500 italic">
          {t('toolCallBlock.noArguments')}
        </span>
      )}
    </div>
  );
};
