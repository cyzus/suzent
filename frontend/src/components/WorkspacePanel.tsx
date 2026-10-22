import React, { createContext, useContext, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { isImeComposing } from '../lib/ime';

interface WorkspacePanels {
  navigationKey: string;
  host: HTMLDivElement | null;
  setHost: (host: HTMLDivElement | null) => void;
}

const WorkspaceContext = createContext<WorkspacePanels | null>(null);

export function WorkspacePanelProvider({
  children,
  navigationKey,
}: {
  children: React.ReactNode;
  navigationKey: string;
}): React.ReactElement {
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  return (
    <WorkspaceContext.Provider value={{ host, setHost, navigationKey }}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function WorkspacePanelHost(): React.ReactElement {
  const context = useContext(WorkspaceContext);
  return <div ref={context?.setHost} className="workspace-panel-host" />;
}

interface WorkspacePanelProps {
  open: boolean;
  onClose?: () => void;
  closeOnEscape?: boolean;
  children: React.ReactNode;
  className?: string;
}

export function WorkspacePanel({
  open,
  onClose,
  closeOnEscape = true,
  children,
  className = 'flex-col',
}: WorkspacePanelProps): React.ReactElement | null {
  const context = useContext(WorkspaceContext);
  const panel = useRef<HTMLElement>(null);
  const id = useId();
  const close = useRef(onClose);
  close.current = onClose;
  const previousNavigation = useRef(context?.navigationKey);
  useEffect(() => {
    if (previousNavigation.current !== context?.navigationKey) {
      previousNavigation.current = context?.navigationKey;
      if (open) close.current?.();
    }
  }, [context?.navigationKey, open]);

  useEffect(() => {
    if (!open || !context?.host) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panel.current?.focus();
    const handleKey = (event: KeyboardEvent): void => {
      if (isImeComposing(event) || event.defaultPrevented) return;
      if (
        event.key === 'Escape' &&
        closeOnEscape &&
        context.host?.lastElementChild === panel.current
      ) {
        event.preventDefault();
        close.current?.();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => {
      window.removeEventListener('keydown', handleKey);
      if (previous?.isConnected) previous.focus();
    };
  }, [open, context?.host, closeOnEscape]);

  if (!open || !context?.host) return null;
  return createPortal(
    <section
      ref={panel}
      tabIndex={-1}
      data-workspace-panel={id}
      className={`relative flex h-full min-h-0 w-full min-w-0 overflow-hidden bg-white text-brutal-black outline-none dark:bg-zinc-900 dark:text-white ${className}`}
    >
      {children}
    </section>,
    context.host
  );
}
