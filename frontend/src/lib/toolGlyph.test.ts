import { describe, expect, it } from 'vitest';
import {
  ToolGlyphScene,
  pickToolSvgGlyphKind,
  toolGlyphMarkup,
  type ToolSvgGlyphKind,
} from '../../../packages/suzent-bot-core/src/toolGlyph';

describe('shared mechanical tool glyphs', () => {
  for (const kind of Object.keys(toolGlyphMarkup) as ToolSvgGlyphKind[]) {
    it(`${kind} animates internal shapes and freezes for reduced motion`, () => {
      const glyph = new ToolGlyphScene(kind);
      const first = glyph.frame(0, false);
      const later = glyph.frame(0.8, false);
      expect(first.viewBox).toBe('0 0 24 24');
      expect(first.nodes.length).toBeGreaterThan(0);
      expect(later.nodes).not.toEqual(first.nodes);
      expect(glyph.frame(10, true).nodes).toEqual(later.nodes);
      expect(glyph.frame(10, true).settled).toBe(true);
    });
  }
  it('keeps tool-specific silhouettes and approval priority', () => {
    expect(pickToolSvgGlyphKind('WebSearch', 'radar')).toBe('globe');
    expect(pickToolSvgGlyphKind('read_file', 'scan')).toBe('read');
    expect(pickToolSvgGlyphKind('read_file', 'pending')).toBe('pending');
    expect(pickToolSvgGlyphKind('create_tasks', 'snap')).toBe('tasks');
  });
});
