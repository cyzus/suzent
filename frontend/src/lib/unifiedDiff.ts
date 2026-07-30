export interface ParsedUnifiedDiff {
  original: string;
  modified: string;
}

export function parseUnifiedDiff(diff: string): ParsedUnifiedDiff | null {
  if (!diff.trim()) return null;

  const original: string[] = [];
  const modified: string[] = [];
  let inHunk = false;
  let hasContent = false;
  let hasPreviousHunk = false;

  for (const line of diff.replace(/\r\n/g, '\n').split('\n')) {
    if (line.startsWith('@@')) {
      if (hasPreviousHunk) {
        original.push('⋯');
        modified.push('⋯');
      }
      inHunk = true;
      hasPreviousHunk = true;
      continue;
    }
    if (!inHunk || line === '\\ No newline at end of file') continue;

    const marker = line[0];
    const content = line.slice(1);
    if (marker === ' ') {
      original.push(content);
      modified.push(content);
      hasContent = true;
    } else if (marker === '-') {
      original.push(content);
      hasContent = true;
    } else if (marker === '+') {
      modified.push(content);
      hasContent = true;
    }
  }

  if (!hasContent) return null;
  return {
    original: original.join('\n'),
    modified: modified.join('\n'),
  };
}
