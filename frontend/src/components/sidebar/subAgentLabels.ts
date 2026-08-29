/**
 * Tools are registered under class-style names (`RunCommandTool`); the suffix
 * is noise on a chip. Naming what an agent can actually do reads as capability,
 * where a bare count only reads as a row in a ledger.
 */
export function toolLabel(name: string): string {
  return name.replace(/Tool$/, '');
}
