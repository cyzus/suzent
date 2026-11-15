import React, { useMemo, useState } from 'react';
import { ExpandedSurfaceCard } from '../ExpandedSurfaceCard';
import { WorkspacePanel } from '../WorkspacePanel';
import { CanvasView } from '../sidebar/CanvasView';
import { BackgroundTaskView } from '../sidebar/BackgroundTaskView';
import { WebActivitiesView } from '../sidebar/WebActivitiesView';
import { useWebHistory } from '../../hooks/useWebHistory';
import { useI18n } from '../../i18n';
import type { Message } from '../../types/api';

export type PeekPopupContent =
  { kind: 'canvas' } | { kind: 'subagent'; taskId: string } | { kind: 'web'; contextId: string };

interface ChatPeekPopupProps {
  content: PeekPopupContent | null;
  onClose: () => void;
  canvas: React.ComponentProps<typeof CanvasView>['canvas'];
  onCanvasDispatch: React.ComponentProps<typeof CanvasView>['onDispatch'];
  messages: Message[];
}

const TITLE_KEYS: Record<PeekPopupContent['kind'], string> = {
  canvas: 'sidebar.tabs.canvas',
  subagent: 'sidebar.tabs.agents',
  web: 'sidebar.tabs.browser',
};

/**
 * What a chat in Regent's side panel would show in its sidebar -- the canvas,
 * a sub-agent, a web step -- opened over the window instead, since the panel
 * has no sidebar of its own.
 */
export const ChatPeekPopup: React.FC<ChatPeekPopupProps> = ({
  content,
  onClose,
  canvas,
  onCanvasDispatch,
  messages,
}) => {
  const { t } = useI18n();
  const [browserStreamActive, setBrowserStreamActive] = useState(false);
  const webMessages = useMemo(
    () => (content?.kind === 'web' ? messages : []),
    [content?.kind, messages]
  );
  const webHistory = useWebHistory(webMessages);
  if (!content) return null;
  return (
    <WorkspacePanel open onClose={onClose}>
      <ExpandedSurfaceCard title={t(TITLE_KEYS[content.kind])} dockedToolbar onShrink={onClose}>
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-white dark:bg-zinc-900">
          {content.kind === 'canvas' && (
            <CanvasView canvas={canvas} onDispatch={onCanvasDispatch} />
          )}
          {content.kind === 'subagent' && (
            <BackgroundTaskView taskId={content.taskId} onClose={onClose} />
          )}
          {content.kind === 'web' && (
            <WebActivitiesView
              visible
              history={webHistory}
              isBrowserStreamActive={browserStreamActive}
              onBrowserStreamActive={setBrowserStreamActive}
              forcedContextId={content.contextId}
              onClearForcedContext={onClose}
            />
          )}
        </div>
      </ExpandedSurfaceCard>
    </WorkspacePanel>
  );
};
