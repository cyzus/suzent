import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../../i18n';
import { EmailTab } from './EmailTab';

describe('Email settings', () => {
  it('renders its labels and an empty account list', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <EmailTab />
      </I18nProvider>
    );
    expect(html).toContain('Connect a mailbox');
    expect(html).toContain('No mailbox connected');
    expect(html).not.toContain('settings.email.');
  });
});
