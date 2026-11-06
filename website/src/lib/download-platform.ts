export type DownloadPlatform = "macos" | "windows" | "linux" | "ios" | "android";

export function detectDownloadPlatform(
  userAgent: string,
  platform: string,
  maxTouchPoints: number,
): DownloadPlatform | null {
  if (/iPhone|iPad|iPod/.test(userAgent) || (platform === "MacIntel" && maxTouchPoints > 1)) {
    return "ios";
  }
  if (/Android/.test(userAgent)) return "android";
  if (/Windows/.test(userAgent)) return "windows";
  if (/Mac/.test(userAgent)) return "macos";
  if (/Linux/.test(userAgent)) return "linux";
  return null;
}
