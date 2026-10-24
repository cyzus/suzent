// Mirrors is_quiet_reply in suzent/core/heartbeat.py: the token the agent
// answers with when a background turn has nothing to report.
const QUIET_TOKEN = 'HEARTBEAT_OK';
const QUIET_ASIDE_CHARS = 300;

export function isQuietReply(text: string | undefined | null): boolean {
  const trimmed = (text ?? '').trim();
  let aside: string;
  if (trimmed.startsWith(QUIET_TOKEN)) {
    aside = trimmed.slice(QUIET_TOKEN.length);
  } else if (trimmed.endsWith(QUIET_TOKEN)) {
    aside = trimmed.slice(0, -QUIET_TOKEN.length);
  } else {
    return false;
  }
  return aside.trim().length <= QUIET_ASIDE_CHARS;
}
