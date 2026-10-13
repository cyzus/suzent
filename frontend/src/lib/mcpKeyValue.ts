/**
 * Parse the "KEY=value, KEY2=value2" text used for MCP headers and env vars.
 *
 * Only a comma (or newline) that starts a new `KEY=` pair separates entries, and
 * each pair splits on its first `=`, so values keep their own `=` and `,`
 * (base64 tokens, `Accept: a, b`).
 */
export function parseKeyValueList(raw: string): Record<string, string> | undefined {
  if (!raw.trim()) return undefined;
  const out: Record<string, string> = {};
  for (const pair of raw.split(/[,\n](?=\s*[A-Za-z_][\w.-]*\s*=)/)) {
    const eq = pair.indexOf('=');
    if (eq < 0) continue;
    const key = pair.slice(0, eq).trim();
    const value = pair.slice(eq + 1).trim();
    if (key && value) out[key] = value;
  }
  return Object.keys(out).length ? out : undefined;
}

export function formatKeyValueList(values: Record<string, string> | undefined): string {
  return Object.entries(values || {})
    .map(([k, v]) => `${k}=${v}`)
    .join(', ');
}
