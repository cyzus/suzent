import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import rehypePrism from 'rehype-prism-plus';
import { CodeBlockComponent } from './CodeBlockComponent';

const ALLOWED_LANGUAGES = new Set([
  'python', 'javascript', 'typescript', 'java', 'cpp', 'c', 'go', 'rust', 'sql',
  'html', 'css', 'json', 'yaml', 'xml', 'bash', 'shell', 'powershell', 'php',
  'ruby', 'swift', 'kotlin', 'dart', 'r', 'matlab', 'scala', 'perl', 'lua',
  'haskell', 'clojure', 'elixir', 'erlang', 'fsharp', 'ocaml', 'pascal',
  'fortran', 'cobol', 'assembly', 'asm', 'text', 'plain'
]);

interface MarkdownRendererProps {
  content: string;
}

export const MarkdownRenderer = React.memo<MarkdownRendererProps>(({ content }) => {
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

  return (
    <div className="prose tight-lists prose-sm max-w-none break-words select-text">
      <RM
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          rehypeRaw,
          [rehypeSanitize, {
            ...defaultSchema,
            tagNames: [...(defaultSchema.tagNames || []), 'details', 'summary'],
            attributes: {
              ...defaultSchema.attributes,
              details: ['open'],
              summary: [],
              code: ['className'],
              span: ['className']
            }
          }],
          rehypePrism
        ]}
        components={{
          details: (p: any) => (
            <details className="group border-3 border-brutal-black bg-white my-6 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] open:shadow-none open:translate-x-[2px] open:translate-y-[2px] transition-all overflow-hidden">
              {p.children}
            </details>
          ),
          summary: (p: any) => (
            <summary className="cursor-pointer font-mono font-bold p-3 bg-brutal-black text-white border-b-3 border-brutal-black group-open:border-b-3 list-none flex items-center justify-between select-none hover:bg-neutral-800 transition-colors uppercase tracking-wider text-xs">
              <div className="flex items-center gap-3">
                <span className="text-white transform group-open:rotate-90 transition-transform inline-block">►</span>
                <span>{p.children}</span>
              </div>
              <span className="text-[10px] text-neutral-400 group-open:hidden">CLICK TO EXPAND</span>
              <span className="text-[10px] text-neutral-400 hidden group-open:inline">SYSTEM_LOG_ACTIVE</span>
            </summary>
          ),
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
            const codeContent = String(children).replace(/\n$/, '');

            const isText = !lang || lang === 'text';
            const isSingleLine = !codeContent.includes('\n');
            const isShort = codeContent.length < 60;

            if (!inline && !(isText && isSingleLine && isShort)) {
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
          a: (p: any) => (
            <a
              href={p.href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brutal-blue hover:bg-brutal-yellow font-bold underline break-words transition-colors duration-100"
            >
              {p.children}
            </a>
          ),
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
