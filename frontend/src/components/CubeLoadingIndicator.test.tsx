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

  it('renders 4 conveyor cube units and belt track for skills loading', () => {
    const html = renderToStaticMarkup(
      <CubeLoadingIndicator variant="skills" label="Loading skills..." />
    );

    expect(html).toContain('cube-loading-skills');
    expect(html).toContain('cube-loading-belt');
    expect(html).toContain('Loading skills...');
    expect(html.match(/class="cube-loading-unit"/g)).toHaveLength(4);
  });
});

describe('LoadingIndicator', () => {
  it('renders the 7-part 3D sliding puzzle cluster with 1 open slot', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <LoadingIndicator />
      </I18nProvider>
    );

    expect(html).toContain('core-connection-cluster');
    expect(html).toContain('core-connection-part-accent');
    expect(html.match(/core-connection-part/g)?.length).toBeGreaterThanOrEqual(7);
    expect(html.match(/class="core-connection-cube"/g)).toHaveLength(7);
  });
});
