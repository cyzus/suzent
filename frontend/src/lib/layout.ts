export const DESKTOP_BREAKPOINT_PX = 1024;
export const LEFT_SIDEBAR_WIDTH_PX = 320;
export const MIN_LEFT_SIDEBAR_WIDTH_PX = 240;
export const MAX_LEFT_SIDEBAR_WIDTH_PX = 480;
// A narrow chat remains usable while the user gives more room to side content.
export const SQUEEZED_MIN_CHAT_WIDTH_PX = 352;

export const MIN_RIGHT_SIDEBAR_WIDTH_PX = 280;

// Wide content starts larger without imposing a different manual resize limit.
export const CANVAS_WIDTH_RATIO = 0.55;
const MAX_CANVAS_DEFAULT_WIDTH_PX = 1400;

export function getCanvasSidebarWidth(viewportWidth: number, reservedWidth = 0): number {
  const available = viewportWidth - reservedWidth;
  return clampRightSidebarWidth(
    Math.min(MAX_CANVAS_DEFAULT_WIDTH_PX, Math.round(available * CANVAS_WIDTH_RATIO)),
    viewportWidth,
    reservedWidth
  );
}

export function getRightSidebarMaxWidth(viewportWidth: number, reservedWidth = 0): number {
  return Math.max(
    MIN_RIGHT_SIDEBAR_WIDTH_PX,
    viewportWidth - reservedWidth - SQUEEZED_MIN_CHAT_WIDTH_PX
  );
}

// Only collapse the left column once a minimal right panel and chat cannot fit.
export function shouldCollapseLeftSidebarOnRightOpen(
  viewportWidth: number,
  leftWidth = LEFT_SIDEBAR_WIDTH_PX
): boolean {
  if (viewportWidth < DESKTOP_BREAKPOINT_PX) {
    return true;
  }

  const squeezedChatWidth = viewportWidth - leftWidth - MIN_RIGHT_SIDEBAR_WIDTH_PX;
  return squeezedChatWidth < SQUEEZED_MIN_CHAT_WIDTH_PX;
}

export function clampRightSidebarWidth(
  width: number,
  viewportWidth: number,
  reservedWidth = 0
): number {
  const effectiveMaxWidth = getRightSidebarMaxWidth(viewportWidth, reservedWidth);
  return Math.max(MIN_RIGHT_SIDEBAR_WIDTH_PX, Math.min(effectiveMaxWidth, width));
}

/**
 * Whether the right sidebar has to take over the whole width instead of docking.
 * Measured against the chat's hard floor for the same reason as above: a docked
 * panel beside a cramped chat beats covering the chat entirely.
 */
export function shouldUseFullWidthRightSidebar(viewportWidth: number, reservedWidth = 0): boolean {
  return viewportWidth - reservedWidth < SQUEEZED_MIN_CHAT_WIDTH_PX + MIN_RIGHT_SIDEBAR_WIDTH_PX;
}
