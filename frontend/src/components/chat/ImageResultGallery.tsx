import React from 'react';
import { VideoResultPlayer } from './VideoResultPlayer';
import { SpeechPlayer } from './SpeechPlayer';
import { getApiBase, getSandboxParams } from '../../lib/api';
import { useChatStore } from '../../hooks/useChatStore';
import { getMediaToolPaths, MediaToolRenderer } from './MediaToolRenderer';
import { parseToolResultEnvelope } from './ToolCallBlock';
import { ArtifactActions, ArtifactCard } from '../artifacts/ArtifactCard';
import { artifactKind, displayPathOf, savedPaths } from '../../lib/chatArtifacts';
import { useI18n } from '../../i18n';

interface ImageResultCall {
  toolName?: string;
  output?: string;
  args?: string;
}

/**
 * Every file the turn handed over with send_file, in order, each once. A call whose
 * chat-app upload failed still lists them: the files exist on this computer.
 */
export function getSentPaths(calls: ImageResultCall[]): string[] {
  return [
    ...new Set(
      calls.flatMap((call) =>
        call.toolName === 'send_file' ? savedPaths(call.toolName, call.output) : []
      )
    ),
  ];
}

export function getImageResultPaths(calls: ImageResultCall[]): string[] {
  const paths = new Set<string>();
  for (const call of calls) {
    if (call.toolName !== 'generate_image' && call.toolName !== 'edit_image') continue;
    const result = parseToolResultEnvelope(call.output);
    if (result?.success !== true || !result.metadata || typeof result.metadata !== 'object')
      continue;
    for (const path of getMediaToolPaths({
      toolName: call.toolName,
      parsedArgs: null,
      metadata: result.metadata as Record<string, unknown>,
    }))
      paths.add(path);
  }
  return [...paths];
}

export function getRailImagePaths(calls: ImageResultCall[], seen = new Set<string>()): string[] {
  const paths = calls.flatMap((call) => {
    if (call.toolName !== 'analyze_visual') return getImageResultPaths([call]);
    const result = parseToolResultEnvelope(call.output);
    if (!call.output || result?.success === false) return [];
    let args: Record<string, unknown> = {};
    try {
      args = JSON.parse(call.args || '{}');
    } catch {
      /* Streaming arguments may be incomplete. */
    }
    return getMediaToolPaths({
      toolName: call.toolName,
      parsedArgs: args,
      metadata: result?.metadata as Record<string, unknown> | undefined,
    }).filter((path) => !/\.(mp4|mov|webm|avi|mkv)$/i.test(path));
  });
  return paths.filter((path) => {
    const key = path.replace(/\\/g, '/').replace(/\/\.\//g, '/');
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

interface PlayableResult {
  key: string;
  kind: 'video' | 'audio' | 'system';
  path?: string;
  metadata: Record<string, unknown>;
}
export function getPlayableResults(calls: ImageResultCall[]): PlayableResult[] {
  const seen = new Set<string>();
  return calls.flatMap<PlayableResult>((call, index) => {
    if (call.toolName !== 'check_video' && call.toolName !== 'speak') return [];
    const result = parseToolResultEnvelope(call.output);
    if (result?.success !== true || !result.metadata || typeof result.metadata !== 'object')
      return [];
    const metadata = result.metadata as Record<string, unknown>;
    if (
      call.toolName === 'speak' &&
      metadata.engine === 'system' &&
      typeof metadata.text === 'string'
    )
      return [{ key: `speech-${index}`, kind: 'system' as const, metadata }];
    const paths = metadata.saved_paths;
    if (!Array.isArray(paths)) return [];
    return paths
      .filter(
        (path): path is string =>
          typeof path === 'string' && !!path.trim() && !seen.has(path) && !!seen.add(path)
      )
      .map((path) => ({
        key: path,
        kind: call.toolName === 'check_video' ? ('video' as const) : ('audio' as const),
        path,
        metadata,
      }));
  });
}

export function hasMediaResults(calls: ImageResultCall[]): boolean {
  return getImageResultPaths(calls).length > 0 || getPlayableResults(calls).length > 0;
}

/** Media that should close an activity group to preserve its timeline position. */
export function hasVisualMediaResults(calls: ImageResultCall[]): boolean {
  return (
    getImageResultPaths(calls).length > 0 ||
    getPlayableResults(calls).some((item) => item.kind === 'video')
  );
}

export const ImageResultGallery: React.FC<{ calls: ImageResultCall[]; showImages?: boolean }> = ({
  calls,
  showImages = true,
}) => {
  const paths = getImageResultPaths(calls);
  const media = getPlayableResults(calls);
  const { currentChatId, config } = useChatStore();
  return (
    <>
      {showImages && paths.length > 0 && (
        <MediaToolRenderer
          toolName="generate_image"
          parsedArgs={null}
          metadata={{ saved_paths: paths }}
        />
      )}
      {media.length > 0 && (
        <div className="my-2 flex flex-col items-start gap-1">
          {media.map((item) => {
            if (item.kind === 'system')
              return <SpeechPlayer key={item.key} metadata={item.metadata} />;
            if (!currentChatId || !item.path) return null;
            const src = `${getApiBase()}/sandbox/serve?${getSandboxParams(currentChatId, item.path, config.sandbox_volumes)}`;
            return item.kind === 'video' ? (
              <VideoResultPlayer key={src} src={src} path={item.path} />
            ) : (
              <SpeechPlayer key={item.key} src={src} metadata={item.metadata} />
            );
          })}
        </div>
      )}
    </>
  );
};

/**
 * What the agent handed over with send_file, gathered under the reply as artifact cards
 * so it reads as the turn's deliverable rather than a step in the middle of the work.
 */
export const SentFiles: React.FC<{
  calls: ImageResultCall[];
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
}> = ({ calls, onFileClick }) => {
  const paths = getSentPaths(calls);
  return paths.length > 0 ? <SentFilesSection paths={paths} onFileClick={onFileClick} /> : null;
};

const SentFilesSection: React.FC<{
  paths: string[];
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
}> = ({ paths, onFileClick }) => {
  const { t } = useI18n();
  const { currentChatId, config } = useChatStore();
  return (
    <section aria-label={t('sentFile.heading')} className="flex flex-col gap-2 px-1 pt-1">
      <h3 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {t('sentFile.heading')}
        <span className="font-mono tabular-nums text-neutral-400">{paths.length}</span>
      </h3>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
        {paths.map((path) => {
          const shown = displayPathOf(path);
          const name = shown.split('/').filter(Boolean).pop() || shown;
          const directory = shown.slice(0, shown.lastIndexOf('/') + 1);
          return (
            <ArtifactCard
              key={path}
              kind={artifactKind(path)}
              name={name}
              src={
                currentChatId
                  ? `${getApiBase()}/sandbox/serve?${getSandboxParams(currentChatId, path, config.sandbox_volumes)}`
                  : null
              }
              title={shown}
              onOpen={() => onFileClick?.(path, name)}
              actions={<ArtifactActions path={path} chatId={currentChatId} copyable={false} />}
            >
              {directory && (
                <span className="truncate font-mono text-[10px] text-neutral-400">{directory}</span>
              )}
            </ArtifactCard>
          );
        })}
      </div>
    </section>
  );
};
