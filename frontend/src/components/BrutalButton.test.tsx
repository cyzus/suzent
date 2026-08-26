import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { BrutalIconButton } from './BrutalButton';

describe('BrutalIconButton', () => {
  it('provides an accessible label and disables button translation', () => {
    const html = renderToStaticMarkup(
      <BrutalIconButton label="Copy">
        <span>icon</span>
      </BrutalIconButton>
    );

    expect(html).toContain('aria-label="Copy"');
    expect(html).toContain('title="Copy"');
    expect(html).toContain('active:!translate-x-0');
    expect(html).toContain('active:!translate-y-0');
  });
});
