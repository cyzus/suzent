import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { CitationSource } from '../../lib/streamEvents';

/**
 * Inline-citation rendering.
 *
 * The assistant text contains literal `[[cite:t0_src_1]]`
 * (or `[[cite:t0_src_1,t0_src_2]]`)
 * markers. `MarkdownRenderer` splits text nodes on these markers and renders a
 * `CitationBadge` in place. Both the badge and the bottom `SourcesPanel` resolve
 * source ids to titles/urls via this context, which is populated from the
 * `citation_sources` stream event (stored as a 'citation-sources' AGUIPart).
 */

export type CitationSourcesMap = Map<string, CitationSource>;

const CitationContext = createContext<CitationSourcesMap | null>(null);

export const CitationProvider: React.FC<{
  sources: CitationSourcesMap;
  children: React.ReactNode;
}> = ({ sources, children }) => (
  <CitationContext.Provider value={sources}>{children}</CitationContext.Provider>
);

export function useCitationSources(): CitationSourcesMap | null {
  return useContext(CitationContext);
}

// Rich-content markers are typed: a TYPE keyword + payload, in one of three forms:
//   ASCII:  [[TYPE:payload]]        e.g. [[cite:t0_src_1]] or [[cite:t0_src_1,t0_src_2]]
//   PUA:    \ue200TYPE\ue202payload\ue201   e.g. \ue200cite\ue202t0_src_1\ue201
//   OBJ:    \ufffcTYPE\ufffcpayload\ufffc   e.g. \ufffccite\ufffct0_src_1\ufffc
// The PUA form matches ChatGPT's invisible-character scheme; ASCII is a
// debuggable fallback. Some Markdown/browser paths surface the private-use
// delimiters as U+FFFC object replacement boxes, so we parse that too. Today
// only TYPE="cite" is rendered (as a CitationBadge);
// other types are recognised by the grammar but ignored, so adding a new rich
// type later (e.g. filecite, image) is a renderer change, not a parser rewrite.
const ASCII_MARKER = /\[\[([a-zA-Z]+):\s*([^\]\n]+?)\s*\]\]/;
const PUA_MARKER = /\ue200([a-zA-Z]+)\ue202([^\ue201]+)\ue201/;
const OBJ_MARKER = /\ufffc([a-zA-Z]+)\ufffc([a-zA-Z0-9_,\s]+(?:\ufffc[a-zA-Z0-9_,\s]+)*)\ufffc/;
const LOOSE_CITE_MARKER = /\bcite[-:]((?:t\d+_src_\d+)(?:\s*,\s*t\d+_src_\d+)*)\b/;
export const CITATION_MARKER_RE = new RegExp(
  `${ASCII_MARKER.source}|${PUA_MARKER.source}|${OBJ_MARKER.source}|${LOOSE_CITE_MARKER.source}`,
  'g',
);

/** True when the string may contain a typed marker (either form). */
export function hasCitationMarker(text: string): boolean {
  return (
    text.includes('[[') ||
    text.includes('\ue200') ||
    text.includes('\ufffc') ||
    /\bcite[-:]t\d+_src_\d+\b/.test(text)
  );
}

// A marker that has begun streaming but not yet closed \u2014 e.g. `[[cite:t0`,
// `\ue200cite\ue202t0`, or `\ufffccite\ufffct0`. While streaming, the closing
// delimiter (`]]`, `\ue201`, trailing `\ufffc`) may not have arrived yet, so the
// full marker regexes don't match and the raw glyphs (including the U+E200/E202
// private-use boxes/stars) would otherwise leak into the rendered text.
const PARTIAL_MARKER_RE =
  /(?:\[\[|\ue200|\ufffc)[a-zA-Z]*(?:[:\ue202\ufffc][^\]\ue201]*)?$/;

/**
 * Strip a single incomplete typed marker anchored at the end of the string. Used
 * to hide partially-streamed citation markers until the closing delimiter
 * arrives, at which point the full regex takes over and renders a badge.
 */
export function stripTrailingPartialMarker(text: string): string {
  return text.replace(PARTIAL_MARKER_RE, '');
}

/** Source-id separators: comma, PUA separator, or OBJ-normalized separator. */
const ID_SEPARATORS = /[,\ue202\ufffc]/;

/** A parsed marker: its TYPE keyword and the list of payload tokens (e.g. ids). */
interface ParsedMarker { type: string; tokens: string[]; }

function parseMarker(m: RegExpExecArray): ParsedMarker {
  // ASCII groups are 1/2; PUA groups are 3/4; OBJ groups are 5/6;
  // loose fallback is group 7 and always means "cite".
  const type = (m[1] ?? m[3] ?? m[5] ?? (m[7] ? 'cite' : '')).toLowerCase();
  const payload = m[2] ?? m[4] ?? m[6] ?? m[7] ?? '';
  const tokens = payload.split(ID_SEPARATORS).map(s => s.trim()).filter(Boolean);
  return { type, tokens };
}

function escapeMarkdownLinkText(text: string): string {
  return text.replace(/\\/g, '\\\\').replace(/\]/g, '\\]');
}

