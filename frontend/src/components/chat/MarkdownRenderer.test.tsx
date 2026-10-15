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
  ])('keeps streaming and completed markup identical for %s', (content) => {
    expect(render(content, { isStreaming: true })).toBe(render(content));
  });

  it('defers HTML previews until streaming finishes', () => {
    const content = '```html\n<strong>Preview</strong>\n```';
    expect(render(content, { isStreaming: true })).toContain('&lt;strong&gt;');
    expect(render(content)).toContain('<strong>Preview</strong>');
  });
});
