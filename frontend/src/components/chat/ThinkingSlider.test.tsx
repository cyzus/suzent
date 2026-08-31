import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { I18nProvider } from '../../i18n';
import { type ThinkingEffort } from '../../types/api';
import { ThinkingSlider } from './ThinkingSlider';

function render(value: ThinkingEffort, disabled = false): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <ThinkingSlider value={value} onChange={() => {}} disabled={disabled} />
    </I18nProvider>
  );
}

const litBars = (markup: string): number =>
  (markup.match(/class="suzent-ts__bar" data-on="true"/g) ?? []).length;

describe('ThinkingSlider', () => {
  // The number of lit strokes *is* the effort, so an off-by-one here is the
  // whole control lying about what the model was told to do.
  it('lights one stroke per rung of the ramp', () => {
    expect(litBars(render('off'))).toBe(0);
    expect(litBars(render('low'))).toBe(1);
    expect(litBars(render('medium'))).toBe(2);
    expect(litBars(render('high'))).toBe(3);
    expect(litBars(render('xhigh'))).toBe(4);
  });

  it('removes the manual meter while the default holds the wheel', () => {
    const markup = render('auto');

    expect(litBars(markup)).toBe(0);
    expect(markup).toContain('data-mode="auto"');
    expect(markup).toContain('class="suzent-ts__mode suzent-ts__mode-current"');
    expect(markup).toContain('tabindex="-1">Auto</button>');
    expect(markup).toContain(
      'class="suzent-ts__meter" role="slider" tabindex="-1" aria-hidden="true"'
    );
  });

  it('reports the rung to assistive tech as a word, not an index', () => {
    expect(render('xhigh')).toContain('aria-valuetext="X-High"');
    expect(render('xhigh')).toContain('aria-valuenow="4"');
  });

  it('flags the level so the XHIGH treatment can key off it', () => {
    expect(render('xhigh')).toContain('data-level="xhigh"');
    expect(render('low')).toContain('data-level="low"');
  });

  it('keeps the collapsed controls out of the tab order and disables the trigger while streaming', () => {
    const disabledMarkup = render('low', true);

    expect(disabledMarkup).toContain('data-disabled="true"');
    // The accessible name mirrors the visible summary, which drops the mode
    // word once a rung is picked ("Thinking: Low", not "Thinking: Manual · Low").
    expect(disabledMarkup).toContain('class="suzent-ts__trigger" aria-label="Thinking: Low"');
    expect(disabledMarkup).toContain('aria-expanded="false" disabled=""');
    expect(render('low')).toContain('class="suzent-ts__meter" role="slider" tabindex="-1"');
  });
});
