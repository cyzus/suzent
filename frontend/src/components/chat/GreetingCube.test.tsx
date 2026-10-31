import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { GreetingCube } from './GreetingCube';

describe('GreetingCube', () => {
  it('renders decoupled gaze/blink eye groups and omits the outer logo rect on the front face', () => {
    const html = renderToStaticMarkup(<GreetingCube />);

    expect(html).toContain('suzent-logo-gaze');
    expect(html).toContain('suzent-logo-blink');
    expect(html).not.toContain('rx="4"');
  });

  it('renders solid front/back orbit rings with front casing and without dashed strokes', () => {
    const html = renderToStaticMarkup(<GreetingCube engaged />);

    expect(html).toContain('is-input-engaged');
    expect(html.match(/class="suzent-greeting-orbit-casing"/g)).toHaveLength(3);
    expect(html.match(/class="suzent-greeting-orbit-ring"/g)).toHaveLength(6);
    expect(html).not.toContain('stroke-dasharray');
  });
});
