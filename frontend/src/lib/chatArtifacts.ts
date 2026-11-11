import type { AGUIPart } from '../types/agui';
import type { Message } from '../types/api';
import { splitAssistantContent } from './chatUtils';
import { parseToolResultEnvelope } from '../components/chat/ToolCallBlock';

export type ChatArtifactKind = 'image' | 'video' | 'audio' | 'file';

export interface ChatArtifact {
  /** Path as the tool or snapshot reported it; the serve route resolves it. */
  path: string;
  /** Workspace-relative path for display. */
  displayPath: string;
  name: string;
  kind: ChatArtifactKind;
  /** Index into the transcript of the turn that last produced it. */
  messageIndex: number;
}

/**
 * Tools whose `saved_paths` are deliverables: media the agent made, and files it
 * handed to the user with `send_file`. Not files it only looked at.
 */
const OUTPUT_TOOLS = new Set(['generate_image', 'edit_image', 'check_video', 'speak', 'send_file']);

/** The project library's deliverables folder, which the prompts point the agent at. */
const LIBRARY_ARTIFACTS = /\/(?:sandbox\/projects\/[^/]+|workspace)\/artifacts\//;

const EXTENSION_KINDS: Record<string, ChatArtifactKind> = {
  png: 'image',
  jpg: 'image',
  jpeg: 'image',
  gif: 'image',
  webp: 'image',
  svg: 'image',
  mp4: 'video',
  mov: 'video',
  webm: 'video',
  m4v: 'video',
  mp3: 'audio',
  wav: 'audio',
  ogg: 'audio',
  m4a: 'audio',
  aac: 'audio',
  flac: 'audio',
  opus: 'audio',
};

export function artifactKind(path: string): ChatArtifactKind {
  const extension = path.split('.').pop()?.toLowerCase() ?? '';
  return EXTENSION_KINDS[extension] ?? 'file';
}

function displayPathOf(path: string): string {
  const normalized = path.replace(/\\/g, '/');
  const projectMatch = normalized.match(/\/sandbox\/projects\/[^/]+\/(.+)$/);
  if (projectMatch) return projectMatch[1];
  return normalized.replace(/^\/workspace\//, '');
}

function savedPaths(toolName: string | undefined, output: string | undefined): string[] {
  if (!toolName || !OUTPUT_TOOLS.has(toolName)) return [];
  const envelope = parseToolResultEnvelope(output);
  if (!envelope || envelope.success === false) return [];
  const metadata = envelope.metadata as { saved_paths?: unknown } | undefined;
  const paths = metadata?.saved_paths;
  return Array.isArray(paths)
    ? paths.filter((path): path is string => typeof path === 'string' && !!path.trim())
    : [];
}

function partPaths(parts: AGUIPart[]): string[] {
  return parts.flatMap((part) =>
    part.type === 'tool' && part.state !== 'error' && !part.outcome
      ? savedPaths(part.toolName, part.output)
      : []
  );
}

function legacyPaths(content: string): string[] {
  return splitAssistantContent(content).flatMap((block) =>
    block.type === 'toolCall' && block.content ? savedPaths(block.toolName, block.content) : []
  );
}

/**
 * Files the agent produced in this conversation, newest first, one entry per path.
 *
 * Counts what generation tools and `send_file` saved, and files the agent wrote
 * into the project library's `artifacts/`. Other edits are working changes, shown
 * on each turn's changed-files card, and files it only read are not outputs.
 */
export function collectChatArtifacts(messages: Message[]): ChatArtifact[] {
  const byPath = new Map<string, ChatArtifact>();
  const add = (path: string, messageIndex: number): void => {
    const shown = displayPathOf(path);
    byPath.delete(path);
    byPath.set(path, {
      path,
      displayPath: shown,
      name: shown.split('/').filter(Boolean).pop() || shown,
      kind: artifactKind(path),
      messageIndex,
    });
  };

  messages.forEach((message, index) => {
    if (message.role !== 'assistant') return;
    const paths = message.parts?.length
      ? partPaths(message.parts)
      : message.content
        ? legacyPaths(message.content)
        : [];
    for (const path of paths) add(path, index);
    if (message.file_changes_undone) return;
    for (const change of message.file_changes ?? []) {
      if (change.after_exists === false) byPath.delete(change.path);
      else if (LIBRARY_ARTIFACTS.test(change.path.replace(/\\/g, '/'))) add(change.path, index);
    }
  });

  return [...byPath.values()].reverse();
}
