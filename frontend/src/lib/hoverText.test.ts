import { describe, expect, it } from 'vitest';
import { HOVER_TEXT_MAX, hoverText } from './hoverText';

describe('hoverText', () => {
  it('drops empty values so no tooltip appears', () => {
    expect(hoverText(undefined)).toBeUndefined();
    expect(hoverText(null)).toBeUndefined();
    expect(hoverText('  \n\t ')).toBeUndefined();
  });

  it('folds multi-line text onto one line', () => {
    expect(hoverText('line one\n\n  line two')).toBe('line one line two');
  });

  it('keeps short text untouched', () => {
    expect(hoverText('Run npm test')).toBe('Run npm test');
  });

  it('cuts long text to the cap with an ellipsis', () => {
    const result = hoverText('x'.repeat(1000));
    expect(result).toHaveLength(HOVER_TEXT_MAX);
    expect(result?.endsWith('…')).toBe(true);
  });

  it('honours a custom cap', () => {
    expect(hoverText('abcdefghij', 5)).toBe('abcd…');
  });
});
