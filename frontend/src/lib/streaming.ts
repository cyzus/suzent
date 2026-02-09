import type { ChatConfig, FileAttachment } from '../types/api';
import { useChatStore } from '../hooks/useChatStore'; // (Note: runtime import not used directly here, but kept for context)
// import { API_BASE } from './api'; // Removed legacy import
import { getApiBase } from './api';

// Streaming implementation mirroring logic from Streamlit app.py
// Maintains content blocks (markdown/code) toggled by CODE_TAG sentinel.

export interface StreamCallbacks {
  onDelta: (delta: string) => void;
  onAction?: () => void;
  onNewAssistantMessage?: () => void;
  onPlanUpdate?: (plan: any) => void;
  onStreamComplete?: () => void; // new callback for when streaming finishes
  onStreamStopped?: (payload?: any) => void;
  onStepComplete?: (stepInfo: string) => void; // callback when action step completes
  onImagesProcessed?: (images: any[]) => void; // callback when images are processed
}

// Detect if agent is using code tags (CodeAgent) or structured tool calls (ToolCallingAgent)
let detectedAgentType: 'code' | 'toolcalling' | null = null;

interface ContentBlock {
  type: 'markdown' | 'code' | 'log';
  content: string;
  title?: string; // For log blocks
}

function escapeHtml(unsafe: string) {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatLogContent(content: any): string {
  if (typeof content === 'string') return escapeHtml(content);
  try {
    return escapeHtml(JSON.stringify(content, null, 2));
  } catch {
    return escapeHtml(String(content));
  }
}

function assembleForStorage(blocks: ContentBlock[], isInCodeBlock: boolean): string {
  // Build markdown incrementally; keep final code block open if still streaming
  return blocks
    .map((b, i) => {
      if (b.type === 'markdown') return b.content;

      if (b.type === 'log') {
        // Reconstruct the HTML details block for storage
        return `\n\n<details><summary>${b.title || 'Details'}</summary>\n\n<pre><code class="language-text">${b.content}</code></pre>\n\n</details>\n\n`;
      }

      const isLast = i === blocks.length - 1;
      // Preserve whitespace in code blocks - only check if empty
      const cleanContent = String(b.content || '');
      if (!cleanContent) return '';

      if (isLast && isInCodeBlock) {
        // Open fence only (no closing) so subsequent stream deltas stay inside
        return `\n\n\`\`\`python\n${cleanContent}`;
      }
      // Closed code block with proper formatting
      return `\n\n\`\`\`python\n${cleanContent}\n\`\`\`\n\n`;
    })
    .join('');
}

function getStepFootnote(step: any, stepName: string): string {
  let foot = `${stepName}`;
  if (step?.token_usage) {
    const inp = step.token_usage.input_tokens?.toLocaleString?.() ?? step.token_usage.input_tokens;
    const outp = step.token_usage.output_tokens?.toLocaleString?.() ?? step.token_usage.output_tokens;
    foot += ` | Input tokens: ${inp} | Output tokens: ${outp}`;
  }
  const dur = step?.timing?.duration;
  if (dur) {
    const dNum = parseFloat(dur);
    if (!Number.isNaN(dNum)) foot += ` | Duration: ${dNum.toFixed(2)}s`;
  }
  return foot;
}

export async function streamChat(prompt: string, config: ChatConfig, callbacks: StreamCallbacks, codeTag = '<code>', reset = false, chatId?: string | null, imageFiles?: File[], fileAttachments?: FileAttachment[]) {
  const { onDelta, onAction, onNewAssistantMessage, onStreamStopped, onStreamComplete, onPlanUpdate, onStepComplete, onImagesProcessed } = callbacks;

  let body: BodyInit;
  let headers: HeadersInit;

  if (imageFiles && imageFiles.length > 0) {
    // Use FormData for multipart upload when images are present
    const formData = new FormData();
    formData.append('message', prompt);
    formData.append('config', JSON.stringify(config));
    formData.append('reset', String(reset));
    if (chatId) {
      formData.append('chat_id', chatId);
    }
    if (fileAttachments && fileAttachments.length > 0) {
      formData.append('files_metadata', JSON.stringify(fileAttachments));
    }
    imageFiles.forEach((file) => {
      formData.append('files', file);
    });
    body = formData;
    headers = {}; // Let browser set Content-Type with boundary
  } else {
    // Use JSON for backward compatibility when no images
    const payload: any = { message: prompt, config, reset };
    if (chatId) {
      payload.chat_id = chatId;
    }
    if (fileAttachments && fileAttachments.length > 0) {
      payload.files = fileAttachments;
    }
    body = JSON.stringify(payload);
    headers = { 'Content-Type': 'application/json' };
  }



  const apiBase = getApiBase();
  console.log('[streamChat] API_BASE:', apiBase);
  const res = await fetch(`${apiBase}/chat`, {
    method: 'POST',
    body,
    headers
  });
  console.log('[streamChat] Response status:', res.status, 'ok:', res.ok);
  if (!res.ok) {
    console.error('[streamChat] Response not OK:', await res.text());
    return;
  }
  if (!res.body) {
    console.error('[streamChat] No response body');
    return;
  }

  // State for current assistant message
  let blocks: ContentBlock[] = [{ type: 'markdown', content: '' }];
  let isInCodeBlock = false;
  let assembledLen = 0;
  // Buffer for detecting split codeTag across chunks
  let pendingCodeProbe = '';

  const emitDiff = () => {
    const assembled = assembleForStorage(blocks, isInCodeBlock);
    if (assembled.length > assembledLen) {
      const delta = assembled.slice(assembledLen);
      assembledLen = assembled.length;
      onDelta(delta);
    }
  };

  const flushPendingIfAny = () => {
    if (pendingCodeProbe) {
      // Pending never completed a full codeTag -> treat as plain text
      blocks[blocks.length - 1].content += pendingCodeProbe;
      pendingCodeProbe = '';
    }
  };

  const resetForNewAssistantMessage = () => {
    flushPendingIfAny();
    blocks = [{ type: 'markdown', content: '' }];
    isInCodeBlock = false;
    assembledLen = 0;
    if (onNewAssistantMessage) onNewAssistantMessage();
  };

  // Start first assistant message container
  if (onNewAssistantMessage) onNewAssistantMessage();

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let terminatedEarly = false;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || '';
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) continue;
      if (!line.startsWith('data:')) continue;
      const jsonStr = line.slice(5).trim();
      let obj: any;
      try { obj = JSON.parse(jsonStr); } catch { continue; }
      const type = obj.type;
      const data = obj.data;

      // Auto-detect agent type from stream_delta content
      if (type === 'stream_delta' && !detectedAgentType) {
        const content = data?.content || '';
        if (content.includes(codeTag)) {
          detectedAgentType = 'code';
        } else if (data?.tool_calls && data.tool_calls.length > 0) {
          detectedAgentType = 'toolcalling';
        }
      }

      if (type === 'stream_delta') {
        let content: string = data?.content || '';

        // ToolCallingAgent: handle tool_calls in stream_delta
        if (data?.tool_calls && data.tool_calls.length > 0) {
          flushPendingIfAny();
          if (isInCodeBlock) { isInCodeBlock = false; blocks.push({ type: 'markdown', content: '' }); }

          const toolCall = data.tool_calls[0]; // Usually one at a time
          if (toolCall?.function?.name) {
            const toolName = toolCall.function.name;
            const toolArgs = toolCall.function.arguments || '';
            blocks[blocks.length - 1].content += `\n\n**🔧 Calling Tool:** \`${toolName}\`\n\n`;
            if (toolArgs && toolArgs !== '{}') {
              try {
                const parsedArgs = typeof toolArgs === 'string' ? JSON.parse(toolArgs) : toolArgs;
                blocks[blocks.length - 1].content += `**Arguments:**\n\`\`\`json\n${JSON.stringify(parsedArgs, null, 2)}\n\`\`\`\n\n`;
              } catch {
                blocks[blocks.length - 1].content += `**Arguments:** ${toolArgs}\n\n`;
              }
            }
            emitDiff();
          }
          continue;
        }

        if (!content) continue;
        content = pendingCodeProbe + content;
        pendingCodeProbe = '';
        let processPos = 0;
        while (true) {
          const idx = content.indexOf(codeTag, processPos);
          if (idx === -1) break;
          const before = content.slice(processPos, idx);
          if (before) blocks[blocks.length - 1].content += before;
          if (isInCodeBlock) {
            // Close current code block by toggling to markdown
            blocks.push({ type: 'markdown', content: '' });
            isInCodeBlock = false;
          } else {
            // Start a new code block
            blocks.push({ type: 'code', content: '' });
            isInCodeBlock = true;
          }
          processPos = idx + codeTag.length;
        }
        let leftover = content.slice(processPos);
        let keepForProbe = 0;
        for (let k = Math.min(codeTag.length - 1, leftover.length); k > 0; k--) {
          if (codeTag.startsWith(leftover.slice(-k))) { keepForProbe = k; break; }
        }
        if (keepForProbe) {
          pendingCodeProbe = leftover.slice(-keepForProbe);
          leftover = leftover.slice(0, leftover.length - keepForProbe);
        }
        if (leftover) blocks[blocks.length - 1].content += leftover;
        emitDiff();
      } else if (type === 'final_answer') {
        flushPendingIfAny();

        // Final answer should be a separate message
        // First, emit what we have so far (if any)
        emitDiff();

        // Start a new assistant message for the final answer
        if (onNewAssistantMessage) onNewAssistantMessage();

        // Reset blocks and assembledLen for new message
        blocks = [{ type: 'markdown', content: '' }];
        isInCodeBlock = false;
        assembledLen = 0;  // Critical: reset so emitDiff works for new message

        // Add final answer as clean markdown
        const finalAnswerContent = String(data || '').trim();
        if (finalAnswerContent) {
          blocks[0].content = finalAnswerContent;
          emitDiff();
        }

        // Include final answer token usage in step tracking
        if (obj.token_usage && onStepComplete) {
          const stepName = 'Final Answer';
          const stepInfo = getStepFootnote(obj, stepName);
          onStepComplete(stepInfo);
        }
      } else if (type === 'tool_output') {
        // ToolCallingAgent specific: tool execution result
        flushPendingIfAny();
        if (onAction) onAction();
        if (isInCodeBlock) { isInCodeBlock = false; blocks.push({ type: 'markdown', content: '' }); }

        const toolName = data?.tool_call?.name || 'unknown';
        const output = data?.output || data?.observation || '';

        if (output && !data?.is_final_answer) {
          const escapedOutput = formatLogContent(output);
          // Push a log block instead of appending HTML string
          if (isInCodeBlock) { isInCodeBlock = false; blocks.push({ type: 'markdown', content: '' }); }
          blocks.push({
            type: 'log',
            content: escapedOutput,
            title: `📦 Tool Output: \`${toolName}\``
          });
          blocks.push({ type: 'markdown', content: '' });
          emitDiff();
        }
      } else if (type === 'action') {
        flushPendingIfAny();
        if (onAction) onAction();
        if (isInCodeBlock) { isInCodeBlock = false; blocks.push({ type: 'markdown', content: '' }); }
        let actionMarkdown = '';

        // Handle observations differently for CodeAgent vs ToolCallingAgent
        let observations: string | undefined = data?.observations;
        if (observations && !data?.is_final_answer) {
          // CodeAgent format: "Execution logs:\nLast output from code snippet:\n..."
          if (data?.code_action) {
            // This is CodeAgent
            observations = observations.replace(/^Execution logs:\s*/i, '').trim();
            const splitObs = observations.split(/Last output from code snippet:\s*/i);
            observations = splitObs[0].trimEnd();
            if (observations) {
              const escapedObs = formatLogContent(observations);
              // Push a log block
              if (isInCodeBlock) { isInCodeBlock = false; blocks.push({ type: 'markdown', content: '' }); }
              blocks.push({
                type: 'log',
                content: escapedObs,
                title: 'Execution Logs'
              });
              blocks.push({ type: 'markdown', content: '' });
            }
          } else {
            // ToolCallingAgent: plain observation text
            // Usually already shown in tool_output, skip duplicate
          }
        }

        blocks[blocks.length - 1].content += actionMarkdown;
        emitDiff();

        // Send step completion info to callback (will be displayed outside bubble)
        if (data?.step_number && onStepComplete) {
          const stepName = `Step: ${data.step_number}`;
          const stepInfo = getStepFootnote(data, stepName);
          onStepComplete(stepInfo);
        }

        // Only reset if not final answer
        if (!data?.is_final_answer) {
          resetForNewAssistantMessage();
        }
      } else if (type === 'action_step') {
        // ActionStep event (mapped from ActionStep type) - redundant, already handled in 'action'
        // This shouldn't appear since ActionStep is mapped to 'action' in step_to_json_event
      } else if (type === 'action_output') {
        // Handle action_output events (both agents can send these)
        const output = data?.output;
        if (output && !data?.is_final_answer) {
          flushPendingIfAny();
          if (isInCodeBlock) { isInCodeBlock = false; blocks.push({ type: 'markdown', content: '' }); }
          const outputStr = typeof output === 'object' ? JSON.stringify(output, null, 2) : output;
          blocks[blocks.length - 1].content += `\n\n**Result:**\n\`\`\`text\n${outputStr}\n\`\`\`\n\n`;
          emitDiff();
        }
      } else if (type === 'error') {
        flushPendingIfAny();
        if (isInCodeBlock) { isInCodeBlock = false; blocks.push({ type: 'markdown', content: '' }); }
        blocks[blocks.length - 1].content += `\n\n**Error:** ${data}`;
        emitDiff();
        resetForNewAssistantMessage();
      } else if (type === 'plan_refresh') {
        if (data && onPlanUpdate) onPlanUpdate(data);
        if (onAction) onAction();
      } else if (type === 'images_processed') {
        // Backend has processed uploaded images, replace previews with compressed versions
        if (data && onImagesProcessed) {
          onImagesProcessed(data);
        }
      } else if (type === 'stopped') {
        terminatedEarly = true;
        if (onStreamStopped) onStreamStopped(data);
        break;
      }
    }
    if (terminatedEarly) break;
  }
  // Flush any trailing pending probe characters (incomplete tag) at end of stream
  if (pendingCodeProbe) {
    blocks[blocks.length - 1].content += pendingCodeProbe;
    pendingCodeProbe = '';
    emitDiff();
  }
  // Close any still-open code block at end so rendering finalizes
  if (isInCodeBlock) {
    isInCodeBlock = false;
    // Re-emit to add closing fence
    emitDiff();
  }

  // Reset agent type detection for next stream
  detectedAgentType = null;

  // Trigger final save when streaming completes
  if (onStreamComplete) {
    onStreamComplete();
  }
}
