import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../../i18n';
import { ToolCallBlock } from './ToolCallBlock';

function renderOutput(toolName: string, output: string): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <ToolCallBlock toolName={toolName} output={output} defaultCollapsed={false} />
    </I18nProvider>
  );
}

const markdown =
  '# Page title\n\n**Important**\n\n| Name | Value |\n| --- | --- |\n| Example | 42 |';

describe('web fetch output', () => {
  it.each(['webpage_fetch', 'WebFetch', 'webfetch', 'web_fetch'])(
    'renders raw Markdown including GFM tables for %s',
    (toolName) => {
      const html = renderOutput(toolName, markdown);
      expect(html).toContain('<h1');
      expect(html).toContain('<strong>Important</strong>');
      expect(html).toContain('<table');
      expect(html).not.toContain('| --- |');
    }
  );

  it('unwraps a ToolResult before rendering Markdown', () => {
    const html = renderOutput(
      'webpage_fetch',
      JSON.stringify({ success: true, message: markdown, metadata: { url: 'https://example.com' } })
    );
    expect(html).toContain('<h1');
    expect(html).toContain('<table');
    expect(html).not.toContain('&quot;message&quot;');
    expect(html).not.toContain('&quot;metadata&quot;');
  });

  it('displays the error message without its envelope', () => {
    const html = renderOutput(
      'WebFetch',
      JSON.stringify({ success: false, message: 'Unable to fetch page.', error_code: 'FAILED' })
    );
    expect(html).toContain('Unable to fetch page.');
    expect(html).not.toContain('&quot;error_code&quot;');
  });
});

it.each(['web_search', 'WebSearch'])('preserves search result cards for %s', (toolName) => {
  const html = renderOutput(
    toolName,
    JSON.stringify({
      success: true,
      message: JSON.stringify({
        results: [
          { title: 'Search hit', url: 'https://example.com/page', description: 'A result' },
        ],
      }),
    })
  );
  expect(html).toContain('href="https://example.com/page"');
  expect(html).toContain('Search hit');
  expect(html).toContain('A result');
  expect(html).not.toContain('&quot;message&quot;');
});
