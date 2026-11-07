/** A second Run now is refused while a run is in flight or this action is still saving. */
export function canStartRun(running: boolean, pending: boolean): boolean {
  return !running && !pending;
}
