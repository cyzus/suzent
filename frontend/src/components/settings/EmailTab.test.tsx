import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../../i18n';
import { EmailTab } from './EmailTab';

describe('Email settings', () => {
  it('asks to turn the plugin on before showing mailboxes', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <EmailTab />
      </I18nProvider>
    );
    expect(html).toContain('Turn on the Email plugin');
    expect(html).not.toContain('Connect a mailbox');
    expect(html).not.toContain('settings.email.');
  });
});
