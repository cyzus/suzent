import React from 'react';
import { useI18n } from '../../i18n';
import { useFocalStatus } from '../../hooks/useFocalStatus';
import { useChatStreamingStore } from '../../hooks/useChatStore';
import { FOCAL_CHAT_ID, type FocalAgentStatus } from '../../lib/focalAgent';
import { RegentCube } from './RegentCube';
import { regentState, useRegentNod } from './regentState';

interface RegentIdentityProps {
  status: FocalAgentStatus | null;
  /** Regent is answering in this chat right now, ahead of the next status poll. */
  working?: boolean;
  /** Bumped when Regent has something new to say; replays the cube's nod. */
  nod?: number;
}

/**
 * Who the conversation is with: the crowned cube beside "SUZENT Regent", sized
 * to sit in the app header without changing its height. The cube shows what
 * Regent is doing; the details live in its side panel.
 */
export function RegentIdentity({
  status,
  working = false,
  nod = 0,
}: RegentIdentityProps): React.ReactElement {
  const { t } = useI18n();
  const state = working ? 'working' : regentState(status);
  const presence = state === 'working' ? t('chatList.focal.working') : t('chatList.focal.role');

  return (
    <div className="regent-identity flex min-w-0 items-center gap-2" title={presence}>
      <span key={nod} className={nod > 0 ? 'regent-nod inline-flex' : 'inline-flex'}>
        <RegentCube size={26} state={state} />
      </span>
      <span className="shrink-0 font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
        {t('chatList.focal.brand')}
      </span>
      <span className="shrink-0 font-brutal text-2xl font-black leading-none tracking-[-0.04em] [-webkit-text-stroke:0.75px_currentColor] text-brutal-black dark:text-white">
        {t('chatList.focal.name')}
      </span>
    </div>
  );
}

/** `RegentIdentity` fed by Regent's live status, for the app header. */
export function LiveRegentIdentity(): React.ReactElement {
  const status = useFocalStatus();
  const { isStreaming, activeStreamingChatId } = useChatStreamingStore();
  return (
    <RegentIdentity
      status={status}
      working={isStreaming && activeStreamingChatId === FOCAL_CHAT_ID}
      nod={useRegentNod(status)}
    />
  );
}
