"use client";
import { useEffect, type ReactNode } from "react";
import { RootProvider } from "fumadocs-ui/provider/next";
import { useTheme } from "next-themes";
import { useLocale } from "./locale";
import { fumadocsTranslations } from "@/lib/messages";
function ThemeBridge() {
  const { resolvedTheme } = useTheme();
  const locale = useLocale();
  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.lang = locale;
  }, [resolvedTheme, locale]);
  return null;
}
export function Providers({ children }: { children: ReactNode }) {
  const locale = useLocale();
  return (
    <RootProvider
      search={{ enabled: false }}
      i18n={{
        locale,
        translations: fumadocsTranslations(locale),
      }}
    >
      <ThemeBridge />
      {children}
    </RootProvider>
  );
}
