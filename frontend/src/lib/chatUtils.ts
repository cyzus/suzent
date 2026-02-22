
export interface ContentBlock {
  type: 'markdown' | 'code' | 'log' | 'toolCall';
  content: string;
  lang?: string;
  title?: string;
  toolName?: string;
  toolArgs?: string;
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

  return mergeToolCallPairs(converted);
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
