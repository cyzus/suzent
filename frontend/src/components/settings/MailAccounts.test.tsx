import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../../i18n';
import { MailAccounts } from './MailAccounts';

describe('mail accounts', () => {
  it('renders the add form with translated labels', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <MailAccounts openLink={() => {}} />
      </I18nProvider>
    );
    expect(html).toContain('Add mailbox');
    expect(html).not.toContain('settings.email.');
  });
});
