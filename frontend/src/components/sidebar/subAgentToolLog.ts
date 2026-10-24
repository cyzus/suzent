export interface ToolLogEntry {
  toolName: string;
  args: string;
  output?: string;
}

interface ToolMessage {
  role?: string;
  content?: unknown;
  tool_call_id?: string;
  tool_calls?: { id?: string; function?: { name?: string; arguments?: unknown } }[];
  parts?: {
    type: string;
    toolCallId?: string;
    toolName?: string;
    args?: unknown;
    output?: unknown;
  }[];
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value);
}

/** Accept both captured stream parts and legacy chat records. */
export function extractToolLog(messages: ToolMessage[]): ToolLogEntry[] {
  const entries: ToolLogEntry[] = [];
  const byId = new Map<string, ToolLogEntry>();
  const outputs = new Map<string, string>();
  for (const msg of messages) {
    if (msg.role === 'tool' && msg.tool_call_id) {
      outputs.set(msg.tool_call_id, text(msg.content));
    }
  }
  const add = (id: string | undefined, entry: ToolLogEntry): void => {
    const existing = id ? byId.get(id) : undefined;
    if (existing) {
      Object.assign(existing, entry, { output: entry.output ?? existing.output });
    } else {
      entries.push(entry);
      if (id) byId.set(id, entry);
    }
  };
  for (const msg of messages) {
    if (msg.role !== 'assistant') continue;
    for (const call of msg.tool_calls ?? []) {
      add(call.id, {
        toolName: call.function?.name ?? 'unknown',
        args: text(call.function?.arguments),
        output: call.id ? outputs.get(call.id) : undefined,
      });
    }
    for (const part of msg.parts ?? []) {
      if (part.type !== 'tool') continue;
      add(part.toolCallId, {
        toolName: part.toolName ?? 'unknown',
        args: text(part.args),
        output:
          part.output == null
            ? part.toolCallId
              ? outputs.get(part.toolCallId)
              : undefined
            : text(part.output),
      });
    }
  }
  return entries;
}
