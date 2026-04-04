export type DesktopPlatform = 'windows' | 'macos' | 'linux' | 'unknown';

export function detectDesktopPlatform(
  userAgent: string,
  platform: string,
): DesktopPlatform {
  const ua = userAgent.toLowerCase();
  const pf = platform.toLowerCase();

  if (pf.includes('mac') || ua.includes('mac os')) {
    return 'macos';
  }

  if (pf.includes('win') || ua.includes('windows')) {
    return 'windows';
  }

  if (pf.includes('linux') || ua.includes('linux') || ua.includes('x11')) {
    return 'linux';
  }

  return 'unknown';
}