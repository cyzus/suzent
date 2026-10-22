import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../../i18n';
import { MarkdownRenderer } from './MarkdownRenderer';

function render(
  content: string,
  props: Partial<React.ComponentProps<typeof MarkdownRenderer>> = {}
): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <MarkdownRenderer content={content} onFileClick={() => undefined} {...props} />
    </I18nProvider>
  );
}

vi.mock('dompurify', () => ({ default: { sanitize: (html: string) => html } }));

describe('MarkdownRenderer', () => {
  it('renders bracket-delimited display math from model replies', () => {
    const html = render(String.raw`渲染效果：
\[
(13-13)\times 11+4!=24
\]`);
    expect(html).toContain('class="katex-display"');
    expect(html).toContain('×');
  });

  it('renders parenthesized inline math', () => {
    const html = render(String.raw`Formula: \(\frac{a}{b}\) done.`);
    expect(html).toContain('<mfrac>');
    expect(html).not.toContain('class="katex-display"');
  });

  it('preserves LaTeX delimiters inside code and escaped delimiters', () => {
    const html = render('`\\(x\\)`\n\n```text\n\\[x\\]\n```\n\n\\\\(x\\\\)');
    expect(html).not.toContain('class="katex"');
    expect(html).toContain('\\(x\\)');
    expect(html).toContain('\\[x\\]');
  });

  it('renders inline and display math with accessible MathML', () => {
    const html = render('Energy: $E = mc^2$\n\n$$\n\\frac{a}{b}\n$$');

    expect(html).toContain('class="katex"');
    expect(html).toContain('class="katex-display"');
    expect(html).toContain('<math');
    expect(html).toContain('<mfrac>');
  });

  it('leaves math inside code and escaped dollar signs unchanged', () => {
    const html = render('`$x^2$`\n\n```text\n$$x^2$$\n```\n\nCost: \\$5');

    expect(html).not.toContain('class="katex"');
    expect(html).toContain('$x^2$');
    expect(html).toContain('Cost: $5');
  });

  it('keeps prices readable alongside inline math', () => {
    const html = render('Prices: $100 and $200. Formula: $x^2$. Also $123+4$.');
    const singlePrice = render('Price: $100.');

    expect(html).toContain('$100 and $200');
    expect(html).toContain('class="katex"');
    expect(html).not.toContain('100and');
    expect(singlePrice).toContain('$100');
    expect(singlePrice).not.toContain('class="katex"');
  });

  it('keeps invalid math readable without breaking the message', () => {
    const html = render('Before $\\invalidcommand{x}$ after');

    expect(html).toContain('\\invalidcommand');
    expect(html).toContain('Before');
    expect(html).toContain('after');
  });

  it('uses nested markdown link text for file buttons', () => {
    const html = render(
      '已完成深度调研，并整理成文档：[`docs/paper/RELATED_WORK_RESEARCH.md`](file:///D:/workspace/enoxian/docs/paper/RELATED_WORK_RESEARCH.md)'
    );

    expect(html).toContain('docs/paper/RELATED_WORK_RESEARCH.md');
    expect(html).not.toContain('[object Object]');
  });

  it('uses sidebar-sized headings in compact streaming mode', () => {
    const html = render('# Project context', { isStreaming: true, compact: true });

    expect(html).toContain('markdown-compact');
    expect(html).toBe(render('# Project context', { compact: true }));
  });
  it.each([
    '# Heading\nBody without a blank line',
    '*emphasis* and **bold** and ~~deleted~~',
    '- parent\n  - child\n\n1. first\n2. second',
    '> quoted text\n\n---',
    '[website](https://example.com) and [file](file:///workspace/test.txt)',
    '| Left | Right |\n| :--- | ---: |\n| one | two |',
    '```python\nprint("hello")\n```',
    '```python\nprint("partial")',
    'Inline $x^2$ and display:\n\n$$\n\\sum_{i=1}^{n} i\n$$',
    'Partial $\\frac{x}{',
    String.raw`\[ (13-13)\times 11+4!=24 \]`,
    String.raw`Partial \(\frac{x}{`,
  ])('keeps streaming and completed markup identical for %s', (content) => {
    expect(render(content, { isStreaming: true })).toBe(render(content));
  });

  it('defers HTML previews until streaming finishes', () => {
    const content = '```html\n<strong>Preview</strong>\n```';
    expect(render(content, { isStreaming: true })).toContain('&lt;strong&gt;');
    expect(render(content)).toContain('<strong>Preview</strong>');
  });
});
