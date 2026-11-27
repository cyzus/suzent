import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  ArrowRightIcon,
  PlusIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

import { useI18n } from '../../i18n';
import { invoke, listen } from '../../lib/desktop';
import { isImeComposing } from '../../lib/ime';

interface AgentBrowserPaneProps {
  visible: boolean;
}

export interface AgentTab {
  id: string;
  title: string;
  url: string;
  loading: boolean;
  canGoBack: boolean;
  canGoForward: boolean;
}

export interface AgentBrowserState {
  tabs: AgentTab[];
  selected: string | null;
}

/** The address bar shows nothing for a blank tab, ready to type into. */
export function displayUrl(url: string | undefined): string {
  return !url || url === 'about:blank' ? '' : url;
}

const command = (action: string, args: { id?: string; url?: string } = {}): void => {
  void invoke('agent_browser_command', { action, ...args }).catch(() => undefined);
};

const ICON_BUTTON =
  'flex h-7 w-7 shrink-0 items-center justify-center text-neutral-600 hover:bg-neutral-100 disabled:opacity-30 disabled:hover:bg-transparent dark:text-zinc-300 dark:hover:bg-zinc-700';

/**
 * Tabs, an address bar and the place of the agent's real browser page, which
 * the desktop app draws over this element. The page is live: the user can
 * scroll, click and type in it while the agent works, and the agent acts on
 * whichever tab the user picks here.
 */
