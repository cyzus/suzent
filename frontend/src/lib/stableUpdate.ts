/**
 * Helpers that hand React back the previous value when a poll returned the
 * same data, so a background refresh that changed nothing does not re-render
 * every subscriber.
 */

export function shallowEqual<T extends object>(a: T, b: T): boolean {
  if (a === b) return true;
  const aKeys = Object.keys(a) as (keyof T)[];
  if (aKeys.length !== Object.keys(b).length) return false;
  return aKeys.every((key) => Object.is(a[key], b[key]));
}

export function stableObject<T extends object>(prev: T, next: T): T {
  return shallowEqual(prev, next) ? prev : next;
}

/**
 * Reuse each item of `prev` that is shallow-equal to the item at the same
 * position in `next`, and `prev` itself when every item matched.
 */
export function stableList<T extends object>(prev: T[], next: T[]): T[] {
  let changed = prev.length !== next.length;
  const merged = next.map((item, index) => {
    const old = prev[index];
    if (old !== undefined && shallowEqual(old, item)) return old;
    changed = true;
    return item;
  });
  return changed ? merged : prev;
}
