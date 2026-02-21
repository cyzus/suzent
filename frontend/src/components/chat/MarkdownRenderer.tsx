import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypePrism from 'rehype-prism-plus';
import { CodeBlockComponent } from './CodeBlockComponent';
import { ClickableContent } from '../ClickableContent';
import { DocumentTextIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';

const ALLOWED_LANGUAGES = new Set([
  'python', 'javascript', 'typescript', 'java', 'cpp', 'c', 'go', 'rust', 'sql',
  'html', 'css', 'json', 'yaml', 'xml', 'bash', 'shell', 'powershell', 'php',
  'ruby', 'swift', 'kotlin', 'dart', 'r', 'matlab', 'scala', 'perl', 'lua',
  'haskell', 'clojure', 'elixir', 'erlang', 'fsharp', 'ocaml', 'pascal',
  'fortran', 'cobol', 'assembly', 'asm', 'text', 'plain'
]);

interface MarkdownRendererProps {
  content: string;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
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
      className="inline-flex items-center gap-1 bg-brutal-yellow border-2 border-brutal-black px-2 py-0.5 font-mono text-xs font-bold text-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] brutal-btn transition-all cursor-pointer"
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
      <DocumentTextIcon className="w-3 h-3 stroke-[3]" />
      <span>{displayName}</span>
    </span>
  );
};

export const MarkdownRenderer = React.memo<MarkdownRendererProps>(({ content, onFileClick }) => {
  const RM: any = ReactMarkdown;

  // Normalize content
  const normalized = String(content)
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/^\n+/, '')
    .replace(/\n+$/, '');

  // Sanitize code block languages
  const sanitized = normalized.replace(/```\s*([^\n`]*)/g, (_m, info) => {
    const token = String(info || '').trim().split(/\s+/)[0] || '';
    const clean = token.replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();
    return ALLOWED_LANGUAGES.has(clean) ? `\`\`\`${clean}` : '```';
  });

  // Safe URL transform - block dangerous protocols while allowing file:// and standard protocols
  const safeUrlTransform = (url: string): string => {
    const urlLower = url.toLowerCase().trim();

    // Allow safe protocols
    const safeProtocols = ['http:', 'https:', 'mailto:', 'file:', 'tel:'];
    const hasProtocol = urlLower.includes(':');

    if (hasProtocol) {
      const isAllowed = safeProtocols.some(protocol => urlLower.startsWith(protocol));
      if (!isAllowed) {
        // Block dangerous protocols like javascript:, data:, vbscript:, etc.
        return '';
      }
    }

    // Allow relative URLs and fragment links
    return url;
  };

  return (
    <div className="prose tight-lists prose-sm max-w-none break-words select-text">
      <RM
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypePrism]}
        urlTransform={safeUrlTransform}
        components={{
          pre: (p: any) => {
            if (p.node?.children?.length === 1 && p.node.children[0].tagName === 'code') {
              return <>{p.children}</>;
            }
            return (
              <div className="bg-neutral-50 p-4 overflow-x-auto">
                <pre className="font-mono text-xs text-brutal-black leading-relaxed whitespace-pre-wrap break-all">
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

            // Detect if this is inline code (no language and not in a <pre> parent)
            const isInline = inline !== false && !lang;

            const isText = !lang || lang === 'text';
            const isSingleLine = !codeContent.includes('\n');
            const isShort = codeContent.length < 60;

            // Check if inline code contains a file path pattern
            if (isInline && onFileClick) {
              // Pattern 1: Markdown file:// link in backticks: `[text](file:///path)`
              const fileLinkMatch = codeContent.match(/^\[([^\]]+)\]\(file:\/\/([^\)]+)\)$/);
              if (fileLinkMatch) {
                const [, displayName, path] = fileLinkMatch;
                return <FileButton path={path} displayName={displayName} onFileClick={onFileClick} />;
              }

              // Pattern 2: Plain absolute path in backticks: `/persistence/file.txt`
              const absolutePathMatch = codeContent.match(/^\/[\w\-./]+\.\w{2,5}$/);
              if (absolutePathMatch) {
                const path = codeContent.trim();
                return <FileButton path={path} displayName={path} onFileClick={onFileClick} />;
              }
            }

            if (!isInline && !(isText && isSingleLine && isShort)) {
              return <CodeBlockComponent lang={lang || 'text'} content={codeContent} />;
            }
            return (
              <code
                className="bg-brutal-yellow px-1.5 py-0.5 border-2 border-brutal-black text-[11px] font-mono text-brutal-black font-bold break-words"
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
            if (onFileClick && (hrefStr.startsWith('file://') || hrefStr.startsWith('/persistence/') || hrefStr.startsWith('/mnt/'))) {
              const path = hrefStr.startsWith('file://') ? hrefStr.replace('file://', '') : hrefStr;
              return <FileButton path={path} displayName={String(children)} onFileClick={onFileClick} />;
            }

            // Regular external links
            return (
              <a
                href={hrefStr}
                target="_blank"
                rel="noopener noreferrer"
                className="text-brutal-blue hover:bg-brutal-yellow font-bold underline break-words transition-colors duration-100"
              >
                {children}
              </a>
            );
          },
          table: (p: any) => (
            <div className="overflow-x-auto">
              <table className="text-xs border-3 border-brutal-black">{p.children}</table>
            </div>
          ),
          th: (p: any) => <th className="border-2 border-brutal-black px-2 py-1 bg-brutal-yellow font-bold">{p.children}</th>,
          td: (p: any) => <td className="border-2 border-brutal-black px-2 py-1 align-top">{p.children}</td>,
          ul: (p: any) => <ul className="list-disc pl-5">{p.children}</ul>,
          ol: (p: any) => <ol className="list-decimal pl-5">{p.children}</ol>,
          h1: (p: any) => <h1 className="text-xl font-brutal font-bold mb-2 break-words uppercase">{p.children}</h1>,
          h2: (p: any) => <h2 className="text-lg font-brutal font-bold mb-2 break-words uppercase">{p.children}</h2>,
          h3: (p: any) => <h3 className="text-base font-bold mb-1 break-words uppercase">{p.children}</h3>,
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

            // Apply ClickableContent for plain text paragraphs to detect file paths
            if (isSimpleText && onFileClick) {
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

            return <p className="leading-relaxed break-words whitespace-pre-wrap m-0">{pArg.children}</p>;
          },
          blockquote: (p: any) => (
            <blockquote className="border-l-4 border-brutal-black pl-3 italic text-neutral-600 break-words bg-neutral-50 py-1 pr-2">
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
