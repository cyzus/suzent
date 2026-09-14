import data from "../../.generated/content.json";
import type { Locale } from "./locales";
export type PageKind =
  | "redirect"
  | "doc"
  | "category"
  | "post"
  | "blog"
  | "archive"
  | "tags"
  | "tag"
  | "authors"
  | "author"
  | "home"
  | "sovereign"
  | "privacy"
  | "notfound";
export interface Page {
  kind: PageKind;
  url: string;
  canonicalPath: string;
  title: string;
  description?: string;
  redirectTo?: string;
  locale: Locale;
  content?: string;
  source?: string;
  translationSource?: string;
  translated: boolean;
  relative?: string;
  directory?: string;
  position?: number;
  date?: string;
  tags?: string[];
  authors?: string[];
  tag?: string;
  author?: string;
  toc?: { title: string; url: string; depth: number }[];
  searchText?: string;
}
export const pages = data.pages as Page[];
export const authors = data.authors as Record<
  string,
  { name: string; title: string; url: string; image_url: string }
>;
export function getPage(url: string): Page | undefined {
  return pages.find((page) => page.url === (url.replace(/\/$/, "") || "/"));
}