function escapeMarkdownReferenceTitle(text: string): string {
  return text.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, ' ');
}

/**
 * Convert inline citation protocol markers into portable Markdown references for
 * clipboard/export. Screen rendering uses badges; copied text should be useful
 * outside Suzent.
 */
export function formatTextWithCitationReferences(
  text: string,
  sourcesMap: CitationSourcesMap,
): string {
  if (!hasCitationMarker(text)) return text;

  const refs: CitationSource[] = [];
  const refById = new Map<string, number>();
  const re = new RegExp(CITATION_MARKER_RE.source, 'g');

  const body = text.replace(re, (...args: unknown[]) => {
    const match = args.slice(0, -2) as unknown as RegExpExecArray;
    const offset = Number(args[args.length - 2] ?? 0);
    const { type, tokens } = parseMarker(match);
    if (type !== 'cite' || tokens.length === 0) return '';

    const labels = tokens.map(id => {
      const source = sourcesMap.get(id);
      if (!source || !source.url) return `[source: ${id}]`;
      let ref = refById.get(id);
      if (!ref) {
        refs.push(source);
        ref = refs.length;
        refById.set(id, ref);
      }
      return `[${escapeMarkdownLinkText(sourceName(source))}][${ref}]`;
    });
    const prefix = offset > 0 && !/\s/.test(text[offset - 1]) ? ' ' : '';
    return labels.length > 0 ? `${prefix}${labels.join(' ')}` : '';
  });

  if (refs.length === 0) return body;

  const referenceLines = refs.map((source, idx) => {
    const title = sourceLabel(source);
    const titlePart = title ? ` "${escapeMarkdownReferenceTitle(title)}"` : '';
    return `[${idx + 1}]: ${source.url}${titlePart}`;
  });
  return `${body.trimEnd()}\n\n${referenceLines.join('\n')}`;
}

/**
 * Split a plain string on typed markers, returning strings interleaved with
 * rendered marker elements. The badge number is the source's 1-based position in
 * the sources map (matching the SourcesPanel ordering). Used by both the full
 * and lite markdown renderers.
 */
export function renderTextWithCitations(
  text: string,
  sourcesMap: CitationSourcesMap | null,
  keyPrefix: string,
): React.ReactNode[] {
  if (!sourcesMap || !hasCitationMarker(text)) {
    // No complete marker, but a partial one may be mid-stream at the end.
    return [stripTrailingPartialMarker(text)];
  }

  const nodes: React.ReactNode[] = [];
  const re = new RegExp(CITATION_MARKER_RE.source, 'g');
  let last = 0;
  let m: RegExpExecArray | null;
  let n = 0;

  while ((m = re.exec(text)) !== null) {
    const before = text.slice(last, m.index);
    const { type, tokens } = parseMarker(m);
    last = re.lastIndex;

    if (type === 'cite' && tokens.length > 0) {
      nodes.push(before);
      nodes.push(
        <CitationBadge key={`${keyPrefix}-cite-${n++}`} sourceIds={tokens} />,
      );
    } else {
      // Unknown/unsupported marker type: keep the leading text, drop the marker.
      nodes.push(before);
    }
  }
  // A partial marker may still be streaming at the very end; hide it until the
  // closing delimiter arrives and the full regex above turns it into a badge.
  if (last < text.length) nodes.push(stripTrailingPartialMarker(text.slice(last)));
  return nodes;
}

