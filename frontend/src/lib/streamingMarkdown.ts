/**
 * Split markdown that is still streaming into top-level blocks that can each be
 * parsed once.
 *
 * A live reply is re-rendered every animation frame. Parsing the whole of it
 * each time (GFM, math, KaTeX) grows with the reply until the main thread is
 * saturated: scrolling stutters and the webview stops keeping up with the
 * pointer. Every block but the last is finished, so rendering them separately
 * lets memoization skip them and only the tail is parsed per frame.
 *
 * Only blank lines that cannot belong to the block above are split on: never
 * inside a code fence or a `$$` math block, and never before an indented line
 * or a list item, which may continue the list or item above. Whatever this
 * gets wrong only lasts until the stream ends, when the reply is rendered whole.
 */
const FENCE = /^ {0,3}(`{3,}|~{3,})/;
const CONTINUES_ABOVE = /^(\s|[-*+]\s|\d{1,9}[.)]\s|>|\[\^)/;

export function splitStreamingBlocks(markdown: string): string[] {
  const lines = markdown.split('\n');
  const blocks: string[] = [];
  let current: string[] = [];
  let fence: string | null = null;
  let inMath = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fenceMatch = line.match(FENCE);
    if (fence) {
      if (fenceMatch && fenceMatch[1][0] === fence[0] && fenceMatch[1].length >= fence.length) {
        fence = null;
      }
    } else if (fenceMatch) {
      fence = fenceMatch[1];
    } else {
      const trimmed = line.trim();
      if (inMath) {
        if (trimmed.endsWith('$$')) inMath = false;
      } else if (
        trimmed === '$$' ||
        (trimmed.startsWith('$$') && !trimmed.slice(2).endsWith('$$'))
      ) {
        inMath = true;
      }
    }

    const next = lines[i + 1];
    const splitHere =
      !fence &&
      !inMath &&
      line.trim() === '' &&
      current.length > 0 &&
      next !== undefined &&
      next.trim() !== '' &&
      !CONTINUES_ABOVE.test(next);
    if (splitHere) {
      blocks.push(current.join('\n'));
      current = [];
      continue;
    }
    current.push(line);
  }
  if (current.length > 0) blocks.push(current.join('\n'));
  return blocks;
}
