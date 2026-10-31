import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { I18nProvider } from '../i18n';
import { CubeLoadingIndicator } from './CubeLoadingIndicator';
import { LoadingIndicator } from './chat/StatusMessages';

describe('CubeLoadingIndicator', () => {
  it('renders 3 stacked cube units for settings loading', () => {
    const html = renderToStaticMarkup(
      <CubeLoadingIndicator variant="settings" label="Loading configuration..." />
    );

    expect(html).toContain('cube-loading-settings');
    expect(html).toContain('Loading configuration...');
    expect(html.match(/class="cube-loading-unit"/g)).toHaveLength(3);
  });

  it('renders 4 hopping cube units for skills loading', () => {
    const html = renderToStaticMarkup(
      <CubeLoadingIndicator variant="skills" label="Loading skills..." />
    );

    expect(html).toContain('cube-loading-skills');
    expect(html).toContain('Loading skills...');
    expect(html.match(/class="cube-loading-unit"/g)).toHaveLength(4);
  });
});

describe('LoadingIndicator', () => {
  it('renders the 8-part 3D core connection cube cluster', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <LoadingIndicator />
      </I18nProvider>
    );

    expect(html).toContain('core-connection-cluster');
    expect(html.match(/class="core-connection-part"/g)).toHaveLength(8);
  });
});
