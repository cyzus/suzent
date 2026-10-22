export function htmlContentHeight(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? Math.max(40, Math.ceil(value))
    : null;
}

export function buildHtmlDocument(html: string, autoSize: boolean): string {
  if (!autoSize) return html;
  // Standards mode prevents a fragment's body height from inheriting the iframe viewport.
  const document = /^\s*<!doctype\s/i.test(html) ? html : `<!DOCTYPE html>\n${html}`;
  return `${document}
<style>html, body { height: auto !important; min-height: 0 !important; }</style>
<script>
(function () {
  var pending = false;
  var previous = 0;
  function measure() {
    pending = false;
    var body = document.body;
    if (!body || !document.documentElement.clientWidth) return;
    var style = getComputedStyle(body);
    var marginTop = parseFloat(style.marginTop) || 0;
    var marginBottom = parseFloat(style.marginBottom) || 0;
    var height = Math.ceil(Math.max(body.scrollHeight, body.getBoundingClientRect().height) + marginTop + marginBottom);
    if (height > 0 && height !== previous) {
      previous = height;
      window.parent.postMessage({ type: 'a2ui:resize', height: height }, '*');
    }
  }
  function schedule() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(measure);
  }
  window.addEventListener('load', schedule);
  window.addEventListener('resize', schedule);
  document.addEventListener('load', schedule, true);
  if (window.ResizeObserver) {
    var observer = new ResizeObserver(schedule);
    observer.observe(document.documentElement);
    observer.observe(document.body);
  }
  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true });
  if (document.fonts) document.fonts.ready.then(schedule);
  schedule();
})();
</script>`;
}
