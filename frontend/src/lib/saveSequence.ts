/**
 * Orders overlapping saves so a slow, older one never publishes its result
 * over a newer one's. Start each save with `begin()`, then hand its result
 * to `land()`, which returns the newest result landed so far.
 */
export class SaveSequence<T> {
  private started = 0;
  private landedTicket = 0;
  private landedValue: T | undefined;

  begin(): number {
    return ++this.started;
  }

  /** No save has started since this one. */
  isNewest(ticket: number): boolean {
    return ticket === this.started;
  }

  land(ticket: number, value: T): T {
    if (ticket > this.landedTicket) {
      this.landedTicket = ticket;
      this.landedValue = value;
    }
    return this.landedValue as T;
  }

  /** The newest result landed so far. */
  latest(): T | undefined {
    return this.landedValue;
  }
}
