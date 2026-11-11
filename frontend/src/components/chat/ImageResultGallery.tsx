import React from 'react';
import { VideoResultPlayer } from './VideoResultPlayer';
import { SpeechPlayer } from './SpeechPlayer';
import { getApiBase, getSandboxParams } from '../../lib/api';
import { useChatStore } from '../../hooks/useChatStore';
import { getMediaToolPaths, MediaToolRenderer } from './MediaToolRenderer';
import { parseToolResultEnvelope } from './ToolCallBlock';
import { SentFileCard } from './SentFileCard';

interface ImageResultCall {
  toolName?: string;
  output?: string;
  args?: string;
}

const SENT_IMAGE = /\.(png|jpe?g|gif|webp)$/i;
const SENT_VIDEO = /\.(mp4|mov|webm|m4v)$/i;
const SENT_AUDIO = /\.(mp3|m4a|aac|wav|ogg|opus)$/i;

/**
 * Paths the agent handed over with send_file. A call whose chat-app upload failed still
 * lists them: the files exist on this computer, so they are shown here regardless.
 */
function sentPaths(call: ImageResultCall): string[] {
  if (call.toolName !== 'send_file') return [];
  const result = parseToolResultEnvelope(call.output);
  if (!result?.metadata || typeof result.metadata !== 'object') return [];
  const paths = (result.metadata as Record<string, unknown>).saved_paths;
  return Array.isArray(paths)
    ? paths.filter((path): path is string => typeof path === 'string' && !!path.trim())
    : [];
}

/** Sent files that are neither images, video nor audio, shown as file cards. */
export function getSentFilePaths(calls: ImageResultCall[]): string[] {
  const paths = new Set<string>();
  for (const call of calls)
    for (const path of sentPaths(call))
      if (!SENT_IMAGE.test(path) && !SENT_VIDEO.test(path) && !SENT_AUDIO.test(path))
        paths.add(path);
  return [...paths];
}

export function getImageResultPaths(calls: ImageResultCall[]): string[] {
  const paths = new Set<string>();
  for (const call of calls) {
    for (const path of sentPaths(call)) if (SENT_IMAGE.test(path)) paths.add(path);
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
    if (call.toolName === 'send_file')
      return sentPaths(call)
        .filter((path) => (SENT_VIDEO.test(path) || SENT_AUDIO.test(path)) && !seen.has(path))
        .map((path) => {
          seen.add(path);
          return {
            key: path,
            kind: SENT_VIDEO.test(path) ? ('video' as const) : ('audio' as const),
            path,
            metadata: { saved_paths: [path] },
          };
        });
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
  return (
    getImageResultPaths(calls).length > 0 ||
    getPlayableResults(calls).length > 0 ||
    getSentFilePaths(calls).length > 0
  );
}

/** Media that should close an activity group to preserve its timeline position. */
export function hasVisualMediaResults(calls: ImageResultCall[]): boolean {
  return (
    getImageResultPaths(calls).length > 0 ||
    getSentFilePaths(calls).length > 0 ||
    getPlayableResults(calls).some((item) => item.kind === 'video')
  );
}

export const ImageResultGallery: React.FC<{ calls: ImageResultCall[]; showImages?: boolean }> = ({
  calls,
  showImages = true,
}) => {
  const paths = getImageResultPaths(calls);
  const media = getPlayableResults(calls);
  const files = getSentFilePaths(calls);
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
      {files.length > 0 && (
        <div className="my-2 flex flex-col items-start gap-2">
          {files.map((path) => (
            <SentFileCard key={path} path={path} />
          ))}
        </div>
      )}
    </>
  );
};
