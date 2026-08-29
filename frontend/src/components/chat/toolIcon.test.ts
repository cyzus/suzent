import { describe, expect, it } from 'vitest';

import { getToolIcon, getToolIconClassName } from './toolIcon';

describe('tool icon helpers', () => {
  it('chooses the pending icon before tool name heuristics', () => {
    expect(getToolIcon('web_search', 'pending')).toBe('⏳');
  });

  it('maps tool names to the shared icon set', () => {
    expect(getToolIcon('web_search')).toBe('🔍');
    expect(getToolIcon('read_file')).toBe('📁');
  });

  it('gives delegation its own mark instead of the generic wrench', () => {
    expect(getToolIcon('agent')).toBe('🤖');
    expect(getToolIcon('subagent')).toBe('🤖');
  });

  it('reads a delegation as delegation even when its name mentions the web', () => {
    // Checked before the substring heuristics: a "web_agent" is an agent, not
    // a search box.
    expect(getToolIcon('web_agent')).toBe('🤖');
  });

  it('still falls back to the wrench for anything unrecognised', () => {
    expect(getToolIcon('some_unknown_tool')).toBe('🔧');
  });

  it('keeps the icon layout class consistent between collapsed and expanded states', () => {
    expect(getToolIconClassName(false, false)).toContain('tool-group-icon');
    expect(getToolIconClassName(true, false)).toContain('animate-pulse');
    expect(getToolIconClassName(true, true)).not.toContain('animate-pulse');
  });

  it('can force grouped icons into monochrome mode', () => {
    expect(getToolIconClassName(false, false, true)).toContain('tool-group-icon--mono');
    expect(getToolIconClassName(false, false, true)).not.toContain('animate-pulse');
  });
});
