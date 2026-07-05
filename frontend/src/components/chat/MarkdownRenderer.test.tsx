import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../../i18n';
import { MarkdownRenderer } from './MarkdownRenderer';

function render(content: string): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <MarkdownRenderer content={content} onFileClick={() => undefined} />
    </I18nProvider>,
  );
}

describe('MarkdownRenderer', () => {
  it('uses nested markdown link text for file buttons', () => {
    const html = render(
      '已完成深度调研，并整理成文档：[`docs/paper/RELATED_WORK_RESEARCH.md`](file:///D:/workspace/enoxian/docs/paper/RELATED_WORK_RESEARCH.md)',
    );

    expect(html).toContain('docs/paper/RELATED_WORK_RESEARCH.md');
    expect(html).not.toContain('[object Object]');
  });
});