/** Per-type emoji fallback, used when a source has no favicon. */
const TYPE_ICON: Record<string, string> = {
  search: '🔍',
  webpage: '🌐',
  file: '📄',
  notebook: '📓',
  memory: '🧠',
  mcp: '🔌',
  code: '💻',
  browser: '🖥️',
  subagent: '🤖',
};

/** Per-extension emoji for `file` sources that have no favicon. */
const FILE_EXT_ICONS: Record<string, string> = {
  md: '📝', txt: '📄', pdf: '📕',
  py: '🐍', ts: '📘', tsx: '📘', js: '📜', jsx: '📜',
  json: '📋', yaml: '📋', yml: '📋', toml: '📋',
  png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🎞️', svg: '🖼️',
};

function typeIcon(type?: string, url?: string | null): string {
  if (type === 'file' && url) {
    const ext = url.split(/[?#]/)[0].split('.').pop()?.toLowerCase();
    if (ext && FILE_EXT_ICONS[ext]) return FILE_EXT_ICONS[ext];
  }
  return (type && TYPE_ICON[type]) || '🔗';
}

/**
 * Best-effort display label for a source url: hostname for web urls
 * (e.g. "www.bbc.co.uk" -> "bbc.co.uk"), filename for `file://` urls.
 */
function domainOf(url?: string | null): string {
  if (!url) return '';
  try {
    if (url.startsWith('file://')) {
      // Windows: /C:/Users/x.txt, Unix: /home/user/x.txt — take the basename.
      const path = new URL(url).pathname.replace(/\\/g, '/');
      const name = path.split('/').filter(Boolean).pop();
      return name ? decodeURIComponent(name) : 'file';
    }
    const host = new URL(url).hostname.replace(/^www\./, '');
    return host;
  } catch {
    return '';
  }
}

/** Short, human label for a source: its title, else its domain, else its id. */
function sourceLabel(s: CitationSource): string {
  if (s.title && s.title.trim()) return s.title.trim();
  const d = domainOf(s.url);
  if (d) return d;
  return s.id;
}

/** Compact source name for inline badges: prefer the site/source over article title. */
function sourceName(s: CitationSource): string {
  const d = domainOf(s.url);
  if (d) return d;
  if (s.title && s.title.trim()) return s.title.trim();
  return s.id;
}

async function openSource(url: string) {
  if (!url) return;
  try {
    // file:// — open natively under Tauri; in the browser, file:// can't be
    // opened programmatically, so copy the path to the clipboard instead.
    if (url.startsWith('file://')) {
      if (window.__TAURI__) {
        const { open } = await import('@tauri-apps/plugin-shell');
        await open(url);
      } else {
        await navigator.clipboard.writeText(url.replace(/^file:\/\//, ''));
      }
      return;
    }
    if (window.__TAURI__) {
      const { open } = await import('@tauri-apps/plugin-shell');
      await open(url);
      return;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
  } catch (err) {
    console.warn('Failed to open citation source', err);
  }
}

/**
 * Favicon with graceful fallback: if the image fails to load (or there's no
 * favicon url), render the source type's emoji instead so we never show a
 * broken-image glyph.
 */
const Favicon: React.FC<{ src?: string | null; type?: string; url?: string | null; className?: string }> = ({
  src,
  type,
  url,
  className = 'w-3.5 h-3.5',
}) => {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return <span className={`inline-flex items-center justify-center leading-none ${className}`}>{typeIcon(type, url)}</span>;
  }
  return (
    <img
      src={src}
      alt=""
      className={`${className} shrink-0 rounded-[2px] object-contain`}
      onError={() => setFailed(true)}
      loading="lazy"
    />
  );
};

/** Hover-intent: small open/close delay so the card doesn't flicker on transit. */
function useHoverCard() {
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clear = () => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  };
  const onEnter = () => {
    clear();
    timer.current = setTimeout(() => setOpen(true), 80);
  };
  const onLeave = () => {
    clear();
    timer.current = setTimeout(() => setOpen(false), 140);
  };
  return { open, onEnter, onLeave };
}

/** One row in the hover card: favicon, title, domain, optional snippet. */
const SourceCardRow: React.FC<{ source: CitationSource }> = ({ source: s }) => {
  const domain = domainOf(s.url);
  return (
    <a
      href={s.url || '#'}
      target="_blank"
      rel="noopener noreferrer"
      onClick={e => {
        if (!s.url) return;
        e.preventDefault();
        e.stopPropagation();
        void openSource(s.url);
      }}
      className="flex items-start gap-2 p-2 rounded-[2px] hover:bg-neutral-100 dark:hover:bg-zinc-700/70 no-underline group/srow max-w-full overflow-hidden"
    >
      <Favicon src={s.favicon} type={s.type} url={s.url} className="w-4 h-4 mt-0.5" />
      <span className="min-w-0 flex flex-col leading-tight">
        <span className="text-[12px] font-bold text-brutal-black dark:text-neutral-100 line-clamp-2 break-words group-hover/srow:underline">
          {sourceLabel(s)}
        </span>
        {domain && (
          <span className="mt-0.5 text-[10px] font-medium text-neutral-500 dark:text-neutral-400 truncate">{domain}</span>
        )}
        {s.snippet && (
          <span className="mt-1 text-[10px] text-neutral-500 dark:text-neutral-400 line-clamp-2 break-words">
            {s.snippet}
          </span>
        )}
      </span>
    </a>
  );
};

/**
 * Inline citation chip — favicon + source name (Perplexity style), not a number.
 * Hovering reveals a card with the full title, domain, and snippet for each
 * cited source. For multiple sources, shows stacked favicons + the primary name.
 * If metadata is missing (for example an older persisted chat without
 * citation_sources), it still renders a muted fallback chip so the citation does
 * not disappear.
 */
export const CitationBadge: React.FC<{ sourceIds: string[] }> = ({ sourceIds }) => {
  const sourcesMap = useCitationSources();
  const { open, onEnter, onLeave } = useHoverCard();
  const anchorRef = useRef<HTMLSpanElement>(null);
  const [cardStyle, setCardStyle] = useState<React.CSSProperties | null>(null);

  const sources = sourceIds
    .map(id => sourcesMap?.get(id))
    .filter((s): s is CitationSource => Boolean(s));
  const unresolvedIds = sourceIds.filter(id => !sourcesMap?.has(id));

  useEffect(() => {
    if (!open || !anchorRef.current) return;

    const updatePosition = () => {
      const rect = anchorRef.current?.getBoundingClientRect();
      if (!rect) return;

      const margin = 12;
      const width = Math.min(360, Math.max(220, window.innerWidth - margin * 2));
      const left = Math.min(
        Math.max(rect.left + rect.width / 2 - width / 2, margin),
        window.innerWidth - width - margin,
      );
      const top = rect.top >= 132 ? rect.top - margin : rect.bottom + margin;
      const placeBelow = rect.top < 132;

      setCardStyle({
        left,
        top,
        width,
        transform: placeBelow ? undefined : 'translateY(-100%)',
      });
    };

    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [open]);

  if (sources.length === 0) {
    const label = sourceIds[0] || 'source';
    const extra = Math.max(0, sourceIds.length - 1);
    return (
      <span className="relative inline-flex align-baseline mx-0.5">
        <span
          className="inline-flex items-center gap-1 max-w-[180px] h-[18px] pl-1 pr-1.5
            align-[-0.2em] rounded-full border border-dashed border-neutral-300 dark:border-zinc-600
            bg-neutral-50/70 dark:bg-zinc-800/70 text-neutral-500 dark:text-neutral-400
            no-underline"
          title={`Citation source metadata missing: ${sourceIds.join(', ')}`}
        >
          <span className="text-[10px] leading-none">↗</span>
          <span className="text-[10px] font-medium leading-none truncate">
            {label}
            {extra > 0 && <span className="text-neutral-400"> +{extra}</span>}
          </span>
        </span>
      </span>
    );
  }

  const primary = sources[0];
  const label = sourceName(primary);
  const extra = sources.length + unresolvedIds.length - 1;
  const popover = open && typeof document !== 'undefined' ? createPortal(
    <span
      className="fixed z-[9999] block
        bg-white dark:bg-zinc-800 border-2 border-brutal-black dark:border-zinc-500
        rounded-[3px] p-1.5 min-w-0"
      style={cardStyle ?? { left: -9999, top: -9999, width: 360 }}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
    >
      {sources.map((s, i) => (
        <SourceCardRow key={i} source={s} />
      ))}
    </span>,
    document.body,
  ) : null;

  return (
    <span
      ref={anchorRef}
      className="relative inline-flex align-baseline mx-0.5"
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
    >
      <button
        type="button"
        onClick={() => primary.url && void openSource(primary.url)}
        className="inline-flex items-center gap-1 max-w-[180px] h-[18px] pl-1 pr-1.5
          align-[-0.2em] rounded-full border border-neutral-300 dark:border-zinc-600
          bg-neutral-50 dark:bg-zinc-800 text-neutral-700 dark:text-neutral-200
          hover:border-brutal-black dark:hover:border-white hover:bg-brutal-yellow/40
          transition-colors cursor-pointer no-underline"
        title={[...sources.map(sourceName), ...unresolvedIds].join(', ')}
      >
        {/* Stacked favicons for multi-source, single otherwise */}
        <span className="flex items-center">
          {sources.slice(0, 2).map((s, i) => (
            <Favicon
              key={i}
              src={s.favicon}
              type={s.type}
              url={s.url}
              className={`w-3 h-3 ${i > 0 ? '-ml-1 ring-1 ring-neutral-50 dark:ring-zinc-800 rounded-full' : ''}`}
            />
          ))}
        </span>
        <span className="text-[10px] font-medium leading-none truncate">
          {label}
          {extra > 0 && <span className="text-neutral-400"> +{extra}</span>}
        </span>
      </button>

      {popover}
    </span>
  );
};

/**
 * Compact, inline sources control meant to sit on the message action row next to
 * copy/retry. The collapsed pill shows stacked favicons + a count; clicking pops
 * a source list anchored to the pill. The list is portaled to <body> and
 * positioned in the viewport (preferring above the pill, flipping below when
 * there's more room) with a height cap, so a long/streaming list never clips
 * off-screen. Closes on outside click and Escape.
 */
/**
 * Bounds to keep a popover inside the chat: the nearest scrollable ancestor's
 * rect, intersected with the viewport (so we never exceed the window either).
 * Falls back to the viewport when no scroll container is found.
 */
function scrollContainerBounds(el: HTMLElement): { top: number; bottom: number; left: number; right: number } {
  const viewport = { top: 0, bottom: window.innerHeight, left: 0, right: window.innerWidth };
  let node: HTMLElement | null = el.parentElement;
  while (node) {
    const style = getComputedStyle(node);
    // Must be an actual scroll *and* really clip content. Note: a div with
    // `overflow-x: hidden` reports computed `overflow-y: auto` per the CSS spec
    // even when it never scrolls — so we also require the element to overflow on
    // that axis, otherwise these `overflow-x-hidden` message wrappers would be
    // mistaken for the chat's scroll container (full height -> bounds too tall).
    const scrollsY = /(auto|scroll|overlay)/.test(style.overflowY) && node.scrollHeight > node.clientHeight;
    const scrollsX = /(auto|scroll|overlay)/.test(style.overflowX) && node.scrollWidth > node.clientWidth;
    if (scrollsY || scrollsX) {
      const r = node.getBoundingClientRect();
      return {
        top: Math.max(viewport.top, r.top),
        bottom: Math.min(viewport.bottom, r.bottom),
        left: Math.max(viewport.left, r.left),
        right: Math.min(viewport.right, r.right),
      };
    }
    node = node.parentElement;
  }
  return viewport;
}

export const SourcesPanel: React.FC<{ sources: CitationSource[] }> = ({ sources }) => {
  const [expanded, setExpanded] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [panelStyle, setPanelStyle] = useState<React.CSSProperties | null>(null);

  React.useEffect(() => {
    if (!expanded) return;
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (ref.current?.contains(target) || panelRef.current?.contains(target)) return;
      setExpanded(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpanded(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [expanded]);

  // Position the dropdown in the viewport (it's portaled to <body> so it escapes
  // any scroll/overflow ancestor). The action row sits low and the list grows
  // upward, so without a viewport-aware cap the top entries clip off-screen —
  // especially while sources are still streaming in. We prefer opening above the
  // pill but flip below when there's more room, and cap max-height to the space
  // available on the chosen side so the whole list stays scrollable on-screen.
  React.useEffect(() => {
    if (!expanded) return;

    const updatePosition = () => {
      const anchor = ref.current;
      if (!anchor) return;
      const rect = anchor.getBoundingClientRect();

      // Clamp to the chat's scroll container so the panel never spills outside the
      // chat window (over the toolbar or the app chrome). Fall back to the viewport.
      const bounds = scrollContainerBounds(anchor);

      const margin = 12;
      const gap = 6;
      const availWidth = bounds.right - bounds.left - margin * 2;
      const width = Math.min(440, Math.max(220, availWidth));
      const left = Math.min(
        Math.max(rect.left, bounds.left + margin),
        bounds.right - width - margin,
      );
      const spaceAbove = rect.top - bounds.top - margin;
      const spaceBelow = bounds.bottom - rect.bottom - margin;
      const placeBelow = spaceBelow > spaceAbove;
      const maxHeight = Math.max(120, (placeBelow ? spaceBelow : spaceAbove) - gap);

      // Measure the panel's natural height so we can pin its top edge ourselves
      // (no translateY), which lets us hard-clamp it inside the bounds — otherwise
      // an upward-growing panel can poke above the chat container / over the
      // toolbar when our space estimate and the real content height disagree.
      const naturalHeight = panelRef.current?.scrollHeight ?? maxHeight;
      const height = Math.min(naturalHeight, maxHeight);
      const rawTop = placeBelow ? rect.bottom + gap : rect.top - gap - height;
      const top = Math.min(
        Math.max(rawTop, bounds.top + margin),
        bounds.bottom - height - margin,
      );

      setPanelStyle({ left, top, width, maxHeight });
    };

    // First pass positions with an estimated height (panel not yet measured);
    // a second pass after paint re-runs with the panel's real scrollHeight so the
    // top-edge clamp is exact. Re-runs again as sources stream in (length dep).
    updatePosition();
    const raf = requestAnimationFrame(updatePosition);
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [expanded, sources.length]);

  if (sources.length === 0) return null;

  return (
    <span ref={ref} className="relative inline-flex">
      <button
        onClick={() => setExpanded(e => !e)}
        className="flex items-center gap-1.5 text-[10px] font-mono font-bold uppercase tracking-tight
          text-neutral-400 hover:text-brutal-black dark:hover:text-white transition-colors"
      >
        <span className="flex items-center">
          {sources.slice(0, 4).map((s, i) => (
            <Favicon
              key={i}
              src={s.favicon}
              type={s.type}
              url={s.url}
              className={`w-3.5 h-3.5 ${i > 0 ? '-ml-1 ring-1 ring-white dark:ring-zinc-900 rounded-full' : ''}`}
            />
          ))}
          {sources.length > 4 && (
            <span className="text-[9px] text-neutral-400 ml-1">+{sources.length - 4}</span>
          )}
        </span>
        <span>{sources.length} {sources.length === 1 ? 'Source' : 'Sources'}</span>
        <svg
          className={`w-3 h-3 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={3}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && typeof document !== 'undefined' && createPortal(
        <div
          ref={panelRef}
          className="fixed z-[9999] flex flex-col gap-0.5
            bg-white dark:bg-zinc-800 border-2 border-brutal-black dark:border-zinc-500
            rounded-[3px] p-1.5 overflow-y-auto"
          style={panelStyle ?? { left: -9999, top: -9999, width: 360 }}
        >
          {sources.map((s, i) => {
            const domain = domainOf(s.url);
            return (
              <a
                key={s.id}
                href={s.url || '#'}
                target="_blank"
                rel="noopener noreferrer"
                onClick={e => {
                  if (!s.url) return;
                  e.preventDefault();
                  e.stopPropagation();
                  void openSource(s.url);
                }}
                className="flex items-start gap-2 p-2 rounded-[2px] hover:bg-neutral-100 dark:hover:bg-zinc-700/70 group no-underline"
              >
                <span className="font-mono font-bold text-neutral-400 text-[11px] w-4 shrink-0 mt-0.5 text-right">{i + 1}</span>
                <Favicon src={s.favicon} type={s.type} url={s.url} className="w-4 h-4 mt-0.5" />
                <span className="min-w-0 flex flex-col leading-tight">
                  <span className="text-[12px] font-semibold text-brutal-black dark:text-neutral-100 line-clamp-1 group-hover:underline">
                    {sourceLabel(s)}
                  </span>
                  {domain && (
                    <span className="text-[10px] text-neutral-500 dark:text-neutral-400 truncate">{domain}</span>
                  )}
                </span>
              </a>
            );
          })}
        </div>,
        document.body,
      )}
    </span>
  );
};
