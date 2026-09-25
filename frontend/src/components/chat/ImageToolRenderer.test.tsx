import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { groupActivityChunks } from './ActivityRail';
import { ImageResultGallery, getImageResultPaths } from './ImageResultGallery';
import { getImageToolPaths, ImageToolRenderer } from './ImageToolRenderer';

vi.mock('../../hooks/useChatStore', () => ({
  useChatStore: () => ({ currentChatId: 'chat-1', config: { sandbox_volumes: [] } }),
}));
vi.mock('../../lib/api', () => ({
  getApiBase: () => 'http://localhost:8000',
  getSandboxParams: (chatId: string, path: string) =>
    new URLSearchParams({ chat_id: chatId, path }).toString(),
}));
vi.mock('../../i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock('./MarkdownRenderer', () => ({
  MarkdownRenderer: ({ content }: { content: string }) => <p>{content}</p>,
}));

describe('image tool previews', () => {
  it('renders all generated images through the file endpoint and preserves the result', () => {
    const html = renderToStaticMarkup(
      <ImageToolRenderer
        toolName="generate_image"
        parsedArgs={{ prompt: 'A landscape' }}
        metadata={{ saved_paths: ['C:\\images\\a #1.png', '/workspace/images/b.png'] }}
        output="Generated two images."
      />
    );
    expect(html.match(/<img /g)).toHaveLength(2);
    expect(html).toContain('path=C%3A%5Cimages%5Ca+%231.png');
    expect(html).toContain('chat_id=chat-1');
    expect(html).toContain('Generated two images.');
    expect(html.match(/<button /g)).toHaveLength(2);
    expect(html).not.toContain('target=');
    expect(html).not.toContain('<a ');
  });

  it('prefers the resolved analysis path and falls back for older results', () => {
    const props = { toolName: 'analyze_image', parsedArgs: { image_path: 'photo.png' } };
    expect(getImageToolPaths(props)).toEqual(['photo.png']);
    expect(
      getImageToolPaths({ ...props, metadata: { image_path: '/workspace/photo.png' } })
    ).toEqual(['/workspace/photo.png']);
    const html = renderToStaticMarkup(<ImageToolRenderer {...props} output="A cat." />);
    expect(html).toContain('<img ');
    expect(html).toContain('A cat.');
  });

  it('handles failed generation and malformed metadata without rendering broken images', () => {
    expect(getImageToolPaths({ toolName: 'generate_image', parsedArgs: null })).toEqual([]);
    expect(
      getImageToolPaths({
        toolName: 'generate_image',
        parsedArgs: null,
        metadata: { saved_paths: [null, 1, '', 'a.png', 'a.png'] },
      })
    ).toEqual(['a.png']);
  });
});

it('renders edited outputs rather than source images', () => {
  expect(
    getImageToolPaths({
      toolName: 'edit_image',
      parsedArgs: { image_paths: ['source.png'] },
      metadata: { saved_paths: ['edited.png'] },
    })
  ).toEqual(['edited.png']);
});

it('shows successful outputs outside tool details, deduplicating paths and ignoring failures', () => {
  const output = JSON.stringify({ success: true, metadata: { saved_paths: ['result.png'] } });
  const html = renderToStaticMarkup(
    <ImageResultGallery
      calls={[
        { toolName: 'generate_image', output },
        { toolName: 'edit_image', output },
        {
          toolName: 'edit_image',
          output: JSON.stringify({ success: false, metadata: { saved_paths: ['failed.png'] } }),
        },
        { toolName: 'analyze_image', output },
        { toolName: 'edit_image', output: '{' },
      ]}
    />
  );
  expect(html.match(/<img /g)).toHaveLength(1);
  expect(html).not.toContain('<details');
  expect(html).not.toContain('failed.png');
});

it('ends a rail at each successful image result while preserving later tool and text order', () => {
  const output = JSON.stringify({
    success: true,
    message: 'Done',
    metadata: { saved_paths: ['a.png'] },
  });
  const parts = [
    { type: 'tool', toolName: 'read_file' },
    { type: 'tool', toolName: 'generate_image', output },
    { type: 'tool', toolName: 'analyze_image' },
    { type: 'tool', toolName: 'edit_image', output },
    { type: 'text', text: 'Final explanation' },
  ];
  const groups = groupActivityChunks(
    parts,
    (part) => part.type === 'tool',
    (part) => getImageResultPaths([part]).length > 0
  );
  expect(groups.map((group) => group.type)).toEqual(['activity', 'activity', 'single']);
  expect(
    groups
      .filter((group) => group.type === 'activity')
      .map((group) => group.chunks.map(({ chunk }) => chunk.toolName))
  ).toEqual([
    ['read_file', 'generate_image'],
    ['analyze_image', 'edit_image'],
  ]);
});
