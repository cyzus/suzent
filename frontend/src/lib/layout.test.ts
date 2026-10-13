import { describe, expect, it } from 'vitest';
import {
  clampRightSidebarWidth,
  getCanvasSidebarWidth,
  getRightSidebarMaxWidth,
  shouldCollapseLeftSidebarOnRightOpen,
  shouldUseFullWidthRightSidebar,
} from './layout';

describe('resizable sidebar layout', () => {
  it('uses the actual left width when deciding whether both panels fit', () => {
    expect(shouldCollapseLeftSidebarOnRightOpen(1100, 480)).toBe(true);
    expect(shouldCollapseLeftSidebarOnRightOpen(1100, 320)).toBe(false);
    expect(shouldCollapseLeftSidebarOnRightOpen(1180, 480)).toBe(false);
  });

  it('preserves room for chat as the left panel gets wider', () => {
    expect(clampRightSidebarWidth(1000, 1440, 320)).toBe(768);
    expect(clampRightSidebarWidth(1000, 1440, 480)).toBe(608);
    expect(getCanvasSidebarWidth(1440, 480)).toBe(528);
  });

  it('lets all content grow beyond its default width, including on wide displays', () => {
    expect(getCanvasSidebarWidth(1440, 320)).toBe(616);
    expect(getRightSidebarMaxWidth(1440, 320)).toBe(768);
    expect(getCanvasSidebarWidth(3440, 320)).toBe(1400);
    expect(getRightSidebarMaxWidth(3440, 320)).toBe(2768);
  });

  it('switches to overlay exactly when minimum docked columns no longer fit', () => {
    expect(shouldUseFullWidthRightSidebar(1112, 480)).toBe(false);
    expect(getRightSidebarMaxWidth(1112, 480)).toBe(280);
    expect(shouldUseFullWidthRightSidebar(1111, 480)).toBe(true);
    expect(clampRightSidebarWidth(100, 1111, 480)).toBe(280);
  });
});
