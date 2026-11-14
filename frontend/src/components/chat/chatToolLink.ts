import { parseToolResultEnvelope } from './ToolCallBlock';
import { normalizeToolName } from './toolSummary';

export interface LinkedChat {
  id: string;
  title: string | null;
}

// Regent's tools whose result names the session the work went to.
const CHAT_LINK_TOOLS = new Set(['agent_dispatch', 'mailbox']);

/**
 * The local session a dispatch or re-route reached, from the tool's result
 * metadata. Only a local session carries agent_title; a paired Suzent or A2A
 * agent address has no chat here to open.
 */
export function linkedChatFor(
  toolName: string,
  metadata: Record<string, unknown> | null | undefined
): LinkedChat | null {
  if (!CHAT_LINK_TOOLS.has(normalizeToolName(toolName))) return null;
  const id = metadata?.agent_id;
  const title = metadata?.agent_title;
  if (typeof id !== 'string' || !id || typeof title !== 'string') return null;
  return { id, title: title.trim() || null };
}

/** Every distinct session a group of finished tool calls linked to, in order. */
export function linkedChatsFromTools(
  tools: { toolName?: string; output?: string; failed?: boolean; running?: boolean }[]
): LinkedChat[] {
  const seen = new Map<string, LinkedChat>();
  for (const tool of tools) {
    if (tool.failed || tool.running || !tool.toolName) continue;
    const metadata = parseToolResultEnvelope(tool.output)?.metadata;
    const link = linkedChatFor(
      tool.toolName,
      metadata && typeof metadata === 'object' && !Array.isArray(metadata)
        ? (metadata as Record<string, unknown>)
        : null
    );
    if (link && !seen.has(link.id)) seen.set(link.id, link);
  }
  return [...seen.values()];
}
