export const DESKTOP_BREAKPOINT_PX = 1024;
export const LEFT_SIDEBAR_WIDTH_PX = 320;
// The chat's comfortable width: the right sidebar gives up its own width to
// preserve this before the chat is asked to give up anything.
export const MIN_CHAT_WIDTH_PX = 580;
// The chat's hard floor. Between the two the chat is squeezed -- cramped beats
// losing a sidebar, since the squeeze reverses itself the moment room returns.
export const SQUEEZED_MIN_CHAT_WIDTH_PX = 420;

export const MIN_RIGHT_SIDEBAR_WIDTH_PX = 280;
export const MAX_RIGHT_SIDEBAR_WIDTH_PX = 720;

// Canvas holds wide content (bracket tables, forms), so it scales with the
// viewport rather than a fixed cap: it takes CANVAS_WIDTH_RATIO of the available
// width, is allowed to squeeze the chat down to CANVAS_MIN_CHAT_WIDTH_PX (tighter
// than the shared MIN_CHAT_WIDTH_PX), and never exceeds MAX_CANVAS_SIDEBAR_WIDTH_PX.
export const CANVAS_WIDTH_RATIO = 0.55;
export const CANVAS_MIN_CHAT_WIDTH_PX = SQUEEZED_MIN_CHAT_WIDTH_PX;
export const MAX_CANVAS_SIDEBAR_WIDTH_PX = 1400;

/**
 * Canvas sidebar width: a ratio of the width left after the reserved (left
 * sidebar) area, clamped so the chat keeps CANVAS_MIN_CHAT_WIDTH_PX and the
 * sidebar stays within [MIN_RIGHT_SIDEBAR_WIDTH_PX, MAX_CANVAS_SIDEBAR_WIDTH_PX].
 */
export function getCanvasSidebarWidth(viewportWidth: number, reservedWidth = 0): number {
  const available = viewportWidth - reservedWidth;
  const byRatio = Math.round(available * CANVAS_WIDTH_RATIO);
  const maxByChatWidth = available - CANVAS_MIN_CHAT_WIDTH_PX;
  return Math.max(
    MIN_RIGHT_SIDEBAR_WIDTH_PX,
    Math.min(MAX_CANVAS_SIDEBAR_WIDTH_PX, maxByChatWidth, byRatio),
  );
}

export function getRightSidebarMaxWidth(
  viewportWidth: number,
  reservedWidth = 0,
  hardCap: number = MAX_RIGHT_SIDEBAR_WIDTH_PX,
): number {
  const dynamicMaxByChatWidth = Math.max(
    MIN_RIGHT_SIDEBAR_WIDTH_PX,
    viewportWidth - MIN_CHAT_WIDTH_PX - reservedWidth,
  );
  return Math.min(hardCap, dynamicMaxByChatWidth);
}

/**
 * Whether the left sidebar has to give up its column for the right one.
 *
 * Concessions run cheapest-first, and this is the last of them. The right
 * sidebar is narrowed toward MIN_RIGHT_SIDEBAR_WIDTH_PX first (see
 * clampRightSidebarWidth), then the chat is squeezed from MIN_CHAT_WIDTH_PX
 * down to SQUEEZED_MIN_CHAT_WIDTH_PX. Only when even a minimal right sidebar
 * would push the chat past that floor does a whole sidebar have to go -- so
 * this measures the tightest layout the three panes can hold, not the
 * comfortable one.
 */
export function shouldCollapseLeftSidebarOnRightOpen(viewportWidth: number): boolean {
  if (viewportWidth < DESKTOP_BREAKPOINT_PX) {
    return true;
  }

  const squeezedChatWidth =
    viewportWidth - LEFT_SIDEBAR_WIDTH_PX - MIN_RIGHT_SIDEBAR_WIDTH_PX;
  return squeezedChatWidth < SQUEEZED_MIN_CHAT_WIDTH_PX;
}

export function clampRightSidebarWidth(
  width: number,
  viewportWidth: number,
  reservedWidth = 0,
  hardCap: number = MAX_RIGHT_SIDEBAR_WIDTH_PX,
): number {
  const effectiveMaxWidth = getRightSidebarMaxWidth(viewportWidth, reservedWidth, hardCap);
  return Math.max(MIN_RIGHT_SIDEBAR_WIDTH_PX, Math.min(effectiveMaxWidth, width));
}

/**
 * Whether the right sidebar has to take over the whole width instead of docking.
 * Measured against the chat's hard floor for the same reason as above: a docked
 * panel beside a cramped chat beats covering the chat entirely.
 */
export function shouldUseFullWidthRightSidebar(viewportWidth: number, reservedWidth = 0): boolean {
  return viewportWidth - reservedWidth < (SQUEEZED_MIN_CHAT_WIDTH_PX + MIN_RIGHT_SIDEBAR_WIDTH_PX);
}
