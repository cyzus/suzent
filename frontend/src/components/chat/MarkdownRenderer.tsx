import { ChatMarkdownImage } from '../ChatImageGallery';
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import { remarkCurrency } from '../../lib/remarkCurrency';
import { remarkLatexMath } from '../../lib/remarkLatexMath';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { CodeBlockComponent } from './CodeBlockComponent';
import { ClickableContent } from '../ClickableContent';
import { hasCitationMarker, renderTextWithCitations, useCitationSources } from './Citations';
import { DocumentTextIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { getApiBase } from '../../lib/api';
import { splitStreamingBlocks } from '../../lib/streamingMarkdown';

export function sanitizeMarkdownCodeFenceLanguages(markdown: string): string {
  const repairedLooseUrlFences = markdown.replace(
    /^([ \t]{0,3})`{1,2}(https?:\/\/[^\n`]+)\n[ \t]*`{1,2}[ \t]*$/gm,
    '$1```\n$2\n$1```'
  );

  return repairedLooseUrlFences.replace(/^([ \t]{0,3}```)[ \t]*([^\n`]*)/gm, (_m, fence, info) => {
    const token =
      String(info || '')
        .trim()
        .split(/\s+/)[0] || '';
    if (!token) return fence;
    // A fence with an info string can never close a block, so dropping the info
    // string would turn an inner ```diff into the outer block's closing fence.
    const clean = token.replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();
    return `${fence}${clean || 'text'}`;
  });
}

interface MarkdownRendererProps {
  content: string;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
  isStreaming?: boolean;
  compact?: boolean;
  /**
   * Draw a blinking caret after the last character while streaming.
   */
  caret?: boolean;
}

function encodePathSegments(path: string): string {
  return path
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/');
}

function fileUrlToPath(url: string): string | null {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'file:') return null;

    let pathname = decodeURIComponent(parsed.pathname).replace(/\\/g, '/');
    // Windows file URLs parse as /C:/path. Strip the leading slash.
    if (/^\/[a-zA-Z]:\//.test(pathname)) {
      pathname = pathname.slice(1);
    }
    return pathname;
  } catch {
    return null;
  }
}

function suzentSessionFileUrlToServeUrl(url: string): string | null {
  const path = fileUrlToPath(url);
  if (!path) return null;

  const normalized = path.replace(/\\/g, '/');
  const match = normalized.match(/(?:^|\/)sessions\/([^/]+)\/(.+)$/);
  if (!match) return null;

  const [, chatId, relativePath] = match;
  if (!chatId || !relativePath || relativePath.includes('..')) return null;

  return `${getApiBase()}/sandbox/serve/${encodeURIComponent(chatId)}/workspace/${encodePathSegments(relativePath)}`;
}

function normalizeMarkdownUrl(url: string): string {
  const trimmed = url.trim();
  if (!trimmed) return '';

  if (/^file:/i.test(trimmed)) {
    // Session-workspace files are rewritten to a /sandbox/serve URL. Any other
    // file:// URL (e.g. an absolute repo path) is left intact so the `a`
    // renderer can turn it into a clickable FileButton (opened in the file view
    // via onFileClick) instead of being blanked into a dead href.
    return suzentSessionFileUrlToServeUrl(trimmed) || trimmed;
  }

  return trimmed;
}

// Reusable clickable file button component
const FileButton: React.FC<{
  path: string;
  displayName: string;
  onFileClick: (path: string, fileName: string, shiftKey?: boolean) => void;
}> = ({ path, displayName, onFileClick }) => {
  const { t } = useI18n();
  const fileName = path.split('/').pop() || displayName;

  return (
    <span
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onFileClick(path, fileName, e.shiftKey);
      }}
      className="inline-flex max-w-full items-center gap-1 bg-brutal-yellow border-2 border-brutal-black px-2 py-0.5 font-mono text-xs font-bold text-brutal-black shadow-brutal-sm brutal-btn transition-all cursor-pointer"
      title={t('fileLink.clickToView', { path })}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onFileClick(path, fileName, e.shiftKey);
        }
      }}
    >
      <DocumentTextIcon className="w-3 h-3 stroke-[3] shrink-0" />
      <span className="truncate">{displayName}</span>
    </span>
  );
};

