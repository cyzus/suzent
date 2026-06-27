import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CodeBlockComponent } from './CodeBlockComponent';
import { ClickableContent } from '../ClickableContent';
import {
  hasCitationMarker,
  renderTextWithCitations,
  useCitationSources,
  type CitationSourcesMap,
} from './Citations';
import { DocumentTextIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { getApiBase } from '../../lib/api';

const ALLOWED_LANGUAGES = new Set([
  'python', 'javascript', 'typescript', 'java', 'cpp', 'c', 'go', 'rust', 'sql',
  'html', 'css', 'json', 'yaml', 'xml', 'bash', 'shell', 'powershell', 'php',
  'ruby', 'swift', 'kotlin', 'dart', 'r', 'matlab', 'scala', 'perl', 'lua',
  'haskell', 'clojure', 'elixir', 'erlang', 'fsharp', 'ocaml', 'pascal',
  'fortran', 'cobol', 'assembly', 'asm', 'text', 'plain'
]);

export function sanitizeMarkdownCodeFenceLanguages(markdown: string): string {
  const repairedLooseUrlFences = markdown.replace(
    /^([ \t]{0,3})`{1,2}(https?:\/\/[^\n`]+)\n[ \t]*`{1,2}[ \t]*$/gm,
    '$1```\n$2\n$1```',
  );

  return repairedLooseUrlFences.replace(/^([ \t]{0,3}```)[ \t]*([^\n`]*)/gm, (_m, fence, info) => {
    const token = String(info || '').trim().split(/\s+/)[0] || '';
    const clean = token.replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();
    return ALLOWED_LANGUAGES.has(clean) ? `${fence}${clean}` : fence;
  });
}

interface MarkdownRendererProps {
  content: string;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
  streamingLite?: boolean;
}

function encodePathSegments(path: string): string {
  return path
    .split('/')
    .filter(Boolean)
    .map(segment => encodeURIComponent(segment))
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
    return suzentSessionFileUrlToServeUrl(trimmed) || '';
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
      className="inline-flex max-w-full items-center gap-1 bg-brutal-yellow border-2 border-brutal-black px-2 py-0.5 font-mono text-xs font-bold text-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] brutal-btn transition-all cursor-pointer"
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
    const props = children.props as { children?: React.ReactNode };
    if (props.children) return extractCodeText(props.children);
  }
  return children == null ? '' : String(children);
}

function renderLiteInline(text: string, sourcesMap?: CitationSourcesMap | null): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const pattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  // Plain-text segments are routed through the citation splitter so [[cite:..]]
  // markers become badges; code/bold tokens pass through untouched.
  const pushText = (value: string, key: string) => {
    if (sourcesMap && hasCitationMarker(value)) {
      nodes.push(...renderTextWithCitations(value, sourcesMap, key));
    } else {
      nodes.push(value);
    }
  };

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      pushText(text.slice(lastIndex, match.index), `lite-${lastIndex}`);
    }

    const token = match[0];
    if (token.startsWith('`')) {
      nodes.push(
        <code key={`code-${match.index}`} className="bg-brutal-yellow px-1.5 py-0.5 border border-brutal-black text-[11px] font-mono text-brutal-black font-bold break-words whitespace-pre-wrap box-decoration-clone">
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      nodes.push(<strong key={`strong-${match.index}`}>{token.slice(2, -2)}</strong>);
    }

    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    pushText(text.slice(lastIndex), `lite-${lastIndex}`);
  }

  return nodes;
}

