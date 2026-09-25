import React from 'react';
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

export const ImageResultGallery: React.FC<{ calls: ImageResultCall[] }> = ({ calls }) => {
  const paths = getImageResultPaths(calls);
  if (!paths.length) return null;
  return (
    <ImageToolRenderer
      toolName="generate_image"
      parsedArgs={null}
      metadata={{ saved_paths: [...paths] }}
    />
  );
};