function extractCodeText(children: React.ReactNode): string {
  if (typeof children === 'string') return children;
  if (Array.isArray(children)) return children.map(extractCodeText).join('');
  if (React.isValidElement(children)) {
    return extractCodeText((children.props as { children?: React.ReactNode }).children);
  }
  return children == null || typeof children === 'boolean' ? '' : String(children);
}

function extractNodeText(children: React.ReactNode): string {
  if (typeof children === 'string' || typeof children === 'number') return String(children);
  if (Array.isArray(children)) return children.map(extractNodeText).join('');
  if (React.isValidElement(children)) {
    const props = children.props as { children?: React.ReactNode };
    return extractNodeText(props.children);
  }
  return '';
}

const MarkdownStreamingContext = React.createContext(false);

const MarkdownCodeBlock: React.FC<{ lang: string; content: string }> = (props) => {
  const isStreaming = React.useContext(MarkdownStreamingContext);
  return <CodeBlockComponent {...props} isStreaming={isStreaming} showCursor={false} />;
};

const REMARK_PLUGINS = [remarkGfm, remarkMath, remarkCurrency, remarkLatexMath];
const REHYPE_PLUGINS = [rehypeKatex];

/**
 * Block dangerous protocols while allowing standard ones. Pure, so it lives at
 * module scope: a fresh identity each render would re-run react-markdown's URL
 * pass for nothing.
 */
function safeUrlTransform(url: string): string {
  const normalizedUrl = normalizeMarkdownUrl(url);
  const urlLower = normalizedUrl.toLowerCase().trim();

  // Allow safe protocols. `file:` is permitted because the `a` renderer
  // intercepts file:// hrefs into a FileButton (opened in the in-app file
  // view via onFileClick) rather than letting the browser navigate to them —
  // so it must survive this transform instead of being stripped to ''.
  const safeProtocols = ['http:', 'https:', 'mailto:', 'tel:', 'file:'];
  const hasProtocol = urlLower.includes(':');

  if (urlLower.startsWith('data:image/')) {
    return /^data:image\/(?:png|jpe?g|gif|webp|svg\+xml);base64,/i.test(normalizedUrl)
      ? normalizedUrl
      : '';
  }

  if (hasProtocol) {
    const isAllowed = safeProtocols.some((protocol) => urlLower.startsWith(protocol));
    if (!isAllowed) {
      // Block dangerous protocols like javascript:, unsupported data:, vbscript:, etc.
      return '';
    }
  }

  // Allow relative URLs and fragment links
  return normalizedUrl;
}

/**
 * One parsed run of markdown. Memoized on its text, so while a reply streams
 * the blocks that are already finished are not parsed again every frame.
 */
const MarkdownBlock = React.memo<{ content: string; components: object }>(
  ({ content, components }) => {
    const RM: any = ReactMarkdown;
    return (
      <RM
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
        urlTransform={safeUrlTransform}
        components={components}
      >
        {content}
      </RM>
    );
  }
);
MarkdownBlock.displayName = 'MarkdownBlock';

