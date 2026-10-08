export interface PanelResizeOptions {
  panel: HTMLElement;
  handle: HTMLElement;
  pointerId: number;
  startX: number;
  direction: 1 | -1;
  minWidth: number;
  maxWidth: number;
  onFinish: (width: number | null) => void;
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
  onFinish,
}: PanelResizeOptions): () => void {
  const originalWidth = panel.style.width;
  let width = panel.getBoundingClientRect().width;
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
    width = Math.max(minWidth, Math.min(maxWidth, width + direction * (clientX - previousX)));
    previousX = clientX;
  };
  const finish = (commit: boolean): void => {
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
    if (commit) apply();
    else panel.style.width = originalWidth;
    onFinish(commit ? width : null);
  };
  const move = (event: PointerEvent): void => {
    if (event.pointerId !== pointerId) return;
    update(event.clientX);
    if (!frame) frame = requestAnimationFrame(apply);
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
