import { ChatConfig } from '../types/api';
import { useChatStore } from '../hooks/useChatStore'; // (Note: runtime import not used directly here, but kept for context)

// Streaming implementation mirroring logic from Streamlit app.py
// Maintains content blocks (markdown/code) toggled by CODE_TAG sentinel.

export interface StreamCallbacks {
  onDelta: (delta: string) => void;            // incremental markdown delta appended to current assistant message
  onAction?: () => void;                       // plan refresh trigger
  onNewAssistantMessage?: () => void;          // create a new assistant message container (step split)
}

interface ContentBlock { type: 'markdown' | 'code'; content: string }

function assembleForStorage(blocks: ContentBlock[], isInCodeBlock: boolean): string {
  // Build markdown incrementally; keep final code block open if still streaming
  return blocks
    .map((b, i) => {
      if (b.type === 'markdown') return b.content;
      const isLast = i === blocks.length - 1;
      if (isLast && isInCodeBlock) {
        // Open fence only (no closing) so subsequent stream deltas stay inside
        return `\n\n\u0060\u0060\u0060python\n${b.content}`;
      }
      // Closed code block
      return `\n\n\u0060\u0060\u0060python\n${b.content}\n\u0060\u0060\u0060\n\n`;
    })
    .join('');
}

function getStepFootnote(step: any, stepName: string): string {
  let foot = `**${stepName}**`;
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
  return `<span style="color:#bbbbc2;font-size:12px;">${foot}</span>\n\n`;
}

export async function streamChat(prompt: string, config: ChatConfig, callbacks: StreamCallbacks, codeTag = '<code>') {
  const { onDelta, onAction, onNewAssistantMessage } = callbacks;
  const res = await fetch('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ message: prompt, config }),
    headers: { 'Content-Type': 'application/json' }
  });
  if (!res.body) return;

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

      if (type === 'stream_delta') {
        let content: string = data?.content || '';
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
        if (isInCodeBlock) { isInCodeBlock = false; blocks.push({ type: 'markdown', content: '' }); }
        blocks[blocks.length - 1].content += `\n\n${data}`;
        emitDiff();
      } else if (type === 'action') {
        flushPendingIfAny();
        if (onAction) onAction();
        if (isInCodeBlock) { isInCodeBlock = false; blocks.push({ type: 'markdown', content: '' }); }
        let actionMarkdown = '';
        let observations: string | undefined = data?.observations;
        if (observations && !data?.is_final_answer) {
          observations = observations.replace(/^Execution logs:\s*/i, '').trim();
          const splitObs = observations.split(/Last output from code snippet:\s*/i);
          observations = splitObs[0].trimEnd();
          actionMarkdown += `\n\n<details><summary>📝 Execution Logs</summary>\n\n${observations}\n\n</details>`;
        }
        const stepName = `Step: ${data?.step_number}`;
        actionMarkdown += getStepFootnote(data, stepName);
        blocks[blocks.length - 1].content += actionMarkdown;
        emitDiff();
        resetForNewAssistantMessage();
      } else if (type === 'error') {
        flushPendingIfAny();
        if (isInCodeBlock) { isInCodeBlock = false; blocks.push({ type: 'markdown', content: '' }); }
        blocks[blocks.length - 1].content += `\n\n**Error:** ${data}`;
        emitDiff();
        resetForNewAssistantMessage();
      }
    }
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
}
