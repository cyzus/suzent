import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { I18nProvider } from '../../i18n';
import { VersionCard } from './AboutTab';

function render(props: React.ComponentProps<typeof VersionCard>): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <VersionCard {...props} />
    </I18nProvider>
  );
}

describe('VersionCard', () => {
  it('shows the commit under the version, matching `suzent --version`', () => {
    const html = render({
      label: 'Python backend',
      value: 'v0.10.0',
      commit: '1234abcd',
      tone: 'blue',
    });

    expect(html).toContain('v0.10.0');
    expect(html).toContain('1234abcd');
  });

  it('marks a development build', () => {
    const html = render({
      label: 'Python backend',
      value: 'v0.10.0',
      commit: '1234abcd',
      badge: 'Development build',
      tone: 'blue',
    });

    expect(html).toContain('Development build');
  });

  it('renders the version alone when there is no commit or badge', () => {
    const html = render({ label: 'Desktop frontend', value: 'v0.10.0', tone: 'yellow' });

    expect(html).toContain('v0.10.0');
    expect(html).not.toContain('Development build');
  });

  it('does not render an empty commit line', () => {
    const html = render({
      label: 'Python backend',
      value: 'Unavailable',
      commit: null,
      badge: null,
      tone: 'red',
    });

    expect(html).toContain('Unavailable');
    expect(html).not.toContain('text-neutral-500');
  });
});
