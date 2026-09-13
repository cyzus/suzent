export const locales = ["en", "zh-Hans"] as const;
export type Locale = (typeof locales)[number];
export function localePath(url: string, locale: Locale): string {
  if (!url.startsWith("/") || url.startsWith("//")) return url;
  const stripped = url.replace(/^\/zh-Hans(?=\/|$)/, "") || "/";
  return locale === "en"
    ? stripped
    : "/zh-Hans" + (stripped === "/" ? "" : stripped);
}
export function pathLocale(path: string): Locale {
  return /^\/zh-Hans(?:\/|$)/.test(path) ? "zh-Hans" : "en";
}