export const MarkdownRenderer = React.memo<MarkdownRendererProps>(
  ({ content, onFileClick, isStreaming = false, compact = false, caret = false }) => {
    const sourcesMap = useCitationSources();
    // Every reload of the chat hands each message a fresh sources map, even when
    // its sources are unchanged. Keying the components map on that identity
    // remounted every paragraph of the history, losing the reader's place.
    // Rebuild only when the set of sources changes; read the map through a ref.
    const sourcesMapRef = React.useRef(sourcesMap);
    sourcesMapRef.current = sourcesMap;
    const sourcesSignature = React.useMemo(
      () => (sourcesMap ? Array.from(sourcesMap.keys()).join('\u0000') : ''),
      [sourcesMap]
    );
    const openingLinksRef = React.useRef(new Map<string, number>());

    // The `components` map below is keyed into React's element type. A fresh
    // identity for any entry makes React unmount and remount that entire subtree
    // instead of reconciling it, which destroys any selection the user is holding
    // — so every value the map closes over has to be identity-stable. `onFileClick`
    // arrives fresh from the parent on most renders, so route it through a ref.
    const onFileClickRef = React.useRef(onFileClick);
    React.useEffect(() => {
      onFileClickRef.current = onFileClick;
    });

    const hasFileClick = Boolean(onFileClick);
    const handleFileClick = React.useMemo(
      () =>
        hasFileClick
          ? (filePath: string, fileName: string, shiftKey?: boolean) =>
              onFileClickRef.current?.(filePath, fileName, shiftKey)
          : undefined,
      [hasFileClick]
    );

    const isExternalLink = React.useCallback((href: string): boolean => {
      // Includes file: so renderers without an onFileClick handler still open the
      // link (via openExternalLink -> Tauri shell.open) instead of letting the
      // browser navigate to an http -> file:// URL and bounce back to the app root.
      return /^(https?:|mailto:|tel:|file:)/i.test(href.trim());
    }, []);

    const openExternalLink = React.useCallback(async (href: string) => {
      const link = href.trim();
      if (!link) return;

      // Guard against duplicate click events firing close together.
      const now = Date.now();
      const lastOpen = openingLinksRef.current.get(link);
      if (lastOpen && now - lastOpen < 750) {
        return;
      }
      openingLinksRef.current.set(link, now);

      try {
        if (window.__TAURI__) {
          const { open } = await import('@tauri-apps/plugin-shell');
          await open(link);
          return;
        }

        window.open(link, '_blank', 'noopener,noreferrer');
      } catch (err) {
        console.warn('Failed to open external link', err);
      } finally {
        // Keep a short cooldown to suppress accidental double opens.
        window.setTimeout(() => {
          openingLinksRef.current.delete(link);
        }, 750);
      }
    }, []);

    // Walk rendered children, splitting string nodes that contain a citation
    // marker into text + <CitationBadge> nodes. This is recursive because
    // react-markdown may wrap text in <strong>, <em>, links, etc.
    const applyCitations = React.useCallback(
      (children: React.ReactNode, keyPrefix: string, linkFiles = false): React.ReactNode => {
        const linkText = (text: string, key: string, link: boolean): React.ReactNode =>
          link && handleFileClick ? (
            <ClickableContent key={key} content={text} onFileClick={handleFileClick} />
          ) : (
            text
          );
        const walk = (child: React.ReactNode, key: string, link: boolean): React.ReactNode => {
          if (typeof child === 'string') {
            if (!hasCitationMarker(child)) return linkText(child, key, link);
            // Route even when sourcesMap is null/empty so unresolvable markers are
            // stripped rather than leaking their raw protocol glyphs.
            return renderTextWithCitations(child, sourcesMapRef.current ?? null, key).map(
              (node, i) => (typeof node === 'string' ? linkText(node, `${key}-t${i}`, link) : node)
            );
          }
          if (React.isValidElement(child) && child.props?.children) {
            if (child.type === 'code' || child.props?.node?.tagName === 'code') {
              return child;
            }
            // Links and other custom renderers read their children as text, so
            // file paths are only linked inside plain emphasis.
            const nestedLink = link && (child.type === 'strong' || child.type === 'em');
            const nextChildren = React.Children.map(child.props.children, (nested, i) =>
              walk(nested, `${key}-${i}`, nestedLink)
            );
            return React.cloneElement(child as React.ReactElement<any>, undefined, nextChildren);
          }
          return child;
        };

        const arr = React.Children.toArray(children);
        if (
          !arr.some((c) =>
            typeof c === 'string'
              ? hasCitationMarker(c) || (linkFiles && handleFileClick)
              : React.isValidElement(c)
          )
        ) {
          return children;
        }
        return arr.map((child, i) => walk(child, `${keyPrefix}-${i}`, linkFiles));
      },
      // eslint-disable-next-line react-hooks/exhaustive-deps -- the signature tracks the map's contents
      [sourcesSignature, handleFileClick]
    );

    // Normalize content
    const normalized = String(content)
      .replace(/\r\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/^\n+/, '')
      .replace(/\n+$/, '');

    // Sanitize code block languages
    const sanitized = sanitizeMarkdownCodeFenceLanguages(normalized);
    // react-markdown renders no wrapper, so the blocks land as siblings in the
    // same container and the result looks like one parse. Once the stream ends
    // the text is parsed whole, so anything that spans blocks comes out right.
    const blocks = React.useMemo(
      () => (isStreaming ? splitStreamingBlocks(sanitized) : [sanitized]),
      [isStreaming, sanitized]
    );

    const components = React.useMemo(
      () => ({
        pre: (p: any) => {
          if (p.node?.children?.length === 1 && p.node.children[0].tagName === 'code') {
            const child = React.Children.toArray(p.children)[0];
            const className = React.isValidElement(child)
              ? String((child.props as { className?: string }).className || '')
              : '';
            const match = /language-([a-zA-Z0-9_-]+)/.exec(className);
            const codeContent = extractCodeText(p.children).replace(/\n$/, '');

            return <MarkdownCodeBlock lang={match?.[1] || 'text'} content={codeContent} />;
          }
          return (
            <div className="bg-neutral-50 dark:bg-zinc-800 p-4 overflow-x-auto">
              <pre className="font-mono text-xs text-brutal-black dark:text-neutral-200 leading-relaxed whitespace-pre-wrap break-all">
                {p.children}
              </pre>
            </div>
          );
        },
        code: (codeProps: any) => {
          const { inline, className, children, ...rest } = codeProps;
          const match = /language-([a-zA-Z0-9_-]+)/.exec(className || '');
          const lang = match ? match[1] : null;

          const codeContent = extractCodeText(children).replace(/\n$/, '');

          // Detect if this is inline code (no language and not in a <pre> parent).
          // Some models wrap multi-line ASCII diagrams in a single backtick span;
          // render those as blocks so they don't become a stack of inline chips.
          const isMultilineInlineCode = !lang && codeContent.includes('\n');
          const isInline = inline !== false && !lang && !isMultilineInlineCode;

          if (isInline && hasCitationMarker(codeContent)) {
            return (
              <>{renderTextWithCitations(codeContent, sourcesMapRef.current ?? null, 'code')}</>
            );
          }

          // Check if inline code contains a file path pattern
          if (isInline && handleFileClick) {
            // Pattern 1: Markdown file:// link in backticks: `[text](file:///path)`
            const fileLinkMatch = codeContent.match(/^\[([^\]]+)\]\(file:\/\/([^)]+)\)$/);
            if (fileLinkMatch) {
              const [, displayName, path] = fileLinkMatch;
              return (
                <FileButton path={path} displayName={displayName} onFileClick={handleFileClick} />
              );
            }

            // Pattern 2: Plain absolute path in backticks: `/workspace/file.txt`
            const absolutePathMatch = codeContent.match(
              /^\/(workspace|shared|mnt)\/[\w\-./]+\.\w{2,5}$/
            );
            if (absolutePathMatch) {
              const path = codeContent.trim();
              return <FileButton path={path} displayName={path} onFileClick={handleFileClick} />;
            }
          }

          if (isMultilineInlineCode || !isInline) {
            return <MarkdownCodeBlock lang={lang || 'text'} content={codeContent} />;
          }
          return (
            <code
              className="bg-brutal-yellow px-1.5 py-0.5 border-2 border-brutal-black text-[11px] font-mono text-brutal-black font-bold break-words break-all whitespace-pre-wrap box-decoration-clone"
              {...rest}
            >
              {children}
            </code>
          );
        },
        a: (props: any) => {
          const { href, children } = props;
          const hrefStr = href || '';

          // Handle file:// links and absolute paths as clickable file buttons
          if (
            handleFileClick &&
            (hrefStr.startsWith('file://') ||
              hrefStr.startsWith('/workspace/') ||
              hrefStr.startsWith('/shared/') ||
              hrefStr.startsWith('/mnt/'))
          ) {
            // file:// hrefs are percent-encoded (CJK, spaces, etc.) — decode via
            // fileUrlToPath rather than a naive replace, otherwise the encoded
            // bytes get double-encoded downstream and the file is never found.
            const path = hrefStr.startsWith('file://')
              ? (fileUrlToPath(hrefStr) ?? hrefStr.replace('file://', ''))
              : hrefStr;
            const displayName = extractNodeText(children) || path;
            return (
              <FileButton path={path} displayName={displayName} onFileClick={handleFileClick} />
            );
          }

          // Regular external links
          return (
            <a
              href={hrefStr}
              rel="noopener noreferrer"
              onClick={(e) => {
                if (!isExternalLink(hrefStr)) return;
                e.preventDefault();
                e.stopPropagation();
                void openExternalLink(hrefStr);
              }}
              className="text-brutal-blue hover:bg-brutal-yellow font-bold underline break-words transition-colors duration-100"
            >
              {children}
            </a>
          );
        },
        img: (props: any) => {
          const src = safeUrlTransform(String(props.src || ''));
          if (!src) {
            return <span className="text-neutral-500">{props.alt || ''}</span>;
          }

          return (
            <ChatMarkdownImage
              src={src}
              alt={props.alt || ''}
              title={props.title}
              className="max-w-full max-h-[60vh] object-contain border-2 border-brutal-black shadow-brutal-sm bg-white"
              loading="lazy"
            />
          );
        },
        table: (p: any) => (
          <div className="overflow-x-auto">
            <table className="text-xs border-3 border-brutal-black dark:border-zinc-500">
              {p.children}
            </table>
          </div>
        ),
        th: (p: any) => (
          <th className="border-2 border-brutal-black dark:border-zinc-500 px-2 py-1 bg-brutal-yellow text-brutal-black font-bold break-normal">
            {applyCitations(p.children, 'th')}
          </th>
        ),
        td: (p: any) => (
          <td className="border-2 border-brutal-black dark:border-zinc-500 px-2 py-1 align-top break-normal">
            {applyCitations(p.children, 'td')}
          </td>
        ),
        ul: (p: any) => <ul className="list-disc pl-5">{p.children}</ul>,
        ol: (p: any) => <ol className="list-decimal pl-5">{p.children}</ol>,
        li: (p: any) => <li>{applyCitations(p.children, 'li')}</li>,
        h1: (p: any) => (
          <h1 className="text-xl font-brutal font-bold mb-2 break-words uppercase">
            {applyCitations(p.children, 'h1')}
          </h1>
        ),
        h2: (p: any) => (
          <h2 className="text-lg font-brutal font-bold mb-2 break-words uppercase">
            {applyCitations(p.children, 'h2')}
          </h2>
        ),
        h3: (p: any) => (
          <h3 className="text-base font-bold mb-1 break-words uppercase">
            {applyCitations(p.children, 'h3')}
          </h3>
        ),
        p: (pArg: any) => {
          const text = String(pArg.children?.[0] || '');
          if (text.startsWith('Step: ') && text.includes('tokens')) {
            return (
              <p className="flex items-center gap-3 text-xs sm:text-sm text-brutal-black border-4 border-brutal-black pt-4 pb-3 mt-6 font-mono font-black break-words whitespace-pre-wrap m-0 bg-brutal-yellow -mx-5 px-5 shadow-brutal-sm uppercase tracking-wider">
                <span aria-hidden="true" className="text-lg leading-none">
                  ▣
                </span>
                <span className="flex-1">{pArg.children}</span>
              </p>
            );
          }

          // Link file paths in the text leaves rather than flattening the
          // paragraph: flattening dropped bold/italic and left citation markers
          // nested inside them as raw private-use glyphs.
          return (
            <p className="leading-relaxed break-words whitespace-pre-wrap m-0">
              {applyCitations(pArg.children, 'p', true)}
            </p>
          );
        },
        blockquote: (p: any) => (
          <blockquote className="border-l-4 border-brutal-black pl-3 italic text-neutral-600 dark:text-neutral-400 break-words bg-neutral-50 dark:bg-zinc-800 py-1 pr-2">
            {p.children}
          </blockquote>
        ),
      }),
      // eslint-disable-next-line react-hooks/exhaustive-deps -- the signature tracks the map's contents
      [applyCitations, handleFileClick, isExternalLink, openExternalLink, sourcesSignature]
    );

    return (
      <MarkdownStreamingContext.Provider value={isStreaming}>
        <div
          className={`prose dark:prose-invert tight-lists prose-sm max-w-none break-words select-text${compact ? ' markdown-compact' : ''}${isStreaming && caret ? ' streaming-caret' : ''}`}
        >
          {blocks.map((block, index) => (
            <React.Fragment key={index}>
              {/* The newline one parse leaves between top-level blocks. */}
              {index > 0 && '\n'}
              <MarkdownBlock content={block} components={components} />
            </React.Fragment>
          ))}
        </div>
      </MarkdownStreamingContext.Provider>
    );
  }
);

MarkdownRenderer.displayName = 'MarkdownRenderer';
