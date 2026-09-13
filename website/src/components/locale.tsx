"use client";
import { usePathname } from "next/navigation";
import zh from "../../i18n/zh-Hans/code.json";
import { pathLocale } from "@/lib/locales";
export { localePath, type Locale } from "@/lib/locales";
export function useLocale() {
  return pathLocale(usePathname());
}
export function useTranslator() {
  const locale = useLocale();
  return ({ id, message }: { id: string; message: string }): string =>
    locale === "zh-Hans"
      ? ((zh as Record<string, { message: string }>)[id]?.message ?? message)
      : message;
}
