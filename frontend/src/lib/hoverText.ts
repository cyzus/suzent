/** Longest native tooltip we let a hover raise before it reads as a wall of text. */
export const HOVER_TEXT_MAX = 160;

/**
 * Fit arbitrary text (a prompt, a command, a tool result, an error) into a
 * native `title` tooltip.
 *
 * The browser renders `title` as an unstyled box that wraps whatever it is
 * given, so a full prompt or stack trace turns a passing hover into a screen of
 * text. Newlines are folded to spaces and the text is cut to one glanceable
 * line; the full content stays where it is shown properly (the expanded card,
 * the detail view).
 */
export function hoverText(
  value: string | null | undefined,
  max: number = HOVER_TEXT_MAX
): string | undefined {
  const text = value?.replace(/\s+/g, ' ').trim();
  if (!text) return undefined;
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}
