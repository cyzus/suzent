import { describe, expect, it } from 'vitest';
import { buildHtmlDocument, htmlContentHeight } from './a2uiHtml';

describe('HTML canvas documents', () => {
  it('accepts long articles without the old 4000px cutoff', () => {
    expect(htmlContentHeight(7200.2)).toBe(7201);
    expect(htmlContentHeight(12)).toBe(40);
  });

  it.each([NaN, Infinity, -Infinity, 0, -1, '600', null, undefined])(
    'rejects invalid resize data: %s',
    (height) => expect(htmlContentHeight(height)).toBeNull()
  );

  it('keeps fixed-height applications unchanged', () => {
    const html = '<main style="height:100vh;overflow:auto">App</main>';
    expect(buildHtmlDocument(html, false)).toBe(html);
  });

  it('uses standards mode for fragments without duplicating an existing doctype', () => {
    expect(buildHtmlDocument('<p>News</p>', true)).toMatch(/^<!DOCTYPE html>/);
    expect(
      buildHtmlDocument('<!DOCTYPE html><html><body>News</body></html>', true).match(/<!doctype/gi)
    ).toHaveLength(1);
  });
});
