import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const SRC_DIR = fileURLToPath(new URL('.', import.meta.url));
const SOURCE_FILE = /\.(tsx?|css)$/;

// `drop-shadow-[...]` is a filter, not a box shadow; inset accent bars are a separate pattern.
const ARBITRARY_BOX_SHADOW = /(?<![\w-])shadow-\[(?!inset_)[^\]\s]*\]?/g;

// Soft elevations that are deliberately not part of the hard-shadow scale.
const ALLOWED = new Set(['shadow-[0_18px_48px_rgba(0,0,0,0.12)]']);

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return SOURCE_FILE.test(entry.name) && !entry.name.includes('.test.') ? [path] : [];
  });
}

describe('brutal shadows', () => {
  it('use the shadow-brutal-* tokens instead of arbitrary values', () => {
    const offenders = sourceFiles(SRC_DIR).flatMap((file) => {
      const text = readFileSync(file, 'utf8');
      return [...text.matchAll(ARBITRARY_BOX_SHADOW)]
        .map((match) => match[0])
        .filter((value) => !ALLOWED.has(value))
        .map((value) => `${relative(SRC_DIR, file)}: ${value}`);
    });

    expect(offenders, 'use shadow-brutal-sm / -overlay / shadow-brutal from tailwind.config.cjs').toEqual([]);
  });
});
