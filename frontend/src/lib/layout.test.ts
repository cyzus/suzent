import { describe, expect, it } from 'vitest';
import {
  clampRightSidebarWidth,
  getCanvasSidebarWidth,
  shouldCollapseLeftSidebarOnRightOpen,
} from './layout';

describe('resizable sidebar layout', () => {
  it('uses the actual left width when deciding whether both panels fit', () => {
    expect(shouldCollapseLeftSidebarOnRightOpen(1100, 480)).toBe(true);
    expect(shouldCollapseLeftSidebarOnRightOpen(1100, 320)).toBe(false);
    expect(shouldCollapseLeftSidebarOnRightOpen(1180, 480)).toBe(false);
  });

  it('preserves room for chat as the left panel gets wider', () => {
    expect(clampRightSidebarWidth(720, 1440, 320)).toBe(540);
    expect(clampRightSidebarWidth(720, 1440, 480)).toBe(380);
    expect(getCanvasSidebarWidth(1440, 480)).toBe(528);
  });
});
