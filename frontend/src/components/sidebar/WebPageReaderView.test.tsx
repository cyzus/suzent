import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../../i18n';
import { WebPageReaderView } from './WebPageReaderView';

describe('web page reading view', () => {
  it('loads the source URL in the embedded page instead of a browser preview stream', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <WebPageReaderView markdown="# Extracted text" url="https://example.com/article" />
      </I18nProvider>
    );

    expect(html).toContain('src="https://example.com/article"');
    expect(html).toContain('<iframe');
    expect(html).not.toContain('Waiting for preview');
  });

  it('renders only the Markdown message from a tool result without an extra copy button', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <WebPageReaderView
          markdown={JSON.stringify({
            success: true,
            message: '# Page title\n\n**Important**',
            metadata: { url: 'https://example.com' },
          })}
        />
      </I18nProvider>
    );

    expect(html).toContain('<h1');
    expect(html).toContain('<strong>Important</strong>');
    expect(html).not.toContain('&quot;metadata&quot;');
    expect(html).not.toContain('aria-label="Copy to clipboard"');
  });
});
