export function htmlContentHeight(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? Math.max(40, Math.ceil(value))
    : null;
}

// Mirrors the app's light scrollbar in styles.css; the iframe background is always white.
// Injected ahead of the agent's markup so its own scrollbar rules still win.
const SCROLLBAR_STYLE = `<style>
* { scrollbar-width: thin; scrollbar-color: #000 transparent; }
::-webkit-scrollbar { width: 14px; height: 14px; }
::-webkit-scrollbar-track { background-color: transparent; box-shadow: inset 0 0 0 3px #000; margin: 3px 0; }
::-webkit-scrollbar-thumb { background-color: #000; border-radius: 0; border: 3px solid #000; background-clip: padding-box; }
::-webkit-scrollbar-thumb:hover { background-color: #333; }
::-webkit-scrollbar-corner { background: transparent; }
</style>`;

const DOCTYPE = /^\s*<!doctype[^>]*>/i;

function withScrollbarStyle(html: string): string {
  const doctype = html.match(DOCTYPE);
  if (!doctype) return `${SCROLLBAR_STYLE}\n${html}`;
  return `${doctype[0]}\n${SCROLLBAR_STYLE}${html.slice(doctype[0].length)}`;
}

export function buildHtmlDocument(html: string, autoSize: boolean): string {
  if (!autoSize) return withScrollbarStyle(html);
  // Standards mode prevents a fragment's body height from inheriting the iframe viewport.
  const document = withScrollbarStyle(DOCTYPE.test(html) ? html : `<!DOCTYPE html>\n${html}`);
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
