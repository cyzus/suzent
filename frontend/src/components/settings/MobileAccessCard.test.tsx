import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { I18nProvider } from '../../i18n';
import { MobileAccessCard } from './MobileAccessCard';

function render(): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <MobileAccessCard config={null} />
    </I18nProvider>
  );
}

describe('MobileAccessCard', () => {
  it('offers permission presets and defaults a new phone to full control', () => {
    const html = render();
    const radios = [...html.matchAll(/<label[^>]*>\s*<input type="radio"[^>]*>/g)].map(
      (match) => match[0]
    );

    expect(radios).toHaveLength(4);
    expect(radios[0]).toContain('checked');
    expect(radios.slice(1).some((radio) => radio.includes('checked'))).toBe(false);
    expect(html).toContain('Full control');
    expect(html).toContain('Chat only');
    expect(html).toContain('Read only');
    expect(html).not.toContain('Send messages');
  });
});
