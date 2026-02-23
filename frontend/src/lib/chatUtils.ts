
export interface ContentBlock {
  type: 'markdown' | 'code' | 'log' | 'toolCall' | 'codeStep';
  content: string;
  lang?: string;
  title?: string;
  toolName?: string;
  toolArgs?: string;
  // CodeAgent step fields
  thought?: string;
  codeContent?: string;
  executionLogs?: string;
  result?: string;
}

// Helper to normalize Python code indentation
export function normalizePythonCode(code: string): string {
  const lines = code.split('\n');
  if (lines.length === 0) return code;

  // Find minimum indentation (ignoring empty lines)
  let minIndent = Infinity;
  for (const line of lines) {
    if (line.trim().length > 0) {
      const leadingSpaces = line.match(/^[ ]*/)?.[0].length || 0;
      minIndent = Math.min(minIndent, leadingSpaces);
    }
  }

  // Remove the minimum indentation from all lines
  if (minIndent > 0 && minIndent !== Infinity) {
    return lines.map(line =>
      line.trim().length > 0 ? line.slice(minIndent) : line
    ).join('\n');
  }

  return code;
}

// Helper to generate stable key for a block based on its position and type
// During streaming, blocks grow but don't change position, so index is stable
export function generateBlockKey(block: ContentBlock, index: number, messageIdx: number): string {
  // Use message index + block index + type for a stable key that doesn't change as content grows
  return `msg-${messageIdx}-block-${index}-${block.type}`;
}

const IGNORED_TOOL_NAMES = ['final_answer', 'final answer'];

/** Check if parsed blocks represent a tool-only message (no real prose/code content) */
export function isToolOnlyContent(content: string | undefined): boolean {
  if (!content?.trim()) return false;
  const blocks = splitAssistantContent(content);
  // Filter out ignored tool calls
  const filtered = blocks.filter(b => {
    if (b.type !== 'toolCall') return true;
    return !IGNORED_TOOL_NAMES.includes((b.toolName || '').toLowerCase());
  });
  if (filtered.length === 0) return false;
  // Check if all remaining blocks are toolCall, or have no meaningful content
  const contentBlocks = filtered.filter(b => b.type !== 'toolCall');
  const hasContent = contentBlocks.some(b => b.content.trim().length > 0);
  return !hasContent;
}

