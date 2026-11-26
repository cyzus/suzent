import React, { useEffect, useRef, useState } from 'react';

import { useI18n } from '../../i18n';
import { invoke } from '../../lib/desktop';

interface AgentBrowserPaneProps {
  visible: boolean;
}

/**
 * Holds the place of the agent's real browser page, which the desktop app
 * draws over this element. The page is live: the user can scroll, click and
 * type in it while the agent works.
 */
export function AgentBrowserPane({ visible }: AgentBrowserPaneProps): React.ReactElement {
  const { t } = useI18n();
  const containerRef = useRef<HTMLDivElement>(null);
  const [hasPage, setHasPage] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!visible || !container) return;
    let lastBounds = '';
    let disposed = false;
    const sync = (): void => {
      const rect = container.getBoundingClientRect();
      const bounds = {
        x: Math.round(rect.left),
        y: Math.round(rect.top),
        width: Math.max(1, Math.round(rect.width)),
        height: Math.max(1, Math.round(rect.height)),
      };
      const key = `${bounds.x},${bounds.y},${bounds.width},${bounds.height}`;
      if (key === lastBounds) return;
      lastBounds = key;
      invoke<boolean>('agent_browser_show', { bounds })
        .then((shown) => {
          if (!disposed) setHasPage(shown);
        })
        .catch(() => undefined);
    };
    // The agent may open its first page while the panel is open.
    const poll = window.setInterval(() => {
      lastBounds = '';
      sync();
    }, 2000);
    // Layout moves the panel without resizing it (sidebar slides), which a
    // ResizeObserver alone would miss.
    const observer = new ResizeObserver(sync);
    observer.observe(container);
    let frame = requestAnimationFrame(function tick() {
      sync();
      frame = requestAnimationFrame(tick);
    });
    return () => {
      disposed = true;
      observer.disconnect();
      cancelAnimationFrame(frame);
      window.clearInterval(poll);
      void invoke('agent_browser_hide').catch(() => undefined);
    };
  }, [visible]);

  return (
    <div
      ref={containerRef}
      className="relative flex-1 min-h-0 min-w-0 flex items-center justify-center bg-white dark:bg-zinc-900"
    >
      {!hasPage && (
        <p className="px-4 text-center text-[11px] font-mono text-neutral-400 dark:text-zinc-500">
          {t('browser.desktopEmpty')}
        </p>
      )}
    </div>
  );
}
