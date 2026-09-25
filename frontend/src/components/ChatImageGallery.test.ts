import { describe, expect, it, vi } from 'vitest';
import { collectChatImages } from './ChatImageGallery';

vi.stubGlobal('Node', { DOCUMENT_POSITION_FOLLOWING: 4 });
const node = (position: number, connected = true) =>
  ({
    isConnected: connected,
    position,
    compareDocumentPosition: (other: { position: number }) => (position < other.position ? 4 : 2),
  }) as unknown as HTMLElement;

describe('conversation image collection', () => {
  it('orders mixed image groups by message position rather than mount order', () => {
    const entries = [
      { node: node(3), sources: ['markdown.png'] },
      { node: node(1), sources: ['upload-a.png', 'upload-b.png'] },
      { node: node(2), sources: ['generated.png', 'upload-a.png'] },
      { node: node(0, false), sources: ['old-chat.png'] },
    ];
    expect(collectChatImages(entries, 'generated.png')).toEqual([
      'upload-a.png',
      'upload-b.png',
      'generated.png',
      'markdown.png',
    ]);
  });
  it('keeps a clicked image accessible before its registration effect runs', () => {
    expect(collectChatImages([], 'clicked.png')).toEqual(['clicked.png']);
  });
});