/** Check if parsed blocks represent a CodeAgent intermediate step */
export function isCodeStepContent(content: string | undefined): boolean {
  if (!content?.trim()) return false;
  const trimmed = content.trim();
  const blocks = splitAssistantContent(content);
  const meaningful = blocks.filter(b => b.type !== 'markdown' || b.content.trim().length > 0);
  if (meaningful.length > 0 && meaningful.every(b => b.type === 'codeStep')) return true;
  // Also detect "Thought:"-only messages that didn't get a code block
  if (meaningful.length === 1 && meaningful[0].type === 'markdown' && meaningful[0].content.trim().startsWith('Thought:')) return true;
  // Detect raw final_answer(...) calls that leaked as content
  if (/^\s*final_answer\s*\(/i.test(trimmed)) return true;
  // Detect messages that are only a code block calling final_answer
  if (meaningful.length === 1 && meaningful[0].type === 'code' && /final_answer\s*\(/i.test(meaningful[0].content)) return true;
  // Detect CodeAgent steps without "Thought:" prefix: markdown + code + execution logs
  const hasCode = meaningful.some(b => b.type === 'code' && b.content.trim());
  const hasLogs = meaningful.some(b => b.type === 'log' && b.title === 'Execution Logs');
  if (hasCode && hasLogs) return true;
  return false;
}

/** Check if message is an intermediate step (tool-only or codeStep) — not user-facing content.
 *  If stepInfo is provided, it's a definitive signal the message is an intermediate step. */
export function isIntermediateStepContent(content: string | undefined, stepInfo?: string): boolean {
  if (stepInfo) return true;
  return isToolOnlyContent(content) || isCodeStepContent(content);
}


// Helper to split assistant content into markdown + code + log + toolCall blocks
export function splitAssistantContent(content: string): ContentBlock[] {
  const blocks: ContentBlock[] = [];

  // Regex to find <details> blocks (logs and tool calls stored as logs)
  const logRegex = /<details><summary>(.*?)<\/summary>\s*<pre><code class="language-text">([\s\S]*?)<\/code><\/pre>\s*<\/details>/g;

  let lastIndex = 0;
  let match;

  // First pass: split by log/details blocks
  const splits: { type: 'markdown' | 'log'; content: string; title?: string }[] = [];

  while ((match = logRegex.exec(content)) !== null) {
    const before = content.slice(lastIndex, match.index);
    if (before) {
      splits.push({ type: 'markdown', content: before });
    }

    // Decode HTML entities in content for display
    const rawContent = match[2]
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#039;/g, "'");

    splits.push({
      type: 'log',
      title: match[1],
      content: rawContent
    });

    lastIndex = logRegex.lastIndex;
  }

  const remaining = content.slice(lastIndex);
  if (remaining) {
    splits.push({ type: 'markdown', content: remaining });
  }

  // Second pass: process markdown blocks for code fences
  for (const split of splits) {
    if (split.type === 'log') {
      blocks.push(split as ContentBlock);
      continue;
    }

    // Process markdown for code blocks (existing logic)
    let i = 0;
    const subContent = split.content;
    const len = subContent.length;
    let currentMarkdown = '';

    while (i < len) {
      const fenceStart = subContent.indexOf('```', i);
      if (fenceStart === -1) {
        currentMarkdown += subContent.slice(i);
        break;
      }

      currentMarkdown += subContent.slice(i, fenceStart);
      const langLineEnd = subContent.indexOf('\n', fenceStart + 3);

      if (langLineEnd === -1) {
        currentMarkdown += subContent.slice(fenceStart);
        i = len;
        break;
      }

      const langToken = subContent.slice(fenceStart + 3, langLineEnd).trim();
      const cleanLang = langToken.replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();
      const validLanguages = ['python', 'javascript', 'typescript', 'java', 'cpp', 'c', 'go', 'rust', 'sql', 'html', 'css', 'json', 'yaml', 'xml', 'bash', 'shell', 'powershell', 'php', 'ruby', 'swift', 'kotlin', 'dart', 'r', 'matlab', 'scala', 'perl', 'lua', 'haskell', 'clojure', 'elixir', 'erlang', 'fsharp', 'ocaml', 'pascal', 'fortran', 'cobol', 'assembly', 'asm', 'text', 'plain'];
      const lang = validLanguages.includes(cleanLang) ? cleanLang : 'text';

      const closingFenceRegex = /\n[ \t]*```/g;
      closingFenceRegex.lastIndex = langLineEnd + 1;
      const closingMatch = closingFenceRegex.exec(subContent);
      const closingFence = closingMatch ? closingMatch.index : -1;

      if (closingFence === -1) {
        if (currentMarkdown) {
          blocks.push({ type: 'markdown', content: currentMarkdown });
          currentMarkdown = '';
        }
        let codeBody = subContent.slice(langLineEnd + 1);
        if (lang === 'python') codeBody = normalizePythonCode(codeBody);
        blocks.push({ type: 'code', content: codeBody, lang });
        i = len;
        break;
      } else {
        if (currentMarkdown) {
          blocks.push({ type: 'markdown', content: currentMarkdown });
          currentMarkdown = '';
        }
        let codeBody = subContent.slice(langLineEnd + 1, closingFence);
        if (lang === 'python') codeBody = normalizePythonCode(codeBody);
        blocks.push({ type: 'code', content: codeBody, lang });
        i = closingFence + (closingMatch ? closingMatch[0].length : 4);
      }
    }
    if (currentMarkdown) {
      blocks.push({ type: 'markdown', content: currentMarkdown });
    }
  }

  // Post-process: convert tool-titled log blocks to toolCall blocks FIRST
  // Tool call invocations have title starting with 🔧, tool outputs with 📦
  const converted = blocks
    .map(b => {
      if (b.type !== 'log' || !b.title) return b;

      const toolInvokeMatch = b.title.match(/^\u{1F527}\s+(.+)$/u);
      if (toolInvokeMatch) {
        return {
          type: 'toolCall' as const,
          content: '',
          toolName: toolInvokeMatch[1],
          toolArgs: b.content || undefined,
        };
      }

      const toolOutputMatch = b.title.match(/^\u{1F4E6}\s+(.+)$/u);
      if (toolOutputMatch) {
        return {
          type: 'toolCall' as const,
          content: b.content,
          toolName: toolOutputMatch[1],
        };
      }

      return b;
    })
    // Filter AFTER conversion so toolCall blocks with empty content are kept
    .filter(b => b.content !== '' || b.type === 'toolCall');

  return mergeCodeAgentSteps(mergeToolCallPairs(converted));
}

/**
 * Detect and merge CodeAgent step patterns into codeStep blocks.
 * Pattern: markdown(thought text) + code(python) + optional log("Execution Logs") + optional result
 * The thought may or may not start with "Thought:" prefix.
 * Detection heuristic: markdown + code block + Execution Logs, OR markdown("Thought:...") + code block.
 * The result can appear as markdown("**Result:**") + code(text) or as markdown containing "**Result:**\n```text\n...\n```"
 */
function mergeCodeAgentSteps(blocks: ContentBlock[]): ContentBlock[] {
  if (blocks.length < 2) return blocks;

  const firstMeaningful = blocks.find(b => b.content.trim().length > 0);
  if (!firstMeaningful || firstMeaningful.type !== 'markdown') return blocks;

  const hasThoughtPrefix = firstMeaningful.content.trim().startsWith('Thought:');
  const hasExecutionLogs = blocks.some(b => b.type === 'log' && b.title === 'Execution Logs');
  const hasCodeBlock = blocks.some(b => b.type === 'code' && b.content.trim());

  // Merge if we have markdown + code block (every CodeAgent step has this pattern)
  if (!hasThoughtPrefix && !hasCodeBlock) {
    return blocks;
  }

  // Find the indices of the pattern components
  const thoughtIdx = blocks.indexOf(firstMeaningful);
  let codeIdx = -1;
  let logIdx = -1;
  let resultMarkdownIdx = -1;
  let resultCodeIdx = -1;

  // Look for code block after thought
  for (let i = thoughtIdx + 1; i < blocks.length; i++) {
    if (blocks[i].type === 'code' && blocks[i].content.trim()) {
      codeIdx = i;
      break;
    }
    // Skip empty markdown blocks between thought and code
    if (blocks[i].type === 'markdown' && blocks[i].content.trim()) break;
  }

  if (codeIdx === -1) return blocks; // No code block found — not a CodeAgent step

  // Look for optional execution logs after code
  for (let i = codeIdx + 1; i < blocks.length; i++) {
    if (blocks[i].type === 'log' && blocks[i].title === 'Execution Logs') {
      logIdx = i;
      break;
    }
    if (blocks[i].type === 'markdown' && blocks[i].content.trim()) {
      // Check if this is the Result markdown
      if (blocks[i].content.includes('**Result:**')) {
        resultMarkdownIdx = i;
      }
      break;
    }
  }

  // Look for optional result after log (or after code if no log)
  const searchFrom = logIdx !== -1 ? logIdx + 1 : codeIdx + 1;
  for (let i = searchFrom; i < blocks.length; i++) {
    if (blocks[i].type === 'markdown' && blocks[i].content.includes('**Result:**')) {
      resultMarkdownIdx = i;
      // Look for the result code block right after
      if (i + 1 < blocks.length && blocks[i + 1].type === 'code') {
        resultCodeIdx = i + 1;
      }
      break;
    }
    if (blocks[i].type === 'markdown' && blocks[i].content.trim()) break;
  }

  // Extract fields — strip "Thought:" prefix if present
  const rawThought = firstMeaningful.content.trim();
  const thought = rawThought.startsWith('Thought:') ? rawThought.replace(/^Thought:\s*/i, '').trim() : rawThought;
  const codeContent = blocks[codeIdx].content;
  const executionLogs = logIdx !== -1 ? blocks[logIdx].content : undefined;
  const result = resultCodeIdx !== -1 ? blocks[resultCodeIdx].content : undefined;

  // Determine which block indices were consumed
  const consumed = new Set<number>();
  consumed.add(thoughtIdx);
  consumed.add(codeIdx);
  if (logIdx !== -1) consumed.add(logIdx);
  if (resultMarkdownIdx !== -1) consumed.add(resultMarkdownIdx);
  if (resultCodeIdx !== -1) consumed.add(resultCodeIdx);
  // Also consume empty markdown blocks between thought and final consumed index
  const maxConsumed = Math.max(...consumed);
  for (let i = thoughtIdx; i <= maxConsumed; i++) {
    if (blocks[i].type === 'markdown' && !blocks[i].content.trim()) {
      consumed.add(i);
    }
  }

  // Build the merged codeStep block
  const codeStep: ContentBlock = {
    type: 'codeStep',
    content: thought, // Primary content is the thought for display
    thought,
    codeContent,
    executionLogs,
    result,
  };

  // Rebuild: codeStep + any unconsumed blocks
  const merged: ContentBlock[] = [codeStep];
  for (let i = 0; i < blocks.length; i++) {
    if (!consumed.has(i)) {
      merged.push(blocks[i]);
    }
  }

  return merged;
}

/**
 * Merge tool call invocations with their outputs by position.
 * Invocation = toolCall with no content (empty string). Output = toolCall with content.
 * Pairs them positionally: 1st invocation with 1st output, etc.
 * Handles multiple calls of the same tool correctly.
 */
export function mergeToolCallPairs(blocks: ContentBlock[]): ContentBlock[] {
  const invocations: ContentBlock[] = [];
  const outputs: ContentBlock[] = [];
  const nonToolCall: ContentBlock[] = [];

  for (const b of blocks) {
    if (b.type === 'toolCall') {
      if (!b.content) {
        invocations.push(b); // invocation: has toolArgs but no content
      } else if (!b.toolArgs) {
        outputs.push(b);     // output: has content but no toolArgs
      } else {
        // Already merged (has both)
        nonToolCall.push(b);
      }
    } else {
      nonToolCall.push(b);
    }
  }

  // Pair invocations with outputs positionally
  const merged: ContentBlock[] = [];
  const maxPairs = Math.max(invocations.length, outputs.length);
  for (let i = 0; i < maxPairs; i++) {
    const inv = invocations[i];
    const out = outputs[i];
    if (inv && out) {
      merged.push({
        type: 'toolCall',
        content: out.content,
        toolName: inv.toolName || out.toolName,
        toolArgs: inv.toolArgs,
      });
    } else if (inv) {
      merged.push(inv);
    } else if (out) {
      merged.push(out);
    }
  }

  // Tool calls first (rendered outside box), then content blocks
  return [...merged, ...nonToolCall];
}
