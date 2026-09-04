import { describe, it, expect } from 'vitest';
import { selectContextLimit } from './contextLimit';

const WINDOWS = {
  'gemini/gemini-3.1-pro-preview': 1_048_576,
  'openai/gpt-4.1': 128_000,
};

describe('selectContextLimit', () => {
  it('uses the window of the model in the selector', () => {
    expect(
      selectContextLimit({
        selectedModel: 'gemini/gemini-3.1-pro-preview',
        contextWindows: WINDOWS,
        fallback: 200_000,
      })
    ).toBe(1_048_576);
  });

  it('follows a model switch instead of the limit the last turn reported', () => {
    // The regression: the panel kept showing the previous model's maximum.
    expect(
      selectContextLimit({
        selectedModel: 'openai/gpt-4.1',
        contextWindows: WINDOWS,
        turnLimit: 1_048_576,
        fallback: 200_000,
      })
    ).toBe(128_000);
  });

  it('falls back to the turn’s own limit for a model the listing lacks', () => {
    expect(
      selectContextLimit({
        selectedModel: 'local/unlisted',
        contextWindows: WINDOWS,
        turnLimit: 32_000,
        fallback: 200_000,
      })
    ).toBe(32_000);
  });

  it('falls back to the backend default when nothing else is known', () => {
    expect(selectContextLimit({ contextWindows: WINDOWS, fallback: 200_000 })).toBe(200_000);
  });

  it('is undefined when there is no budget to show', () => {
    expect(selectContextLimit({})).toBeUndefined();
  });
});
