import type { Root, RootContent } from 'mdast';
import type { Plugin } from 'unified';

export const remarkCurrency: Plugin<[], Root> = function () {
  return (tree, file) => {
    const source = String(file.value);

    function restoreCurrency(node: Root | RootContent): void {
      if (!('children' in node)) return;

      node.children = node.children.map((child) => {
        if (child.type === 'inlineMath') {
          const start = child.position?.start.offset;
          const end = child.position?.end.offset;
          if (start !== undefined && end !== undefined) {
            const raw = source.slice(start, end);
            // An amount after the closing dollar means the parser paired two prices.
            if (/^\$\d/.test(raw) && /^\d/.test(source.slice(end))) {
              return { type: 'text', value: raw };
            }
          }
        }
        restoreCurrency(child);
        return child;
      });
    }

    restoreCurrency(tree);
  };
};