const LiteCodeBlock: React.FC<{ lang?: string; content: string }> = ({ lang, content }) => {
  const safeLang = (lang || 'text').replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();
  const lineCount = content ? content.split('\n').length : 1;

  return (
    <div className="my-3 font-mono text-sm border-2 border-brutal-black dark:border-zinc-500 bg-white dark:bg-zinc-900 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-brutal-black dark:bg-zinc-800 border-b-2 border-brutal-black dark:border-zinc-500">
        <span className="text-white dark:text-brutal-yellow font-black uppercase text-[10px] truncate">{safeLang}</span>
        <span className="text-white/55 dark:text-neutral-400 text-[10px] font-bold shrink-0">{lineCount} lines</span>
      </div>
      <pre className="max-w-full text-[12px] text-brutal-black dark:text-neutral-100 px-3 py-2.5 leading-5 overflow-x-auto !bg-transparent whitespace-pre font-mono m-0">
        <code>{content}</code>
      </pre>
    </div>
  );
};

function splitLiteTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  return trimmed.split('|').map(cell => cell.trim());
}

function isLiteTableSeparator(line: string): boolean {
  const cells = splitLiteTableRow(line);
  return cells.length > 0 && cells.every(cell => /^:?-{3,}:?$/.test(cell));
}

const LiteTable: React.FC<{ lines: string[]; sourcesMap?: CitationSourcesMap | null }> = ({ lines, sourcesMap }) => {
  const headers = splitLiteTableRow(lines[0] || '');
  const rows = lines.slice(2).map(splitLiteTableRow);

  return (
    <div className="overflow-x-auto">
      <table className="text-xs border-2 border-brutal-black dark:border-zinc-500 bg-white dark:bg-zinc-900">
        <thead>
          <tr>
            {headers.map((header, idx) => (
              <th key={idx} className="border-2 border-brutal-black dark:border-zinc-500 px-2 py-1 bg-brutal-yellow text-brutal-black font-black uppercase text-left align-top">
                {renderLiteInline(header, sourcesMap)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIdx) => (
            <tr key={rowIdx}>
              {headers.map((_header, colIdx) => (
                <td key={colIdx} className="border-2 border-brutal-black dark:border-zinc-500 px-2 py-1 align-top text-brutal-black dark:text-neutral-100">
                  {renderLiteInline(row[colIdx] ?? '', sourcesMap)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const LiteMarkdownRenderer: React.FC<{ content: string }> = ({ content }) => {
  const sourcesMap = useCitationSources();
  const parts: React.ReactNode[] = [];
  const fencePattern = /```([a-zA-Z0-9_-]*)[ \t]*\n?([\s\S]*?)(?:```|$)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  const pushText = (value: string, keyPrefix: string) => {
    const lines = value.split('\n');
    let paragraph: string[] = [];

    const flushParagraph = () => {
      const text = paragraph.join('\n').trim();
      paragraph = [];
      if (!text) return;

      const key = `${keyPrefix}-p-${parts.length}`;
      const multilineInlineCode = text.match(/^`([\s\S]*)`$/);
      if (multilineInlineCode?.[1]?.includes('\n')) {
        parts.push(<LiteCodeBlock key={key} lang="text" content={multilineInlineCode[1].replace(/^\n|\n$/g, '')} />);
        return;
      }

      if (/^#{1,3}\s+/.test(text)) {
        const level = text.match(/^#+/)?.[0].length ?? 3;
        const body = text.replace(/^#{1,3}\s+/, '');
        const className = level === 1
          ? 'text-xl font-brutal font-bold mb-2 break-words uppercase'
          : level === 2
            ? 'text-lg font-brutal font-bold mb-2 break-words uppercase'
            : 'text-base font-bold mb-1 break-words uppercase';
        parts.push(<div key={key} className={className}>{renderLiteInline(body, sourcesMap)}</div>);
        return;
      }

      parts.push(<p key={key} className="leading-relaxed break-words whitespace-pre-wrap m-0">{renderLiteInline(text, sourcesMap)}</p>);
    };

    for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
      const line = lines[lineIndex];
      if (!line.trim()) {
        flushParagraph();
        continue;
      }

      if (
        line.includes('|') &&
        lineIndex + 1 < lines.length &&
        isLiteTableSeparator(lines[lineIndex + 1])
      ) {
        flushParagraph();
        const tableLines = [line, lines[lineIndex + 1]];
        lineIndex += 2;
        while (lineIndex < lines.length && lines[lineIndex].trim() && lines[lineIndex].includes('|')) {
          tableLines.push(lines[lineIndex]);
          lineIndex++;
        }
        lineIndex--;
        parts.push(<LiteTable key={`${keyPrefix}-table-${parts.length}`} lines={tableLines} sourcesMap={sourcesMap} />);
        continue;
      }

      const ordered = line.match(/^\s*(\d+)\.\s+(.+)$/);
      const bullet = line.match(/^\s*[-*]\s+(.+)$/);
      if (ordered || bullet) {
        flushParagraph();
        const body = ordered?.[2] ?? bullet?.[1] ?? line;
        parts.push(
          <div key={`${keyPrefix}-li-${parts.length}-${lineIndex}`} className="flex gap-2 leading-relaxed">
            <span className="shrink-0 text-neutral-500">{ordered ? `${ordered[1]}.` : '•'}</span>
            <span className="min-w-0 break-words">{renderLiteInline(body, sourcesMap)}</span>
          </div>,
        );
        continue;
      }

      paragraph.push(line);
    }

    flushParagraph();
  };

  while ((match = fencePattern.exec(content)) !== null) {
    if (match.index > lastIndex) {
      pushText(content.slice(lastIndex, match.index), `text-${lastIndex}`);
    }
    parts.push(<LiteCodeBlock key={`code-${match.index}`} lang={match[1] || 'text'} content={(match[2] || '').replace(/\n$/, '')} />);
    lastIndex = fencePattern.lastIndex;
  }

  if (lastIndex < content.length) {
    pushText(content.slice(lastIndex), `text-${lastIndex}`);
  }

  return <div className="prose dark:prose-invert tight-lists prose-sm max-w-none break-words select-text space-y-3">{parts}</div>;
};

export const MarkdownRenderer = React.memo<MarkdownRendererProps>(({ content, onFileClick, streamingLite = false }) => {
  const RM: any = ReactMarkdown;
  const sourcesMap = useCitationSources();
  const openingLinksRef = React.useRef(new Map<string, number>());

  const isExternalLink = React.useCallback((href: string): boolean => {
    return /^(https?:|mailto:|tel:)/i.test(href.trim());
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
  const applyCitations = React.useCallback((children: React.ReactNode, keyPrefix: string): React.ReactNode => {
    if (!sourcesMap) return children;

    const walk = (child: React.ReactNode, key: string): React.ReactNode => {
      if (typeof child === 'string' && hasCitationMarker(child)) {
        return renderTextWithCitations(child, sourcesMap, key);
      }
      if (React.isValidElement(child) && child.props?.children) {
        if (child.type === 'code' || child.props?.node?.tagName === 'code') {
          return child;
        }
        const nextChildren = React.Children.map(child.props.children, (nested, i) =>
          walk(nested, `${key}-${i}`),
        );
        return React.cloneElement(child as React.ReactElement<any>, undefined, nextChildren);
      }
      return child;
    };

    const arr = React.Children.toArray(children);
    if (!arr.some(c => typeof c === 'string' ? hasCitationMarker(c) : React.isValidElement(c))) {
      return children;
    }
    return arr.map((child, i) => walk(child, `${keyPrefix}-${i}`));
  }, [sourcesMap]);

  // Normalize content
  const normalized = String(content)
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/^\n+/, '')
    .replace(/\n+$/, '');

  // Sanitize code block languages
  const sanitized = sanitizeMarkdownCodeFenceLanguages(normalized);

  if (streamingLite) {
    return <LiteMarkdownRenderer content={sanitized} />;
  }

  // Safe URL transform - block dangerous protocols while allowing standard protocols.
  // Suzent-owned file:// session paths are rewritten to /sandbox/serve URLs.
  const safeUrlTransform = (url: string): string => {
    const normalizedUrl = normalizeMarkdownUrl(url);
    const urlLower = normalizedUrl.toLowerCase().trim();

    // Allow safe protocols
    const safeProtocols = ['http:', 'https:', 'mailto:', 'tel:'];
    const hasProtocol = urlLower.includes(':');

    if (urlLower.startsWith('data:image/')) {
      return /^data:image\/(?:png|jpe?g|gif|webp|svg\+xml);base64,/i.test(normalizedUrl)
        ? normalizedUrl
        : '';
    }

    if (hasProtocol) {
      const isAllowed = safeProtocols.some(protocol => urlLower.startsWith(protocol));
      if (!isAllowed) {
        // Block dangerous protocols like javascript:, unsupported data:, vbscript:, etc.
        return '';
      }
    }

    // Allow relative URLs and fragment links
    return normalizedUrl;
  };

  return (
    <div className="prose dark:prose-invert tight-lists prose-sm max-w-none break-words select-text">
      <RM
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[]}
        urlTransform={safeUrlTransform}
        components={{
          pre: (p: any) => {
            if (p.node?.children?.length === 1 && p.node.children[0].tagName === 'code') {
              const child = React.Children.toArray(p.children)[0];
              const className = React.isValidElement(child)
                ? String((child.props as { className?: string }).className || '')
                : '';
              const match = /language-([a-zA-Z0-9_-]+)/.exec(className);
              const codeContent = extractCodeText(p.children).replace(/\n$/, '');

              return <CodeBlockComponent lang={match?.[1] || 'text'} content={codeContent} />;
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

            // Extract text content
            const extractCodeText = (children: any): string => {
              if (typeof children === 'string') return children;
              if (Array.isArray(children)) return children.map(extractCodeText).join('');
              if (React.isValidElement(children)) {
                const props = children.props as any;
                if (props?.children) {
                  return extractCodeText(props.children);
                }
              }
              return String(children);
            };

            const codeContent = extractCodeText(children).replace(/\n$/, '');

            // Detect if this is inline code (no language and not in a <pre> parent).
            // Some models wrap multi-line ASCII diagrams in a single backtick span;
            // render those as blocks so they don't become a stack of inline chips.
            const isMultilineInlineCode = !lang && codeContent.includes('\n');
            const isInline = inline !== false && !lang && !isMultilineInlineCode;

            if (isInline && sourcesMap && hasCitationMarker(codeContent)) {
              return <>{renderTextWithCitations(codeContent, sourcesMap, 'code')}</>;
            }

            // Check if inline code contains a file path pattern
            if (isInline && onFileClick) {
              // Pattern 1: Markdown file:// link in backticks: `[text](file:///path)`
              const fileLinkMatch = codeContent.match(/^\[([^\]]+)\]\(file:\/\/([^\)]+)\)$/);
              if (fileLinkMatch) {
                const [, displayName, path] = fileLinkMatch;
                return <FileButton path={path} displayName={displayName} onFileClick={onFileClick} />;
              }

              // Pattern 2: Plain absolute path in backticks: `/workspace/file.txt`
              const absolutePathMatch = codeContent.match(/^\/(workspace|shared|mnt)\/[\w\-./]+\.\w{2,5}$/);
              if (absolutePathMatch) {
                const path = codeContent.trim();
                return <FileButton path={path} displayName={path} onFileClick={onFileClick} />;
              }
            }

            if (isMultilineInlineCode || !isInline) {
              if (streamingLite) {
                return (
                  <pre className="bg-neutral-50 dark:bg-zinc-900 border border-neutral-300 dark:border-zinc-700 px-3 py-2.5 overflow-x-auto font-mono text-[12px] text-neutral-800 dark:text-neutral-200 leading-5 whitespace-pre-wrap break-all">
                    <code>{codeContent}</code>
                  </pre>
                );
              }
              return <CodeBlockComponent lang={lang || 'text'} content={codeContent} />;
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
            if (onFileClick && (hrefStr.startsWith('file://') || hrefStr.startsWith('/workspace/') || hrefStr.startsWith('/shared/') || hrefStr.startsWith('/mnt/'))) {
              const path = hrefStr.startsWith('file://') ? hrefStr.replace('file://', '') : hrefStr;
              return <FileButton path={path} displayName={String(children)} onFileClick={onFileClick} />;
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
              <img
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
              <table className="text-xs border-3 border-brutal-black">{p.children}</table>
            </div>
          ),
          th: (p: any) => <th className="border-2 border-brutal-black px-2 py-1 bg-brutal-yellow font-bold">{applyCitations(p.children, 'th')}</th>,
          td: (p: any) => <td className="border-2 border-brutal-black px-2 py-1 align-top">{applyCitations(p.children, 'td')}</td>,
          ul: (p: any) => <ul className="list-disc pl-5">{p.children}</ul>,
          ol: (p: any) => <ol className="list-decimal pl-5">{p.children}</ol>,
          li: (p: any) => <li>{applyCitations(p.children, 'li')}</li>,
          h1: (p: any) => <h1 className="text-xl font-brutal font-bold mb-2 break-words uppercase">{applyCitations(p.children, 'h1')}</h1>,
          h2: (p: any) => <h2 className="text-lg font-brutal font-bold mb-2 break-words uppercase">{applyCitations(p.children, 'h2')}</h2>,
          h3: (p: any) => <h3 className="text-base font-bold mb-1 break-words uppercase">{applyCitations(p.children, 'h3')}</h3>,
          p: (pArg: any) => {
            const text = String(pArg.children?.[0] || '');
            if (text.startsWith('Step: ') && text.includes('tokens')) {
              return (
                <p className="flex items-center gap-3 text-xs sm:text-sm text-brutal-black border-4 border-brutal-black pt-4 pb-3 mt-6 font-mono font-black break-words whitespace-pre-wrap m-0 bg-brutal-yellow -mx-5 px-5 shadow-brutal-sm uppercase tracking-wider">
                  <span aria-hidden="true" className="text-lg leading-none">▣</span>
                  <span className="flex-1">{pArg.children}</span>
                </p>
              );
            }

            // Check if paragraph contains only simple text (for ClickableContent detection)
            const isSimpleText = React.Children.toArray(pArg.children).every(
              (child) => typeof child === 'string' ||
                (React.isValidElement(child) && (child.type === 'strong' || child.type === 'em'))
            );

            // Apply ClickableContent for plain text paragraphs to detect file
            // paths — but only when there are no citation markers, since that
            // path flattens children to a string and would drop citation badges.
            const hasCite = React.Children.toArray(pArg.children).some(
              c => typeof c === 'string' && hasCitationMarker(c),
            );
            if (isSimpleText && onFileClick && !hasCite) {
              const extractText = (children: any): string => {
                return React.Children.toArray(children)
                  .map((child) => {
                    if (typeof child === 'string') return child;
                    if (React.isValidElement(child) && child.props?.children) {
                      return extractText(child.props.children);
                    }
                    return '';
                  })
                  .join('');
              };

              const textContent = extractText(pArg.children);
              return (
                <p className="leading-relaxed break-words whitespace-pre-wrap m-0">
                  <ClickableContent content={textContent} onFileClick={onFileClick} />
                </p>
              );
            }

            return <p className="leading-relaxed break-words whitespace-pre-wrap m-0">{applyCitations(pArg.children, 'p')}</p>;
          },
          blockquote: (p: any) => (
            <blockquote className="border-l-4 border-brutal-black pl-3 italic text-neutral-600 dark:text-neutral-400 break-words bg-neutral-50 dark:bg-zinc-800 py-1 pr-2">
              {p.children}
            </blockquote>
          )
        }}
      >
        {sanitized}
      </RM>
    </div>
  );
});

MarkdownRenderer.displayName = 'MarkdownRenderer';
