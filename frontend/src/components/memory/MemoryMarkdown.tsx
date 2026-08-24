/**
 * Markdown rendering for memory content.
 *
 * Memories are stored as markdown and the notebook chunks are markdown documents —
 * headings, fenced code, tables, blockquotes. Stripping the markers (what the cards
 * used to do) turned a code block into a run-on paragraph and a heading into a
 * sentence fragment, which is most of why the list read as noise.
 *
 * Deliberately not the chat `MarkdownRenderer`: that one carries citations, file
 * navigation and Prism highlighting, none of which apply to a memory card, and its
 * type scale is sized for a chat column rather than a card footer.
 */

import React, { useMemo } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * `card` is an excerpt in a scrolling list, where an `h1` must not shout over the
 * card beside it. `document` is a whole file on its own — there the headings are
 * the only structure the reader has, so they get their real size back.
 */
type MemoryMarkdownVariant = 'card' | 'document';

interface MemoryMarkdownProps {
  content: string;
  /** Highlights every occurrence of this string, the way search results do. */
  searchQuery?: string;
  variant?: MemoryMarkdownVariant;
  className?: string;
}

/**
 * Frontmatter is metadata, not prose. It is part of a page's first chunk, and
 * rendering it leaves a rule and a run of `key: value` lines above the actual text.
 */
export function stripFrontmatter(raw: string): string {
  return raw.replace(/^﻿?---\s*\n[\s\S]*?\n---\s*(\n|$)/, '').trimStart();
}

/**
 * `[[Page]]` and `[[Page|label]]` are Obsidian's link syntax, which markdown does
 * not know. There is nowhere to navigate to from a card, so they render as the name
 * they refer to rather than as raw brackets.
 */
function renderWikiLinks(raw: string): string {
  return raw.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_m, target, label) =>
    String(label || target).trim()
  );
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

type HastNode = {
  type: string;
  value?: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
};

/**
 * Wrap search matches in `<mark>` at the tree level rather than in the source.
 *
 * Highlighting the markdown string before parsing would let a query like `#` or `*`
 * inject syntax and change how the document renders. Doing it on the parsed tree
 * means a match can only ever become a `mark` around the text that matched.
 */
function rehypeHighlight(query?: string) {
  return () => (tree: HastNode) => {
    const needle = query?.trim();
    if (!needle) return;
    const pattern = new RegExp(`(${escapeRegExp(needle)})`, 'gi');

    const walk = (node: HastNode) => {
      if (!node.children) return;
      const next: HastNode[] = [];
      for (const child of node.children) {
        if (child.type === 'text' && child.value && pattern.test(child.value)) {
          pattern.lastIndex = 0;
          for (const part of child.value.split(pattern)) {
            if (!part) continue;
            next.push(
              part.toLowerCase() === needle.toLowerCase()
                ? {
                    type: 'element',
                    tagName: 'mark',
                    properties: {
                      className: ['bg-brutal-yellow', 'text-brutal-black', 'font-bold', 'px-0.5'],
                    },
                    children: [{ type: 'text', value: part }],
                  }
                : { type: 'text', value: part }
            );
          }
          continue;
        }
        // Never descend into code: a query matching a keyword would otherwise
        // splice an element into a block that is supposed to be verbatim.
        if (child.tagName !== 'code' && child.tagName !== 'pre') walk(child);
        next.push(child);
      }
      node.children = next;
    };

    walk(tree);
  };
}

/** Heading sizes are the only thing the two variants disagree about. */
const HEADINGS: Record<MemoryMarkdownVariant, string[]> = {
  card: [
    'mb-1 mt-3 font-brutal text-[15px] uppercase tracking-tight first:mt-0',
    'mb-1 mt-3 font-bold text-[14px] tracking-tight first:mt-0',
    'mb-1 mt-2 font-bold text-[13px] uppercase tracking-wide text-neutral-600 dark:text-neutral-400 first:mt-0',
    'mb-1 mt-2 font-bold text-[13px] first:mt-0',
  ],
  document: [
    'mb-3 mt-6 font-brutal text-2xl uppercase tracking-tight first:mt-0',
    'mb-2 mt-6 border-b-2 border-neutral-200 pb-1 font-brutal text-lg uppercase tracking-tight dark:border-zinc-700 first:mt-0',
    'mb-2 mt-4 font-bold text-base tracking-tight first:mt-0',
    'mb-1 mt-4 font-bold text-sm uppercase tracking-wide text-neutral-600 dark:text-neutral-400 first:mt-0',
  ],
};

/** Everything that renders the same at either scale. */
const SHARED: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-0.5 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 list-decimal space-y-0.5 pl-5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="leading-6">{children}</li>,
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="underline decoration-neutral-400 underline-offset-2 hover:decoration-brutal-black dark:hover:decoration-white"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="mb-2 border-l-3 border-brutal-black pl-3 text-neutral-600 dark:border-white/40 dark:text-neutral-400 last:mb-0">
      {children}
    </blockquote>
  ),
  code: ({ className, children }) => {
    // react-markdown gives inline code no language class and no `pre` parent.
    const isBlock = /language-/.test(className || '');
    if (isBlock) {
      return <code className="font-mono text-[12px] leading-5">{children}</code>;
    }
    return (
      <code className="border border-neutral-300 bg-neutral-100 px-1 font-mono text-[12px] dark:border-zinc-600 dark:bg-zinc-900">
        {children}
      </code>
    );
  },
  pre: ({ children }) => (
    <pre className="mb-2 overflow-x-auto border-2 border-brutal-black bg-neutral-50 p-2 dark:border-zinc-600 dark:bg-zinc-900 last:mb-0">
      {children}
    </pre>
  ),
  // Wide tables scroll inside the card instead of stretching it.
  table: ({ children }) => (
    <div className="mb-2 overflow-x-auto last:mb-0">
      <table className="w-full border-collapse text-[12px]">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-brutal-black px-1.5 py-0.5 text-left font-bold dark:border-zinc-600">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-neutral-300 px-1.5 py-0.5 dark:border-zinc-700">{children}</td>
  ),
  hr: () => <hr className="my-3 border-t-2 border-neutral-200 dark:border-zinc-700" />,
  img: ({ src, alt }) => (
    <img src={src} alt={alt} className="my-2 max-w-full border-2 border-brutal-black" />
  ),
};

function componentsFor(variant: MemoryMarkdownVariant): Components {
  const [h1, h2, h3, h4] = HEADINGS[variant];
  return {
    ...SHARED,
    h1: ({ children }) => <h1 className={h1}>{children}</h1>,
    h2: ({ children }) => <h2 className={h2}>{children}</h2>,
    h3: ({ children }) => <h3 className={h3}>{children}</h3>,
    // Anything deeper than h4 is rare enough that it shares h4's treatment.
    h4: ({ children }) => <h4 className={h4}>{children}</h4>,
    h5: ({ children }) => <h5 className={h4}>{children}</h5>,
    h6: ({ children }) => <h6 className={h4}>{children}</h6>,
  };
}

export const MemoryMarkdown: React.FC<MemoryMarkdownProps> = ({
  content,
  searchQuery,
  variant = 'card',
  className = '',
}) => {
  const prepared = useMemo(() => renderWikiLinks(stripFrontmatter(content)), [content]);
  const plugins = useMemo(() => [rehypeHighlight(searchQuery)], [searchQuery]);
  const components = useMemo(() => componentsFor(variant), [variant]);

  return (
    <div className={`memory-md break-words text-[15px] leading-7 ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={plugins} components={components}>
        {prepared}
      </ReactMarkdown>
    </div>
  );
};
