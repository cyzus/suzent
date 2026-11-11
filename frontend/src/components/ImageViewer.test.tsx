import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ImageViewer } from './ImageViewer';

vi.mock('../i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock('@headlessui/react', () => ({
  Dialog: Object.assign(
    ({ children }: { children: React.ReactNode }) => <div role="dialog">{children}</div>,
    {
      Panel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
      Title: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
    }
  ),
}));

describe('image viewer navigation', () => {
  it('opens at the selected image and shows its position and navigation controls', () => {
    const html = renderToStaticMarkup(
      <ImageViewer
        src="b.png"
        images={['a.png', 'b.png', 'c.png']}
        onNavigate={() => {}}
        onClose={() => {}}
      />
    );
    expect(html).toContain('src="b.png"');
    expect(html).toContain('role="dialog"');
    expect(html).toContain('imageViewer.close');
    expect(html).toContain('2 / 3');
    expect(html).toContain('imageViewer.previous');
    expect(html).toContain('imageViewer.next');
  });

  it('keeps single-image callers compatible without navigation controls', () => {
    const html = renderToStaticMarkup(<ImageViewer src="a.png" onClose={() => {}} />);
    expect(html).toContain('src="a.png"');
    expect(html).not.toContain('imageViewer.next');
    expect(renderToStaticMarkup(<ImageViewer src={null} onClose={() => {}} />)).toBe('');
  });
});
