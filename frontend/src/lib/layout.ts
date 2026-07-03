export const DESKTOP_BREAKPOINT_PX = 1024;
export const LEFT_SIDEBAR_WIDTH_PX = 320;
export const MIN_CHAT_WIDTH_PX = 580;

export const FALLBACK_RIGHT_SIDEBAR_WIDTH_PX = 384;
export const MIN_RIGHT_SIDEBAR_WIDTH_PX = 280;
export const MAX_RIGHT_SIDEBAR_WIDTH_PX = 720;

// Canvas holds wide content (bracket tables, forms), so it scales with the
// viewport rather than a fixed cap: it takes CANVAS_WIDTH_RATIO of the available
// width, is allowed to squeeze the chat down to CANVAS_MIN_CHAT_WIDTH_PX (tighter
// than the shared MIN_CHAT_WIDTH_PX), and never exceeds MAX_CANVAS_SIDEBAR_WIDTH_PX.
export const CANVAS_WIDTH_RATIO = 0.55;
export const CANVAS_MIN_CHAT_WIDTH_PX = 420;
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

export function getEffectiveRightSidebarWidth(width: number | null): number {
  return width ?? FALLBACK_RIGHT_SIDEBAR_WIDTH_PX;
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

export function shouldCollapseLeftSidebarOnRightOpen(
  viewportWidth: number,
  rightSidebarWidth: number | null,
): boolean {
  if (viewportWidth < DESKTOP_BREAKPOINT_PX) {
    return true;
  }

  const preferredRightWidth = getEffectiveRightSidebarWidth(rightSidebarWidth);
  const effectiveRightWidth = clampRightSidebarWidth(
    preferredRightWidth,
    viewportWidth,
    LEFT_SIDEBAR_WIDTH_PX,
  );
  const availableChatWidth = viewportWidth - LEFT_SIDEBAR_WIDTH_PX - effectiveRightWidth;
  return availableChatWidth < MIN_CHAT_WIDTH_PX;
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

export function shouldUseFullWidthRightSidebar(viewportWidth: number, reservedWidth = 0): boolean {
  return viewportWidth - reservedWidth < (MIN_CHAT_WIDTH_PX + MIN_RIGHT_SIDEBAR_WIDTH_PX);
}
