import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../i18n';
import { ClickableContent } from './ClickableContent';

function render(content: string, fileChipTone?: 'accent' | 'neutral'): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <ClickableContent
        content={content}
        onFileClick={() => undefined}
        fileChipTone={fileChipTone}
      />
    </I18nProvider>
  );
}

describe('ClickableContent', () => {
  it('renders serialized file mention tokens as a single file chip', () => {
    const html = render('参考这个 @[D:/workspace/enoxian/PAPER.md] 继续');

    expect(html).toContain('D:/workspace/enoxian/PAPER.md');
    expect(html).not.toContain('@[D:');
    expect(html).not.toContain('PAPER.md]');
  });

  it('keeps bare sandbox paths clickable', () => {
    const html = render('Open /workspace/enoxian/PAPER.md please');

    expect(html).toContain('/workspace/enoxian/PAPER.md');
  });

  it('renders a neutral file chip when embedded in a user message', () => {
    const html = render('参考 @[D:/workspace/enoxian/PAPER.md]', 'neutral');

    expect(html).toContain('bg-white');
    expect(html).toContain('dark:bg-zinc-900');
    expect(html).not.toContain('bg-brutal-yellow');
  });
});
