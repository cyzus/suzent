import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { I18nProvider } from '../../i18n';
import { commitUrl } from '../../lib/desktopAbout';
import { AboutDetailRow } from './AboutTab';

function render(props: React.ComponentProps<typeof AboutDetailRow>): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <AboutDetailRow {...props} />
    </I18nProvider>
  );
}

describe('AboutDetailRow', () => {
  it('shows a label and value for install identity fields', () => {
    const html = render({
      label: 'Connected backend',
      value: 'v0.10.0',
    });

    expect(html).toContain('Connected backend');
    expect(html).toContain('v0.10.0');
  });

  it('marks a development build', () => {
    const html = render({
      label: 'Connected backend',
      value: 'v0.10.0',
      badge: 'Development build',
    });

    expect(html).toContain('Development build');
  });

  it('renders a linked commit value', () => {
    const html = render({
      label: 'Commit',
      value: <a href={commitUrl('abcdef12')}>abcdef12</a>,
    });

    expect(html).toContain('abcdef12');
    expect(html).toContain('https://github.com/cyzus/suzent/commit/abcdef12');
  });
});
