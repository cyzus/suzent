/** Where the new-chat project menu should be drawn, in viewport coordinates. */
export interface ProjectMenuGeometry {
  top: number;
  left: number;
  width: number;
  maxHeight: number;
  dropUp: boolean;
}

const MENU_WIDTH = 240;
/** What the menu wants when there is room: list (max-h-60) + the create row. */
const MENU_PREFERRED_HEIGHT = 296;
/** Below this the menu is too cramped to be worth shrinking further. */
const MENU_MIN_HEIGHT = 120;
/** Breathing room kept between the menu and the viewport edges. */
const VIEWPORT_MARGIN = 16;
/** Gap between the trigger button and the menu. */
const MENU_GAP = 4;

/**
 * Place the menu so it stays inside the viewport.
 *
 * The picker renders on the new-chat screen, which lives inside an
 * `overflow-hidden` scroll container, so the menu is portalled to the body and
 * positioned `fixed`. That escapes the clip but means nothing else keeps it on
 * screen: we flip it above the button when below is tighter, cap its height to
 * the space actually available so a long project list scrolls instead of
 * running off the edge, and clamp it horizontally.
 */
export function resolveProjectMenuPosition(
  buttonRect: { top: number; bottom: number; left: number; width: number },
  viewport: { width: number; height: number }
): ProjectMenuGeometry {
  const width = Math.min(MENU_WIDTH, Math.max(0, viewport.width - VIEWPORT_MARGIN * 2));

  const spaceBelow = viewport.height - buttonRect.bottom - MENU_GAP - VIEWPORT_MARGIN;
  const spaceAbove = buttonRect.top - MENU_GAP - VIEWPORT_MARGIN;

  // Prefer dropping down, and only flip when above is genuinely roomier.
  const dropUp = spaceBelow < MENU_PREFERRED_HEIGHT && spaceAbove > spaceBelow;
  const available = dropUp ? spaceAbove : spaceBelow;
  const maxHeight = Math.max(MENU_MIN_HEIGHT, Math.min(MENU_PREFERRED_HEIGHT, available));

  const top = dropUp
    ? Math.max(VIEWPORT_MARGIN, buttonRect.top - MENU_GAP - maxHeight)
    : Math.min(
        Math.max(VIEWPORT_MARGIN, viewport.height - VIEWPORT_MARGIN - maxHeight),
        buttonRect.bottom + MENU_GAP
      );

  // The trigger is centred, so centre the menu on it before clamping.
  const centredLeft = buttonRect.left + buttonRect.width / 2 - width / 2;
  const maxLeft = Math.max(VIEWPORT_MARGIN, viewport.width - width - VIEWPORT_MARGIN);
  const left = Math.min(Math.max(VIEWPORT_MARGIN, centredLeft), maxLeft);

  return { top, left, width, maxHeight, dropUp };
}
