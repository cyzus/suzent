import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MarkdownRenderer } from './MarkdownRenderer';

function renderStreaming(content: string, caret = true): string {
  return renderToStaticMarkup(<MarkdownRenderer content={content} streamingLite caret={caret} />);
}

/** The element the caret's ::after rule will attach to, given the markup. */
function lastBlockClasses(markup: string): string {
  const blocks = markup.match(/<(?:p|div|table)[^>]*class="[^"]*"/g) ?? [];
  return blocks[blocks.length - 1] ?? '';
}

// The caret used to be a sibling element rendered after the whole markdown
// block, which put it on its own line under the text. It is drawn as an
// ::after inside the final block instead, so what matters is that the block
// carries the marker class its caret rule expects.
describe('streaming caret', () => {
  it('marks the container only while streaming', () => {
    expect(renderStreaming('hello')).toContain('streaming-caret');
    expect(renderStreaming('hello', false)).not.toContain('streaming-caret');
  });

  it('ends on a plain paragraph, which takes the caret inline', () => {
    const markup = renderStreaming('Some prose still being written');
    // No marker class means the default rule applies: the caret joins the
    // paragraph's own inline flow, right after the last word.
    expect(lastBlockClasses(markup)).not.toMatch(/lite-(list-row|code|table)/);
  });

  it('tags a trailing list row so the caret goes in the text cell', () => {
    expect(lastBlockClasses(renderStreaming('- first\n- second'))).toContain('lite-list-row');
  });

  it('tags a trailing code block so the caret goes after the last character', () => {
    expect(renderStreaming('```js\nconst a = 1;')).toContain('lite-code');
  });

  it('tags a trailing table', () => {
    expect(renderStreaming('| a | b |\n| --- | --- |\n| 1 | 2 |')).toContain('lite-table');
  });
});
