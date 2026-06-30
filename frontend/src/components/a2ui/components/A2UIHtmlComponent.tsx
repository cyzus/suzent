/**
 * A2UIHtmlComponent — renders free-form agent HTML in a sandboxed iframe.
 *
 * The HTML runs with `sandbox="allow-scripts"` (NO allow-same-origin), so scripts
 * execute but are isolated from the host: no access to cookies, localStorage, or
 * the parent DOM. Two-way feedback to the agent works via postMessage — the HTML
 * posts {type:'a2ui:action', action, context} to window.parent and we forward it
 * to onAction (the same path button/form interactions use).
 *
 * A small bootstrap script is injected into the document to (a) report content
 * height back for auto-sizing and (b) is the trusted shim; the agent's own
 * postMessage calls are validated by shape before dispatch.
 */

import React, { useEffect, useRef, useState } from 'react';
import type { A2UIHtml } from '../../../types/a2ui';

interface Props {
  component: A2UIHtml;
  onAction: (action: string, context: Record<string, unknown>) => void;
}

// Injected into the iframe document. Reports height on load/resize so the host
// can auto-size, and is harmless if the agent also posts its own actions.
const BOOTSTRAP = `
<script>
  (function () {
    function reportHeight() {
      var h = Math.max(
        document.documentElement.scrollHeight,
        document.body ? document.body.scrollHeight : 0
      );
      window.parent.postMessage({ type: 'a2ui:resize', height: h }, '*');
    }
    window.addEventListener('load', reportHeight);
    window.addEventListener('resize', reportHeight);
    if (window.ResizeObserver) {
      new ResizeObserver(reportHeight).observe(document.documentElement);
    }
    // Fallback for content that settles after load (fonts, images).
    setTimeout(reportHeight, 50);
    setTimeout(reportHeight, 300);
  })();
<\/script>
`;

function buildSrcDoc(html: string): string {
  // Append the bootstrap so it runs regardless of whether the agent provided a
  // full document or a bare fragment.
  return `${html}\n${BOOTSTRAP}`;
}

export const A2UIHtmlComponent: React.FC<Props> = ({ component, onAction }) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [autoHeight, setAutoHeight] = useState<number>(160);
  const fixedHeight = typeof component.height === 'number' ? component.height : null;

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Only trust messages from our own iframe's content window.
      if (!iframeRef.current || event.source !== iframeRef.current.contentWindow) {
        return;
      }
      const data = event.data;
      if (!data || typeof data !== 'object') return;

      if (data.type === 'a2ui:resize' && typeof data.height === 'number') {
        if (fixedHeight === null) {
          // Clamp to avoid a runaway/collapsed iframe.
          setAutoHeight(Math.min(Math.max(data.height, 40), 4000));
        }
        return;
      }

      if (data.type === 'a2ui:action' && typeof data.action === 'string') {
        const ctx =
          data.context && typeof data.context === 'object' && !Array.isArray(data.context)
            ? (data.context as Record<string, unknown>)
            : {};
        onAction(data.action, ctx);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [onAction, fixedHeight]);

  return (
    <iframe
      ref={iframeRef}
      title="agent-html"
      // allow-scripts WITHOUT allow-same-origin: scripts run but are sandboxed
      // away from the host origin (no cookies/storage/parent DOM access).
      sandbox="allow-scripts"
      srcDoc={buildSrcDoc(component.html)}
      className="w-full border-2 border-brutal-black bg-white"
      style={{ height: fixedHeight ?? autoHeight }}
    />
  );
};
