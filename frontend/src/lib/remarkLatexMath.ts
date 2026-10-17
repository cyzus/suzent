import type { Plugin } from 'unified';
import type { Root } from 'mdast';
import type { State, Tokenizer } from 'micromark-util-types';
import type {} from 'remark-parse';
import type {} from 'mdast-util-math';

declare module 'micromark-util-types' {
  interface TokenTypeMap {
    latexMath: 'latexMath';
    latexMathData: 'latexMathData';
  }
}

// Tokenize before Markdown consumes backslash escapes; code and links retain
// their own parsing rules instead of being rewritten by a global replacement.
const tokenize: Tokenizer = function (effects, ok, nok) {
  let closing: number;
  const start: State = (code) => {
    effects.enter('latexMath');
    effects.enter('latexMathData');
    effects.consume(code);
    return opening;
  };
  const opening: State = (code) => {
    if (code !== 40 && code !== 91) return nok(code);
    closing = code === 40 ? 41 : 93;
    effects.consume(code);
    return inside;
  };
  const inside: State = (code) => {
    if (code === null) return nok(code);
    if (code === -5 || code === -4 || code === -3) {
      effects.exit('latexMathData');
      effects.enter('lineEnding');
      effects.consume(code);
      effects.exit('lineEnding');
      return afterLineEnding;
    }
    effects.consume(code);
    return code === 92 ? afterSlash : inside;
  };
  const afterLineEnding: State = (code) => {
    effects.enter('latexMathData');
    return inside(code);
  };
  const afterSlash: State = (code) => {
    if (code === closing) {
      effects.consume(code);
      effects.exit('latexMathData');
      effects.exit('latexMath');
      return ok;
    }
    return inside(code);
  };
  return start;
};

export const remarkLatexMath: Plugin<[], Root> = function () {
  const data = this.data();
  (data.micromarkExtensions ??= []).push({
    text: { 92: { name: 'latexMath', tokenize } },
  });
  (data.fromMarkdownExtensions ??= []).push({
    enter: {
      latexMath(token) {
        const source = this.sliceSerialize(token);
        const value = source.slice(2, -2).trim();
        this.enter(
          {
            type: 'inlineMath',
            value,
            data: {
              hName: 'code',
              hProperties: {
                className: ['language-math', source[1] === '[' ? 'math-display' : 'math-inline'],
              },
              hChildren: [{ type: 'text', value }],
            },
          },
          token
        );
        this.buffer();
      },
    },
    exit: {
      latexMath(token) {
        this.resume();
        this.exit(token);
      },
    },
  });
};
