import { useMemo } from 'react';
import type { Message } from '../types/api';
import { splitAssistantContent } from '../lib/chatUtils';

export interface WebHistoryLog {
  id: string; // Tool call ID
  type: 'search' | 'page';
  title: string;
  output: string;
  args?: string;
  timestamp: string;
  messageIndex: number;
}

export function useWebHistory(messages: Message[]): WebHistoryLog[] {
  return useMemo(() => {
    const history: WebHistoryLog[] = [];

    messages.forEach((msg, mIdx) => {
      // Only process assistant messages with content
      if (msg.role !== 'assistant' || !msg.content) return;
      
      const blocks = splitAssistantContent(msg.content);

      for (const block of blocks) {
        if (block.type === 'toolCall' && block.content && block.content.trim()) {
          if (block.toolName === 'web_search') {
            history.push({
              id: block.toolCallId || `search-${mIdx}-${history.length}`,
              type: 'search',
              title: extractSearchTitle(block.toolArgs),
              output: block.content, // tool output is stored in content for toolCall
              args: block.toolArgs,
              timestamp: msg.timestamp || new Date().toISOString(),
              messageIndex: mIdx
            });
          } else if (block.toolName === 'webpage_fetch') {
            history.push({
              id: block.toolCallId || `page-${mIdx}-${history.length}`,
              type: 'page',
              title: extractPageTitle(block.toolArgs),
              output: block.content,
              args: block.toolArgs,
              timestamp: msg.timestamp || new Date().toISOString(),
              messageIndex: mIdx
            });
          }
        }
      }
    });

    return history; // Oldest first
  }, [messages]);
}

function extractSearchTitle(args?: string): string {
  if (!args) return 'Web Search';
  try {
    const parsed = JSON.parse(args);
    return `\uD83D\uDD0D ${parsed.query || 'Unknown'}`;
  } catch {
    return '\uD83D\uDD0D Web Search';
  }
}

function extractPageTitle(args?: string): string {
  if (!args) return 'Web Page';
  try {
    const parsed = JSON.parse(args);
    let url = parsed.url || 'Unknown';
    try {
      if (url.startsWith('http')) {
        const urlObj = new URL(url);
        url = urlObj.hostname + (urlObj.pathname !== '/' ? urlObj.pathname.substring(0, 15) + '...' : '');
      }
    } catch { /* ignore */ }
    return `\uD83D\uDCC4 ${url}`;
  } catch {
    return '\uD83D\uDCC4 Web Page';
  }
}