export function AgentBrowserPane({ visible }: AgentBrowserPaneProps): React.ReactElement {
  const { t } = useI18n();
  const containerRef = useRef<HTMLDivElement>(null);
  const [browser, setBrowser] = useState<AgentBrowserState>({ tabs: [], selected: null });
  const [address, setAddress] = useState('');
  const editing = useRef(false);

  const current = browser.tabs.find((tab) => tab.id === browser.selected);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    let disposed = false;
    void invoke<AgentBrowserState>('agent_browser_state')
      .then((state) => {
        if (!disposed) setBrowser(state);
      })
      .catch(() => undefined);
    void listen<AgentBrowserState>('agent-browser:state', setBrowser).then((stop) => {
      if (disposed) stop();
      else unlisten = stop;
    });
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, []);

  // Typing is never overwritten; a new page or another tab replaces it.
  useEffect(() => {
    if (!editing.current) setAddress(displayUrl(current?.url));
  }, [current?.url, current?.id]);

  useEffect(() => {
    const container = containerRef.current;
    if (!visible || !container) return;
    let lastBounds = '';
    const sync = (): void => {
      const rect = container.getBoundingClientRect();
      // A panel hidden by CSS (e.g. Settings open) has no size: take the page
      // away rather than shrink it to nothing.
      if (rect.width < 2 || rect.height < 2) {
        if (lastBounds !== 'hidden') void invoke('agent_browser_hide').catch(() => undefined);
        lastBounds = 'hidden';
        return;
      }
      const bounds = {
        x: Math.round(rect.left),
        y: Math.round(rect.top),
        width: Math.max(1, Math.round(rect.width)),
        height: Math.max(1, Math.round(rect.height)),
      };
      const key = `${bounds.x},${bounds.y},${bounds.width},${bounds.height}`;
      if (key === lastBounds) return;
      lastBounds = key;
      void invoke('agent_browser_show', { bounds }).catch(() => undefined);
    };
    // The agent may open its first page while the panel is open.
    const poll = window.setInterval(() => {
      if (lastBounds !== 'hidden') lastBounds = '';
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
      observer.disconnect();
      cancelAnimationFrame(frame);
      window.clearInterval(poll);
      void invoke('agent_browser_hide').catch(() => undefined);
    };
  }, [visible]);

  const submit = (event: React.KeyboardEvent<HTMLInputElement>): void => {
    if (isImeComposing(event)) return;
    if (event.key === 'Escape') {
      setAddress(displayUrl(current?.url));
      event.currentTarget.blur();
      return;
    }
    if (event.key !== 'Enter' || !address.trim()) return;
    command('navigate', { id: current?.id, url: address });
    editing.current = false;
    event.currentTarget.blur();
  };

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="shrink-0 border-b-2 border-brutal-black bg-white dark:bg-zinc-800">
        <div
          role="tablist"
          className="flex min-w-0 items-stretch overflow-x-auto bg-neutral-100 dark:bg-zinc-900"
        >
          {browser.tabs.map((tab) => {
            const selected = tab.id === browser.selected;
            const label = tab.title || displayUrl(tab.url) || t('browser.newTab');
            return (
              <div
                key={tab.id}
                className={`group flex min-w-0 max-w-[12rem] shrink-0 items-center border-r border-neutral-200 dark:border-zinc-700 ${selected ? 'bg-white font-bold text-brutal-black dark:bg-zinc-800 dark:text-white' : 'bg-neutral-100 text-neutral-500 dark:bg-zinc-900 dark:text-zinc-400'}`}
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  title={label}
                  className="min-w-0 flex-1 truncate py-1.5 pl-2.5 pr-1 text-left text-[11px]"
                  onClick={() => command('select', { id: tab.id })}
                >
                  {label}
                </button>
                <button
                  type="button"
                  aria-label={t('browser.closeTab')}
                  title={t('browser.closeTab')}
                  className="mr-1 flex h-5 w-5 shrink-0 items-center justify-center text-neutral-500 hover:bg-neutral-200 dark:hover:bg-zinc-600"
                  onClick={() => command('close', { id: tab.id })}
                >
                  <XMarkIcon className="h-3 w-3" aria-hidden="true" />
                </button>
              </div>
            );
          })}
          <button
            type="button"
            aria-label={t('browser.newTab')}
            title={t('browser.newTab')}
            className={ICON_BUTTON}
            onClick={() => command('new')}
          >
            <PlusIcon className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="flex items-center gap-0.5 border-t border-neutral-200 px-1 py-1 dark:border-zinc-700">
          <button
            type="button"
            aria-label={t('browser.back')}
            title={t('browser.back')}
            className={ICON_BUTTON}
            disabled={!current?.canGoBack}
            onClick={() => command('back')}
          >
            <ArrowLeftIcon className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label={t('browser.forward')}
            title={t('browser.forward')}
            className={ICON_BUTTON}
            disabled={!current?.canGoForward}
            onClick={() => command('forward')}
          >
            <ArrowRightIcon className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label={t(current?.loading ? 'browser.stop' : 'browser.reload')}
            title={t(current?.loading ? 'browser.stop' : 'browser.reload')}
            className={ICON_BUTTON}
            disabled={!current}
            onClick={() => command(current?.loading ? 'stop' : 'reload')}
          >
            {current?.loading ? (
              <XMarkIcon className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ArrowPathIcon className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
          <input
            type="text"
            aria-label={t('browser.address')}
            placeholder={t('browser.addressPlaceholder')}
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            className="ml-1 min-w-0 flex-1 border border-neutral-300 bg-white px-2 py-1 font-mono text-[11px] focus:border-brutal-black focus:outline-none dark:border-zinc-600 dark:bg-zinc-900 dark:text-white"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            onFocus={(event) => {
              editing.current = true;
              event.currentTarget.select();
            }}
            onBlur={() => {
              editing.current = false;
            }}
            onKeyDown={submit}
          />
        </div>
      </div>
      <div
        ref={containerRef}
        className="relative flex min-h-0 min-w-0 flex-1 items-center justify-center bg-white dark:bg-zinc-900"
      >
        {!current && (
          <p className="px-4 text-center text-[11px] font-mono text-neutral-400 dark:text-zinc-500">
            {t('browser.desktopEmpty')}
          </p>
        )}
      </div>
    </div>
  );
}
