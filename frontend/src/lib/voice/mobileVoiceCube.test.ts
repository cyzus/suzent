import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

describe('mobile voice renderer', () => {
  it('ships the same renderer and simulation as desktop without stale generated assets', () => {
    const script = fileURLToPath(
      new URL('../../../scripts/build-mobile-voice.mjs', import.meta.url)
    );
    expect(() =>
      execFileSync(process.execPath, [script, '--check'], { stdio: 'pipe' })
    ).not.toThrow();
  });
});
