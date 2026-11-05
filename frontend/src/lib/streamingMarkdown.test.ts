import { describe, expect, it } from 'vitest';
import { splitStreamingBlocks } from './streamingMarkdown';

describe('splitStreamingBlocks', () => {
  it('splits finished top-level blocks and keeps the tail last', () => {
    expect(splitStreamingBlocks('# Title\n\nFirst para.\n\nSecond, still typ')).toEqual([
      '# Title',
      'First para.',
      'Second, still typ',
    ]);
  });

  it('rejoins to the original text', () => {
    const md = 'a\n\n```py\nx = 1\n\ny = 2\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nend';
    expect(splitStreamingBlocks(md).join('\n\n')).toBe(md);
  });

  it('never splits inside a code fence, even an unclosed one', () => {
    expect(splitStreamingBlocks('Intro\n\n```ts\nconst a = 1;\n\nconst b = 2;')).toEqual([
      'Intro',
      '```ts\nconst a = 1;\n\nconst b = 2;',
    ]);
    expect(splitStreamingBlocks('~~~~\n```\n\nstill code\n~~~~\n\nafter')).toEqual([
      '~~~~\n```\n\nstill code\n~~~~',
      'after',
    ]);
  });

  it('never splits inside a display math block', () => {
    expect(splitStreamingBlocks('$$\na = b\n\nc = d\n$$\n\nafter')).toEqual([
      '$$\na = b\n\nc = d\n$$',
      'after',
    ]);
    expect(splitStreamingBlocks('$$x$$\n\nafter')).toEqual(['$$x$$', 'after']);
  });

  it('keeps loose lists and item continuations in one block', () => {
    expect(splitStreamingBlocks('- a\n\n- b\n\n  more of b\n\n1. one\n\n2. two')).toEqual([
      '- a\n\n- b\n\n  more of b\n\n1. one\n\n2. two',
    ]);
    expect(splitStreamingBlocks('> quote\n\n> more')).toEqual(['> quote\n\n> more']);
  });
});
