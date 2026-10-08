export type PanelResizeAction = 'collapse' | 'cover' | 'dock';

export interface PanelResizeOptions {
  panel: HTMLElement;
  handle: HTMLElement;
  pointerId: number;
  startX: number;
  direction: 1 | -1;
  minWidth: number;
  maxWidth: number;
  collapseThreshold?: number;
  coverThreshold?: number;
  dockThreshold?: number;
  onFinish: (width: number | null, action?: PanelResizeAction) => void;
}

/** Keep pointer events out of embedded pages and commit only once per gesture. */
export function startPanelResize({
  panel,
  handle,
  pointerId,
  startX,
  direction,
  minWidth,
  maxWidth,
  collapseThreshold,
  coverThreshold,
  dockThreshold,
  onFinish,
}: PanelResizeOptions): () => void {
  const originalWidth = panel.style.width;
  let width = panel.getBoundingClientRect().width;
  let requestedWidth = width;
  let previousX = startX;
  let frame = 0;
  let finished = false;
  const previousCursor = document.body.style.cursor;
  const previousUserSelect = document.body.style.userSelect;
  const shield = document.createElement('div');
  shield.style.cssText =
    'position:fixed;inset:0;z-index:2147483647;cursor:col-resize;touch-action:none;';
  document.body.appendChild(shield);
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
  handle.setPointerCapture(pointerId);

  const apply = (): void => {
    frame = 0;
    panel.style.width = `${width}px`;
  };
  const update = (clientX: number): void => {
    requestedWidth = Math.max(
      collapseThreshold ?? minWidth,
      Math.min(coverThreshold ?? maxWidth, requestedWidth + direction * (clientX - previousX))
    );
    width = Math.max(minWidth, Math.min(maxWidth, requestedWidth));
    previousX = clientX;
    if (collapseThreshold !== undefined && requestedWidth <= collapseThreshold)
      finish(true, 'collapse');
    else if (coverThreshold !== undefined && requestedWidth >= coverThreshold)
      finish(true, 'cover');
    else if (dockThreshold !== undefined && requestedWidth <= dockThreshold) finish(true, 'dock');
  };
  const finish = (commit: boolean, action?: PanelResizeAction): void => {
    if (finished) return;
    finished = true;
    cancelAnimationFrame(frame);
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', up);
    window.removeEventListener('pointercancel', cancel);
    window.removeEventListener('blur', blur);
    window.removeEventListener('keydown', keydown);
    handle.removeEventListener('lostpointercapture', cancel);
    if (handle.hasPointerCapture(pointerId)) handle.releasePointerCapture(pointerId);
    shield.remove();
    document.body.style.cursor = previousCursor;
    document.body.style.userSelect = previousUserSelect;
    if (commit && !action) apply();
    else panel.style.width = originalWidth;
    if (commit && action) onFinish(width, action);
    else onFinish(commit ? width : null);
  };
  const move = (event: PointerEvent): void => {
    if (event.pointerId !== pointerId) return;
    update(event.clientX);
    if (!finished && !frame) frame = requestAnimationFrame(apply);
  };
  const up = (event: PointerEvent): void => {
    if (event.pointerId !== pointerId) return;
    update(event.clientX);
    finish(true);
  };
  const cancel = (event: PointerEvent): void => {
    if (event.pointerId === pointerId) finish(false);
  };
  const blur = (): void => finish(true);
  const keydown = (event: KeyboardEvent): void => {
    if (event.key === 'Escape') {
      event.preventDefault();
      finish(false);
    }
  };
  window.addEventListener('pointermove', move);
  window.addEventListener('pointerup', up);
  window.addEventListener('pointercancel', cancel);
  window.addEventListener('blur', blur);
  window.addEventListener('keydown', keydown);
  handle.addEventListener('lostpointercapture', cancel);
  return () => finish(false);
}
