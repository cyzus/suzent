import { describe, expect, it } from 'vitest';
import {
  countChangedLines,
  fileToolPath,
  metadataLineCounts,
  parseReadFileOutput,
} from './fileToolPreview';

describe('parseReadFileOutput', () => {
  it('keeps the file line numbers of an offset read', () => {
    const parsed = parseReadFileOutput(
      '[Lines 500-502 of 900] — use offset=503 to read more\n500\tfoo\n501\t\tindented\n502\tbar\r\n'
    );
    expect(parsed).toMatchObject({ start: 500, end: 502, total: 900 });
    expect(parsed?.gutter).toBe('500\n501\n502');
    expect(parsed?.text).toBe('foo\n\tindented\nbar');
  });

  it('returns null for outputs that are not a numbered read', () => {
    expect(parseReadFileOutput('(File has 3 lines, offset 9 is beyond end)')).toBeNull();
    expect(parseReadFileOutput('Error reading file: boom')).toBeNull();
  });
});

describe('line counts', () => {
  it('prefers counts the backend computed', () => {
    expect(metadataLineCounts({ added_lines: 3, removed_lines: 1 })).toEqual({
      addedLines: 3,
      removedLines: 1,
    });
    expect(metadataLineCounts({ old_content: 'a' })).toBeNull();
  });

  it('diffs small inputs and refuses whole large files', () => {
    expect(countChangedLines('a\nb\nc', 'a\nB\nc\nd')).toEqual({ addedLines: 2, removedLines: 1 });
    const big = Array.from({ length: 2000 }, (_, i) => `line ${i}`).join('\n');
    expect(countChangedLines(big, `${big}\nmore`)).toBeNull();
  });
});

describe('fileToolPath', () => {
  it('prefers the resolved path from the result', () => {
    expect(fileToolPath({ file_path: 'a.ts' }, { abs_path: '/w/a.ts' })).toBe('/w/a.ts');
    expect(fileToolPath({ file_path: 'a.ts' }, undefined)).toBe('a.ts');
    expect(fileToolPath(null, null)).toBe('');
  });
});
