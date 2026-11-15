import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../../i18n';
import { FilePreviewHeader } from './SandboxFiles';

describe('FilePreviewHeader', () => {
  it('renders an unframed filename and a trailing close button instead of a left back arrow', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <FilePreviewHeader
          filename="report.md"
          canMaximize
          onClose={() => undefined}
          onReveal={() => undefined}
          onCopyLocation={() => undefined}
          onMaximize={() => undefined}
        />
      </I18nProvider>
    );
    expect(html).toContain('report.md');
    expect(html).toContain('aria-label="Close preview"');
    expect(html).not.toContain('title="Back"');
    expect(html).not.toContain('shadow-brutal-sm');
  });
});
