/**
 * Where the new-chat project menu should be drawn, in viewport coordinates.
 *
 * A drop-up menu is anchored by `bottom` rather than `top`: the element only
 * caps its height with `max-height`, so a short project list renders smaller
 * than `maxHeight` and a `top` computed from the cap would leave the menu
 * floating well above its trigger.
 */
export type ProjectMenuGeometry = {
  left: number;
  width: number;
  maxHeight: number;
} & ({ dropUp: false; top: number } | { dropUp: true; bottom: number });

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

  // The trigger is centred, so centre the menu on it before clamping.
  const centredLeft = buttonRect.left + buttonRect.width / 2 - width / 2;
  const maxLeft = Math.max(VIEWPORT_MARGIN, viewport.width - width - VIEWPORT_MARGIN);
  const left = Math.min(Math.max(VIEWPORT_MARGIN, centredLeft), maxLeft);

  if (dropUp) {
    // Pin the menu's bottom edge just above the trigger. The second term only
    // bites when `maxHeight` hit its floor in a viewport with less room than
    // that, and keeps the top edge on screen.
    const bottom = Math.max(
      VIEWPORT_MARGIN,
      Math.min(
        viewport.height - (buttonRect.top - MENU_GAP),
        viewport.height - VIEWPORT_MARGIN - maxHeight
      )
    );
    return { dropUp: true, bottom, left, width, maxHeight };
  }

  const top = Math.min(
    Math.max(VIEWPORT_MARGIN, viewport.height - VIEWPORT_MARGIN - maxHeight),
    buttonRect.bottom + MENU_GAP
  );
  return { dropUp: false, top, left, width, maxHeight };
}
