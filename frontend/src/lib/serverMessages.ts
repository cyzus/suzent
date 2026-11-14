import type { Message } from '../types/api';
import { collectRunTimings } from './runTiming';
import { hideStreamingDrafts } from './streamingDrafts';
import { hasToolContinuation } from './toolContinuation';

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Track the newest server row folded into a coalesced assistant bubble.
 *
 * A turn's rows collapse into one bubble that keeps the *first* model
 * response's timestamp, and that timestamp marks when the response began --
 * every tool result and follow-up response it led to is later. Without this,
 * nothing downstream can tell how long the turn actually worked.
 */
function noteTurnActivity(bubble: Partial<Message>, timestamp?: string, source?: Message): void {
  bubble.run_timings = collectRunTimings([bubble, ...(source ? [source] : [])]);
  if (!timestamp) return;
  const current = bubble.turn_last_activity_at;
  if (!current || new Date(timestamp).getTime() > new Date(current).getTime()) {
    bubble.turn_last_activity_at = timestamp;
  }
}

/**
 * Fold the backend's stored rows (strict tool_calls arrays and 'tool' roles)
 * into the bubbles the transcript renders, with tool calls as the
 * `<details>` blocks the UI parser expects.
 */
export function mapServerMessages(serverMessages: any[]): Message[] {
  // Match recovery drafts before tool continuations change the response content.
  // Keep the original array indices for forks and file-change references.
  const visibleServerMessages = new Set(hideStreamingDrafts(serverMessages, false));
  const mappedMessages: Message[] = [];

  let currentAssistant: Partial<Message> | null = null;
  // True while the currentAssistant had tool_calls but hasn't yet received
  // a follow-up assistant message (the final-text continuation of that turn).
  // Reset to false once the continuation arrives so the NEXT assistant is a
  // new independent bubble (e.g. a wakeup turn).
  let awaitingToolContinuation = false;

  for (const [serverMessageIndex, msg] of serverMessages.entries()) {
    if (!visibleServerMessages.has(msg)) continue;
    if (msg.role === 'user') {
      // Empty user rows are tool-resume continuations (system-reminder injected
      // by the backend, then stripped to empty). Drop them — they don't represent
      // a real turn and must not flush the assistant buffer or act as boundaries.
      if (!(msg.content || '').trim() && !msg.images?.length && !msg.files?.length) {
        continue;
      }
      if (currentAssistant) {
        mappedMessages.push(currentAssistant as Message);
        currentAssistant = null;
      }
      awaitingToolContinuation = false;
      mappedMessages.push({
        ...msg,
        raw_message_end_index: serverMessageIndex + 1,
      });
    } else if (msg.role === 'system_triggered' || msg.role === 'trigger') {
      // 'trigger' is the legacy name; normalize to 'system_triggered' so the
      // rest of the render pipeline only needs to handle one role.
      if (currentAssistant) {
        mappedMessages.push(currentAssistant as Message);
        currentAssistant = null;
      }
      awaitingToolContinuation = false;
      mappedMessages.push({
        ...msg,
        role: 'system_triggered',
        raw_message_end_index: serverMessageIndex + 1,
      } as Message);
    } else if (msg.role === 'assistant') {
      if (!currentAssistant) {
        currentAssistant = {
          ...msg,
          content: msg.content || '',
          raw_message_end_index: serverMessageIndex + 1,
          file_change_message_index: msg.file_changes?.length ? serverMessageIndex : undefined,
        };
        awaitingToolContinuation = false;
      } else if (awaitingToolContinuation) {
        // This assistant message is the final-text continuation of the
        // preceding tool-call turn — merge it into the same bubble.
        if (msg.content) {
          currentAssistant.content =
            (currentAssistant.content ? currentAssistant.content + '\n\n' : '') + msg.content;
        }
        if (Array.isArray(msg.parts) && msg.parts.length > 0) {
          currentAssistant.parts = [
            ...((currentAssistant.parts as any[] | undefined) || []),
            ...msg.parts,
          ];
        }
        if (Array.isArray(msg.file_changes) && msg.file_changes.length > 0) {
          currentAssistant.file_changes = msg.file_changes;
          currentAssistant.file_changes_undone = msg.file_changes_undone === true;
          currentAssistant.file_change_message_index = serverMessageIndex;
        }
        currentAssistant.raw_message_end_index = serverMessageIndex + 1;
        awaitingToolContinuation = false;
      } else {
        // Independent assistant turn (e.g. wakeup) — new bubble.
        mappedMessages.push(currentAssistant as Message);
        currentAssistant = {
          ...msg,
          content: msg.content || '',
          raw_message_end_index: serverMessageIndex + 1,
          file_change_message_index: msg.file_changes?.length ? serverMessageIndex : undefined,
        };
        awaitingToolContinuation = false;
      }
      noteTurnActivity(currentAssistant!, msg.timestamp, msg);
      awaitingToolContinuation = hasToolContinuation(msg);
      if (msg.tool_calls && Array.isArray(msg.tool_calls)) {
        msg.tool_calls.forEach((tc: any) => {
          const args = escapeHtml(
            typeof tc.function.arguments === 'string'
              ? tc.function.arguments
              : JSON.stringify(tc.function.arguments)
          );
          const stateAttr =
            tc.state === 'approval-requested' ? ' data-approval-state="pending"' : '';
          const idAttr = tc.id ? ` data-approval-id="${escapeHtml(tc.id)}"` : '';
          currentAssistant!.content += `\n<details data-tool-call-id="${escapeHtml(tc.id ?? '')}"${idAttr}${stateAttr}><summary>🔧 ${escapeHtml(tc.function.name)}</summary>\n<pre><code class="language-json">${args}</code></pre>\n</details>\n`;
        });
        awaitingToolContinuation = true;
      }
    } else if (msg.role === 'tool') {
      if (!currentAssistant) {
        currentAssistant = {
          role: 'assistant',
          content: '',
          raw_message_end_index: serverMessageIndex + 1,
        };
      }
      currentAssistant.content += `\n<details data-tool-call-id="${escapeHtml(msg.tool_call_id ?? '')}"><summary>📦 ${escapeHtml(msg.name ?? '')}</summary>\n<pre><code class="language-text">${escapeHtml(msg.content ?? '')}</code></pre>\n</details>\n`;
      currentAssistant.raw_message_end_index = serverMessageIndex + 1;
      noteTurnActivity(currentAssistant!, msg.timestamp, msg);
      awaitingToolContinuation = true;
    } else {
      if (currentAssistant) {
        mappedMessages.push(currentAssistant as Message);
        currentAssistant = null;
      }
      awaitingToolContinuation = false;
      mappedMessages.push({
        ...msg,
        raw_message_end_index: serverMessageIndex + 1,
      });
    }
  }
  if (currentAssistant) {
    mappedMessages.push(currentAssistant as Message);
  }
  return mappedMessages;
}
