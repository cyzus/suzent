import React from 'react';
import { Message } from '../types/api';
import { marked } from 'marked';

// Configure marked with custom renderer to preserve whitespace in code blocks
const renderer = new marked.Renderer();

renderer.code = function({ text, lang }: { text: string; lang?: string }) {
  // Preserve the code content exactly as-is, don't trim or modify
  const language = lang || 'python';
  // Return HTML that preserves all whitespace
  const escapedCode = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
  
  return `<pre class="language-${language}"><code class="language-${language}">${escapedCode}</code></pre>`;
};

marked.setOptions({
  breaks: true, // Convert \n to <br>
  gfm: true, // GitHub Flavored Markdown
  renderer: renderer,
});

export const MessageBubble: React.FC<{ message: Message }> = ({ message }) => {
  // Parse markdown
  const htmlContent = marked.parse(message.content) as string;
  
  return (
    <div className={message.role === 'user' ? 'text-right' : 'text-left'}>
      <div className={`inline-block max-w-3xl rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${message.role === 'user' ? 'bg-brand-600 text-white' : 'bg-neutral-800 text-neutral-100'} `}>
        <div dangerouslySetInnerHTML={{ __html: htmlContent }} />
      </div>
    </div>
  );
};
