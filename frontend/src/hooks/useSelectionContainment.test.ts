import { describe, expect, it } from 'vitest';
import { resolveClampTarget } from './useSelectionContainment';

const PRECEDING = 2;
const FOLLOWING = 4;
const CONTAINED_BY = 16;
const DISCONNECTED = 1;

/** Minimal stand-ins for DOM nodes; the suite runs without a DOM environment. */
function node(positionRelativeToContainer: number): Node {
  return { __pos: positionRelativeToContainer } as unknown as Node;
}

const container = {
  compareDocumentPosition: (other: Node) => (other as unknown as { __pos: number }).__pos,
} as unknown as Node;

describe('resolveClampTarget', () => {

  it('leaves a focus inside the container alone', () => {
    // Chrome reports CONTAINED_BY | FOLLOWING for a descendant.
    expect(resolveClampTarget(container, node(CONTAINED_BY | FOLLOWING))).toBeNull();
  });

  it('leaves the container itself alone', () => {
    expect(resolveClampTarget(container, container)).toBeNull();
  });

  it('clamps a focus that drifted above to the start', () => {
    expect(resolveClampTarget(container, node(PRECEDING))).toBe('start');
  });

  it('clamps a focus that drifted below to the end', () => {
    expect(resolveClampTarget(container, node(FOLLOWING))).toBe('end');
  });

  it('ignores a missing or disconnected focus node', () => {
    expect(resolveClampTarget(container, null)).toBeNull();
    expect(resolveClampTarget(container, node(DISCONNECTED))).toBeNull();
  });
});
