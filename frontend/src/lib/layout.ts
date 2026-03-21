export const DESKTOP_BREAKPOINT_PX = 1024;
export const LEFT_SIDEBAR_WIDTH_PX = 320;
export const MIN_CHAT_WIDTH_PX = 580;

export const FALLBACK_RIGHT_SIDEBAR_WIDTH_PX = 384;
export const MIN_RIGHT_SIDEBAR_WIDTH_PX = 280;
export const MAX_RIGHT_SIDEBAR_WIDTH_PX = 720;

export function getEffectiveRightSidebarWidth(width: number | null): number {
  return width ?? FALLBACK_RIGHT_SIDEBAR_WIDTH_PX;
}

export function getRightSidebarMaxWidth(viewportWidth: number, reservedWidth = 0): number {
  const dynamicMaxByChatWidth = Math.max(
    MIN_RIGHT_SIDEBAR_WIDTH_PX,
    viewportWidth - MIN_CHAT_WIDTH_PX - reservedWidth,
  );
  return Math.min(MAX_RIGHT_SIDEBAR_WIDTH_PX, dynamicMaxByChatWidth);
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

export function clampRightSidebarWidth(width: number, viewportWidth: number, reservedWidth = 0): number {
  const effectiveMaxWidth = getRightSidebarMaxWidth(viewportWidth, reservedWidth);
  return Math.max(MIN_RIGHT_SIDEBAR_WIDTH_PX, Math.min(effectiveMaxWidth, width));
}

export function shouldUseFullWidthRightSidebar(viewportWidth: number, reservedWidth = 0): boolean {
  return viewportWidth - reservedWidth < (MIN_CHAT_WIDTH_PX + MIN_RIGHT_SIDEBAR_WIDTH_PX);
}
