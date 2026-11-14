/** Pure helpers behind the read_file / edit_file / write_file tool blocks. */

// The table below is lines(original) x lines(modified): two 2000-line files
// took ~100ms and 32MB, 5000 lines ~800ms and 200MB. New results carry counts
// from the backend; this only covers older ones, and only when small.
const MAX_LCS_CELLS = 250_000;

export type LineCounts = { addedLines: number; removedLines: number };

/** Counts the backend computed, when the tool result carries them. */
export function metadataLineCounts(
  metadata: Record<string, unknown> | null | undefined
): LineCounts | null {
  const added = metadata?.added_lines;
  const removed = metadata?.removed_lines;
  return typeof added === 'number' && typeof removed === 'number'
    ? { addedLines: added, removedLines: removed }
    : null;
}

/** Line-level diff counts, or null when the inputs are too large to diff here. */
export function countChangedLines(original: string, modified: string): LineCounts | null {
  const originalLines = original.split('\n');
  const modifiedLines = modified.split('\n');
  if ((originalLines.length + 1) * (modifiedLines.length + 1) > MAX_LCS_CELLS) return null;
  const lengths = Array.from({ length: originalLines.length + 1 }, () =>
    Array<number>(modifiedLines.length + 1).fill(0)
  );

  for (let i = originalLines.length - 1; i >= 0; i -= 1) {
    for (let j = modifiedLines.length - 1; j >= 0; j -= 1) {
      lengths[i][j] =
        originalLines[i] === modifiedLines[j]
          ? lengths[i + 1][j + 1] + 1
          : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }

  let i = 0;
  let j = 0;
  let addedLines = 0;
  let removedLines = 0;

  while (i < originalLines.length && j < modifiedLines.length) {
    if (originalLines[i] === modifiedLines[j]) {
      i += 1;
      j += 1;
    } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
      removedLines += 1;
      i += 1;
    } else {
      addedLines += 1;
      j += 1;
    }
  }

  removedLines += originalLines.length - i;
  addedLines += modifiedLines.length - j;
  return { addedLines, removedLines };
}

/** Where a file tool acted, preferring the resolved path the backend reports. */
export function fileToolPath(
  parsedArgs: Record<string, unknown> | null | undefined,
  metadata: Record<string, unknown> | null | undefined
): string {
  if (typeof metadata?.abs_path === 'string') return metadata.abs_path;
  if (typeof parsedArgs?.file_path === 'string') return parsedArgs.file_path;
  if (typeof parsedArgs?.path === 'string') return parsedArgs.path;
  return '';
}

export interface ParsedRead {
  start: number;
  end: number;
  total: number;
  gutter: string;
  text: string;
}

const RANGE_HEADER = /^\[Lines (\d+)-(\d+) of (\d+)\]/;
const NUMBERED_LINE = /^(\d+)\t(.*)$/;

/** Splits read_file's cat -n style output back into line numbers and text. */
export function parseReadFileOutput(output: string): ParsedRead | null {
  const newline = output.indexOf('\n');
  const header = RANGE_HEADER.exec(newline >= 0 ? output.slice(0, newline) : output);
  if (!header || newline < 0) return null;

  const numbers: string[] = [];
  const lines: string[] = [];
  for (const raw of output
    .slice(newline + 1)
    .replace(/\n$/, '')
    .split('\n')) {
    const line = raw.replace(/\r$/, '');
    const match = NUMBERED_LINE.exec(line);
    if (match) {
      numbers.push(match[1]);
      lines.push(match[2]);
    } else {
      numbers.push('');
      lines.push(line);
    }
  }
  return {
    start: Number(header[1]),
    end: Number(header[2]),
    total: Number(header[3]),
    gutter: numbers.join('\n'),
    text: lines.join('\n'),
  };
}
