import React from 'react';
import type { A2UIText } from '../../../types/a2ui';
import { MarkdownRenderer } from '../../chat/MarkdownRenderer';

interface Props { component: A2UIText; }

function looksLikeMarkdown(input: string): boolean {
  const text = input.trim();
  if (!text) return false;
  return (
    text.includes('```') ||
    /^#{1,6}\s/m.test(text) ||
    /^\s*[-*+]\s+/m.test(text) ||
    /^\s*\d+\.\s+/m.test(text) ||
    /\[[^\]]+\]\([^\)]+\)/.test(text) ||
    /^>\s+/m.test(text) ||
    /\|.+\|/.test(text) ||
    /\*\*[^*]+\*\*/.test(text) ||
    /\*[^*\n]+\*/.test(text)
  );
}

export const A2UITextComponent: React.FC<Props> = ({ component }) => {
  const { variant = 'body', markdown = false } = component;
  const rawContent = component.content ?? (component as any).text ?? (component as any).value ?? '';
  // Normalize literal \n sequences the LLM sometimes emits instead of real newlines
  const content = typeof rawContent === 'string' ? rawContent.replace(/\\n/g, '\n') : rawContent;
  const shouldRenderMarkdown = (markdown || looksLikeMarkdown(content)) && variant !== 'code';

  if (shouldRenderMarkdown) {
    return (
      <div className="text-sm text-brutal-black dark:text-neutral-200 leading-relaxed">
        <MarkdownRenderer content={content} />
      </div>
    );
  }

  switch (variant) {
    case 'heading':
      return <h2 className="text-xl font-brutal font-black text-brutal-black dark:text-white mb-2">{content}</h2>;
    case 'subheading':
      return <h3 className="text-base font-bold text-brutal-black dark:text-white mb-1">{content}</h3>;
    case 'caption':
      return <p className="text-xs text-neutral-500 dark:text-neutral-400">{content}</p>;
    case 'code':
      return (
        <pre className="bg-neutral-100 dark:bg-zinc-800 border-2 border-brutal-black p-3 text-xs font-mono overflow-x-auto">
          <code>{content}</code>
        </pre>
      );
    default:
      return <p className="text-sm text-brutal-black dark:text-neutral-200 leading-relaxed">{content}</p>;
  }
};
