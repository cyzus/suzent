import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../../i18n';
import { MarkdownRenderer } from './MarkdownRenderer';

function render(content: string, isStreaming = true, caret = true): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <MarkdownRenderer content={content} isStreaming={isStreaming} caret={caret} />
    </I18nProvider>
  );
}

describe('streaming caret', () => {
  it('marks the container only when requested during streaming', () => {
    expect(render('hello')).toContain('streaming-caret');
    expect(render('hello', true, false)).not.toContain('streaming-caret');
    expect(render('hello', false)).not.toContain('streaming-caret');
  });

  it.each([
    'Some prose',
    '- first\n- second',
    '```python\nprint(1)',
    '| a | b |\n| --- | --- |\n| 1 | 2 |',
    '> quoted text',
  ])('adds a caret without replacing the Markdown structure for %s', (content) => {
    expect(render(content).replace(' streaming-caret', '')).toBe(render(content, false));
  });
});
