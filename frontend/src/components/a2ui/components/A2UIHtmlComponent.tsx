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
import { buildHtmlDocument, htmlContentHeight } from '../../../lib/a2uiHtml';
import type { A2UIHtml } from '../../../types/a2ui';

interface Props {
  component: A2UIHtml;
  framed?: boolean;
  onAction: (action: string, context: Record<string, unknown>) => void;
}

export const A2UIHtmlComponent: React.FC<Props> = ({ component, onAction, framed = true }) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [autoHeight, setAutoHeight] = useState<number>(160);
  const fixedHeight = htmlContentHeight(component.height);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Only trust messages from our own iframe's content window.
      if (!iframeRef.current || event.source !== iframeRef.current.contentWindow) {
        return;
      }
      const data = event.data;
      if (!data || typeof data !== 'object') return;

      if (data.type === 'a2ui:resize') {
        const height = htmlContentHeight(data.height);
        if (fixedHeight === null && height !== null) {
          setAutoHeight(height);
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
      srcDoc={buildHtmlDocument(component.html, fixedHeight === null)}
      className={`block w-full max-h-full bg-white ${framed ? 'border-2 border-brutal-black' : 'border-0'}`}
      style={{ height: fixedHeight ?? autoHeight + (framed ? 4 : 0) }}
    />
  );
};
