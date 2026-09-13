"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useLocale, localePath } from "./locale";
import { messages } from "@/lib/messages";
import styles from "./landing/index.module.css";
function SuzentLogo() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="0" y="0" width="24" height="24" rx="4" fill="var(--h-text)" />
      <rect x="5" y="8" width="5" height="5" rx="1.5" fill="var(--h-bg)" />
      <rect x="14" y="8" width="5" height="5" rx="1.5" fill="var(--h-bg)" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="square"
    >
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="square"
    >
      <circle cx="12" cy="12" r="4" />
      <line x1="12" y1="2" x2="12" y2="5" />
      <line x1="12" y1="19" x2="12" y2="22" />
      <line x1="4.22" y1="4.22" x2="6.34" y2="6.34" />
      <line x1="17.66" y1="17.66" x2="19.78" y2="19.78" />
      <line x1="2" y1="12" x2="5" y2="12" />
      <line x1="19" y1="12" x2="22" y2="12" />
      <line x1="4.22" y1="19.78" x2="6.34" y2="17.66" />
      <line x1="17.66" y1="6.34" x2="19.78" y2="4.22" />
    </svg>
  );
}

/** Half sun / half moon — indicates "follow system preference". */
function AutoIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="square"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3v18" />
      <path d="M12 7a5 5 0 0 1 0 10" fill="currentColor" stroke="none" />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

export function SiteNav() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const colorModeChoice = mounted && theme !== "system" ? theme : null;
  const setColorMode = (value: string | null) => setTheme(value ?? "system");
  const locale = useLocale();
  const text = messages(locale);
  const pathname = usePathname();
  const i18n = {
    locales: ["en", "zh-Hans"],
    currentLocale: locale,
    defaultLocale: "en",
  };

  const otherLocale = i18n.locales.find((l) => l !== i18n.currentLocale);
  const otherLabel = otherLocale === "zh-Hans" ? "中文" : "EN";

  function switchLocaleHref(): string {
    if (!otherLocale) return "#";
    const stripped = pathname.replace(/^\/(zh-Hans)(\/|$)/, "/") || "/";
    return otherLocale === i18n.defaultLocale
      ? stripped
      : `/zh-Hans${stripped === "/" ? "/" : stripped}`;
  }

  // Cycle: auto → light → dark → auto
  function cycleTheme() {
    if (colorModeChoice === null) setColorMode("light");
    else if (colorModeChoice === "light") setColorMode("dark");
    else setColorMode(null);
  }

  const themeIcon =
    colorModeChoice === "light" ? (
      <SunIcon />
    ) : colorModeChoice === "dark" ? (
      <MoonIcon />
    ) : (
      <AutoIcon />
    );
  const themeLabel =
    colorModeChoice === "light"
      ? text.light
      : colorModeChoice === "dark"
        ? text.dark
        : text.auto;

  return (
    <nav className={styles.homeNav} aria-label={text.navigation}>
      <div className={styles.homeNavInner}>
        <Link href={localePath("/", locale)} className={styles.homeNavBrand}>
          <SuzentLogo />
          <span className={styles.homeNavTitle}>SUZENT</span>
        </Link>
        <div className={styles.homeNavLinks}>
          <Link
            href={localePath("/docs/getting-started/intro", locale)}
            className={styles.homeNavLink}
          >
            {text.docs}
          </Link>
          <Link
            href={localePath("/blog", locale)}
            className={styles.homeNavLink}
          >
            {text.blog}
          </Link>
          <Link
            href={localePath("/sovereign", locale)}
            className={styles.homeNavLink}
          >
            {text.manifesto}
          </Link>
          <div className={styles.homeNavUtils}>
            <a
              href="https://github.com/cyzus/suzent"
              className={styles.homeNavIconLink}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="GitHub"
            >
              <GitHubIcon />
            </a>
            {otherLocale && (
              <Link
                href={switchLocaleHref()}
                className={styles.homeNavIconLink}
                aria-label={text.language}
              >
                {otherLabel}
              </Link>
            )}
            <button
              className={styles.homeNavIconLink}
              onClick={cycleTheme}
              aria-label={`${text.theme}: ${themeLabel}`}
              title={themeLabel}
            >
              {themeIcon}
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
