import React, { useEffect, useState } from 'react';
import { useChatCoreStore } from '../../hooks/useChatStore';
import { getApiBase } from '../../lib/api';
import { setupDraft } from '../../lib/setupDraft';
import { Onboarding } from './Onboarding';

export function SetupGate({ children }: { children: React.ReactNode }): React.ReactElement {
  const { backendConfig, config, setConfig, beginNewChat } = useChatCoreStore();
  const [path, setPath] = useState(window.location.hash.slice(1) || '/');
  const [dismissed, setDismissed] = useState(false);
  const pendingKey = `suzent.onboarding.pending:${getApiBase()}`;
  useEffect(() => {
    const changed = () => setPath(window.location.hash.slice(1) || '/');
    window.addEventListener('hashchange', changed);
    return () => window.removeEventListener('hashchange', changed);
  }, []);
  useEffect(() => {
    let pending = false;
    try {
      pending = localStorage.getItem(pendingKey) === '1';
    } catch {
      /* Storage can be unavailable. */
    }
    if (dismissed || path !== '/' || !backendConfig || config.runtime === 'acp') return;
    if (pending || backendConfig.defaultModel === null || backendConfig.models.length === 0) {
      window.location.hash = '#/setup';
    }
  }, [backendConfig, config.runtime, path, pendingKey, dismissed]);
  useEffect(() => {
    if (path !== '/setup') return;
    try {
      localStorage.setItem(pendingKey, '1');
    } catch {
      /* Storage can be unavailable. */
    }
  }, [path, pendingKey]);

  if (path !== '/setup') return <>{children}</>;
  return (
    <main className="h-full w-full overflow-y-auto bg-white text-black dark:bg-zinc-950 dark:text-white">
      <Onboarding
        onExit={() => {
          setDismissed(true);
          try {
            localStorage.removeItem(pendingKey);
          } catch {
            /* Storage may be unavailable. */
          }
          window.location.hash = '#/';
        }}
        onComplete={(model, task) => {
          beginNewChat();
          setConfig((previous) => ({ ...previous, model }));
          setupDraft.task = task;
          try {
            localStorage.removeItem(pendingKey);
          } catch {
            /* Storage can be unavailable. */
          }
          window.location.hash = '#/';
        }}
      />
    </main>
  );
}
