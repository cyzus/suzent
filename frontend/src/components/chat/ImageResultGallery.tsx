import React from 'react';
import { VideoResultPlayer } from './VideoResultPlayer';
import { SpeechPlayer } from './SpeechPlayer';
import { getApiBase, getSandboxParams } from '../../lib/api';
import { useChatStore } from '../../hooks/useChatStore';
import { getImageToolPaths, ImageToolRenderer } from './ImageToolRenderer';
import { parseToolResultEnvelope } from './ToolCallBlock';

interface ImageResultCall {
  toolName?: string;
  output?: string;
}

export function getImageResultPaths(calls: ImageResultCall[]): string[] {
  const paths = new Set<string>();
  for (const call of calls) {
    if (call.toolName !== 'generate_image' && call.toolName !== 'edit_image') continue;
    const result = parseToolResultEnvelope(call.output);
    if (result?.success !== true || !result.metadata || typeof result.metadata !== 'object')
      continue;
    for (const path of getImageToolPaths({
      toolName: call.toolName,
      parsedArgs: null,
      metadata: result.metadata as Record<string, unknown>,
    }))
      paths.add(path);
  }
  return [...paths];
}

interface PlayableResult {
  key: string;
  kind: 'video' | 'audio' | 'system';
  path?: string;
  metadata: Record<string, unknown>;
}
export function getPlayableResults(calls: ImageResultCall[]): PlayableResult[] {
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
      .filter((path): path is string => typeof path === 'string' && !!path.trim())
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

export const ImageResultGallery: React.FC<{ calls: ImageResultCall[] }> = ({ calls }) => {
  const paths = getImageResultPaths(calls);
  const media = getPlayableResults(calls);
  const { currentChatId, config } = useChatStore();
  return (
    <>
      {paths.length > 0 && (
        <ImageToolRenderer
          toolName="generate_image"
          parsedArgs={null}
          metadata={{ saved_paths: paths }}
        />
      )}
      {media.map((item) => {
        if (item.kind === 'system') return <SpeechPlayer key={item.key} metadata={item.metadata} />;
        if (!currentChatId || !item.path) return null;
        const src = `${getApiBase()}/sandbox/serve?${getSandboxParams(currentChatId, item.path, config.sandbox_volumes)}`;
        return item.kind === 'video' ? (
          <VideoResultPlayer key={src} src={src} path={item.path} />
        ) : (
          <SpeechPlayer key={item.key} src={src} metadata={item.metadata} />
        );
      })}
    </>
  );
};
