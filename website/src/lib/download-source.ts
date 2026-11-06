"use client";
import { useEffect, useState } from "react";
import downloads from "../../content/downloads.json";

export const GITHUB_LATEST =
  "https://github.com/cyzus/suzent/releases/latest/download";
export const MIRROR_RELEASES = "https://registry.npmmirror.com/-/binary/suzent";
const RELEASE_TAG = /^v(\d+)\.(\d+)\.(\d+)$/;
export const MS_STORE_URL = downloads.microsoftStore;

async function reachable(url: string, ms: number): Promise<boolean> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), ms);
  try {
    // An opaque response still proves the host answered.
    await fetch(url, {
      mode: "no-cors",
      cache: "no-store",
      signal: controller.signal,
    });
    return true;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timer);
  }
}

function newestMirroredTag(entries: unknown): string | null {
  if (!Array.isArray(entries)) return null;
  const versions = entries
    .map((entry) =>
      String((entry as { name?: unknown })?.name ?? "").replace(/\/$/, ""),
    )
    .filter((tag) => RELEASE_TAG.test(tag))
    .map((tag) => ({ tag, parts: tag.slice(1).split(".").map(Number) }));
  versions.sort(
    (a, b) =>
      b.parts[0] - a.parts[0] ||
      b.parts[1] - a.parts[1] ||
      b.parts[2] - a.parts[2],
  );
  return versions[0]?.tag ?? null;
}

/**
 * Where to download from, decided by the visitor's network rather than their
 * language: a browser that cannot reach Google but can reach npmmirror gets
 * the mainland mirror. Anything uncertain falls back to GitHub.
 */
export function useDownloadSource(): {
  china: boolean;
  mirrorTag: string | null;
} {
  const [source, setSource] = useState<{
    china: boolean;
    mirrorTag: string | null;
  }>({
    china: false,
    mirrorTag: null,
  });
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (await reachable("https://www.google.com/generate_204", 4000)) return;
      if (!(await reachable(`${MIRROR_RELEASES}/`, 4000))) return;
      let mirrorTag: string | null = null;
      try {
        const response = await fetch(`${MIRROR_RELEASES}/`, {
          cache: "no-store",
        });
        if (response.ok) mirrorTag = newestMirroredTag(await response.json());
      } catch {
        // Not mirrored yet, or the listing is not readable cross-origin.
      }
      if (!cancelled) setSource({ china: true, mirrorTag });
    })();
    return () => {
      cancelled = true;
    };
  }, []);
  return source;
}
