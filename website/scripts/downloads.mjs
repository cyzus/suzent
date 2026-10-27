import fs from "node:fs";

export const downloads = JSON.parse(
  fs.readFileSync(new URL("../content/downloads.json", import.meta.url), "utf8"),
);

export function selectAndroidRelease(releases) {
  const candidates = releases.flatMap((release) => {
    const match = /^mobile-v(\d+)\.(\d+)\.(\d+)$/.exec(release.tag_name);
    if (!match || release.draft || release.prerelease) return [];
    const version = match.slice(1).join(".");
    const name = `suzent-${version}-android.apk`;
    const asset = release.assets.find(
      (item) => item.name === name && item.state === "uploaded" && item.size > 0,
    );
    if (!asset) return [];
    return [{ version: match.slice(1).map(Number), url: asset.browser_download_url }];
  });
  candidates.sort((a, b) => {
    for (let i = 0; i < 3; i++) {
      if (a.version[i] !== b.version[i]) return b.version[i] - a.version[i];
    }
    return 0;
  });
  if (!candidates.length) throw new Error("No published mobile release with an Android APK");
  const url = candidates[0].url;
  if (!url.startsWith(`https://github.com/${downloads.repository}/releases/download/mobile-v`)) {
    throw new Error("Unexpected Android download URL");
  }
  return url;
}

export async function resolveAndroidDownload(fetcher = fetch) {
  const releases = [];
  for (let page = 1; ; page++) {
    const response = await fetcher(
      `https://api.github.com/repos/${downloads.repository}/releases?per_page=100&page=${page}`,
      {
        headers: {
          Accept: "application/vnd.github+json",
          ...(process.env.GITHUB_TOKEN
            ? { Authorization: `Bearer ${process.env.GITHUB_TOKEN}` }
            : {}),
        },
        signal: AbortSignal.timeout(30_000),
      },
    );
    if (!response.ok) throw new Error(`Cannot resolve Android release: HTTP ${response.status}`);
    const batch = await response.json();
    releases.push(...batch);
    if (batch.length < 100) break;
  }
  return selectAndroidRelease(releases);
}

export function downloadRedirect(url) {
  const safe = url.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex"><meta http-equiv="refresh" content="0;url=${safe}"><title>Suzent</title></head><body><a href="${safe}">Suzent</a></body></html>`;
}
