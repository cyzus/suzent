import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../i18n';
import { ClickableContent } from './ClickableContent';

function render(content: string): string {
    return renderToStaticMarkup(
        <I18nProvider>
            <ClickableContent content={content} onFileClick={() => undefined} />
        </I18nProvider>,
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
});
