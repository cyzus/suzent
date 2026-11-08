import { describe, expect, it } from 'vitest';
import presentation from '../../../packages/presentation/tokens.json';
import { SCHEME_COLORS } from './useTheme';

describe('warm accent', () => {
  it('uses the shared yellow and a deeper yellow in dark mode', () => {
    expect(SCHEME_COLORS.warm.light).toBe(presentation.colors.yellow);
    expect(SCHEME_COLORS.warm.dark).toBe(presentation.colors['yellow-dark']);
    expect(presentation.colors['yellow-dark']).not.toBe(presentation.colors.yellow);
  });
});
